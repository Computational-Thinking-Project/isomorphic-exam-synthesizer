"""Unit and Lifecycle Integration Tests for Stage 3 Review Lifecycle (TASK-301).

Implements 18 critical test cases:
1. test_zero_connection_during_ai_call
2. test_tx2_retry_idempotency
3. test_emergency_rollback_after_network_partition
4. test_emergency_rollback_cannot_double_refund
5. test_stale_guard_cannot_double_refund_tx2
6. test_multi_version_required_count_invariant
7. test_reserve_at_calls_26
8. test_reserve_at_calls_27_blocked
9. test_revert_never_regenerated_question
10. test_accept_parallel_with_regenerating
11. test_revert_idempotency
12. test_ai_timeout_immediate_rollback
13. test_update_before_insert_ordering
14. test_idor_cross_session
15. test_revert_does_not_change_required_count
16. test_can_finalize_logic
17. test_review_logs_created_on_all_actions
18. test_reject_or_revert_unsets_is_finalized
"""

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.models.schemas import ReserveResult, ReviewDomainException, ReviewProgressResponse
from app.services.review.repository import ReviewRepository, _now_iso
from app.services.review.service import ReviewService, session_lock_registry

_GLOBAL_MOCK_LOCK = threading.RLock()


class MockExecutionResult:
    """Mock result of supabase query execution."""

    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class MockTableQueryBuilder:
    """Fluent mock builder simulating PostgREST table queries in-memory."""

    def __init__(
        self,
        table_name: str,
        db_state: Dict[str, List[Dict[str, Any]]],
        call_log: List[Dict[str, Any]],
    ) -> None:
        self.table_name = table_name
        self.db_state = db_state
        self.call_log = call_log
        self.op = "select"
        self.payload: Any = None
        self.filters: List[tuple[str, str, Any]] = []
        self.limit_val: Optional[int] = None

    def select(self, cols: str = "*") -> "MockTableQueryBuilder":
        self.op = "select"
        return self

    def update(self, values: Dict[str, Any]) -> "MockTableQueryBuilder":
        self.op = "update"
        self.payload = values
        return self

    def insert(self, values: Any) -> "MockTableQueryBuilder":
        self.op = "insert"
        self.payload = values
        return self

    def delete(self) -> "MockTableQueryBuilder":
        self.op = "delete"
        return self

    def eq(self, field: str, val: Any) -> "MockTableQueryBuilder":
        self.filters.append((field, "eq", val))
        return self

    def neq(self, field: str, val: Any) -> "MockTableQueryBuilder":
        self.filters.append((field, "neq", val))
        return self

    def in_(self, field: str, vals: List[Any]) -> "MockTableQueryBuilder":
        self.filters.append((field, "in", vals))
        return self

    def limit(self, n: int) -> "MockTableQueryBuilder":
        self.limit_val = n
        return self

    def order(self, field: str, *args: Any, **kwargs: Any) -> "MockTableQueryBuilder":
        return self

    def _matches(self, row: Dict[str, Any]) -> bool:
        for field, op, val in self.filters:
            actual = None
            if "." in field:
                parts = field.split(".")
                curr: Any = row
                for p in parts:
                    if isinstance(curr, dict):
                        curr = curr.get(p)
                    else:
                        curr = None
                        break
                actual = curr
                if actual is None and field == "exam_versions.session_id":
                    v_id = row.get("version_id")
                    for v in self.db_state.get("exam_versions", []):
                        if str(v.get("id")) == str(v_id):
                            actual = v.get("session_id")
                            break
            else:
                actual = row.get(field)

            if op == "eq":
                if str(actual) != str(val) and actual != val:
                    return False
            elif op == "neq":
                if str(actual) == str(val) or actual == val:
                    return False
            elif op == "in":
                val_strs = [str(v) for v in val]
                if str(actual) not in val_strs and actual not in val:
                    return False
        return True

    def execute(self) -> MockExecutionResult:
        with _GLOBAL_MOCK_LOCK:
            rows = self.db_state.setdefault(self.table_name, [])

            if self.op == "select":
                matched = [r for r in rows if self._matches(r)]
                if self.limit_val is not None:
                    matched = matched[: self.limit_val]
                self.call_log.append(
                    {
                        "op": "select",
                        "table": self.table_name,
                        "filters": list(self.filters),
                        "count": len(matched),
                    }
                )
                return MockExecutionResult(matched)

            elif self.op == "update":
                updated = []
                for r in rows:
                    if self._matches(r):
                        r.update(self.payload)
                        updated.append(dict(r))
                self.call_log.append(
                    {
                        "op": "update",
                        "table": self.table_name,
                        "payload": dict(self.payload),
                        "filters": list(self.filters),
                        "count": len(updated),
                    }
                )
                return MockExecutionResult(updated)

            elif self.op == "insert":
                to_insert = self.payload if isinstance(self.payload, list) else [self.payload]
                inserted = []
                # Unique constraint enforcement for table simulation (e.g. attempt_id on review_attempts)
                for item in to_insert:
                    item_copy = dict(item)
                    if self.table_name == "review_attempts":
                        att_id = str(item_copy.get("attempt_id", ""))
                        if att_id and any(str(r.get("attempt_id", "")) == att_id for r in rows):
                            # ON CONFLICT DO NOTHING: skip inserting duplicate attempt_id
                            continue
                    rows.append(item_copy)
                    inserted.append(item_copy)
                self.call_log.append(
                    {
                        "op": "insert",
                        "table": self.table_name,
                        "payload": inserted[0] if len(inserted) == 1 else inserted,
                    }
                )
                return MockExecutionResult(inserted)

            elif self.op == "delete":
                remaining = []
                deleted = []
                for r in rows:
                    if self._matches(r):
                        deleted.append(dict(r))
                    else:
                        remaining.append(r)
                self.db_state[self.table_name] = remaining
                self.call_log.append(
                    {
                        "op": "delete",
                        "table": self.table_name,
                        "filters": list(self.filters),
                        "count": len(deleted),
                    }
                )
                return MockExecutionResult(deleted)

            return MockExecutionResult([])


class MockRpcQueryBuilder:
    """Fluent mock builder simulating PostgreSQL RPC Stored Procedure executions."""

    def __init__(
        self,
        function_name: str,
        params: Dict[str, Any],
        db_state: Dict[str, List[Dict[str, Any]]],
        call_log: List[Dict[str, Any]],
    ) -> None:
        self.function_name = function_name
        self.params = params or {}
        self.db_state = db_state
        self.call_log = call_log

    def execute(self) -> MockExecutionResult:
        with _GLOBAL_MOCK_LOCK:
            self.call_log.append(
                {"op": "rpc", "function": self.function_name, "params": dict(self.params)}
            )

            if self.function_name == "finalize_approve_session":
                session_id = str(self.params.get("p_session_id", ""))
                user_id = str(self.params.get("p_user_id", ""))
                sessions = self.db_state.get("exam_sessions", [])
                s_row = next((s for s in sessions if str(s.get("id")) == session_id), None)
                if not s_row:
                    raise RuntimeError("ERR_SESSION_NOT_FOUND")

                status = str(s_row.get("status", "")).lower()
                if status == "approved":
                    return MockExecutionResult(
                        [
                            {
                                "status": "approved",
                                "session_id": session_id,
                                "approved_at": s_row.get("approved_at"),
                            }
                        ]
                    )
                if status not in ("reviewed", "generated"):
                    raise RuntimeError("ERR_INVALID_SESSION_STATE")

                # Optimistic locking check against concurrent mutation
                exp_updated = self.params.get("p_expected_updated_at")
                if exp_updated and s_row.get("updated_at") != exp_updated:
                    raise RuntimeError("ERR_INVALID_SESSION_STATE")

                # Check question and version status invariants inside lock
                vqs = self.db_state.get("version_questions", [])
                evs = self.db_state.get("exam_versions", [])
                session_v_ids = {
                    str(v.get("id")) for v in evs if str(v.get("session_id")) == session_id
                }

                unfinalized = [
                    v
                    for v in evs
                    if str(v.get("session_id")) == session_id and not v.get("is_finalized")
                ]
                if unfinalized:
                    raise RuntimeError("ERR_VERSIONS_NOT_FINALIZED")

                session_qs = [
                    q
                    for q in vqs
                    if str(q.get("version_id")) in session_v_ids and q.get("is_current")
                ]
                if not session_qs:
                    raise RuntimeError("ERR_NOT_ALL_QUESTIONS_APPROVED")
                if any(str(q.get("status")).lower() == "regenerating" for q in session_qs):
                    raise RuntimeError("ERR_QUESTION_REGENERATING")
                if any(str(q.get("status")).lower() != "approved" for q in session_qs):
                    raise RuntimeError("ERR_NOT_ALL_QUESTIONS_APPROVED")

                # Atomic mutation
                now_str = _now_iso()
                s_row["status"] = "approved"
                s_row["approved_at"] = now_str
                s_row["updated_at"] = now_str

                logs = self.db_state.setdefault("review_logs", [])
                logs.append(
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "action_type": "APPROVE_ALL",
                        "reason": "Session finalized and locked",
                        "created_at": now_str,
                    }
                )
                return MockExecutionResult(
                    [{"status": "approved", "approved_at": now_str, "session_id": session_id}]
                )

            if self.function_name == "review_reserve_regeneration":
                session_id = str(self.params.get("p_session_id", ""))
                question_id = str(self.params.get("p_question_id", ""))
                user_id = str(self.params.get("p_user_id", ""))
                operation_id = self.params.get("p_operation_id")

                sessions = self.db_state.get("exam_sessions", [])
                s_row = next((s for s in sessions if str(s.get("id")) == session_id), None)
                if not s_row:
                    raise RuntimeError("ERR_SESSION_NOT_FOUND")

                status = str(s_row.get("status", "")).lower()
                if status in ("approved", "exported"):
                    raise RuntimeError("ERR_SESSION_LOCKED")

                gemini_calls = int(s_row.get("gemini_review_calls", 0) or 0)
                if gemini_calls >= 30:
                    raise RuntimeError("ERR_REVIEW_QUOTA_EXHAUSTED")

                vqs = self.db_state.get("version_questions", [])
                evs = self.db_state.get("exam_versions", [])
                session_v_ids = {
                    str(v.get("id")) for v in evs if str(v.get("session_id")) == session_id
                }

                # Model A concurrency: max 1 active regenerating question per session
                active_regen = [
                    q
                    for q in vqs
                    if (not session_v_ids or str(q.get("version_id")) in session_v_ids)
                    and str(q.get("status")).lower() == "regenerating"
                ]
                if active_regen:
                    raise RuntimeError("ERR_SESSION_BUSY_REGENERATING")

                q_row = next((q for q in vqs if str(q.get("id")) == question_id), None)
                if not q_row:
                    raise RuntimeError("ERR_QUESTION_NOT_FOUND")
                if not q_row.get("is_current"):
                    raise RuntimeError("ERR_QUESTION_NOT_CURRENT")
                if str(q_row.get("status", "")).lower() == "regenerating":
                    raise RuntimeError("ERR_QUESTION_BUSY")

                now_str = _now_iso()
                q_row["status"] = "regenerating"
                q_row["updated_at"] = now_str
                s_row["updated_at"] = now_str

                return MockExecutionResult(
                    [
                        {
                            "status": "ok",
                            "question_id": question_id,
                            "session_id": session_id,
                            "operation_id": operation_id,
                        }
                    ]
                )

            return MockExecutionResult([])


class MockSupabaseClient:
    """Mock Supabase client providing stateful in-memory tables and query call logs."""

    def __init__(self, initial_state: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        self.state: Dict[str, List[Dict[str, Any]]] = initial_state or {}
        self.call_log: List[Dict[str, Any]] = []

    def table(self, table_name: str) -> MockTableQueryBuilder:
        return MockTableQueryBuilder(table_name, self.state, self.call_log)

    def rpc(
        self, function_name: str, params: Optional[Dict[str, Any]] = None
    ) -> MockRpcQueryBuilder:
        return MockRpcQueryBuilder(function_name, params or {}, self.state, self.call_log)


def _setup_standard_session_state(
    session_id: str,
    user_id: str,
    gemini_calls: int = 0,
    session_status: str = "generated",
    version_id: str = "ver-001",
    source_id: str = "src-001",
    question_id: str = "vq-001",
    question_status: str = "pending_review",
    is_reverted: bool = False,
    regenerated_from_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Helper to initialize standard database state for tests."""
    return {
        "exam_sessions": [
            {
                "id": session_id,
                "user_id": user_id,
                "status": session_status,
                "gemini_review_calls": gemini_calls,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "exam_versions": [
            {
                "id": version_id,
                "session_id": session_id,
                "version_code": "101",
                "is_finalized": False,
            }
        ],
        "source_questions": [
            {
                "id": source_id,
                "raw_content": "Câu 1: Giải phương trình $x^2 - 4 = 0$",
                "options": ["A. $x = \\pm 2$", "B. $x = 2$", "C. $x = -2$", "D. Vô nghiệm"],
                "correct_key": "A",
                "solution_md": "Lời giải chi tiết câu gốc.",
            }
        ],
        "question_blueprints": [
            {
                "id": "bp-001",
                "source_question_id": source_id,
                "variables": {"a": 4},
                "domains": {"a": "[1, 10]"},
                "invariants": ["a > 0"],
                "variation_modes": ["numerical"],
            }
        ],
        "version_questions": [
            {
                "id": question_id,
                "version_id": version_id,
                "source_question_id": source_id,
                "question_no": 1,
                "content": "Câu 1: Giải phương trình $x^2 - 9 = 0$",
                "options": ["A. $x = \\pm 3$", "B. $x = 3$", "C. $x = -3$", "D. Vô nghiệm"],
                "correct_key": "A",
                "solution_md": "Lời giải biến thể 1",
                "canonical_question_no": 1,
                "canonical_options": [
                    "A. $x = \\pm 3$",
                    "B. $x = 3$",
                    "C. $x = -3$",
                    "D. Vô nghiệm",
                ],
                "canonical_correct_key": "A",
                "canonical_solution_md": "Lời giải",
                "status": question_status,
                "is_current": True,
                "is_reverted": is_reverted,
                "regenerated_from_id": regenerated_from_id,
                "regeneration_id": None,
                "validation_report": {"is_valid": True},
                "exam_versions": {"session_id": session_id, "is_finalized": False},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "review_logs": [],
    }


# ==============================================================================
# 18 Test Cases Specification
# ==============================================================================


@pytest.mark.asyncio
async def test_zero_connection_during_ai_call():
    """Test 1: Zero connection pool checkout & lock released during AI call."""
    session_id = "00000000-0000-0000-0000-000000000001"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    lock_checked = False

    async def mock_ai_generator(**kwargs):
        nonlocal lock_checked
        # Verify that the session lock is NOT held during the AI generation phase
        lock = session_lock_registry.get_lock(UUID(session_id))
        assert not lock.locked(), "Lock must be released before invoking AI"
        lock_checked = True
        return {
            "content": "Câu mới được sinh",
            "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
            "correct_key": "A",
            "solution_md": "HDG",
            "validation_report": {"is_valid": True},
            "api_calls_count": 1,
        }

    service = ReviewService(db, ai_generator=mock_ai_generator)
    res = await service.reject_question(session_id, q_id, user_id)

    assert lock_checked is True
    assert res.status == "pending_review"
    assert res.question_id != q_id


@pytest.mark.asyncio
async def test_tx2_retry_idempotency():
    """Test 2: TX2 retry with same regeneration_id is idempotent (no duplicate insert/refund)."""
    session_id = "00000000-0000-0000-0000-000000000002"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=1)
    # Set status to regenerating (simulating TX1 has completed)
    state["version_questions"][0]["status"] = "regenerating"
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    old_snapshot = state["version_questions"][0]
    new_data = {
        "content": "Đề mới",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "correct_key": "A",
        "solution_md": "Lời giải",
        "validation_report": {"is_valid": True},
    }
    regen_id = uuid4()

    # Call 1: Success
    res1 = await repo.complete_regeneration_tx(
        session_id=session_id,
        old_q_snapshot=old_snapshot,
        new_data=new_data,
        regeneration_id=regen_id,
        actual_calls=1,
        user_id=user_id,
    )
    assert res1 is not None
    assert str(res1["regeneration_id"]) == str(regen_id)

    # Check quota after Call 1: Architecture A retains 1 committed call
    session_row = state["exam_sessions"][0]
    assert session_row["gemini_review_calls"] == 1
    insert_count_after_call1 = len(
        [c for c in db.call_log if c["op"] == "insert" and c["table"] == "version_questions"]
    )
    assert insert_count_after_call1 == 1

    # Call 2: Duplicate TX2 retry with identical regeneration_id
    res2 = await repo.complete_regeneration_tx(
        session_id=session_id,
        old_q_snapshot=old_snapshot,
        new_data=new_data,
        regeneration_id=regen_id,
        actual_calls=1,
        user_id=user_id,
    )
    assert res2 is not None
    assert res2["id"] == res1["id"]
    # Verify no additional insert occurred
    insert_count_after_call2 = len(
        [c for c in db.call_log if c["op"] == "insert" and c["table"] == "version_questions"]
    )
    assert insert_count_after_call2 == 1
    assert session_row["gemini_review_calls"] == 1


@pytest.mark.asyncio
async def test_emergency_rollback_after_network_partition():
    """Test 3: AI succeeds but TX2 retry exhausted -> Emergency Rollback retains committed calls and resets question."""
    session_id = "00000000-0000-0000-0000-000000000003"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    async def mock_ai_generator(**kwargs):
        op_id = kwargs.get("operation_id")
        acquire_cb = kwargs.get("acquire_attempt")
        if op_id and callable(acquire_cb):
            await acquire_cb(op_id, uuid4())
        return {
            "content": "Câu mới",
            "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
            "correct_key": "A",
            "validation_report": {"is_valid": True},
            "api_calls_count": 1,
        }

    service = ReviewService(db, ai_generator=mock_ai_generator)

    # Force repo.complete_regeneration_tx to fail
    async def fail_tx2(*args, **kwargs):
        raise ConnectionError("Network partition during TX2")

    service.repo.complete_regeneration_tx = fail_tx2  # type: ignore

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 500
    assert exc_info.value.error_code == "ERR_DB_PERSISTENCE_FAILED"

    # Verify quota charges 1 dispatched call (Architecture A does not refund committed permit)
    session_row = state["exam_sessions"][0]
    assert session_row["gemini_review_calls"] == 1

    # Verify old question reverted to pending_review
    q_row = state["version_questions"][0]
    assert q_row["status"] == "pending_review"


@pytest.mark.asyncio
async def test_emergency_rollback_cannot_double_refund():
    """Test 4: If TX2 already committed, subsequent emergency rollback returns False and does not refund."""
    session_id = "00000000-0000-0000-0000-000000000004"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=3)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    regen_id = uuid4()
    # Simulate TX2 already succeeded: new row exists with regeneration_id
    state["version_questions"].append(
        {
            "id": "new-vq-002",
            "version_id": "ver-001",
            "source_question_id": "src-001",
            "regeneration_id": str(regen_id),
            "status": "pending_review",
            "is_current": True,
        }
    )
    # Old question is already rejected/archived
    state["version_questions"][0]["status"] = "rejected"
    state["version_questions"][0]["is_current"] = False

    # Attempt emergency rollback with that regen_id
    rolled_back = await repo.emergency_rollback_tx(
        session_id=session_id,
        old_question_id=q_id,
        regeneration_id=regen_id,
        error_msg="Late timeout",
        user_id=user_id,
    )

    assert rolled_back is False
    # Quota remains 3, not refunded
    assert state["exam_sessions"][0]["gemini_review_calls"] == 3


@pytest.mark.asyncio
async def test_stale_guard_cannot_double_refund_tx2():
    """Test 5: Stale guard checks rowcount; resets status without corrupting quota."""
    session_id = "00000000-0000-0000-0000-000000000005"
    user_id = "user-123"
    q_id = "vq-001"
    # Question updated 10 minutes ago
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=3)
    state["version_questions"][0]["status"] = "regenerating"
    state["version_questions"][0]["updated_at"] = "2026-01-01T00:00:00Z"
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    # First run of stale recovery recovers 1 item
    recovered = await repo.recover_stale_questions()
    assert recovered == 1
    # Architecture A: committed quota is retained
    assert state["exam_sessions"][0]["gemini_review_calls"] == 3
    assert state["version_questions"][0]["status"] == "pending_review"

    # Second concurrent or repeated run finds status is pending_review (not regenerating)
    recovered_again = await repo.recover_stale_questions()
    assert recovered_again == 0
    # Quota stays 3
    assert state["exam_sessions"][0]["gemini_review_calls"] == 3


@pytest.mark.asyncio
async def test_multi_version_required_count_invariant():
    """Test 6: Multi-version required count invariant calculates 6, not 3, for 2 versions sharing 3 questions."""
    session_id = "00000000-0000-0000-0000-000000000006"
    user_id = "user-123"
    state = _setup_standard_session_state(session_id, user_id)
    # Add second version
    state["exam_versions"].append(
        {
            "id": "ver-002",
            "session_id": session_id,
            "version_code": "102",
            "is_finalized": False,
        }
    )
    # Setup 6 questions: 3 source questions across 2 versions
    state["version_questions"] = []
    for v_id in ["ver-001", "ver-002"]:
        for s_idx in [1, 2, 3]:
            state["version_questions"].append(
                {
                    "id": f"vq-{v_id}-s{s_idx}",
                    "version_id": v_id,
                    "source_question_id": f"src-00{s_idx}",
                    "status": "pending_review",
                    "is_current": True,
                    "exam_versions": {"session_id": session_id, "is_finalized": False},
                }
            )

    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)
    progress = await repo.get_review_progress_data(session_id)

    # Must be 6 distinct (version_id, source_question_id) pairs!
    assert progress["required_count"] == 6
    assert progress["current_count"] == 6
    assert progress["approved_count"] == 0
    assert progress["is_complete"] is False


@pytest.mark.asyncio
async def test_reserve_at_calls_26():
    """Test 7: At 26 calls, TX1 permits reservation without pre-incrementing quota."""
    session_id = "00000000-0000-0000-0000-000000000007"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=26)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    res = await repo.reserve_max_quota_and_start_regenerating(session_id, q_id, user_id)
    assert res == ReserveResult.OK
    # Quota remains 26 in TX1 (Architecture A pure per-acquire)
    assert state["exam_sessions"][0]["gemini_review_calls"] == 26
    assert state["version_questions"][0]["status"] == "regenerating"

    # Subsequent acquire_attempt increments quota to 27
    permit = await repo.acquire_attempt(uuid4(), uuid4())
    assert permit.dispatch_permitted is True
    assert permit.calls_used == 27
    assert state["exam_sessions"][0]["gemini_review_calls"] == 27


@pytest.mark.asyncio
async def test_reserve_at_calls_30_blocked():
    """Test 8: At 30 calls, session quota is fully exhausted -> 429 Error at TX1."""
    session_id = "00000000-0000-0000-0000-000000000008"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=30)
    db = MockSupabaseClient(state)
    service = ReviewService(db, ai_generator=AsyncMock())

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 429
    assert exc_info.value.error_code == "ERR_REVIEW_QUOTA_EXHAUSTED"
    # Quota remained 30
    assert state["exam_sessions"][0]["gemini_review_calls"] == 30


@pytest.mark.asyncio
async def test_revert_never_regenerated_question():
    """Test 9: Reverting an original question that was never regenerated raises 400 Bad Request."""
    session_id = "00000000-0000-0000-0000-000000000009"
    user_id = "user-123"
    q_id = "vq-001"
    # regenerated_from_id is None, is_reverted is False
    state = _setup_standard_session_state(
        session_id, user_id, question_id=q_id, regenerated_from_id=None, is_reverted=False
    )
    db = MockSupabaseClient(state)
    service = ReviewService(db, ai_generator=AsyncMock())

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.revert_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "ERR_QUESTION_NOT_REGENERATED"


@pytest.mark.asyncio
async def test_accept_parallel_with_regenerating():
    """Test 10: Accepting Q2 while Q1 is regenerating proceeds immediately with 200 OK."""
    session_id = "00000000-0000-0000-0000-000000000010"
    user_id = "user-123"
    state = _setup_standard_session_state(
        session_id, user_id, question_id="vq-001", question_status="regenerating"
    )
    # Add Q2
    state["version_questions"].append(
        {
            "id": "vq-002",
            "version_id": "ver-001",
            "source_question_id": "src-002",
            "question_no": 2,
            "content": "Câu 2",
            "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
            "correct_key": "B",
            "status": "pending_review",
            "is_current": True,
            "is_reverted": False,
            "exam_versions": {"session_id": session_id, "is_finalized": False},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db = MockSupabaseClient(state)
    service = ReviewService(db)

    # Accept Q2
    res = await service.accept_question(session_id, "vq-002", user_id)
    assert res.question_id == "vq-002"
    assert res.status == "approved"
    # Q1 remains regenerating
    assert state["version_questions"][0]["status"] == "regenerating"


@pytest.mark.asyncio
async def test_revert_idempotency():
    """Test 11: Reverting already reverted question returns 200 OK idempotently."""
    session_id = "00000000-0000-0000-0000-000000000011"
    user_id = "user-123"
    q_id = "vq-reverted-001"
    state = _setup_standard_session_state(
        session_id,
        user_id,
        question_id=q_id,
        question_status="approved",
        is_reverted=True,
        regenerated_from_id="vq-old",
    )
    db = MockSupabaseClient(state)
    service = ReviewService(db)

    res = await service.revert_question(session_id, q_id, user_id)
    assert res.question_id == q_id
    assert res.is_reverted is True
    assert res.status == "approved"
    # No new rows inserted into version_questions
    assert len(state["version_questions"]) == 1


@pytest.mark.asyncio
async def test_ai_timeout_immediate_rollback():
    """Test 12: AI timeout raises 504 and immediately triggers emergency rollback."""
    session_id = "00000000-0000-0000-0000-000000000012"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    async def timeout_ai(**kwargs):
        op_id = kwargs.get("operation_id")
        acquire_cb = kwargs.get("acquire_attempt")
        if op_id and callable(acquire_cb):
            await acquire_cb(op_id, uuid4())
        raise asyncio.TimeoutError("Gemini call timed out after 45s")

    service = ReviewService(db, ai_generator=timeout_ai)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 504
    assert exc_info.value.error_code == "ERR_AI_TIMEOUT"

    # Verify quota charges 1 committed call (retained after rollback)
    assert state["exam_sessions"][0]["gemini_review_calls"] == 1
    # Verify status reverted to pending_review
    assert state["version_questions"][0]["status"] == "pending_review"


@pytest.mark.asyncio
async def test_update_before_insert_ordering():
    """Test 13: In TX2, old question UPDATE is_current=False occurs before new question INSERT is_current=True."""
    session_id = "00000000-0000-0000-0000-000000000013"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    state["version_questions"][0]["status"] = "regenerating"
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    old_snapshot = state["version_questions"][0]
    new_data = {
        "content": "Câu mới",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "correct_key": "A",
        "validation_report": {"is_valid": True},
    }

    await repo.complete_regeneration_tx(
        session_id=session_id,
        old_q_snapshot=old_snapshot,
        new_data=new_data,
        regeneration_id=uuid4(),
        actual_calls=1,
        user_id=user_id,
    )

    # Analyze order of operations in call_log
    ops = [
        (c["op"], c["table"], c.get("payload", {}).get("is_current"))
        for c in db.call_log
        if c["table"] == "version_questions"
    ]

    update_idx = next(
        i for i, (op, _, is_cur) in enumerate(ops) if op == "update" and is_cur is False
    )
    insert_idx = next(i for i, (op, _, is_cur) in enumerate(ops) if op == "insert")

    assert update_idx < insert_idx, "UPDATE is_current=False must precede INSERT is_current=True"


@pytest.mark.asyncio
async def test_idor_cross_session():
    """Test 14: Accessing question belonging to another session raises 404 (Anti-IDOR)."""
    session_a = "00000000-0000-0000-0000-000000000014"
    session_b = "00000000-0000-0000-0000-000000000099"
    user_id = "user-123"
    q_id = "vq-session-b"
    state = _setup_standard_session_state(session_b, user_id, question_id=q_id)
    # Register session A as well
    state["exam_sessions"].append(
        {
            "id": session_a,
            "user_id": user_id,
            "status": "generated",
            "gemini_review_calls": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db = MockSupabaseClient(state)
    service = ReviewService(db)

    # Attempt to reject question of session_b using session_a URL
    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_a, q_id, user_id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "ERR_QUESTION_NOT_FOUND"


@pytest.mark.asyncio
async def test_revert_does_not_change_required_count():
    """Test 15: Required count remains invariant before and after reject and revert."""
    session_id = "00000000-0000-0000-0000-000000000015"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    p0 = await repo.get_review_progress_data(session_id)
    assert p0["required_count"] == 1

    # Simulate reject -> new variant
    new_data = {
        "content": "Variant 2",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "correct_key": "B",
    }
    state["version_questions"][0]["status"] = "regenerating"
    created = await repo.complete_regeneration_tx(
        session_id=session_id,
        old_q_snapshot=state["version_questions"][0],
        new_data=new_data,
        regeneration_id=uuid4(),
        actual_calls=1,
        user_id=user_id,
    )
    assert created is not None

    p1 = await repo.get_review_progress_data(session_id)
    assert p1["required_count"] == 1

    # Revert variant back to source
    await repo.atomic_revert_tx(session_id, created["id"], user_id)

    p2 = await repo.get_review_progress_data(session_id)
    assert p2["required_count"] == 1


@pytest.mark.asyncio
async def test_can_finalize_logic():
    """Test 16: can_finalize is True only when all questions approved, 0 regenerating, not finalized."""
    session_id = "00000000-0000-0000-0000-000000000016"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(
        session_id, user_id, question_id=q_id, question_status="pending_review"
    )
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    # 1. pending_review -> can_finalize = False
    p1 = await repo.get_review_progress_data(session_id)
    assert p1["can_finalize"] is False

    # 2. approved -> can_finalize = True
    state["version_questions"][0]["status"] = "approved"
    p2 = await repo.get_review_progress_data(session_id)
    assert p2["can_finalize"] is True

    # 3. regenerating question exists -> can_finalize = False
    state["version_questions"].append(
        {
            "id": "vq-002",
            "version_id": "ver-001",
            "source_question_id": "src-002",
            "status": "regenerating",
            "is_current": True,
            "exam_versions": {"session_id": session_id, "is_finalized": False},
        }
    )
    p3 = await repo.get_review_progress_data(session_id)
    assert p3["can_finalize"] is False


@pytest.mark.asyncio
async def test_review_logs_created_on_all_actions():
    """Test 17: Audit logs are recorded on Accept, Reject, Revert, and Emergency Rollback."""
    session_id = "00000000-0000-0000-0000-000000000017"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    # Action 1: Accept
    await repo.accept_question_tx(session_id, q_id, user_id)
    assert any(
        log["payload"]["action_type"] == "ACCEPT"
        for log in db.call_log
        if log["table"] == "review_logs"
    )

    # Action 2: Rollback
    state["version_questions"][0]["status"] = "regenerating"
    await repo.emergency_rollback_tx(session_id, q_id, uuid4(), "test error", user_id)
    assert any(
        log["payload"]["action_type"] == "REJECT_FAILED"
        for log in db.call_log
        if log["table"] == "review_logs"
    )

    # Action 3: Revert (on regenerated question)
    state["version_questions"][0]["regenerated_from_id"] = "vq-prev"
    await repo.atomic_revert_tx(session_id, q_id, user_id)
    assert any(
        log["payload"]["action_type"] == "REVERT"
        for log in db.call_log
        if log["table"] == "review_logs"
    )


@pytest.mark.asyncio
async def test_reject_or_revert_unsets_is_finalized():
    """Test 18: Invalidation unsets is_finalized=True on versions and sets session status back to generated."""
    session_id = "00000000-0000-0000-0000-000000000018"
    user_id = "user-123"
    state = _setup_standard_session_state(session_id, user_id, session_status="reviewed")
    state["exam_versions"][0]["is_finalized"] = True
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    invalidated = await repo.invalidate_shuffle_if_finalized(session_id)
    assert invalidated is True

    # Check version was demoted from is_finalized
    assert state["exam_versions"][0]["is_finalized"] is False
    # Check session was demoted to generated
    assert state["exam_sessions"][0]["status"] == "generated"


@pytest.mark.asyncio
async def test_f03_canonical_answers_independent_from_rejected_candidate():
    """Finding F03: Regenerated variant must snapshot its own canonical options, key and solution."""
    session_id = "00000000-0000-0000-0000-000000000019"
    user_id = "user-123"
    q_id = "vq-001"
    # Old candidate has roots ±3 (key A)
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    # Old question has old canonical values
    state["version_questions"][0]["canonical_options"] = [
        "A. x=±3",
        "B. x=3",
        "C. x=-3",
        "D. Vô nghiệm",
    ]
    state["version_questions"][0]["canonical_correct_key"] = "A"
    state["version_questions"][0]["canonical_solution_md"] = "Giải ra x=±3, chọn A."

    db = MockSupabaseClient(state)

    # New candidate from AI has roots ±5 (key C)
    async def ai_gen_roots_5(**kwargs):
        return {
            "content": "Giải phương trình x^2 - 25 = 0.",
            "options": ["A. x=±1", "B. x=5", "C. x=±5", "D. Vô nghiệm"],
            "correct_key": "C",
            "solution_md": "x^2 = 25 => x = ±5. Đáp án C.",
            "validation_report": {"is_valid": True, "math_verified": True},
            "api_calls_count": 1,
        }

    service = ReviewService(db, ai_generator=ai_gen_roots_5)
    resp = await service.reject_question(session_id, q_id, user_id)

    assert resp.status == "pending_review"
    # Find newly created version question
    new_q = [q for q in state["version_questions"] if q["is_current"] is True][0]
    # F03 check: Canonical options MUST be from new AI output, NOT old candidate!
    assert new_q["canonical_options"] == ["A. x=±1", "B. x=5", "C. x=±5", "D. Vô nghiệm"]
    assert new_q["canonical_correct_key"] == "C"
    assert new_q["canonical_solution_md"] == "x^2 = 25 => x = ±5. Đáp án C."


@pytest.mark.asyncio
async def test_f04_production_reject_without_ai_adapter_returns_503():
    """Finding F04: Reject without configured AI adapter raises 503 before locking DB or touching quota."""
    session_id = "00000000-0000-0000-0000-000000000020"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    # ReviewService with NO ai_generator configured
    service = ReviewService(db, ai_generator=None)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 503
    assert exc_info.value.error_code == "ERR_AI_SERVICE_UNAVAILABLE"

    # Verify DB was NOT mutated: question still pending_review, quota untouched
    assert state["version_questions"][0]["status"] == "pending_review"
    assert state["exam_sessions"][0]["gemini_review_calls"] == 0


@pytest.mark.asyncio
async def test_f06_stale_recovery_with_caller_user_id():
    """Finding F06: Stale recovery automatically runs on get_progress and records caller user_id."""
    from datetime import timedelta

    session_id = "00000000-0000-0000-0000-000000000021"
    caller_user_id = "caller-user-789"
    q_id = "vq-stale"
    state = _setup_standard_session_state(
        session_id,
        caller_user_id,
        question_id=q_id,
        question_status="regenerating",
        gemini_calls=4,
    )
    # Set updated_at to 4 minutes in the past (> 3 mins threshold)
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    state["version_questions"][0]["updated_at"] = stale_time

    db = MockSupabaseClient(state)
    service = ReviewService(db)

    # Calling get_progress triggers stale recovery
    progress = await service.get_progress(session_id, user_id=caller_user_id)
    assert progress.required_count == 1

    # Question must be recovered to pending_review
    assert state["version_questions"][0]["status"] == "pending_review"

    # F06 check: review_logs MUST contain caller_user_id, NEVER 00000000-0000-0000-0000-000000000000
    stale_logs = [
        log
        for log in db.call_log
        if log["table"] == "review_logs" and log["payload"]["action_type"] == "REJECT_FAILED"
    ]
    assert len(stale_logs) == 1
    assert stale_logs[0]["payload"]["user_id"] == caller_user_id
    assert stale_logs[0]["payload"]["reason"] == "STALE_TIMEOUT"


@pytest.mark.asyncio
async def test_source_snapshot_provides_content_hash_and_aliases_for_task_304():
    """Verify get_question_snapshot populates content_hash and adapter aliases for TASK-304."""
    session_id = "00000000-0000-0000-0000-000000000022"
    user_id = "user-123"
    q_id = "vq-hash-test"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    repo = ReviewRepository(db)
    snapshot = await repo.get_question_snapshot(q_id)

    source = snapshot["source"]
    assert "content_hash" in source
    assert len(source["content_hash"]) == 64  # Valid sha256 hex digest
    assert source["question_text"] == "Câu 1: Giải phương trình $x^2 - 4 = 0$"
    assert source["correct_answer"] == "A"
    assert isinstance(source["options"], list)
    assert len(source["options"]) == 4


@pytest.mark.asyncio
async def test_invalidation_clears_shuffle_seed_permutations_and_answer_keys():
    """Verify invalidation clears shuffle_seed, permutations, and purges answer_keys (Contract with Hùng)."""
    session_id = "00000000-0000-0000-0000-000000000023"
    user_id = "user-123"
    state = _setup_standard_session_state(session_id, user_id, session_status="reviewed")
    v_id = state["exam_versions"][0]["id"]
    state["exam_versions"][0]["is_finalized"] = True
    state["exam_versions"][0]["shuffle_seed"] = "seed-hash-123"
    state["exam_versions"][0]["permutations"] = {"question_order": [1, 2, 3]}

    # Add dummy answer keys
    state["answer_keys"] = [
        {"id": "ak-1", "version_id": v_id, "display_no": 1, "display_correct_key": "B"},
        {"id": "ak-2", "version_id": v_id, "display_no": 2, "display_correct_key": "D"},
    ]

    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    invalidated = await repo.invalidate_shuffle_if_finalized(session_id)
    assert invalidated is True

    # Check version fields reset
    version = state["exam_versions"][0]
    assert version["is_finalized"] is False
    assert version["shuffle_seed"] is None
    assert version["permutations"] is None

    # Check answer_keys purged
    assert len(state["answer_keys"]) == 0

    # Check session demoted to generated
    assert state["exam_sessions"][0]["status"] == "generated"


@pytest.mark.asyncio
async def test_session_level_single_active_regeneration_concurrency():
    """Verify Model A concurrency: only 1 active regenerating question per session (C01)."""
    session_id = "00000000-0000-0000-0000-000000000024"
    user_id = "user-123"
    state = _setup_standard_session_state(
        session_id, user_id, question_id="vq-active-regen", question_status="regenerating"
    )

    # Add a second question in the same session
    v_id = state["exam_versions"][0]["id"]
    state["version_questions"].append(
        {
            "id": "vq-second-q",
            "version_id": v_id,
            "source_question_id": "sq-123",
            "question_no": 2,
            "content": "Question 2",
            "options": ["A", "B", "C", "D"],
            "correct_key": "B",
            "status": "pending_review",
            "is_current": True,
            "is_reverted": False,
            "regenerated_from_id": None,
            "regeneration_id": None,
            "exam_versions": {"session_id": session_id, "is_finalized": False},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
    )

    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    # Attempting to reserve quota for second question must return SESSION_BUSY
    res = await repo.reserve_max_quota_and_start_regenerating(session_id, "vq-second-q", user_id)
    assert res == ReserveResult.SESSION_BUSY

    # Service call must raise ReviewDomainException 409 ERR_SESSION_BUSY_REGENERATING
    service = ReviewService(db, ai_generator=lambda **kw: {})
    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, "vq-second-q", user_id)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_SESSION_BUSY_REGENERATING"


@pytest.mark.asyncio
async def test_progress_extended_contract_fields_and_slots():
    """Verify ReviewProgressResponse satisfies both TASK-302 RPC contract and legacy fields (C02)."""
    session_id = "00000000-0000-0000-0000-000000000025"
    user_id = "user-123"
    state = _setup_standard_session_state(
        session_id, user_id, question_id="vq-slot-1", question_status="approved"
    )
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    data = await repo.get_review_progress_data(session_id)
    assert data["expected_slots"] == 1
    assert data["current_slots"] == 1
    assert data["approved_slots"] == 1
    assert data["regenerating_slots"] == 0
    assert data["missing_slots"] == 0
    assert data["duplicate_slots"] == 0
    assert data["ready"] is True

    # Test Pydantic model serialization & backward compatibility
    resp = ReviewProgressResponse(**data)
    assert resp.expected_slots == resp.required_count == 1
    assert resp.current_slots == resp.current_count == 1
    assert resp.approved_slots == resp.approved_count == 1
    assert resp.ready == resp.can_finalize is True


@pytest.mark.asyncio
async def test_audit_log_user_id_never_null():
    """Verify that all review_logs entries strictly record valid user_id (Migration 006 compliance)."""
    session_id = "00000000-0000-0000-0000-000000000026"
    user_id = "teacher-uuid-456"
    q_id = "vq-audit-check"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    async def _mock_ai(**kw: Any) -> Dict[str, Any]:
        return {
            "content": "New STEM",
            "stem_latex": "New STEM",
            "options": ["1", "2", "3", "4"],
            "correct_key": "C",
            "solution_md": "Sol",
            "validation_report": {"is_valid": True},
            "api_calls_count": 1,
        }

    service = ReviewService(db, ai_generator=_mock_ai)

    # 1. Accept action
    await service.accept_question(session_id, q_id, user_id)

    # 2. Reject action
    rej_resp = await service.reject_question(session_id, q_id, user_id)

    # 3. Revert action
    await service.revert_question(session_id, rej_resp.question_id, user_id)

    # Verify all review_logs in state
    logs = state.get("review_logs", [])
    assert len(logs) >= 3
    for log_entry in logs:
        assert log_entry.get("user_id") is not None
        assert log_entry.get("user_id") == user_id
        assert len(str(log_entry.get("user_id"))) > 0


@pytest.mark.asyncio
async def test_reject_passes_operation_id_and_acquires_permit():
    """Verify reject_question passes operation_id and callable acquire_attempt conforming to TASK-304."""
    session_id = "00000000-0000-0000-0000-000000000027"
    user_id = "teacher-uuid-permit-test"
    q_id = "vq-permit-check"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    passed_kwargs = {}

    async def _mock_ai(**kwargs: Any) -> Dict[str, Any]:
        passed_kwargs.update(kwargs)
        op_id = kwargs.get("operation_id")
        acquire_cb = kwargs.get("acquire_attempt")
        assert op_id is not None
        assert callable(acquire_cb)

        # Simulate adapter requesting a permit before dispatch
        attempt_id = uuid4()
        permit = await acquire_cb(op_id, attempt_id)
        assert permit.operation_id == op_id
        assert permit.attempt_id == attempt_id
        assert permit.dispatch_permitted is True
        assert permit.replayed is False
        assert permit.calls_used >= 1

        return {
            "content": "Permit-tested STEM",
            "stem_latex": "Permit-tested STEM",
            "options": ["1", "2", "3", "4"],
            "correct_key": "B",
            "solution_md": "Permit Sol",
            "validation_report": {"is_valid": True},
            "api_calls_count": 1,
        }

    service = ReviewService(db, ai_generator=_mock_ai)
    resp = await service.reject_question(session_id, q_id, user_id)

    assert resp.status == "pending_review"
    assert "operation_id" in passed_kwargs
    assert "acquire_attempt" in passed_kwargs


@pytest.mark.asyncio
async def test_reject_denied_permit_raises_429_exhausted():
    """Verify reject stops immediately and raises 429 when attempt permit is denied due to quota."""
    session_id = "00000000-0000-0000-0000-000000000028"
    user_id = "teacher-uuid-denied-test"
    q_id = "vq-permit-denied"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    async def _mock_exhausted_ai(**kwargs: Any) -> Dict[str, Any]:
        op_id = kwargs.get("operation_id")
        acquire_cb = kwargs.get("acquire_attempt")
        permit = await acquire_cb(op_id, uuid4())

        class MockTargetedError(RuntimeError):
            code = "REVIEW_QUOTA_EXHAUSTED"
            api_calls_count = 0

        if not permit.dispatch_permitted:
            raise MockTargetedError("REVIEW_QUOTA_EXHAUSTED")
        return {}

    # Pre-exhaust quota to 30
    state["exam_sessions"][0]["gemini_review_calls"] = 26
    service = ReviewService(db, ai_generator=_mock_exhausted_ai)

    # In TX1, 26 + 4 <= 30 passes reserve. Then in AI execution, acquire_attempt sees session limit
    # or simulated denial and adapter raises REVIEW_QUOTA_EXHAUSTED.
    state["exam_sessions"][0]["gemini_review_calls"] = 30  # Simulate concurrent depletion
    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 429
    assert exc_info.value.error_code == "ERR_REVIEW_QUOTA_EXHAUSTED"


@pytest.mark.asyncio
async def test_reject_uncertain_permit_retains_charge_and_fails_502():
    """Verify uncertain/invalid permit raises 502 and retains acknowledged charges without over-refunding."""
    session_id = "00000000-0000-0000-0000-000000000029"
    user_id = "teacher-uuid-uncertain-test"
    q_id = "vq-permit-uncertain"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    async def _mock_uncertain_ai(**kwargs: Any) -> Dict[str, Any]:
        op_id = kwargs.get("operation_id")
        acquire_cb = kwargs.get("acquire_attempt")

        # First attempt is granted
        permit1 = await acquire_cb(op_id, uuid4())
        assert permit1.dispatch_permitted is True

        class MockUncertainError(RuntimeError):
            code = "REVIEW_PERMIT_UNCERTAIN"
            api_calls_count = 1  # 1 permit was acknowledged before uncertain failure

        raise MockUncertainError("REVIEW_PERMIT_UNCERTAIN")

    service = ReviewService(db, ai_generator=_mock_uncertain_ai)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == "ERR_AI_GATEWAY_PERMIT_FAILURE"

    # Verify that the 1 acknowledged permit remains charged in session quota
    assert state["exam_sessions"][0]["gemini_review_calls"] == 1


# ==============================================================================
# F07 Comprehensive Regression Test Suite (Architecture A - 11 Tests)
# ==============================================================================


@pytest.mark.asyncio
async def test_f07_quota_boundary_at_26_allows_valid_attempt():
    """1. Verify at session quota 26, attempt 1 is granted with calls_used=27 (No false denial at boundary)."""
    session_id = "00000000-0000-0000-0000-000000000101"
    user_id = "teacher-101"
    state = _setup_standard_session_state(session_id, user_id, gemini_calls=26)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    op_id = uuid4()
    repo.register_operation(op_id, session_id)

    att_1 = uuid4()
    permit = await repo.acquire_attempt(op_id, att_1)
    assert permit.dispatch_permitted is True
    assert permit.replayed is False
    assert permit.calls_used == 27
    assert permit.remaining_calls == 3
    assert state["exam_sessions"][0]["gemini_review_calls"] == 27


@pytest.mark.asyncio
async def test_f07_operation_exhausted_after_4_attempts():
    """2. Verify within a single operation, attempts 1-4 are granted, attempt 5 is denied."""
    session_id = "00000000-0000-0000-0000-000000000102"
    user_id = "teacher-102"
    state = _setup_standard_session_state(session_id, user_id, gemini_calls=10)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    op_id = uuid4()
    repo.register_operation(op_id, session_id)

    # 4 attempts granted
    for i in range(1, 5):
        p = await repo.acquire_attempt(op_id, uuid4())
        assert p.dispatch_permitted is True
        assert p.replayed is False
        assert p.calls_used == 10 + i

    # 5th attempt denied (operation exhausted)
    p5 = await repo.acquire_attempt(op_id, uuid4())
    assert p5.dispatch_permitted is False
    assert p5.replayed is False
    assert p5.calls_used == 14
    assert state["exam_sessions"][0]["gemini_review_calls"] == 14


@pytest.mark.asyncio
async def test_f07_session_exhausted_at_30_denied():
    """3. Verify when session calls reached 30, subsequent acquire is denied."""
    session_id = "00000000-0000-0000-0000-000000000103"
    user_id = "teacher-103"
    state = _setup_standard_session_state(session_id, user_id, gemini_calls=30)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    op_id = uuid4()
    repo.register_operation(op_id, session_id)

    permit = await repo.acquire_attempt(op_id, uuid4())
    assert permit.dispatch_permitted is False
    assert permit.replayed is False
    assert permit.calls_used == 30
    assert permit.remaining_calls == 0
    assert state["exam_sessions"][0]["gemini_review_calls"] == 30


@pytest.mark.asyncio
async def test_f07_replay_across_separate_clients_same_db():
    """4. Verify replay detection works across separate repository instances sharing underlying DB state."""
    session_id = "00000000-0000-0000-0000-000000000104"
    user_id = "teacher-104"
    shared_state = _setup_standard_session_state(session_id, user_id, gemini_calls=5)

    db_client_a = MockSupabaseClient(shared_state)
    repo_a = ReviewRepository(db_client_a)

    db_client_b = MockSupabaseClient(shared_state)
    repo_b = ReviewRepository(db_client_b)

    op_id = uuid4()
    att_id = uuid4()
    repo_a.register_operation(op_id, session_id)

    # Worker A acquires permit
    permit_a = await repo_a.acquire_attempt(op_id, att_id)
    assert permit_a.dispatch_permitted is True
    assert permit_a.replayed is False
    assert permit_a.calls_used == 6

    # Worker B tries to acquire with same attempt_id (Worker B does NOT have RAM state from Worker A)
    permit_b = await repo_b.acquire_attempt(op_id, att_id)
    assert permit_b.dispatch_permitted is False
    assert permit_b.replayed is True
    assert permit_b.calls_used == 6


@pytest.mark.asyncio
async def test_f07_concurrent_same_attempt_id_only_one_granted():
    """5. Race condition: Two concurrent acquires with identical attempt_id -> exactly one granted."""
    session_id = "00000000-0000-0000-0000-000000000105"
    user_id = "teacher-105"
    shared_state = _setup_standard_session_state(session_id, user_id, gemini_calls=12)

    db_a = MockSupabaseClient(shared_state)
    repo_a = ReviewRepository(db_a)

    db_b = MockSupabaseClient(shared_state)
    repo_b = ReviewRepository(db_b)

    op_id = uuid4()
    repo_a.register_operation(op_id, session_id)
    repo_b.register_operation(op_id, session_id)

    same_attempt = uuid4()
    permits = await asyncio.gather(
        repo_a.acquire_attempt(op_id, same_attempt),
        repo_b.acquire_attempt(op_id, same_attempt),
    )

    granted = [p for p in permits if p.dispatch_permitted is True]
    replayed = [p for p in permits if p.replayed is True]

    assert len(granted) == 1
    assert len(replayed) == 1
    assert shared_state["exam_sessions"][0]["gemini_review_calls"] == 13


@pytest.mark.asyncio
async def test_f07_concurrent_two_ops_at_26_no_oversubscribe():
    """6. Concurrency: Two operations at session=26 running 4 attempts each cannot exceed 30 calls."""
    session_id = "00000000-0000-0000-0000-000000000106"
    user_id = "teacher-106"
    shared_state = _setup_standard_session_state(session_id, user_id, gemini_calls=26)

    db = MockSupabaseClient(shared_state)
    repo = ReviewRepository(db)

    op_a = uuid4()
    op_b = uuid4()
    repo.register_operation(op_a, session_id)
    repo.register_operation(op_b, session_id)

    async def run_op(op_id: UUID) -> List[Any]:
        res = []
        for _ in range(4):
            p = await repo.acquire_attempt(op_id, uuid4())
            res.append(p)
        return res

    results = await asyncio.gather(run_op(op_a), run_op(op_b))
    all_permits = results[0] + results[1]
    granted = [p for p in all_permits if p.dispatch_permitted is True]

    # Exactly 4 permits should be granted to reach 30 (26 + 4 = 30)
    assert len(granted) == 4
    assert shared_state["exam_sessions"][0]["gemini_review_calls"] == 30


@pytest.mark.asyncio
async def test_f07_rollback_zero_committed_permits():
    """7. Failure before any permit is acquired -> rollback leaves session quota completely untouched."""
    session_id = "00000000-0000-0000-0000-000000000107"
    user_id = "teacher-107"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=15)
    db = MockSupabaseClient(state)

    async def failing_ai_without_permit(**kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("Immediate pre-dispatch error")

    service = ReviewService(db, ai_generator=failing_ai_without_permit)
    with pytest.raises(ReviewDomainException):
        await service.reject_question(session_id, q_id, user_id)

    # Session calls remains exactly 15 (no subtraction, no addition)
    assert state["exam_sessions"][0]["gemini_review_calls"] == 15
    assert state["version_questions"][0]["status"] == "pending_review"


@pytest.mark.asyncio
async def test_f07_rollback_retains_committed_permits():
    """8. AI fails after 2 permits granted -> rollback retains 2 committed permits, does not refund."""
    session_id = "00000000-0000-0000-0000-000000000108"
    user_id = "teacher-108"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=5)
    db = MockSupabaseClient(state)

    async def ai_fails_after_2_permits(**kwargs: Any) -> Dict[str, Any]:
        op_id = kwargs["operation_id"]
        acquire_cb = kwargs["acquire_attempt"]
        # Acquire 2 permits
        p1 = await acquire_cb(op_id, uuid4())
        assert p1.dispatch_permitted is True
        p2 = await acquire_cb(op_id, uuid4())
        assert p2.dispatch_permitted is True

        class MockAdapterError(RuntimeError):
            code = "REVIEW_PERMIT_UNCERTAIN"
            api_calls_count = 2

        raise MockAdapterError("Uncertain connection after 2 permits")

    service = ReviewService(db, ai_generator=ai_fails_after_2_permits)
    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 502
    # 5 + 2 = 7; quota retains both committed permits
    assert state["exam_sessions"][0]["gemini_review_calls"] == 7
    assert state["version_questions"][0]["status"] == "pending_review"


@pytest.mark.asyncio
async def test_f07_rollback_idempotent():
    """9. Emergency rollback called twice with same parameters is idempotent and does not alter quota."""
    session_id = "00000000-0000-0000-0000-000000000109"
    user_id = "teacher-109"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=8)
    state["version_questions"][0]["status"] = "regenerating"
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    regen_id = uuid4()
    # First rollback: succeeds
    rb1 = await repo.emergency_rollback_tx(session_id, q_id, regen_id, "Error 1", user_id, 1)
    assert rb1 is True
    assert state["version_questions"][0]["status"] == "pending_review"
    assert state["exam_sessions"][0]["gemini_review_calls"] == 8

    # Second rollback: status is already pending_review, returns False
    rb2 = await repo.emergency_rollback_tx(session_id, q_id, regen_id, "Error 2", user_id, 1)
    assert rb2 is False
    assert state["version_questions"][0]["status"] == "pending_review"
    assert state["exam_sessions"][0]["gemini_review_calls"] == 8


@pytest.mark.asyncio
async def test_f07_db_unavailable_fail_closed():
    """10. Database connection failure during acquire fails closed (raises, no blind permit granted)."""
    session_id = "00000000-0000-0000-0000-000000000110"
    user_id = "teacher-110"
    state = _setup_standard_session_state(session_id, user_id, gemini_calls=10)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    op_id = uuid4()
    repo.register_operation(op_id, session_id)

    # Simulate DB disconnection
    def broken_table(name: str):
        raise ConnectionError("DB connection refused")

    db.table = broken_table  # type: ignore

    with pytest.raises(ConnectionError):
        await repo.acquire_attempt(op_id, uuid4())

    # Session calls remains unchanged (not granted)
    assert state["exam_sessions"][0]["gemini_review_calls"] == 10


@pytest.mark.asyncio
async def test_f07_service_maps_all_permit_error_codes():
    """11. Verify Service properly maps adapter exception codes to correct HTTP domain errors."""
    session_id = "00000000-0000-0000-0000-000000000111"
    user_id = "teacher-111"

    error_mappings = [
        ("REVIEW_QUOTA_EXHAUSTED", 429, "ERR_REVIEW_QUOTA_EXHAUSTED"),
        ("OPERATION_EXHAUSTED", 429, "ERR_OPERATION_QUOTA_EXHAUSTED"),
        ("REVIEW_ATTEMPT_REPLAYED", 409, "ERR_ATTEMPT_REPLAYED"),
        ("REVIEW_PERMIT_UNCERTAIN", 502, "ERR_AI_GATEWAY_PERMIT_FAILURE"),
        ("REVIEW_PERMIT_INVALID", 502, "ERR_AI_GATEWAY_PERMIT_FAILURE"),
        ("DB_UNAVAILABLE", 503, "ERR_AI_GATEWAY_PERMIT_FAILURE"),
    ]

    for err_code, expected_status, expected_domain_code in error_mappings:
        q_id = f"vq-{err_code.lower()}"
        state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
        db = MockSupabaseClient(state)

        class CustomAdapterError(RuntimeError):
            code = err_code

        async def _failing_ai(**kwargs: Any):
            raise CustomAdapterError(f"Simulated {err_code}")

        service = ReviewService(db, ai_generator=_failing_ai)
        with pytest.raises(ReviewDomainException) as exc_info:
            await service.reject_question(session_id, q_id, user_id)

        assert exc_info.value.status_code == expected_status, f"Failed mapping for {err_code}"
        assert exc_info.value.error_code == expected_domain_code, f"Failed error code for {err_code}"

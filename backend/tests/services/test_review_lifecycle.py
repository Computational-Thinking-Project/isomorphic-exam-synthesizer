"""Unit and Lifecycle Integration Tests for Stage 3 Review Lifecycle (TASK-301).

Implements 18 critical test cases:
1. test_zero_connection_during_ai_call
2. test_tx2_retry_idempotency
3. test_emergency_rollback_after_network_partition
4. test_emergency_rollback_cannot_double_refund
5. test_stale_guard_cannot_double_refund_tx2
6. test_multi_version_required_count_invariant
7. test_reserve_at_calls_27
8. test_reserve_at_calls_28_blocked
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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import pytest

from app.models.schemas import ReserveResult, ReviewDomainException
from app.services.review.repository import ReviewRepository
from app.services.review.service import ReviewService, session_lock_registry


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
            for item in to_insert:
                item_copy = dict(item)
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

        return MockExecutionResult([])


class MockSupabaseClient:
    """Mock Supabase client providing stateful in-memory tables and query call logs."""

    def __init__(self, initial_state: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        self.state: Dict[str, List[Dict[str, Any]]] = initial_state or {}
        self.call_log: List[Dict[str, Any]] = []

    def table(self, table_name: str) -> MockTableQueryBuilder:
        return MockTableQueryBuilder(table_name, self.state, self.call_log)


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
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=3)
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
        actual_calls=1,  # 3 - 1 = 2 calls refund
        user_id=user_id,
    )
    assert res1 is not None
    assert str(res1["regeneration_id"]) == str(regen_id)

    # Check quota after Call 1: 3 - 2 = 1
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
    # Verify quota was not refunded a second time
    assert session_row["gemini_review_calls"] == 1


@pytest.mark.asyncio
async def test_emergency_rollback_after_network_partition():
    """Test 3: AI succeeds but TX2 retry exhausted -> Emergency Rollback refunds 3 calls and resets question."""
    session_id = "00000000-0000-0000-0000-000000000003"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id)
    db = MockSupabaseClient(state)

    async def mock_ai_generator(**kwargs):
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

    # Verify quota returned to 0 (TX1 added 3, emergency rollback refunded 3)
    session_row = state["exam_sessions"][0]
    assert session_row["gemini_review_calls"] == 0

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
    """Test 5: Stale guard checks rowcount; if row was already modified, does not refund."""
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
    assert state["exam_sessions"][0]["gemini_review_calls"] == 0
    assert state["version_questions"][0]["status"] == "pending_review"

    # Second concurrent or repeated run finds status is pending_review (not regenerating)
    recovered_again = await repo.recover_stale_questions()
    assert recovered_again == 0
    # Quota stays 0, no double decrement below 0
    assert state["exam_sessions"][0]["gemini_review_calls"] == 0


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
async def test_reserve_at_calls_27():
    """Test 7: At 27 calls, reserving 3 calls reaches 30 <= 30 (Allowed)."""
    session_id = "00000000-0000-0000-0000-000000000007"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=27)
    db = MockSupabaseClient(state)
    repo = ReviewRepository(db)

    res = await repo.reserve_max_quota_and_start_regenerating(session_id, q_id, user_id)
    assert res == ReserveResult.OK
    # Quota incremented to 30
    assert state["exam_sessions"][0]["gemini_review_calls"] == 30
    assert state["version_questions"][0]["status"] == "regenerating"


@pytest.mark.asyncio
async def test_reserve_at_calls_28_blocked():
    """Test 8: At 28 calls, reserving 3 calls would exceed 30 (28 + 3 = 31 > 30) -> 429 Error."""
    session_id = "00000000-0000-0000-0000-000000000008"
    user_id = "user-123"
    q_id = "vq-001"
    state = _setup_standard_session_state(session_id, user_id, question_id=q_id, gemini_calls=28)
    db = MockSupabaseClient(state)
    service = ReviewService(db)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 429
    assert exc_info.value.error_code == "ERR_REVIEW_QUOTA_EXHAUSTED"
    # Quota remained 28
    assert state["exam_sessions"][0]["gemini_review_calls"] == 28


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
    service = ReviewService(db)

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
        raise asyncio.TimeoutError("Gemini call timed out after 45s")

    service = ReviewService(db, ai_generator=timeout_ai)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(session_id, q_id, user_id)

    assert exc_info.value.status_code == 504
    assert exc_info.value.error_code == "ERR_AI_TIMEOUT"

    # Verify quota rolled back to 0
    assert state["exam_sessions"][0]["gemini_review_calls"] == 0
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

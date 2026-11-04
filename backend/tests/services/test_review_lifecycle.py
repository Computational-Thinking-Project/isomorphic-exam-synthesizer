"""TASK-301 caller regressions against the pinned TASK-302 receipt protocol.

The previous fake at 1366f3c modelled table writes, a question regeneration_id
binding, and fabricated confirmation. Those are not the SQL006 contract.
These tests use the actual service/repository with explicit RPC fixtures.
Immediate scheduling is isolated in test_review_flow; it is NOT a proof of DB
concurrency, row locks, pool usage or migrations. Those remain integration gates.
"""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.schemas import ReviewAcquireUnavailableError, ReviewDomainException
from app.services.review.repository import ReviewRepository
from app.services.review.service import ReviewService

from .test_review_flow import counts, immediate, output
from .test_review_flow import state as state


class AdapterError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def test_zero_connection_during_ai_call(state):
    """No caller lock is held; real pool checkout still needs DB instrumentation."""
    immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert state.provider_calls == 1  # provider fixture asserts the local lock is released


@pytest.mark.parametrize(
    "status,expected", [("generating", 409), ("approved", 423), ("exported", 423)]
)
@pytest.mark.parametrize("action", ["accept_question", "revert_question", "reject_question"])
def test_session_status_guards(state, action, status, expected):
    state.status = status
    with pytest.raises(ReviewDomainException) as error:
        immediate(getattr(state.service(), action)(state.sid, state.qid, "owner"))
    assert error.value.status_code == expected and state.calls == []


def test_non_null_approval_timestamp_locks_mutation(state):
    state.approved_at = "2026-11-04T00:00:00Z"
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner"))
    assert error.value.status_code == 423 and state.calls == []


def test_f04_production_reject_without_ai_adapter_returns_503(state):
    service = ReviewService(state.owner, state.worker)
    with pytest.raises(ReviewDomainException) as error:
        immediate(service.reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert error.value.error_code == "ERR_AI_SERVICE_UNAVAILABLE"
    assert state.operations == {} and state.charges == 0


@pytest.mark.parametrize("action", ["accept_question", "revert_question", "reject_question"])
def test_idor_cross_session(state, action):
    with pytest.raises(ReviewDomainException) as error:
        immediate(getattr(state.service(), action)(str(uuid4()), state.qid, "owner", str(uuid4())))
    assert error.value.status_code == 404 and state.calls == []


@pytest.mark.parametrize("action", ["accept_question", "revert_question", "reject_question"])
def test_malformed_uuid_is_rejected_before_query(state, action):
    with pytest.raises(ReviewDomainException) as error:
        immediate(getattr(state.service(), action)(state.sid, "vq-not-a-uuid", "owner"))
    assert error.value.status_code == 400 and state.calls == []


@pytest.mark.parametrize("charged", [False, True])
def test_ai_timeout_settles_from_ledger_without_refund(state, charged):
    async def timeout(**kwargs):
        if charged:
            await kwargs["acquire_attempt"](kwargs["operation_id"], uuid4())
        raise TimeoutError("private provider text")

    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service(timeout).reject_question(state.sid, state.qid, "owner", key))
    assert error.value.status_code == 504 and "private" not in error.value.detail
    assert state.operations[key]["operation_status"] == "failed"
    assert state.charges == int(charged)
    settlement = next(p for _, n, p in state.calls if n == "review_fail_regeneration")
    assert settlement == {"p_operation_id": key, "p_error_code": "AI_TIMEOUT"}


@pytest.mark.parametrize(
    "code,status",
    [
        ("REVIEW_QUOTA_EXHAUSTED", 429),
        ("REVIEW_ATTEMPT_EXHAUSTED", 429),
        ("REVIEW_ATTEMPT_REPLAYED", 409),
        ("REVIEW_PERMIT_UNCERTAIN", 502),
        ("REVIEW_PERMIT_INVALID", 502),
        ("DB_UNAVAILABLE", 503),
        ("SOURCE_NOT_CONFIRMED", 422),
    ],
)
def test_f07_service_maps_errors_without_client_accounting(state, code, status):
    async def failure(**kwargs):
        raise AdapterError(code)

    with pytest.raises(ReviewDomainException) as error:
        immediate(
            state.service(failure).reject_question(state.sid, state.qid, "owner", str(uuid4()))
        )
    assert error.value.status_code == status and state.charges == 0
    params = next(p for _, n, p in state.calls if n == "review_fail_regeneration")
    assert set(params) == {"p_operation_id", "p_error_code"}
    assert " " not in params["p_error_code"]


def test_unknown_permit_response_retains_committed_charge(state):
    original = state.rpc

    def lose_permit(role, name, params):
        data = original(role, name, params)
        if name == "review_acquire_attempt":
            raise ConnectionError("lost grant response")
        return data

    state.rpc = lose_permit
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert error.value.status_code == 503
    assert state.charges == 1 and state.complete_calls == 0
    assert next(iter(state.operations.values()))["settlement"]["api_calls_used"] == 1
    assert sum(n == "review_acquire_attempt" for _, n, _ in state.calls) == 1


def test_f03_completion_sends_new_candidates_own_answers(state):
    result = immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    payload = next(
        p["p_candidate"] for _, n, p in state.calls if n == "review_complete_regeneration"
    )
    assert payload["options"] == output()["options"]
    assert payload["correct_key"] == output()["correct_key"]
    assert payload["solution_md"] == output()["solution_md"]
    assert result.options == output()["options"]
    # SQL006 owns the new canonical snapshot; caller cannot copy canonical fields from old rows.
    assert not any(k.startswith("canonical_") for k in payload)


def test_first_candidate_can_be_reverted_per_owner_contract(state):
    assert not state.rows[state.qid].get("regenerated_from_id")
    result = immediate(state.service().revert_question(state.sid, state.qid, "owner", str(uuid4())))
    assert result.question_id == state.qid and result.status == "approved" and result.is_reverted
    assert len(state.rows) == 1


def test_revert_and_accept_do_not_create_another_review_budget(state):
    immediate(state.service().revert_question(state.sid, state.qid, "owner", str(uuid4())))
    immediate(state.service().accept_question(state.sid, state.qid, "owner", str(uuid4())))
    assert state.charges == 0 and not any(role == "worker" for role, _, _ in state.calls)


def test_failed_operation_replay_cannot_be_dispatched_again(state):
    key = str(uuid4())
    state.snapshot["format"] = "database_rows"
    with pytest.raises(ReviewDomainException):
        immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    calls_before = len(state.calls)
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    assert error.value.error_code == "ERR_OPERATION_FINISHED"
    assert state.provider_calls == state.charges == 0
    assert len(state.calls) == calls_before + 1  # receipt read only


def test_emergency_rollback_receipt_replay_is_idempotent(state):
    op = uuid4()
    repo = state.service().repo
    immediate(repo.reserve_regeneration(state.sid, state.qid, op))
    first = immediate(repo.settle_failure(state.sid, state.qid, op, "AI_TIMEOUT"))
    second = immediate(repo.settle_failure(state.sid, state.qid, op, "AI_TIMEOUT"))
    assert first.replayed is False and second.replayed is True
    assert state.charges == 0


def test_f06_discovery_needs_no_question_regeneration_id(state):
    op = uuid4()
    repo = state.service().repo
    immediate(repo.reserve_regeneration(state.sid, state.qid, op))
    assert "regeneration_id" not in state.rows[state.qid]
    state.operations[str(op)]["expires_at"] = "2000-01-01T00:00:00+00:00"
    assert immediate(repo.recover_stale_questions(state.sid)) == 1
    assert immediate(repo.recover_stale_questions(state.sid)) == 0
    assert state.operations[str(op)]["operation_status"] == "recovered"


def test_snapshot_helper_never_hashes_live_rows(state):
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().repo.get_question_snapshot(state.qid))
    assert error.value.error_code == "ERR_FROZEN_SNAPSHOT_REQUIRED" and state.calls == []


def test_late_invalidation_cannot_write_even_with_old_test_flag(state):
    repo = ReviewRepository(state.owner, service_db=state.worker, allow_table_fallback=True)
    with pytest.raises(ReviewDomainException) as error:
        immediate(repo.invalidate_shuffle_if_finalized(state.sid))
    assert error.value.error_code == "ERR_UNSAFE_MUTATION" and state.calls == []


def test_compatibility_reserve_retains_the_full_receipt(state):
    op = uuid4()
    result = immediate(
        state.service().repo.reserve_max_quota_and_start_regenerating(
            state.sid, state.qid, "owner", op
        )
    )
    assert (
        result.operation_id == op and result.snapshot == state.snapshot and result.replayed is False
    )


@pytest.mark.parametrize(
    "approved,status,can_finalize",
    [(1, "reviewed", True), (1, "approved", False), (0, "generated", False)],
)
def test_progress_reads_consistent_rpc_snapshot_without_mutation(
    state, approved, status, can_finalize
):
    progress = counts(approved)
    progress["unapproved_question_ids"] = [] if approved else [state.qid]
    state.progress_data = dict(
        session_id=state.sid, session_status=status, replayed=False, progress=progress
    )
    result = immediate(state.service().get_progress(state.sid, "owner"))
    assert result.can_finalize is can_finalize
    assert result.unapproved_question_ids == ([] if approved else [state.qid])
    assert [name for _, name, _ in state.calls] == ["review_get_progress"]


def test_f07_replayed_permit_is_not_locally_regranted(state):
    op, attempt = uuid4(), uuid4()
    repo = state.service().repo
    immediate(repo.reserve_regeneration(state.sid, state.qid, op))
    first = immediate(repo.acquire_attempt(op, attempt))
    second = immediate(repo.acquire_attempt(op, attempt))
    assert first.dispatch_permitted and not first.replayed
    assert not second.dispatch_permitted and second.replayed
    assert state.charges == 1


@pytest.mark.parametrize(
    "message", ["PGRST202 function missing", "42501 permission denied", "connection lost"]
)
def test_f07_missing_or_denied_rpc_has_no_local_ledger_fallback(message):
    def fail(*_):
        raise RuntimeError(message)

    repo = ReviewRepository(
        SimpleNamespace(table=lambda *_: pytest.fail("table fallback reached")),
        service_db=SimpleNamespace(rpc=fail),
        allow_table_fallback=True,
    )
    with pytest.raises(ReviewAcquireUnavailableError):
        immediate(repo.acquire_attempt(uuid4(), uuid4()))


def test_frozen_input_is_detached_from_receipt(state):
    before = deepcopy(state.snapshot)
    immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert state.snapshot == before
    assert all(
        "p_user_id" not in params and "actual_calls_dispatched" not in params
        for _, _, params in state.calls
    )

"""Negative RPC boundaries using the actual production repository/parser."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.schemas import ReviewAcquireUnavailableError, ReviewDomainException
from app.services.review.receipts import (
    ProgressCounts,
    ReservationReceipt,
    reservation_receipt,
    rpc_object,
)
from app.services.review.repository import ReviewRepository


def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    else:
        raise AssertionError("Unexpected external await")
    finally:
        coroutine.close()


def progress(**updates):
    return (
        dict(
            expected_slots=4,
            current_slots=1,
            approved_slots=1,
            regenerating_slots=0,
            missing_slots=3,
            duplicate_slots=0,
            ready=False,
        )
        | updates
    )


@pytest.mark.parametrize("value", [None, [], [{}, {}], "bad", True])
def test_rpc_shape_must_be_object_or_singleton(value):
    with pytest.raises(ReviewDomainException):
        rpc_object(value)


@pytest.mark.parametrize(
    "changes",
    [
        {"ready": "false"},
        {"approved_slots": True},
        {"missing_slots": -1},
        {"current_slots": "1"},
        {"approved_slots": 2},
        {"ready": True},
        {"unapproved_question_ids": [str(uuid4())]},
    ],
)
def test_progress_does_not_coerce_or_hide_inconsistent_counts(changes):
    with pytest.raises(ValueError):
        ProgressCounts.model_validate(progress(**changes))


def test_nested_progress_missing_slots_are_preserved():
    sid = str(uuid4())
    data = dict(session_id=sid, session_status="generated", replayed=False, progress=progress())
    calls = []

    def rpc(name, params):
        calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))

    repo = ReviewRepository(SimpleNamespace(rpc=rpc))
    result = immediate(repo.progress(sid))
    assert (result["expected_slots"], result["missing_slots"], result["can_finalize"]) == (
        4,
        3,
        False,
    )
    assert len(calls) == 1


def test_progress_does_not_fabricate_empty_unapproved_ids():
    sid = str(uuid4())
    data = dict(
        session_id=sid,
        session_status="generated",
        replayed=False,
        progress=progress(approved_slots=0),
    )
    repo = ReviewRepository(
        SimpleNamespace(rpc=lambda *_: SimpleNamespace(execute=lambda: SimpleNamespace(data=data)))
    )
    with pytest.raises(ReviewDomainException) as error:
        immediate(repo.progress(sid))
    assert error.value.error_code == "ERR_PROGRESS_DETAILS_UNAVAILABLE"


@pytest.mark.parametrize(
    "method",
    ["progress", "get_review_progress_data", "recover_stale_operations", "recover_stale_questions"],
)
def test_missing_rpc_never_enters_table_fallback(method):
    client = SimpleNamespace(table=lambda *_: pytest.fail("Table fallback reached"))
    repo = ReviewRepository(client)
    with pytest.raises(ReviewDomainException) as error:
        immediate(getattr(repo, method)(str(uuid4())))
    assert error.value.status_code == 503


def reservation(sid, qid, op):
    return dict(
        session_id=sid,
        question_id=qid,
        operation_id=str(op),
        session_status="generated",
        replayed=False,
        operation_status="active",
        snapshot={"format": "database_rows"},
        expires_at=(datetime.now(timezone.utc) + timedelta(seconds=180)).isoformat(),
        max_attempts=4,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"replayed": "false"},
        {"max_attempts": 4.0},
        {"operation_id": str(uuid4())},
        {"expires_at": "2030-01-01T00:00:00"},
        {"operation_status": "failed"},
        {"status": "denied"},
        {"question_id": str(uuid4())},
    ],
)
def test_malformed_reservation_never_becomes_ok(changes):
    sid, qid, op = str(uuid4()), str(uuid4()), uuid4()
    with pytest.raises(ReviewDomainException):
        reservation_receipt(reservation(sid, qid, op) | changes, sid, qid, op)


def test_reservation_retains_frozen_snapshot_and_status():
    sid, qid, op = str(uuid4()), str(uuid4()), uuid4()
    data = reservation(sid, qid, op)
    result = reservation_receipt(data, sid, qid, op)
    assert isinstance(result, ReservationReceipt)
    assert result.snapshot == data["snapshot"] and result.operation_status == "active"


@pytest.mark.parametrize(
    "changes",
    [
        {"dispatch_permitted": "false"},
        {"replayed": 1},
        {"calls_used": True},
        {"calls_used": 31, "remaining_calls": -1},
        {"calls_used": 27, "remaining_calls": 4},
        {"operation_id": str(uuid4())},
        {"replayed": True, "dispatch_permitted": True},
        {"extra": "unsupported"},
    ],
)
def test_malformed_permit_never_authorizes_dispatch(changes):
    op, attempt = uuid4(), uuid4()
    value = (
        dict(
            operation_id=str(op),
            attempt_id=str(attempt),
            dispatch_permitted=True,
            replayed=False,
            calls_used=27,
            remaining_calls=3,
        )
        | changes
    )
    worker = SimpleNamespace(
        rpc=lambda *_: SimpleNamespace(execute=lambda: SimpleNamespace(data=value))
    )
    repo = ReviewRepository(
        SimpleNamespace(table=lambda *_: pytest.fail("table fallback reached")), service_db=worker
    )
    with pytest.raises(ReviewAcquireUnavailableError):
        immediate(repo.acquire_attempt(op, attempt))


@pytest.mark.parametrize(
    "used,dispatch,replayed", [(27, True, False), (30, False, False), (30, False, True)]
)
def test_valid_permit_flags_and_counts_are_preserved(used, dispatch, replayed):
    op, attempt = uuid4(), uuid4()
    value = dict(
        operation_id=str(op),
        attempt_id=str(attempt),
        dispatch_permitted=dispatch,
        replayed=replayed,
        calls_used=used,
        remaining_calls=30 - used,
    )
    worker = SimpleNamespace(
        rpc=lambda *_: SimpleNamespace(execute=lambda: SimpleNamespace(data=value))
    )
    result = immediate(
        ReviewRepository(SimpleNamespace(), service_db=worker).acquire_attempt(op, attempt)
    )
    assert result.dispatch_permitted is dispatch and result.replayed is replayed
    assert result.calls_used == used and result.remaining_calls == 30 - used

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.schemas import ReviewDomainException
from app.services.review.receipts import settlement_receipt
from app.services.review.repository import ReviewRepository


def immediate(coroutine):
    """Exercise synchronous PostgREST boundaries, without an event loop or sockets."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    else:
        raise AssertionError("This unit boundary unexpectedly suspended")
    finally:
        coroutine.close()


def receipt(sid, qid, op):
    return dict(
        session_id=str(sid),
        question_id=str(qid),
        operation_id=str(op),
        session_status="generated",
        operation_status="failed",
        replayed=False,
        recovered=False,
        api_calls_used=1,
        progress=dict(
            expected_slots=1,
            current_slots=1,
            approved_slots=0,
            regenerating_slots=0,
            missing_slots=0,
            duplicate_slots=0,
            ready=False,
        ),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"replayed": "false"},
        {"api_calls_used": True},
        {"api_calls_used": 5},
        {"operation_status": "active"},
        {"recovered": True},
        {"operation_id": str(uuid4())},
    ],
)
def test_malformed_failure_receipt_is_uncertain(change):
    sid, qid, op = uuid4(), uuid4(), uuid4()
    value = receipt(sid, qid, op) | change
    with pytest.raises(ReviewDomainException) as error:
        settlement_receipt(value, str(sid), str(qid), op)
    assert error.value.status_code == 503


def test_worker_is_not_substituted_with_owner():
    repo = ReviewRepository(SimpleNamespace())
    assert repo.worker_db is None
    with pytest.raises(ReviewDomainException) as error:
        immediate(repo.settle_failure(str(uuid4()), str(uuid4()), uuid4(), "AI_TIMEOUT"))
    assert error.value.status_code == 503


def test_failure_rpc_receipt_and_code_preserve_committed_charge():
    sid, qid, op = uuid4(), uuid4(), uuid4()
    calls = []

    def rpc(name, params):
        calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=receipt(sid, qid, op)))

    repo = ReviewRepository(SimpleNamespace(), service_db=SimpleNamespace(rpc=rpc))
    result = immediate(repo.settle_failure(str(sid), str(qid), op, "AI_TIMEOUT"))
    assert result.api_calls_used == 1
    assert calls == [
        ("review_fail_regeneration", {"p_operation_id": str(op), "p_error_code": "AI_TIMEOUT"})
    ]


def test_transport_failure_is_not_reported_as_settled():
    def rpc(*args):
        raise ConnectionError("internal provider SQL detail")

    repo = ReviewRepository(SimpleNamespace(), service_db=SimpleNamespace(rpc=rpc))
    with pytest.raises(ReviewDomainException) as error:
        immediate(repo.settle_failure(str(uuid4()), str(uuid4()), uuid4(), "AI_TIMEOUT"))
    assert error.value.error_code == "ERR_SETTLEMENT_UNCERTAIN"
    assert "SQL detail" not in error.value.detail


def test_raw_exception_text_does_not_enter_failure_rpc():
    calls = []

    def rpc(*args):
        calls.append(args)

    repo = ReviewRepository(SimpleNamespace(), service_db=SimpleNamespace(rpc=rpc))
    with pytest.raises(ReviewDomainException):
        immediate(
            repo.settle_failure(str(uuid4()), str(uuid4()), uuid4(), "Timeout: secret detail")
        )
    assert calls == []

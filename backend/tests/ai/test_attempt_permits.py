import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.ai.gateway import GatewayError
from app.services.generation.attempts import AttemptPermit, DurableAttemptBudget


def grant(op, attempt, **changes):
    return AttemptPermit(
        **{
            "operation_id": op,
            "attempt_id": attempt,
            "dispatch_permitted": True,
            "calls_used": 1,
            "remaining_calls": 29,
            "replayed": False,
            **changes,
        }
    )


@pytest.mark.asyncio
async def test_each_attempt_has_distinct_identity_and_local_ceiling():
    seen = []

    async def acquire(operation_id, attempt_id):
        seen.append((operation_id, attempt_id))
        return grant(operation_id, attempt_id, calls_used=len(seen))

    op = uuid4()
    budget = DurableAttemptBudget(4, op, acquire)
    await asyncio.gather(*(budget.reserve() for _ in range(4)))
    with pytest.raises(GatewayError, match="REQUEST_BUDGET_EXHAUSTED"):
        await budget.reserve()
    assert budget.used == 4
    assert len({attempt for _, attempt in seen}) == 4
    assert all(operation == op for operation, _ in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,code",
    [
        ({"dispatch_permitted": False}, "REVIEW_QUOTA_EXHAUSTED"),
        ({"replayed": True}, "REVIEW_ATTEMPT_REPLAYED"),
        ({"operation_id": uuid4()}, "REVIEW_PERMIT_INVALID"),
        ({"attempt_id": uuid4()}, "REVIEW_PERMIT_INVALID"),
        ({"calls_used": 0}, "REVIEW_PERMIT_INVALID"),
    ],
)
async def test_invalid_denied_and_replayed_permits_stop_without_reacquiring(change, code):
    callback = AsyncMock(side_effect=lambda op, attempt: grant(op, attempt, **change))
    budget = DurableAttemptBudget(4, uuid4(), callback)
    for _ in range(2):
        with pytest.raises(GatewayError, match=code):
            await budget.reserve()
    callback.assert_awaited_once()
    assert budget.used == 0


@pytest.mark.asyncio
async def test_lost_response_is_sanitized_and_never_retried_with_a_new_id():
    callback = AsyncMock(side_effect=OSError("private database details"))
    budget = DurableAttemptBudget(4, uuid4(), callback)
    for _ in range(2):
        with pytest.raises(GatewayError, match="REVIEW_PERMIT_UNCERTAIN") as exc:
            await budget.reserve()
        assert "private" not in str(exc.value)
        assert not exc.value.retryable
    callback.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancellation_during_acquisition_requires_reconciliation():
    entered = asyncio.Event()

    async def acquire(op, attempt):
        entered.set()
        await asyncio.Event().wait()

    callback = AsyncMock(side_effect=acquire)
    budget = DurableAttemptBudget(4, uuid4(), callback)
    task = asyncio.create_task(budget.reserve())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(GatewayError, match="REVIEW_PERMIT_UNCERTAIN"):
        await budget.reserve()
    callback.assert_awaited_once()


def test_rpc_wrapper_must_preserve_strict_boolean_and_counter_types():
    for changes in [{"dispatch_permitted": "false"}, {"replayed": 0}, {"calls_used": True}]:
        with pytest.raises(ValidationError):
            grant(uuid4(), uuid4(), **changes)

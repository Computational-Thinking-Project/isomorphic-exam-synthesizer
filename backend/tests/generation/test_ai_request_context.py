import asyncio
import time
from typing import cast
from uuid import uuid4

import pytest

from app.services.ai.gateway import GatewayError
from app.services.generation.ai_request_context import JobRequestReservation
from app.services.generation.job_contracts import (
    GenerationJobError,
    GenerationJobStore,
    GenerationPlan,
    GenerationQuotaExceeded,
    QuestionTarget,
)


class QuotaStore:
    def __init__(self, count=0, *, error=None, response=None):
        self.count = count
        self.calls = 0
        self.error = error
        self.response = response

    async def reserve_gemini_call(self, plan):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.count >= 250:
            raise GenerationQuotaExceeded()
        self.count += 1
        return self.response if self.response is not None else self.count


def reservation(store, *, count=0, deadline=None):
    plan = GenerationPlan(
        uuid4(), uuid4(), (QuestionTarget(uuid4(), 1, 1),), frozenset(), count, None
    )
    return JobRequestReservation(
        cast(GenerationJobStore, store),
        plan,
        time.monotonic() + 30 if deadline is None else deadline,
    )


@pytest.mark.asyncio
async def test_hook_returns_none_and_never_resets_existing_quota():
    store = QuotaStore(249)
    hook = reservation(store, count=249)
    assert await hook.context.reserve_request() is None
    assert store.count == 250 and store.calls == 1
    with pytest.raises(GatewayError) as error:
        await hook.context.reserve_request()
    assert error.value.code == "REQUEST_BUDGET_EXHAUSTED" and not error.value.retryable
    assert store.calls == 1


@pytest.mark.asyncio
async def test_database_quota_rejection_stays_a_budget_error():
    store = QuotaStore(error=GenerationQuotaExceeded())
    hook = reservation(store)
    with pytest.raises(GatewayError) as error:
        await hook.context.reserve_request()
    assert error.value.code == "REQUEST_BUDGET_EXHAUSTED"
    hook.raise_if_failed()
    with pytest.raises(GatewayError):
        await hook.context.reserve_request()
    assert store.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [0, -1, 251, True, "1", 10])
async def test_invalid_or_nonincreasing_committed_counts_latch_storage_failure(response):
    store = QuotaStore(10, response=response)
    hook = reservation(store, count=10)
    for operation in (hook.context.reserve_request, hook.context.reserve_request):
        with pytest.raises(GenerationJobError) as error:
            await operation()
        assert error.value.code == "ERR_GENERATION_STORAGE_FAILURE"
    assert store.calls == 1
    with pytest.raises(GenerationJobError):
        hook.raise_if_failed()


@pytest.mark.asyncio
async def test_uncertain_storage_failure_is_not_retried_by_concurrent_reservations():
    store = QuotaStore(error=ConnectionError("private database URL"))
    hook = reservation(store)
    errors = await asyncio.gather(
        *(hook.context.reserve_request() for _ in range(8)), return_exceptions=True
    )
    assert store.calls == 1
    assert all(isinstance(error, GenerationJobError) for error in errors)
    assert all("private" not in str(error) for error in errors)


@pytest.mark.asyncio
async def test_deadline_before_reservation_spends_nothing():
    store = QuotaStore()
    hook = reservation(store, deadline=time.monotonic() - 1)
    with pytest.raises(GatewayError) as error:
        await hook.context.reserve_request()
    assert error.value.code == "JOB_DEADLINE" and store.calls == 0


@pytest.mark.asyncio
async def test_cancelled_reservation_is_uncertain_and_cannot_be_sent_again():
    entered = asyncio.Event()

    class PendingStore(QuotaStore):
        async def reserve_gemini_call(self, plan):
            self.calls += 1
            entered.set()
            await asyncio.Event().wait()

    store = PendingStore()
    hook = reservation(store)
    task = asyncio.create_task(hook.context.reserve_request())
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(GenerationJobError):
        await hook.context.reserve_request()
    assert store.calls == 1


@pytest.mark.parametrize("deadline", [True, "1", float("nan"), float("inf")])
def test_invalid_deadline_is_rejected(deadline):
    with pytest.raises(ValueError):
        reservation(QuotaStore(), deadline=deadline)

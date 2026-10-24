import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from google.genai import errors, types

from app.core.config import Settings
from app.services.ai import gateway as module
from app.services.ai.gateway import GatewayError, GeminiGateway, RequestBudget, RequestContext


@pytest.fixture
def pool(monkeypatch):
    clients = []

    def create(**kwargs):
        client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=AsyncMock(return_value="response")),
                aclose=AsyncMock(),
            ),
            close=Mock(),
        )
        clients.append((kwargs, client))
        return client

    monkeypatch.setattr(module.genai, "Client", create)
    monkeypatch.setattr(module.secrets, "choice", lambda entries: entries[0])
    return clients


def settings(**kwargs):
    return Settings(
        _env_file=None,
        GEMINI_API_KEY="",
        GEMINI_API_KEY_1="test-one",
        GEMINI_API_KEY_2="test-two",
        GEMINI_API_KEY_3="",
        **kwargs,
    )


def context(budget, seconds=1):
    return RequestContext(time.monotonic() + seconds, budget.reserve)


async def send(gateway, ctx):
    return await gateway.generate_content(
        contents="data", config=types.GenerateContentConfig(), context=ctx
    )


@pytest.mark.asyncio
async def test_rate_limited_key_is_skipped_on_next_request_and_budget_counts(pool):
    gateway = GeminiGateway(settings())
    budget = RequestBudget(3)
    pool[0][1].aio.models.generate_content.side_effect = errors.ClientError(429, {})
    with pytest.raises(GatewayError, match="API_RATE_LIMIT"):
        await send(gateway, context(budget))
    assert await send(gateway, context(budget)) == "response"
    assert budget.used == 2
    assert [c.aio.models.generate_content.await_count for _, c in pool] == [1, 1]
    assert all(args["http_options"].retry_options.attempts == 1 for args, _ in pool)
    await gateway.aclose()


@pytest.mark.asyncio
async def test_expired_job_does_not_reserve_or_send_even_if_sdk_returns_immediately(pool):
    gateway = GeminiGateway(settings())
    budget = RequestBudget(3)
    with pytest.raises(GatewayError, match="JOB_DEADLINE"):
        await send(gateway, context(budget, seconds=-1))
    assert budget.used == 0
    for _, client in pool:
        client.aio.models.generate_content.assert_not_awaited()
    await gateway.aclose()


@pytest.mark.asyncio
async def test_all_keys_cool_down_without_spinning_or_spending_budget(pool):
    gateway = GeminiGateway(settings())
    for _, client in pool:
        client.aio.models.generate_content.side_effect = errors.ClientError(429, {})
    budget = RequestBudget(10)
    ctx = context(budget, seconds=0.05)
    for _ in range(2):
        with pytest.raises(GatewayError, match="API_RATE_LIMIT"):
            await send(gateway, ctx)
    with pytest.raises(GatewayError, match="JOB_DEADLINE"):
        await send(gateway, ctx)
    assert budget.used == 2
    await gateway.aclose()


@pytest.mark.asyncio
async def test_auth_disables_key_and_errors_never_include_sdk_secret(pool):
    gateway = GeminiGateway(settings())
    budget = RequestBudget(10)
    for _, client in pool:
        client.aio.models.generate_content.side_effect = errors.ClientError(
            403, {"error": {"message": "secret-credential-url"}}
        )
    for index in range(2):
        with pytest.raises(GatewayError, match="API_AUTH") as caught:
            await send(gateway, context(budget))
        assert "secret-credential" not in str(caught.value)
        assert caught.value.retryable is (index == 0)
    with pytest.raises(GatewayError, match="API_NO_AVAILABLE_KEYS"):
        await send(gateway, context(budget))
    assert budget.used == 2
    await gateway.aclose()


@pytest.mark.asyncio
async def test_concurrent_requests_respect_global_limit_and_atomic_budget(pool):
    active = maximum = 0

    async def slow(**kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.01)
            return "response"
        finally:
            active -= 1

    gateway = GeminiGateway(settings(GEMINI_MAX_CONCURRENCY=2))
    for _, client in pool:
        client.aio.models.generate_content.side_effect = slow
    budget = RequestBudget(5)
    ctx = context(budget)
    results = await asyncio.gather(*(send(gateway, ctx) for _ in range(10)), return_exceptions=True)
    assert maximum == 2
    assert budget.used == 5
    assert results.count("response") == 5
    assert all(isinstance(r, GatewayError) for r in results if r != "response")
    await gateway.aclose()


@pytest.mark.asyncio
async def test_deadline_while_queued_spends_no_extra_request(pool):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(**kwargs):
        started.set()
        await release.wait()
        return "response"

    gateway = GeminiGateway(settings(GEMINI_MAX_CONCURRENCY=1))
    pool[0][1].aio.models.generate_content.side_effect = slow
    budget = RequestBudget(3)
    first = asyncio.create_task(send(gateway, context(budget)))
    await started.wait()
    with pytest.raises(GatewayError, match="JOB_DEADLINE"):
        await send(gateway, context(budget, seconds=0.01))
    assert budget.used == 1
    release.set()
    await first
    await gateway.aclose()


@pytest.mark.asyncio
async def test_timeout_and_cancel_release_capacity_and_cleanup(pool):
    gateway = GeminiGateway(settings(GEMINI_REQUEST_TIMEOUT_SECONDS=0.01))

    async def slow(**kwargs):
        await asyncio.sleep(10)

    pool[0][1].aio.models.generate_content.side_effect = slow
    budget = RequestBudget(5)
    with pytest.raises(GatewayError, match="API_TIMEOUT"):
        await send(gateway, context(budget))
    task = asyncio.create_task(send(gateway, context(budget)))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    pool[0][1].aio.models.generate_content.side_effect = None
    assert await send(gateway, context(budget)) == "response"
    await gateway.aclose()
    await gateway.aclose()
    for _, client in pool:
        client.aio.aclose.assert_awaited_once()
        client.close.assert_called_once()
    with pytest.raises(GatewayError, match="GATEWAY_CLOSED"):
        await send(gateway, context(budget))

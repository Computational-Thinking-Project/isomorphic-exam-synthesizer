import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from typing import cast
from uuid import UUID

import pytest

from app.services.observability.runtime_registry import RuntimeRegistry


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


@pytest.fixture
def registry() -> RuntimeRegistry:
    result = RuntimeRegistry(clock=Clock())
    result.start()
    return result


@pytest.mark.parametrize(
    "operation",
    [
        lambda registry: registry.snapshot(),
        lambda registry: registry.begin_sse_connection(),
        lambda registry: registry.begin_job(UUID(int=1)),
        lambda registry: registry.begin_gemini_attempt(),
    ],
)
def test_operations_require_explicit_startup(
    operation: Callable[[RuntimeRegistry], object],
) -> None:
    with pytest.raises(RuntimeError):
        operation(RuntimeRegistry(clock=Clock()))


def test_startup_is_explicit_and_repeated_start_does_not_reset_state() -> None:
    clock = Clock()
    registry = RuntimeRegistry(clock=clock)
    clock.value = 200.0
    registry.start()
    connection = registry.begin_sse_connection()
    clock.value = 212.5
    registry.start()
    snapshot = registry.snapshot()
    assert snapshot.uptime_seconds == 12.5
    assert snapshot.active_sse_connections == 1
    assert snapshot.gemini_call_count == 0
    assert snapshot.gemini_error_rate == 0
    assert snapshot.background_jobs_running == 0
    connection.close()


@pytest.mark.parametrize("value", [True, None, "1", float("nan"), float("inf"), float("-inf")])
def test_invalid_startup_clock_is_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        RuntimeRegistry(clock=Clock(cast(float, value))).start()


@pytest.mark.parametrize("value", [99.0, True, float("nan"), float("inf"), float("-inf")])
def test_invalid_elapsed_clock_is_not_hidden_as_zero(value: float) -> None:
    clock = Clock()
    registry = RuntimeRegistry(clock=clock)
    registry.start()
    clock.value = value
    with pytest.raises(ValueError):
        registry.snapshot()


def test_clock_origin_can_be_negative() -> None:
    clock = Clock(-50.0)
    registry = RuntimeRegistry(clock=clock)
    registry.start()
    clock.value = -48.0
    assert registry.snapshot().uptime_seconds == 2.0


def test_sse_counts_connections_and_cleanup_is_idempotent(registry: RuntimeRegistry) -> None:
    first = registry.begin_sse_connection()
    second = registry.begin_sse_connection()
    assert registry.snapshot().active_sse_connections == 2
    first.close()
    first.close()
    assert registry.snapshot().active_sse_connections == 1
    second.close()
    assert registry.snapshot().active_sse_connections == 0


def test_jobs_count_distinct_executing_sessions_until_last_handle_closes(
    registry: RuntimeRegistry,
) -> None:
    first = registry.begin_job(UUID(int=1))
    duplicate = registry.begin_job(UUID(int=1))
    second = registry.begin_job(UUID(int=2))
    assert registry.snapshot().background_jobs_running == 2
    first.close()
    first.close()
    assert registry.snapshot().background_jobs_running == 2
    duplicate.close()
    assert registry.snapshot().background_jobs_running == 1
    second.close()
    assert registry.snapshot().background_jobs_running == 0
    replacement = registry.begin_job(UUID(int=1))
    assert registry.snapshot().background_jobs_running == 1
    replacement.close()


@pytest.mark.parametrize("session_id", [None, "", "session-id", str(UUID(int=1)), 1, True])
def test_jobs_require_canonical_session_ids(registry: RuntimeRegistry, session_id: object) -> None:
    with pytest.raises(TypeError):
        registry.begin_job(cast(UUID, session_id))
    assert registry.snapshot().background_jobs_running == 0


def test_gemini_ratio_excludes_inflight_attempts_and_retries_are_separate(
    registry: RuntimeRegistry,
) -> None:
    failed = registry.begin_gemini_attempt()
    retry = registry.begin_gemini_attempt()
    inflight = registry.begin_gemini_attempt()
    assert registry.snapshot().gemini_call_count == 3
    assert registry.snapshot().gemini_error_rate == 0
    failed.finish(failed=True)
    assert registry.snapshot().gemini_error_rate == 1
    retry.finish(failed=False)
    assert registry.snapshot().gemini_error_rate == 0.5
    failed.finish(failed=False)
    retry.finish(failed=True)
    assert registry.snapshot().gemini_error_rate == 0.5
    inflight.finish(failed=False)
    assert registry.snapshot().gemini_error_rate == pytest.approx(1 / 3)


def test_unknown_provider_outcome_can_be_released_without_inventing_success_or_failure(
    registry: RuntimeRegistry,
) -> None:
    unknown = registry.begin_gemini_attempt()
    unknown.abandon()
    unknown.abandon()
    unknown.finish(failed=True)
    success = registry.begin_gemini_attempt()
    success.finish(failed=False)
    assert registry.snapshot().gemini_call_count == 2
    assert registry.snapshot().gemini_error_rate == 0


@pytest.mark.parametrize("failed", [None, 0, 1, "false"])
def test_attempt_outcomes_are_explicit_booleans(registry: RuntimeRegistry, failed: object) -> None:
    attempt = registry.begin_gemini_attempt()
    with pytest.raises(TypeError):
        attempt.finish(failed=cast(bool, failed))
    attempt.finish(failed=True)
    assert registry.snapshot().gemini_error_rate == 1


def test_parallel_cleanup_does_not_finish_the_same_attempt_multiple_times(
    registry: RuntimeRegistry,
) -> None:
    attempt = registry.begin_gemini_attempt()
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: attempt.finish(failed=True), range(40)))
    success = registry.begin_gemini_attempt()
    success.finish(failed=False)
    assert registry.snapshot().gemini_error_rate == 0.5


def test_parallel_producers_and_snapshot_readers_keep_consistent_counts(
    registry: RuntimeRegistry,
) -> None:
    def work(index: int) -> None:
        connection = registry.begin_sse_connection()
        job = registry.begin_job(UUID(int=index % 4 + 1))
        attempt = registry.begin_gemini_attempt()
        snapshot = registry.snapshot()
        assert snapshot.active_sse_connections >= 1
        assert 1 <= snapshot.background_jobs_running <= 4
        assert 0 <= snapshot.gemini_error_rate <= 1
        attempt.finish(failed=index % 4 == 0)
        connection.close()
        job.close()

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(work, range(400)))
    snapshot = registry.snapshot()
    assert snapshot.gemini_call_count == 400
    assert snapshot.gemini_error_rate == 0.25
    assert snapshot.active_sse_connections == snapshot.background_jobs_running == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_async_producers_release_gauges_in_finally(
    registry: RuntimeRegistry, error: type[BaseException]
) -> None:
    async def work() -> None:
        connection = registry.begin_sse_connection()
        job = registry.begin_job(UUID(int=1))
        try:
            await asyncio.sleep(0)
            raise error()
        finally:
            connection.close()
            job.close()

    with pytest.raises(error):
        await work()
    assert registry.snapshot().active_sse_connections == 0
    assert registry.snapshot().background_jobs_running == 0


def test_new_registry_has_separate_worker_state(registry: RuntimeRegistry) -> None:
    registry.begin_sse_connection().close()
    registry.begin_gemini_attempt().finish(failed=True)
    fresh = RuntimeRegistry(clock=Clock())
    fresh.start()
    assert fresh.snapshot().gemini_call_count == 0
    assert registry.snapshot().gemini_call_count == 1


def test_snapshot_is_immutable_and_reading_does_not_change_counters(
    registry: RuntimeRegistry,
) -> None:
    first = registry.snapshot()
    assert registry.snapshot() == first
    with pytest.raises(FrozenInstanceError):
        setattr(first, "gemini_call_count", 100)

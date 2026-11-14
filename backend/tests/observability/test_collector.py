from collections.abc import Callable
from typing import cast
from uuid import uuid4

import pytest

from app.services.observability.collector import (
    RuntimeMetricsCollector,
    RuntimeMetricsUnavailableError,
)
from app.services.observability.runtime_registry import RuntimeRegistry


def test_fresh_snapshot_tracks_shared_registry_and_reads_memory_each_time() -> None:
    now = [10.0]
    registry = RuntimeRegistry(clock=lambda: now[0])
    registry.start()
    memory = iter([32.0, 48.0])
    collector = RuntimeMetricsCollector(
        registry, gemini_model="configured-model", memory_reader=lambda: next(memory)
    )
    assert collector.collect().process_memory_mb == 32
    connection = registry.begin_sse_connection()
    job = registry.begin_job(uuid4())
    registry.begin_gemini_attempt().finish(failed=True)
    now[0] = 15
    result = collector.collect()
    assert result.model_dump() == {
        "status": "operational",
        "gemini_model": "configured-model",
        "uptime_seconds": 5.0,
        "active_sse_connections": 1,
        "gemini_call_count": 1,
        "gemini_error_rate": 1.0,
        "background_jobs_running": 1,
        "process_memory_mb": 48.0,
    }
    connection.close()
    job.close()


@pytest.mark.parametrize("memory", [-1.0, float("nan"), float("inf"), True, "32"])
def test_invalid_memory_never_becomes_partial_success(memory: object) -> None:
    registry = RuntimeRegistry()
    registry.start()
    collector = RuntimeMetricsCollector(
        registry, gemini_model="model", memory_reader=cast(Callable[[], float], lambda: memory)
    )
    with pytest.raises(RuntimeMetricsUnavailableError):
        collector.collect()


def test_unstarted_registry_and_memory_failure_are_safe() -> None:
    registry = RuntimeRegistry()

    def unavailable() -> float:
        raise OSError("private path")

    collector = RuntimeMetricsCollector(registry, gemini_model="model", memory_reader=unavailable)
    with pytest.raises(RuntimeMetricsUnavailableError, match="temporarily unavailable"):
        collector.collect()
    registry.start()
    with pytest.raises(RuntimeMetricsUnavailableError) as error:
        collector.collect()
    assert "private" not in str(error.value)


def test_blank_model_is_unavailable_without_fallback() -> None:
    registry = RuntimeRegistry()
    registry.start()
    collector = RuntimeMetricsCollector(registry, gemini_model=" ", memory_reader=lambda: 0.0)
    with pytest.raises(RuntimeMetricsUnavailableError):
        collector.collect()

"""Assemble a fresh worker snapshot without network probes or fallback values."""

from collections.abc import Callable

from app.models.runtime_metrics import RuntimeMetricsResponse
from app.services.observability.process_memory import read_process_memory_mb
from app.services.observability.runtime_registry import RuntimeRegistry


class RuntimeMetricsUnavailableError(RuntimeError):
    """Safe failure for the eventual HTTP 503 mapping."""


class RuntimeMetricsCollector:
    def __init__(
        self,
        registry: RuntimeRegistry,
        *,
        gemini_model: str,
        memory_reader: Callable[[], float] = read_process_memory_mb,
    ) -> None:
        self._registry = registry
        self._model = gemini_model
        self._memory_reader = memory_reader

    def collect(self) -> RuntimeMetricsResponse:
        try:
            activity = self._registry.snapshot()
            return RuntimeMetricsResponse(
                status="operational",
                gemini_model=self._model,
                uptime_seconds=activity.uptime_seconds,
                active_sse_connections=activity.active_sse_connections,
                gemini_call_count=activity.gemini_call_count,
                gemini_error_rate=activity.gemini_error_rate,
                background_jobs_running=activity.background_jobs_running,
                process_memory_mb=self._memory_reader(),
            )
        except Exception:
            raise RuntimeMetricsUnavailableError(
                "Runtime metrics are temporarily unavailable."
            ) from None

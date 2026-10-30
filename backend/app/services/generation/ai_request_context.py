"""Adapt durable reservations to the AI hook; never count a batch as a call."""

import asyncio
import math
import time

from app.services.ai.gateway import GatewayError, RequestContext
from app.services.generation.job_contracts import (
    GenerationJobError,
    GenerationJobStore,
    GenerationPlan,
    GenerationQuotaExceeded,
)


class JobRequestReservation:
    """One job-scoped hook, with a fatal latch for uncertain storage outcomes.

    The AI service can convert callback exceptions into QuestionResult errors.
    Its caller must check raise_if_failed before saving any subsequent result
    and after the batch. A failed/cancelled DB write is never retried here.
    """

    def __init__(self, store: GenerationJobStore, plan: GenerationPlan, deadline: float) -> None:
        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
        ):
            raise ValueError("Expected a finite absolute job deadline.")
        self._store = store
        self._plan = plan
        self._deadline = float(deadline)
        self._last_count = plan.gemini_call_count
        self._failed = False
        self._exhausted = self._last_count >= 250
        self._lock = asyncio.Lock()
        self.context = RequestContext(self._deadline, self.reserve)

    @staticmethod
    def _storage_failure() -> GenerationJobError:
        return GenerationJobError(
            503,
            "ERR_GENERATION_STORAGE_FAILURE",
            "Generation reservation could not be confirmed. Verify session state before retrying.",
        )

    def raise_if_failed(self) -> None:
        if self._failed:
            raise self._storage_failure() from None

    async def reserve(self) -> None:
        # Serializing reservations prevents a second dispatch after this hook
        # has learned that the previous database outcome is uncertain.
        async with self._lock:
            self.raise_if_failed()
            if time.monotonic() >= self._deadline:
                raise GatewayError("JOB_DEADLINE")
            if self._exhausted:
                raise GatewayError("REQUEST_BUDGET_EXHAUSTED")
            try:
                async with asyncio.timeout_at(self._deadline):
                    count = await self._store.reserve_gemini_call(self._plan)
            except GenerationQuotaExceeded:
                self._exhausted = True
                raise GatewayError("REQUEST_BUDGET_EXHAUSTED") from None
            except asyncio.CancelledError:
                self._failed = True
                raise
            except Exception:
                self._failed = True
                raise self._storage_failure() from None
            if type(count) is not int or not self._last_count < count <= 250:
                self._failed = True
                raise self._storage_failure() from None
            self._last_count = count
            self._exhausted = count == 250

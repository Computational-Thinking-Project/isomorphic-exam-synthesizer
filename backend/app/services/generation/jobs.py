"""Durable-progress orchestrator with explicitly injected DB and AI adapters."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, TypeVar
from uuid import UUID

from app.models.generation_events import EventName, GenerationEventData, SessionOutcome
from app.services.generation.events import GenerationEventBroker
from app.services.generation.job_contracts import (
    GeneratedDraft,
    GenerationJobError,
    GenerationJobStore,
    GenerationPlan,
    GenerationQuotaExceeded,
    QuestionTarget,
)
from app.services.observability.runtime_registry import RuntimeRegistry

T = TypeVar("T")


class ProviderCalls:
    """AI adapter wraps EACH raw outbound attempt, including repair/retry, here.

    Never wrap an entire generate/validate method. Local schema/math failures
    after a successful response are outside this boundary. SDK-hidden retries
    must be disabled or observed by the eventual AI adapter.
    """

    def __init__(
        self,
        store: GenerationJobStore,
        plan: GenerationPlan,
        registry: RuntimeRegistry,
        semaphore: asyncio.Semaphore,
        deadline: float,
    ) -> None:
        self._store = store
        self._plan = plan
        self._registry = registry
        self._semaphore = semaphore
        self.deadline = deadline
        self._count = plan.gemini_call_count

    async def send(self, outbound: Callable[[], Awaitable[T]]) -> T:
        async with asyncio.timeout_at(self.deadline):
            async with self._semaphore:
                if self._count >= 250:
                    raise GenerationQuotaExceeded("Gemini batch quota exhausted.")
                count = await self._store.reserve_gemini_call(self._plan)
                if type(count) is not int or not 1 <= count <= 250:
                    raise RuntimeError("Invalid durable reservation response.")
                self._count = max(self._count, count)
                if asyncio.get_running_loop().time() >= self.deadline:
                    raise TimeoutError("Generation deadline expired before transport.")
                handle = self._registry.begin_gemini_attempt()
                try:
                    result = await outbound()
                except asyncio.CancelledError:
                    handle.abandon()
                    raise
                except Exception:
                    handle.finish(failed=True)
                    raise
                else:
                    handle.finish(failed=False)
                    return result


class GenerationPipeline(Protocol):
    async def generate(
        self, plan: GenerationPlan, target: QuestionTarget, calls: ProviderCalls
    ) -> GeneratedDraft | None:
        """AI + four validators; None means no saveable candidate.

        A saveable candidate that fails validation after retries is returned
        with has_warning=True. Returning None never invents a placeholder row.
        """
        ...


@dataclass(frozen=True, slots=True)
class JobOutcome:
    status: SessionOutcome
    completed: int
    total: int
    error_code: str | None = None
    state_persisted: bool = True


class GenerationJobRunner:
    """One shared runner/worker; DB claim remains authoritative across restarts.

    Current items run in deterministic order. The shared provider semaphore
    bounds outbound requests across all jobs, not merely within a single job.
    """

    def __init__(
        self,
        pipeline: GenerationPipeline,
        events: GenerationEventBroker,
        registry: RuntimeRegistry,
        *,
        timeout_seconds: float = 600,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 600
        ):
            raise ValueError("Job timeout must be positive and at most 600 seconds.")
        self._pipeline = pipeline
        self._events = events
        self._registry = registry
        self._timeout = timeout_seconds
        self._provider_slots = asyncio.Semaphore(3)
        self._claims: dict[UUID, UUID | None] = {}
        self._executing: set[UUID] = set()
        self._claim_lock = asyncio.Lock()

    async def claim(
        self, store: GenerationJobStore, session_id: UUID, *, retry: bool = False
    ) -> GenerationPlan:
        async with self._claim_lock:
            if session_id in self._claims:
                raise GenerationJobError(
                    409, "ERR_ALREADY_GENERATING", "The session is already generating."
                )
            self._claims[session_id] = None
        try:
            await self._events.ensure_session(session_id)
            # The store must compare timestamps inside its update/transaction.
            await store.fail_stale(
                session_id, cutoff=datetime.now(timezone.utc) - timedelta(minutes=12)
            )
            plan = await store.claim(session_id, retry=retry)
            if plan.session_id != session_id:
                raise ValueError("Claim returned another session.")
            await self._events.reopen(session_id)
            async with self._claim_lock:
                self._claims[session_id] = plan.job_id
            return plan
        except BaseException:
            async with self._claim_lock:
                self._claims.pop(session_id, None)
            raise

    async def run(self, plan: GenerationPlan, store: GenerationJobStore) -> JobOutcome:
        async with self._claim_lock:
            if (
                self._claims.get(plan.session_id) != plan.job_id
                or plan.session_id in self._executing
            ):
                raise GenerationJobError(
                    409, "ERR_ALREADY_GENERATING", "No pending claim is available for this job."
                )
            self._executing.add(plan.session_id)
        completed = set(plan.saved)
        total = len(plan.targets)
        code: str | None = None
        cancelled = False
        fatal = False
        handle = None
        try:
            handle = self._registry.begin_job(plan.session_id)
            deadline = asyncio.get_running_loop().time() + self._timeout
            calls = ProviderCalls(store, plan, self._registry, self._provider_slots, deadline)
            async with asyncio.timeout_at(deadline):
                for target in plan.targets:
                    if target in completed:
                        continue
                    await self._emit(plan, "progress", len(completed), target=target)
                    draft = await self._pipeline.generate(plan, target, calls)
                    if draft is None:
                        await self._emit(
                            plan,
                            "warning",
                            len(completed),
                            target=target,
                            code="ERR_NO_SAVEABLE_CANDIDATE",
                        )
                        continue
                    draft = GeneratedDraft.model_validate(draft.model_dump())
                    # Emit done ONLY after the per-question durable commit succeeds.
                    await store.save_draft(plan, target, draft)
                    completed.add(target)
                    if draft.has_warning:
                        await self._emit(
                            plan,
                            "warning",
                            len(completed),
                            target=target,
                            draft=draft,
                            code="ERR_VALIDATION_WARNING",
                        )
                    await self._emit(
                        plan, "question_done", len(completed), target=target, draft=draft
                    )
        except GenerationQuotaExceeded:
            code = "ERR_GEMINI_QUOTA_EXHAUSTED"
        except TimeoutError:
            code = "ERR_GENERATION_TIMEOUT"
        except asyncio.CancelledError:
            code = "ERR_GENERATION_INTERRUPTED"
            cancelled = True
        except Exception:
            code = "ERR_GENERATION_FAILED"
            fatal = True
        try:
            if len(completed) < total and code is None:
                code = "ERR_GENERATION_INCOMPLETE"
            outcome: SessionOutcome = (
                "failed"
                if fatal
                else "generated"
                if len(completed) == total
                else "partial_generated"
                if completed
                else "failed"
            )
            persisted = True
            try:
                # Bounded cleanup outside the expired job timeout. Fenced store
                # refuses stale workers and must not blindly retry uncertain writes.
                async with asyncio.timeout(10):
                    await store.finish(plan, outcome, error_code=code)
            except Exception:
                persisted = False
                code = "ERR_GENERATION_STORAGE_FAILURE"
            try:
                await self._emit(
                    plan,
                    "error" if not persisted or outcome == "failed" else "done",
                    len(completed),
                    code=code,
                    outcome=outcome if persisted else None,
                )
            except Exception:
                # A notification failure must not rewrite an already committed state.
                pass
            result = JobOutcome(outcome, len(completed), total, code, persisted)
            if cancelled:
                raise asyncio.CancelledError
            return result
        finally:
            if handle is not None:
                handle.close()
            async with self._claim_lock:
                self._claims.pop(plan.session_id, None)
                self._executing.discard(plan.session_id)

    async def _emit(
        self,
        plan: GenerationPlan,
        event: EventName,
        completed: int,
        *,
        target: QuestionTarget | None = None,
        draft: GeneratedDraft | None = None,
        code: str | None = None,
        outcome: SessionOutcome | None = None,
    ) -> None:
        await self._events.publish(
            plan.session_id,
            event,
            GenerationEventData(
                timestamp=datetime.now(timezone.utc),
                question_no=target.question_no if target else None,
                version_index=target.version_index if target else None,
                status="warning"
                if event in {"warning", "error"}
                else "done"
                if event in {"done", "question_done"}
                else "generating",
                percent_complete=completed * 100 / len(plan.targets),
                retry_count=draft.retry_count if draft else 0,
                error_code=code,
                error_message="Generation could not complete this operation." if code else None,
                session_status=outcome,
            ),
        )

"""Bridge a server-owned job snapshot to the existing async AI batch service.

This module does not create clients, confirm sources, implement SQL, publish SSE
or register routes. Its required callback owns durable persistence and must
commit before returning or reporting progress to a browser.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from app.models.generation import BatchResult, QuestionResult
from app.models.schemas import SourceQuestion
from app.services.generation.ai_mapping import PreparedAIResult, prepare_question_result
from app.services.generation.ai_request_context import JobRequestReservation
from app.services.generation.job_contracts import GenerationJobStore, GenerationPlan, QuestionTarget
from app.services.generation.service import GenerationService


class AIBatchInputs(BaseModel):
    """Explicit server-supplied inputs, not an HTTP request or DB schema.

    The stored confirmation hash must come from the trusted confirmation flow.
    Accepting it here is not proof that a user has confirmed the source.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sources: tuple[SourceQuestion, ...] = Field(min_length=1, max_length=20)
    blueprints: dict[str, dict[str, Any]]
    confirmed_source_hash: StrictStr
    base_seed: StrictInt
    variation_modes: tuple[StrictStr, ...]
    completed: tuple[QuestionResult, ...]

    @field_validator("confirmed_source_hash")
    @classmethod
    def nonblank_hash(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A stored source confirmation hash is required.")
        return value


def _check_plan_inputs(plan: GenerationPlan, inputs: AIBatchInputs) -> None:
    source_numbers = {target.source_question_id: target.question_no for target in plan.targets}
    expected_order = sorted(source_numbers, key=lambda key: source_numbers[key])
    source_ids = [UUID(source.id) for source in inputs.sources]
    if source_ids != expected_order:
        raise ValueError("AI sources do not match the plan's ordered source identities.")
    if set(inputs.blueprints) != {source.id for source in inputs.sources}:
        raise ValueError("AI Blueprints do not cover the job sources.")
    cached: set[QuestionTarget] = set()
    indices = {source_id: index for index, source_id in enumerate(source_ids)}
    for result in inputs.completed:
        prepared = prepare_question_result(result, plan)
        if prepared.target in cached or prepared.draft is None or result.candidate is None:
            raise ValueError("Expected unique saveable completed AI results.")
        expected_seed = (
            inputs.base_seed
            + result.version_index * 1000
            + indices[UUID(result.source_question_id)]
        )
        if result.candidate.seed != expected_seed:
            raise ValueError("Completed AI result does not match the job seed.")
        cached.add(prepared.target)
    if cached != set(plan.saved):
        raise ValueError("Completed AI records do not match the committed job targets.")


class AIBatchAdapter:
    def __init__(self, service: GenerationService) -> None:
        # Inject AIRuntime.generation; never create another key pool or service.
        self._service = service

    async def run(
        self,
        plan: GenerationPlan,
        inputs: AIBatchInputs,
        store: GenerationJobStore,
        *,
        deadline: float,
        on_result: Callable[[PreparedAIResult], Awaitable[None]],
    ) -> BatchResult:
        # Revalidate nested mutable models and detach every external reference
        # before the first await. A frozen model alone is not a deep snapshot.
        snapshot = AIBatchInputs.model_validate(inputs.model_dump())
        _check_plan_inputs(plan, snapshot)
        reservation = JobRequestReservation(store, plan, deadline)
        callback_lock = asyncio.Lock()
        attempted: set[QuestionTarget] = set()
        acknowledged: set[QuestionTarget] = set()
        callback_failure: BaseException | None = None

        async def deliver(result: QuestionResult) -> None:
            nonlocal callback_failure
            reservation.raise_if_failed()
            prepared = prepare_question_result(result, plan)
            async with callback_lock:
                reservation.raise_if_failed()
                if callback_failure is not None:
                    raise callback_failure
                if prepared.target in plan.saved or prepared.target in attempted:
                    raise ValueError("AI must deliver each new target only once.")
                attempted.add(prepared.target)
                try:
                    await on_result(prepared)
                except BaseException as exc:
                    callback_failure = exc
                    raise
                acknowledged.add(prepared.target)

        try:
            async with asyncio.timeout_at(deadline):
                batch = await self._service.generate_exam_drafts(
                    list(snapshot.sources),
                    snapshot.blueprints,
                    confirmed_source_hash=snapshot.confirmed_source_hash,
                    n_versions=max(target.version_index for target in plan.targets),
                    context=reservation.context,
                    base_seed=snapshot.base_seed,
                    variation_modes=list(snapshot.variation_modes),
                    completed=list(snapshot.completed),
                    on_result=deliver,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            reservation.raise_if_failed()
            raise
        reservation.raise_if_failed()
        if callback_failure is not None:
            raise callback_failure
        checked = BatchResult.model_validate(batch.model_dump())
        results = [prepare_question_result(result, plan) for result in checked.results]
        keys = [result.target for result in results]
        if len(keys) != len(plan.targets) or set(keys) != set(plan.targets):
            raise ValueError("AI batch did not return exactly the planned targets.")
        if acknowledged != set(plan.targets) - set(plan.saved):
            raise ValueError("AI batch returned before all new result callbacks completed.")
        completed_count = sum(result.draft is not None for result in results)
        expected_status = (
            "generated"
            if completed_count == len(plan.targets)
            else "partial_generated"
            if completed_count
            else "failed"
        )
        if checked.status != expected_status:
            raise ValueError("AI batch status does not match its results.")
        return checked

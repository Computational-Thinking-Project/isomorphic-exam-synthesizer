import asyncio
import json
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.models.generation import (
    BatchResult,
    CandidatePayload,
    GeneratedQuestion,
    QuestionResult,
    ValidationReport,
    render_solution,
)
from app.models.schemas import SourceQuestion
from app.services.blueprint.adapters import prepare_sources
from app.services.blueprint.service import source_fingerprint
from app.services.generation.ai_batch_adapter import AIBatchAdapter, AIBatchInputs
from app.services.generation.job_contracts import (
    GenerationJobError,
    GenerationJobStore,
    GenerationPlan,
    QuestionTarget,
)
from app.services.generation.service import GenerationService, fingerprint
from app.services.validator.pipeline import validate_solution


def setup_case():
    data = json.loads((Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text())
    source = SourceQuestion.model_validate(data["source"])
    payload = CandidatePayload.model_validate(data["candidates"][0])
    result = QuestionResult(
        version_index=1,
        source_question_id=source.id,
        request_fingerprint="request-fingerprint",
        candidate=GeneratedQuestion(
            **payload.model_dump(),
            source_question_id=source.id,
            variant_id="var_new",
            blueprint_fingerprint=fingerprint(data["blueprint"]),
            seed=1100,
            solution_md=render_solution(payload.solution),
            has_warning=True,
        ),
        validation=ValidationReport(checks=validate_solution(payload)),
        attempts=1,
    )
    plan = GenerationPlan(
        uuid4(), uuid4(), (QuestionTarget(UUID(source.id), 1, 1),), frozenset(), 0, None
    )
    inputs = AIBatchInputs(
        sources=(source,),
        blueprints={source.id: data["blueprint"]},
        confirmed_source_hash=source_fingerprint(prepare_sources([source])),
        base_seed=100,
        variation_modes=("context",),
        completed=(),
    )
    store = Mock()
    store.reserve_gemini_call = AsyncMock(return_value=1)
    service = Mock(spec=GenerationService)

    async def generate(sources, blueprints, **kwargs):
        await kwargs["context"].reserve_request()
        await kwargs["on_result"](result.model_copy(deep=True))
        return BatchResult(results=[result], status="generated")

    service.generate_exam_drafts = AsyncMock(side_effect=generate)
    return plan, inputs, store, service, result


async def run(case, callback=None):
    plan, inputs, store, service, _ = case
    return await AIBatchAdapter(service).run(
        plan,
        inputs,
        cast(GenerationJobStore, store),
        deadline=time.monotonic() + 30,
        on_result=callback if callback is not None else AsyncMock(),
    )


@pytest.mark.asyncio
async def test_adapter_calls_one_batch_with_full_inputs_and_prepared_callback():
    case = setup_case()
    callback = AsyncMock()
    result = await run(case, callback)
    plan, inputs, store, service, _ = case
    assert result.status == "generated"
    service.generate_exam_drafts.assert_awaited_once()
    args, kwargs = service.generate_exam_drafts.call_args
    assert args[0] == list(inputs.sources) and args[1] == inputs.blueprints
    assert kwargs["n_versions"] == 1 and kwargs["base_seed"] == 100
    assert kwargs["variation_modes"] == ["context"] and kwargs["completed"] == []
    assert kwargs["confirmed_source_hash"] == inputs.confirmed_source_hash
    store.reserve_gemini_call.assert_awaited_once_with(plan)
    prepared = callback.call_args.args[0]
    assert prepared.target == plan.targets[0] and prepared.draft is not None
    assert prepared.raw_result.candidate.seed == 1100


@pytest.mark.asyncio
async def test_adapter_waits_for_the_save_acknowledgement():
    case = setup_case()
    entered, release = asyncio.Event(), asyncio.Event()

    async def save(prepared):
        entered.set()
        await release.wait()

    task = asyncio.create_task(run(case, save))
    await asyncio.wait_for(entered.wait(), 1)
    assert not task.done()
    release.set()
    await task


@pytest.mark.asyncio
async def test_adapter_propagates_save_failure_without_retry():
    case = setup_case()
    callback = AsyncMock(side_effect=ConnectionError("storage response lost"))
    with pytest.raises(ConnectionError):
        await run(case, callback)
    callback.assert_awaited_once()
    case[3].generate_exam_drafts.assert_awaited_once()


@pytest.mark.asyncio
async def test_swallowed_quota_storage_error_does_not_become_a_partial_success():
    case = setup_case()
    plan, inputs, store, service, value = case
    store.reserve_gemini_call.side_effect = ConnectionError("private storage")

    async def swallowed(sources, blueprints, **kwargs):
        try:
            await kwargs["context"].reserve_request()
        except Exception:
            failed = value.model_copy(
                update={"candidate": None, "error_code": "GENERATION_INTERNAL"}
            )
        await kwargs["on_result"](failed)
        return BatchResult(results=[failed], status="failed")

    service.generate_exam_drafts.side_effect = swallowed
    callback = AsyncMock()
    with pytest.raises(GenerationJobError) as error:
        await run(case, callback)
    assert error.value.code == "ERR_GENERATION_STORAGE_FAILURE"
    callback.assert_not_awaited()
    store.reserve_gemini_call.assert_awaited_once_with(plan)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem", ["source", "blueprint_keys", "completed", "duplicate_cache", "seed"]
)
async def test_plan_input_mismatches_fail_before_service_or_reservation(problem):
    plan, inputs, store, service, value = setup_case()
    if problem == "source":
        inputs.sources[0].id = str(uuid4())
    elif problem == "blueprint_keys":
        inputs = inputs.model_copy(update={"blueprints": {}})
    elif problem == "completed":
        plan = replace(plan, saved=frozenset(plan.targets))
    else:
        plan = replace(plan, saved=frozenset(plan.targets))
        if problem == "seed":
            value.candidate.seed = 999
        inputs = inputs.model_copy(
            update={"completed": (value, value) if problem == "duplicate_cache" else (value,)}
        )
    with pytest.raises(ValueError):
        await run((plan, inputs, store, service, value))
    service.generate_exam_drafts.assert_not_awaited()
    store.reserve_gemini_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_input_snapshot_isolated_from_changes_while_service_is_running():
    case = setup_case()
    _, inputs, _, service, value = case
    original = deepcopy(inputs.model_dump())
    entered, release = asyncio.Event(), asyncio.Event()

    async def generate(sources, blueprints, **kwargs):
        entered.set()
        await release.wait()
        assert sources[0].options == original["sources"][0]["options"]
        assert blueprints == original["blueprints"]
        await kwargs["on_result"](value)
        return BatchResult(results=[value], status="generated")

    service.generate_exam_drafts.side_effect = generate
    task = asyncio.create_task(run(case))
    await asyncio.wait_for(entered.wait(), 1)
    inputs.sources[0].options[0] = "mutated"
    inputs.blueprints.clear()
    release.set()
    await task


@pytest.mark.asyncio
async def test_duplicate_callback_does_not_write_the_same_target_twice():
    case = setup_case()
    service, value = case[3:]

    async def generate(sources, blueprints, **kwargs):
        await kwargs["on_result"](value)
        await kwargs["on_result"](value)

    service.generate_exam_drafts.side_effect = generate
    callback = AsyncMock()
    with pytest.raises(ValueError):
        await run(case, callback)
    callback.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_cached_results_need_no_reservation_or_new_callback():
    plan, inputs, store, service, value = setup_case()
    plan = replace(plan, saved=frozenset(plan.targets), gemini_call_count=250)
    inputs = inputs.model_copy(update={"completed": (value,)})
    service.generate_exam_drafts.side_effect = None
    service.generate_exam_drafts.return_value = BatchResult(results=[value], status="generated")
    callback = AsyncMock()
    await run((plan, inputs, store, service, value), callback)
    store.reserve_gemini_call.assert_not_awaited()
    callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_is_not_converted_to_a_successful_batch():
    case = setup_case()
    entered = asyncio.Event()

    async def generate(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    case[3].generate_exam_drafts.side_effect = generate
    task = asyncio.create_task(run(case))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

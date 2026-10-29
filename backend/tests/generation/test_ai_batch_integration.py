"""Real service/gateway/validators, offline SDK transport and persistence fixtures."""

import asyncio
import json
import time
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.core.config import Settings
from app.models.generation import CandidatePayload, StepByStepSolution
from app.models.generation_events import GenerationEventData
from app.models.schemas import SourceQuestion
from app.services.ai.gateway import GeminiGateway
from app.services.blueprint.adapters import prepare_sources
from app.services.blueprint.common import ToolError, canonical
from app.services.blueprint.service import source_fingerprint
from app.services.generation.ai_batch_adapter import AIBatchAdapter, AIBatchInputs
from app.services.generation.events import GenerationEventBroker
from app.services.generation.job_contracts import (
    GenerationJobError,
    GenerationJobStore,
    GenerationPlan,
    GenerationQuotaExceeded,
    QuestionTarget,
)
from app.services.generation.service import GenerationService, candidate_identity
from app.services.observability.runtime_registry import RuntimeRegistry
from app.services.validator.pipeline import CandidateValidator


class FixtureStore:
    """No real database: verifies callback ordering, not SQL atomicity or RLS."""

    def __init__(self):
        self.count = 0
        self.rows = {}

    async def reserve_gemini_call(self, plan):
        if self.count >= 250:
            raise GenerationQuotaExceeded()
        self.count += 1
        return self.count

    async def save(self, prepared):
        if prepared.draft is not None:
            assert prepared.target not in self.rows
            self.rows[prepared.target] = prepared.raw_result.model_copy(deep=True)


@pytest_asyncio.fixture
async def ai_case(monkeypatch):
    data = json.loads((Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text())
    source = SourceQuestion.model_validate(data["source"])
    responses = deepcopy(data["candidates"])
    calls = []

    async def send(**kwargs):
        calls.append(kwargs)
        value = responses.pop(0)
        return SimpleNamespace(
            text=value if isinstance(value, str) else canonical(value),
            candidates=[SimpleNamespace(finish_reason="STOP")],
            model_version="offline-transport",
            usage_metadata=None,
        )

    sdk_send = AsyncMock(side_effect=send)
    sdk = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=sdk_send), aclose=AsyncMock()),
        close=Mock(),
    )
    monkeypatch.setattr("app.services.ai.gateway.genai.Client", lambda **kwargs: sdk)
    settings = Settings(
        _env_file=None,
        GEMINI_API_KEY=SecretStr("offline-test-key"),
        GEMINI_API_KEY_1=SecretStr(""),
        GEMINI_API_KEY_2=SecretStr(""),
        GEMINI_API_KEY_3=SecretStr(""),
    )
    gateway = GeminiGateway(settings)
    service = GenerationService(gateway, CandidateValidator(timeout=1))
    store = FixtureStore()
    plan = GenerationPlan(
        uuid4(),
        uuid4(),
        tuple(QuestionTarget(UUID(source.id), 1, v) for v in (1, 2)),
        frozenset(),
        0,
        None,
    )
    inputs = AIBatchInputs(
        sources=(source,),
        blueprints={source.id: data["blueprint"]},
        confirmed_source_hash=source_fingerprint(prepare_sources([source])),
        base_seed=100,
        variation_modes=("context",),
        completed=(),
    )
    try:
        yield SimpleNamespace(
            adapter=AIBatchAdapter(service),
            service=service,
            plan=plan,
            inputs=inputs,
            store=store,
            calls=calls,
            sdk_send=sdk_send,
            responses=responses,
            data=data,
        )
    finally:
        await gateway.aclose()


async def execute(case, *, plan=None, inputs=None, callback=None, deadline=None):
    return await case.adapter.run(
        case.plan if plan is None else plan,
        case.inputs if inputs is None else inputs,
        cast(GenerationJobStore, case.store),
        deadline=time.monotonic() + 30 if deadline is None else deadline,
        on_result=case.store.save if callback is None else callback,
    )


@pytest.mark.asyncio
async def test_two_versions_commit_before_sse_and_keep_honest_warnings(ai_case):
    case = ai_case
    events = GenerationEventBroker()
    registry = RuntimeRegistry()
    registry.start()
    frames = []

    async def watch():
        async for frame in events.stream(case.plan.session_id, registry=registry):
            frames.append(frame)

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0)

    async def commit_then_notify(prepared):
        await case.store.save(prepared)
        assert prepared.target in case.store.rows
        await events.publish(
            case.plan.session_id,
            "question_done",
            GenerationEventData(
                timestamp=datetime.now(timezone.utc),
                status="done",
                percent_complete=len(case.store.rows) * 50,
                completed_count=len(case.store.rows),
                total_count=2,
                question_no=prepared.target.question_no,
                version_index=prepared.target.version_index,
            ),
        )

    batch = await execute(case, callback=commit_then_notify)
    await events.publish(
        case.plan.session_id,
        "done",
        GenerationEventData(
            timestamp=datetime.now(timezone.utc),
            status="done",
            percent_complete=100,
            completed_count=2,
            total_count=2,
            session_status=batch.status,
        ),
    )
    await asyncio.wait_for(watcher, 1)
    assert batch.status == "generated" and case.store.count == len(case.calls) == 2
    assert len(case.store.rows) == 2
    assert len({candidate_identity(row.candidate) for row in batch.results}) == 2
    assert all(
        row.candidate.has_warning and row.validation.requires_teacher_review
        for row in batch.results
    )
    updates = [
        json.loads(frame.split("data: ", 1)[1])
        for frame in frames
        if "event: question_done" in frame
    ]
    assert [update["completed_count"] for update in updates] == [1, 2]
    assert registry.snapshot().active_sse_connections == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("first_version", [1, 2])
async def test_save_failure_preserves_acknowledged_rows_and_resume_skips_them(
    ai_case, monkeypatch, first_version
):
    case = ai_case
    saved_targets = []
    failed_results = []
    delivered_targets = []
    real_batch = case.service.generate_exam_drafts

    async def ordered_batch(*args, **kwargs):
        deliver = kwargs["on_result"]
        first_acknowledged = asyncio.Event()

        async def ordered_result(result):
            # Gate before entering the adapter's callback lock. Waiting inside
            # save would deadlock if the other version acquired that lock first.
            if result.version_index != first_version:
                await first_acknowledged.wait()
            await deliver(result)
            if result.version_index == first_version:
                first_acknowledged.set()

        kwargs["on_result"] = ordered_result
        return await real_batch(*args, **kwargs)

    async def save(prepared):
        assert prepared.draft is not None
        delivered_targets.append(prepared.target)
        if not saved_targets:
            await case.store.save(prepared)
            assert prepared.target in case.store.rows
            saved_targets.append(prepared.target)
        else:
            failed_results.append(prepared)
            raise ConnectionError("simulated persistence failure")

    with monkeypatch.context() as patch:
        patch.setattr(case.service, "generate_exam_drafts", ordered_batch)
        with pytest.raises(ExceptionGroup) as error:
            await execute(case, callback=save)
    assert len(error.value.exceptions) == 1
    failure = error.value.exceptions[0]
    assert isinstance(failure, ConnectionError)
    assert str(failure) == "simulated persistence failure"
    assert [target.version_index for target in delivered_targets] == [
        first_version,
        3 - first_version,
    ]
    assert len(saved_targets) == len(failed_results) == 1
    saved_target = saved_targets[0]
    failed = failed_results[0]
    assert set(case.store.rows) == {saved_target}
    assert failed.target not in case.store.rows
    previous = case.store.rows[saved_target].model_dump(mode="json")
    plan = replace(case.plan, saved=frozenset(case.store.rows), gemini_call_count=case.store.count)
    inputs = case.inputs.model_copy(update={"completed": tuple(case.store.rows.values())})

    # Replace any remaining fixture replies with exactly the unsaved candidate;
    # resume must not depend on the fixture queue's size or candidate ordering.
    assert len(case.calls) == case.store.count == 2
    assert failed.raw_result.candidate is not None
    payload = CandidatePayload.model_validate(
        {name: getattr(failed.raw_result.candidate, name) for name in CandidatePayload.model_fields}
    )
    case.responses[:] = [payload.model_dump(mode="json")]
    requests_before = len(case.calls)
    resumed_targets = []

    async def save_missing(prepared):
        assert prepared.target not in plan.saved
        resumed_targets.append(prepared.target)
        await case.store.save(prepared)

    batch = await execute(case, plan=plan, inputs=inputs, callback=save_missing)
    assert batch.status == "generated" and len(case.calls) == requests_before + 1
    assert case.store.count == plan.gemini_call_count + 1 == len(case.calls)
    assert resumed_targets == [failed.target]
    assert len(batch.results) == 2 and set(case.store.rows) == set(plan.targets)
    assert all(result.candidate is not None for result in batch.results)
    assert case.responses == []
    assert case.store.rows[saved_target].model_dump(mode="json") == previous


@pytest.mark.asyncio
async def test_duplicate_candidates_retry_inside_the_real_batch_service(ai_case):
    case = ai_case
    case.responses[:] = [
        deepcopy(case.data["candidates"][0]),
        deepcopy(case.data["candidates"][0]),
        deepcopy(case.data["candidates"][1]),
    ]
    batch = await execute(case)
    assert batch.status == "generated" and case.store.count == len(case.calls) == 3
    assert sorted(result.attempts for result in batch.results) == [1, 2]
    assert len({candidate_identity(row.candidate) for row in batch.results}) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["hash", "blueprint", "mode"])
async def test_real_preflight_rejects_invalid_inputs_before_quota(ai_case, problem):
    case = ai_case
    inputs = case.inputs.model_copy(deep=True)
    if problem == "hash":
        inputs = inputs.model_copy(update={"confirmed_source_hash": "not-the-confirmed-hash"})
    elif problem == "blueprint":
        blueprint = inputs.blueprints[inputs.sources[0].id]
        blueprint["requirement"]["source"]["content"][0]["text"] += " changed"
    else:
        inputs = inputs.model_copy(update={"variation_modes": ("NUMERICAL",)})
    with pytest.raises(ToolError):
        await execute(case, inputs=inputs)
    assert case.store.count == 0 and case.calls == []


@pytest.mark.asyncio
async def test_real_quota_exhaustion_returns_partial_without_fake_rows(ai_case):
    case = ai_case
    case.store.count = 249
    batch = await execute(case, plan=replace(case.plan, gemini_call_count=249))
    assert batch.status == "partial_generated" and case.store.count == 250
    assert len(case.calls) == len(case.store.rows) == 1
    failed = [result for result in batch.results if result.candidate is None]
    assert len(failed) == 1 and failed[0].error_code == "REQUEST_BUDGET_EXHAUSTED"


@pytest.mark.asyncio
async def test_stale_completed_fingerprint_is_rejected_before_another_request(ai_case):
    case = ai_case
    plan = replace(case.plan, targets=case.plan.targets[:1])
    batch = await execute(case, plan=plan)
    cached = batch.results[0].model_copy(deep=True)
    cached.request_fingerprint = "stale-result"
    inputs = case.inputs.model_copy(update={"completed": (cached,)})
    resume = replace(plan, saved=frozenset(plan.targets), gemini_call_count=case.store.count)
    calls_before = len(case.calls)
    with pytest.raises(ToolError) as error:
        await execute(case, plan=resume, inputs=inputs)
    assert error.value.code == "RESUME_MISMATCH"
    assert len(case.calls) == calls_before and len(case.store.rows) == 1


@pytest.mark.asyncio
async def test_schema_exhaustion_keeps_errors_without_inventing_drafts(ai_case):
    case = ai_case
    plan = replace(case.plan, targets=case.plan.targets[:1])
    case.responses[:] = ["not JSON"] * 4
    delivered = []

    async def receive(prepared):
        delivered.append(prepared)
        await case.store.save(prepared)

    batch = await execute(case, plan=plan, callback=receive)
    assert batch.status == "failed" and batch.results[0].candidate is None
    assert batch.results[0].error_code is not None
    assert delivered[0].draft is None and case.store.rows == {}
    assert case.store.count == len(case.calls) <= 4


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "invalid_count"])
async def test_real_service_cannot_hide_a_fatal_quota_storage_failure(ai_case, failure):
    case = ai_case
    reserve = AsyncMock(side_effect=ConnectionError("private DB"))
    if failure == "invalid_count":
        reserve = AsyncMock(return_value=0)
    case.store.reserve_gemini_call = reserve
    with pytest.raises(GenerationJobError) as error:
        await execute(case)
    assert error.value.code == "ERR_GENERATION_STORAGE_FAILURE"
    reserve.assert_awaited_once()
    assert case.calls == [] and case.store.rows == {}


@pytest.mark.asyncio
async def test_solution_consistency_checks_remain_inside_accept_retry(ai_case):
    case = ai_case
    plan = replace(case.plan, targets=case.plan.targets[:1])
    wrong = deepcopy(case.data["candidates"][0])
    wrong["correct_key"] = "B"
    repaired = deepcopy(wrong["solution"])
    repaired.update(correct_key="B", final_answer=wrong["options"][1])
    case.responses[:] = [wrong, repaired]
    batch = await execute(case, plan=plan)
    assert batch.status == "generated" and len(case.calls) == 2
    assert case.calls[1]["config"].response_json_schema == StepByStepSolution.model_json_schema()
    candidate = batch.results[0].candidate
    assert candidate.correct_key == candidate.solution.correct_key == "B"
    assert candidate.solution.final_answer == candidate.options[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["cancel", "deadline"])
async def test_transport_interruption_never_creates_completed_rows(ai_case, stop):
    case = ai_case
    entered = asyncio.Event()

    async def pending(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    case.sdk_send.side_effect = pending
    if stop == "cancel":
        task = asyncio.create_task(execute(case))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(TimeoutError):
            await execute(case, deadline=time.monotonic() + 0.05)
    assert case.store.rows == {}

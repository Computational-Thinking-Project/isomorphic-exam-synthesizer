import asyncio
import copy
import json
import multiprocessing
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.generation import CandidatePayload, StepByStepSolution, ValidationReport
from app.models.schemas import SourceQuestion
from app.services.ai.gateway import GatewayError, RequestBudget, RequestContext
from app.services.ai.structured_output import parse_model_output
from app.services.blueprint.adapters import prepare_sources, resolve_answer_key, source_to_item
from app.services.blueprint.common import ToolError, canonical
from app.services.blueprint.schema_adapter import generation_payload
from app.services.blueprint.service import BlueprintService, source_fingerprint
from app.services.generation.service import GenerationService
from app.services.observability.ai_instrumentation import make_gemini_attempt_observer
from app.services.observability.runtime_registry import RuntimeRegistry
from app.services.validator.base import CheckResult
from app.services.validator.pipeline import CandidateValidator, validate_solution
from app.services.validator.process_runner import ProcessResult, run_with_timeout


@pytest.fixture
def pipeline():
    data = json.loads((Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8"))
    source = SourceQuestion.model_validate(data["source"])
    calls = []
    responses = list(data["candidates"])

    async def generate(**kwargs):
        await kwargs["context"].reserve_request()
        calls.append(kwargs)
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value if isinstance(value, str) else canonical(value),
                               candidates=[SimpleNamespace(finish_reason="STOP")],
                               model_version="offline", usage_metadata=None)

    gateway = SimpleNamespace(model="offline", generate_content=AsyncMock(side_effect=generate))
    unknown = CheckResult(check_name="answer_verified", passed=False, status="unsupported", detail="arbitrary math")

    async def validate(candidate, **kwargs):
        return ValidationReport(checks=[*validate_solution(candidate), unknown])

    validator = SimpleNamespace(validate=AsyncMock(side_effect=validate))
    budget = RequestBudget(30)
    return SimpleNamespace(
        source=source, blueprint=data["blueprint"], candidates=data["candidates"],
        gateway=gateway, validator=validator, service=GenerationService(gateway, validator),
        responses=responses, calls=calls, budget=budget,
        context=RequestContext(time.monotonic() + 30, budget.reserve),
        confirmed=source_fingerprint(prepare_sources([source])),
    )


async def generate(p, **kwargs):
    return await p.service.generate_question(p.source, p.blueprint,
        confirmed_source_hash=p.confirmed, context=p.context, **kwargs)


@pytest.mark.asyncio
async def test_one_call_returns_question_answer_solution_with_honest_validation(pipeline):
    p = pipeline
    result = await generate(p)
    assert result.error_code is None
    assert result.candidate.requires_teacher_review and result.candidate.has_warning
    assert result.candidate.to_legacy().correct_answer == p.source.options[0]
    assert "Đáp án A" in result.candidate.solution_md
    assert p.budget.used == result.attempts == 1
    config = p.calls[0]["config"]
    assert config.response_schema is None
    assert config.response_json_schema == CandidatePayload.model_json_schema()


@pytest.mark.asyncio
async def test_guards_reject_before_spending_quota(pipeline):
    p = pipeline
    with pytest.raises(ToolError) as caught:
        await p.service.generate_question(p.source, p.blueprint, confirmed_source_hash="stale", context=p.context)
    assert caught.value.code == "SOURCE_NOT_CONFIRMED"
    bad = copy.deepcopy(p.blueprint)
    bad["requirement"]["source"]["content"][0]["text"] += " changed"
    with pytest.raises(ToolError):
        await p.service.generate_question(p.source, bad, confirmed_source_hash=p.confirmed, context=p.context)
    with pytest.raises(ToolError):
        await generate(p, variation_modes=["unallowed_dimension"])
    conflict = copy.deepcopy(p.blueprint)
    conflict["constraint"]["source_check"]["computed_answer"]["option_ids"] = [
        source_to_item(p.source)["source"]["options"][1]["id"]]
    with pytest.raises(ToolError) as caught:
        await p.service.generate_question(p.source, conflict, confirmed_source_hash=p.confirmed, context=p.context)
    assert caught.value.code == "BLUEPRINT_SOURCE_ANSWER_CONFLICT"
    assert not p.calls


@pytest.mark.asyncio
async def test_solution_only_repair_freezes_question_and_uses_same_budget(pipeline):
    p = pipeline
    broken = copy.deepcopy(p.candidates[0])
    broken["solution"]["correct_key"] = "B"
    p.responses[:] = [broken, p.candidates[0]["solution"]]
    result = await generate(p)
    assert result.candidate and result.error_code is None and p.budget.used == 2
    assert p.calls[1]["config"].response_json_schema == StepByStepSolution.model_json_schema()
    assert result.candidate.question_text == broken["question_text"]
    assert "solution_consistency" in p.calls[1]["contents"]


@pytest.mark.asyncio
async def test_bad_schema_and_known_validator_error_retry_but_unknown_does_not(pipeline):
    p = pipeline
    p.responses.insert(0, "{invalid")
    p.responses.insert(1, {**p.candidates[0], "options": ["1"]})
    result = await generate(p)
    assert result.candidate and p.budget.used == 3
    assert "AI_SCHEMA_INVALID" in p.calls[2]["contents"]


@pytest.mark.asyncio
async def test_duplicate_source_and_duplicate_across_versions_are_retried(pipeline):
    p = pipeline
    original = {**p.candidates[0], "question_text": p.source.question_text}
    p.responses[:] = [{"variants": [{"version_index": 1, "candidate": original}, {"version_index": 2, "candidate": p.candidates[0]}]}, p.candidates[0], p.candidates[1]]
    result = await p.service.generate_exam_drafts([p.source], {p.source.id: p.blueprint},
        confirmed_source_hash=p.confirmed, n_versions=2, context=p.context)
    assert result.status == "generated" and p.budget.used == 3
    assert len({r.candidate.question_text for r in result.results}) == 2


@pytest.mark.asyncio
async def test_quota_failure_returns_partial_and_resume_only_calls_missing_slots(pipeline):
    p = pipeline
    p.budget.limit = 1
    p.responses[:] = [{"variants": [{"version_index": 1, "candidate": p.candidates[0]}, {"version_index": 2, "candidate": p.candidates[0]}]}, p.candidates[1]]
    first = await p.service.generate_exam_drafts([p.source], {p.source.id: p.blueprint},
        confirmed_source_hash=p.confirmed, n_versions=2, context=p.context)
    assert first.status == "partial_generated"
    completed = [r for r in first.results if r.candidate]
    assert len(completed) == 1
    p.budget.limit = 10
    save = AsyncMock()
    resumed = await p.service.generate_exam_drafts([p.source], {p.source.id: p.blueprint},
        confirmed_source_hash=p.confirmed, n_versions=2, context=p.context,
        completed=completed, on_result=save)
    assert resumed.status == "generated" and p.budget.used == 2
    assert save.await_count == 1
    assert completed[0].candidate.variant_id in {r.candidate.variant_id for r in resumed.results}
    with pytest.raises(ToolError):
        await p.service.generate_exam_drafts([p.source], {p.source.id: p.blueprint},
            confirmed_source_hash=p.confirmed, n_versions=2, context=p.context,
            completed=completed, base_seed=999)


@pytest.mark.asyncio
async def test_regenerate_keeps_blueprint_and_old_candidate_and_has_no_teacher_prompt(pipeline):
    p = pipeline
    previous = (await generate(p)).candidate
    snapshot = previous.model_dump()
    p.responses.insert(0, p.candidates[0])
    result = await p.service.regenerate_question(p.source, p.blueprint, previous,
        confirmed_source_hash=p.confirmed, context=p.context)
    assert result.candidate and result.candidate.question_text != previous.question_text
    assert result.candidate.blueprint_fingerprint == previous.blueprint_fingerprint
    assert result.candidate.seed != previous.seed
    assert previous.model_dump() == snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", [False, True])
async def test_regeneration_rejects_other_version_even_with_shuffled_options(pipeline, exhausted):
    p = pipeline
    previous = (await generate(p)).candidate
    peer = (await generate(p)).candidate
    snapshot = peer.model_dump()
    duplicate = copy.deepcopy(p.candidates[1])
    duplicate["options"] = duplicate["options"][1:] + duplicate["options"][:1]
    duplicate["correct_key"] = duplicate["solution"]["correct_key"] = "D"
    p.responses[:] = [duplicate] * 4 if exhausted else [duplicate, p.candidates[2]]
    result = await p.service.regenerate_question(p.source, p.blueprint, previous,
        confirmed_source_hash=p.confirmed, context=p.context, current_candidates=[peer])
    assert peer.model_dump() == snapshot
    if exhausted:
        assert result.candidate is None and result.error_code == "DUPLICATE_CANDIDATE"
        assert result.attempts == 4
    else:
        assert result.candidate.question_text == p.candidates[2]["question_text"]
        assert result.attempts == 2
        assert "duplicate_candidate" in p.calls[-1]["contents"]


@pytest.mark.asyncio
async def test_regeneration_rejects_foreign_peer_before_calling_api(pipeline):
    p = pipeline
    previous = (await generate(p)).candidate
    peer = previous.model_copy(update={"source_question_id": "foreign"})
    with pytest.raises(ToolError) as caught:
        await p.service.regenerate_question(p.source, p.blueprint, previous,
            confirmed_source_hash=p.confirmed, context=p.context, current_candidates=[peer])
    assert caught.value.code == "PREVIOUS_VARIANT_MISMATCH"
    assert p.budget.used == 1


@pytest.mark.asyncio
async def test_deadline_and_nonretryable_error_are_bounded(pipeline):
    p = pipeline
    p.responses[:] = [GatewayError("REQUEST_BUDGET_EXHAUSTED", retryable=False)]
    result = await generate(p)
    assert result.candidate is None and result.attempts == 1
    assert result.error_code == "REQUEST_BUDGET_EXHAUSTED"

    async def blocked(**kwargs):
        await asyncio.sleep(10)
    p.gateway.generate_content.side_effect = blocked
    p.context = RequestContext(time.monotonic() + 0.02, p.budget.reserve)
    result = await generate(p)
    assert result.error_code == "JOB_DEADLINE" and result.candidate is None


@pytest.mark.asyncio
async def test_persistence_failure_is_propagated_not_reported_as_success(pipeline):
    p = pipeline
    with pytest.raises(RuntimeError, match="database unavailable"):
        await p.service.generate_exam_drafts([p.source], {p.source.id: p.blueprint},
            confirmed_source_hash=p.confirmed, n_versions=1, context=p.context,
            on_result=AsyncMock(side_effect=RuntimeError("database unavailable")))


@pytest.mark.asyncio
async def test_blueprint_extract_resume_skips_api_and_rejects_stale_cache(pipeline):
    p = pipeline
    p.responses[:] = [generation_payload(p.blueprint)]
    service = BlueprintService(p.gateway)
    results, stats = await service.extract_sources([p.source], confirmed_source_hash=p.confirmed, context=p.context)
    assert results[0]["error"] is None and stats[0]["requests"] == 1
    ready = {p.source.id: results[0]}
    cached, stats = await service.extract_sources([p.source], confirmed_source_hash=p.confirmed, context=p.context, ready=ready)
    assert cached == results and stats[0]["requests"] == 0 and p.budget.used == 1
    ready[p.source.id]["input_fingerprint"] = "stale"
    with pytest.raises(ToolError):
        await service.extract_sources([p.source], confirmed_source_hash=p.confirmed, context=p.context, ready=ready)


@pytest.mark.asyncio
async def test_blueprint_callback_persists_each_result_and_failure_propagates(pipeline):
    p = pipeline
    p.responses[:] = [generation_payload(p.blueprint)]
    save = AsyncMock()
    await BlueprintService(p.gateway).extract_sources([p.source], confirmed_source_hash=p.confirmed,
        context=p.context, on_result=save)
    saved, metadata = save.await_args.args
    assert saved["source_question_id"] == p.source.id and saved["input_fingerprint"]
    assert metadata["requests"] == 1
    p.responses[:] = [generation_payload(p.blueprint)]
    with pytest.raises(ExceptionGroup):
        await BlueprintService(p.gateway).extract_sources([p.source], confirmed_source_hash=p.confirmed,
            context=p.context, on_result=AsyncMock(side_effect=RuntimeError("DB failed")))


@pytest.mark.asyncio
async def test_repeated_invalid_output_stops_and_cancellation_propagates(pipeline):
    p = pipeline
    p.responses[:] = ["broken"] * 8
    result = await generate(p)
    assert result.candidate is None and result.attempts == p.budget.used == 3
    p.gateway.generate_content.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await generate(p)


@pytest.mark.asyncio
async def test_known_failures_stop_after_four_total_attempts(pipeline):
    p = pipeline
    p.validator.validate.side_effect = None
    p.validator.validate.return_value = ValidationReport(checks=[
        CheckResult(check_name="answer_verified", passed=False, status="failed", detail="wrong answer")])
    result = await generate(p)
    assert result.candidate is None and result.error_code == "VALIDATION_FAILED"
    assert result.attempts == p.budget.used == 4


@pytest.mark.parametrize("wrong_reasoning", [
    "Hai cạnh bằng nhau nên mọi tam giác đều vuông.",
    "Xác suất bằng tổng số trường hợp chia số trường hợp thuận lợi.",
    "Hàm liên tục luôn có đạo hàm.",
    "Bình phương hai vế luôn giữ nguyên tập nghiệm.",
    "Thể tích hình chóp bằng diện tích đáy nhân chiều cao.",
])
def test_right_key_never_certifies_wrong_freeform_reasoning(pipeline, wrong_reasoning):
    candidate = CandidatePayload.model_validate(pipeline.candidates[0])
    candidate.solution.steps[0].explanation = wrong_reasoning
    checks = {check.check_name: check for check in validate_solution(candidate)}
    assert checks["solution_consistency"].passed  # Internal agreement only.
    assert not checks["solution_reasoning"].passed and checks["solution_reasoning"].status == "unknown"


@pytest.mark.parametrize("solution_key,final_answer,valid", [
    ("B", "2 và 5", True),
    ("A", "2 và 5", False),
    ("B", "B", False),
    ("B", "3 và 4", False),
])
def test_string_option_is_matched_by_key_and_content(pipeline, solution_key, final_answer, valid):
    candidate = CandidatePayload.model_validate({
        **pipeline.candidates[0], "options": ["3 và 4", "2 và 5", "-2 và -5", "1 và 10"],
        "correct_key": "B", "solution": {"correct_key": solution_key, "final_answer": final_answer,
        "steps": [{"explanation": "Phân tích đa thức thành nhân tử."}]},
    })
    consistency = next(c for c in validate_solution(candidate) if c.check_name == "solution_consistency")
    assert consistency.passed is valid


@pytest.mark.asyncio
async def test_all_blueprints_are_checked_before_any_generation(pipeline):
    p = pipeline
    second = p.source.model_copy(update={"id": "second"})
    with pytest.raises(ToolError):
        await p.service.generate_exam_drafts([p.source, second],
            {p.source.id: p.blueprint, second.id: p.blueprint},
            confirmed_source_hash=source_fingerprint(prepare_sources([p.source, second])),
            n_versions=2, context=p.context)
    assert not p.calls


@pytest.mark.asyncio
async def test_expired_blueprint_job_returns_error_without_api(pipeline):
    p = pipeline
    context = RequestContext(time.monotonic() - 1, p.budget.reserve)
    results, _ = await BlueprintService(p.gateway).extract_sources([p.source],
        confirmed_source_hash=p.confirmed, context=context)
    assert results[0]["blueprint"] is None and results[0]["error"]["code"] == "JOB_DEADLINE"
    assert not p.calls


@pytest.mark.asyncio
async def test_runtime_is_lazy_and_services_share_one_gateway(monkeypatch):
    from app.core.config import Settings
    from app.services.ai import runtime

    gateway = SimpleNamespace(model="offline", aclose=AsyncMock())
    factory = Mock(return_value=gateway)
    monkeypatch.setattr(runtime, "GeminiGateway", factory)
    observer = Mock()
    settings = Settings(_env_file=None)
    services = runtime.AIRuntime(settings, attempt_observer=observer)
    await services.aclose()
    factory.assert_not_called()
    assert services.blueprints.gateway is services.generation.gateway is gateway
    assert services.generation is services.generation
    factory.assert_called_once_with(settings, attempt_observer=observer)
    await services.aclose()
    gateway.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("accept_candidate", [True, False])
async def test_real_gateway_shares_reservations_across_extraction_and_generation(
    pipeline, monkeypatch, accept_candidate
):
    from app.core.config import Settings
    from app.services.ai import gateway as transport

    p = pipeline

    def response(payload):
        return SimpleNamespace(
            text=canonical(payload),
            candidates=[SimpleNamespace(finish_reason="STOP")],
            model_version="offline",
            usage_metadata=None,
        )

    sdk = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(
                generate_content=AsyncMock(
                    side_effect=[
                        response(generation_payload(p.blueprint)),
                        response(p.candidates[0]),
                    ]
                )
            ),
            aclose=AsyncMock(),
        ),
        close=Mock(),
    )
    monkeypatch.setattr(transport.genai, "Client", lambda **kwargs: sdk)
    config = Settings(
        _env_file=None,
        GEMINI_API_KEY="offline-key",
        GEMINI_API_KEY_1="",
        GEMINI_API_KEY_2="",
        GEMINI_API_KEY_3="",
    )
    if not accept_candidate:
        p.validator.validate.side_effect = None
        p.validator.validate.return_value = ValidationReport(
            checks=[CheckResult(check_name="domain", passed=False, status="failed")]
        )
    registry = RuntimeRegistry()
    registry.start()
    budget = RequestBudget(2)
    context = RequestContext(time.monotonic() + 30, budget.reserve)
    async with transport.GeminiGateway(
        config, attempt_observer=make_gemini_attempt_observer(registry)
    ) as gateway:
        blueprints, _ = await BlueprintService(gateway).extract_sources(
            [p.source], confirmed_source_hash=p.confirmed, context=context
        )
        service = GenerationService(gateway, p.validator)
        result = await service.generate_question(
            p.source, blueprints[0]["blueprint"], confirmed_source_hash=p.confirmed, context=context
        )
        assert (result.candidate is not None) is accept_candidate
        if not accept_candidate:
            assert result.validation.failures[0].check_name == "domain"
        blocked = await service.generate_question(
            p.source, blueprints[0]["blueprint"], confirmed_source_hash=p.confirmed, context=context
        )
        assert blocked.error_code == "REQUEST_BUDGET_EXHAUSTED"
    snapshot = registry.snapshot()
    assert snapshot.gemini_call_count == 2
    assert sdk.aio.models.generate_content.await_count == budget.used == 2
    assert snapshot.gemini_error_rate == 0
    sdk.aio.aclose.assert_awaited_once()
    sdk.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("stem", [
    "Cho tam giác ABC có các cạnh 3, 4, 5. Tính diện tích.",
    "Tính xác suất rút hai viên bi đỏ khi chọn không hoàn lại.",
    "Cho hàm số liên tục trên đoạn [0,1]. Khẳng định nào đúng?",
    "Tìm tham số để phương trình có hai nghiệm phân biệt.",
    "Tính thể tích hình chóp theo hình vẽ.",
])
async def test_unsupported_topics_never_report_math_verified(pipeline, stem):
    candidate = CandidatePayload.model_validate({**pipeline.candidates[0], "question_text": stem})
    report = await CandidateValidator(timeout=5).validate(candidate, deadline=time.monotonic() + 15)
    math = next(c for c in report.checks if c.check_name == "answer_verified")
    assert not math.passed and math.status == "unsupported"
    assert report.has_warning and report.requires_teacher_review


@pytest.mark.parametrize("text", ['{"correct_key":"A","correct_key":"B"}', '{"x":NaN}'])
def test_strict_output_rejects_ambiguous_json(text):
    with pytest.raises(ToolError):
        parse_model_output(text, CandidatePayload)


def test_adapter_preserves_content_handles_numeric_uuid_and_rejects_ambiguous_answer(pipeline):
    p = pipeline
    item = source_to_item(p.source)
    assert item["source"]["question_id"].startswith("q_")
    assert item["source"]["content"][0]["text"] == p.source.question_text
    assert resolve_answer_key("$1856$", p.source.options) == "A"
    with pytest.raises(ToolError):
        resolve_answer_key("A", ["0", "A", "2", "3"])


@pytest.mark.asyncio
async def test_real_validator_keeps_arbitrary_problem_unknown_and_detects_false_equation(pipeline):
    validator = CandidateValidator(timeout=5)
    candidate = CandidatePayload.model_validate(pipeline.candidates[0])
    report = await validator.validate(candidate, deadline=time.monotonic() + 15)
    assert not report.failures
    assert report.has_warning and report.requires_teacher_review
    assert next(c for c in report.checks if c.check_name == "answer_verified").status == "unsupported"
    equation = candidate.model_copy(update={"question_text": "Giải phương trình $x+1=3$.",
        "options": ["9", "2", "3", "4"],
        "solution": StepByStepSolution(correct_key="A", final_answer="9", steps=[{"explanation": "Sai có chủ ý để kiểm thử."}])})
    report = await validator.validate(equation, deadline=time.monotonic() + 15)
    assert any(c.check_name == "answer_verified" for c in report.failures)


@pytest.mark.asyncio
async def test_candidate_validator_passes_frozen_blueprint_to_four_tiers(pipeline, monkeypatch):
    from app.services.validator.base import ValidationReport as AggregateReport

    candidate = CandidatePayload.model_validate(pipeline.candidates[0])
    blueprint = {"requirement": {"parameter_domains": {"x": [1, 5]}}}
    received = []

    def fake_validate(question_text, options, correct_answer, **kwargs):
        received.append((question_text, options, correct_answer, kwargs))
        return AggregateReport(
            passed=False, status="failed", confidence="rule_only",
            checks=[CheckResult(check_name="parameter_bounds", passed=False, status="failed")],
        )

    monkeypatch.setattr("app.services.validator.pipeline.validate_question", fake_validate)
    def run_in_test_process(target, *, args=(), **kwargs):
        return ProcessResult(success=True, data=target(*args))

    monkeypatch.setattr("app.services.validator.pipeline.run_with_timeout", run_in_test_process)
    report = await CandidateValidator().validate(
        candidate, deadline=time.monotonic() + 5, blueprint=blueprint
    )
    assert received[0][3]["blueprint"] == blueprint
    assert received[0][3]["parameters"] is None
    assert any(check.check_name == "parameter_bounds" for check in report.failures)
    assert any(check.check_name == "parameter_coverage" for check in report.checks)


@pytest.mark.asyncio
async def test_f02_deadline_keeps_real_slots_until_worker_cleanup(pipeline, monkeypatch):
    candidate = CandidatePayload.model_validate(pipeline.candidates[0])
    lock = threading.Lock()
    three_started = threading.Event()
    active = 0
    maximum = 0

    def blocked_worker(target, *, cancel_signal, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == 3:
                three_started.set()
        try:
            assert cancel_signal.wait(timeout=2)
            time.sleep(0.2)  # OS cleanup still owns the slot after caller timeout.
            return ProcessResult(success=False, error="cancelled")
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr("app.services.validator.pipeline.run_with_timeout", blocked_worker)
    validator = CandidateValidator(timeout=1)
    timed_out = [
        asyncio.create_task(
            validator.validate(candidate, deadline=time.monotonic() + 0.3)
        )
        for _ in range(3)
    ]
    assert await asyncio.to_thread(three_started.wait, 2)
    fourth = asyncio.create_task(
        validator.validate(candidate, deadline=time.monotonic() + 1)
    )
    results = await asyncio.gather(*timed_out, return_exceptions=True)
    assert all(isinstance(result, TimeoutError) for result in results)
    assert maximum <= 3
    fourth.cancel()
    with pytest.raises(asyncio.CancelledError):
        await fourth
    assert active == 0
    assert await validator.aclose(timeout_seconds=1)


@pytest.mark.asyncio
async def test_f02_external_cancel_reclaims_worker_before_slot_reuse(pipeline, monkeypatch):
    candidate = CandidatePayload.model_validate(pipeline.candidates[0])
    started = threading.Event()
    stopped = threading.Event()

    def blocked_worker(target, *, cancel_signal, **kwargs):
        started.set()
        assert cancel_signal.wait(timeout=2)
        time.sleep(0.05)
        stopped.set()
        return ProcessResult(success=False, error="cancelled")

    monkeypatch.setattr("app.services.validator.pipeline.run_with_timeout", blocked_worker)
    validator = CandidateValidator(timeout=5)
    task = asyncio.create_task(validator.validate(candidate, deadline=time.monotonic() + 5))
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    assert await validator.aclose(timeout_seconds=1)


def _f02_block_forever():
    while True:
        time.sleep(0.05)


@pytest.mark.asyncio
async def test_f02_real_processes_never_exceed_three(pipeline, monkeypatch):
    candidate = CandidatePayload.model_validate(pipeline.candidates[0])
    before = {child.pid for child in multiprocessing.active_children()}

    def run_blocker(target, *, cancel_signal, **kwargs):
        return run_with_timeout(
            _f02_block_forever,
            timeout=15,
            start_method="spawn",
            cancel_signal=cancel_signal,
        )

    monkeypatch.setattr("app.services.validator.pipeline.run_with_timeout", run_blocker)
    validator = CandidateValidator(timeout=15)
    deadline = time.monotonic() + 15
    first = [
        asyncio.create_task(validator.validate(candidate, deadline=deadline))
        for _ in range(3)
    ]
    fourth = None
    maximum = 0
    try:
        for _ in range(500):
            active = {child.pid for child in multiprocessing.active_children()} - before
            maximum = max(maximum, len(active))
            if len(active) == 3:
                break
            await asyncio.sleep(0.01)
        assert maximum == 3
        fourth = asyncio.create_task(validator.validate(candidate, deadline=deadline))
        await asyncio.sleep(0.05)
        for task in first:
            task.cancel()
        for _ in range(100):
            active = {child.pid for child in multiprocessing.active_children()} - before
            maximum = max(maximum, len(active))
            if all(task.done() for task in first):
                break
            await asyncio.sleep(0.01)
        assert maximum <= 3
    finally:
        for task in [*first, fourth]:
            if task is not None:
                task.cancel()
        await asyncio.gather(*(task for task in [*first, fourth] if task is not None),
                             return_exceptions=True)
        assert await validator.aclose(timeout_seconds=2)
    assert not {child.pid for child in multiprocessing.active_children()} - before

@pytest.mark.asyncio
async def test_four_versions_share_one_request_and_persist_in_order(pipeline):
    p = pipeline
    variants = []
    for version in range(1, 5):
        candidate = {**p.candidates[0], "question_text": f"Biến thể {version}"}
        variants.append({"version_index": version, "candidate": candidate})
    p.responses[:] = [{"variants": list(reversed(variants))}]
    saved = []
    async def persist(result):
        saved.append(result.version_index)
    result = await p.service.generate_exam_drafts(
        [p.source], {p.source.id: p.blueprint}, confirmed_source_hash=p.confirmed,
        n_versions=4, context=p.context, on_result=persist,
    )
    assert result.status == "generated"
    assert p.budget.used == len(p.calls) == 1
    assert saved == [1, 2, 3, 4]
    assert [r.version_index for r in result.results] == saved

@pytest.mark.asyncio
async def test_sources_are_generated_question_first_before_next_source(pipeline):
    p = pipeline
    other = p.source.model_copy(update={"id": "q2"})
    blueprint = copy.deepcopy(p.blueprint)
    old_id = source_to_item(p.source)["source"]["question_id"]
    new_id = source_to_item(other)["source"]["question_id"]
    blueprint = json.loads(json.dumps(blueprint).replace(old_id, new_id))
    payload = {"variants": [
        {"version_index": version, "candidate": {
            **p.candidates[0], "question_text": f"Câu {version}",
        }} for version in (1, 2)
    ]}
    p.responses[:] = [payload, payload]
    saved = []
    async def persist(result):
        saved.append((result.source_question_id, result.version_index))
    result = await p.service.generate_exam_drafts(
        [p.source, other], {p.source.id: p.blueprint, other.id: blueprint},
        confirmed_source_hash=source_fingerprint(prepare_sources([p.source, other])),
        n_versions=2, context=p.context, on_result=persist,
    )
    assert result.status == "generated"
    assert p.budget.used == 2
    assert saved == [(p.source.id, 1), (p.source.id, 2), ("q2", 1), ("q2", 2)]


@pytest.mark.asyncio
async def test_repeated_wrong_batch_version_ids_stop_at_schema_limit_without_candidates(pipeline):
    p = pipeline
    p.responses[:] = [{"variants": [
        {"version_index": 1, "candidate": p.candidates[0]},
        {"version_index": 1, "candidate": p.candidates[1]},
    ]}] * 3
    result = await p.service.generate_exam_drafts(
        [p.source], {p.source.id: p.blueprint}, confirmed_source_hash=p.confirmed,
        n_versions=2, context=p.context,
    )
    assert result.status == "failed"
    assert all(r.candidate is None for r in result.results)
    assert p.budget.used == 3
    assert all(r.attempts == 3 and not r.exhausted_attempts for r in result.results)
    p.validator.validate.assert_not_awaited()


def four_version_payload(p):
    return {"variants": [
        {"version_index": version, "candidate": {
            **copy.deepcopy(p.candidates[0]), "question_text": f"Biến thể mới {version}",
        }} for version in range(1, 5)
    ]}


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["json", "solution", "duplicate_version", "missing_version"])
async def test_invalid_four_version_batch_recovers_before_any_candidate_is_saved(pipeline, invalid):
    p = pipeline
    bad = four_version_payload(p)
    code = "GENERATION_INVALID"
    if invalid == "json":
        bad = "{invalid"
        code = "INVALID_JSON"
    elif invalid == "solution":
        del bad["variants"][2]["candidate"]["solution"]
        code = "AI_SCHEMA_INVALID"
    elif invalid == "duplicate_version":
        bad["variants"][2]["version_index"] = 1
    else:
        bad["variants"].pop()
    valid = four_version_payload(p)
    valid["variants"].reverse()
    p.responses[:] = [bad, valid]
    saved = []
    async def persist(result):
        assert len(p.calls) == 2 and result.candidate is not None
        saved.append(result.version_index)
    result = await p.service.generate_exam_drafts(
        [p.source], {p.source.id: p.blueprint}, confirmed_source_hash=p.confirmed,
        n_versions=4, context=p.context, on_result=persist,
    )
    assert result.status == "generated" and p.budget.used == 2
    assert saved == [1, 2, 3, 4]
    assert all(r.attempts == 2 for r in result.results)
    assert p.validator.validate.await_count == 4
    assert code in p.calls[1]["contents"] and "output_schema" in p.calls[1]["contents"]


@pytest.mark.asyncio
async def test_repeated_malformed_batch_stops_after_three_schema_failures(pipeline):
    p = pipeline
    p.responses[:] = ["{invalid"] * 3 + [four_version_payload(p)]
    result = await generate_batch(p)
    assert result.status == "failed" and p.budget.used == len(p.calls) == 3
    assert len(p.responses) == 1
    assert all(r.candidate is None and r.error_code == "INVALID_JSON"
               and r.attempts == 3 and not r.exhausted_attempts for r in result.results)
    p.validator.validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_schema_and_transport_failures_share_four_attempts(pipeline, monkeypatch):
    p = pipeline
    monkeypatch.setattr("app.services.generation.service.asyncio.sleep", AsyncMock())
    p.responses[:] = ["{invalid", GatewayError("API_TIMEOUT", retryable=True), "{invalid", "{invalid"]
    result = await generate_batch(p)
    assert result.status == "failed" and p.budget.used == len(p.calls) == 4
    assert all(r.attempts == 4 and r.exhausted_attempts and r.candidate is None for r in result.results)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["quota", "deadline"])
async def test_schema_recovery_respects_shared_budget_and_deadline(pipeline, stop):
    p = pipeline
    p.responses[:] = ["{invalid", batch_payload(p)]
    if stop == "quota":
        p.budget.limit = 1
    else:
        p.context = RequestContext(time.monotonic() + 0.02, p.budget.reserve)
        original = p.gateway.generate_content.side_effect
        async def stalled(**kwargs):
            if p.calls:
                await asyncio.sleep(1)
            return await original(**kwargs)
        p.gateway.generate_content.side_effect = stalled
    result = await generate_batch(p)
    code = "REQUEST_BUDGET_EXHAUSTED" if stop == "quota" else "JOB_DEADLINE"
    assert result.status == "failed" and p.budget.used == 1
    assert all(r.error_code == code and not r.exhausted_attempts for r in result.results)
    p.validator.validate.assert_not_awaited()


def batch_payload(p):
    return {"variants": [
        {"version_index": version, "candidate": p.candidates[version - 1]}
        for version in (1, 2)
    ]}


async def generate_batch(p, **kwargs):
    return await p.service.generate_exam_drafts(
        [p.source], {p.source.id: p.blueprint}, confirmed_source_hash=p.confirmed,
        n_versions=2, context=p.context, **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["API_TIMEOUT", "API_RATE_LIMIT", "API_TRANSPORT"])
async def test_transient_batch_error_retries_shared_request_before_validation(pipeline, monkeypatch, code):
    p = pipeline
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.generation.service.asyncio.sleep", sleep)
    p.responses[:] = [GatewayError(code, retryable=True), batch_payload(p)]
    saved = AsyncMock()
    result = await generate_batch(p, on_result=saved)
    assert result.status == "generated" and p.budget.used == len(p.calls) == 2
    assert [r.attempts for r in result.results] == [2, 2]
    assert saved.await_count == p.validator.validate.await_count == 2
    sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_batch_retries_count_toward_each_slots_four_attempt_limit(pipeline, monkeypatch):
    p = pipeline
    monkeypatch.setattr("app.services.generation.service.asyncio.sleep", AsyncMock())
    payload = batch_payload(p)
    payload["variants"][0]["candidate"] = {
        **p.candidates[0], "question_text": p.source.question_text,
    }
    p.responses[:] = [GatewayError("API_TIMEOUT", retryable=True)] * 3 + [payload]
    result = await generate_batch(p)
    first, second = result.results
    assert result.status == "partial_generated" and p.budget.used == len(p.calls) == 4
    assert first.attempts == second.attempts == 4
    assert first.error_code == "DUPLICATE_CANDIDATE" and first._exhausted_attempts
    assert second.candidate is not None


@pytest.mark.asyncio
async def test_four_retryable_batch_failures_mark_all_slots_exhausted(pipeline, monkeypatch):
    p = pipeline
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.generation.service.asyncio.sleep", sleep)
    p.responses[:] = [GatewayError("API_RATE_LIMIT", retryable=True)] * 4
    result = await generate_batch(p)
    assert result.status == "failed" and p.budget.used == len(p.calls) == 4
    assert all(r.attempts == 4 and r._exhausted_attempts for r in result.results)
    assert all(r.error_code == "API_RATE_LIMIT" for r in result.results)
    assert [call.args[0] for call in sleep.await_args_list] == [1, 2, 4]
    p.validator.validate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["quota", "deadline", "auth", "cancel"])
async def test_batch_retry_stops_without_fallback_on_quota_deadline_auth_or_cancel(pipeline, monkeypatch, stop):
    p = pipeline
    if stop == "deadline":
        p.context = RequestContext(time.monotonic() + 0.02, p.budget.reserve)
    else:
        monkeypatch.setattr("app.services.generation.service.asyncio.sleep", AsyncMock())
    p.responses[:] = [GatewayError("API_TIMEOUT", retryable=True), batch_payload(p)]
    if stop == "quota":
        p.budget.limit = 1
    elif stop == "auth":
        p.responses[:] = [GatewayError("API_AUTH")]
    elif stop == "cancel":
        p.gateway.generate_content.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await generate_batch(p)
        return
    result = await generate_batch(p)
    code = {"quota": "REQUEST_BUDGET_EXHAUSTED", "deadline": "JOB_DEADLINE", "auth": "API_AUTH"}[stop]
    assert result.status == "failed" and len(p.calls) == 1
    assert all(r.error_code == code and not r._exhausted_attempts for r in result.results)

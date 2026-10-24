import asyncio
import copy
import json
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
from app.services.validator.base import CheckResult
from app.services.validator.pipeline import CandidateValidator, validate_solution


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
    p.responses[:] = [original, p.candidates[0], p.candidates[0], p.candidates[1]]
    result = await p.service.generate_exam_drafts([p.source], {p.source.id: p.blueprint},
        confirmed_source_hash=p.confirmed, n_versions=2, context=p.context)
    assert result.status == "generated" and p.budget.used == 4
    assert len({r.candidate.question_text for r in result.results}) == 2


@pytest.mark.asyncio
async def test_quota_failure_returns_partial_and_resume_only_calls_missing_slots(pipeline):
    p = pipeline
    p.budget.limit = 1
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
    with pytest.raises(ExceptionGroup):
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
    factory = AsyncMock()  # Startup must not touch SDK/network.
    monkeypatch.setattr(runtime, "GeminiGateway", factory)
    services = runtime.AIRuntime(Settings(_env_file=None))
    await services.aclose()
    factory.assert_not_called()
    monkeypatch.setattr(runtime, "GeminiGateway", lambda settings: gateway)
    assert services.blueprints.gateway is services.generation.gateway is gateway
    assert services.generation is services.generation
    await services.aclose()
    gateway.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_gateway_shares_reservations_across_extraction_and_generation(pipeline, monkeypatch):
    from app.core.config import Settings
    from app.services.ai import gateway as transport

    p = pipeline

    def response(payload):
        return SimpleNamespace(text=canonical(payload), candidates=[SimpleNamespace(finish_reason="STOP")],
                               model_version="offline", usage_metadata=None)

    sdk = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(
        side_effect=[response(generation_payload(p.blueprint)), response(p.candidates[0])])),
        aclose=AsyncMock()), close=Mock())
    monkeypatch.setattr(transport.genai, "Client", lambda **kwargs: sdk)
    config = Settings(_env_file=None, GEMINI_API_KEY="offline-key", GEMINI_API_KEY_1="",
                      GEMINI_API_KEY_2="", GEMINI_API_KEY_3="")
    budget = RequestBudget(2)
    context = RequestContext(time.monotonic() + 30, budget.reserve)
    async with transport.GeminiGateway(config) as gateway:
        blueprints, _ = await BlueprintService(gateway).extract_sources([p.source],
            confirmed_source_hash=p.confirmed, context=context)
        service = GenerationService(gateway, p.validator)
        result = await service.generate_question(p.source, blueprints[0]["blueprint"],
            confirmed_source_hash=p.confirmed, context=context)
        assert result.candidate and budget.used == 2
        blocked = await service.generate_question(p.source, blueprints[0]["blueprint"],
            confirmed_source_hash=p.confirmed, context=context)
        assert blocked.error_code == "REQUEST_BUDGET_EXHAUSTED"
    assert sdk.aio.models.generate_content.await_count == 2
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

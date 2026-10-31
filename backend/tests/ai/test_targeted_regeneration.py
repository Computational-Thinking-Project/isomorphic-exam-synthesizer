import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.generation import ValidationReport
from app.models.schemas import SourceQuestion
from app.models.targeted import RegeneratedVariantResult
from app.services.blueprint.adapters import prepare_sources
from app.services.blueprint.common import canonical
from app.services.blueprint.service import source_fingerprint
from app.services.generation.service import GenerationService
from app.services.generation.targeted_service import (
    TargetedGenerationError,
    TargetedRegenerator,
    mock_regenerate_question_variant,
)
from app.services.validator.base import CheckResult
from app.services.validator.pipeline import validate_solution


@pytest.fixture
def handoff():
    data = json.loads((Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8"))
    source = SourceQuestion.model_validate(data["source"])
    responses = [data["candidates"][1]]

    async def generate(**kwargs):
        await kwargs["context"].reserve_request()
        value = responses.pop(0)
        return SimpleNamespace(text=value if isinstance(value, str) else canonical(value),
                               candidates=[SimpleNamespace(finish_reason="STOP")],
                               model_version="offline", usage_metadata=None)

    async def validate(candidate, **kwargs):
        return ValidationReport(checks=[*validate_solution(candidate), CheckResult(
            check_name="answer_verified", passed=False, status="unsupported", detail="Teacher review required",
        )])

    gateway = SimpleNamespace(model="offline", generate_content=AsyncMock(side_effect=generate))
    validator = SimpleNamespace(validate=AsyncMock(side_effect=validate))
    question_id = str(uuid4())
    args = dict(
        session_id=str(uuid4()), question_id=question_id,
        source_snapshot={**source.model_dump(), "content_hash": source_fingerprint(prepare_sources([source]))},
        blueprint=data["blueprint"], current_variant={
            "id": question_id, "source_question_id": source.id,
            "content": data["candidates"][0]["question_text"], "options": data["candidates"][0]["options"],
        }, peer_variants=[],
    )
    return SimpleNamespace(args=args, responses=responses, data=data, gateway=gateway, validator=validator,
                           adapter=TargetedRegenerator(GenerationService(gateway, validator)))


@pytest.mark.asyncio
async def test_review_payload_matches_key_and_keeps_unknown_honest(handoff):
    h = handoff
    before = copy.deepcopy(h.args)
    result = await h.adapter(**h.args)
    assert result["content"] == result["stem_latex"] == h.data["candidates"][1]["question_text"]
    assert result["api_calls_count"] == 1
    assert result["correct_key"] == h.data["candidates"][1]["correct_key"]
    assert result["validation_report"]["is_valid"]
    assert not result["validation_report"]["math_verified"]
    assert result["validation_report"]["requires_teacher_review"]
    assert result["validation_report"]["warnings"]
    assert h.args == before


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["hash", "blueprint", "source_id", "question_id"])
async def test_invalid_snapshots_fail_before_quota(handoff, mutation):
    h = handoff
    if mutation == "hash":
        h.args["source_snapshot"].pop("content_hash")
    elif mutation == "blueprint":
        h.args["blueprint"] = {"variables": {"a": 3}}
    elif mutation == "source_id":
        h.args["current_variant"]["source_question_id"] = "other"
    else:
        h.args["current_variant"]["id"] = str(uuid4())
    with pytest.raises(TargetedGenerationError) as exc:
        await h.adapter(**h.args)
    assert exc.value.api_calls_count == 0
    assert h.gateway.generate_content.await_count == 0


@pytest.mark.asyncio
async def test_peer_and_rejected_question_are_excluded_including_display_labels(handoff):
    h = handoff
    candidate = h.data["candidates"][1]
    h.args["peer_variants"] = [{"source_question_id": h.args["source_snapshot"]["id"],
                               "content": candidate["question_text"],
                               "options": [f"{k}. {v}" for k, v in zip("ABCD", candidate["options"], strict=True)]}]
    h.responses[:] = [h.data["candidates"][0], candidate, candidate, candidate]
    with pytest.raises(TargetedGenerationError) as exc:
        await h.adapter(**h.args)
    assert exc.value.code == "DUPLICATE_CANDIDATE"
    assert exc.value.api_calls_count == 4


@pytest.mark.asyncio
async def test_reserved_budget_cannot_be_exceeded_and_failure_keeps_count(handoff):
    h = handoff
    h.responses[:] = ["broken json"] * 4
    h.adapter.max_api_calls = 2
    with pytest.raises(TargetedGenerationError) as exc:
        await h.adapter(**h.args)
    assert exc.value.api_calls_count == 2
    # The transport stub calls reserve before dispatch, as GeminiGateway does.
    assert len(h.responses) == 2


@pytest.mark.asyncio
async def test_two_math_retries_within_total_attempt_cap(handoff):
    h = handoff
    h.responses[:] = [h.data["candidates"][1]] * 4
    h.validator.validate = AsyncMock(return_value=ValidationReport(checks=[CheckResult(
        check_name="answer_verified", passed=False, status="failed", detail="Wrong answer",
    )]))
    with pytest.raises(TargetedGenerationError) as exc:
        await h.adapter(**h.args)
    assert exc.value.code == "MATH_RETRIES_EXHAUSTED"
    assert exc.value.api_calls_count == 3


@pytest.mark.asyncio
async def test_explicit_mock_never_claims_calls_or_math_verification(handoff):
    result = await mock_regenerate_question_variant(**handoff.args)
    assert result["api_calls_count"] == 0
    assert not result["validation_report"]["math_verified"]
    assert "MOCK" in result["content"]
    result.pop("content")
    RegeneratedVariantResult.model_validate(result)


def test_result_schema_rejects_bad_key_or_duplicate_options():
    from pydantic import ValidationError

    fields = dict(stem_latex="Question", options=["1", "2", "3", "4"], correct_key="E",
                  solution_md="Solution", validation_report={"is_valid": True}, api_calls_count=1)
    with pytest.raises(ValidationError):
        RegeneratedVariantResult(**fields)
    fields.update(correct_key="A", options=["1", " 1 ", "3", "4"])
    with pytest.raises(ValidationError):
        RegeneratedVariantResult(**fields)

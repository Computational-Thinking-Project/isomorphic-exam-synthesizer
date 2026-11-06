"""Executable handoff for W2 consumers; no network, SQL or mathematical proof."""

import hashlib
import json
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.generation import QuestionResult, render_solution
from app.models.schemas import SourceQuestion
from app.services.ai.gateway import RequestBudget, RequestContext
from app.services.blueprint.adapters import prepare_sources
from app.services.blueprint.common import ToolError, canonical
from app.services.blueprint.service import source_fingerprint
from app.services.generation.service import GenerationService, fingerprint

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def handoff():
    contract = json.loads((FIXTURES / "w2_ai_contract.json").read_text(encoding="utf-8"))
    reference = json.loads((FIXTURES / contract["reference_fixture"]).read_text(encoding="utf-8"))
    source = SourceQuestion.model_validate(reference["source"])
    gateway = SimpleNamespace(model=contract["model"], generate_content=AsyncMock())
    service = GenerationService(gateway)
    budget = RequestBudget(10)
    return SimpleNamespace(
        contract=contract, reference=reference, source=source, gateway=gateway,
        service=service, budget=budget,
        kwargs=dict(
            confirmed_source_hash=source_fingerprint(prepare_sources([source])),
            n_versions=1, base_seed=contract["base_seed"],
            variation_modes=contract["variation_modes"],
            context=RequestContext(time.monotonic() + 30, budget.reserve),
        ),
    )


def test_ordered_batch_hash_is_not_a_per_question_hash(handoff):
    values = handoff.contract["source_hashes"]
    sources = [SourceQuestion.model_validate(value) for value in values["ordered_sources"]]
    items = prepare_sources(sources)
    wire = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert source_fingerprint(items) == hashlib.sha256(wire.encode("utf-8")).hexdigest()
    assert source_fingerprint(items) == values["ordered_batch_hash"]
    assert source_fingerprint(list(reversed(items))) == values["reversed_batch_hash"]
    assert values["ordered_batch_hash"] != values["reversed_batch_hash"]
    for source, item in zip(sources, items, strict=True):
        assert source_fingerprint([item]) == values["per_question_hashes"][source.id]
        assert source_fingerprint([item]) != values["ordered_batch_hash"]


@pytest.mark.parametrize("case", ["success", "warning_timeout", "hard_failure", "provider_failure"])
def test_full_result_fixture_preserves_answer_and_validation_evidence(handoff, case):
    raw = handoff.contract["cases"][case]["result"]
    saved = QuestionResult.model_validate_json(canonical(raw))
    assert saved.model_dump(mode="json") == raw
    assert handoff.contract["blueprint_fingerprint"] == fingerprint(handoff.reference["blueprint"])
    assert saved.request_fingerprint == handoff.service._request_fingerprint(
        prepare_sources([handoff.source])[0], handoff.reference["blueprint"], 1100, ["context"]
    )
    if saved.candidate:
        candidate = saved.candidate
        assert candidate.seed == 1100
        assert candidate.blueprint_fingerprint == handoff.contract["blueprint_fingerprint"]
        assert candidate.solution.correct_key == candidate.correct_key
        assert candidate.solution.final_answer == candidate.options["ABCD".index(candidate.correct_key)]
        assert candidate.solution_md == render_solution(candidate.solution)
        assert saved.validation and not saved.validation.failures
        assert candidate.has_warning and candidate.requires_teacher_review
    else:
        assert saved.error_code
        if saved.validation is not None:
            assert saved.validation.failures


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["success", "warning_timeout"])
async def test_completed_resume_keeps_full_record_without_dispatch(handoff, case):
    saved = QuestionResult.model_validate(handoff.contract["cases"][case]["result"])
    callback = AsyncMock()
    batch = await handoff.service.generate_exam_drafts(
        [handoff.source], {handoff.source.id: handoff.reference["blueprint"]},
        completed=[saved], on_result=callback, **handoff.kwargs,
    )
    assert batch.status == "generated"
    assert batch.results[0].model_dump() == saved.model_dump()
    handoff.gateway.generate_content.assert_not_called()
    callback.assert_not_called()
    assert handoff.budget.used == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "seed", "candidate_seed", "model", "prompt", "modes", "blueprint", "source", "source_hash",
    "hard_failure", "provider_failure", "missing_validation", "duplicate_slot",
])
async def test_incompatible_completed_results_fail_before_dispatch(handoff, monkeypatch, change):
    source = handoff.source.model_copy(deep=True)
    blueprint = deepcopy(handoff.reference["blueprint"])
    completed = [QuestionResult.model_validate(handoff.contract["cases"]["success"]["result"])]
    expected = "RESUME_MISMATCH"
    if change == "seed":
        handoff.kwargs["base_seed"] += 1
    elif change == "candidate_seed":
        completed[0].candidate.seed += 1
    elif change == "model":
        handoff.gateway.model = "different-model"
    elif change == "prompt":
        monkeypatch.setattr("app.services.generation.service.PROMPT_VERSION", "different-prompt")
    elif change == "modes":
        handoff.kwargs["variation_modes"] = ["values"]
    elif change == "blueprint":
        blueprint["requirement"]["variation_policy"]["allowed_transformations"][0]["description"] += " Updated."
    elif change == "source":
        source.question_text += " Edited."
        expected = "SOURCE_NOT_CONFIRMED"
    elif change == "source_hash":
        handoff.kwargs["confirmed_source_hash"] = "0" * 64
        expected = "SOURCE_NOT_CONFIRMED"
    elif change in ("hard_failure", "provider_failure"):
        completed = [QuestionResult.model_validate(handoff.contract["cases"][change]["result"])]
    elif change == "missing_validation":
        completed[0].validation = None
    elif change == "duplicate_slot":
        completed.append(completed[0].model_copy(deep=True))
    with pytest.raises(ToolError) as error:
        await handoff.service.generate_exam_drafts(
            [source], {source.id: blueprint}, completed=completed, **handoff.kwargs,
        )
    assert error.value.code == expected
    handoff.gateway.generate_content.assert_not_called()
    assert handoff.budget.used == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("public_id", ["NUMERICAL", "parameter_variation", "STRUCTURAL", "NONE"])
async def test_unmapped_public_modes_are_not_silently_treated_as_empty(handoff, public_id):
    handoff.kwargs["variation_modes"] = [public_id]
    with pytest.raises(ToolError) as error:
        await handoff.service.generate_exam_drafts(
            [handoff.source], {handoff.source.id: handoff.reference["blueprint"]}, **handoff.kwargs,
        )
    assert error.value.code == "ERR_CONFIG_CONFLICT"
    handoff.gateway.generate_content.assert_not_called()

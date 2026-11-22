"""Per-question policy uses the full source order, never a global intersection."""

import json
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.generation import QuestionResult
from app.models.schemas import SourceQuestion
from app.services.ai.gateway import RequestBudget, RequestContext
from app.services.blueprint.adapters import prepare_sources, source_to_item
from app.services.blueprint.common import ToolError
from app.services.blueprint.service import source_fingerprint
from app.services.generation.mode_mapper import question_policy
from app.services.generation.service import GenerationService


def fixture_sources():
    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8")
    )
    original = SourceQuestion.model_validate(data["source"])
    sources, blueprints = [], {}
    dimensions = [("values",), ("context",), ("values", "context"), ("wording",)]
    for allowed in dimensions:
        source = original.model_copy(update={"id": str(uuid4())})
        blueprint = json.loads(
            json.dumps(data["blueprint"]).replace(
                source_to_item(original)["source"]["question_id"],
                source_to_item(source)["source"]["question_id"],
            )
        )
        template = blueprint["requirement"]["variation_policy"]["allowed_transformations"][0]
        blueprint["requirement"]["variation_policy"]["allowed_transformations"] = [
            dict(deepcopy(template), dimension=dimension, id=f"change-{dimension}")
            for dimension in allowed
        ]
        sources.append(source)
        blueprints[source.id] = blueprint
    return sources, blueprints


@pytest.mark.asyncio
async def test_service_dispatches_only_each_questions_dimensions_and_keeps_seed_indices(
    monkeypatch,
):
    sources, blueprints = fixture_sources()
    service = GenerationService(SimpleNamespace(model="fixture"))
    calls = []

    async def generate(source, item, blueprint, context, seed, version, modes, **kwargs):
        calls.append((source.id, seed, version, tuple(modes)))
        return QuestionResult(
            source_question_id=source.id,
            version_index=version,
            request_fingerprint=service._request_fingerprint(item, blueprint, seed, modes),
            error_code="PROVIDER_FAILED",
            attempts=1,
        )

    monkeypatch.setattr(service, "_generate", generate)
    modes = {
        key: tuple(question_policy(value)["canonical_dimensions"])
        for key, value in blueprints.items()
    }
    context = RequestContext(time.monotonic() + 30, RequestBudget(10).reserve)
    batch = await service.generate_exam_drafts(
        sources,
        blueprints,
        confirmed_source_hash=source_fingerprint(prepare_sources(sources)),
        n_versions=2,
        context=context,
        variation_modes=["values", "context"],
        source_variation_modes=modes,
        clone_source_ids=frozenset({sources[3].id}),
    )
    assert set(calls) == {
        (source.id, 100 + version * 1000 + index, version, modes[source.id])
        for version in (1, 2)
        for index, source in enumerate(sources[:3])
    }
    assert batch.status == "partial_generated"  # two clones, six failed AI slots
    assert len(batch.results) == 6
    calls.clear()
    bad_modes = dict(modes, **{sources[0].id: ("context",)})
    with pytest.raises(ToolError, match="Chính sách"):
        await service.generate_exam_drafts(
            sources,
            blueprints,
            confirmed_source_hash=source_fingerprint(prepare_sources(sources)),
            n_versions=2,
            context=context,
            source_variation_modes=bad_modes,
            clone_source_ids=frozenset({sources[3].id}),
        )
    assert not calls


@pytest.mark.parametrize("transforms", [[], None, [{}], [{"dimension": "values"}]])
def test_malformed_policy_is_not_clone(transforms):
    _, blueprints = fixture_sources()
    blueprint = next(iter(blueprints.values()))
    blueprint["requirement"]["variation_policy"]["allowed_transformations"] = transforms
    with pytest.raises(ValueError, match="Malformed"):
        question_policy(blueprint)


@pytest.mark.asyncio
async def test_adapter_rejects_ai_callback_for_clone_before_persistence():
    from unittest.mock import AsyncMock

    from tests.generation.test_ai_batch_adapter import run, setup_case

    plan, inputs, store, service, result = setup_case()
    blueprint = deepcopy(inputs.blueprints[result.source_question_id])
    for transform in blueprint["requirement"]["variation_policy"]["allowed_transformations"]:
        transform["dimension"] = "wording"
    inputs = inputs.model_copy(
        update={
            "blueprints": {result.source_question_id: blueprint},
            "source_variation_modes": {result.source_question_id: ()},
            "clone_source_ids": frozenset({result.source_question_id}),
        }
    )
    callback = AsyncMock()
    with pytest.raises(ValueError, match="new AI target"):
        await run((plan, inputs, store, service, result), callback=callback)
    callback.assert_not_awaited()

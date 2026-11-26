"""EXT-02: generation_mode contract on models, config repository, claim reader and API."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.generation_config import GenerationConfigRequest, GenerationConfigResponse
from app.services.generation.config_repository import GenerationConfigRepository
from app.services.generation.config_service import GenerationConfigError
from app.services.generation.mode_mapper import frozen_generation_mode, mode_question_policy
from tests.api.test_generation_config import ApiHarness, payload
from tests.api.test_generation_config import api as api  # noqa: F401
from tests.generation.test_config_repository import (
    SESSION_ID,
    canonical_snapshot,
    make_db,
    make_rows,
    saved_receipt,
)

ROOT = Path(__file__).resolve().parents[3]
BLUEPRINT = json.loads(
    (ROOT / "backend/tests/fixtures/ai_pipeline.json").read_text(encoding="utf-8-sig")
)["blueprint"]


def test_request_defaults_to_ai_generation_and_accepts_shuffle_only() -> None:
    assert GenerationConfigRequest(n_versions=2).generation_mode == "ai_generation"
    request = GenerationConfigRequest.model_validate({"n_versions": 2, "generation_mode": "shuffle_only"})
    assert request.generation_mode == "shuffle_only"
    # An empty variation list never means shuffle_only.
    assert GenerationConfigRequest(n_versions=2, active_variation_modes=[]).generation_mode == "ai_generation"


@pytest.mark.parametrize("mode", ["bogus", "NONE", "", None, 1, "SHUFFLE_ONLY"])
def test_request_rejects_unknown_mode(mode: object) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate({"n_versions": 2, "generation_mode": mode})


def test_response_accepts_mapping_1_2_and_rejects_unknown_mode() -> None:
    receipt = saved_receipt({"sources": []}, [])
    receipt["config"].update(mapping_version="1.2", generation_mode="shuffle_only")
    assert GenerationConfigResponse.model_validate(receipt).config.generation_mode == "shuffle_only"
    receipt["config"]["generation_mode"] = "bogus"
    with pytest.raises(ValidationError):
        GenerationConfigResponse.model_validate(receipt)


def test_repository_sends_mode_and_accepts_matching_receipt() -> None:
    db, _ = make_db(make_rows())
    manifest = canonical_snapshot()["manifest"]
    receipt = saved_receipt(manifest, [])
    receipt["config"].update(mapping_version="1.2", generation_mode="shuffle_only")
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=receipt)
    config = GenerationConfigRequest(n_versions=2, generation_mode="shuffle_only")
    result = GenerationConfigRepository(db).save_config(SESSION_ID, config, manifest)
    assert result.config.generation_mode == "shuffle_only"
    assert db.rpc.call_args.args[1]["p_generation_mode"] == "shuffle_only"


@pytest.mark.parametrize(
    ("requested", "returned", "modes"),
    [
        ("shuffle_only", "ai_generation", []),
        ("ai_generation", "shuffle_only", []),
        # A shuffle_only receipt can never carry AI dimensions.
        ("shuffle_only", "shuffle_only", ["NUMERICAL", "parameter_variation"]),
    ],
)
def test_repository_rejects_receipt_with_other_mode(requested: str, returned: str, modes: list[str]) -> None:
    db, _ = make_db(make_rows())
    manifest = canonical_snapshot()["manifest"]
    receipt = saved_receipt(manifest, modes)
    receipt["config"].update(mapping_version="1.2", generation_mode=returned)
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=receipt)
    with pytest.raises(GenerationConfigError) as exc_info:
        GenerationConfigRepository(db).save_config(
            SESSION_ID, GenerationConfigRequest(n_versions=2, generation_mode=requested), manifest
        )
    assert exc_info.value.status_code == 500


def test_shuffle_only_policy_ignores_ai_capable_blueprint() -> None:
    assert mode_question_policy("ai_generation", deepcopy(BLUEPRINT))["result_kind"] == "AI_RESULT"
    assert mode_question_policy("shuffle_only", deepcopy(BLUEPRINT)) == {
        "canonical_dimensions": [],
        "result_kind": "ORIGINAL_CLONE",
    }


@pytest.mark.parametrize("mode", ["ai_generation", "shuffle_only"])
def test_malformed_blueprint_is_rejected_in_both_modes(mode: str) -> None:
    blueprint = deepcopy(BLUEPRINT)
    blueprint["requirement"]["variation_policy"]["allowed_transformations"] = []
    with pytest.raises(ValueError):
        mode_question_policy(mode, blueprint)


def test_unknown_mode_policy_is_rejected() -> None:
    with pytest.raises(ValueError):
        mode_question_policy("bogus", deepcopy(BLUEPRINT))


@pytest.mark.parametrize(
    ("config", "context", "expected"),
    [
        ({}, {"mapping_version": "1.0"}, "ai_generation"),
        ({"generation_mode": "ai_generation"}, {"mapping_version": "1.1"}, "ai_generation"),
        (
            {"generation_mode": "shuffle_only"},
            {"mapping_version": "1.2", "generation_mode": "shuffle_only"},
            "shuffle_only",
        ),
        (
            {"generation_mode": "ai_generation"},
            {"mapping_version": "1.2", "generation_mode": "ai_generation"},
            "ai_generation",
        ),
    ],
)
def test_frozen_mode_reads_snapshot(config: dict, context: dict, expected: str) -> None:
    assert frozen_generation_mode(config, context) == expected


@pytest.mark.parametrize(
    ("config", "context"),
    [
        ({"generation_mode": "shuffle_only"}, {"mapping_version": "1.1"}),
        ({}, {"mapping_version": "1.1", "generation_mode": "ai_generation"}),
        ({"generation_mode": "shuffle_only"}, {"mapping_version": "1.2"}),
        ({}, {"mapping_version": "1.2", "generation_mode": "shuffle_only"}),
        ({"generation_mode": "ai_generation"}, {"mapping_version": "1.2", "generation_mode": "shuffle_only"}),
        ({"generation_mode": "bogus"}, {"mapping_version": "1.2", "generation_mode": "bogus"}),
        ({"generation_mode": "ai_generation"}, {"mapping_version": "1.3", "generation_mode": "ai_generation"}),
    ],
)
def test_frozen_mode_fails_closed(config: dict, context: dict) -> None:
    with pytest.raises(ValueError):
        frozen_generation_mode(config, context)


def test_api_passes_shuffle_only_to_store(api: ApiHarness) -> None:
    response = api.post(payload(generation_mode="shuffle_only"))
    assert response.status_code == 200
    assert response.json()["config"]["generation_mode"] == "shuffle_only"
    assert api.store.save_calls[0][1].generation_mode == "shuffle_only"


def test_api_old_payload_without_mode_is_ai_generation(api: ApiHarness) -> None:
    response = api.post(payload())
    assert response.status_code == 200
    assert api.store.save_calls[0][1].generation_mode == "ai_generation"


def test_api_rejects_unknown_mode_before_storage(api: ApiHarness) -> None:
    response = api.post(payload(generation_mode="bogus"))
    assert response.status_code == 422
    assert api.store.save_calls == []

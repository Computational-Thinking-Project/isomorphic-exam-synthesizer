"""EXT-02: generation_mode contract on models, config repository, claim reader and API."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from postgrest.exceptions import APIError
from pydantic import ValidationError

from app.models.generation_config import GenerationConfigRequest, GenerationConfigResponse
from app.services.generation.config_repository import GenerationConfigRepository
from app.services.generation.config_service import GenerationConfigError
from app.services.generation.mode_mapper import (
    GenerationModeConflict,
    frozen_generation_mode,
    job_generation_mode,
    mode_question_policy,
    slot_result_kind,
)
from tests.api.test_generation_config import HEADERS as API_HEADERS
from tests.api.test_generation_config import OTHER_SESSION_ID as API_OTHER_SESSION_ID
from tests.api.test_generation_config import SESSION_ID as API_SESSION_ID
from tests.api.test_generation_config import ApiHarness, payload
from tests.api.test_generation_config import api as api  # noqa: F401
from tests.generation.test_config_repository import (
    SESSION_ID,
    canonical_snapshot,
    make_db,
    make_rows,
    saved_receipt,
)

# Relative to backend/tests so it also resolves inside the backend container (/backend).
BLUEPRINT = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8-sig")
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


def test_repository_omits_default_mode_for_pre_028_databases() -> None:
    db, _ = make_db(make_rows())
    manifest = canonical_snapshot()["manifest"]
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=saved_receipt(manifest, []))
    GenerationConfigRepository(db).save_config(SESSION_ID, GenerationConfigRequest(n_versions=2), manifest)
    assert "p_generation_mode" not in db.rpc.call_args.args[1]


SID_AI = "00000000-0000-4000-8000-000000000101"
SID_CLONE = "00000000-0000-4000-8000-000000000102"
AI_POLICY = {"canonical_dimensions": ["values"], "result_kind": "AI_RESULT"}
CLONE_POLICY = {"canonical_dimensions": [], "result_kind": "ORIGINAL_CLONE"}


def snapshot_row(version: str, mode: str | None = None, policies: dict | None = None, **extra) -> dict:
    payload: dict = {
        "question_policies": policies or {},
        "confirmed_sources": [{"source_question_id": SID_AI}, {"source_question_id": SID_CLONE}],
    }
    if mode is not None:
        payload["generation_mode"] = mode
    return {
        "mapping_version": version,
        "generation_mode": mode,
        "public_modes": ["NUMERICAL", "parameter_variation"],
        "canonical_dimensions": ["values"],
        "snapshot_payload": payload,
        **extra,
    }


@pytest.mark.parametrize(("public_modes", "dimensions", "expected"), [
    ([], [], "ORIGINAL_CLONE"),
    (["NUMERICAL", "parameter_variation"], ["values"], "AI_RESULT"),
    ([], ["values"], "AI_RESULT"),
])
def test_reader_legacy_1_0_uses_session_rule(public_modes: list, dimensions: list, expected: str) -> None:
    row = snapshot_row("1.0", public_modes=public_modes, canonical_dimensions=dimensions)
    row["snapshot_payload"] = {}
    assert job_generation_mode(row) == "ai_generation"
    assert slot_result_kind(row, SID_AI) == expected


def test_reader_1_1_uses_frozen_per_slot_policy() -> None:
    row = snapshot_row("1.1", policies={SID_AI: AI_POLICY, SID_CLONE: CLONE_POLICY})
    assert job_generation_mode(row) == "ai_generation"
    assert slot_result_kind(row, SID_AI) == "AI_RESULT"
    assert slot_result_kind(row, UUID(SID_CLONE)) == "ORIGINAL_CLONE"


@pytest.mark.parametrize("mode", ["ai_generation", "shuffle_only"])
def test_reader_1_2_reads_mode_and_slots(mode: str) -> None:
    policies = {SID_AI: AI_POLICY, SID_CLONE: CLONE_POLICY} if mode == "ai_generation" else {
        SID_AI: CLONE_POLICY, SID_CLONE: CLONE_POLICY}
    row = snapshot_row("1.2", mode, policies)
    assert job_generation_mode(row) == mode
    expected = "AI_RESULT" if mode == "ai_generation" else "ORIGINAL_CLONE"
    assert slot_result_kind(row, SID_AI) == expected
    assert slot_result_kind(row, SID_CLONE) == "ORIGINAL_CLONE"


@pytest.mark.parametrize("row", [
    snapshot_row("1.2", "shuffle_only", {SID_AI: AI_POLICY}),  # shuffle_only can never be AI
    snapshot_row("1.1", policies={}),  # missing slot
    snapshot_row("1.1", policies={SID_AI: {"result_kind": "CONFIRMED_SOURCE_FALLBACK"}}),
    snapshot_row("1.1", policies={SID_AI: "AI_RESULT"}),
    snapshot_row("1.3", "ai_generation", {SID_AI: AI_POLICY}),  # unknown version
    snapshot_row("1.2", None, {SID_AI: AI_POLICY}),  # null mode
    {**snapshot_row("1.2", "ai_generation", {SID_AI: AI_POLICY}), "generation_mode": "shuffle_only"},
    {**snapshot_row("1.2", "ai_generation", {SID_AI: AI_POLICY}), "snapshot_payload": None},
])
def test_reader_fails_closed(row: dict) -> None:
    with pytest.raises(GenerationModeConflict):
        slot_result_kind(row, SID_AI)


def test_reader_mode_mismatch_between_column_and_payload() -> None:
    row = snapshot_row("1.2", "shuffle_only", {SID_AI: CLONE_POLICY})
    row["snapshot_payload"]["generation_mode"] = "ai_generation"
    with pytest.raises(GenerationModeConflict):
        job_generation_mode(row)
    assert issubclass(GenerationModeConflict, ValueError)


@pytest.mark.parametrize("mode", ["ai_generation", "shuffle_only"])
@pytest.mark.parametrize("sources", [
    [{"source_question_id": SID_CLONE}],  # policy entry whose source is absent
    [{"source_question_id": SID_AI}, {"source_question_id": SID_AI}],  # duplicate source
    [],
    None,
])
def test_reader_requires_exactly_one_frozen_source(mode: str, sources: list | None) -> None:
    policy = AI_POLICY if mode == "ai_generation" else CLONE_POLICY
    row = snapshot_row("1.2", mode, {SID_AI: policy, SID_CLONE: CLONE_POLICY})
    row["snapshot_payload"]["confirmed_sources"] = sources
    with pytest.raises(GenerationModeConflict):
        slot_result_kind(row, SID_AI)


def confirm(api: ApiHarness, session_id: object = API_SESSION_ID):
    return api.client.post(f"/api/sessions/{session_id}/shuffle-only/confirm", headers=API_HEADERS)


def test_confirm_api_returns_reviewed_receipt(api: ApiHarness) -> None:
    receipt = {"success": True, "session_id": str(API_SESSION_ID), "session_status": "reviewed",
               "generation_mode": "shuffle_only", "confirmed_slots": 4, "replayed": False,
               "progress": {"ready": True}}
    api.db.rpc.return_value.execute.return_value = SimpleNamespace(data=receipt)
    response = confirm(api)
    assert response.status_code == 200 and response.json() == receipt
    api.db.rpc.assert_called_once_with("confirm_shuffle_only_copies", {"p_session_id": str(API_SESSION_ID)})


@pytest.mark.parametrize(("code", "message", "status", "error"), [
    ("55006", "ERR_MODE_NOT_SHUFFLE_ONLY", 409, "ERR_MODE_NOT_SHUFFLE_ONLY"),
    ("55000", "ERR_SHUFFLE_ONLY_NOT_READY: copies do not match", 409, "ERR_SHUFFLE_ONLY_NOT_READY"),
    ("55000", "REVIEW_BUSY", 409, "REVIEW_BUSY"),
    ("55000", "REVIEW_LOCKED", 423, "REVIEW_LOCKED"),
    ("XX000", "boom", 500, "ERR_CONFIG_STORAGE_FAILURE"),
])
def test_confirm_api_maps_database_errors(api: ApiHarness, code: str, message: str, status: int, error: str) -> None:
    api.db.rpc.return_value.execute.side_effect = APIError({"code": code, "message": message})
    response = confirm(api)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == error


@pytest.mark.parametrize("data", [None, {}, {"success": True, "session_id": "other", "session_status": "reviewed"},
                                  {"success": True, "session_status": "generated"}])
def test_confirm_api_rejects_malformed_receipt(api: ApiHarness, data: object) -> None:
    api.db.rpc.return_value.execute.return_value = SimpleNamespace(data=data)
    assert confirm(api).status_code == 500


def test_confirm_api_checks_ownership_before_rpc(api: ApiHarness) -> None:
    response = confirm(api, API_OTHER_SESSION_ID)
    assert response.status_code in {403, 404}
    api.db.rpc.assert_not_called()

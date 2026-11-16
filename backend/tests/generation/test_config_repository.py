from collections.abc import Mapping
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from postgrest.exceptions import APIError

from app.models.generation_config import GenerationConfigRequest, GenerationConfigResponse
from app.services.generation.config_repository import GenerationConfigRepository
from app.services.generation.config_service import (
    GenerationConfigError,
    validate_generation_config,
)

SESSION_ID = UUID(int=1)
QUESTION_1 = UUID(int=2)
QUESTION_2 = UUID(int=3)


def make_rows() -> dict[str, list[dict[str, object]]]:
    return {
        "exam_sessions": [{"id": str(SESSION_ID), "status": "blueprinted", "approved_at": None}],
        "source_questions": [],
        "question_blueprints": [],
    }


def make_db(rows: Mapping[str, object]) -> tuple[MagicMock, dict[str, MagicMock]]:
    db = MagicMock()
    queries: dict[str, MagicMock] = {}
    for table, data in rows.items():
        query = MagicMock()
        for method in ["select", "eq", "order", "in_", "limit"]:
            getattr(query, method).return_value = query
        query.execute.return_value = SimpleNamespace(data=data)
        queries[table] = query
    db.table.side_effect = queries.__getitem__
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"session_id": str(SESSION_ID), "ready": False, "reason": "NO_CONFIRMATION", "confirmed_sources": []}
    )
    return db, queries


def assert_no_writes(db: MagicMock, queries: dict[str, MagicMock]) -> None:
    assert all(args.args[0] != "save_generation_config" for args in db.rpc.call_args_list)
    for query in queries.values():
        for method in ["insert", "update", "delete", "upsert"]:
            getattr(query, method).assert_not_called()


def assert_storage_failure(db: MagicMock) -> None:
    with pytest.raises(GenerationConfigError) as exc_info:
        GenerationConfigRepository(db).load_context(SESSION_ID)
    assert exc_info.value.status_code == 500
    assert exc_info.value.to_detail() == {
        "code": "ERR_CONFIG_STORAGE_FAILURE",
        "message": "Generation configuration could not be processed.",
    }


def test_not_found_or_rls_hidden_session_stops_before_snapshot() -> None:
    db, queries = make_db({**make_rows(), "exam_sessions": []})
    assert GenerationConfigRepository(db).load_context(SESSION_ID) is None
    db.table.assert_called_once_with("exam_sessions")
    db.rpc.assert_not_called()
    assert_no_writes(db, queries)


@pytest.mark.parametrize(
    "rows",
    [
        None,
        {},
        ["unexpected"],
        [{"id": "invalid-uuid", "status": "blueprinted", "approved_at": None}],
        [{"id": str(QUESTION_1), "status": "blueprinted", "approved_at": None}],
        [{"id": str(SESSION_ID), "status": None, "approved_at": None}],
        [{"id": str(SESSION_ID), "status": "blueprinted"}],
        make_rows()["exam_sessions"] * 2,
    ],
)
def test_invalid_session_data_fails_before_snapshot(rows: object) -> None:
    db, queries = make_db({**make_rows(), "exam_sessions": rows})
    assert_storage_failure(db)
    db.rpc.assert_not_called()
    assert_no_writes(db, queries)


@pytest.mark.parametrize("status", ["blueprinted", "configured", "draft"])
def test_repository_retains_session_state_for_preflight(status: str) -> None:
    rows = make_rows()
    rows["exam_sessions"][0]["status"] = status
    db, _ = make_db(rows)
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None and context.status == status
    db.table.assert_called_once_with("exam_sessions")


def canonical_snapshot() -> dict[str, object]:
    source_id = str(QUESTION_1)
    revision_id = str(UUID(int=20))
    blueprint_revision_id = str(UUID(int=21))
    confirmation_id = str(UUID(int=22))
    source = {
        "source_question_id": source_id,
        "question_no": 1,
        "source_revision_id": revision_id,
        "blueprint_revision_id": blueprint_revision_id,
        "source_fingerprint": "a" * 64,
        "blueprint_fingerprint": "b" * 64,
        "confirmed_input": {"question_text": "1 + 1 = ?"},
        "canonical_blueprint": {
            "requirement": {
                "variation_policy": {
                    "allowed_transformations": [
                        {
                            "id": "replace_values",
                            "dimension": "values",
                            "description": "Replace numerical values",
                            "target_refs": [],
                            "preconditions": [],
                            "limits": [],
                        }
                    ]
                }
            }
        },
    }
    return {
        "session_id": str(SESSION_ID),
        "ready": True,
        "reason": None,
        "confirmation_id": confirmation_id,
        "confirmed_sources": [source],
        "source_order": [source_id],
        "confirmed_source_hash": "c" * 64,
        "manifest": {
            "confirmation_id": confirmation_id,
            "sources": [{key: source[key] for key in (
                "source_question_id", "question_no", "source_revision_id", "blueprint_revision_id"
            )}],
        },
    }


def test_canonical_snapshot_never_reads_legacy_blueprints() -> None:
    rows = make_rows()
    rows["question_blueprints"] = []
    db, queries = make_db(rows)
    snapshot = canonical_snapshot()
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=snapshot)

    context = GenerationConfigRepository(db).load_context(SESSION_ID)

    assert context is not None and context.snapshot_ready
    assert context.expected_snapshot == snapshot["manifest"]
    assert context.canonical_blueprints[0].source_question_id == QUESTION_1
    queries["source_questions"].execute.assert_not_called()
    queries["question_blueprints"].execute.assert_not_called()
    config = GenerationConfigRequest(n_versions=1)
    assert validate_generation_config(config, context).active_variation_modes == []
    db.rpc.assert_called_once_with(
        "get_generation_source_snapshot", {"p_session_id": str(SESSION_ID)}
    )
    db.table.assert_called_once_with("exam_sessions")
    queries["exam_sessions"].eq.assert_called_once_with("id", str(SESSION_ID))
    assert_no_writes(db, queries)


@pytest.mark.parametrize(
    "reason", ["NO_CONFIRMATION", "ARTIFACT_STALE", "CANONICAL_BLUEPRINTS_INCOMPLETE"]
)
def test_canonical_not_ready_does_not_fall_back_to_legacy(reason: str) -> None:
    db, queries = make_db(make_rows())
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"session_id": str(SESSION_ID), "ready": False, "reason": reason}
    )
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None and context.snapshot_reason == reason
    queries["source_questions"].execute.assert_not_called()
    queries["question_blueprints"].execute.assert_not_called()
    with pytest.raises(GenerationConfigError, match="requires 1"):
        validate_generation_config(GenerationConfigRequest(n_versions=1, active_variation_modes=[]), context)


def test_snapshot_rpc_failure_never_falls_back_to_legacy() -> None:
    db, queries = make_db(make_rows())
    db.rpc.return_value.execute.side_effect = RuntimeError("private transport failure")
    assert_storage_failure(db)
    db.rpc.assert_called_once()
    queries["source_questions"].execute.assert_not_called()
    queries["question_blueprints"].execute.assert_not_called()


@pytest.mark.parametrize("damage", ["missing_manifest", "wrong_revision", "missing_blueprint", "wrong_order"])
def test_malformed_canonical_snapshot_fails_closed(damage: str) -> None:
    db, queries = make_db(make_rows())
    snapshot = canonical_snapshot()
    if damage == "missing_manifest":
        del snapshot["manifest"]
    elif damage == "wrong_revision":
        snapshot["manifest"]["sources"][0]["source_revision_id"] = str(UUID(int=99))
    elif damage == "missing_blueprint":
        del snapshot["confirmed_sources"][0]["canonical_blueprint"]
    else:
        snapshot["source_order"] = [str(QUESTION_2)]
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=snapshot)
    assert_storage_failure(db)
    queries["question_blueprints"].execute.assert_not_called()


def saved_receipt(manifest: dict[str, object] | None, modes: list[str]) -> dict[str, object]:
    return {
        "success": True,
        "session_id": str(SESSION_ID),
        "config_id": str(UUID(int=30)),
        "status": "configured",
        "config": {
            "n_versions": 2,
            "active_variation_modes": modes,
            "ordering_preferences": {"shuffle_questions": False, "shuffle_options": False},
            "source_manifest": manifest,
            "canonical_dimensions": ["values"] if modes else [],
            "mapping_version": "1.0",
        },
    }


def test_save_passes_exact_manifest_to_one_rpc_and_validates_receipt() -> None:
    db, queries = make_db(make_rows())
    manifest = canonical_snapshot()["manifest"]
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data=saved_receipt(manifest, ["NUMERICAL", "parameter_variation"])
    )
    config = GenerationConfigRequest(n_versions=2)
    result = GenerationConfigRepository(db).save_config(SESSION_ID, config, manifest)
    assert isinstance(result, GenerationConfigResponse)
    assert result.config.active_variation_modes == ["NUMERICAL", "parameter_variation"]
    db.rpc.assert_called_once_with(
        "save_generation_config",
        {
            "p_session_id": str(SESSION_ID),
            "p_n_versions": 2,
            "p_active_variation_modes": [],
            "p_ordering_preferences": {"shuffle_questions": False, "shuffle_options": False},
            "p_expected_snapshot": manifest,
        },
    )
    for query in queries.values():
        for method in ("insert", "update", "delete", "upsert"):
            getattr(query, method).assert_not_called()


def test_save_without_manifest_does_not_write() -> None:
    db, _ = make_db(make_rows())
    with pytest.raises(GenerationConfigError) as exc_info:
        GenerationConfigRepository(db).save_config(
            SESSION_ID, GenerationConfigRequest(n_versions=2), None
        )
    assert exc_info.value.status_code == 409
    db.rpc.assert_not_called()


@pytest.mark.parametrize(
    ("modes", "dimensions"),
    [
        ([], []),
        (["context_swap"], ["context"]),
        (["NUMERICAL", "parameter_variation", "context_swap"], ["values", "context"]),
    ],
)
def test_accept_server_modes_in_sql_order(modes: list[str], dimensions: list[str]) -> None:
    db, _ = make_db(make_rows())
    manifest = canonical_snapshot()["manifest"]
    receipt = saved_receipt(manifest, modes)
    receipt["config"]["canonical_dimensions"] = dimensions
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=receipt)
    result = GenerationConfigRepository(db).save_config(
        SESSION_ID, GenerationConfigRequest(n_versions=2), manifest
    )
    assert result.config.active_variation_modes == modes
    assert result.config.canonical_dimensions == dimensions


@pytest.mark.parametrize(
    "damage",
    [
        "wrong_session",
        "wrong_manifest",
        "wrong_modes",
        "wrong_mode_order",
        "wrong_dimension_order",
        "duplicate_dimension",
        "missing_ordering",
        "missing_config_id",
    ],
)
def test_bad_save_receipt_is_never_success(damage: str) -> None:
    db, _ = make_db(make_rows())
    manifest = canonical_snapshot()["manifest"]
    receipt = saved_receipt(manifest, ["NUMERICAL", "parameter_variation"])
    if damage == "wrong_session":
        receipt["session_id"] = str(QUESTION_2)
    elif damage == "wrong_manifest":
        receipt["config"]["source_manifest"] = None
    elif damage == "wrong_modes":
        receipt["config"]["active_variation_modes"] = []
    elif damage == "wrong_mode_order":
        receipt["config"]["active_variation_modes"] = ["parameter_variation", "NUMERICAL"]
    elif damage == "wrong_dimension_order":
        receipt["config"]["canonical_dimensions"] = ["context", "values"]
        receipt["config"]["active_variation_modes"].append("context_swap")
    elif damage == "duplicate_dimension":
        receipt["config"]["canonical_dimensions"] = ["values", "values"]
    elif damage == "missing_ordering":
        del receipt["config"]["ordering_preferences"]
    else:
        del receipt["config_id"]
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=receipt)
    with pytest.raises(GenerationConfigError) as exc_info:
        GenerationConfigRepository(db).save_config(
            SESSION_ID, GenerationConfigRequest(n_versions=2), manifest
        )
    assert exc_info.value.code == "ERR_CONFIG_STORAGE_FAILURE"


@pytest.mark.parametrize(
    ("sqlstate", "message", "http_status", "public_code"),
    [
        ("P0002", "Session not found", 404, "ERR_SESSION_NOT_FOUND"),
        ("42501", "Access denied", 403, "ERR_FORBIDDEN"),
        ("22023", "ERR_SOURCE_NOT_READY: ARTIFACT_STALE", 422, "ERR_SOURCE_NOT_READY"),
        ("22023", "ERR_CONFIG_CONFLICT: canonical mode intersection", 400, "ERR_CONFIG_CONFLICT"),
        ("55006", "ERR_CONFIG_CONFLICT: snapshot changed", 409, "ERR_CONFIG_CONFLICT"),
    ],
)
def test_save_maps_genuine_sqlstate_and_business_prefix(
    sqlstate: str, message: str, http_status: int, public_code: str
) -> None:
    db, _ = make_db(make_rows())
    db.rpc.return_value.execute.side_effect = APIError({"code": sqlstate, "message": message})
    with pytest.raises(GenerationConfigError) as exc_info:
        GenerationConfigRepository(db).save_config(
            SESSION_ID, GenerationConfigRequest(n_versions=2), canonical_snapshot()["manifest"]
        )
    assert (exc_info.value.status_code, exc_info.value.code) == (http_status, public_code)
    db.rpc.assert_called_once()


def test_save_timeout_is_uncertain_and_never_retried() -> None:
    db, _ = make_db(make_rows())
    db.rpc.return_value.execute.side_effect = TimeoutError("private connection")
    with pytest.raises(GenerationConfigError) as exc_info:
        GenerationConfigRepository(db).save_config(
            SESSION_ID, GenerationConfigRequest(n_versions=2), canonical_snapshot()["manifest"]
        )
    assert (exc_info.value.status_code, exc_info.value.code) == (504, "ERR_CONFIG_OUTCOME_UNCERTAIN")
    db.rpc.assert_called_once()

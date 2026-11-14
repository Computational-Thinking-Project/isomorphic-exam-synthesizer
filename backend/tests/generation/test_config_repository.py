from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call
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
CONFIRMED_AT = "2026-10-26T01:30:00+00:00"


def make_rows() -> dict[str, list[dict[str, object]]]:
    return {
        "exam_sessions": [{"id": str(SESSION_ID), "status": "blueprinted", "approved_at": None}],
        "source_questions": [
            {"id": str(QUESTION_1), "session_id": str(SESSION_ID)},
            {"id": str(QUESTION_2), "session_id": str(SESSION_ID)},
        ],
        "question_blueprints": [
            {
                "source_question_id": str(QUESTION_1),
                "variation_modes": ["NUMERICAL", "NONE"],
                "confirmed_at": CONFIRMED_AT,
                "is_fallback": True,
                "extraction_source": "FALLBACK_DETERMINISTIC",
            },
            {
                "source_question_id": str(QUESTION_2),
                "variation_modes": ["NONE"],
                "confirmed_at": CONFIRMED_AT,
            },
        ],
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


def test_loads_typed_context_with_session_scoped_reads_and_no_writes() -> None:
    rows = make_rows()
    original = deepcopy(rows)
    db, queries = make_db(rows)

    context = GenerationConfigRepository(db).load_context(SESSION_ID)

    assert context is not None
    assert context.session_id == SESSION_ID
    assert context.status == "blueprinted"
    assert [source.id for source in context.source_questions] == [QUESTION_1, QUESTION_2]
    assert all(source.session_id == SESSION_ID for source in context.source_questions)
    assert [bp.source_question_id for bp in context.blueprints] == [QUESTION_1, QUESTION_2]
    assert context.blueprints[0].confirmed_at == datetime(2026, 10, 26, 1, 30, tzinfo=timezone.utc)
    assert context.blueprints[0].variation_modes == ["NUMERICAL", "NONE"]
    assert rows == original

    db.rpc.assert_called_once_with("get_generation_source_snapshot", {"p_session_id": str(SESSION_ID)})
    assert db.table.call_args_list == [
        call("exam_sessions"),
        call("source_questions"),
        call("question_blueprints"),
    ]
    queries["exam_sessions"].select.assert_called_once_with("id,status,approved_at")
    queries["exam_sessions"].eq.assert_called_once_with("id", str(SESSION_ID))
    queries["source_questions"].select.assert_called_once_with("id,session_id")
    queries["source_questions"].eq.assert_called_once_with("session_id", str(SESSION_ID))
    queries["source_questions"].order.assert_called_once_with("question_no")
    queries["source_questions"].limit.assert_called_once_with(21)
    queries["question_blueprints"].select.assert_called_once_with(
        "source_question_id,variation_modes,confirmed_at"
    )
    queries["question_blueprints"].in_.assert_called_once_with(
        "source_question_id", [str(QUESTION_1), str(QUESTION_2)]
    )
    queries["question_blueprints"].limit.assert_called_once_with(3)
    assert_no_writes(db, queries)


def test_not_found_or_rls_hidden_session_stops_without_fallback_reads() -> None:
    rows = make_rows()
    rows["exam_sessions"] = []
    db, queries = make_db(rows)

    assert GenerationConfigRepository(db).load_context(SESSION_ID) is None
    db.table.assert_called_once_with("exam_sessions")
    queries["source_questions"].execute.assert_not_called()
    queries["question_blueprints"].execute.assert_not_called()
    assert_no_writes(db, queries)


def test_empty_sources_skip_blueprint_query_and_remain_a_readiness_error() -> None:
    rows = make_rows()
    rows["source_questions"] = []
    db, queries = make_db(rows)
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None
    assert context.source_questions == ()
    assert context.blueprints == ()
    queries["question_blueprints"].execute.assert_not_called()
    with pytest.raises(GenerationConfigError) as exc_info:
        validate_generation_config(
            GenerationConfigRequest(n_versions=1, active_variation_modes=[]), context
        )
    assert exc_info.value.code == "ERR_SOURCE_NOT_READY"
    assert_no_writes(db, queries)


@pytest.mark.parametrize("table", ["exam_sessions", "source_questions", "question_blueprints"])
@pytest.mark.parametrize("data", [None, {}, "unexpected", [None], ["row"]])
def test_malformed_database_results_are_not_coerced_to_empty_rows(table: str, data: object) -> None:
    rows: dict[str, object] = dict(make_rows())
    rows[table] = data
    db, queries = make_db(rows)
    assert_storage_failure(db)
    assert_no_writes(db, queries)


@pytest.mark.parametrize("table", ["exam_sessions", "source_questions", "question_blueprints"])
def test_database_exceptions_are_safe_and_do_not_trigger_writes_or_retries(table: str) -> None:
    db, queries = make_db(dict(make_rows()))
    queries[table].execute.side_effect = RuntimeError("private database failure details")
    assert_storage_failure(db)
    queries[table].execute.assert_called_once()
    assert_no_writes(db, queries)


@pytest.mark.parametrize(
    ("table", "field", "value"),
    [
        ("exam_sessions", "id", "invalid-uuid"),
        ("exam_sessions", "id", str(UUID(int=999))),
        ("exam_sessions", "status", None),
        ("exam_sessions", "status", ""),
        ("source_questions", "id", 2),
        ("source_questions", "session_id", str(UUID(int=999))),
        ("question_blueprints", "source_question_id", "invalid-uuid"),
        ("question_blueprints", "source_question_id", str(UUID(int=999))),
    ],
)
def test_malformed_identifiers_status_and_scope_fail_safely(
    table: str, field: str, value: object
) -> None:
    rows = make_rows()
    rows[table][0][field] = value
    db, queries = make_db(dict(rows))
    assert_storage_failure(db)
    if table == "source_questions":
        queries["question_blueprints"].execute.assert_not_called()
    assert_no_writes(db, queries)


@pytest.mark.parametrize(
    ("table", "field"),
    [
        ("exam_sessions", "id"),
        ("exam_sessions", "status"),
        ("exam_sessions", "approved_at"),
        ("source_questions", "id"),
        ("source_questions", "session_id"),
        ("question_blueprints", "source_question_id"),
        ("question_blueprints", "variation_modes"),
        ("question_blueprints", "confirmed_at"),
    ],
)
def test_required_database_fields_must_exist(table: str, field: str) -> None:
    rows = make_rows()
    del rows[table][0][field]
    db, _ = make_db(dict(rows))
    assert_storage_failure(db)


def test_duplicate_session_rows_are_an_internal_error() -> None:
    rows = make_rows()
    rows["exam_sessions"] *= 2
    db, _ = make_db(dict(rows))
    assert_storage_failure(db)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-26T01:30:00Z",
        "2026-10-26T08:30:00+07:00",
        datetime(2026, 10, 26, 1, 30, tzinfo=timezone.utc),
    ],
)
def test_confirmed_timestamps_are_parsed_with_timezone(timestamp: object) -> None:
    rows = make_rows()
    rows["question_blueprints"][0]["confirmed_at"] = timestamp
    db, _ = make_db(dict(rows))
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None
    assert context.blueprints[0].confirmed_at == datetime(2026, 10, 26, 1, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "timestamp", ["invalid", "", "2026-10-26", "2026-10-26T01:30:00", True, 123]
)
def test_invalid_or_naive_confirmation_timestamps_are_internal_errors(timestamp: object) -> None:
    rows = make_rows()
    rows["question_blueprints"][0]["confirmed_at"] = timestamp
    db, _ = make_db(dict(rows))
    assert_storage_failure(db)


@pytest.mark.parametrize("problem", ["missing", "duplicate", "unconfirmed"])
def test_blueprint_readiness_problems_are_preserved_for_the_validator(problem: str) -> None:
    rows = make_rows()
    if problem == "missing":
        rows["question_blueprints"] = rows["question_blueprints"][:1]
    elif problem == "duplicate":
        rows["question_blueprints"].append(deepcopy(rows["question_blueprints"][0]))
    else:
        rows["question_blueprints"][0]["confirmed_at"] = None
    db, queries = make_db(dict(rows))
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None
    with pytest.raises(GenerationConfigError) as exc_info:
        validate_generation_config(
            GenerationConfigRequest(n_versions=1, active_variation_modes=[]), context
        )
    assert exc_info.value.code == "ERR_SOURCE_NOT_READY"
    assert_no_writes(db, queries)


@pytest.mark.parametrize("modes", [None, "NONE", [1], [""]])
def test_invalid_stored_modes_reach_the_validator_without_silent_defaults(modes: object) -> None:
    rows = make_rows()
    rows["question_blueprints"][0]["variation_modes"] = modes
    db, _ = make_db(dict(rows))
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None
    assert context.blueprints[0].variation_modes == modes
    with pytest.raises(GenerationConfigError) as exc_info:
        validate_generation_config(
            GenerationConfigRequest(n_versions=1, active_variation_modes=[]), context
        )
    assert exc_info.value.code == "ERR_CONFIG_STORAGE_FAILURE"


def test_source_overflow_is_detectable_without_unbounded_reads() -> None:
    rows = make_rows()
    rows["source_questions"] = [
        {"id": str(UUID(int=100 + i)), "session_id": str(SESSION_ID)} for i in range(21)
    ]
    rows["question_blueprints"] = []
    db, queries = make_db(dict(rows))
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None
    assert len(context.source_questions) == 21
    queries["source_questions"].limit.assert_called_once_with(21)
    with pytest.raises(GenerationConfigError) as exc_info:
        validate_generation_config(
            GenerationConfigRequest(n_versions=1, active_variation_modes=[]), context
        )
    assert exc_info.value.code == "ERR_SOURCE_NOT_READY"


def test_duplicate_sources_are_not_hidden_by_deduplication_of_query_ids() -> None:
    rows = make_rows()
    rows["source_questions"].append(deepcopy(rows["source_questions"][0]))
    db, queries = make_db(dict(rows))
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None
    assert len(context.source_questions) == 3
    queries["question_blueprints"].in_.assert_called_once_with(
        "source_question_id", [str(QUESTION_1), str(QUESTION_2)]
    )
    with pytest.raises(GenerationConfigError) as exc_info:
        validate_generation_config(
            GenerationConfigRequest(n_versions=1, active_variation_modes=[]), context
        )
    assert exc_info.value.code == "ERR_SOURCE_NOT_READY"


@pytest.mark.parametrize("session_status", ["blueprinted", "configured", "draft"])
def test_repository_reads_state_without_reimplementing_business_policy(session_status: str) -> None:
    rows = make_rows()
    rows["exam_sessions"][0]["status"] = session_status
    db, queries = make_db(dict(rows))
    context = GenerationConfigRepository(db).load_context(SESSION_ID)
    assert context is not None
    assert context.status == session_status
    assert_no_writes(db, queries)


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
            "requirement": {"variation_policy": {"allowed_transformations": [{"dimension": "values"}]}}
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
    assert validate_generation_config(
        GenerationConfigRequest(n_versions=1, active_variation_modes=["NUMERICAL"]), context
    ).active_variation_modes == ["NUMERICAL"]
    assert_no_writes(db, queries)


@pytest.mark.parametrize("reason", ["ARTIFACT_STALE", "CANONICAL_BLUEPRINTS_INCOMPLETE"])
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
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": True},
            "source_manifest": manifest,
            "canonical_dimensions": ["values"] if modes else [],
            "mapping_version": "1.0",
        },
    }


def test_save_passes_exact_manifest_to_one_rpc_and_validates_receipt() -> None:
    db, queries = make_db(make_rows())
    manifest = canonical_snapshot()["manifest"]
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=saved_receipt(manifest, ["NUMERICAL"]))
    config = GenerationConfigRequest(n_versions=2, active_variation_modes=["NUMERICAL"])
    result = GenerationConfigRepository(db).save_config(SESSION_ID, config, manifest)
    assert isinstance(result, GenerationConfigResponse)
    db.rpc.assert_called_once_with("save_generation_config", {
        "p_session_id": str(SESSION_ID),
        "p_n_versions": 2,
        "p_active_variation_modes": ["NUMERICAL"],
        "p_ordering_preferences": {"shuffle_questions": True, "shuffle_options": True},
        "p_expected_snapshot": manifest,
    })
    for query in queries.values():
        for method in ("insert", "update", "delete", "upsert"):
            getattr(query, method).assert_not_called()


def test_legacy_save_sends_explicit_null_manifest() -> None:
    db, _ = make_db(make_rows())
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=saved_receipt(None, []))
    result = GenerationConfigRepository(db).save_config(
        SESSION_ID, GenerationConfigRequest(n_versions=2, active_variation_modes=[]), None
    )
    assert result.config.source_manifest is None
    assert db.rpc.call_args.args[1]["p_expected_snapshot"] is None


@pytest.mark.parametrize("damage", ["wrong_session", "wrong_manifest", "wrong_modes", "missing_config_id"])
def test_bad_save_receipt_is_never_success(damage: str) -> None:
    db, _ = make_db(make_rows())
    manifest = canonical_snapshot()["manifest"]
    receipt = saved_receipt(manifest, ["NUMERICAL"])
    if damage == "wrong_session":
        receipt["session_id"] = str(QUESTION_2)
    elif damage == "wrong_manifest":
        receipt["config"]["source_manifest"] = None
    elif damage == "wrong_modes":
        receipt["config"]["active_variation_modes"] = []
    else:
        del receipt["config_id"]
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=receipt)
    with pytest.raises(GenerationConfigError) as exc_info:
        GenerationConfigRepository(db).save_config(
            SESSION_ID, GenerationConfigRequest(n_versions=2, active_variation_modes=["NUMERICAL"]), manifest
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
            SESSION_ID, GenerationConfigRequest(n_versions=2, active_variation_modes=[]), None
        )
    assert (exc_info.value.status_code, exc_info.value.code) == (http_status, public_code)
    db.rpc.assert_called_once()


def test_save_timeout_is_uncertain_and_never_retried() -> None:
    db, _ = make_db(make_rows())
    db.rpc.return_value.execute.side_effect = TimeoutError("private connection")
    with pytest.raises(GenerationConfigError) as exc_info:
        GenerationConfigRepository(db).save_config(
            SESSION_ID, GenerationConfigRequest(n_versions=2, active_variation_modes=[]), None
        )
    assert (exc_info.value.status_code, exc_info.value.code) == (504, "ERR_CONFIG_OUTCOME_UNCERTAIN")
    db.rpc.assert_called_once()

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call
from uuid import UUID

import pytest

from app.models.generation_config import GenerationConfigRequest
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
        "exam_sessions": [{"id": str(SESSION_ID), "status": "blueprinted"}],
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
    return db, queries


def assert_no_writes(db: MagicMock, queries: dict[str, MagicMock]) -> None:
    db.rpc.assert_not_called()
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

    assert db.table.call_args_list == [
        call("exam_sessions"),
        call("source_questions"),
        call("question_blueprints"),
    ]
    queries["exam_sessions"].select.assert_called_once_with("id,status")
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

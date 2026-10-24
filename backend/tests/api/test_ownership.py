"""Unit tests for assert_ownership helper and table whitelist (SEC-07)."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.dependencies import ALLOWED_TABLES, assert_ownership


def make_mock_db(data_map: dict[str, dict[str, list[dict]]]):
    """Helper to mock Supabase client queries.

    data_map format:
    {
        "table_name": {
            "resource_id": [{"col": "val", ...}]
        }
    }
    """
    mock_client = MagicMock()

    def table_side_effect(table_name):
        mock_table = MagicMock()

        def select_side_effect(cols):
            mock_select = MagicMock()

            def eq_side_effect(col_name, val):
                mock_eq = MagicMock()
                mock_exec = MagicMock()
                # Lookup row in data_map
                records = data_map.get(table_name, {}).get(str(val), [])
                mock_exec.data = records
                mock_eq.execute.return_value = mock_exec
                return mock_eq

            mock_select.eq.side_effect = eq_side_effect
            return mock_select

        mock_table.select.side_effect = select_side_effect
        return mock_table

    mock_client.table.side_effect = table_side_effect
    return mock_client


def test_disallowed_table_raises_400():
    """Any table outside ALLOWED_TABLES must immediately raise 400 Bad Request."""
    invalid_tables = ["users", "security_events", "non_existent_table", "information_schema"]
    for tbl in invalid_tables:
        with pytest.raises(HTTPException) as exc_info:
            assert_ownership(
                table=tbl,
                resource_id="some-id",
                user_id="user-123",
                db=MagicMock(),
            )
        assert exc_info.value.status_code == 400
        assert f"Table '{tbl}' is not permitted" in exc_info.value.detail


def test_allowed_tables_match_specification():
    """Verify ALLOWED_TABLES strictly contains the 8 expected tables."""
    expected = {
        "exam_sessions",
        "source_questions",
        "question_blueprints",
        "generation_configs",
        "exam_versions",
        "version_questions",
        "answer_keys",
        "review_logs",
    }
    assert ALLOWED_TABLES == expected


def test_exam_sessions_direct_ownership_success():
    """Direct ownership check on exam_sessions succeeds when user_id matches."""
    db = make_mock_db({
        "exam_sessions": {
            "session-1": [{"user_id": "user-alice"}],
        }
    })
    # Should not raise any exception
    assert_ownership("exam_sessions", "session-1", "user-alice", db=db)


def test_exam_sessions_forbidden():
    """Raises 403 Forbidden when exam_sessions belongs to another user."""
    db = make_mock_db({
        "exam_sessions": {
            "session-1": [{"user_id": "user-bob"}],
        }
    })
    with pytest.raises(HTTPException) as exc_info:
        assert_ownership("exam_sessions", "session-1", "user-alice", db=db)
    assert exc_info.value.status_code == 403
    assert "You do not have permission" in exc_info.value.detail


def test_exam_sessions_not_found():
    """Raises 404 Not Found when session does not exist."""
    db = make_mock_db({"exam_sessions": {}})
    with pytest.raises(HTTPException) as exc_info:
        assert_ownership("exam_sessions", "non-existent-session", "user-alice", db=db)
    assert exc_info.value.status_code == 404
    assert "Resource not found" in exc_info.value.detail


def test_source_questions_traversal_success():
    """source_questions traverses to exam_sessions and validates owner."""
    db = make_mock_db({
        "source_questions": {
            "sq-1": [{"session_id": "session-1"}],
        },
        "exam_sessions": {
            "session-1": [{"user_id": "user-alice"}],
        },
    })
    assert_ownership("source_questions", "sq-1", "user-alice", db=db)


def test_question_blueprints_traversal_success():
    """question_blueprints -> source_questions -> exam_sessions."""
    db = make_mock_db({
        "question_blueprints": {
            "bp-1": [{"source_question_id": "sq-1"}],
        },
        "source_questions": {
            "sq-1": [{"session_id": "session-1"}],
        },
        "exam_sessions": {
            "session-1": [{"user_id": "user-alice"}],
        },
    })
    assert_ownership("question_blueprints", "bp-1", "user-alice", db=db)


def test_version_questions_traversal_success():
    """version_questions -> exam_versions -> exam_sessions."""
    db = make_mock_db({
        "version_questions": {
            "vq-1": [{"version_id": "ver-1"}],
        },
        "exam_versions": {
            "ver-1": [{"session_id": "session-1"}],
        },
        "exam_sessions": {
            "session-1": [{"user_id": "user-alice"}],
        },
    })
    assert_ownership("version_questions", "vq-1", "user-alice", db=db)


def test_review_logs_traversal_success():
    """review_logs -> version_questions -> exam_versions -> exam_sessions."""
    db = make_mock_db({
        "review_logs": {
            "rl-1": [{"version_question_id": "vq-1"}],
        },
        "version_questions": {
            "vq-1": [{"version_id": "ver-1"}],
        },
        "exam_versions": {
            "ver-1": [{"session_id": "session-1"}],
        },
        "exam_sessions": {
            "session-1": [{"user_id": "user-alice"}],
        },
    })
    assert_ownership("review_logs", "rl-1", "user-alice", db=db)


def test_traversal_forbidden_for_other_user():
    """Traversing child resource fails with 403 when root session is owned by someone else."""
    db = make_mock_db({
        "review_logs": {
            "rl-1": [{"version_question_id": "vq-1"}],
        },
        "version_questions": {
            "vq-1": [{"version_id": "ver-1"}],
        },
        "exam_versions": {
            "ver-1": [{"session_id": "session-1"}],
        },
        "exam_sessions": {
            "session-1": [{"user_id": "user-mallory"}],
        },
    })
    with pytest.raises(HTTPException) as exc_info:
        assert_ownership("review_logs", "rl-1", "user-alice", db=db)
    assert exc_info.value.status_code == 403


def test_traversal_intermediate_not_found():
    """Traversing child resource fails with 404 when intermediate parent is missing."""
    db = make_mock_db({
        "question_blueprints": {
            "bp-1": [{"source_question_id": "missing-sq"}],
        },
        "source_questions": {},
    })
    with pytest.raises(HTTPException) as exc_info:
        assert_ownership("question_blueprints", "bp-1", "user-alice", db=db)
    assert exc_info.value.status_code == 404

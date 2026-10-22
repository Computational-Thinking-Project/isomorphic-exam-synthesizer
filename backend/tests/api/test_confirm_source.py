"""Unit tests for Confirm Source Exam & Blueprint Activation (TASK-205).

Validates all 12 test cases:
1. Unauthenticated (401)
2. Forbidden / Wrong Owner (403)
3. Session Not Found (404)
4. Conflict when status == 'blueprinted' (409)
5. Conflict when status == 'generating' (409)
6. 422 when Session has no questions
7. 422 when questions have missing answers
8. 422 when questions have security warnings and acknowledged=False
9. 422 when questions have security warnings and body is empty {}
10. Success when 0 security warnings and blueprints exist (200)
11. Success when security warnings acknowledged=True (200)
12. Auto-creation of missing blueprints during confirmation (200)
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

MOCK_SESSION_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer mock-valid-jwt-token"}


@pytest.fixture
def mock_auth_user(mock_user_response):
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = mock_user_response
    return mock_supabase


def _create_mock_questions(count: int = 5, has_missing: bool = False, has_warning: bool = False):
    """Helper to create dummy source question records."""
    questions = []
    for i in range(1, count + 1):
        questions.append(
            {
                "id": f"00000000-0000-0000-0000-00000000000{i}",
                "session_id": MOCK_SESSION_ID,
                "question_no": i,
                "raw_content": f"Câu {i}: Cho tam giác vuông có cạnh {i} và {i + 1}.",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "correct_key": "A",
                "solution_md": "Lời giải",
                "has_missing_answer": (i == 2 and has_missing),
                "has_security_warning": (i == 1 and has_warning),
            }
        )
    return questions


# ---------------------------------------------------------------------------
# 1. Unauthenticated & Authorization Tests
# ---------------------------------------------------------------------------


def test_confirm_unauthenticated(client):
    """POST /confirm-source without Bearer token returns 401."""
    response = client.post(
        f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
        json={"acknowledged_security_warnings": False},
    )
    assert response.status_code == 401


def test_confirm_forbidden_wrong_owner(client, mock_auth_user, auth_headers):
    """POST /confirm-source raises 403 Forbidden when assert_ownership rejects."""
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch(
            "app.api.routes.sessions.assert_ownership",
            side_effect=HTTPException(status_code=403, detail="Forbidden: Not session owner"),
        ),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )
    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]


def test_confirm_session_not_found(client, mock_auth_user, auth_headers):
    """POST /confirm-source raises 404 Not Found when session does not exist."""
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch(
            "app.api.routes.sessions.assert_ownership",
            side_effect=HTTPException(status_code=404, detail="Session not found"),
        ),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 2. State Precondition Tests (HTTP 409)
# ---------------------------------------------------------------------------


def test_confirm_conflict_blueprinted(client, mock_auth_user, auth_headers):
    """Reject with 409 Conflict if session is already 'blueprinted'."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "blueprinted"}]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )
    assert response.status_code == 409
    assert "blueprinted" in response.json()["detail"]


def test_confirm_conflict_generating(client, mock_auth_user, auth_headers):
    """Reject with 409 Conflict if session is in 'generating' status."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "generating"}]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )
    assert response.status_code == 409
    assert "generating" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 3. Data Integrity & Validation Tests (HTTP 422)
# ---------------------------------------------------------------------------


def test_confirm_422_no_questions(client, mock_auth_user, auth_headers):
    """Reject with 422 Unprocessable Entity if session has no source questions."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]
    mock_questions = MagicMock()
    mock_questions.data = []

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
        mock_questions
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )
    assert response.status_code == 422
    assert "no source questions" in response.json()["detail"]


def test_confirm_422_has_missing_answer(client, mock_auth_user, auth_headers):
    """Reject with 422 Unprocessable Entity if any question is missing an answer key."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]
    mock_questions = MagicMock()
    mock_questions.data = _create_mock_questions(count=3, has_missing=True)

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
        mock_questions
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )
    assert response.status_code == 422
    assert "missing answers" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 4. Security (SEC-02) Tests (HTTP 422)
# ---------------------------------------------------------------------------


def test_confirm_422_security_unacknowledged(client, mock_auth_user, auth_headers):
    """Reject with 422 if questions have security warnings and acknowledged=False."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]
    mock_questions = MagicMock()
    mock_questions.data = _create_mock_questions(count=3, has_warning=True)

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
        mock_questions
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )
    assert response.status_code == 422
    assert "security warnings" in response.json()["detail"]


def test_confirm_422_security_missing_body(client, mock_auth_user, auth_headers):
    """Reject with 422 when body is empty {} and warnings exist (defaults to False)."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]
    mock_questions = MagicMock()
    mock_questions.data = _create_mock_questions(count=3, has_warning=True)

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
        mock_questions
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={},
            headers=auth_headers,
        )
    assert response.status_code == 422
    assert "security warnings" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 5. Success Flow & Blueprint Auto-Creation (HTTP 200)
# ---------------------------------------------------------------------------


def test_confirm_success_no_warnings(client, mock_auth_user, auth_headers):
    """Successful source confirmation when 0 security warnings exist."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]
    mock_questions = MagicMock()
    mock_questions.data = _create_mock_questions(count=5)

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
        mock_questions
    )

    # Blueprints query returns all existing
    mock_bps = MagicMock()
    mock_bps.data = [{"source_question_id": q["id"]} for q in mock_questions.data]
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_bps

    # Update calls
    mock_update = MagicMock()
    mock_update.data = [{}]
    mock_db.table.return_value.update.return_value.in_.return_value.execute.return_value = (
        mock_update
    )
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        mock_update
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == MOCK_SESSION_ID
    assert data["status"] == "blueprinted"
    assert data["total_questions"] == 5
    assert data["total_blueprints"] == 5
    assert "confirmed_at" in data
    assert data["confirmed_at"] is not None


def test_confirm_success_security_acknowledged(client, mock_auth_user, auth_headers):
    """Successful confirmation when security warning exists and acknowledged=True."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]
    mock_questions = MagicMock()
    mock_questions.data = _create_mock_questions(count=3, has_warning=True)

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
        mock_questions
    )

    mock_bps = MagicMock()
    mock_bps.data = [{"source_question_id": q["id"]} for q in mock_questions.data]
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_bps

    mock_update = MagicMock()
    mock_update.data = [{}]
    mock_db.table.return_value.update.return_value.in_.return_value.execute.return_value = (
        mock_update
    )
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        mock_update
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": True},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blueprinted"
    assert data["total_questions"] == 3


def test_confirm_auto_creates_missing_blueprints(client, mock_auth_user, auth_headers):
    """Confirm-source auto-creates missing blueprints if background task was partial."""
    mock_db = MagicMock()
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]
    mock_questions = MagicMock()
    mock_questions.data = _create_mock_questions(count=5)

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_status
    )
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
        mock_questions
    )

    # Only 3 blueprints exist initially (questions 1, 2, 3)
    mock_bps = MagicMock()
    mock_bps.data = [{"source_question_id": q["id"]} for q in mock_questions.data[:3]]
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_bps

    # Mock insert for missing blueprints
    mock_insert = MagicMock()
    mock_insert.data = [{}]
    mock_db.table.return_value.insert.return_value.execute.return_value = mock_insert

    # Update calls
    mock_update = MagicMock()
    mock_update.data = [{}]
    mock_db.table.return_value.update.return_value.in_.return_value.execute.return_value = (
        mock_update
    )
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        mock_update
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
        patch("app.api.routes.sessions.assert_ownership", return_value=None),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/confirm-source",
            json={"acknowledged_security_warnings": False},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total_questions"] == 5
    assert data["total_blueprints"] == 5
    # Verify insert was called for missing blueprints
    mock_db.table("question_blueprints").insert.assert_called_once()

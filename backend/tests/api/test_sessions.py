"""Unit tests for Exam Sessions CRUD and Clone API endpoints (TASK-104)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer mock-valid-jwt-token"}


@pytest.fixture
def mock_auth_user(mock_user_response):
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = mock_user_response
    return mock_supabase


def test_create_session_unauthenticated(client):
    """POST /api/sessions without token returns 401."""
    response = client.post("/api/sessions", json={"title": "Đề thi thử"})
    assert response.status_code == 401


def test_create_session_validation_error(client, mock_auth_user, auth_headers):
    """POST /api/sessions with empty title returns 422."""
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=MagicMock()),
    ):
        response = client.post("/api/sessions", json={"title": ""}, headers=auth_headers)
    assert response.status_code == 422



def test_create_session_success(client, mock_auth_user, test_user_id, auth_headers):
    """POST /api/sessions creates session with draft status and returns 201."""
    mock_db = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = [{
        "id": "new-session-uuid-1",
        "user_id": test_user_id,
        "title": "Đề thi Khảo sát Toán 12",
        "subject": "Toán",
        "grade": 12,
        "status": "draft",
        "gemini_call_count": 0,
        "retry_count": 0,
        "approved_at": None,
        "created_at": "2026-10-18T12:00:00Z",
        "updated_at": "2026-10-18T12:00:00Z",
    }]
    mock_db.table.return_value.insert.return_value.execute.return_value = mock_exec

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post(
            "/api/sessions",
            json={"title": "Đề thi Khảo sát Toán 12", "subject": "Toán", "grade": 12},
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "new-session-uuid-1"
    assert data["title"] == "Đề thi Khảo sát Toán 12"
    assert data["status"] == "draft"
    assert data["user_id"] == test_user_id


def test_list_sessions_success(client, mock_auth_user, test_user_id, auth_headers):
    """GET /api/sessions returns paginated session list for current user."""
    mock_db = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = [
        {
            "id": "session-1",
            "user_id": test_user_id,
            "title": "Đề 1",
            "subject": "Toán",
            "grade": 12,
            "status": "draft",
            "gemini_call_count": 0,
            "retry_count": 0,
            "approved_at": None,
            "created_at": "2026-10-18T10:00:00Z",
            "updated_at": "2026-10-18T10:00:00Z",
        },
        {
            "id": "session-2",
            "user_id": test_user_id,
            "title": "Đề 2",
            "subject": "Toán",
            "grade": 12,
            "status": "approved",
            "gemini_call_count": 4,
            "retry_count": 0,
            "approved_at": "2026-10-18T11:00:00Z",
            "created_at": "2026-10-18T09:00:00Z",
            "updated_at": "2026-10-18T11:00:00Z",
        },
    ]
    mock_exec.count = 2

    # Chain: table().select().eq().order().range().execute()
    mock_query = MagicMock()
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.range.return_value.execute.return_value = mock_exec
    mock_db.table.return_value.select.return_value = mock_query

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions?page=1&page_size=10", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == "session-1"
    assert data["items"][1]["id"] == "session-2"


def test_list_sessions_empty(client, mock_auth_user, auth_headers):
    """GET /api/sessions returns empty list when user has no sessions."""
    mock_db = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = []
    mock_exec.count = 0

    mock_query = MagicMock()
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.range.return_value.execute.return_value = mock_exec
    mock_db.table.return_value.select.return_value = mock_query

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_get_session_detail_success(client, mock_auth_user, test_user_id, auth_headers):
    """GET /api/sessions/{id} returns full detail with source questions and versions."""
    mock_db = MagicMock()

    # Route calls:
    # 1. assert_ownership -> table("exam_sessions").select("user_id").eq("id", "session-1") -> [{"user_id": test_user_id}]
    # 2. session info -> table("exam_sessions").select("*").eq("id", "session-1") -> [session record]
    # 3. questions -> table("source_questions").select("*").eq("session_id", "session-1") -> [questions]
    # 4. versions -> table("exam_versions").select("*").eq("session_id", "session-1") -> [versions]
    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-1",
                "user_id": test_user_id,
                "title": "Đề thi chi tiết",
                "subject": "Toán",
                "grade": 12,
                "status": "draft",
                "gemini_call_count": 0,
                "retry_count": 0,
                "approved_at": None,
                "created_at": "2026-10-18T10:00:00Z",
                "updated_at": "2026-10-18T10:00:00Z",
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s
        elif table_name == "source_questions":
            exec_q = MagicMock()
            exec_q.data = [{
                "id": "sq-1",
                "session_id": "session-1",
                "question_no": 1,
                "raw_content": "Cho hàm số $y=f(x)$...",
            }]
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_q
        elif table_name == "exam_versions":
            exec_v = MagicMock()
            exec_v.data = [{
                "id": "ver-1",
                "session_id": "session-1",
                "version_code": "101",
            }]
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_v
        return mock_t

    mock_db.table.side_effect = table_router

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions/session-1", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "session-1"
    assert data["title"] == "Đề thi chi tiết"
    assert len(data["source_questions"]) == 1
    assert data["source_questions"][0]["id"] == "sq-1"
    assert len(data["exam_versions"]) == 1
    assert data["exam_versions"][0]["version_code"] == "101"


def test_get_session_detail_forbidden(client, mock_auth_user, auth_headers):
    """GET /api/sessions/{id} returns 403 when session belongs to another user."""
    mock_db = MagicMock()
    exec_res = MagicMock()
    exec_res.data = [{"user_id": "different-user-uuid"}]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = exec_res

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions/session-other", headers=auth_headers)

    assert response.status_code == 403


def test_get_session_detail_not_found(client, mock_auth_user, auth_headers):
    """GET /api/sessions/{id} returns 404 when session does not exist."""
    mock_db = MagicMock()
    exec_res = MagicMock()
    exec_res.data = []
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = exec_res

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions/non-existent-session", headers=auth_headers)

    assert response.status_code == 404


def test_update_session_success(client, mock_auth_user, test_user_id, auth_headers):
    """PATCH /api/sessions/{id} updates title and returns updated session."""
    mock_db = MagicMock()

    # assert_ownership check
    exec_owner = MagicMock()
    exec_owner.data = [{"user_id": test_user_id}]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = exec_owner

    # update
    exec_upd = MagicMock()
    exec_upd.data = [{
        "id": "session-1",
        "user_id": test_user_id,
        "title": "Tên mới cập nhật",
        "subject": "Toán",
        "grade": 12,
        "status": "draft",
        "gemini_call_count": 0,
        "retry_count": 0,
        "approved_at": None,
        "created_at": "2026-10-18T10:00:00Z",
        "updated_at": "2026-10-18T10:30:00Z",
    }]
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = exec_upd

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.patch(
            "/api/sessions/session-1",
            json={"title": "Tên mới cập nhật"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Tên mới cập nhật"


def test_delete_session_success(client, mock_auth_user, test_user_id, auth_headers):
    """DELETE /api/sessions/{id} deletes session and returns 204 No Content."""
    mock_db = MagicMock()
    exec_owner = MagicMock()
    exec_owner.data = [{"user_id": test_user_id}]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = exec_owner
    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.delete("/api/sessions/session-1", headers=auth_headers)

    assert response.status_code == 204


def test_clone_session_default_title(client, mock_auth_user, test_user_id, auth_headers):
    """POST /api/sessions/{id}/clone copies session and appends '(Bản sao)' to title."""
    mock_db = MagicMock()

    # Route interactions:
    # 1. assert_ownership -> user_id check
    # 2. orig_res -> exam_sessions.select("*").eq("id", "session-orig")
    # 3. create_res -> exam_sessions.insert(new_session_data)
    # 4. sq_res -> source_questions.select("*").eq("session_id", "session-orig") -> 1 question
    # 5. ins_sq_res -> source_questions.insert() -> returns new sq
    # 6. bp_res -> question_blueprints.select("*").eq("source_question_id", "old-sq-1") -> 1 blueprint
    # 7. ins_bp_res -> question_blueprints.insert()
    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            # select for assert_ownership and original
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-orig",
                "user_id": test_user_id,
                "title": "Đề thi ban đầu",
                "subject": "Toán",
                "grade": 12,
                "status": "blueprinted",
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s

            # insert cloned
            exec_ins = MagicMock()
            exec_ins.data = [{
                "id": "session-cloned-uuid",
                "user_id": test_user_id,
                "title": "Đề thi ban đầu (Bản sao)",
                "subject": "Toán",
                "grade": 12,
                "status": "draft",
                "gemini_call_count": 0,
                "retry_count": 0,
                "approved_at": None,
                "created_at": "2026-10-18T12:00:00Z",
                "updated_at": "2026-10-18T12:00:00Z",
            }]
            mock_t.insert.return_value.execute.return_value = exec_ins

        elif table_name == "source_questions":
            exec_sq = MagicMock()
            exec_sq.data = [{
                "id": "sq-old-1",
                "session_id": "session-orig",
                "question_no": 1,
                "raw_content": "Câu 1 gốc...",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "correct_key": "A",
            }]
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_sq

            exec_ins_sq = MagicMock()
            exec_ins_sq.data = [{"id": "sq-new-1"}]
            mock_t.insert.return_value.execute.return_value = exec_ins_sq

        elif table_name == "question_blueprints":
            exec_bp = MagicMock()
            exec_bp.data = [{
                "id": "bp-old-1",
                "source_question_id": "sq-old-1",
                "variables": {"x": "int"},
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_bp
            mock_t.insert.return_value.execute.return_value = MagicMock()

        return mock_t

    mock_db.table.side_effect = table_router

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post("/api/sessions/session-orig/clone", headers=auth_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "session-cloned-uuid"
    assert data["title"] == "Đề thi ban đầu (Bản sao)"
    assert data["status"] == "draft"


def test_clone_session_custom_title(client, mock_auth_user, test_user_id, auth_headers):
    """POST /api/sessions/{id}/clone with new_title uses the provided title."""
    mock_db = MagicMock()

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-orig",
                "user_id": test_user_id,
                "title": "Đề thi ban đầu",
                "subject": "Toán",
                "grade": 12,
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s

            exec_ins = MagicMock()
            exec_ins.data = [{
                "id": "session-cloned-uuid-2",
                "user_id": test_user_id,
                "title": "Tên tùy chỉnh cho bản sao",
                "subject": "Toán",
                "grade": 12,
                "status": "draft",
                "gemini_call_count": 0,
                "retry_count": 0,
                "approved_at": None,
                "created_at": "2026-10-18T12:00:00Z",
                "updated_at": "2026-10-18T12:00:00Z",
            }]
            mock_t.insert.return_value.execute.return_value = exec_ins

        elif table_name == "source_questions":
            exec_sq = MagicMock()
            exec_sq.data = []  # Empty session clone
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_sq

        return mock_t

    mock_db.table.side_effect = table_router

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post(
            "/api/sessions/session-orig/clone",
            json={"new_title": "Tên tùy chỉnh cho bản sao"},
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Tên tùy chỉnh cho bản sao"

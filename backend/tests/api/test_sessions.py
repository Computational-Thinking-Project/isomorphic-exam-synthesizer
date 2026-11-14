"""Unit tests for Exam Sessions CRUD and Clone API endpoints (TASK-104)."""

import json
from unittest.mock import MagicMock, patch

import pytest

SOURCE_REVISION = "11111111-2222-4333-8444-555555555555"


def configure_session_detail_rpcs(
    mock_db, session, questions, *, generation_snapshot=None, generation_error=None
):
    """Model the two distinct RPC contracts used by merged Stage 1/Stage 2."""
    def rpc_router(name, params):
        assert params == {"p_session_id": session["id"]}
        rpc = MagicMock()
        if name == "get_session_source_preview":
            rpc.execute.return_value.data = {
                "session": session,
                "source_revision": SOURCE_REVISION,
                "source_questions": questions,
            }
        elif name == "get_generation_source_snapshot":
            if generation_error is not None:
                rpc.execute.side_effect = generation_error
            else:
                rpc.execute.return_value.data = generation_snapshot
        else:
            raise AssertionError(f"Unexpected RPC: {name}")
        return rpc

    mock_db.rpc.side_effect = rpc_router


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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}

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
        elif table_name == "generation_configs":
            exec_cfg = MagicMock()
            exec_cfg.data = [{
                "id": "cfg-1",
                "session_id": "session-1",
                "n_versions": 2,
                "active_variation_modes": ["parameter_variation"],
                "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
            }]
            mock_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = exec_cfg
        elif table_name == "question_blueprints":
            exec_bp = MagicMock()
            exec_bp.data = [{
                "id": "bp-1",
                "source_question_id": "sq-1",
                "confirmed_at": "2026-10-18T10:05:00Z",
                "is_fallback": False,
                "variation_modes": ["parameter_variation", "context_swap"],
            }]
            mock_t.select.return_value.in_.return_value.execute.return_value = exec_bp
        return mock_t

    mock_db.table.side_effect = table_router
    preview_session = table_router("exam_sessions").select().eq().execute().data[0]
    preview_questions = table_router("source_questions").select().eq().order().execute().data
    configure_session_detail_rpcs(
        mock_db, preview_session, preview_questions,
        generation_snapshot={"ready": False, "reason": "NO_CONFIRMATION"},
    )

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
    assert data["generation_config"] is not None
    assert data["generation_config"]["n_versions"] == 2
    assert data["blueprint_summary"] is not None
    # W4: this fixture is draft + NO_CONFIRMATION. Copied/old confirmed legacy
    # rows must not make an unconfirmed import/clone appear generation-ready.
    assert data["blueprint_summary"]["is_ready"] is False
    assert data["blueprint_summary"]["supported_modes"] is None
    # Q01: source_revision must be present and equal to updated_at
    assert data["source_revision"] == SOURCE_REVISION
    mock_db.rpc.assert_any_call("get_session_source_preview", {"p_session_id": "session-1"})
    mock_db.rpc.assert_any_call("get_generation_source_snapshot", {"p_session_id": "session-1"})
    assert "source_questions" not in [call.args[0] for call in mock_db.table.call_args_list]


def test_get_session_detail_forbidden(client, mock_auth_user, auth_headers):
    """GET /api/sessions/{id} returns 403 when session belongs to another user."""
    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}

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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}

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
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}

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


def test_create_session_whitespace_title_rejected(client, mock_auth_user, auth_headers):
    """POST /api/sessions with whitespace-only title returns 422."""
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=MagicMock()),
    ):
        response = client.post("/api/sessions", json={"title": "   "}, headers=auth_headers)
    assert response.status_code == 422


def test_update_session_whitespace_title_rejected(client, mock_auth_user, auth_headers):
    """PATCH /api/sessions/{id} with whitespace-only title returns 422."""
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=MagicMock()),
    ):
        response = client.patch(
            "/api/sessions/session-1",
            json={"title": "   "},
            headers=auth_headers,
        )
    assert response.status_code == 422


def test_clone_session_whitespace_title_rejected(client, mock_auth_user, auth_headers):
    """POST /api/sessions/{id}/clone with whitespace-only new_title returns 422."""
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=MagicMock()),
    ):
        response = client.post(
            "/api/sessions/session-1/clone",
            json={"new_title": "   "},
            headers=auth_headers,
        )
    assert response.status_code == 422


def test_clone_session_fails_and_cleans_up_when_question_insert_returns_empty(
    client, mock_auth_user, test_user_id, auth_headers
):
    """POST /api/sessions/{id}/clone triggers cleanup when question insert returns empty data."""
    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
    deleted_session_ids = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            # Ownership check & fetch orig session
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-orig",
                "user_id": test_user_id,
                "title": "Đề thi gốc",
                "subject": "Toán",
                "grade": 12,
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s

            # Insert cloned session
            exec_ins = MagicMock()
            exec_ins.data = [{
                "id": "session-cloned-uuid-temp",
                "user_id": test_user_id,
                "title": "Đề thi gốc (Bản sao)",
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

            # Delete call for cleanup
            def record_delete_call():
                eq_mock = MagicMock()
                def execute_delete(col, val):
                    if col == "id":
                        deleted_session_ids.append(val)
                    return MagicMock()
                eq_mock.eq.side_effect = lambda col, val: MagicMock(execute=lambda: (deleted_session_ids.append(val), MagicMock())[1])
                return eq_mock

            mock_t.delete.side_effect = record_delete_call

        elif table_name == "source_questions":
            # Return 1 source question to copy
            exec_sq = MagicMock()
            exec_sq.data = [{
                "id": "sq-1",
                "session_id": "session-orig",
                "question_no": 1,
                "raw_content": "Câu 1: ...",
            }]
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_sq

            # Failed insert: returns empty data
            exec_ins_sq = MagicMock()
            exec_ins_sq.data = []
            mock_t.insert.return_value.execute.return_value = exec_ins_sq

        return mock_t

    mock_db.table.side_effect = table_router

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post("/api/sessions/session-orig/clone", headers=auth_headers)

    assert response.status_code == 500
    assert "Failed to clone" in response.json()["detail"]
    assert "session-cloned-uuid-temp" in deleted_session_ids


def test_clone_session_fails_and_cleans_up_on_db_exception(
    client, mock_auth_user, test_user_id, auth_headers
):
    """POST /api/sessions/{id}/clone triggers cleanup when DB raises unexpected exception during copying."""
    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
    deleted_session_ids = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-orig",
                "user_id": test_user_id,
                "title": "Đề thi gốc",
                "subject": "Toán",
                "grade": 12,
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s

            exec_ins = MagicMock()
            exec_ins.data = [{
                "id": "session-cloned-crash-uuid",
                "user_id": test_user_id,
                "title": "Đề thi gốc (Bản sao)",
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

            mock_t.delete.side_effect = lambda: MagicMock(
                eq=lambda col, val: MagicMock(
                    execute=lambda: (deleted_session_ids.append(val), MagicMock())[1]
                )
            )

        elif table_name == "source_questions":
            mock_t.select.return_value.eq.return_value.order.return_value.execute.side_effect = RuntimeError(
                "Connection broken"
            )

        return mock_t

    mock_db.table.side_effect = table_router

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post("/api/sessions/session-orig/clone", headers=auth_headers)

    assert response.status_code == 500
    assert "Failed to clone" in response.json()["detail"]
    assert "session-cloned-crash-uuid" in deleted_session_ids


def test_get_session_detail_invalid_blueprint_modes_structure(
    client, mock_auth_user, test_user_id, auth_headers
):
    """GET /api/sessions/{id} returns is_ready=False and supported_modes=None when variation_modes is an object (F02/F09)."""
    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-invalid-modes",
                "user_id": test_user_id,
                "title": "Đề kiểm tra",
                "subject": "Toán",
                "grade": 12,
                "status": "blueprinted",
                "gemini_call_count": 0,
                "retry_count": 0,
                "approved_at": None,
                "created_at": "2026-10-18T10:00:00Z",
                "updated_at": "2026-10-18T10:00:00Z",
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s
        elif table_name == "source_questions":
            exec_q = MagicMock()
            exec_q.data = [{"id": "q-1", "session_id": "session-invalid-modes", "question_no": 1}]
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_q
        elif table_name == "exam_versions":
            exec_v = MagicMock()
            exec_v.data = []
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_v
        elif table_name == "generation_configs":
            exec_cfg = MagicMock()
            exec_cfg.data = []
            mock_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = exec_cfg
        elif table_name == "question_blueprints":
            exec_bp = MagicMock()
            # Blueprint with invalid variation_modes structure (object instead of array)
            exec_bp.data = [{
                "id": "bp-1",
                "source_question_id": "q-1",
                "confirmed_at": "2026-11-01T00:00:00Z",
                "is_fallback": False,
                "variation_modes": {"NUMERICAL": True},
            }]
            mock_t.select.return_value.in_.return_value.execute.return_value = exec_bp
        return mock_t

    mock_db.table.side_effect = table_router
    preview_session = table_router("exam_sessions").select().eq().execute().data[0]
    preview_questions = table_router("source_questions").select().eq().order().execute().data
    configure_session_detail_rpcs(
        mock_db, preview_session, preview_questions,
        generation_snapshot={"ready": False, "reason": "NO_CONFIRMATION"},
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions/session-invalid-modes", headers=auth_headers)

    assert response.status_code == 200
    bp_summary = response.json()["blueprint_summary"]
    assert bp_summary is not None
    assert bp_summary["is_ready"] is False
    assert bp_summary["supported_modes"] is None


def test_clone_session_default_title_and_subject_encoding(
    client, mock_auth_user, test_user_id, auth_headers
):
    """POST /api/sessions/{id}/clone uses correct Vietnamese encoding for default title and fallback subject (F08/F09)."""
    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
    inserted_records = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-orig",
                "user_id": test_user_id,
                "title": "Đề toán 12",
                "subject": None,  # Test fallback to default 'Toán' when subject is absent/None
                "grade": 12,
                "status": "draft",
                "gemini_call_count": 0,
                "retry_count": 0,
                "approved_at": None,
                "created_at": "2026-10-18T10:00:00Z",
                "updated_at": "2026-10-18T10:00:00Z",
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s

            def capture_insert(data):
                inserted_records.append(data)
                exec_ins = MagicMock()
                exec_ins.data = [{
                    **data,
                    "id": "session-cloned-new",
                    "status": "draft",
                    "gemini_call_count": 0,
                    "retry_count": 0,
                    "approved_at": None,
                    "created_at": "2026-10-18T12:00:00Z",
                    "updated_at": "2026-10-18T12:00:00Z",
                }]
                m = MagicMock()
                m.execute.return_value = exec_ins
                return m

            mock_t.insert.side_effect = capture_insert
        elif table_name == "source_questions":
            exec_q = MagicMock()
            exec_q.data = []
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_q
        return mock_t

    mock_db.table.side_effect = table_router

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post("/api/sessions/session-orig/clone", json={}, headers=auth_headers)

    assert response.status_code == 201
    assert len(inserted_records) == 1
    assert inserted_records[0]["title"] == "Đề toán 12 (Bản sao)"
    assert inserted_records[0]["subject"] == "Toán"
    data = response.json()
    assert data["title"] == "Đề toán 12 (Bản sao)"
    assert data["subject"] == "Toán"



def test_get_session_detail_tc_ready_02_original_clone(
    client, mock_auth_user, test_user_id, auth_headers
):
    """TC-READY-02: Confirmed blueprints with no common variation modes yield is_ready=True, supported_modes=[]."""
    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-clone-ready",
                "user_id": test_user_id,
                "title": "Session Clone Ready",
                "subject": "Toán",
                "grade": 12,
                "status": "blueprinted",
                "gemini_call_count": 0,
                "retry_count": 0,
                "approved_at": None,
                "created_at": "2026-11-01T00:00:00Z",
                "updated_at": "2026-11-01T00:00:00Z",
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s
        elif table_name == "source_questions":
            exec_q = MagicMock()
            exec_q.data = [
                {"id": "q-1", "session_id": "session-clone-ready", "question_no": 1},
                {"id": "q-2", "session_id": "session-clone-ready", "question_no": 2},
            ]
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_q
        elif table_name == "exam_versions":
            exec_v = MagicMock()
            exec_v.data = []
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_v
        elif table_name == "generation_configs":
            exec_c = MagicMock()
            exec_c.data = []
            mock_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = exec_c
        elif table_name == "question_blueprints":
            exec_bp = MagicMock()
            # q-1 supports NONE, q-2 supports NONE (or disjoint modes) -> no common variable mode
            exec_bp.data = [
                {
                    "id": "bp-1",
                    "source_question_id": "q-1",
                    "confirmed_at": "2026-11-01T00:00:00Z",
                    "is_fallback": False,
                    "variation_modes": ["NONE"],
                },
                {
                    "id": "bp-2",
                    "source_question_id": "q-2",
                    "confirmed_at": "2026-11-01T00:00:00Z",
                    "is_fallback": False,
                    "variation_modes": ["NONE"],
                },
            ]
            mock_t.select.return_value.in_.return_value.execute.return_value = exec_bp
        return mock_t

    mock_db.table.side_effect = table_router
    preview_session = table_router("exam_sessions").select().eq().execute().data[0]
    preview_questions = table_router("source_questions").select().eq().order().execute().data
    configure_session_detail_rpcs(
        mock_db, preview_session, preview_questions,
        generation_snapshot={"ready": False, "reason": "NO_CONFIRMATION"},
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions/session-clone-ready", headers=auth_headers)

    assert response.status_code == 200
    bp_summary = response.json()["blueprint_summary"]
    assert bp_summary is not None
    assert bp_summary["is_ready"] is True
    assert bp_summary["supported_modes"] == []


def test_get_session_detail_tc_ready_03_available_and_unavailable_modes(
    client, mock_auth_user, test_user_id, auth_headers
):
    """TC-READY-03: Confirmed blueprints classify supported modes into available (100% sources) and unavailable."""
    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-modes-ready",
                "user_id": test_user_id,
                "title": "Session Modes Ready",
                "subject": "Toán",
                "grade": 12,
                "status": "blueprinted",
                "gemini_call_count": 0,
                "retry_count": 0,
                "approved_at": None,
                "created_at": "2026-11-01T00:00:00Z",
                "updated_at": "2026-11-01T00:00:00Z",
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s
        elif table_name == "source_questions":
            exec_q = MagicMock()
            exec_q.data = [
                {"id": "q-1", "session_id": "session-modes-ready", "question_no": 1},
                {"id": "q-2", "session_id": "session-modes-ready", "question_no": 2},
            ]
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_q
        elif table_name == "exam_versions":
            exec_v = MagicMock()
            exec_v.data = []
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_v
        elif table_name == "generation_configs":
            exec_c = MagicMock()
            exec_c.data = []
            mock_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = exec_c
        elif table_name == "question_blueprints":
            exec_bp = MagicMock()
            # q-1 has NUMERICAL and context_swap; q-2 only has NUMERICAL
            exec_bp.data = [
                {
                    "id": "bp-1",
                    "source_question_id": "q-1",
                    "confirmed_at": "2026-11-01T00:00:00Z",
                    "is_fallback": False,
                    "variation_modes": ["NUMERICAL", "context_swap"],
                },
                {
                    "id": "bp-2",
                    "source_question_id": "q-2",
                    "confirmed_at": "2026-11-01T00:00:00Z",
                    "is_fallback": False,
                    "variation_modes": ["NUMERICAL"],
                },
            ]
            mock_t.select.return_value.in_.return_value.execute.return_value = exec_bp
        return mock_t

    mock_db.table.side_effect = table_router
    preview_session = table_router("exam_sessions").select().eq().execute().data[0]
    preview_questions = table_router("source_questions").select().eq().order().execute().data
    configure_session_detail_rpcs(
        mock_db, preview_session, preview_questions,
        generation_snapshot={"ready": False, "reason": "NO_CONFIRMATION"},
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions/session-modes-ready", headers=auth_headers)

    assert response.status_code == 200
    bp_summary = response.json()["blueprint_summary"]
    assert bp_summary is not None
    assert bp_summary["is_ready"] is True
    modes = bp_summary["supported_modes"]
    assert isinstance(modes, list)
    assert len(modes) == 2

    # Available mode: NUMERICAL (supported by 2/2)
    num_mode = next(m for m in modes if m["id"] == "NUMERICAL")
    assert num_mode["is_available"] is True
    assert num_mode["question_count"] == 2
    assert "unavailable_reason" not in num_mode

    # Unavailable mode: context_swap (supported by 1/2)
    ctx_mode = next(m for m in modes if m["id"] == "context_swap")
    assert ctx_mode["is_available"] is False
    assert ctx_mode["question_count"] == 1
    assert "Chỉ hỗ trợ 1/2 câu trong đề" in ctx_mode["unavailable_reason"]


def test_get_session_detail_canonical_readiness(
    client, mock_auth_user, test_user_id, auth_headers
):
    """Canonical session without legacy blueprints correctly reports ready and supported_modes."""
    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "exam_sessions":
            exec_s = MagicMock()
            exec_s.data = [{
                "id": "session-canonical-only",
                "user_id": test_user_id,
                "title": "Canonical Session",
                "subject": "Toán",
                "grade": 12,
                "status": "blueprinted",
                "gemini_call_count": 0,
                "retry_count": 0,
                "approved_at": None,
                "created_at": "2026-11-01T00:00:00Z",
                "updated_at": "2026-11-01T00:00:00Z",
            }]
            mock_t.select.return_value.eq.return_value.execute.return_value = exec_s
        elif table_name == "source_questions":
            exec_q = MagicMock()
            exec_q.data = [
                {"id": "q-1", "session_id": "session-canonical-only", "question_no": 1},
                {"id": "q-2", "session_id": "session-canonical-only", "question_no": 2},
            ]
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_q
        elif table_name == "exam_versions":
            exec_v = MagicMock()
            exec_v.data = []
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = exec_v
        elif table_name == "generation_configs":
            exec_c = MagicMock()
            exec_c.data = []
            mock_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = exec_c
        return mock_t

    mock_db.table.side_effect = table_router

    # RPC get_generation_source_snapshot returns ready=True with 2 confirmed canonical blueprints
    mock_rpc = MagicMock()
    mock_rpc.data = {
        "session_id": "session-canonical-only",
        "ready": True,
        "confirmed_sources": [
            {
                "source_question_id": "q-1",
                "canonical_blueprint": {
                    "requirement": {
                        "variation_policy": {
                            "allowed_transformations": [{"dimension": "values"}]
                        }
                    }
                }
            },
            {
                "source_question_id": "q-2",
                "canonical_blueprint": {
                    "requirement": {
                        "variation_policy": {
                            "allowed_transformations": [{"dimension": "values"}]
                        }
                    }
                }
            }
        ]
    }
    preview_session = table_router("exam_sessions").select().eq().execute().data[0]
    preview_questions = table_router("source_questions").select().eq().order().execute().data
    configure_session_detail_rpcs(
        mock_db, preview_session, preview_questions,
        generation_snapshot=mock_rpc.data,
    )

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.get("/api/sessions/session-canonical-only", headers=auth_headers)

    assert response.status_code == 200
    bp_summary = response.json()["blueprint_summary"]
    assert bp_summary is not None
    assert bp_summary["is_ready"] is True
    assert bp_summary["confirmed_blueprints"] == 2
    assert {mode["id"] for mode in bp_summary["supported_modes"]} == {"NUMERICAL", "parameter_variation"}
    assert all(mode["is_available"] for mode in bp_summary["supported_modes"])


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot", [
    {"ready": False, "reason": "CANONICAL_BLUEPRINTS_INCOMPLETE"},
    {"ready": False, "reason": "ARTIFACT_STALE"},
    {"ready": True, "confirmed_sources": [{"source_question_id": "q", "canonical_blueprint": {}}]},
    ["malformed"],
    None,
    RuntimeError("RPC unavailable"),
])
async def test_canonical_unavailable_never_falls_back_to_legacy(snapshot):
    from app.api.routes.sessions import get_session_detail
    from app.models.schemas import CurrentUser

    session = {
        "id": "s", "user_id": "u", "title": "Session", "subject": "Toán", "grade": 12,
        "status": "blueprinted", "created_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z",
    }
    mock_db = MagicMock()
    tables = []

    def table(name):
        tables.append(name)
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.execute.return_value.data = {
            "exam_sessions": [session], "source_questions": [{"id": "q", "question_no": 1}],
            "exam_versions": [], "generation_configs": [],
        }[name]
        return query

    mock_db.table.side_effect = table
    configure_session_detail_rpcs(
        mock_db, session,
        [{"id": "q", "session_id": "s", "question_no": 1}],
        generation_snapshot=None if isinstance(snapshot, Exception) else snapshot,
        generation_error=snapshot if isinstance(snapshot, Exception) else None,
    )
    with patch("app.api.routes.sessions.assert_ownership"):
        response = await get_session_detail("s", CurrentUser(id="u", email="owner@example.invalid", access_token="fixture-token"), mock_db)
    assert response.blueprint_summary["is_ready"] is False
    assert response.blueprint_summary["supported_modes"] is None
    assert "question_blueprints" not in tables


@pytest.mark.asyncio
async def test_legacy_whitespace_id_does_not_publish_a_selectable_alias():
    from app.api.routes.sessions import get_session_detail
    from app.models.schemas import CurrentUser

    mock_db = MagicMock()
    mock_db.rpc.return_value.execute.return_value.data = {"ready": False, "reason": "NO_CONFIRMATION"}
    session = {
        "id": "s", "user_id": "u", "title": "Session", "subject": "Toán", "grade": 12,
        "status": "blueprinted", "created_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z",
    }

    def table(name):
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.in_.return_value = query
        query.execute.return_value.data = {
            "exam_sessions": [session],
            "source_questions": [{"id": "q1"}, {"id": "q2"}],
            "exam_versions": [], "generation_configs": [],
            "question_blueprints": [
                {"source_question_id": "q1", "confirmed_at": "confirmed", "variation_modes": [" NUMERICAL "]},
                {"source_question_id": "q2", "confirmed_at": "confirmed", "variation_modes": ["NUMERICAL"]},
            ],
        }[name]
        return query

    mock_db.table.side_effect = table
    configure_session_detail_rpcs(
        mock_db, session,
        [{"id": "q1", "session_id": "s", "question_no": 1},
         {"id": "q2", "session_id": "s", "question_no": 2}],
        generation_snapshot={"ready": False, "reason": "NO_CONFIRMATION"},
    )
    with patch("app.api.routes.sessions.assert_ownership"):
        response = await get_session_detail("s", CurrentUser(id="u", email="owner@example.invalid", access_token="fixture-token"), mock_db)
    assert response.blueprint_summary["is_ready"]
    assert response.blueprint_summary["supported_modes"] == [{
        "id": "NUMERICAL", "label": "Thay đổi số liệu", "question_count": 1, "is_available": False,
        "unavailable_reason": "Chỉ hỗ trợ 1/2 câu trong đề (yêu cầu toàn bộ câu hỏi hỗ trợ).",
    }]


def test_update_ordering_preferences_success(client, mock_auth_user, test_user_id, auth_headers):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": test_user_id, "status": "reviewed"}
    ]
    mock_db.rpc.return_value.execute.return_value.data = {
        "success": True,
        "session_id": "session-1",
        "status": "reviewed",
        "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
    }
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        res = client.patch(
            "/api/sessions/session-1/ordering-preferences",
            json={"shuffle_questions": True, "shuffle_options": False},
            headers=auth_headers,
        )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["ordering_preferences"] == {"shuffle_questions": True, "shuffle_options": False}


def test_update_ordering_preferences_locked(client, mock_auth_user, test_user_id, auth_headers):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": test_user_id, "status": "draft"}
    ]
    mock_db.rpc.return_value.execute.side_effect = Exception("ERR_CONFIG_CONFLICT: preferences locked (55006)")
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        res = client.patch(
            "/api/sessions/session-1/ordering-preferences",
            json={"shuffle_questions": True, "shuffle_options": False},
            headers=auth_headers,
        )
    assert res.status_code == 423


@pytest.mark.parametrize(
    "invalid_val",
    ["true", "false", "yes", "no", 0, 1, None, [], {}],
)
@pytest.mark.parametrize("field_name", ["shuffle_questions", "shuffle_options"])
def test_update_ordering_preferences_strict_bool_rejected(
    client, mock_auth_user, test_user_id, auth_headers, invalid_val, field_name
):
    mock_db = MagicMock()
    payload = {"shuffle_questions": True, "shuffle_options": False}
    payload[field_name] = invalid_val

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        for route in [
            "/api/sessions/session-1/ordering-preferences",
            "/api/sessions/session-1/preferences",
        ]:
            res = client.patch(route, json=payload, headers=auth_headers)
            assert res.status_code == 422, f"Expected 422 for {field_name}={invalid_val!r}, got {res.status_code}"
            assert mock_db.rpc.call_count == 0


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"shuffle_questions": True},  # missing shuffle_options
        {"shuffle_options": False},  # missing shuffle_questions
        {},  # empty payload
        [],  # root must be an object
        None,  # JSON null root
        {"shuffle_questions": True, "shuffle_options": False, "extra_field": True},  # extra field
    ],
)
@pytest.mark.parametrize("route", ["ordering-preferences", "preferences"])
def test_update_ordering_preferences_schema_violations(
    client, mock_auth_user, test_user_id, auth_headers, invalid_payload, route
):
    mock_db = MagicMock()
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        res = client.patch(
            f"/api/sessions/session-1/{route}",
            content=json.dumps(invalid_payload),
            headers={**auth_headers, "Content-Type": "application/json"},
        )
        assert res.status_code == 422
        assert mock_db.rpc.call_count == 0


@pytest.mark.parametrize("route", ["ordering-preferences", "preferences"])
def test_update_ordering_preferences_unauthenticated(client, route):
    with patch("app.api.dependencies.get_authenticated_client") as db_factory:
        res = client.patch(
            f"/api/sessions/session-1/{route}",
            json={"shuffle_questions": False, "shuffle_options": False},
        )
    assert res.status_code == 401
    db_factory.assert_not_called()


@pytest.mark.parametrize("route", ["ordering-preferences", "preferences"])
@pytest.mark.parametrize("rows,status", [([], 404), ([{"user_id": "foreign-owner"}], 403)])
def test_update_ordering_preferences_ownership(
    client, mock_auth_user, auth_headers, route, rows, status
):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = rows
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        res = client.patch(
            f"/api/sessions/session-1/{route}",
            json={"shuffle_questions": False, "shuffle_options": False},
            headers=auth_headers,
        )
    assert res.status_code == status
    mock_db.rpc.assert_not_called()


def test_update_ordering_preferences_openapi_alias_hidden(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "patch" in paths["/api/sessions/{session_id}/ordering-preferences"]
    assert "/api/sessions/{session_id}/preferences" not in paths


@pytest.mark.parametrize(
    ("q", "o"),
    [
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    ],
)
@pytest.mark.parametrize(
    "route_template",
    [
        "/api/sessions/session-1/ordering-preferences",
        "/api/sessions/session-1/preferences",
    ],
)
def test_update_ordering_preferences_all_valid_combinations(
    client, mock_auth_user, test_user_id, auth_headers, q, o, route_template
):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": test_user_id, "status": "reviewed"}
    ]
    mock_db.rpc.return_value.execute.return_value.data = {
        "success": True,
        "session_id": "session-1",
        "status": "reviewed",
        "ordering_preferences": {"shuffle_questions": q, "shuffle_options": o},
    }
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        res = client.patch(
            route_template,
            json={"shuffle_questions": q, "shuffle_options": o},
            headers=auth_headers,
        )
    assert res.status_code == 200, res.text
    assert res.json() == {
        "success": True,
        "session_id": "session-1",
        "status": "reviewed",
        "ordering_preferences": {"shuffle_questions": q, "shuffle_options": o},
    }


@pytest.mark.parametrize(
    "bad_receipt",
    [
        None,
        [],
        {},
        "not-a-dict",
        123,
        # Missing or invalid success
        {
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
        },
        {
            "success": False,
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
        },
        {
            "success": "true",
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
        },
        # Missing or invalid session_id
        {
            "success": True,
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
        },
        {
            "success": True,
            "session_id": "different-session-uuid",
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
        },
        {
            "success": True,
            "session_id": 12345,
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
        },
        # Missing or invalid status
        {
            "success": True,
            "session_id": "session-1",
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
        },
        {
            "success": True,
            "session_id": "session-1",
            "status": "draft",
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
        },
        # Missing or invalid ordering_preferences
        {
            "success": True,
            "session_id": "session-1",
            "status": "reviewed",
        },
        {
            "success": True,
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": None,
        },
        {
            "success": True,
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": [],
        },
        {
            "success": True,
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": True},
        },
        {
            "success": True,
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": {
                "shuffle_questions": True,
                "shuffle_options": False,
                "extra_key": True,
            },
        },
        {
            "success": True,
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": 1, "shuffle_options": 0},
        },
        {
            "success": True,
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": "true", "shuffle_options": "false"},
        },
        # Receipt preferences do not match requested preferences
        {
            "success": True,
            "session_id": "session-1",
            "status": "reviewed",
            "ordering_preferences": {"shuffle_questions": False, "shuffle_options": True},
        },
    ],
)
@pytest.mark.parametrize("route", ["ordering-preferences", "preferences"])
def test_update_ordering_preferences_fail_closed_on_bad_receipt(
    client, mock_auth_user, test_user_id, auth_headers, bad_receipt, route
):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": test_user_id, "status": "reviewed"}
    ]
    mock_db.rpc.return_value.execute.return_value.data = bad_receipt
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        res = client.patch(
            f"/api/sessions/session-1/{route}",
            json={"shuffle_questions": True, "shuffle_options": False},
            headers=auth_headers,
        )
    assert res.status_code == 503
    data = res.json()
    assert data["error_code"] == "ERR_PREFERENCES_UPDATE_FAILED"


@pytest.mark.parametrize(
    ("db_exc", "expected_status", "expected_error_code"),
    [
        (Exception("invalid ordering preferences: (22023)"), 422, "ERR_CONFIG_CONFLICT"),
        (Exception("Session not found (P0002)"), 404, None),
        (Exception("Access denied (42501)"), 403, None),
        (Exception("Unexpected database timeout"), 503, "ERR_PREFERENCES_UPDATE_FAILED"),
    ],
)
def test_update_ordering_preferences_db_exceptions(
    client, mock_auth_user, test_user_id, auth_headers, db_exc, expected_status, expected_error_code
):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": test_user_id, "status": "reviewed"}
    ]
    mock_db.rpc.return_value.execute.side_effect = db_exc
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        res = client.patch(
            "/api/sessions/session-1/ordering-preferences",
            json={"shuffle_questions": True, "shuffle_options": False},
            headers=auth_headers,
        )
    assert res.status_code == expected_status
    if expected_error_code:
        assert res.json()["error_code"] == expected_error_code

"""Unit tests for JWT authentication dependency and /api/users/me endpoint."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.dependencies import get_current_user
from app.models.schemas import CurrentUser


@pytest.mark.asyncio
async def test_get_current_user_missing_header(dummy_request):
    """Raise 401 when Authorization header is absent."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request=dummy_request, authorization=None)
    assert exc_info.value.status_code == 401
    assert "Missing authorization header" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_invalid_format(dummy_request):
    """Raise 401 when Authorization header is not 'Bearer <token>'."""
    for invalid_header in ["Token 123", "Bearer", "Bearer  ", "Basic 123", "JustAToken"]:
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=dummy_request, authorization=invalid_header)
        assert exc_info.value.status_code == 401
        assert "Invalid authorization header format" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_valid_token(dummy_request, mock_user_response, test_user_id):
    """Return CurrentUser when token is valid and populate request.state.authenticated_user_id."""
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = mock_user_response

    with patch("app.api.dependencies.get_supabase_client", return_value=mock_supabase):
        user = await get_current_user(request=dummy_request, authorization="Bearer valid-jwt-token")

    assert isinstance(user, CurrentUser)
    assert user.id == test_user_id
    assert user.email == "teacher@school.edu.vn"
    assert user.name == "Thầy Nguyễn Văn A"
    assert user.access_token == "valid-jwt-token"
    assert getattr(dummy_request.state, "authenticated_user_id", None) == test_user_id
    mock_supabase.auth.get_user.assert_called_once_with("valid-jwt-token")


@pytest.mark.asyncio
async def test_get_current_user_expired_or_invalid_token(dummy_request):
    """Raise 401 when Supabase Auth rejects the token, with sanitized error message."""
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("JWT expired or signature invalid")

    with patch("app.api.dependencies.get_supabase_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=dummy_request, authorization="Bearer expired-jwt-token")

    assert exc_info.value.status_code == 401
    assert "Invalid or expired token" in exc_info.value.detail
    # Must not leak raw exception detail
    assert "JWT expired or signature invalid" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_null_user_response(dummy_request):
    """Raise 401 when Supabase Auth returns empty user."""
    mock_supabase = MagicMock()
    empty_response = MagicMock()
    empty_response.user = None
    mock_supabase.auth.get_user.return_value = empty_response

    with patch("app.api.dependencies.get_supabase_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=dummy_request, authorization="Bearer empty-user-jwt")

    assert exc_info.value.status_code == 401
    assert "Invalid or expired token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_configuration_error(dummy_request):
    """Raise 500 when Supabase client is misconfigured (e.g. missing env vars)."""
    with patch(
        "app.api.dependencies.get_supabase_client",
        side_effect=RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be configured"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=dummy_request, authorization="Bearer valid-token")

    assert exc_info.value.status_code == 500
    assert "Authentication service is misconfigured" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_network_error(dummy_request):
    """Raise 503 when network connection to Supabase Auth fails."""
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = httpx.ConnectError("Failed to connect to Supabase")

    with patch("app.api.dependencies.get_supabase_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=dummy_request, authorization="Bearer valid-token")

    assert exc_info.value.status_code == 503
    assert "Authentication service temporarily unavailable" in exc_info.value.detail


def test_users_me_unauthorized(client):
    """Calling GET /api/users/me without token returns 401."""
    response = client.get("/api/users/me")
    assert response.status_code == 401


def test_users_me_success_with_db_record(client, mock_user_response, test_user_id):
    """Calling GET /api/users/me with valid token returns user profile from public.users."""
    mock_supabase_auth = MagicMock()
    mock_supabase_auth.auth.get_user.return_value = mock_user_response

    mock_db_client = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_execute = MagicMock()

    mock_execute.data = [{
        "id": test_user_id,
        "email": "teacher@school.edu.vn",
        "name": "Thầy Nguyễn Văn A",
        "created_at": "2026-10-18T10:00:00Z",
    }]
    mock_eq.execute.return_value = mock_execute
    mock_select.eq.return_value = mock_eq
    mock_db_client.table.return_value.select.return_value = mock_select

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_supabase_auth),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db_client),
    ):
        response = client.get(
            "/api/users/me",
            headers={"Authorization": "Bearer valid-jwt-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user_id
    assert data["email"] == "teacher@school.edu.vn"
    assert data["name"] == "Thầy Nguyễn Văn A"
    assert data["created_at"] == "2026-10-18T10:00:00Z"


def test_users_me_fallback_when_db_record_absent(client, mock_user_response, test_user_id):
    """Calling GET /api/users/me falls back to JWT claims if public.users row is not found."""
    mock_supabase_auth = MagicMock()
    mock_supabase_auth.auth.get_user.return_value = mock_user_response

    mock_db_client = MagicMock()
    mock_execute = MagicMock()
    mock_execute.data = []  # No DB row yet
    mock_db_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_execute

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_supabase_auth),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db_client),
    ):
        response = client.get(
            "/api/users/me",
            headers={"Authorization": "Bearer valid-jwt-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user_id
    assert data["email"] == "teacher@school.edu.vn"
    assert data["name"] == "Thầy Nguyễn Văn A"
    assert data["created_at"] is None


@pytest.mark.asyncio
async def test_get_current_user_sets_authenticated_user_id_on_request_state(
    mock_user_response, test_user_id
):
    """Ensure authenticated_user_id is populated on request.state for rate limiting (TASK-005 contract)."""
    from types import SimpleNamespace

    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = mock_user_response
    mock_request = SimpleNamespace(state=SimpleNamespace())

    with patch("app.api.dependencies.get_supabase_client", return_value=mock_supabase):
        user = await get_current_user(request=mock_request, authorization="Bearer valid-jwt-token")

    assert user.id == test_user_id
    assert getattr(mock_request.state, "authenticated_user_id", None) == test_user_id

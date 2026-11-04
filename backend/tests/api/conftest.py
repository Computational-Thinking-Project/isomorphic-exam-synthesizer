"""Fixtures and test helpers for API tests."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app
from app.models.schemas import CurrentUser


@pytest.fixture
def dummy_request() -> Request:
    """Create a dummy Starlette Request object for direct dependency testing."""
    return Request({"type": "http", "headers": []})



@pytest.fixture
def test_user_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def mock_supabase_user(test_user_id: str):
    """Mock Supabase Auth User object."""
    user = MagicMock()
    user.id = test_user_id
    user.email = "teacher@school.edu.vn"
    user.user_metadata = {"full_name": "Thầy Nguyễn Văn A"}
    return user


@pytest.fixture
def mock_user_response(mock_supabase_user):
    """Mock response from supabase.auth.get_user()."""
    response = MagicMock()
    response.user = mock_supabase_user
    return response


@pytest.fixture
def current_user(test_user_id: str) -> CurrentUser:
    """Standard authenticated CurrentUser instance."""
    return CurrentUser(
        id=test_user_id,
        email="teacher@school.edu.vn",
        name="Thầy Nguyễn Văn A",
        access_token="mock-valid-jwt-token-xyz",
    )


@pytest.fixture
def client() -> TestClient:
    """TestClient for FastAPI app."""
    if hasattr(app.state, "limiter") and hasattr(app.state.limiter, "_storage"):
        app.state.limiter._storage.reset()
    return TestClient(app)

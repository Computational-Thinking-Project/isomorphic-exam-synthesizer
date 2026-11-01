"""API Endpoint Tests for Review Lifecycle (TASK-301).

Tests all 4 endpoints:
- POST /api/sessions/{session_id}/questions/{version_question_id}/accept
- POST /api/sessions/{session_id}/questions/{version_question_id}/reject
- POST /api/sessions/{session_id}/questions/{version_question_id}/revert
- GET  /api/sessions/{session_id}/review/progress
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.main import app
from app.models.schemas import (
    CurrentUser,
    RegeneratedQuestionResponse,
    ReviewActionResponse,
    ReviewDomainException,
    ReviewProgressResponse,
)
from app.services.review.service import ReviewService

MOCK_SESSION_ID = "00000000-0000-0000-0000-000000000001"
MOCK_QUESTION_ID = "11111111-1111-1111-1111-111111111111"
MOCK_USER_ID = "user-123456"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer mock-valid-jwt-token"}


@pytest.fixture
def mock_current_user() -> CurrentUser:
    return CurrentUser(
        id=MOCK_USER_ID,
        email="teacher@school.edu.vn",
        name="Thầy Nguyễn Văn A",
        access_token="mock-valid-jwt-token",
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# Authentication & Ownership Guard Tests
# ==============================================================================


def test_review_endpoints_unauthenticated(client: TestClient):
    """Calling any review endpoint without Authorization header returns 401."""
    # Ensure no dependency overrides
    app.dependency_overrides.clear()

    res_accept = client.post(f"/api/sessions/{MOCK_SESSION_ID}/questions/{MOCK_QUESTION_ID}/accept")
    assert res_accept.status_code == 401

    res_reject = client.post(f"/api/sessions/{MOCK_SESSION_ID}/questions/{MOCK_QUESTION_ID}/reject")
    assert res_reject.status_code == 401

    res_revert = client.post(f"/api/sessions/{MOCK_SESSION_ID}/questions/{MOCK_QUESTION_ID}/revert")
    assert res_revert.status_code == 401

    res_progress = client.get(f"/api/sessions/{MOCK_SESSION_ID}/review/progress")
    assert res_progress.status_code == 401


# ==============================================================================
# Functional Success & Domain Exception Tests
# ==============================================================================


def test_accept_question_success(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """POST /accept returns 200 with ReviewActionResponse."""
    expected_resp = ReviewActionResponse(
        question_id=MOCK_QUESTION_ID,
        session_id=MOCK_SESSION_ID,
        status="approved",
        is_current=True,
        is_reverted=False,
        updated_at="2026-10-29T12:00:00Z",
    )

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "accept_question",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.post(
                f"/api/sessions/{MOCK_SESSION_ID}/questions/{MOCK_QUESTION_ID}/accept",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    assert data["question_id"] == MOCK_QUESTION_ID
    assert data["status"] == "approved"
    assert data["is_current"] is True


def test_reject_question_success(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """POST /reject returns 200 with RegeneratedQuestionResponse."""
    expected_resp = RegeneratedQuestionResponse(
        question_id="22222222-2222-2222-2222-222222222222",
        regenerated_from_id=MOCK_QUESTION_ID,
        status="pending_review",
        content="Câu hỏi mới sau sinh lại",
        options=["A. 1", "B. 2", "C. 3", "D. 4"],
        correct_key="B",
        solution_md="Lời giải chi tiết mới",
        validation_report={"is_valid": True},
    )

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "reject_question",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.post(
                f"/api/sessions/{MOCK_SESSION_ID}/questions/{MOCK_QUESTION_ID}/reject",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    assert data["question_id"] == "22222222-2222-2222-2222-222222222222"
    assert data["regenerated_from_id"] == MOCK_QUESTION_ID
    assert data["status"] == "pending_review"


def test_reject_question_quota_exhausted_returns_429(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """POST /reject returns 429 when quota is exhausted."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "reject_question",
                new_callable=AsyncMock,
                side_effect=ReviewDomainException(
                    429, "ERR_REVIEW_QUOTA_EXHAUSTED", "Quota exceeded"
                ),
            ),
        ):
            res = client.post(
                f"/api/sessions/{MOCK_SESSION_ID}/questions/{MOCK_QUESTION_ID}/reject",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 429
    data = res.json()
    assert data["error_code"] == "ERR_REVIEW_QUOTA_EXHAUSTED"
    assert data["detail"] == "Quota exceeded"


def test_revert_question_success(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """POST /revert returns 200 with reverted status."""
    expected_resp = ReviewActionResponse(
        question_id=MOCK_QUESTION_ID,
        session_id=MOCK_SESSION_ID,
        status="approved",
        is_current=True,
        is_reverted=True,
        updated_at="2026-10-29T12:00:00Z",
    )

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "revert_question",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.post(
                f"/api/sessions/{MOCK_SESSION_ID}/questions/{MOCK_QUESTION_ID}/revert",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    assert data["is_reverted"] is True
    assert data["status"] == "approved"


def test_get_review_progress_success(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """GET /review/progress returns 200 with ReviewProgressResponse."""
    expected_resp = ReviewProgressResponse(
        session_id=MOCK_SESSION_ID,
        required_count=6,
        current_count=6,
        approved_count=6,
        regenerating_count=0,
        unapproved_question_ids=[],
        is_complete=True,
        can_finalize=True,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "get_progress",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/progress",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == MOCK_SESSION_ID
    assert data["required_count"] == 6
    assert data["is_complete"] is True
    assert data["can_finalize"] is True

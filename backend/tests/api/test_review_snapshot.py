"""API Endpoint Tests for Review Snapshot (W4-MVP-03).

Tests GET /api/sessions/{session_id}/review/snapshot:
- Authentication & Authorization (401 without JWT, 404/403 on ownership denial)
- Parameter validation (400 on malformed UUID)
- Golden complete 3x2 matrix (200 OK, Cache-Control: no-store, typed schema, full slot invariants)
- Partial generation matrix (200 OK, read_only=true, missing slot candidate=null)
- Candidate provenance & validation resolution (regenerated, original_clone, ai_generated, unavailable)
- Domain exceptions & HTTP status mapping (409 state conflict / post-shuffle, 423 locked, 503 invariant/RPC failure)
- Stable ordering and deterministic response
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.main import app
from app.models.schemas import (
    CurrentUser,
    ReviewDomainException,
    ReviewSnapshotCandidate,
    ReviewSnapshotResponse,
)
from app.services.review.service import ReviewService

MOCK_SESSION_ID = "10000000-0000-0000-0000-000000000001"
MOCK_USER_ID = "00000000-0000-0000-0000-000000000001"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "review_snapshot"


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


def _load_fixture(name: str) -> dict:
    fixture_path = FIXTURES_DIR / name
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# Authentication, Authorization & Ownership Tests
# ==============================================================================


def test_review_snapshot_unauthenticated(client: TestClient):
    """Calling GET snapshot without Authorization header returns 401."""
    app.dependency_overrides.clear()
    res = client.get(f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot")
    assert res.status_code == 401


def test_review_snapshot_invalid_uuid(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """Calling GET snapshot with invalid UUID returns 400."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        res = client.get(
            "/api/sessions/not-a-valid-uuid/review/snapshot",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 400


def test_review_snapshot_ownership_denied_404(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """Foreign session returns 404 (RLS concealment policy via RPC)."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with patch.object(
            ReviewService,
            "get_current_snapshot",
            new_callable=AsyncMock,
            side_effect=ReviewDomainException(
                404, "ERR_QUESTION_NOT_FOUND", "Không tìm thấy câu hỏi hoặc phiên thi"
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 404
    assert res.json()["error_code"] == "ERR_QUESTION_NOT_FOUND"


def test_review_snapshot_ownership_denied_403(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """Explicit permission denial returns 403 when configured."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with patch.object(
            ReviewService,
            "get_current_snapshot",
            new_callable=AsyncMock,
            side_effect=ReviewDomainException(
                403, "ERR_FORBIDDEN", "Không có quyền thực hiện thao tác này"
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 403


# ==============================================================================
# Functional Success & Golden Fixtures Tests
# ==============================================================================


def test_review_snapshot_200_golden_complete(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """GET snapshot returns 200 with Golden 3x2 complete matrix and Cache-Control: no-store."""
    fixture_data = _load_fixture("complete.json")
    expected_resp = ReviewSnapshotResponse.model_validate(fixture_data)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "get_current_snapshot",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "no-store"
    data = res.json()

    assert data["session_id"] == MOCK_SESSION_ID
    assert data["session_status"] == "generated"
    assert data["read_only"] is False
    assert len(data["sources"]) == 3
    assert len(data["versions"]) == 2

    # Verify total slots = 3 x 2 = 6
    total_slots = sum(len(v["slots"]) for v in data["versions"])
    assert total_slots == 6
    assert data["progress"]["expected_slots"] == 6
    assert data["progress"]["current_slots"] == 6
    assert data["progress"]["missing_slots"] == 0

    # Verify each slot has a valid candidate
    for v in data["versions"]:
        for slot in v["slots"]:
            assert slot["candidate"] is not None
            assert slot["candidate"]["candidate_id"] is not None
            assert slot["candidate"]["status"] == "pending_review"
            assert len(slot["candidate"]["options"]) == 4
            assert slot["candidate"]["validation_source"] == "generation_result"
            assert slot["candidate"]["origin"] == "ai_generated"


def test_review_snapshot_200_partial(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """GET snapshot returns 200 with read_only=true and candidate=null on missing slot."""
    fixture_data = _load_fixture("partial.json")
    expected_resp = ReviewSnapshotResponse.model_validate(fixture_data)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "get_current_snapshot",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    assert data["session_status"] == "partial_generated"
    assert data["read_only"] is True
    assert data["progress"]["missing_slots"] == 1
    assert data["progress"]["current_slots"] == 5

    # Check that version 2, slot 3 has candidate = null
    v2 = next(v for v in data["versions"] if v["version_index"] == 2)
    missing_slot = next(s for s in v2["slots"] if s["question_no"] == 3)
    assert missing_slot["candidate"] is None


def test_review_snapshot_200_regenerated(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """GET snapshot identifies regenerated candidate with validation_source=version_question."""
    fixture_data = _load_fixture("regenerated.json")
    expected_resp = ReviewSnapshotResponse.model_validate(fixture_data)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "get_current_snapshot",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    cand = data["versions"][0]["slots"][0]["candidate"]
    assert cand["origin"] == "regenerated"
    assert cand["validation_source"] == "version_question"
    assert cand["validation_report"]["regenerated"] is True


def test_review_snapshot_200_clone(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """GET snapshot identifies original clone candidate."""
    fixture_data = _load_fixture("clone.json")
    expected_resp = ReviewSnapshotResponse.model_validate(fixture_data)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "get_current_snapshot",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    cand = data["versions"][0]["slots"][0]["candidate"]
    assert cand["origin"] == "original_clone"
    assert cand["validation_source"] == "unavailable"
    assert cand["validation_report"] is None


def test_review_snapshot_200_invalid_validation(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """GET snapshot handles missing validation evidence as null/unavailable."""
    fixture_data = _load_fixture("invalid_validation.json")
    expected_resp = ReviewSnapshotResponse.model_validate(fixture_data)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "get_current_snapshot",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    cand = data["versions"][0]["slots"][0]["candidate"]
    assert cand["has_warning"] is True
    assert cand["validation_report"] is None
    assert cand["validation_source"] == "unavailable"
    assert cand["origin"] == "unknown"


# ==============================================================================
# Domain Exception & HTTP Status Code Mapping Tests
# ==============================================================================


@pytest.mark.parametrize(
    "exc_status,exc_code,exc_msg,expected_http",
    [
        (409, "ERR_REVIEW_STATE_CONFLICT", "Phiên thi chưa hoàn tất tiến trình sinh", 409),
        (409, "ERR_REVIEW_NO_SNAPSHOT", "Không tìm thấy snapshot dữ liệu sinh", 409),
        (423, "ERR_SESSION_LOCKED", "Phiên đề đã được phê duyệt và khóa bất biến", 423),
        (503, "ERR_SOURCE_MISMATCH", "Dữ liệu nguồn đã xác nhận không khớp", 503),
        (503, "ERR_REVIEW_INVARIANT_VIOLATION", "Duplicate current candidate", 503),
        (503, "ERR_SNAPSHOT_MALFORMED", "Pydantic parsing failed", 503),
    ],
)
def test_review_snapshot_domain_exceptions(
    client: TestClient,
    mock_current_user: CurrentUser,
    auth_headers: dict,
    exc_status: int,
    exc_code: str,
    exc_msg: str,
    expected_http: int,
):
    """Domain exceptions from repository/RPC map to the designated HTTP statuses."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.review.assert_ownership", return_value=None),
            patch.object(
                ReviewService,
                "get_current_snapshot",
                new_callable=AsyncMock,
                side_effect=ReviewDomainException(exc_status, exc_code, exc_msg),
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == expected_http
    body = res.json()
    assert body["error_code"] == exc_code


# ==============================================================================
# Service & Repository Unit / Invariant Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_review_service_calls_repository_with_session_id():
    """ReviewService.get_current_snapshot delegates directly to repository without fabricating data."""
    mock_repo = MagicMock()
    fixture_data = _load_fixture("complete.json")
    mock_repo.read_current_snapshot = AsyncMock(return_value=fixture_data)

    service = ReviewService(db=MagicMock())
    service.repo = mock_repo

    result = await service.get_current_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    mock_repo.read_current_snapshot.assert_awaited_once_with(MOCK_SESSION_ID)
    assert isinstance(result, ReviewSnapshotResponse)
    assert str(result.session_id) == MOCK_SESSION_ID


@pytest.mark.asyncio
async def test_review_service_raises_503_on_malformed_rpc_data():
    """ReviewService raises 503 ERR_SNAPSHOT_MALFORMED when RPC payload violates schema."""
    mock_repo = MagicMock()
    mock_repo.read_current_snapshot = AsyncMock(return_value={"session_id": "not-complete-data"})

    service = ReviewService(db=MagicMock())
    service.repo = mock_repo

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_current_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)

    assert exc_info.value.status_code == 503
    assert exc_info.value.error_code == "ERR_SNAPSHOT_MALFORMED"


def test_review_snapshot_candidate_options_validation():
    """ReviewSnapshotCandidate fails validation when options array does not have exactly 4 items."""
    with pytest.raises(ValueError, match="options must contain exactly 4 elements"):
        ReviewSnapshotCandidate(
            candidate_id=UUID("40000000-0000-0000-0000-000000000001"),
            status="pending_review",
            content="Test",
            options=["A", "B", "C"],  # Only 3
            correct_key="A",
            validation_source="unavailable",
            origin="ai_generated",
            is_reverted=False,
            updated_at="2026-11-08T08:00:00Z",
        )


def test_review_snapshot_200_regenerating_status(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """GET snapshot returns 200 with candidate in 'regenerating' status and ready=false."""
    fixture_data = _load_fixture("complete.json")
    fixture_data["versions"][0]["slots"][0]["candidate"]["status"] = "regenerating"
    fixture_data["progress"]["ready"] = False
    expected_resp = ReviewSnapshotResponse.model_validate(fixture_data)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with patch.object(
            ReviewService,
            "get_current_snapshot",
            new_callable=AsyncMock,
            return_value=expected_resp,
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/review/snapshot",
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    cand = data["versions"][0]["slots"][0]["candidate"]
    assert cand["status"] == "regenerating"
    assert data["progress"]["ready"] is False


def test_exception_mapping_context_distinction():
    """Verify REVIEW_SOURCE_MISMATCH maps to 503 for snapshot RPC, but 422 for write RPCs."""
    from app.services.review.repository import _map_rpc_exception

    exc = Exception("P0001: REVIEW_SOURCE_MISMATCH")

    # Snapshot RPC context -> 503
    snapshot_err = _map_rpc_exception(exc, rpc_name="get_review_current_snapshot")
    assert snapshot_err.status_code == 503
    assert snapshot_err.error_code == "ERR_SOURCE_MISMATCH"

    # Write RPC context (e.g. review_accept_question) -> 422
    write_err = _map_rpc_exception(exc, rpc_name="review_accept_question")
    assert write_err.status_code == 422
    assert write_err.error_code == "ERR_INVALID_PAYLOAD"

    # Default / no rpc_name -> 422 (preserving legacy Write API behavior)
    default_err = _map_rpc_exception(exc)
    assert default_err.status_code == 422
    assert default_err.error_code == "ERR_INVALID_PAYLOAD"


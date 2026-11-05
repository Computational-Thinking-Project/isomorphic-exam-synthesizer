"""HTTP contract for the shuffle endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.main import app
from app.models.schemas import CurrentUser, ReviewDomainException
from app.services.shuffler.schemas import FinalizeShuffleResponse


def test_shuffle_auth_ownership_and_receipt():
    client = TestClient(app)
    session = str(uuid4())
    version = str(uuid4())
    assert client.post(f"/api/sessions/{session}/finalize/shuffle").status_code == 401
    user = CurrentUser(
        id=str(uuid4()), email="teacher@example.invalid", name="Teacher", access_token="token"
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()
    try:
        assert client.post("/api/sessions/not-uuid/finalize/shuffle").status_code == 400
        with patch(
            "app.api.routes.finalize.assert_ownership",
            side_effect=ReviewDomainException(403, "ERR_FORBIDDEN", "forbidden"),
        ):
            assert client.post(f"/api/sessions/{session}/finalize/shuffle").status_code == 403
        result = FinalizeShuffleResponse(
            session_id=session,
            status="reviewed",
            is_finalized=True,
            versions=[{"version_id": version, "version_code": "101", "total_questions": 1}],
        )
        with (
            patch("app.api.routes.finalize.assert_ownership"),
            patch(
                "app.api.routes.finalize.FinalizeService.shuffle_session",
                new_callable=AsyncMock,
                return_value=result,
            ) as shuffle,
        ):
            response = client.post(f"/api/sessions/{session}/finalize/shuffle")
            assert response.status_code == 200
            assert response.json() == result.model_dump()
            shuffle.assert_awaited_once_with(session, user.id)
        with (
            patch("app.api.routes.finalize.assert_ownership"),
            patch(
                "app.api.routes.finalize.FinalizeService.shuffle_session",
                new_callable=AsyncMock,
                side_effect=ReviewDomainException(503, "ERR_SHUFFLE_UNAVAILABLE", "unavailable"),
            ),
        ):
            assert client.post(f"/api/sessions/{session}/finalize/shuffle").status_code == 503
    finally:
        app.dependency_overrides.clear()

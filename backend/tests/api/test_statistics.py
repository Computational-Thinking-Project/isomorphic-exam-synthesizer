from unittest.mock import MagicMock, patch

import pytest
from postgrest.exceptions import APIError

PATH = "/api/users/me/statistics"
HEADERS = {"Authorization": "Bearer fixture-token"}
STATUSES = (
    "draft", "blueprinted", "configured", "generating", "partial_generated",
    "generated", "reviewed", "approved", "exported", "failed",
)


@pytest.fixture
def authenticated_db(mock_user_response):
    auth = MagicMock()
    auth.auth.get_user.return_value = mock_user_response
    db = MagicMock()
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=auth),
        patch("app.api.dependencies.get_authenticated_client", return_value=db) as user_client,
    ):
        yield db
        user_client.assert_called_once_with("fixture-token")


def test_statistics_require_authentication(client):
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers={"Authorization": "Basic invalid"}).status_code == 401


@pytest.mark.parametrize(
    ("rows", "totals", "buckets"),
    [
        ([{"status": status, "count": 1} for status in STATUSES], (10, 7, 1, 1), dict.fromkeys(STATUSES, 1)),
        ([{"status": "draft", "count": 2}], (2, 2, 0, 0), {"draft": 2}),
        ([{"status": "failed", "count": 3}], (3, 0, 0, 0), {"failed": 3}),
        ([], (0, 0, 0, 0), {}),
        ([{"status": None, "count": 2}, {"status": "future", "count": 1}], (3, 0, 0, 0), {"unknown": 3}),
    ],
)
def test_statistics_counts(client, authenticated_db, rows, totals, buckets):
    authenticated_db.rpc.return_value.execute.return_value.data = rows
    response = client.get(PATH, params={"user_id": "another-user"}, headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    total, in_progress, approved, exported = totals
    assert response.json() == {
        "total_sessions": total,
        "in_progress_sessions": in_progress,
        "approved_not_exported_sessions": approved,
        "exported_sessions": exported,
        "by_status": dict.fromkeys((*STATUSES, "unknown"), 0) | buckets,
    }
    authenticated_db.rpc.assert_called_once_with("get_my_session_status_counts", {})
    authenticated_db.rpc.return_value.execute.assert_called_once_with()


@pytest.mark.parametrize("rows", [None, {}, [{"count": 2}], [{"status": "draft", "count": True}]])
def test_statistics_rejects_malformed_result(client, authenticated_db, rows):
    authenticated_db.rpc.return_value.execute.return_value.data = rows
    response = client.get(PATH, headers=HEADERS)
    assert response.status_code == 503
    assert response.json() == {"detail": "Session statistics temporarily unavailable"}


def test_statistics_handles_database_failure(client, authenticated_db):
    authenticated_db.rpc.return_value.execute.side_effect = APIError({"message": "internal detail"})
    response = client.get(PATH, headers=HEADERS)
    assert response.status_code == 503
    assert "internal detail" not in response.text

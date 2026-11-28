from unittest.mock import MagicMock, patch

import pytest
from postgrest.exceptions import APIError

from app.models.exam_metadata import ExamMetadata

PATH = "/api/users/me/settings"
HEADERS = {"Authorization": "Bearer fixture-token"}


@pytest.fixture
def authenticated_db(mock_user_response):
    auth = MagicMock()
    auth.auth.get_user.return_value = mock_user_response
    db = MagicMock()
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=auth),
        patch("app.api.dependencies.get_authenticated_client", return_value=db),
    ):
        yield db


def test_exam_settings_require_authentication(client):
    assert client.get(PATH).status_code == 401
    assert client.patch(PATH, json={"grade": 10}).status_code == 401


def test_get_exam_settings_without_saved_defaults(client, authenticated_db, test_user_id):
    query = authenticated_db.table.return_value.select.return_value
    query.eq.return_value.limit.return_value.execute.return_value.data = []

    response = client.get(PATH, headers=HEADERS, params={"user_id": "another-user"})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json() == dict.fromkeys(ExamMetadata.model_fields)
    authenticated_db.table.assert_called_once_with("user_exam_settings")
    query.eq.assert_called_once_with("user_id", test_user_id)


def test_patch_normalizes_metadata_and_distinguishes_omitted_and_null(client, authenticated_db):
    patch_result = authenticated_db.rpc.return_value.execute.return_value
    patch_result.data = dict.fromkeys(ExamMetadata.model_fields) | {"school": "Trường A", "grade": 10}

    response = client.patch(PATH, headers=HEADERS, json={"school": " Trường A ", "subject": None})

    assert response.status_code == 200
    assert response.json() == patch_result.data
    authenticated_db.rpc.assert_called_once_with(
        "patch_my_exam_settings", {"p_patch": {"school": "Trường A", "subject": None}}
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": "another-user"},
        {"grade": "12"},
        {"grade": True},
        {"semester": 3},
        {"academic_year": "2026-2028"},
        {"exam_date": "2026-02-29"},
        {"duration_minutes": 0},
    ],
)
def test_invalid_patch_does_not_write(client, authenticated_db, payload):
    assert client.patch(PATH, headers=HEADERS, json=payload).status_code == 422
    authenticated_db.rpc.assert_not_called()


def test_empty_patch_only_reads(client, authenticated_db):
    query = authenticated_db.table.return_value.select.return_value
    query.eq.return_value.limit.return_value.execute.return_value.data = [{"grade": 11}]

    response = client.patch(PATH, headers=HEADERS, json={})

    assert response.status_code == 200
    assert response.json()["grade"] == 11
    authenticated_db.rpc.assert_not_called()


def test_failed_write_does_not_expose_database_details(client, authenticated_db):
    authenticated_db.rpc.return_value.execute.side_effect = APIError({"message": "internal detail"})

    response = client.patch(PATH, headers=HEADERS, json={"grade": 11})

    assert response.status_code == 503
    assert "internal detail" not in response.text

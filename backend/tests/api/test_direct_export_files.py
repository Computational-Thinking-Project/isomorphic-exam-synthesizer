from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.api.routes import private_export
from app.main import app
from app.models.schemas import CurrentUser, ReviewDomainException


@pytest.fixture
def client(monkeypatch):
    saved = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="owner", email="teacher@example.test", access_token="fixture")
    app.dependency_overrides[get_user_db] = lambda: Mock()
    monkeypatch.setattr(private_export, "run_private_export", Mock(return_value={
        "exam_101.pdf": b"%PDF-test", "exam_101.md": b"# Exam",
    }))
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def test_select_format_and_download_exact_bytes(client):
    response = client.get("/api/sessions/s1/export/files?format=pdf")
    assert response.status_code == 200
    assert response.json() == {"files": [{"filename": "exam_101.pdf", "size_bytes": 9}]}
    response = client.get("/api/sessions/s1/export/files?format=pdf&filename=exam_101.pdf")
    assert response.content == b"%PDF-test"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"


def test_file_selector_rejects_cross_format_and_paths(client):
    assert client.get("/api/sessions/s1/export/files?format=zip").status_code == 422
    assert client.get("/api/sessions/s1/export/files?format=pdf&filename=exam_101.md").status_code == 404
    assert client.get("/api/sessions/s1/export/files?format=pdf&filename=../other.pdf").status_code == 404


def test_file_download_preserves_owner_denial(client, monkeypatch):
    monkeypatch.setattr(private_export, "run_private_export",
                        Mock(side_effect=ReviewDomainException(403, "ERR_FORBIDDEN", "forbidden")))
    assert client.get("/api/sessions/s1/export/files?format=pdf").status_code == 403

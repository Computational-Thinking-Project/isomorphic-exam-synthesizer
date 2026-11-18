"""HTTP -> real service orchestration with fake durable/Storage ports, not live proof."""

import threading
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_private_export import args
from test_private_export import workflow as shared_workflow

from app.api.dependencies import get_current_user, get_user_db
from app.api.routes import private_export
from app.models.schemas import CurrentUser, ReviewDomainException
from app.services.exporter.private_models import ExportFailure


@pytest.fixture
def workflow(snapshot):
    return shared_workflow.__wrapped__(snapshot)


@pytest.fixture
def http(workflow, monkeypatch):
    app = FastAPI()
    app.include_router(private_export.router, prefix="/api/sessions")
    sid, uid = args(workflow)
    db = object()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uid, email="owner@example.test", access_token="test-only"
    )
    app.dependency_overrides[get_user_db] = lambda: db
    calls = []

    def run(operation, session, owner, user_db):
        assert user_db is db
        calls.append((operation, session, owner, threading.get_ident()))
        return getattr(workflow[0], operation)(session, owner)

    monkeypatch.setattr(private_export, "run_private_export", run)
    with TestClient(app) as client:
        yield client, f"/api/sessions/{sid}/export", calls, app


def test_build_replay_status_and_reissued_download(http, workflow):
    client, path, calls, _ = http
    assert client.get(path).json() == {"state": "idle"}
    assert workflow[4].call_count == 0
    for _ in range(2):
        response = client.post(path)
        assert response.status_code == 200
        assert set(response.json()) == {"state", "filename", "sha256", "size_bytes"}
    assert workflow[4].call_count == workflow[2].uploads == 1
    assert client.get(path).json()["state"] == "ready"
    for _ in range(2):
        grant = client.post(path + "/download-url")
        assert grant.status_code == 200
        assert grant.headers["cache-control"] == "no-store"
        assert grant.json()["expires_in"] == 3600
    assert workflow[2].signs == 2
    assert all(c[2] == args(workflow)[1] for c in calls)
    assert all(c[3] != threading.get_ident() for c in calls)


def test_live_claim_is_202_and_status_never_takes_over(http, workflow):
    client, path, _, _ = http
    workflow[1].claim(workflow[0]._snapshot(*args(workflow))[1])
    assert client.post(path).status_code == 202
    assert client.get(path).json() == {"state": "preparing"}
    assert workflow[4].call_count == workflow[2].uploads == workflow[2].signs == 0


@pytest.mark.parametrize("suffix", ["", "/download-url"])
def test_no_body_cannot_inject_owner_or_revision(http, suffix):
    client, path, calls, _ = http
    response = client.post(path + suffix, json={"owner_id": "other", "revision": "fake"})
    assert response.status_code == 400
    assert calls == []


@pytest.mark.parametrize("status", [400, 403, 404, 409, 423])
def test_domain_failures_propagate_without_privileged_calls(http, workflow, status):
    client, path, _, _ = http
    workflow[3].side_effect = ReviewDomainException(status, "ERR_TEST_BOUNDARY", "safe")
    for method, target in [
        (client.post, path),
        (client.get, path),
        (client.post, path + "/download-url"),
    ]:
        response = method(target)
        assert response.status_code == status
    assert workflow[1].current is None
    assert workflow[4].call_count == workflow[2].uploads == workflow[2].signs == 0


def test_unauthenticated_all_routes(http):
    client, path, calls, app = http
    del app.dependency_overrides[get_current_user]
    for method, target in [
        (client.post, path),
        (client.get, path),
        (client.post, path + "/download-url"),
    ]:
        assert method(target).status_code == 401
    assert calls == []


def test_lost_upload_response_requires_status_reconciliation(http, workflow):
    client, path, _, _ = http
    workflow[2].upload_failure = True
    result = client.post(path)
    assert result.status_code == 503
    assert result.json() == {"error_code": "ERR_EXPORT_STORAGE_OUTCOME_UNKNOWN"}
    assert client.get(path).json() == {"state": "preparing"}
    assert client.post(path).status_code == 202
    assert client.post(path + "/download-url").status_code == 409
    assert workflow[2].uploads == 1
    assert workflow[1].completions == 0


def test_unknown_exception_is_sanitized(http, monkeypatch):
    client, path, _, _ = http
    monkeypatch.setattr(
        private_export, "run_private_export", Mock(side_effect=RuntimeError("secret"))
    )
    result = client.post(path)
    assert result.status_code == 503
    assert "secret" not in result.text


def test_runtime_disabled_or_incomplete_config_never_creates_client(monkeypatch):
    from app.core.config import settings
    from app.services.exporter import private_runtime

    create = Mock()
    monkeypatch.setattr(private_runtime, "create_client", create)
    for enabled in (False, True):
        monkeypatch.setattr(settings, "PRIVATE_EXPORT_ENABLED", enabled)
        monkeypatch.setattr(settings, "PRIVATE_EXPORT_RPC_TIMEOUT_SECONDS", None)
        with pytest.raises(ExportFailure, match="ERR_EXPORT_UNAVAILABLE"):
            private_runtime.run_private_export("status", "session", "owner", Mock())
    create.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_runtime_separates_privileged_clients_and_closes_after_worker(fail, monkeypatch):
    from pydantic import SecretStr

    from app.core.config import settings
    from app.services.exporter import private_runtime
    from app.services.exporter.private_models import ExportResult

    monkeypatch.setattr(settings, "PRIVATE_EXPORT_ENABLED", True)
    monkeypatch.setattr(settings, "PRIVATE_EXPORT_RPC_TIMEOUT_SECONDS", 7)
    monkeypatch.setattr(settings, "PRIVATE_EXPORT_STORAGE_TIMEOUT_SECONDS", 11)
    monkeypatch.setattr(settings, "PRIVATE_EXPORT_BUCKET", "exam-export-bundles")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", SecretStr("test-only"))
    clients = []
    sdk_clients = []
    user_db = Mock()

    def create(url, key, *, options):
        assert key == "test-only"
        clients.append(options.httpx_client)
        sdk = Mock()
        sdk_clients.append(sdk)
        return sdk

    monkeypatch.setattr(private_runtime, "create_client", create)
    loader = Mock()
    monkeypatch.setattr(private_runtime, "user_snapshot_loader", loader)

    def status(sid, owner):
        assert len(clients) == 2 and clients[0] is not clients[1]
        assert clients[0].timeout.read == 7
        assert clients[1].timeout.read == 11
        assert all(not c.is_closed for c in clients)
        if fail:
            raise RuntimeError("transport failure")
        return ExportResult("idle")

    factory = Mock(return_value=Mock(status=status))
    monkeypatch.setattr(private_runtime, "PrivateExportService", factory)
    if fail:
        with pytest.raises(RuntimeError):
            private_runtime.run_private_export("status", "session", "owner", user_db)
    else:
        assert (
            private_runtime.run_private_export("status", "session", "owner", user_db).state
            == "idle"
        )
    loader.assert_called_once_with(user_db, provenance_db=sdk_clients[0])
    assert all(c.is_closed for c in clients)

"""TASK-12: registered-app auth boundary; Auth transport is fake, no lifespan/jobs.

These are local HTTP checks, not deployed JWT/RLS/Storage evidence.
"""

import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.main import app

SYNTHETIC_ID = "11111111-1111-4111-8111-111111111111"
# SSE GET authenticates with a single-use ticket instead of a Bearer header.
TICKET_STREAM = "/api/sessions/{session_id}/events"
PROTECTED = [
    (method.upper(), path)
    for path, operations in app.openapi()["paths"].items()
    if path.startswith(("/api/sessions", "/api/users")) and path != TICKET_STREAM
    for method in operations
    if method in {"get", "post", "patch", "delete", "put"}
]
# Historical alias is deliberately hidden from OpenAPI.
PROTECTED.append(("PATCH", "/api/sessions/{session_id}/preferences"))


@pytest.fixture
def boundary(monkeypatch):
    # Keep actual auth dependency and middleware; fail on any downstream DB use.
    assert dependencies.get_current_user not in app.dependency_overrides
    overrides = app.dependency_overrides.copy()
    downstream = Mock(side_effect=AssertionError("Unauthenticated DB access"))
    for dependency in (dependencies.get_user_db, dependencies.get_service_db):
        app.dependency_overrides[dependency] = downstream
    auth = Mock(return_value=SimpleNamespace(user=None))
    factory = Mock(return_value=SimpleNamespace(auth=SimpleNamespace(get_user=auth)))
    monkeypatch.setattr(dependencies, "get_supabase_client", factory)
    app.state.limiter._storage.reset()
    # No context manager: do not start generation workers/recovery lifespan.
    client = TestClient(app)
    try:
        yield client, factory, auth
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
        app.state.limiter._storage.reset()
        downstream.assert_not_called()


@pytest.mark.parametrize(
    "method,path", PROTECTED, ids=[f"{method} {path}" for method, path in PROTECTED]
)
@pytest.mark.parametrize(
    "authorization", [None, "", "Basic test", "Bearer", "Bearer ", "Bearer test-only-invalid-token"]
)
def test_w4_registered_routes_fail_closed_before_database(boundary, method, path, authorization):
    client, factory, auth = boundary
    path = re.sub(r"\{[^}]+\}", SYNTHETIC_ID, path)
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.request(method, path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert SYNTHETIC_ID not in response.text
    if authorization == "Bearer test-only-invalid-token":
        factory.assert_called_once_with()
        auth.assert_called_once_with("test-only-invalid-token")
    else:
        factory.assert_not_called()


def test_w4_auth_inventory_includes_export_and_stream_ticket_issuance():
    paths = {path for _, path in PROTECTED}
    assert {
        f"/api/sessions/{{session_id}}/{suffix}"
        for suffix in (
            "export",
            "export/download-url",
            "events/ticket",
            "finalize/approve",
            "confirm-source",
            "generate",
            "review/snapshot",
        )
    } <= paths


def test_w4_unknown_sse_ticket_cannot_reach_owner_lookup(boundary, monkeypatch):
    from app import main

    lookup = Mock(side_effect=AssertionError("Unknown ticket reached owner lookup"))
    monkeypatch.setattr(main, "get_service_role_client", lookup)
    client, factory, _ = boundary
    response = client.get(f"/api/sessions/{SYNTHETIC_ID}/events", params={"ticket": SYNTHETIC_ID})
    assert response.status_code == 401
    assert "text/event-stream" not in response.headers.get("content-type", "")
    factory.assert_not_called()
    lookup.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("PRIVATE_EXPORT_ENABLED", False),
        ("PRIVATE_EXPORT_RPC_TIMEOUT_SECONDS", None),
        ("PRIVATE_EXPORT_STORAGE_TIMEOUT_SECONDS", None),
        ("PRIVATE_EXPORT_BUCKET", "unapproved-bucket"),
        ("SUPABASE_URL", ""),
        ("SUPABASE_SERVICE_ROLE_KEY", ""),
    ],
)
def test_w4_incomplete_export_config_never_opens_privileged_transport(monkeypatch, field, value):
    from pydantic import SecretStr

    from app.core.config import settings
    from app.services.exporter import private_runtime
    from app.services.exporter.private_models import ExportFailure

    valid = {
        "PRIVATE_EXPORT_ENABLED": True,
        "PRIVATE_EXPORT_RPC_TIMEOUT_SECONDS": 7,
        "PRIVATE_EXPORT_STORAGE_TIMEOUT_SECONDS": 11,
        "PRIVATE_EXPORT_BUCKET": "exam-export-bundles",
        "SUPABASE_URL": "https://mock.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": SecretStr("synthetic-test-only"),
    }
    for name, setting in valid.items():
        monkeypatch.setattr(settings, name, setting)
    monkeypatch.setattr(settings, field, SecretStr(value) if field.endswith("_KEY") else value)
    transport, factory = Mock(), Mock()
    monkeypatch.setattr(private_runtime.httpx, "Client", transport)
    monkeypatch.setattr(private_runtime, "create_client", factory)
    with pytest.raises(ExportFailure, match="ERR_EXPORT_UNAVAILABLE"):
        private_runtime.run_private_export("export", SYNTHETIC_ID, SYNTHETIC_ID, Mock())
    transport.assert_not_called()
    factory.assert_not_called()

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.api.routes.generation_stream import create_generation_stream_router
from app.core.rate_limit import create_limiter, register_rate_limiter
from app.models.generation_events import GenerationEventData
from app.models.schemas import CurrentUser
from app.services.generation.events import GenerationEventBroker
from app.services.generation.tickets import StreamTicketStore
from app.services.observability.runtime_registry import RuntimeRegistry


@pytest.fixture
def stream_api(monkeypatch):
    sid, uid = uuid4(), uuid4()
    registry = RuntimeRegistry()
    registry.start()
    tickets = StreamTicketStore()
    events = GenerationEventBroker()
    owner = AsyncMock(return_value=True)
    limiter = create_limiter()
    app = FastAPI()
    register_rate_limiter(app, limiter_instance=limiter)
    app.include_router(
        create_generation_stream_router(
            tickets=tickets,
            events=events,
            registry=registry,
            is_current_owner=owner,
            limiter_instance=limiter,
        ),
        prefix="/api/sessions",
    )
    # Overrides are confined to this test app. Missing auth is tested separately.
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=str(uid), email="review@example.test", access_token="fixture"
    )
    app.dependency_overrides[get_user_db] = lambda: object()
    monkeypatch.setattr(
        "app.api.routes.generation_stream.assert_ownership", lambda *args, **kwargs: None
    )
    with TestClient(app) as client:
        yield client, sid, uid, registry, tickets, events, owner, app


def test_issue_ticket_requires_auth_and_current_ownership(stream_api) -> None:
    client, sid, uid, registry, tickets, events, owner, app = stream_api
    del app.dependency_overrides[get_current_user]
    response = client.post(f"/api/sessions/{sid}/events/ticket")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    owner.assert_not_called()


def test_ticket_stream_replay_and_single_use(stream_api) -> None:
    client, sid, uid, registry, tickets, events, owner, app = stream_api
    asyncio.run(
        events.publish(
            sid,
            "done",
            GenerationEventData(
                timestamp=datetime.now(timezone.utc), status="done", percent_complete=100
            ),
        )
    )
    response = client.post(f"/api/sessions/{sid}/events/ticket")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    ticket = response.json()["ticket"]
    path = f"/api/sessions/{sid}/events?ticket={ticket}"
    response = client.get(path)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers["x-accel-buffering"] == "no"
    assert "id: 1\nevent: done" in response.text
    owner.assert_awaited_once_with(sid, uid)
    assert client.get(path).status_code == 401
    assert registry.snapshot().active_sse_connections == 0


@pytest.mark.parametrize("result", [False, "true", None])
def test_ownership_change_rejects_stream_without_gauge(stream_api, result) -> None:
    client, sid, uid, registry, tickets, events, owner, app = stream_api
    owner.return_value = result
    ticket = client.post(f"/api/sessions/{sid}/events/ticket").json()["ticket"]
    assert client.get(f"/api/sessions/{sid}/events?ticket={ticket}").status_code == 403
    assert registry.snapshot().active_sse_connections == 0


def test_owner_lookup_error_is_safe_and_consumes_ticket(stream_api) -> None:
    client, sid, uid, registry, tickets, events, owner, app = stream_api
    owner.side_effect = RuntimeError("private database url")
    ticket = client.post(f"/api/sessions/{sid}/events/ticket").json()["ticket"]
    path = f"/api/sessions/{sid}/events?ticket={ticket}"
    response = client.get(path)
    assert response.status_code == 503 and "private" not in response.text
    assert client.get(path).status_code == 401


def test_wrong_session_and_malformed_cursor(stream_api) -> None:
    client, sid, uid, registry, tickets, events, owner, app = stream_api
    ticket = client.post(f"/api/sessions/{sid}/events/ticket").json()["ticket"]
    assert client.get(f"/api/sessions/{uuid4()}/events?ticket={ticket}").status_code == 401
    assert (
        client.get(
            f"/api/sessions/{sid}/events?ticket={ticket}", headers={"Last-Event-ID": "bad"}
        ).status_code
        == 422
    )
    owner.assert_not_called()


def test_future_cursor_returns_resync_conflict_before_stream(stream_api) -> None:
    client, sid, uid, registry, tickets, events, owner, app = stream_api
    ticket = client.post(f"/api/sessions/{sid}/events/ticket").json()["ticket"]
    response = client.get(f"/api/sessions/{sid}/events?ticket={ticket}&last_event_id=10")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_EVENT_HISTORY_LOST"
    assert registry.snapshot().active_sse_connections == 0

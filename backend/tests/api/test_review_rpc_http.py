"""HTTP -> actual caller/repository over explicit RPC/provider fixtures.

TestClient uses the real ASGI event loop; no scheduling or ReviewService methods
are stubbed. Auth/ownership and storage/provider are injected, so these tests do
not prove JWT verification, RLS, SQL transactions or cross-worker concurrency.
"""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from services.test_review_flow import State

from app.api.dependencies import get_current_user, get_service_db, get_user_db
from app.api.routes import review
from app.main import app
from app.models.schemas import CurrentUser


@pytest.fixture
def http_review(monkeypatch):
    state = State()
    ownership_checks = []

    def ownership(table, resource, actor, **_):
        ownership_checks.append((table, resource, actor))

    original_overrides = app.dependency_overrides.copy()
    monkeypatch.setattr(review, "assert_ownership", ownership)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=str(uuid4()), email="fixture@example.com", name="Fixture", access_token="fixture"
    )
    app.dependency_overrides[get_user_db] = lambda: state.owner
    app.dependency_overrides[get_service_db] = lambda: state.worker
    app.dependency_overrides[review.get_ai_generator] = lambda: state.provider
    client = TestClient(app)
    try:
        yield state, client, ownership_checks
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def action_url(state, action):
    return f"/api/sessions/{state.sid}/questions/{state.qid}/{action}"


def test_http_reject_runs_actual_caller_and_replays_completed_receipt(http_review):
    state, client, ownership = http_review
    key = str(uuid4())
    first = client.post(action_url(state, "reject"), headers={"Idempotency-Key": key})
    assert first.status_code == 200, first.text
    assert first.json()["validation_report"]["math_verified"] is False
    assert state.charges == state.provider_calls == state.complete_calls == 1
    assert len(ownership) == 2
    state.status = "approved"
    state.operations[key]["expires_at"] = "2000-01-01T00:00:00Z"
    replay = client.post(action_url(state, "reject"), headers={"Idempotency-Key": key})
    assert replay.status_code == 200, replay.text
    assert replay.json()["question_id"] == first.json()["question_id"]
    assert state.provider_calls == 1 and state.complete_calls == 1
    assert {role for role, n, _ in state.calls if n == "review_reserve_regeneration"} == {
        "owner"
    }
    assert {role for role, n, _ in state.calls if n == "review_acquire_attempt"} == {"worker"}


def test_http_legacy_snapshot_fails_and_settles_before_permit(http_review):
    state, client, _ = http_review
    state.snapshot["format"] = "database_rows"
    key = str(uuid4())
    result = client.post(action_url(state, "reject"), headers={"Idempotency-Key": key})
    assert result.status_code == 422, result.text
    assert state.operations[key]["operation_status"] == "failed"
    assert state.provider_calls == state.charges == state.complete_calls == 0
    failures = [(role, p) for role, n, p in state.calls if n == "review_fail_regeneration"]
    assert len(failures) == 1 and failures[0][0] == "worker"
    assert failures[0][1]["p_operation_id"] == key


def test_http_active_replay_does_not_dispatch_or_settle(http_review):
    state, client, _ = http_review
    key = str(uuid4())
    state.rpc(
        "owner",
        "review_reserve_regeneration",
        {"p_session_id": state.sid, "p_question_id": state.qid, "p_operation_id": key},
    )
    result = client.post(action_url(state, "reject"), headers={"Idempotency-Key": key})
    assert result.status_code == 409, result.text
    assert state.provider_calls == state.charges == 0
    assert state.operations[key]["operation_status"] == "active"
    assert not any(n == "review_fail_regeneration" for _, n, _ in state.calls)


@pytest.mark.parametrize("action", ["accept", "revert"])
def test_http_action_key_replays_after_lock_but_new_action_is_locked(http_review, action):
    state, client, _ = http_review
    key = str(uuid4())
    first = client.post(action_url(state, action), headers={"Idempotency-Key": key})
    assert first.status_code == 200, first.text
    state.status = "approved"
    replay = client.post(action_url(state, action), headers={"Idempotency-Key": key})
    assert replay.status_code == 200, replay.text
    new = client.post(action_url(state, action), headers={"Idempotency-Key": str(uuid4())})
    assert new.status_code == 423, new.text
    assert len(state.actions) == 1
    assert all(
        role == "owner" and UUID(p["p_action_id"])
        for role, n, p in state.calls
        if n == f"review_{action}_question"
    )


@pytest.mark.parametrize("action", ["accept", "reject", "revert"])
def test_http_invalid_key_rejected_before_ownership_and_rpc(http_review, action):
    state, client, ownership = http_review
    result = client.post(action_url(state, action), headers={"Idempotency-Key": "bad-key"})
    assert result.status_code == 400, result.text
    assert not ownership and not state.calls and not state.operations


def test_http_unconfigured_provider_has_no_reservation_or_quota_effect(http_review):
    state, client, _ = http_review
    app.dependency_overrides[review.get_ai_generator] = lambda: None
    result = client.post(action_url(state, "reject"))
    assert result.status_code == 503, result.text
    assert not state.operations and state.charges == state.provider_calls == 0

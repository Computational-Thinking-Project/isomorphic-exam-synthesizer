"""Public confirmation through actual producer/repository, explicit storage/provider fixtures.

Legacy003/fallback creation expectations are replaced by canonical pending/resume.
Audit atomicity and claims are independently exercised by PostgreSQL tests.
"""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.api.dependencies import get_current_user, get_service_db, get_user_db
from app.api.routes import source_artifacts
from app.main import app
from app.models.schemas import CurrentUser


@pytest.fixture
def flow(monkeypatch):
    sid, actor = str(uuid4()), str(uuid4())
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8")
    )
    source = fixture["source"]
    row = dict(
        id=source["id"],
        session_id=sid,
        question_no=1,
        raw_content=source["question_text"],
        options=source["options"],
        correct_key="A",
        solution_md=None,
        has_missing_answer=False,
    )
    state = SimpleNamespace(
        sid=sid,
        actor=actor,
        row=row,
        status="draft",
        owner=actor,
        calls=[],
        confirmation=None,
        error=None,
        read_error=False,
        ready=False,
        revision="2026-11-04T00:00:00Z",
        supported_modes=None,
        extracts=0,
    )
    db = MagicMock()

    def table(name):
        query = MagicMock()
        query.select.return_value = query.eq.return_value = query.order.return_value = query

        def execute():
            return SimpleNamespace(
                data=[
                    dict(
                        user_id=state.owner, status=state.status, updated_at=state.revision
                    )
                ]
                if name == "exam_sessions"
                else ([] if state.row is None else [state.row])
            )

        query.execute.side_effect = execute
        return query

    db.table.side_effect = table

    def rpc(name, params):
        state.calls.append((name, deepcopy(params)))

        def execute():
            if name == "confirm_source_artifacts":
                if state.error:
                    raise state.error

                if state.confirmation is not None:
                    saved = state.confirmation

                # Replay phải dùng đúng key, actor và source đã xác nhận.
                if (
                    params["p_confirmation_id"] != saved["confirmation_id"]
                    or params["p_actor_id"] != saved["actor_id"]
                    or params["p_sources"] != saved["sources"]
                ):
                    raise RuntimeError("ARTIFACT_IDEMPOTENCY_CONFLICT")

                data = deepcopy(saved)
                data["replayed"] = True

            else:
                # Mô phỏng revision guard trong PostgreSQL RPC.
                if params["p_expected_updated_at"] != state.revision:
                    raise RuntimeError("ARTIFACT_STALE")

                if state.status != "draft":
                    raise RuntimeError("ARTIFACT_STALE")

                data = dict(
                    confirmation_id=params["p_confirmation_id"],
                    session_id=sid,
                    actor_id=params["p_actor_id"],
                    confirmed_at="2026-11-04T00:00:00Z",
                    status="blueprinted",
                    total_questions=1,
                    total_blueprints=0,
                    canonical_status="pending",
                    replayed=False,
                    sources=params["p_sources"],
                )

                state.confirmation = deepcopy(data)
                state.status = "blueprinted"

            return SimpleNamespace(data=data)
            if name == "get_source_artifacts":
                if state.read_error:
                    raise ConnectionError("lost response")
                return SimpleNamespace(
                    data=dict(
                        confirmation=state.confirmation,
                        pending_source_question_ids=[] if state.ready else [source["id"]],
                        ready=state.ready,
                    )
                )
            if name == "claim_source_production":
                return SimpleNamespace(
                    data=dict(
                        session_id=sid,
                        source_question_id=source["id"],
                        source_revision_id=params["p_source_revision_id"],
                        producer_job_id=params["p_job_id"],
                        status="claimed",
                        expires_at="2099-01-01T00:00:00Z",
                    )
                )
            if name == "publish_canonical_blueprint":
                state.ready = True
                publication = params["p_publication"]
                return SimpleNamespace(
                    data=dict(
                        session_id=sid,
                        source_question_id=publication["source_question_id"],
                        source_revision_id=publication["source_revision_id"],
                        blueprint_revision_id=publication["blueprint_revision_id"],
                        replayed=False,
                    )
                )
            if name == "fail_source_production":
                return SimpleNamespace(data=dict(settled=True))
            raise AssertionError(name)

        return SimpleNamespace(execute=execute)

    worker = SimpleNamespace(rpc=rpc)
    db.rpc.side_effect = rpc

    class Extractor:
        async def extract_confirmed(self, items, **kwargs):
            state.extracts += 1
            assert state.confirmation is not None
            return [{"blueprint": deepcopy(fixture["blueprint"])}], []

    state.extractor = Extractor()
    monkeypatch.setattr(source_artifacts, "blueprint_service", lambda request: None)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update(
        {
            get_current_user: lambda: CurrentUser(
                id=actor, email="fixture@example.com", name="Fixture", access_token="fixture"
            ),
            get_user_db: lambda: db,
            get_service_db: lambda: worker,
        }
    )
    if hasattr(app.state, "limiter"):
        app.state.limiter._storage.reset()
    client = TestClient(app)
    try:
        yield state, client
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def url(state, suffix="confirm-source"):
    return f"/api/sessions/{state.sid}/{suffix}"


def test_confirm_pending_without_adapter_or_legacy_blueprint(flow):
    state, client = flow
    result = client.post(url(state), json={})
    assert result.status_code == 200, result.text
    assert result.json()["canonical_status"] == "pending"
    assert result.json()["total_blueprints"] == 0
    assert state.extracts == 0
    assert [n for n, _ in state.calls] == ["confirm_source_artifacts", "get_source_artifacts"]
    assert state.calls[0][1]["p_actor_id"] == state.actor


# ---------------------------------------------------------------------------
# Q01 — source_revision contract tests
# ---------------------------------------------------------------------------

def test_confirm_with_matching_source_revision_succeeds(flow):
    state, client = flow
    key = str(uuid4())

    response = client.post(
        url(state),
        json={"source_revision": state.revision},
        headers={"Idempotency-Key": key},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "blueprinted"

    rpc_calls = [
        params for name, params in state.calls
        if name == "confirm_source_artifacts"
    ]
    assert len(rpc_calls) == 1
    assert rpc_calls[0]["p_expected_updated_at"] == state.revision


def test_confirm_with_mismatched_source_revision_returns_409_conflict(flow):
    state, client = flow
    stale_revision = "2026-01-01T00:00:00Z"

    response = client.post(
        url(state),
        json={"source_revision": stale_revision},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 409, response.text
    assert "ERR_SOURCE_REVISION_CONFLICT" in response.text
    assert state.confirmation is None
    assert state.status == "draft"

    rpc_calls = [
        params for name, params in state.calls
        if name == "confirm_source_artifacts"
    ]
    assert len(rpc_calls) == 1
    assert rpc_calls[0]["p_expected_updated_at"] == stale_revision


def test_confirm_without_source_revision_returns_422(flow):
    state, client = flow

    response = client.post(url(state), json={})

    assert response.status_code == 422
    assert state.confirmation is None
    assert not state.calls


def test_idempotent_retry_with_same_key_and_revision(flow):
    state, client = flow
    key = str(uuid4())
    payload = {"source_revision": state.revision}
    headers = {"Idempotency-Key": key}

    first = client.post(
        url(state),
        json=payload,
        headers=headers,
    )
    assert first.status_code == 200, first.text

    replay = client.post(
        url(state),
        json=payload,
        headers=headers,
    )
    assert replay.status_code == 200, replay.text

    assert first.json()["confirmation_id"] == key
    assert replay.json()["confirmation_id"] == key

    confirm_calls = [
        params for name, params in state.calls
        if name == "confirm_source_artifacts"
    ]
    assert len(confirm_calls) == 2
    assert confirm_calls[0]["p_confirmation_id"] == key
    assert confirm_calls[1]["p_confirmation_id"] == key
    assert confirm_calls[0]["p_sources"] == confirm_calls[1]["p_sources"]

def test_background_publication_and_retry_are_actual_producer(flow, monkeypatch):
    state, client = flow
    client.post(url(state), json={})
    monkeypatch.setattr(source_artifacts, "blueprint_service", lambda request: state.extractor)
    result = client.post(url(state, "source-artifacts/retry"))
    assert result.status_code == 202, result.text
    status = client.get(url(state, "source-artifacts"))
    assert status.status_code == 200 and status.json()["ready"] is True
    assert state.extracts == 1
    assert client.post(url(state, "source-artifacts/retry")).status_code == 200
    assert state.extracts == 1


def test_postcommit_read_failure_retains_confirmation_and_same_key_reconciles(flow):
    state, client = flow
    state.read_error = True

    key = str(uuid4())
    payload = {"source_revision": state.revision}
    headers = {"Idempotency-Key": key}

    first = client.post(url(state), json=payload, headers=headers)

    assert first.status_code == 503
    assert state.confirmation is not None

    state.read_error = False

    replay = client.post(url(state), json=payload, headers=headers)

    assert replay.status_code == 200, replay.text
    assert replay.json()["confirmation_id"] == key
    assert state.confirmation["confirmation_id"] == key

@pytest.mark.parametrize("status", ["blueprinted", "generating", "approved"])
def test_without_key_reconfirmation_refused(flow, status):
    state, client = flow
    state.status = status
    assert client.post(url(state), json={}).status_code == 409
    assert not state.calls


@pytest.mark.parametrize("missing", [True, False])
def test_missing_source_or_answer_is_rejected_before_worker(flow, missing):
    state, client = flow
    if missing:
        state.row["has_missing_answer"] = True
    else:
        state.row = None
    assert client.post(url(state), json={}).status_code == 422
    assert not state.calls


@pytest.mark.parametrize(
    "suffix,method",
    [("confirm-source", "post"), ("source-artifacts", "get"), ("source-artifacts/retry", "post")],
)
def test_owner_guard_before_worker(flow, suffix, method):
    state, client = flow
    state.owner = str(uuid4())
    options = (
    {"json": {"source_revision": state.revision}}
    if suffix == "confirm-source"
    else {}
)
    assert getattr(client, method)(url(state, suffix), **options).status_code == 403
    assert not state.calls


@pytest.mark.parametrize(
    "suffix,method",
    [("confirm-source", "post"), ("source-artifacts", "get"), ("source-artifacts/retry", "post")],
)
def test_source_endpoints_require_authentication(flow, suffix, method):
    state, client = flow
    app.dependency_overrides.pop(get_current_user)
    options = (
    {"json": {"source_revision": state.revision}}
    if suffix == "confirm-source"
    else {}
)
    assert getattr(client, method)(url(state, suffix), **options).status_code == 401
    assert not state.calls


def test_status_is_read_only_and_retry_without_adapter_is_503(flow):
    state, client = flow
    client.post(url(state), json={})
    state.calls.clear()
    assert client.get(url(state, "source-artifacts")).json()["ready"] is False
    assert client.post(url(state, "source-artifacts/retry")).status_code == 503
    assert all(n == "get_source_artifacts" for n, _ in state.calls)


@pytest.mark.parametrize("status,code", [("approved", 423), ("exported", 423), ("generating", 409)])
def test_pending_retry_checks_session_guard_before_scheduling(flow, monkeypatch, status, code):
    state, client = flow
    assert client.post(url(state), json={}).status_code == 200
    state.status = status
    monkeypatch.setattr(source_artifacts, "blueprint_service", lambda request: state.extractor)
    state.calls.clear()
    assert client.post(url(state, "source-artifacts/retry")).status_code == code
    assert state.extracts == 0
    assert all(name == "get_source_artifacts" for name, _ in state.calls)


@pytest.mark.parametrize(
    "error,status,rolled_back",
    [
        (httpx.ReadTimeout(""), 504, False),
        (httpx.ReadError(""), 504, False),
        (httpx.RemoteProtocolError(""), 504, False),
        (APIError(dict(code="23505", message="conflict", details=None, hint=None)), 500, True),
        (APIError(dict(code="08007", message="uncertain", details=None, hint=None)), 500, False),
        (APIError(dict(code="502", message="gateway", details="<html>", hint=None)), 500, False),
        (RuntimeError("unknown"), 500, False),
    ],
)
def test_confirmation_error_never_claims_unproven_rollback(flow, error, status, rolled_back):
    state, client = flow
    state.error = error
    result = client.post(url(state), json={})
    assert result.status_code == status, result.text
    assert ("rolled back" in result.text) == rolled_back
    assert state.extracts == 0


def test_invalid_key_has_no_rpc_effect(flow):
    state, client = flow
    assert client.post(url(state), json={}, headers={"Idempotency-Key": "bad"}).status_code == 400
    assert not state.calls


# ---------------------------------------------------------------------------
# Q02 — supported_modes in source-artifacts status
# ---------------------------------------------------------------------------


def test_source_artifacts_status_pending_has_no_supported_modes(flow):
    """GET /source-artifacts returns supported_modes=None while not ready."""
    state, client = flow
    client.post(url(state), json={})
    state.calls.clear()
    status_resp = client.get(url(state, "source-artifacts"))
    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["ready"] is False
    # Not ready → supported_modes must be None (not computed yet)
    assert data.get("supported_modes") is None


def test_source_artifacts_status_ready_has_supported_modes_list(flow, monkeypatch):
    """GET /source-artifacts returns supported_modes list when ready."""
    from app.api.routes import source_artifacts

    state, client = flow
    client.post(url(state), json={})
    # Publish so it becomes ready
    monkeypatch.setattr(source_artifacts, "blueprint_service", lambda request: state.extractor)
    client.post(url(state, "source-artifacts/retry"))
    # Patch _collect_supported_modes to return a known list
    monkeypatch.setattr(
        source_artifacts,
        "_collect_supported_modes",
        lambda db, session_id: ["PARAM", "SHUFFLE"],
    )
    status_resp = client.get(url(state, "source-artifacts"))
    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["ready"] is True
    assert data["supported_modes"] == ["PARAM", "SHUFFLE"]


def test_source_artifacts_ready_with_empty_modes_is_valid(flow, monkeypatch):
    """ready=True with supported_modes=[] is a valid state (NONE-only blueprint)."""
    from app.api.routes import source_artifacts

    state, client = flow
    client.post(url(state), json={})
    monkeypatch.setattr(source_artifacts, "blueprint_service", lambda request: state.extractor)
    client.post(url(state, "source-artifacts/retry"))
    monkeypatch.setattr(
        source_artifacts,
        "_collect_supported_modes",
        lambda db, session_id: [],
    )
    status_resp = client.get(url(state, "source-artifacts"))
    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["ready"] is True
    assert data["supported_modes"] == []

def test_changed_source_after_preview_returns_409(flow):
    state, client = flow
    preview_revision = state.revision

    # Một tab khác đã thay thế đề nguồn.
    state.revision = "2026-11-05T01:00:00Z"

    response = client.post(
        url(state),
        json={"source_revision": preview_revision},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 409
    assert "ERR_SOURCE_REVISION_CONFLICT" in response.text
    assert state.confirmation is None
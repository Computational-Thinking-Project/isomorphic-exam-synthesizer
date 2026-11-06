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
        revision=str(uuid4()),
        supported_modes=None,
        extracts=0,
        table_calls=[],
        mutate_after_preview=False,
        preview_failure=False,
        production_status=None,
    )
    db = MagicMock()

    def table(name):
        state.table_calls.append(name)
        if name == "generation_configs":
            query = MagicMock()
            query.select.return_value = query
            query.eq.return_value = query
            query.limit.return_value = query
            query.execute.return_value = SimpleNamespace(data=[])
            return query
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
            if name == "get_generation_source_snapshot":
                return SimpleNamespace(
                    data={
                        "ready": False,
                        "reason": "CANONICAL_BLUEPRINTS_INCOMPLETE",
                    }
                )
            if name == "get_session_source_preview":
                if state.preview_failure:
                    raise ConnectionError("preview unavailable")
                preview = dict(
                    session=dict(id=sid, user_id=state.owner, status=state.status,
                                 title="Fixture", subject="Math", grade=12,
                                 created_at="2026-11-04T00:00:00Z", updated_at="2026-11-04T00:00:00Z"),
                    source_revision=state.revision,
                    source_questions=[] if state.row is None else [deepcopy(state.row)],
                )
                if state.mutate_after_preview:
                    state.revision = str(uuid4())
                    state.row["raw_content"] = "Other tab"
                return SimpleNamespace(data=preview)
            if name == "confirm_source_artifacts":
                if state.error:
                    raise state.error

                if state.confirmation is not None:
                    saved = state.confirmation

                    if params["p_confirmation_id"] != saved["confirmation_id"]:
                        raise RuntimeError("ARTIFACT_STALE")
                    # SQL replay binds source content, not freshly prepared artifact UUIDs.
                    if (
                        params["p_confirmation_id"] != saved["confirmation_id"]
                        or params["p_actor_id"] != saved["actor_id"]
                        or [{k: v for k, v in item.items() if k != "source_revision_id"} for item in params["p_sources"]]
                        != [{k: v for k, v in item.items() if k != "source_revision_id"} for item in saved["sources"]]
                    ):
                        raise RuntimeError("ARTIFACT_IDEMPOTENCY_CONFLICT")

                    data = deepcopy(saved)
                    data["replayed"] = True

                else:
                    # Mô phỏng revision guard trong PostgreSQL RPC.
                    if params["p_expected_source_revision"] != state.revision:
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
                if state.confirmation is None:
                    raise APIError(
                        {"code": "P0002", "message": "not found", "details": None, "hint": None}
                    )
                # Build production list consistent with SourceArtifactState validation.
                # source_revision_id must match the one stored in confirmation.sources[0].
                source_revision_id = state.confirmation["sources"][0]["source_revision_id"]
                production = [
                    dict(
                        source_question_id=source["id"],
                        source_revision_id=source_revision_id,
                        status="ready" if state.ready else (state.production_status or "pending"),
                        expires_at="2099-01-01T00:00:00Z" if state.production_status == "running" else None,
                        error_code="FIXTURE_FAILURE" if state.production_status == "failed" else None,
                    )
                ]
                return SimpleNamespace(
                    data=dict(
                        confirmation=state.confirmation,
                        pending_source_question_ids=[] if state.ready else [source["id"]],
                        ready=state.ready,
                        production=production,
                        supported_modes=state.supported_modes,
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
                if state.supported_modes is None:
                    state.supported_modes = []
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
    # One stable operation key by default; negative cases explicitly remove it.
    client.headers["Idempotency-Key"] = str(uuid4())
    try:
        yield state, client
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def url(state, suffix="confirm-source"):
    return f"/api/sessions/{state.sid}/{suffix}"


def test_postreview_missing_key_is_rejected_before_worker(flow):
    state, client = flow
    client.headers.pop("Idempotency-Key")
    result = client.post(url(state), json={"source_revision": state.revision})
    assert result.status_code == 422, result.text
    assert not state.calls


def test_preview_is_one_rpc_snapshot_even_if_another_tab_changes_source(flow):
    state, client = flow
    revision, content = state.revision, state.row["raw_content"]
    state.mutate_after_preview = True
    response = client.get(f"/api/sessions/{state.sid}")
    assert response.status_code == 200, response.text
    assert response.json()["source_revision"] == revision
    assert response.json()["source_questions"][0]["raw_content"] == content
    assert [
        name for name, _ in state.calls
        if name == "get_session_source_preview"
    ] == ["get_session_source_preview"]
    assert "source_questions" not in state.table_calls
    stale = client.post(url(state), json={"source_revision": revision})
    assert stale.status_code == 409
    assert state.confirmation is None


def test_failed_snapshot_does_not_fall_back_to_independent_queries(flow):
    state, client = flow
    state.preview_failure = True
    response = client.get(f"/api/sessions/{state.sid}")
    assert response.status_code == 503
    assert "source_questions" not in state.table_calls


def test_confirm_pending_without_adapter_or_legacy_blueprint(flow):
    state, client = flow
    result = client.post(url(state), json={"source_revision": state.revision})
    assert result.status_code == 200, result.text
    assert result.json()["canonical_status"] == "pending"
    assert result.json()["total_blueprints"] == 0
    assert state.extracts == 0
    assert [n for n, _ in state.calls] == [
        "get_session_source_preview", "confirm_source_artifacts", "get_source_artifacts"
    ]
    assert state.calls[1][1]["p_actor_id"] == state.actor
    assert "source_questions" not in state.table_calls


# ---------------------------------------------------------------------------
# Q01 — source_revision contract tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("uppercase", [False, True])
def test_confirm_with_matching_source_revision_succeeds(flow, uppercase):
    state, client = flow
    key = str(uuid4())
    session_id = state.sid.upper() if uppercase else state.sid

    response = client.post(
        f"/api/sessions/{session_id}/confirm-source",
        json={"source_revision": state.revision},
        headers={"Idempotency-Key": key},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "blueprinted"
    assert state.calls[0] == ("get_session_source_preview", {"p_session_id": state.sid})

    rpc_calls = [
        params for name, params in state.calls
        if name == "confirm_source_artifacts"
    ]
    assert len(rpc_calls) == 1
    assert rpc_calls[0]["p_expected_source_revision"] == state.revision


@pytest.mark.parametrize("source", ["valid", "empty", "missing_answer"])
def test_confirm_with_mismatched_source_revision_returns_409_conflict(flow, source):
    state, client = flow
    stale_revision = str(uuid4())
    if source == "empty":
        state.row = None
    elif source == "missing_answer":
        state.row["has_missing_answer"] = True

    response = client.post(
        url(state),
        json={"source_revision": stale_revision},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 409, response.text
    assert "ERR_SOURCE_REVISION_CONFLICT" in response.text
    assert state.confirmation is None
    assert state.status == "draft"

    assert [name for name, _ in state.calls] == ["get_session_source_preview"]


def test_confirm_without_source_revision_returns_422(flow):
    state, client = flow

    response = client.post(url(state), json={})

    assert response.status_code == 422
    assert state.confirmation is None
    assert not state.calls


@pytest.mark.parametrize("revision", ["bad", "2026-11-05T00:00:00Z", None, 17])
def test_malformed_revision_is_rejected_before_worker(flow, revision):
    state, client = flow
    response = client.post(url(state), json={"source_revision": revision})
    assert response.status_code == 422
    assert not state.calls


def test_same_key_changed_source_is_idempotency_conflict(flow):
    state, client = flow
    headers = {"Idempotency-Key": str(uuid4())}
    payload = {"source_revision": state.revision}
    assert client.post(url(state), json=payload, headers=headers).status_code == 200
    state.row["raw_content"] += " changed"
    result = client.post(url(state), json=payload, headers=headers)
    assert result.status_code == 409
    assert result.json()["error_code"] == "ERR_IDEMPOTENCY_CONFLICT"


def test_new_key_cannot_reconfirm_blueprinted_session(flow):
    state, client = flow
    payload = {"source_revision": state.revision}
    assert client.post(url(state), json=payload, headers={"Idempotency-Key": str(uuid4())}).status_code == 200
    receipt = deepcopy(state.confirmation)
    assert client.post(url(state), json=payload, headers={"Idempotency-Key": str(uuid4())}).status_code == 409
    assert state.confirmation == receipt


def test_source_content_race_maps_to_source_changed(flow):
    state, client = flow
    state.error = RuntimeError("ARTIFACT_SOURCE_MISMATCH")
    result = client.post(url(state), json={"source_revision": state.revision})
    assert result.status_code == 409
    assert result.json()["error_code"] == "ERR_SOURCE_CHANGED"
    assert state.confirmation is None


def test_idempotent_retry_with_same_key_and_stale_revision(flow):
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
        json={"source_revision": str(uuid4())},
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
    assert confirm_calls[0]["p_sources"][0]["confirmed_input"] == confirm_calls[1]["p_sources"][0]["confirmed_input"]

def test_background_publication_and_retry_are_actual_producer(flow, monkeypatch):
    state, client = flow
    client.post(url(state), json={"source_revision": state.revision})
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
    client.headers.pop("Idempotency-Key")
    assert client.post(url(state), json={"source_revision": state.revision}).status_code == 422
    assert not state.calls


@pytest.mark.parametrize("missing", [True, False])
def test_missing_source_or_answer_is_rejected_before_worker(flow, missing):
    state, client = flow
    if missing:
        state.row["has_missing_answer"] = True
    else:
        state.row = None
    assert client.post(url(state), json={"source_revision": state.revision}).status_code == 422
    assert [name for name, _ in state.calls] == ["get_session_source_preview"]


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
    client.post(url(state), json={"source_revision": state.revision})
    state.calls.clear()
    assert client.get(url(state, "source-artifacts")).json()["ready"] is False
    assert client.post(url(state, "source-artifacts/retry")).status_code == 503
    assert all(n == "get_source_artifacts" for n, _ in state.calls)


@pytest.mark.parametrize("status,code", [("approved", 423), ("exported", 423), ("generating", 409)])
def test_pending_retry_checks_session_guard_before_scheduling(flow, monkeypatch, status, code):
    state, client = flow
    assert client.post(url(state), json={"source_revision": state.revision}).status_code == 200
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
    result = client.post(url(state), json={"source_revision": state.revision})
    assert result.status_code == status, result.text
    assert ("rolled back" in result.text) == rolled_back
    assert state.extracts == 0


def test_invalid_key_has_no_rpc_effect(flow):
    state, client = flow
    assert client.post(url(state), json={"source_revision": state.revision}, headers={"Idempotency-Key": "bad"}).status_code == 400
    assert not state.calls


# ---------------------------------------------------------------------------
# Q02 — supported_modes in source-artifacts status
# ---------------------------------------------------------------------------


def test_source_artifacts_status_pending_has_no_supported_modes(flow):
    """GET /source-artifacts returns supported_modes=None while not ready."""
    state, client = flow
    client.post(url(state), json={"source_revision": state.revision})
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
    client.post(url(state), json={"source_revision": state.revision})
    # Publish so it becomes ready
    monkeypatch.setattr(source_artifacts, "blueprint_service", lambda request: state.extractor)
    client.post(url(state, "source-artifacts/retry"))
    state.supported_modes = []
    status_resp = client.get(url(state, "source-artifacts"))
    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["ready"] is True
    assert data["supported_modes"] == []


def test_source_artifacts_ready_with_empty_modes_is_valid(flow, monkeypatch):
    """ready=True with supported_modes=[] is a valid state (NONE-only blueprint)."""
    from app.api.routes import source_artifacts

    state, client = flow
    client.post(url(state), json={"source_revision": state.revision})
    monkeypatch.setattr(source_artifacts, "blueprint_service", lambda request: state.extractor)
    client.post(url(state, "source-artifacts/retry"))
    state.supported_modes = []
    status_resp = client.get(url(state, "source-artifacts"))
    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["ready"] is True
    assert data["supported_modes"] == []

def test_changed_source_between_confirmation_snapshot_and_commit_returns_409(flow):
    state, client = flow
    preview_revision = state.revision

    state.mutate_after_preview = True

    response = client.post(
        url(state),
        json={"source_revision": preview_revision},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 409
    assert "ERR_SOURCE_REVISION_CONFLICT" in response.text
    assert state.confirmation is None
    assert [name for name, _ in state.calls] == [
        "get_session_source_preview", "confirm_source_artifacts"
    ]
    assert state.calls[1][1]["p_expected_source_revision"] == preview_revision


def mode(**updates):
    return dict(id="context_swap", label="Context", description="Fixture mode",
                question_count=1, is_available=True, **updates)


@pytest.mark.parametrize("production_status", ["pending", "running", "failed"])
def test_status_states_keep_modes_null_from_single_rpc(flow, production_status):
    state, client = flow
    assert client.post(url(state), json={"source_revision": state.revision}).status_code == 200
    state.production_status = production_status
    state.calls.clear()
    response = client.get(url(state, "source-artifacts"))
    assert response.status_code == 200, response.text
    assert response.json()["canonical_status"] == production_status
    assert response.json()["supported_modes"] is None
    assert [name for name, _ in state.calls] == ["get_source_artifacts"]


def test_canonical_mode_object_shape_is_preserved(flow):
    state, client = flow
    assert client.post(url(state), json={"source_revision": state.revision}).status_code == 200
    state.ready, state.supported_modes = True, [mode()]
    state.calls.clear()
    response = client.get(url(state, "source-artifacts"))
    assert response.status_code == 200
    assert response.json()["supported_modes"] == [mode()]
    assert len(state.calls) == 1


@pytest.mark.parametrize("modes", [
    None, ["context_swap"], [{}],
    [dict(mode(), id="SHUFFLE")],
    [dict(mode(), question_count=True)],
    [dict(mode(), question_count=2)],
    [dict(mode(), is_available=False)],
    [dict(mode(), is_available="true")],
    [dict(mode(), label=1)], [mode(), mode()],
])
def test_ready_mode_contract_invalid_fails_closed(flow, modes):
    state, client = flow
    assert client.post(url(state), json={"source_revision": state.revision}).status_code == 200
    state.ready, state.supported_modes = True, modes
    assert client.get(url(state, "source-artifacts")).status_code == 503


def test_pending_cannot_advertise_even_empty_mode_array(flow):
    state, client = flow
    assert client.post(url(state), json={"source_revision": state.revision}).status_code == 200
    state.supported_modes = []
    assert client.get(url(state, "source-artifacts")).status_code == 503


def test_ready_requires_per_question_production_evidence(flow, monkeypatch):
    from app.services.blueprint.producer import SourceArtifactRepository
    state, client = flow
    assert client.post(url(state), json={"source_revision": state.revision}).status_code == 200
    state.ready, state.supported_modes = True, []
    original = SourceArtifactRepository._call

    async def corrupt(self, name, params):
        data = await original(self, name, params)
        if name == "get_source_artifacts":
            data["production"] = []
        return data

    monkeypatch.setattr(SourceArtifactRepository, "_call", corrupt)
    assert client.get(url(state, "source-artifacts")).status_code == 503

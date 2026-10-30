from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.api.routes.generation_jobs import create_generation_job_router
from app.core.rate_limit import create_limiter, register_rate_limiter
from app.models.schemas import CurrentUser
from app.services.generation.job_contracts import GenerationJobError
from app.services.generation.jobs import GenerationJobRunner


@pytest.fixture
def job_api(monkeypatch):
    sid, uid = uuid4(), uuid4()
    runner = MagicMock(spec=GenerationJobRunner)
    plan = MagicMock()
    runner.claim = AsyncMock(return_value=plan)
    runner.run = AsyncMock()
    store = MagicMock()
    factory = MagicMock(return_value=store)
    ownership = MagicMock()
    monkeypatch.setattr("app.api.routes.generation_jobs.assert_ownership", ownership)
    app = FastAPI()
    limiter = create_limiter()
    register_rate_limiter(app, limiter_instance=limiter)
    app.include_router(
        create_generation_job_router(factory, runner=runner, limiter_instance=limiter),
        prefix="/api/sessions",
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=str(uid), email="fixture@example.test", access_token="fixture"
    )
    app.dependency_overrides[get_user_db] = lambda: store
    with TestClient(app) as client:
        yield client, sid, runner, factory, ownership, app, plan, store


@pytest.mark.parametrize("path,retry", [("generate", False), ("retry-generation", True)])
def test_start_and_retry_claim_before_scheduling(job_api, path: str, retry: bool) -> None:
    client, sid, runner, factory, ownership, app, plan, store = job_api
    response = client.post(f"/api/sessions/{sid}/{path}")
    assert response.status_code == 202
    assert response.json() == {"session_id": str(sid), "status": "generating"}
    runner.claim.assert_awaited_once_with(store, sid, retry=retry)
    runner.run.assert_awaited_once_with(plan, store)
    ownership.assert_called_once()


def test_missing_auth_stops_before_claim(job_api) -> None:
    client, sid, runner, factory, ownership, app, plan, store = job_api
    del app.dependency_overrides[get_current_user]
    response = client.post(f"/api/sessions/{sid}/generate")
    assert response.status_code == 401
    factory.assert_not_called()
    runner.claim.assert_not_awaited()


def test_non_owner_does_not_schedule_job(job_api) -> None:
    client, sid, runner, factory, ownership, app, plan, store = job_api
    ownership.side_effect = HTTPException(403, "Forbidden")
    assert client.post(f"/api/sessions/{sid}/generate").status_code == 403
    factory.assert_not_called()
    runner.run.assert_not_awaited()


def test_duplicate_state_conflict_does_not_schedule_job(job_api) -> None:
    client, sid, runner, factory, ownership, app, plan, store = job_api
    runner.claim.side_effect = GenerationJobError(
        409, "ERR_ALREADY_GENERATING", "Already generating."
    )
    response = client.post(f"/api/sessions/{sid}/generate")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_ALREADY_GENERATING"
    runner.run.assert_not_awaited()


def test_unknown_storage_errors_do_not_leak_or_auto_retry(job_api) -> None:
    client, sid, runner, factory, ownership, app, plan, store = job_api
    runner.claim.side_effect = HTTPException(502, "private credential")
    response = client.post(f"/api/sessions/{sid}/generate")
    assert response.status_code == 503 and "private" not in response.text
    assert runner.claim.await_count == 1
    runner.run.assert_not_awaited()


def test_generate_and_retry_share_quota_across_session_ids(job_api) -> None:
    client, sid, runner, factory, ownership, app, plan, store = job_api
    for index in range(10):
        path = "generate" if index % 2 else "retry-generation"
        assert client.post(f"/api/sessions/{uuid4()}/{path}").status_code == 202
    response = client.post(f"/api/sessions/{sid}/generate")
    assert response.status_code == 429 and int(response.headers["Retry-After"]) >= 1
    assert runner.claim.await_count == 10

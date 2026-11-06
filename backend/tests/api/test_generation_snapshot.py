import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.api.routes.generation_snapshot import create_generation_snapshot_router
from app.models.generation_events import GenerationEventData
from app.models.schemas import CurrentUser
from app.services.generation.events import GenerationEventBroker


class SnapshotDB:
    def __init__(self, session_id, snapshot_id):
        self.session_id = session_id
        self.snapshot_id = snapshot_id
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        assert name == "load_generation_completed_results"
        result = {
            "session_id": str(self.session_id),
            "snapshot_id": str(self.snapshot_id),
            "context": {"n_versions": 2, "confirmed_sources": [{"question_no": 1}]},
            "completed": [{"version_index": 1, "question_no": 1, "is_success": True}],
            "failures": [{"version_index": 2, "question_no": 1, "is_success": False}],
        }
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=result))

    def table(self, name):
        assert name == "exam_sessions"
        return self

    def select(self, *args):
        return self

    def eq(self, *args):
        return self

    def limit(self, *args):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"id": str(self.session_id), "status": "partial_generated"}])


def test_snapshot_projects_durable_partial_progress_and_replay_mark(monkeypatch):
    session_id, user_id, snapshot_id = uuid4(), uuid4(), uuid4()
    db = SnapshotDB(session_id, snapshot_id)
    broker = GenerationEventBroker()
    asyncio.run(
        broker.publish(
            session_id,
            "progress",
            GenerationEventData(
                timestamp=datetime.now(timezone.utc),
                status="generating",
                percent_complete=0,
            ),
        )
    )
    app = FastAPI()
    app.include_router(create_generation_snapshot_router(broker), prefix="/api/sessions")
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=str(user_id), email="fixture@example.test", access_token="fixture"
    )
    app.dependency_overrides[get_user_db] = lambda: db
    monkeypatch.setattr("app.api.routes.generation_snapshot.assert_ownership", lambda *a, **k: None)
    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{session_id}/generation-snapshot")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["session_status"] == "partial_generated"
    assert data["progress"]["completed_count"] == 1
    assert data["progress"]["total_count"] == 2
    assert data["progress"]["percent_complete"] == 50
    assert data["question_statuses"]["1-1"]["status"] == "done"
    assert data["question_statuses"]["2-1"]["status"] == "failed"
    assert data["stream_epoch"] == broker.epoch
    assert data["resume_after_event_id"] == 1
    assert db.calls == [("load_generation_completed_results", {"p_session_id": str(session_id)})]

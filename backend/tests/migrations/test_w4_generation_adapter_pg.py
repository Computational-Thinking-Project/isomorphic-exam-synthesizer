"""Run the HTTP adapters and worker against disposable PostgreSQL 002–019.

The client bridge uses real SQL roles and RPCs with fixture authentication.
It does not exercise PostgREST, JWT transport, or a live AI provider.
"""

import asyncio
import json
from concurrent.futures import Future
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.api.dependencies import get_current_user, get_user_db
from app.api.routes import (
    generation_config,
    generation_jobs,
    generation_snapshot,
    generation_stream,
    sessions,
)
from app.core.rate_limit import create_limiter, register_rate_limiter
from app.models.generation import BatchResult, QuestionResult
from app.models.schemas import CurrentUser
from app.services.generation.ai_batch_adapter import AIBatchAdapter
from app.services.generation.config_repository import GenerationConfigRepository
from app.services.generation.events import GenerationEventBroker
from app.services.generation.job_repository import GenerationJobRepository
from app.services.generation.jobs import GenerationJobRunner
from app.services.generation.tickets import StreamTicketStore
from app.services.observability.runtime_registry import RuntimeRegistry
from tests.migrations.test_generation_w2 import OWNER, TYPES, asyncpg, result_for, role, rpc
from tests.migrations.test_generation_w2 import db as db  # noqa: F401
from tests.migrations.test_w4_config_guards import OFF, migrate, publish

pytestmark = [pytest.mark.asyncio, pytest.mark.parametrize("db", ["w4"], indirect=True)]
FOREIGN = "00000000-0000-0000-0000-000000000002"
RPC_ARGS = {
    "get_session_source_preview": ("p_session_id",),
    "get_generation_source_snapshot": ("p_session_id",),
    "save_generation_config": (
        "p_session_id", "p_n_versions", "p_active_variation_modes", "p_ordering_preferences",
        "p_expected_snapshot",
    ),
    "fail_stale_generation_job": ("p_session_id", "p_cutoff_seconds"),
    "claim_generation_job": ("p_session_id", "p_is_retry"),
    "load_generation_completed_results": ("p_session_id",),
    "reserve_generation_quota": ("p_session_id", "p_calls_requested", "p_job_token"),
    "persist_generation_clone": ("p_session_id", "p_job_token", "p_clone_record"),
    "persist_generation_result": (
        "p_session_id", "p_job_token", "p_version_index", "p_source_question_id",
        "p_question_no", "p_is_success", "p_error_code", "p_attempts", "p_seed",
        "p_request_fingerprint", "p_raw_result", "p_content", "p_options", "p_correct_key",
        "p_solution_md", "p_has_warning",
    ),
    "finish_generation_job": ("p_session_id", "p_outcome", "p_job_token"),
    "finish_generation_job_with_error": ("p_session_id", "p_outcome", "p_job_token", "p_error_code"),
}


class SqlClient:
    def __init__(self, connection, loop, session_id):
        self.connection = connection
        self.loop = loop
        self.session_id = session_id
        self.calls: list[tuple[str, dict]] = []
        self.damage_claim = False

    def execute_sql(self, coroutine):
        future: Future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return SimpleNamespace(data=future.result(timeout=10))
        except asyncpg.PostgresError as exc:
            raise APIError({"code": exc.sqlstate, "message": exc.message}) from exc

    def rpc(self, name, params):
        self.calls.append((name, params))
        assert params["p_session_id"] == self.session_id
        names = RPC_ARGS[name]
        assert set(params) == set(names)

        def execute():
            result = self.execute_sql(rpc(self.connection, name, *(params[key] for key in names)))
            if self.damage_claim and name == "claim_generation_job":
                result.data["context"]["mapping_version"] = "corrupted"
            return result

        return SimpleNamespace(execute=execute)

    def table(self, name):
        assert name in {"exam_sessions", "exam_versions", "generation_configs"}
        return SqlRead(self, name)


class SqlRead:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.columns = "*"
        self.limit_rows = None

    def select(self, columns):
        self.columns = columns
        return self

    def eq(self, key, value):
        assert key == ("id" if self.table == "exam_sessions" else "session_id")
        assert value == self.client.session_id
        return self

    def order(self, key, *, desc):
        assert self.table == "exam_versions" and key == "created_at" and not desc
        return self

    def limit(self, rows):
        self.limit_rows = rows
        return self

    def execute(self):
        async def read():
            key = "id" if self.table == "exam_sessions" else "session_id"
            rows = await self.client.connection.fetch(
                f"SELECT to_jsonb(t) FROM {self.table} t WHERE {key} = $1::uuid ORDER BY created_at",
                self.client.session_id,
            )
            result = [json.loads(row[0]) for row in rows[:self.limit_rows]]
            if self.columns != "*":
                result = [{key: row[key] for key in self.columns.split(",")} for row in result]
            return result

        return self.client.execute_sql(read())


async def test_save_reload_claim_and_run_on_postgres(db, monkeypatch):
    await run_generation_case(db, monkeypatch, clone=False, partial_first=True)


async def test_original_clone_uses_no_provider_and_persists_on_postgres(db, monkeypatch):
    await run_generation_case(db, monkeypatch, clone=True)


async def test_corrupt_claim_is_rejected_and_durable_job_recovers(db, monkeypatch):
    await run_generation_case(db, monkeypatch, clone=True, corrupt_claim=True)


async def run_generation_case(db, monkeypatch, *, clone, corrupt_claim=False, partial_first=False):
    for name, types in (
        ("get_session_source_preview", ["uuid"]),
        ("fail_stale_generation_job", ["uuid", "int"]),
        ("finish_generation_job_with_error", ["uuid", "text", "uuid", "text"]),
    ):
        monkeypatch.setitem(TYPES, name, types)
    await migrate(db)
    snapshot = await publish(db, clone=clone)
    loop = asyncio.get_running_loop()
    owner = SqlClient(db.owner, loop, db.sid)
    worker = SqlClient(db.worker, loop, db.sid)
    owner.damage_claim = corrupt_claim
    monkeypatch.setattr("app.services.generation.job_repository.get_service_role_client", lambda: worker)
    foreign_conn = await asyncpg.connect(db.dsn)
    await role(foreign_conn, "authenticated", FOREIGN)
    foreign = SqlClient(foreign_conn, loop, db.sid)

    provider_calls = []

    async def fake_batch(sources, _blueprints, **kwargs):
        assert kwargs["variation_modes"]
        assert kwargs["n_versions"] == 1
        assert [source.id for source in sources] == snapshot["source_order"]
        cached = {result.source_question_id: result for result in kwargs["completed"]}
        first_run_is_partial = partial_first and not provider_calls
        results = []
        for index, source in enumerate(sources):
            if source.id in cached:
                results.append(cached[source.id])
                continue
            await kwargs["context"].reserve_request()
            provider_calls.append(index)
            result = QuestionResult.model_validate(result_for(
                db, {"context": snapshot}, index=index, success=not (first_run_is_partial and index == 1),
            ))
            await kwargs["on_result"](result)
            results.append(result)
        return BatchResult(status="partial_generated" if first_run_is_partial else "generated", results=results)

    registry = RuntimeRegistry()
    events = GenerationEventBroker()
    tickets = StreamTicketStore()
    runner = GenerationJobRunner(
        None, events, registry, batch=AIBatchAdapter(SimpleNamespace(generate_exam_drafts=fake_batch))
    )

    async def is_owner(session_id, user_id):
        return session_id == UUID(db.sid) and user_id == UUID(OWNER)

    app = FastAPI()
    limiter = create_limiter()
    register_rate_limiter(app, limiter_instance=limiter)
    for router in (
        generation_config.create_generation_config_router(GenerationConfigRepository, limiter_instance=limiter),
        generation_jobs.create_generation_job_router(
            GenerationJobRepository, runner=runner, limiter_instance=limiter
        ),
        generation_snapshot.create_generation_snapshot_router(events),
        generation_stream.create_generation_stream_router(
            tickets=tickets, events=events, registry=registry, is_current_owner=is_owner,
            limiter_instance=limiter,
        ),
    ):
        app.include_router(router, prefix="/api/sessions")
    app.add_api_route("/api/sessions/{session_id}", sessions.get_session_detail, methods=["GET"])

    def use_identity(db_client, user_id):
        app.dependency_overrides[get_user_db] = lambda: db_client
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=user_id, email="fixture@example.test", access_token="fixture",
        )

    def exercise_http():
        registry.start()
        base = f"/api/sessions/{db.sid}"
        request = {"n_versions": 1, "active_variation_modes": [], "ordering_preferences": OFF}
        with TestClient(app) as client:
            use_identity(foreign, FOREIGN)
            assert client.post(base + "/config", json=request).status_code in {403, 404}
            assert client.post(base + "/generate").status_code in {403, 404}
            assert foreign.calls == []
            use_identity(owner, OWNER)
            response = client.post(base + "/config", json=request)
            assert response.status_code == 200, response.text
            config = response.json()["config"]
            assert config["n_versions"] == 1 and config["ordering_preferences"] == OFF
            assert config["source_manifest"] == snapshot["manifest"]
            assert bool(config["active_variation_modes"]) == (not clone)
            detail = client.get(base)
            assert detail.status_code == 200, detail.text
            assert detail.json()["blueprint_summary"]["is_ready"] is True
            saved = detail.json()["generation_config"]
            assert all(saved[key] == value for key, value in config.items())
            response = client.post(base + "/generate")
            if corrupt_claim:
                assert response.status_code == 503, response.text
                assert response.json()["detail"]["code"] == "ERR_GENERATION_STORAGE_FAILURE"
                assert client.post(base + "/retry-generation").status_code == 409
                return
            assert response.status_code == 202, response.text
            if partial_first:
                first = client.get(base + "/generation-snapshot").json()
                assert first["status"] == "partial_generated"
                assert first["progress"]["completed_count"] == 1
                retry = client.post(base + "/retry-generation")
                assert retry.status_code == 202, retry.text
            response = client.get(base + "/generation-snapshot")
            assert response.status_code == 200, response.text
            progress = response.json()
            assert progress["status"] == "generated"
            assert progress["progress"]["completed_count"] == len(snapshot["source_order"])
            ticket = client.post(base + "/events/ticket", params={"stream_epoch": progress["stream_epoch"]})
            assert ticket.status_code == 200, ticket.text
            stream = client.get(base + "/events", params={"ticket": ticket.json()["ticket"]})
            assert stream.status_code == 200
            assert stream.text.count("event: question_done") == len(snapshot["source_order"])
            assert "event: done" in stream.text

    try:
        await asyncio.to_thread(exercise_http)
        persisted = await rpc(db.worker, "load_generation_completed_results", db.sid)
        if corrupt_claim:
            assert not provider_calls and persisted["completed"] == []
            state = await db.admin.fetchrow(
                "SELECT status, active_job_id FROM exam_sessions WHERE id=$1::uuid", db.sid
            )
            assert state["status"] == "generating" and state["active_job_id"] is not None
            await db.admin.execute(
                "UPDATE exam_sessions SET generation_last_activity_at = clock_timestamp() - interval '800 seconds' "
                "WHERE id=$1::uuid", db.sid
            )
            recovered = await rpc(db.worker, "fail_stale_generation_job", db.sid, 720)
            assert recovered["stale_job_recovered"] and recovered["old_active_job_id"] == str(state["active_job_id"])
            retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
            assert retry["snapshot_id"] == persisted["snapshot_id"]
            assert retry["job_id"] != str(state["active_job_id"])
            with pytest.raises(asyncpg.PostgresError) as exc:
                await rpc(db.worker, "reserve_generation_quota", db.sid, 1, state["active_job_id"])
            assert exc.value.sqlstate == "55006"
        else:
            result_kind = "ORIGINAL_CLONE" if clone else "AI_RESULT"
            assert [row["result_kind"] for row in persisted["completed"]] == [result_kind] * 2
            assert await db.admin.fetchval("SELECT count(*) FROM version_questions WHERE is_current") == 2
            expected_calls = [] if clone else ([0, 1, 1] if partial_first else [0, 1])
            assert provider_calls == expected_calls
            assert await db.admin.fetchval(
                "SELECT gemini_call_count FROM exam_sessions WHERE id=$1::uuid", db.sid
            ) == len(provider_calls)
    finally:
        await foreign_conn.close()

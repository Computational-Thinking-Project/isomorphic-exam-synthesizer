"""Run the HTTP adapters and worker against disposable PostgreSQL through 021.

The client bridge uses real SQL roles and RPCs with fixture authentication.
It does not exercise PostgREST, JWT transport, or a live AI provider.
"""

import asyncio
import json
from concurrent.futures import Future
from pathlib import Path
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
from app.models.schemas import CurrentUser, SourceQuestion
from app.services.blueprint.adapters import source_to_item
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
FALLBACK_SQL = (
    Path(__file__).resolve().parents[2] / "migrations/021_w4_confirmed_source_fallback.sql"
)
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
        self.lose_fallback_response = False

    def execute_sql(self, coroutine):
        future: Future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return SimpleNamespace(data=future.result(timeout=10))
        except asyncpg.PostgresError as exc:
            raise APIError({"code": exc.sqlstate, "message": exc.message, "details": exc.detail}) from exc

    def rpc(self, name, params):
        self.calls.append((name, params))
        assert params["p_session_id"] == self.session_id
        names = RPC_ARGS[name]
        assert set(params) == set(names)

        def execute():
            result = self.execute_sql(rpc(self.connection, name, *(params[key] for key in names)))
            if self.damage_claim and name == "claim_generation_job":
                result.data["context"]["mapping_version"] = "corrupted"
            if self.lose_fallback_response and name == "persist_generation_result" and (
                params["p_raw_result"].get("result_kind") == "CONFIRMED_SOURCE_FALLBACK"
            ):
                self.lose_fallback_response = False
                raise TimeoutError("Fixture dropped committed fallback response.")
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


@pytest.mark.parametrize("lost_response", [False, True])
async def test_fallback_retry_uses_current_021_receipt(db, monkeypatch, lost_response):
    await run_generation_case(
        db, monkeypatch, clone=False, partial_first=True, fallback_first=True,
        lost_response=lost_response,
    )


@pytest.mark.parametrize("retry", [False, True])
async def test_q01_characterizes_missing_solution_claim_on_021(db, monkeypatch, retry):
    await run_generation_case(db, monkeypatch, clone=True, missing_solution=True, retry_missing=retry)


async def run_generation_case(
    db, monkeypatch, *, clone, corrupt_claim=False, partial_first=False,
    fallback_first=False, lost_response=False, missing_solution=False, retry_missing=False,
):
    for name, types in (
        ("get_session_source_preview", ["uuid"]),
        ("fail_stale_generation_job", ["uuid", "int"]),
        ("finish_generation_job_with_error", ["uuid", "text", "uuid", "text"]),
    ):
        monkeypatch.setitem(TYPES, name, types)
    await migrate(db)
    await db.admin.execute(FALLBACK_SQL.read_text(encoding="utf-8-sig"))
    for index, row in enumerate(db.rows):
        solution = "" if missing_solution and index == 1 else "Count valid placements and multiply the probability by 3190."
        row["solution_md"] = solution
        source = SourceQuestion(
            id=row["id"], question_text=row["raw_content"], options=row["options"],
            correct_answer=row["correct_key"], solution=solution,
        )
        db.blueprints[index]["requirement"]["source"] = source_to_item(source)["source"]
        await db.admin.execute(
            "UPDATE source_questions SET solution_md = $1 WHERE id = $2::uuid", solution, row["id"]
        )
    snapshot = await publish(db, clone=clone)
    if missing_solution:
        assert snapshot["confirmed_sources"][1]["confirmed_input"]["solution"] == ""
    loop = asyncio.get_running_loop()
    owner = SqlClient(db.owner, loop, db.sid)
    worker = SqlClient(db.worker, loop, db.sid)
    owner.damage_claim = corrupt_claim
    worker.lose_fallback_response = lost_response
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
        committed_fallbacks = kwargs.get("committed_fallbacks", frozenset())
        first_run_is_partial = partial_first and not provider_calls
        results = []
        for index, source in enumerate(sources):
            if (1, source.id) in committed_fallbacks:
                continue
            if source.id in cached:
                results.append(cached[source.id])
                continue
            fallback = fallback_first and first_run_is_partial and index == 0
            for _ in range(4 if fallback else 1):
                await kwargs["context"].reserve_request()
                provider_calls.append(index)
            result = QuestionResult.model_validate(result_for(
                db, {"context": snapshot}, index=index,
                success=not (fallback or (first_run_is_partial and index == 1)),
            ))
            if fallback:
                result.attempts = 4
                result.error_code = "VALIDATION_FAILED"
                result._exhausted_attempts = True
            await kwargs["on_result"](result)
            results.append(result)
        status = "failed" if fallback_first and first_run_is_partial else (
            "partial_generated" if first_run_is_partial else "generated"
        )
        return BatchResult(status=status, results=results)

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
            if missing_solution:
                # 021 has no Q01 gate. HTTP accepts the claim, then the worker fails closed.
                assert response.status_code == 202, response.text
                if retry_missing:
                    retry = client.post(base + "/retry-generation")
                    assert retry.status_code == 202, retry.text
                progress = client.get(base + "/generation-snapshot").json()
                assert progress["status"] == "failed"
                assert progress["generation_error_code"] == "ERR_SOURCE_SOLUTION_REQUIRED"
                assert progress["progress"]["completed_count"] == 1
                return
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
            if fallback_first:
                assert stream.text.count("GENERATION_RETRIES_EXHAUSTED") == 1

    try:
        await asyncio.to_thread(exercise_http)
        persisted = await rpc(db.worker, "load_generation_completed_results", db.sid)
        if missing_solution:
            assert not provider_calls and len(persisted["completed"]) == 1
            claims = [params["p_is_retry"] for name, params in owner.calls if name == "claim_generation_job"]
            assert claims == ([False, True] if retry_missing else [False])
            assert await db.admin.fetchval("SELECT count(*) FROM generation_job_snapshots") == 1
            assert await db.admin.fetchval("SELECT count(*) FROM version_questions WHERE is_current") == 1
        elif corrupt_claim:
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
            expected_kinds = ["CONFIRMED_SOURCE_FALLBACK", "AI_RESULT"] if fallback_first else [result_kind] * 2
            assert [row["result_kind"] for row in persisted["completed"]] == expected_kinds
            if fallback_first:
                assert len(persisted["fallback_receipts"]) == 1
                assert persisted["fallback_receipts"][0]["raw_result"]["solution_md"] == db.rows[0]["solution_md"]
                writes = [params for name, params in worker.calls if name == "persist_generation_result"]
                assert len([p for p in writes if p["p_raw_result"].get("result_kind") == expected_kinds[0]]) == 1
            assert await db.admin.fetchval("SELECT count(*) FROM version_questions WHERE is_current") == 2
            expected_calls = [] if clone else ([0, 1, 1] if partial_first else [0, 1])
            if fallback_first:
                expected_calls = [0, 0, 0, 0, 1, 1]
            assert provider_calls == expected_calls
            assert await db.admin.fetchval(
                "SELECT gemini_call_count FROM exam_sessions WHERE id=$1::uuid", db.sid
            ) == len(provider_calls)
    finally:
        await foreign_conn.close()

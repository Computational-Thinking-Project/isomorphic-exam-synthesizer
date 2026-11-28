"""EXT-02 Step 3: backend confirmation of shuffle-only copies (migration 028b) on PostgreSQL.

Uses the opt-in disposable W2 fixture (RUN_TASK207_REAL_DB_TESTS). No cloud keys or live AI.
"""

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from tests.migrations.test_generation_mode_pg import migrate as migrate_028
from tests.migrations.test_generation_mode_pg import quota, save
from tests.migrations.test_generation_w2 import (
    OWNER,
    ROOT,
    TYPES,
    asyncpg,
    persist,
    result_for,
    role,
    rpc,
)
from tests.migrations.test_generation_w2 import db as db  # noqa: F401
from tests.migrations.test_per_question_generation import clone_record
from tests.migrations.test_w4_config_guards import publish

pytestmark = [pytest.mark.asyncio, pytest.mark.parametrize("db", ["w4"], indirect=True)]
SQL_028B = ROOT / "backend/migrations/028b_ext02_shuffle_only_confirm.sql"
TYPES["confirm_shuffle_only_copies"] = ["uuid"]
TYPES["review_accept_question"] = ["uuid", "uuid", "uuid"]


async def migrate(db, *, with_028b=True):
    await migrate_028(db)
    if with_028b:
        await db.admin.execute(SQL_028B.read_text(encoding="utf-8"))


async def generated_shuffle_only(db, versions=2, *, finish=True):
    """Claim a shuffle-only job and persist every clone slot through the RPCs."""
    await save(db, await publish(db), versions=versions, mode="shuffle_only")
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    for version in range(1, versions + 1):
        for index in range(len(db.rows)):
            await rpc(db.worker, "persist_generation_clone", db.sid, job["job_id"],
                      clone_record(job, index=index, version=version))
    if finish:
        await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    return job


async def state(db):
    """Everything confirmation may change; failures must leave it identical."""
    return await db.admin.fetchval(
        "SELECT jsonb_build_object('status',(SELECT status FROM exam_sessions WHERE id=$1::uuid),"
        "'questions',(SELECT jsonb_agg(jsonb_build_object('id',q.id,'status',q.status,'current',q.is_current)"
        " ORDER BY q.id) FROM version_questions q JOIN exam_versions v ON v.id=q.version_id"
        " WHERE v.session_id=$1::uuid))",
        db.sid,
    )


async def ready(db):
    snapshot = json.loads(await db.owner.fetchval("SELECT get_review_current_snapshot($1::uuid)", db.sid))
    return snapshot["progress"]["ready"]


async def test_confirm_moves_generated_copies_to_reviewed_and_replays(db):
    await migrate(db)
    await generated_shuffle_only(db)
    assert await ready(db) is False
    first = await rpc(db.owner, "confirm_shuffle_only_copies", db.sid)
    assert first["session_status"] == "reviewed" and first["replayed"] is False
    assert first["confirmed_slots"] == 4 and first["progress"]["ready"] is True
    assert await ready(db) is True
    after = await state(db)
    assert {q["status"] for q in json.loads(after)["questions"]} == {"approved"}
    second = await rpc(db.worker, "confirm_shuffle_only_copies", db.sid)  # worker retry
    assert second["replayed"] is True and second["session_status"] == "reviewed"
    assert await state(db) == after
    assert await quota(db) == 0


async def assert_rejected(db, match, conn=None):
    before = await state(db)
    with pytest.raises(asyncpg.PostgresError, match=match):
        await rpc(conn or db.owner, "confirm_shuffle_only_copies", db.sid)
    assert await state(db) == before


async def test_ai_generation_job_is_rejected(db):
    await migrate(db)
    await save(db, await publish(db), versions=1)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    for index in range(2):
        await persist(db, job, result_for(db, job, index=index))
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    await assert_rejected(db, "ERR_MODE_NOT_SHUFFLE_ONLY")


async def test_missing_slot_is_rejected(db):
    await migrate(db)
    job = await generated_shuffle_only(db, finish=False)
    await rpc(db.worker, "finish_generation_job", db.sid, "partial_generated", job["job_id"])
    await assert_rejected(db, "ERR_SHUFFLE_ONLY_NOT_READY")  # partial_generated status
    # Even a forged 'generated' status cannot confirm an incomplete copy set.
    await db.admin.execute(
        "DELETE FROM generation_target_results WHERE session_id=$1::uuid AND version_index=2", db.sid
    )
    await db.admin.execute(
        "DELETE FROM version_questions q USING exam_versions v WHERE v.id=q.version_id"
        " AND v.session_id=$1::uuid AND v.version_code='102'", db.sid,
    )
    await db.admin.execute("UPDATE exam_sessions SET status='generated' WHERE id=$1::uuid", db.sid)
    await assert_rejected(db, "ERR_SHUFFLE_ONLY_NOT_READY")


@pytest.mark.parametrize(
    "tamper",
    [
        # Canonical columns and clone fingerprints are already protected by table
        # constraints; these cases change what the constraints still allow.
        "UPDATE generation_target_results SET result_kind='AI_RESULT',clone_fingerprint=NULL,"
        "request_fingerprint=repeat('a',64) WHERE id=(SELECT id FROM generation_target_results LIMIT 1)",
        "UPDATE version_questions SET correct_key='D' WHERE id=(SELECT id FROM version_questions LIMIT 1)",
        "UPDATE version_questions SET solution_md='x' WHERE id=(SELECT id FROM version_questions LIMIT 1)",
        "UPDATE version_questions SET options='[\"1\",\"2\",\"3\",\"4\"]' WHERE id=(SELECT id FROM version_questions LIMIT 1)",
        "UPDATE version_questions SET status='regenerating' WHERE id=(SELECT id FROM version_questions LIMIT 1)",
    ],
)
async def test_mismatched_copies_are_rejected(db, tamper):
    await migrate(db)
    await generated_shuffle_only(db)
    await db.admin.execute(tamper)
    await assert_rejected(db, "ERR_SHUFFLE_ONLY_NOT_READY|ERR_CONFIG_CONFLICT")


async def test_active_review_operation_is_rejected(db):
    await migrate(db)
    await generated_shuffle_only(db)
    question = await db.admin.fetchval("SELECT id FROM version_questions LIMIT 1")
    await db.admin.execute(
        "INSERT INTO review_operations(operation_id,session_id,question_id,actor_id,prior_status,snapshot,reservation_result)"
        " VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'pending_review','{}','{}')",
        str(uuid4()), db.sid, question, OWNER,
    )
    await assert_rejected(db, "REVIEW_BUSY")


@pytest.mark.parametrize(("status", "match"), [("generating", "ERR_SHUFFLE_ONLY_NOT_READY"), ("approved", "REVIEW_LOCKED")])
async def test_wrong_status_is_rejected(db, status, match):
    await migrate(db)
    await generated_shuffle_only(db)
    job_id = "gen_random_uuid()" if status == "generating" else "active_job_id"
    await db.admin.execute(
        f"UPDATE exam_sessions SET status='{status}',active_job_id={job_id} WHERE id=$1::uuid", db.sid
    )
    await assert_rejected(db, match)


async def test_foreign_user_and_anon_cannot_confirm(db):
    await migrate(db)
    await generated_shuffle_only(db)
    await role(db.owner, "authenticated", str(uuid4()))
    await assert_rejected(db, "Access denied")
    await role(db.owner, "anon", str(uuid4()))
    await assert_rejected(db, "permission denied")
    for principal, allowed in [("anon", False), ("authenticated", True), ("service_role", True)]:
        assert await db.admin.fetchval(
            "SELECT has_function_privilege($1,'public.confirm_shuffle_only_copies(uuid)','EXECUTE')", principal
        ) == allowed


async def test_manual_accept_blocked_in_shuffle_only_and_old_receipt_replays(db):
    await migrate(db, with_028b=False)
    await generated_shuffle_only(db)
    question = await db.admin.fetchval("SELECT id::text FROM version_questions ORDER BY id LIMIT 1")
    action = str(uuid4())
    receipt = await rpc(db.owner, "review_accept_question", db.sid, question, action)
    await db.admin.execute(SQL_028B.read_text(encoding="utf-8"))
    replay = await rpc(db.owner, "review_accept_question", db.sid, question, action)
    assert replay == {**receipt, "replayed": True}
    other = await db.admin.fetchval("SELECT id::text FROM version_questions ORDER BY id OFFSET 1 LIMIT 1")
    with pytest.raises(asyncpg.PostgresError, match="ERR_MODE_SHUFFLE_ONLY"):
        await rpc(db.owner, "review_accept_question", db.sid, other, str(uuid4()))
    # The confirmation still completes the remaining copies.
    result = await rpc(db.owner, "confirm_shuffle_only_copies", db.sid)
    assert result["session_status"] == "reviewed" and result["progress"]["ready"] is True


async def test_manual_accept_still_works_in_ai_generation(db):
    await migrate(db)
    await save(db, await publish(db), versions=1)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    for index in range(2):
        await persist(db, job, result_for(db, job, index=index))
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    for question in await db.admin.fetch("SELECT id::text FROM version_questions"):
        await rpc(db.owner, "review_accept_question", db.sid, question["id"], str(uuid4()))
    assert await db.admin.fetchval("SELECT status FROM exam_sessions WHERE id=$1::uuid", db.sid) == "reviewed"


async def test_worker_confirms_shuffle_only_without_ai_then_shuffle_and_export(db, monkeypatch):
    """Real job runner: clone path, automatic confirmation, then the normal shuffle/approve/export."""
    from app.services.exporter.snapshot_adapter import load_approved_export_snapshot
    from app.services.finalize.shuffle_input import prepare_shuffle
    from app.services.generation.ai_batch_adapter import AIBatchAdapter
    from app.services.generation.events import GenerationEventBroker
    from app.services.generation.job_repository import GenerationJobRepository
    from app.services.generation.jobs import GenerationJobRunner
    from app.services.generation.service import GenerationService
    from app.services.observability.runtime_registry import RuntimeRegistry
    from tests.migrations.test_export_snapshot_pg import SqlReadClient
    from tests.migrations.test_w4_generation_adapter_pg import RPC_ARGS, SqlClient

    monkeypatch.setitem(TYPES, "finish_generation_job_with_error", ["uuid", "text", "uuid", "text"])
    monkeypatch.setitem(TYPES, "fail_stale_generation_job", ["uuid", "int"])
    monkeypatch.setitem(RPC_ARGS, "confirm_shuffle_only_copies", ("p_session_id",))
    await migrate(db)
    await save(db, await publish(db), versions=2, mode="shuffle_only")
    loop = asyncio.get_running_loop()

    class SerialSqlClient(SqlClient):
        def __init__(self, *args):
            super().__init__(*args)
            self.lock = asyncio.Lock()

        def execute_sql(self, coroutine):
            async def serialized():
                async with self.lock:
                    return await coroutine

            return super().execute_sql(serialized())

    owner, worker = SerialSqlClient(db.owner, loop, db.sid), SerialSqlClient(db.worker, loop, db.sid)
    monkeypatch.setattr("app.services.generation.job_repository.get_service_role_client", lambda: worker)
    service = GenerationService(SimpleNamespace(model="fixture"))
    ai_calls = []

    async def forbidden(*args, **kwargs):
        ai_calls.append(args)
        raise AssertionError("shuffle_only must not call the AI generator")

    monkeypatch.setattr(service, "_generate", forbidden)
    registry = RuntimeRegistry()
    registry.start()
    runner = GenerationJobRunner(None, GenerationEventBroker(), registry, batch=AIBatchAdapter(service))
    store = GenerationJobRepository(owner)
    plan = await runner.claim(store, UUID(db.sid))
    outcome = await runner.run(plan, store)
    assert outcome.status == "generated", outcome
    assert ai_calls == [] and await quota(db) == 0
    assert any(name == "confirm_shuffle_only_copies" for name, _ in worker.calls)
    assert not any(name == "reserve_generation_quota" for name, _ in worker.calls + owner.calls)
    assert await db.admin.fetchval("SELECT status FROM exam_sessions WHERE id=$1::uuid", db.sid) == "reviewed"
    assert await ready(db) is True

    async def rows(table):
        return [json.loads(row[0]) for row in await db.owner.fetch(f"SELECT to_jsonb(t) FROM {table} t")]

    columns = {
        "generation_configs": "id,session_id,n_versions,ordering_preferences",
        "exam_versions": "id,session_id,version_code",
        "source_questions": "id,session_id,question_no",
        "version_questions": "id,version_id,source_question_id,content,canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,status,is_current",
    }

    def project(table, values):
        return [{key: row[key] for key in columns[table].split(",")} for row in values]

    (config,) = project("generation_configs", await rows("generation_configs"))
    versions = project("exam_versions", await rows("exam_versions"))
    sources = project("source_questions", await rows("source_questions"))
    questions = project("version_questions", await rows("version_questions"))
    shuffled = prepare_shuffle(db.sid, config, versions, sources, questions)
    payload = {
        "actor_id": OWNER,
        "snapshot": {"config": config, "versions": versions, "sources": sources, "questions": questions},
        "versions": [version.model_dump(mode="json") for version in shuffled],
    }
    await db.worker.fetchval("SELECT finalize_persist_shuffle($1::uuid,$2::jsonb)", db.sid, json.dumps(payload))
    await db.owner.fetchval("SELECT finalize_approve_session($1::uuid,NULL,NULL)", db.sid)

    def value(script):
        query = script[script.index("SELECT"):]
        return asyncio.run_coroutine_threadsafe(db.owner.fetchval(query), loop).result(timeout=10)

    client = SqlReadClient(SimpleNamespace(value=value), actor=OWNER)
    exported = await asyncio.to_thread(lambda: asyncio.run(load_approved_export_snapshot(client, db.sid, OWNER)))
    assert exported.status == "approved"
    assert sum(len(version.questions) for version in exported.versions) == 4


async def logs(db):
    return await db.admin.fetch(
        "SELECT user_id::text AS user_id, action_type::text AS action, reason FROM review_logs WHERE session_id=$1::uuid",
        db.sid,
    )


async def test_owner_confirm_writes_one_verified_accept_log_per_copy(db):
    await migrate(db)
    await generated_shuffle_only(db)
    await rpc(db.owner, "confirm_shuffle_only_copies", db.sid)
    rows = await logs(db)
    assert len(rows) == 4
    assert {(row["user_id"], row["action"], row["reason"]) for row in rows} == {
        (OWNER, "ACCEPT", "SHUFFLE_ONLY_CONFIRM")
    }
    await rpc(db.owner, "confirm_shuffle_only_copies", db.sid)  # replay adds nothing
    assert len(await logs(db)) == 4


async def test_worker_confirm_writes_no_log_without_a_verified_actor(db):
    await migrate(db)
    await generated_shuffle_only(db)
    result = await rpc(db.worker, "confirm_shuffle_only_copies", db.sid)
    assert result["session_status"] == "reviewed"
    assert await logs(db) == []

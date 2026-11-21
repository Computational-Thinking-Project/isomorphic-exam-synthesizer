"""Issue #70: real PostgreSQL policy freeze, mixed ledger and historical retry."""

import json
from copy import deepcopy

import pytest

from tests.migrations.test_generation_clone import clone_record as legacy_clone_record
from tests.migrations.test_generation_w2 import ROOT, asyncpg, persist, result_for, rpc
from tests.migrations.test_generation_w2 import db as db  # noqa: F401
from tests.migrations.test_w4_config_guards import publish, save

pytestmark = [pytest.mark.asyncio, pytest.mark.parametrize("db", ["w4"], indirect=True)]
SQL = ROOT / "backend/migrations/026_per_question_generation_policy.sql"


async def migrate(db, *, latest=True):
    for number in ("019", "020", "021", "022", "023", "024", "025"):
        (path,) = (ROOT / "backend/migrations").glob(number + "_*.sql")
        await db.admin.execute(path.read_text(encoding="utf-8-sig"))
    if latest:
        await db.admin.execute(SQL.read_text(encoding="utf-8"))


def set_dimensions(db, dimensions):
    for blueprint, allowed in zip(db.blueprints, dimensions):
        template = blueprint["requirement"]["variation_policy"]["allowed_transformations"][0]
        blueprint["requirement"]["variation_policy"]["allowed_transformations"] = [
            dict(deepcopy(template), dimension=dimension, id=f"change-{dimension}")
            for dimension in allowed
        ]


def clone_record(*args, **kwargs):
    record = legacy_clone_record(*args, **kwargs)
    if not (record["solution_md"] or "").strip():
        record["solution_md"] = "Không có lời giải cho câu hỏi này."
    return record


async def test_disjoint_dimensions_are_union_and_frozen_per_question(db):
    await migrate(db)
    set_dimensions(db, [("values",), ("context",)])
    snapshot = await publish(db)
    config = (await save(db, snapshot, versions=1))["config"]
    assert config["mapping_version"] == "1.1"
    assert config["canonical_dimensions"] == ["values", "context"]
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert job["context"]["question_policies"] == {
        row["id"]: {"canonical_dimensions": list(dimensions), "result_kind": "AI_RESULT"}
        for row, dimensions in zip(db.rows, [("values",), ("context",)])
    }
    for index in range(2):
        await persist(db, job, result_for(db, job, index=index))
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    assert len((await rpc(db.owner, "load_generation_completed_results", db.sid))["completed"]) == 2


async def test_mixed_clone_ai_wrong_writer_idempotency_resume_and_quota(db):
    await migrate(db)
    set_dimensions(db, [("values", "context"), ("wording", "names")])
    await save(db, await publish(db), versions=2)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    record = clone_record(job, index=1)
    first = await rpc(db.worker, "persist_generation_clone", db.sid, job["job_id"], record)
    replay = await rpc(db.worker, "persist_generation_clone", db.sid, job["job_id"], record)
    assert replay["replayed"] and not first["replayed"]
    assert replay["version_question_id"] == first["version_question_id"]
    with pytest.raises(asyncpg.PostgresError):
        await persist(db, job, result_for(db, job, index=1))
    with pytest.raises(asyncpg.PostgresError):
        await rpc(db.worker, "persist_generation_clone", db.sid, job["job_id"], clone_record(job))
    await persist(db, job, result_for(db, job))
    await rpc(db.worker, "finish_generation_job", db.sid, "partial_generated", job["job_id"])
    await db.admin.execute(SQL.read_text(encoding="utf-8"))
    retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert retry["context"] == job["context"] and retry["snapshot_id"] == job["snapshot_id"]
    assert [row["result_kind"] for row in retry["committed_targets"]] == [
        "AI_RESULT",
        "ORIGINAL_CLONE",
    ]
    with pytest.raises(asyncpg.PostgresError):
        await rpc(
            db.worker,
            "persist_generation_clone",
            db.sid,
            job["job_id"],
            clone_record(job, index=1, version=2),
        )
    await rpc(
        db.worker,
        "persist_generation_clone",
        db.sid,
        retry["job_id"],
        clone_record(retry, index=1, version=2),
    )
    await persist(db, retry, result_for(db, retry, version=2))
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", retry["job_id"])
    completed = await rpc(db.owner, "load_generation_completed_results", db.sid)
    assert len(completed["completed"]) == 4
    assert (
        await db.admin.fetchval(
            "SELECT gemini_call_count FROM exam_sessions WHERE id=$1::uuid", db.sid
        )
        == 0
    )
    for principal in ("anon", "authenticated", "service_role"):
        for signature in (
            "_generation_question_policy(jsonb)",
            "_generation_is_clone(generation_job_snapshots,uuid)",
        ):
            assert not await db.admin.fetchval(
                "SELECT has_function_privilege($1,$2,'EXECUTE')", principal, "public." + signature
            )


async def test_legacy_frozen_intersection_retry_is_unchanged(db):
    await migrate(db, latest=False)
    set_dimensions(db, [("values",), ("context",)])
    await save(db, await publish(db), versions=2)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert job["context"]["mapping_version"] == "1.0"
    assert job["context"]["canonical_dimensions"] == []
    await rpc(db.worker, "persist_generation_clone", db.sid, job["job_id"], clone_record(job))
    await rpc(db.worker, "finish_generation_job", db.sid, "partial_generated", job["job_id"])
    before = await db.admin.fetchval("SELECT to_jsonb(j) FROM generation_job_snapshots j")
    await db.admin.execute(SQL.read_text(encoding="utf-8"))
    assert await db.admin.fetchval("SELECT to_jsonb(j) FROM generation_job_snapshots j") == before
    retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert retry["context"] == job["context"]
    assert retry["snapshot_id"] == job["snapshot_id"]
    assert len(retry["committed_targets"]) == 1
    await rpc(
        db.worker, "persist_generation_clone", db.sid, retry["job_id"], clone_record(retry, index=1)
    )


@pytest.mark.parametrize("transforms", [[], None, [{}], [{"dimension": "values"}]])
async def test_invalid_policy_never_becomes_clone(db, transforms):
    await migrate(db)
    blueprint = deepcopy(db.blueprints[0])
    blueprint["requirement"]["variation_policy"]["allowed_transformations"] = transforms
    with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_READY"):
        await db.admin.fetchval(
            "SELECT _generation_question_policy($1::jsonb)", json.dumps(blueprint)
        )


@pytest.mark.parametrize("lost_response", [False, True])
async def test_worker_mixed_ai_clone_fallback_resume_preserves_quota(
    db, monkeypatch, lost_response
):
    import asyncio
    from types import SimpleNamespace
    from uuid import UUID

    from app.models.generation import QuestionResult
    from app.services.generation.ai_batch_adapter import AIBatchAdapter
    from app.services.generation.events import GenerationEventBroker
    from app.services.generation.job_repository import GenerationJobRepository
    from app.services.generation.jobs import GenerationJobRunner
    from app.services.generation.service import GenerationService
    from app.services.observability.runtime_registry import RuntimeRegistry
    from tests.migrations.test_generation_w2 import TYPES
    from tests.migrations.test_w4_generation_adapter_pg import SqlClient

    monkeypatch.setitem(TYPES, "finish_generation_job_with_error", ["uuid", "text", "uuid", "text"])
    monkeypatch.setitem(TYPES, "fail_stale_generation_job", ["uuid", "int"])
    await migrate(db)
    set_dimensions(db, [("values", "context"), ("wording",)])
    snapshot = await publish(db)
    await save(db, snapshot, versions=2)
    loop = asyncio.get_running_loop()

    class SerialSqlClient(SqlClient):
        # asyncpg permits one operation per fixture connection; PostgREST uses
        # separate transactions. Serialize the bridge, not production dispatch.
        def __init__(self, *args):
            super().__init__(*args)
            self.lock = asyncio.Lock()

        def execute_sql(self, coroutine):
            async def serialized():
                async with self.lock:
                    return await coroutine

            return super().execute_sql(serialized())

    owner, worker = (
        SerialSqlClient(db.owner, loop, db.sid),
        SerialSqlClient(db.worker, loop, db.sid),
    )
    worker.lose_fallback_response = lost_response
    monkeypatch.setattr(
        "app.services.generation.job_repository.get_service_role_client", lambda: worker
    )
    service = GenerationService(SimpleNamespace(model="fixture"))
    calls = []
    inspection_lock = asyncio.Lock()

    async def generate(source, item, blueprint, context, seed, version, modes, **kwargs):
        assert source.id == db.rows[0]["id"]
        assert modes == ["values", "context"]
        # Clone slots are already durable before any provider reservation.
        async with inspection_lock:
            assert (
                await db.admin.fetchval(
                    "SELECT count(*) FROM generation_target_results WHERE result_kind='ORIGINAL_CLONE'"
                )
                == 2
            )
        for _ in range(4 if version == 2 else 1):
            await context.reserve_request()
            calls.append((version, source.id, seed, tuple(modes)))
        result = QuestionResult.model_validate(
            result_for(db, {"context": snapshot}, version=version, success=version == 1)
        )
        result.request_fingerprint = service._request_fingerprint(item, blueprint, seed, modes)
        if version == 2:
            result.attempts = 4
            result.error_code = "VALIDATION_FAILED"
            result._exhausted_attempts = True
        return result

    monkeypatch.setattr(service, "_generate", generate)
    registry = RuntimeRegistry()
    registry.start()
    failures = []

    class CheckedAdapter(AIBatchAdapter):
        async def run(self, *args, **kwargs):
            try:
                return await super().run(*args, **kwargs)
            except Exception as exc:
                failures.append(repr(exc))
                raise

    runner = GenerationJobRunner(
        None, GenerationEventBroker(), registry, batch=CheckedAdapter(service)
    )
    store = GenerationJobRepository(owner)
    plan = await runner.claim(store, UUID(db.sid))
    outcome = await runner.run(plan, store)
    if lost_response:
        assert outcome.status == "generated", (outcome, failures)
        assert not worker.lose_fallback_response  # readback reconciles lost receipt
        # A crashed process may leave a fully committed job needing a final retry.
        await db.admin.execute(
            "UPDATE exam_sessions SET status='partial_generated', active_job_id=NULL WHERE id=$1::uuid",
            db.sid,
        )
        retry = await runner.claim(store, UUID(db.sid), retry=True)
        assert retry.inputs.snapshot_id == plan.inputs.snapshot_id
        assert len(retry.saved) == 4
        outcome = await runner.run(retry, store)
    assert outcome.status == "generated", (outcome, failures)
    assert len(calls) == 5
    loaded = await rpc(db.owner, "load_generation_completed_results", db.sid)
    assert [row["result_kind"] for row in loaded["completed"]] == [
        "AI_RESULT",
        "ORIGINAL_CLONE",
        "CONFIRMED_SOURCE_FALLBACK",
        "ORIGINAL_CLONE",
    ]
    assert (
        await db.admin.fetchval(
            "SELECT gemini_call_count FROM exam_sessions WHERE id=$1::uuid", db.sid
        )
        == 5
    )
    assert await db.admin.fetchval("SELECT count(*) FROM version_questions WHERE is_current") == 4
    await assert_review_and_export(db)


async def assert_review_and_export(db):
    import asyncio
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.exporter.snapshot_adapter import load_approved_export_snapshot
    from app.services.finalize.shuffle_input import prepare_shuffle
    from tests.migrations.test_export_snapshot_pg import SqlReadClient
    from tests.migrations.test_generation_w2 import OWNER

    async def rows(table):
        # Fixed fixture-owned table names, read as the authenticated owner.
        return [
            json.loads(row[0]) for row in await db.owner.fetch(f"SELECT to_jsonb(t) FROM {table} t")
        ]

    review = json.loads(
        await db.owner.fetchval("SELECT get_review_current_snapshot($1::uuid)", db.sid)
    )
    assert review["session_id"] == db.sid
    questions = await rows("version_questions")
    for question in questions:
        await db.owner.fetchval(
            "SELECT review_accept_question($1::uuid,$2::uuid,$3::uuid)",
            db.sid,
            question["id"],
            str(uuid4()),
        )
    assert (
        await db.admin.fetchval("SELECT status FROM exam_sessions WHERE id=$1::uuid", db.sid)
        == "reviewed"
    )
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
        "snapshot": {
            "config": config,
            "versions": versions,
            "sources": sources,
            "questions": questions,
        },
        "versions": [version.model_dump(mode="json") for version in shuffled],
    }
    await db.worker.fetchval(
        "SELECT finalize_persist_shuffle($1::uuid,$2::jsonb)", db.sid, json.dumps(payload)
    )
    await db.owner.fetchval("SELECT finalize_approve_session($1::uuid,NULL,NULL)", db.sid)
    loop = asyncio.get_running_loop()

    def value(script):
        # Reuse the existing export fixture bridge; role is already authenticated.
        query = script[script.index("SELECT") :]
        return asyncio.run_coroutine_threadsafe(db.owner.fetchval(query), loop).result(timeout=10)

    client = SqlReadClient(SimpleNamespace(value=value), actor=OWNER)

    def load():
        return asyncio.run(load_approved_export_snapshot(client, db.sid, OWNER))

    exported = await asyncio.to_thread(load)
    assert exported.status == "approved"
    assert len(exported.versions) == 2
    assert sum(len(version.questions) for version in exported.versions) == 4


async def test_unfrozen_legacy_config_upgrades_only_on_new_claim(db):
    await migrate(db, latest=False)
    set_dimensions(db, [("values",), ("context",)])
    snapshot = await publish(db)
    await save(db, snapshot)
    await db.admin.execute(SQL.read_text(encoding="utf-8"))
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert job["context"]["mapping_version"] == "1.1"
    assert job["context"]["canonical_dimensions"] == ["values", "context"]


async def test_retry_rejects_corrupt_frozen_policy_before_mutation(db):
    await migrate(db)
    set_dimensions(db, [("values",), ("wording",)])
    await save(db, await publish(db))
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    await rpc(db.worker, "finish_generation_job", db.sid, "failed", job["job_id"])
    await db.admin.execute(
        "UPDATE generation_job_snapshots SET snapshot_payload=jsonb_set(snapshot_payload,'{question_policies}','{}')"
    )
    with pytest.raises(asyncpg.PostgresError, match="frozen question policy changed"):
        await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert (
        await db.admin.fetchval("SELECT status FROM exam_sessions WHERE id=$1::uuid", db.sid)
        == "failed"
    )


async def test_all_clone_new_job_needs_no_ai_runtime_and_rejects_foreign_owner(db, monkeypatch):
    import asyncio
    from uuid import UUID

    from app.services.generation.events import GenerationEventBroker
    from app.services.generation.job_repository import CloneJobInputs, GenerationJobRepository
    from app.services.generation.jobs import GenerationJobRunner
    from app.services.observability.runtime_registry import RuntimeRegistry
    from tests.migrations.test_generation_w2 import TYPES, role
    from tests.migrations.test_w4_generation_adapter_pg import SqlClient

    await migrate(db)
    set_dimensions(db, [("wording",), ("names", "representation", "option_order")])
    snapshot = await publish(db)
    config = (await save(db, snapshot))["config"]
    assert config["mapping_version"] == "1.1" and config["canonical_dimensions"] == []
    await role(db.owner, "authenticated", "00000000-0000-0000-0000-000000000002")
    with pytest.raises(asyncpg.PostgresError):
        await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert await db.admin.fetchval("SELECT count(*) FROM generation_job_snapshots") == 0
    await role(db.owner, "authenticated")
    monkeypatch.setitem(TYPES, "fail_stale_generation_job", ["uuid", "int"])
    monkeypatch.setitem(TYPES, "finish_generation_job_with_error", ["uuid", "text", "uuid", "text"])
    loop = asyncio.get_running_loop()
    owner, worker = SqlClient(db.owner, loop, db.sid), SqlClient(db.worker, loop, db.sid)
    monkeypatch.setattr(
        "app.services.generation.job_repository.get_service_role_client", lambda: worker
    )
    registry = RuntimeRegistry()
    registry.start()
    runner = GenerationJobRunner(None, GenerationEventBroker(), registry)
    store = GenerationJobRepository(owner)
    plan = await runner.claim(store, UUID(db.sid))
    assert isinstance(plan.inputs, CloneJobInputs)
    outcome = await runner.run(plan, store)
    assert outcome.status == "generated" and outcome.completed == 4
    assert all(name != "reserve_generation_quota" for name, _ in worker.calls)
    assert (
        await db.admin.fetchval(
            "SELECT gemini_call_count FROM exam_sessions WHERE id=$1::uuid", db.sid
        )
        == 0
    )

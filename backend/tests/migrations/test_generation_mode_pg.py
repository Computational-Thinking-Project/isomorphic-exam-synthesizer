"""EXT-02: generation_mode frozen per job (migration 028) on real PostgreSQL.

Uses the opt-in disposable W2 fixture (RUN_TASK207_REAL_DB_TESTS). No cloud keys or live AI.
"""

import json
from uuid import uuid4

import pytest

from app.models.schemas import SourceQuestion
from app.services.blueprint.adapters import source_to_item
from tests.migrations.test_generation_w2 import ROOT, TYPES, asyncpg, persist, result_for, rpc
from tests.migrations.test_generation_w2 import db as db  # noqa: F401
from tests.migrations.test_per_question_generation import SQL as SQL_026
from tests.migrations.test_per_question_generation import clone_record
from tests.migrations.test_per_question_generation import migrate as migrate_026
from tests.migrations.test_w4_config_guards import publish

pytestmark = [pytest.mark.asyncio, pytest.mark.parametrize("db", ["w4"], indirect=True)]
SQL = ROOT / "backend/migrations/028_generation_mode.sql"
TYPES["update_generation_ordering_preferences"] = ["uuid", "jsonb"]
SIGNATURE = "public.save_generation_config(uuid,int,jsonb,jsonb,jsonb,text)"


async def migrate(db, *, latest=True):
    await migrate_026(db, latest=latest)
    if latest:
        for number in ("027", "028"):
            (path,) = (ROOT / "backend/migrations").glob(number + "_*.sql")
            await db.admin.execute(path.read_text(encoding="utf-8"))


async def save(db, snapshot, versions=2, mode=None, ordering=None):
    # Named arguments: omitting p_generation_mode is the pre-EXT-02 caller.
    args = ["p_session_id=>$1::uuid", "p_n_versions=>$2::int", "p_expected_snapshot=>$3::jsonb"]
    values = [db.sid, versions, json.dumps(snapshot["manifest"])]
    if ordering is not None:
        args.append(f"p_ordering_preferences=>${len(values) + 1}::jsonb")
        values.append(json.dumps(ordering))
    if mode is not None:
        args.append(f"p_generation_mode=>${len(values) + 1}::text")
        values.append(mode)
    return json.loads(
        await db.owner.fetchval(f"SELECT save_generation_config({','.join(args)})", *values)
    )


async def quota(db):
    return await db.admin.fetchval(
        "SELECT gemini_call_count FROM exam_sessions WHERE id=$1::uuid", db.sid
    )


async def job_mode(db):
    return await db.admin.fetchval(
        "SELECT _generation_job_mode(j) FROM generation_job_snapshots j WHERE session_id=$1::uuid",
        db.sid,
    )


async def interrupt(db):
    # Model a worker crash: the job stops without a clean finish.
    await db.admin.execute(
        "UPDATE exam_sessions SET status='partial_generated', active_job_id=NULL WHERE id=$1::uuid",
        db.sid,
    )


@pytest.mark.parametrize("latest_026,version", [(False, "1.0"), (True, "1.1")])
async def test_legacy_snapshots_resolve_to_ai_generation(db, latest_026, version):
    await migrate(db, latest=False)
    if latest_026:
        await db.admin.execute(SQL_026.read_text(encoding="utf-8"))
    await save(db, await publish(db))
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert job["context"]["mapping_version"] == version
    await rpc(db.worker, "finish_generation_job", db.sid, "failed", job["job_id"])
    before = await db.admin.fetchval("SELECT to_jsonb(j) FROM generation_job_snapshots j")
    for number in ("026", "027", "028"):
        (path,) = (ROOT / "backend/migrations").glob(number + "_*.sql")
        await db.admin.execute(path.read_text(encoding="utf-8"))
    # History is not rewritten: the column stays NULL and the helper resolves the mode.
    after = json.loads(await db.admin.fetchval("SELECT to_jsonb(j) FROM generation_job_snapshots j"))
    assert after.pop("generation_mode") is None
    assert after == json.loads(before)
    assert await job_mode(db) == "ai_generation"
    config = json.loads(
        await db.admin.fetchval("SELECT to_jsonb(c) FROM generation_configs c WHERE session_id=$1::uuid", db.sid)
    )
    assert config["generation_mode"] == "ai_generation"
    retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert retry["context"] == job["context"] and retry["snapshot_id"] == job["snapshot_id"]
    assert retry["config"]["generation_mode"] == "ai_generation"


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE generation_job_snapshots SET generation_mode=NULL",
        "UPDATE generation_job_snapshots SET snapshot_payload=snapshot_payload-'generation_mode'",
        "UPDATE generation_job_snapshots SET snapshot_payload=jsonb_set(snapshot_payload,'{generation_mode}','\"shuffle_only\"')",
        "UPDATE generation_job_snapshots SET snapshot_payload=jsonb_set(snapshot_payload,'{generation_mode}','\"bogus\"')",
        "UPDATE generation_job_snapshots SET mapping_version='1.3'",
    ],
)
async def test_unknown_or_inconsistent_1_2_mode_fails_closed(db, change):
    await migrate(db)
    await save(db, await publish(db))
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert job["context"]["mapping_version"] == "1.2"
    assert job["context"]["generation_mode"] == "ai_generation" == await job_mode(db)
    await rpc(db.worker, "finish_generation_job", db.sid, "failed", job["job_id"])
    await db.admin.execute(change)
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await job_mode(db)
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await rpc(db.owner, "claim_generation_job", db.sid, True)
    with pytest.raises(asyncpg.PostgresError, match="CHECK|check|generation_mode"):
        await db.admin.execute("UPDATE generation_job_snapshots SET generation_mode='bogus'")


async def test_shuffle_only_ai_capable_blueprint_is_clone_only_with_zero_quota(db):
    await migrate(db)
    snapshot = await publish(db)  # Fixture Blueprints allow AI dimensions.
    saved = await save(db, snapshot, versions=2, mode="shuffle_only")
    assert saved["config"]["generation_mode"] == "shuffle_only"
    assert saved["config"]["active_variation_modes"] == []
    assert saved["config"]["canonical_dimensions"] == []
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert job["config"]["generation_mode"] == "shuffle_only"
    assert job["context"]["generation_mode"] == "shuffle_only"
    assert job["context"]["mapping_version"] == "1.2"
    assert job["context"]["question_policies"] == {
        row["id"]: {"canonical_dimensions": [], "result_kind": "ORIGINAL_CLONE"} for row in db.rows
    }
    assert await job_mode(db) == "shuffle_only"
    # The database itself refuses AI quota and AI results for this job.
    with pytest.raises(asyncpg.PostgresError, match="ERR_MODE_SHUFFLE_ONLY"):
        await rpc(db.worker, "reserve_generation_quota", db.sid, 1, job["job_id"])
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await persist(db, job, result_for(db, job))
    await rpc(db.worker, "persist_generation_clone", db.sid, job["job_id"], clone_record(job))
    await interrupt(db)
    retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert retry["context"] == job["context"] and retry["snapshot_id"] == job["snapshot_id"]
    with pytest.raises(asyncpg.PostgresError, match="ERR_MODE_SHUFFLE_ONLY"):
        await rpc(db.worker, "reserve_generation_quota", db.sid, 1, retry["job_id"])
    for index, version in ((1, 1), (0, 2), (1, 2)):
        await rpc(
            db.worker, "persist_generation_clone", db.sid, retry["job_id"],
            clone_record(retry, index=index, version=version),
        )
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", retry["job_id"])
    completed = await rpc(db.owner, "load_generation_completed_results", db.sid)
    assert [row["result_kind"] for row in completed["completed"]] == ["ORIGINAL_CLONE"] * 4
    assert await quota(db) == 0
    await assert_one_ledger_row_per_slot(db, retry["snapshot_id"], slots=4, kind="ORIGINAL_CLONE")


async def assert_one_ledger_row_per_slot(db, snapshot_id, *, slots, kind):
    """Ledger shape consumers (Export) rely on is unchanged for mapping 1.2 jobs."""
    rows = await db.admin.fetch(
        "SELECT * FROM generation_target_results WHERE session_id=$1::uuid AND is_success",
        db.sid,
    )
    assert len(rows) == slots
    assert len({(row["version_index"], row["source_question_id"]) for row in rows}) == slots
    for row in rows:
        assert str(row["snapshot_id"]) == snapshot_id and str(row["session_id"]) == db.sid
        assert row["version_question_id"] is not None and row["source_question_id"] is not None
        assert row["result_kind"] == kind
        if kind == "ORIGINAL_CLONE":
            assert len(row["clone_fingerprint"]) == 64
            assert all(char in "0123456789abcdef" for char in row["clone_fingerprint"])
        else:
            assert row["clone_fingerprint"] is None and row["request_fingerprint"]


async def test_ai_generation_1_2_ledger_rows_keep_dev_shape(db):
    await migrate(db)
    await save(db, await publish(db), versions=1)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert job["context"]["mapping_version"] == "1.2"
    for index in range(2):
        await persist(db, job, result_for(db, job, index=index))
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    await assert_one_ledger_row_per_slot(db, job["snapshot_id"], slots=2, kind="AI_RESULT")


async def assert_python_reader_matches_sql(db):
    from app.services.generation.mode_mapper import job_generation_mode, slot_result_kind

    row = json.loads(await db.admin.fetchval(
        "SELECT to_jsonb(j) FROM generation_job_snapshots j WHERE session_id=$1::uuid", db.sid
    ))
    assert job_generation_mode(row) == await job_mode(db)
    for source in row["snapshot_payload"]["confirmed_sources"]:
        sql_clone = await db.admin.fetchval(
            "SELECT _generation_is_clone(j,$2::uuid) FROM generation_job_snapshots j WHERE session_id=$1::uuid",
            db.sid, source["source_question_id"],
        )
        expected = "ORIGINAL_CLONE" if sql_clone else "AI_RESULT"
        assert slot_result_kind(row, source["source_question_id"]) == expected
    return row


@pytest.mark.parametrize(
    "setup",
    ["legacy_1_0", "legacy_1_1_mixed", "ai_1_2_mixed", "ai_1_2_all_clone", "shuffle_only_1_2"],
)
async def test_python_reader_parity_with_sql_helpers(db, setup):
    from tests.migrations.test_per_question_generation import set_dimensions

    if setup.startswith("legacy"):
        await migrate(db, latest=False)
        if setup == "legacy_1_1_mixed":
            await db.admin.execute(SQL_026.read_text(encoding="utf-8"))
            set_dimensions(db, [("values",), ("wording",)])
        await save(db, await publish(db))
        await rpc(db.owner, "claim_generation_job", db.sid, False)
        for number in ("026", "027", "028"):
            (path,) = (ROOT / "backend/migrations").glob(number + "_*.sql")
            await db.admin.execute(path.read_text(encoding="utf-8"))
    else:
        await migrate(db)
        if setup == "ai_1_2_mixed":
            set_dimensions(db, [("values", "context"), ("wording",)])
        snapshot = await publish(db, clone=setup == "ai_1_2_all_clone")
        await save(db, snapshot, mode="shuffle_only" if setup.startswith("shuffle") else None)
        await rpc(db.owner, "claim_generation_job", db.sid, False)
    row = await assert_python_reader_matches_sql(db)
    expected_version = {"legacy_1_0": "1.0", "legacy_1_1_mixed": "1.1"}.get(setup, "1.2")
    assert row["mapping_version"] == expected_version


@pytest.mark.parametrize("first,second", [("ai_generation", "shuffle_only"), ("shuffle_only", "ai_generation")])
async def test_changed_mode_on_retry_conflicts(db, first, second):
    await migrate(db)
    await save(db, await publish(db), mode=first)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    await interrupt(db)
    await db.admin.execute(
        "UPDATE generation_configs SET generation_mode=$2 WHERE session_id=$1::uuid", db.sid, second
    )
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert await job_mode(db) == first
    await db.admin.execute(
        "UPDATE generation_configs SET generation_mode=$2 WHERE session_id=$1::uuid", db.sid, first
    )
    retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert retry["snapshot_id"] == job["snapshot_id"]


async def test_old_payload_without_mode_and_single_signature_acl(db):
    await migrate(db)
    snapshot = await publish(db)
    result = await save(db, snapshot)
    assert result["config"]["generation_mode"] == "ai_generation"
    assert result["config"]["mapping_version"] == "1.2"
    # Positional five-argument callers (pre-EXT-02 tests and adapters) still resolve.
    positional = await rpc(
        db.owner, "save_generation_config", db.sid, 2, [],
        {"shuffle_questions": True, "shuffle_options": False}, snapshot["manifest"],
    )
    assert positional["config"]["generation_mode"] == "ai_generation"
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await save(db, snapshot, mode="bogus")
    assert await db.admin.fetchval(
        "SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname='save_generation_config'"
    ) == 1
    for principal, allowed in [("anon", False), ("authenticated", True), ("service_role", True)]:
        assert await db.admin.fetchval(
            "SELECT has_function_privilege($1,$2,'EXECUTE')", principal, SIGNATURE
        ) == allowed
    assert not await db.admin.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_proc p,aclexplode(p.proacl) a WHERE p.oid=$1::regprocedure"
        " AND a.grantee=0 AND a.privilege_type='EXECUTE')", SIGNATURE,
    )
    for principal in ("anon", "authenticated", "service_role"):
        for signature in (
            "_generation_job_mode(generation_job_snapshots)",
            "_generation_mode_policy(text,jsonb)",
        ):
            assert not await db.admin.fetchval(
                "SELECT has_function_privilege($1,$2,'EXECUTE')", principal, "public." + signature
            )


async def test_migration_replay_is_idempotent(db):
    await migrate(db)
    await save(db, await publish(db), mode="shuffle_only")
    await rpc(db.owner, "claim_generation_job", db.sid, False)
    before = await db.admin.fetchval(
        "SELECT jsonb_build_object('c',(SELECT to_jsonb(c) FROM generation_configs c),"
        "'j',(SELECT to_jsonb(j) FROM generation_job_snapshots j))"
    )
    await db.admin.execute(SQL.read_text(encoding="utf-8"))
    after = await db.admin.fetchval(
        "SELECT jsonb_build_object('c',(SELECT to_jsonb(c) FROM generation_configs c),"
        "'j',(SELECT to_jsonb(j) FROM generation_job_snapshots j))"
    )
    assert after == before
    assert await job_mode(db) == "shuffle_only"


async def add_sources(db, count):
    """Append synthetic source questions built like the shared fixture rows."""
    fixture = json.loads(
        (ROOT / "backend/tests/fixtures/ai_pipeline.json").read_text(encoding="utf-8-sig")
    )
    source = SourceQuestion.model_validate(fixture["source"])
    old_id = source_to_item(source)["source"]["question_id"]
    for _ in range(count):
        number = len(db.rows) + 1
        src = source.model_copy(update={"id": str(uuid4())})
        new_id = source_to_item(src)["source"]["question_id"]
        db.blueprints.append(
            json.loads(json.dumps(fixture["blueprint"], ensure_ascii=False).replace(old_id, new_id))
        )
        db.rows.append(dict(
            id=src.id, session_id=db.sid, question_no=number, raw_content=src.question_text,
            options=src.options, correct_key=src.correct_answer, solution_md=src.solution,
        ))
        await db.admin.execute(
            "INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key,solution_md)"
            " VALUES($1::uuid,$2::uuid,$3,$4,$5::jsonb,$6,$7)",
            src.id, db.sid, number, src.question_text, json.dumps(src.options),
            src.correct_answer, src.solution,
        )


async def drop_last_source(db):
    row = db.rows.pop()
    db.blueprints.pop()
    await db.admin.execute("DELETE FROM source_questions WHERE id=$1::uuid", row["id"])


@pytest.mark.parametrize("mode", ["ai_generation", "shuffle_only"])
@pytest.mark.parametrize("count", [1, 20])
async def test_one_and_twenty_questions_are_accepted(db, mode, count):
    await migrate(db)
    if count == 1:
        await drop_last_source(db)
    else:
        await add_sources(db, count - len(db.rows))
    await save(db, await publish(db), versions=1, mode=mode)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert len(job["context"]["confirmed_sources"]) == count
    assert job["context"]["generation_mode"] == mode


@pytest.mark.parametrize("mode", ["ai_generation", "shuffle_only"])
@pytest.mark.parametrize("count", [0, 21])
async def test_zero_and_twenty_one_questions_are_rejected_before_claim(db, mode, count):
    """0/21 sources: nothing can be configured or claimed; no job and no quota.

    Source rows are locked once configured (ARTIFACT_SOURCE_LOCKED), and confirmation
    itself accepts only 1-20 sources, so the out-of-range source is set up before any
    confirmation. A forged 'configured' row then proves the claim also refuses it.
    """
    await migrate(db)
    if count:
        await add_sources(db, count - len(db.rows))
    else:
        while db.rows:
            await drop_last_source(db)
    snapshot = await rpc(db.owner, "get_generation_source_snapshot", db.sid)
    assert snapshot["ready"] is False
    with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_READY|ERR_CONFIG_CONFLICT"):
        await save(db, {"manifest": {}}, versions=1, mode=mode)
    await db.admin.execute(
        "INSERT INTO generation_configs(session_id,n_versions,generation_mode) VALUES($1::uuid,1,$2)",
        db.sid, mode,
    )
    await db.admin.execute("UPDATE exam_sessions SET status='configured' WHERE id=$1::uuid", db.sid)
    with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_READY|ERR_CONFIG_CONFLICT"):
        await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert await db.admin.fetchval("SELECT count(*) FROM generation_job_snapshots") == 0
    assert await quota(db) == 0


async def test_preferences_locked_after_permutation_is_persisted(db):
    await migrate(db)
    await save(db, await publish(db), mode="shuffle_only",
               ordering={"shuffle_questions": False, "shuffle_options": False})
    await db.admin.execute("UPDATE exam_sessions SET status='reviewed' WHERE id=$1::uuid", db.sid)
    both_on = {"shuffle_questions": True, "shuffle_options": True}
    updated = await rpc(db.owner, "update_generation_ordering_preferences", db.sid, both_on)
    assert updated["ordering_preferences"] == both_on
    # finalize_persist_shuffle marks every version finalized once permutations are written.
    await db.admin.execute(
        "INSERT INTO exam_versions(session_id,version_code,is_finalized) VALUES($1::uuid,'101',true)", db.sid
    )
    with pytest.raises(asyncpg.PostgresError, match="preferences locked"):
        await rpc(db.owner, "update_generation_ordering_preferences", db.sid,
                  {"shuffle_questions": False, "shuffle_options": False})
    stored = json.loads(await db.admin.fetchval(
        "SELECT ordering_preferences FROM generation_configs WHERE session_id=$1::uuid", db.sid
    ))
    assert stored == both_on


async def test_worker_runs_shuffle_only_without_ai_or_quota(db, monkeypatch):
    """Real job runner + repository on PostgreSQL: the clone path, never the AI batch."""
    import asyncio
    from types import SimpleNamespace
    from uuid import UUID

    from app.services.generation.ai_batch_adapter import AIBatchAdapter
    from app.services.generation.events import GenerationEventBroker
    from app.services.generation.job_repository import CloneJobInputs, GenerationJobRepository
    from app.services.generation.jobs import GenerationJobRunner
    from app.services.generation.service import GenerationService
    from app.services.observability.runtime_registry import RuntimeRegistry
    from tests.migrations.test_per_question_generation import assert_review_and_export
    from tests.migrations.test_w4_generation_adapter_pg import SqlClient

    monkeypatch.setitem(TYPES, "finish_generation_job_with_error", ["uuid", "text", "uuid", "text"])
    monkeypatch.setitem(TYPES, "fail_stale_generation_job", ["uuid", "int"])
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
    assert isinstance(plan.inputs, CloneJobInputs)
    outcome = await runner.run(plan, store)
    assert outcome.status == "generated", outcome
    assert ai_calls == []
    assert not any(name == "reserve_generation_quota" for name, _ in worker.calls + owner.calls)
    assert await quota(db) == 0
    loaded = await rpc(db.owner, "load_generation_completed_results", db.sid)
    assert [row["result_kind"] for row in loaded["completed"]] == ["ORIGINAL_CLONE"] * 4
    await assert_review_and_export(db)

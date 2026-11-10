"""W4-MVP-01 on PostgreSQL, merged 002-016 plus append-only 019.

Uses the opt-in disposable W2 fixture. No production credentials or live AI.
The old W2 fixtures remain useful as compatibility/upgrade evidence separately.
"""

import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pytest

from app.services.blueprint.artifacts import prepare_blueprint_artifact, prepare_source_artifacts
from tests.migrations.test_generation_w2 import ROOT, OWNER, asyncpg, role, rpc
from tests.migrations.test_generation_w2 import db as db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.parametrize("db", ["w4"], indirect=True)]
MIGRATION = ROOT / "backend/migrations/019_w4_config_defaults.sql"
OFF = {"shuffle_questions": False, "shuffle_options": False}


async def migrate(db):
    await db.admin.execute(MIGRATION.read_text(encoding="utf-8"))


async def confirm(db, conn=None, key=None, revision=None):
    revision = revision or await db.admin.fetchval(
        "SELECT source_content_revision FROM exam_sessions WHERE id=$1::uuid", db.sid
    )
    return json.loads(await (conn or db.worker).fetchval(
        "SELECT confirm_source_artifacts($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5::jsonb)",
        db.sid, OWNER, key or str(uuid4()), revision,
        json.dumps(prepare_source_artifacts(db.sid, db.rows)),
    ))


async def publish(db, *, clone=False):
    receipt = await confirm(db)
    for artifact, blueprint in zip(receipt["sources"], db.blueprints):
        blueprint = deepcopy(blueprint)
        if clone:
            for transform in blueprint["requirement"]["variation_policy"]["allowed_transformations"]:
                transform["dimension"] = "wording"
        publication = prepare_blueprint_artifact(artifact, blueprint)
        publication["producer_job_id"] = publication["blueprint_revision_id"]
        await rpc(db.worker, "claim_source_production", db.sid, artifact["source_revision_id"], publication["producer_job_id"])
        await rpc(db.worker, "publish_canonical_blueprint", db.sid, publication)
    snapshot = await rpc(db.owner, "get_generation_source_snapshot", db.sid)
    assert snapshot["ready"], snapshot
    return snapshot


async def save(db, snapshot, versions=2, ordering=None, conn=None):
    # Named arguments exercise omission without introducing another overload.
    if ordering is None:
        return json.loads(await (conn or db.owner).fetchval(
            "SELECT save_generation_config(p_session_id=>$1::uuid,p_n_versions=>$2::int,p_expected_snapshot=>$3::jsonb)",
            db.sid, versions, json.dumps(snapshot["manifest"]),
        ))
    return await rpc(conn or db.owner, "save_generation_config", db.sid, versions, [], ordering, snapshot["manifest"])


async def stored(db):
    return await db.admin.fetchval("SELECT to_jsonb(c) FROM generation_configs c WHERE session_id=$1::uuid", db.sid)


@pytest.mark.parametrize("versions", [1, 2, 3, 4])
@pytest.mark.parametrize("questions,options", [(False, False), (True, False), (False, True), (True, True)])
async def test_config_matrix_persist_read_replay_and_claim(db, versions, questions, options):
    await migrate(db)
    snapshot = await publish(db)
    flags = {"shuffle_questions": questions, "shuffle_options": options}
    first = await save(db, snapshot, versions, flags)
    second = await save(db, snapshot, versions, flags)
    assert first == second
    row = json.loads(await stored(db))
    assert row["ordering_preferences"] == flags and row["n_versions"] == versions
    assert json.loads(await db.owner.fetchval("SELECT ordering_preferences FROM generation_configs WHERE session_id=$1::uuid", db.sid)) == flags
    assert await db.admin.fetchval("SELECT count(*) FROM generation_configs") == 1
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert job["context"]["ordering_preferences"] == flags
    assert job["context"]["n_versions"] == versions


async def test_fresh_defaults_column_rpc_signature_and_acl(db):
    await migrate(db)
    await db.admin.execute("INSERT INTO generation_configs(session_id,n_versions) VALUES($1::uuid,1)", db.sid)
    assert json.loads(await stored(db))["ordering_preferences"] == OFF
    await db.admin.execute("DELETE FROM generation_configs WHERE session_id=$1::uuid", db.sid)
    snapshot = await publish(db, clone=True)
    result = await save(db, snapshot)
    assert result["config"]["ordering_preferences"] == OFF
    assert result["config"]["active_variation_modes"] == []
    state = json.loads(await db.owner.fetchval("SELECT get_source_artifacts($1::uuid)", db.sid))
    assert state["ready"] is True and state["supported_modes"] == []
    assert await db.admin.fetchval("SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname='save_generation_config'") == 1
    for principal, allowed in [("anon", False), ("authenticated", True), ("service_role", True)]:
        assert await db.admin.fetchval("SELECT has_function_privilege($1,'public.save_generation_config(uuid,int,jsonb,jsonb,jsonb)','EXECUTE')", principal) == allowed
    assert not await db.admin.fetchval("SELECT EXISTS(SELECT 1 FROM pg_proc p,aclexplode(p.proacl) a WHERE p.oid='public.save_generation_config(uuid,int,jsonb,jsonb,jsonb)'::regprocedure AND a.grantee=0 AND a.privilege_type='EXECUTE')")


@pytest.mark.parametrize("questions,options", [(False, False), (True, False), (False, True), (True, True)])
async def test_populated_upgrade_and_replay_preserve_preferences(db, questions, options):
    snapshot = await publish(db)
    await save(db, snapshot, 3, {"shuffle_questions": questions, "shuffle_options": options})
    before = await stored(db)
    acl = await db.admin.fetchval("SELECT proacl::text FROM pg_proc WHERE oid='public.save_generation_config(uuid,int,jsonb,jsonb,jsonb)'::regprocedure")
    for _ in range(2):
        await migrate(db)
        assert await stored(db) == before
        assert await db.admin.fetchval("SELECT proacl::text FROM pg_proc WHERE oid='public.save_generation_config(uuid,int,jsonb,jsonb,jsonb)'::regprocedure") == acl


@pytest.mark.parametrize("versions", [0, 5, -1, None])
async def test_invalid_counts_are_atomic(db, versions):
    await migrate(db)
    snapshot = await publish(db)
    await save(db, snapshot)
    before = await stored(db)
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await save(db, snapshot, versions)
    assert await stored(db) == before


@pytest.mark.parametrize("literal", ["true", "1.5", "'invalid'", "'{}'::jsonb", "ARRAY[1]"])
async def test_rpc_rejects_non_integer_sql_inputs(db, literal):
    await migrate(db)
    await publish(db)
    with pytest.raises(asyncpg.PostgresError):
        await db.owner.fetchval(f"SELECT save_generation_config('{db.sid}',{literal})")
    assert await stored(db) is None


@pytest.mark.parametrize("value", [None, "false", 0, 1, [], {}, "yes"])
@pytest.mark.parametrize("field", ["shuffle_questions", "shuffle_options"])
async def test_boolean_values_are_strict_and_atomic(db, value, field):
    await migrate(db)
    snapshot = await publish(db)
    await save(db, snapshot)
    before = await stored(db)
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await save(db, snapshot, ordering={**OFF, field: value})
    assert await stored(db) == before


async def test_draft_legacy_rows_cannot_authorize_config_or_claim(db):
    await migrate(db)
    for row in db.rows:
        await db.admin.execute("INSERT INTO question_blueprints(source_question_id,confirmed_at,variation_modes) VALUES($1::uuid,now(),'[]')", row["id"])
    assert (await rpc(db.owner, "get_generation_source_snapshot", db.sid))["ready"] is False
    for function, args in [("save_generation_config", (db.sid, 2)), ("claim_generation_job", (db.sid, False))]:
        with pytest.raises(asyncpg.PostgresError):
            await rpc(db.owner, function, *args)
    # Client cannot manufacture the lifecycle state that the legacy path needs.
    with pytest.raises(asyncpg.PostgresError):
        await db.owner.execute("UPDATE exam_sessions SET status='blueprinted' WHERE id=$1::uuid", db.sid)
    with pytest.raises(asyncpg.PostgresError):
        await db.owner.fetchval("SELECT confirm_exam_source($1::uuid,2)", db.sid)
    assert await stored(db) is None
    assert await db.admin.fetchval("SELECT count(*) FROM generation_job_snapshots") == 0


@pytest.mark.parametrize("state", ["pending", "running", "failed"])
async def test_incomplete_production_rejects_config_and_claim(db, state):
    await migrate(db)
    receipt = await confirm(db)
    if state != "pending":
        source = receipt["sources"][0]
        token = str(uuid4())
        await rpc(db.worker, "claim_source_production", db.sid, source["source_revision_id"], token)
        if state == "failed":
            await db.worker.execute("SELECT fail_source_production($1::uuid,$2::uuid,$3::uuid,'PROVIDER_FAILED')", db.sid, source["source_revision_id"], token)
    artifact = json.loads(await db.owner.fetchval("SELECT get_source_artifacts($1::uuid)", db.sid))
    assert artifact["ready"] is False and artifact["supported_modes"] is None
    assert state in {item["status"] for item in artifact["production"]}
    with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_READY"):
        await rpc(db.owner, "save_generation_config", db.sid, 2)
    with pytest.raises(asyncpg.PostgresError):
        await rpc(db.owner, "claim_generation_job", db.sid, False)


@pytest.mark.parametrize("mutation", ["manifest", "source_revision", "blueprint", "fingerprint"])
async def test_stale_config_or_source_cannot_claim_or_fall_back(db, mutation):
    await migrate(db)
    snapshot = await publish(db)
    await save(db, snapshot)
    for row in db.rows:
        await db.admin.execute("INSERT INTO question_blueprints(source_question_id,confirmed_at,variation_modes) VALUES($1::uuid,now(),'[]')", row["id"])
    if mutation == "manifest":
        await db.admin.execute("UPDATE generation_configs SET source_manifest='{}'")
    elif mutation == "source_revision":
        cid = await db.admin.fetchval("SELECT confirmation_id FROM source_artifact_confirmations WHERE session_id=$1::uuid", db.sid)
        rev = str(uuid4())
        qid = db.rows[0]["id"]
        await db.admin.execute(
            "INSERT INTO source_artifact_revisions(source_revision_id,confirmation_id,source_question_id,source_fingerprint,confirmed_input) VALUES($1::uuid,$2::uuid,$3::uuid,repeat('0',64),'{}')",
            rev, cid, qid,
        )
        await db.admin.execute(
            "UPDATE source_artifact_heads SET blueprint_revision_id=NULL, source_revision_id=$1::uuid WHERE source_question_id=$2::uuid",
            rev, qid,
        )
    elif mutation == "blueprint":
        await db.admin.execute("UPDATE source_artifact_heads SET blueprint_revision_id=NULL")
    else:
        await db.admin.execute("UPDATE source_artifact_revisions SET source_fingerprint=repeat('0',64)")
    before = await stored(db)
    with pytest.raises(asyncpg.PostgresError, match="ERR_(CONFIG_CONFLICT|SOURCE_NOT_READY)"):
        await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert await stored(db) == before
    assert await db.admin.fetchval("SELECT count(*) FROM generation_job_snapshots") == 0


async def test_foreign_owner_and_anonymous_cannot_read_config_or_claim(db):
    await migrate(db)
    snapshot = await publish(db)
    await save(db, snapshot)
    before = await stored(db)
    for principal in ("authenticated", "anon"):
        await role(db.owner, principal, str(uuid4()))
        for function, args in [("get_generation_source_snapshot", (db.sid,)), ("save_generation_config", (db.sid, 2)), ("claim_generation_job", (db.sid, False))]:
            with pytest.raises(asyncpg.PostgresError):
                await rpc(db.owner, function, *args)
        if principal == "authenticated":
            assert await db.owner.fetchval("SELECT count(*) FROM generation_configs") == 0
    assert await stored(db) == before


@pytest.mark.parametrize("state", ["approved", "exported", "reviewed"])
async def test_config_cannot_bypass_later_session_states(db, state):
    await migrate(db)
    snapshot = await publish(db)
    await save(db, snapshot)
    await db.admin.execute("UPDATE exam_sessions SET status=$2::session_status WHERE id=$1::uuid", db.sid, state)
    before = await stored(db)
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await save(db, snapshot, 4)
    assert await stored(db) == before


async def test_concurrent_identical_configs_commit_one_row(db):
    await migrate(db)
    snapshot = await publish(db)
    other = await asyncpg.connect(db.dsn)
    try:
        await role(other, "authenticated")
        results = await asyncio.gather(save(db, snapshot), save(db, snapshot, conn=other))
        assert results[0] == results[1]
        assert await db.admin.fetchval("SELECT count(*) FROM generation_configs") == 1
    finally:
        await other.close()


async def test_confirmation_lock_serializes_config_and_remains_not_ready(db):
    await migrate(db)
    transaction = db.worker.transaction()
    await transaction.start()
    task = None
    try:
        await confirm(db)
        task = asyncio.create_task(rpc(db.owner, "save_generation_config", db.sid, 2))
        # Observe PostgreSQL lock contention instead of assuming a sleep proves it.
        for _ in range(100):
            if await db.admin.fetchval("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=$1", db.owner.get_server_pid()):
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("configuration never waited for confirmation's root lock")
        assert not task.done()
        await transaction.commit()
        with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_READY"):
            await task
        assert await stored(db) is None
        assert await db.admin.fetchval("SELECT count(*) FROM source_artifact_confirmations") == 1
    finally:
        if db.worker.is_in_transaction():
            await transaction.rollback()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

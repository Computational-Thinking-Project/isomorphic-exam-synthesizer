"""Real W2 SQL tests; explicit opt-in, random databases in a no-network cluster."""

import asyncio
import json
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from app.models.schemas import SourceQuestion
from app.services.blueprint.adapters import prepare_sources, source_to_item
from app.services.blueprint.artifacts import prepare_blueprint_artifact, prepare_source_artifacts
from app.services.blueprint.common import canonical
from app.services.blueprint.service import source_fingerprint
from app.services.generation.service import fingerprint
from tests.migrations.test_stage3_schema import BOOTSTRAP

asyncpg = pytest.importorskip("asyncpg")
pytestmark = pytest.mark.asyncio
ROOT = Path(__file__).resolve().parents[3]
OWNER = "00000000-0000-0000-0000-000000000001"
ORDERING = {"shuffle_questions": True, "shuffle_options": False}
TYPES = {
    "get_generation_source_snapshot": ["uuid"],
    "save_generation_config": ["uuid", "int", "jsonb", "jsonb", "jsonb"],
    "claim_generation_job": ["uuid", "boolean"],
    "finish_generation_job": ["uuid", "text", "uuid"],
    "load_generation_completed_results": ["uuid"],
    "persist_generation_clone": ["uuid", "uuid", "jsonb"],
    "confirm_source_artifacts": ["uuid", "uuid", "uuid", "timestamptz", "jsonb"],
    "claim_source_production": ["uuid", "uuid", "uuid"],
    "publish_canonical_blueprint": ["uuid", "jsonb"],
    "persist_generation_result": [
        "uuid",
        "uuid",
        "int",
        "uuid",
        "int",
        "boolean",
        "text",
        "int",
        "int",
        "text",
        "jsonb",
        "text",
        "jsonb",
        "text",
        "text",
        "boolean",
    ],
    "reserve_generation_quota": ["uuid", "int", "uuid"],
}


async def rpc(conn, name, *args):
    types = TYPES[name][: len(args)]
    values = [
        json.dumps(v, ensure_ascii=False) if t == "jsonb" and v is not None else v
        for t, v in zip(types, args)
    ]
    placeholders = ",".join("$" + str(i) + "::" + t for i, t in enumerate(types, 1))
    return json.loads(await conn.fetchval(f"SELECT public.{name}({placeholders})", *values))


async def role(conn, name="service_role", actor=OWNER):
    await conn.execute("RESET ROLE")
    await conn.execute(f"SET ROLE {name}")
    await conn.execute(
        "SELECT set_config('request.jwt.claim.sub',$1,false),set_config('request.jwt.claim.role',$2,false)",
        actor,
        name,
    )


@pytest.fixture
async def db(request):
    if os.environ.get("RUN_TASK207_REAL_DB_TESTS") != "1":
        pytest.skip("explicit isolated TASK-207 PostgreSQL opt-in required")
    dsn = os.environ["TASK207_TEST_DSN"]
    parsed = urlparse(dsn)
    assert parsed.hostname == "127.0.0.1" and parsed.path.startswith("/task207_cluster_")
    base = await asyncpg.connect(dsn)
    assert await base.fetchval("SELECT current_database()") == parsed.path[1:]
    name = "task207_case_" + uuid4().hex
    await base.execute(f'CREATE DATABASE "{name}"')
    case_dsn = dsn.rsplit("/", 1)[0] + "/" + name
    admin = await asyncpg.connect(case_dsn)
    owner = worker = None
    try:
        await admin.execute(BOOTSTRAP)
        await admin.execute((ROOT / "backend/scripts/schema.sql").read_text(encoding="utf-8-sig"))
        # Model Supabase bootstrap grants before migrations narrow write authority.
        await admin.execute("""
            GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role;
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO authenticated,service_role;
            GRANT INSERT,UPDATE,DELETE ON exam_sessions,source_questions,question_blueprints,generation_configs TO authenticated;
        """)
        for number in ("002", "003", "004", "005", "006", "007", "008", "009"):
            files = list((ROOT / "backend/migrations").glob(number + "_*.sql"))
            assert len(files) == 1
            await admin.execute(files[0].read_text(encoding="utf-8-sig"))
        # W4 exercises the full merged source-confirmation chain, including the
        # UUID overload and revocation of legacy confirmation. Historical W2
        # upgrade fixtures intentionally retain their original baseline.
        if getattr(request, "param", None) == "w4":
            for number in ("010", "011", "012", "013", "014"):
                files = list((ROOT / "backend/migrations").glob(number + "_*.sql"))
                assert len(files) == 1
                sql = files[0].read_text(encoding="utf-8-sig")
                if sql.strip():
                    await admin.execute(sql)
        await admin.execute(
            "INSERT INTO auth.users(id,email) VALUES($1::uuid,'fixture@example.invalid')", OWNER
        )
        await admin.execute(
            "INSERT INTO public.users(id,email) VALUES($1::uuid,'fixture@example.invalid') ON CONFLICT(id) DO NOTHING",
            OWNER,
        )
        sid = str(uuid4())
        await admin.execute(
            "INSERT INTO public.exam_sessions(id,user_id,title) VALUES($1::uuid,$2::uuid,'W2')",
            sid,
            OWNER,
        )
        fixture = json.loads(
            (ROOT / "backend/tests/fixtures/ai_pipeline.json").read_text(encoding="utf-8-sig")
        )
        source = SourceQuestion.model_validate(fixture["source"])
        old_id = source_to_item(source)["source"]["question_id"]
        rows, blueprints = [], []
        for index in range(2):
            src = source.model_copy(update={"id": str(uuid4())})
            new_id = source_to_item(src)["source"]["question_id"]
            blueprint = json.loads(
                json.dumps(fixture["blueprint"], ensure_ascii=False).replace(old_id, new_id)
            )
            rows.append(
                dict(
                    id=src.id,
                    session_id=sid,
                    question_no=index + 1,
                    raw_content=src.question_text,
                    options=src.options,
                    correct_key=src.correct_answer,
                    solution_md=src.solution,
                )
            )
            blueprints.append(blueprint)
            await admin.execute(
                "INSERT INTO public.source_questions(id,session_id,question_no,raw_content,options,correct_key,solution_md) VALUES($1::uuid,$2::uuid,$3,$4,$5::jsonb,$6,$7)",
                src.id,
                sid,
                index + 1,
                src.question_text,
                json.dumps(src.options),
                src.correct_answer,
                src.solution,
            )
        if getattr(request, "param", None) == "upgrade":
            await admin.execute(
                "INSERT INTO generation_configs(session_id,n_versions) VALUES($1::uuid,2)", sid
            )
        await admin.execute(
            (ROOT / "backend/migrations/015_stage2_canonical_w2_integration.sql").read_text(
                encoding="utf-8-sig"
            )
        )
        if getattr(request, "param", None) != "pre_clone":
            await admin.execute(
                (ROOT / "backend/migrations/016_stage2_original_clone.sql").read_text(
                    encoding="utf-8-sig"
                )
            )
        if getattr(request, "param", None) == "w4":
            for number in ("017", "018"):
                files = list((ROOT / "backend/migrations").glob(number + "_*.sql"))
                assert len(files) == 1
                await admin.execute(files[0].read_text(encoding="utf-8-sig"))
        owner, worker = await asyncpg.connect(case_dsn), await asyncpg.connect(case_dsn)
        await role(owner, "authenticated")
        await role(worker)
        yield SimpleNamespace(
            admin=admin,
            owner=owner,
            worker=worker,
            sid=sid,
            rows=rows,
            blueprints=blueprints,
            dsn=case_dsn,
        )
    finally:
        for conn in (owner, worker, admin):
            if conn:
                await conn.close()
        await base.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await base.close()


async def publish(env):
    artifacts = prepare_source_artifacts(env.sid, env.rows)
    stamp = await env.admin.fetchval(
        "SELECT updated_at FROM exam_sessions WHERE id=$1::uuid", env.sid
    )
    await rpc(
        env.worker, "confirm_source_artifacts", env.sid, OWNER, str(uuid4()), stamp, artifacts
    )
    for artifact, blueprint in zip(artifacts, env.blueprints):
        pub = prepare_blueprint_artifact(artifact, blueprint)
        pub["producer_job_id"] = pub["blueprint_revision_id"]
        await rpc(
            env.worker,
            "claim_source_production",
            env.sid,
            artifact["source_revision_id"],
            pub["producer_job_id"],
        )
        await rpc(env.worker, "publish_canonical_blueprint", env.sid, pub)
    return await rpc(env.owner, "get_generation_source_snapshot", env.sid)


async def configure(env, modes=None, versions=1):
    snap = await publish(env)
    assert snap["ready"], snap
    await rpc(
        env.owner,
        "save_generation_config",
        env.sid,
        versions,
        modes if modes is not None else ["context_swap"],
        ORDERING,
        snap["manifest"],
    )
    return snap


def result_for(env, job, index=0, version=1, success=True):
    fixture = json.loads(
        (ROOT / "backend/tests/fixtures/w2_ai_contract.json").read_text(encoding="utf-8-sig")
    )
    result = deepcopy(fixture["cases"]["success"]["result"])
    src = job["context"]["confirmed_sources"][index]
    result.update(
        version_index=version,
        source_question_id=src["source_question_id"],
        error_code=None if success else "PROVIDER_FAILED",
    )
    result["candidate"].update(
        source_question_id=src["source_question_id"],
        seed=100 + version * 1000 + index,
        blueprint_fingerprint=fingerprint(src["canonical_blueprint"]),
    )
    # Synthetic SQL-slot identifier, not a GenerationService cache key.
    result["request_fingerprint"] = fingerprint(
        {"slot": src["source_question_id"], "version": version}
    )
    if not success:
        result.update(candidate=None, validation=None)
    return result


async def persist(env, job, result, **overrides):
    src = next(
        s
        for s in job["context"]["confirmed_sources"]
        if s["source_question_id"] == result["source_question_id"]
    )
    index = job["context"]["confirmed_sources"].index(src)
    c = result["candidate"]
    data = dict(
        session=env.sid,
        token=job["job_id"],
        version=result["version_index"],
        source=result["source_question_id"],
        question_no=src["question_no"],
        success=result["error_code"] is None,
        error=result["error_code"],
        attempts=result["attempts"],
        seed=100 + result["version_index"] * 1000 + index,
        fingerprint=result["request_fingerprint"],
        raw=result,
        content=c["question_text"] if c else None,
        options=c["options"] if c else None,
        key=c["correct_key"] if c else None,
        solution=c["solution_md"] if c else None,
        warning=c["has_warning"] if c else False,
    )
    data.update(overrides)
    return await rpc(env.worker, "persist_generation_result", *data.values())


async def test_canonical_hash_order_and_fresh_chain(db):
    snap = await publish(db)
    assert snap["ready"], snap
    assert await db.admin.fetchval("SELECT count(*) FROM question_blueprints") == 0
    sources = [
        SourceQuestion.model_validate(row["confirmed_input"]) for row in snap["confirmed_sources"]
    ]
    assert snap["confirmed_source_hash"] == source_fingerprint(prepare_sources(sources))
    assert snap["confirmed_source_hash"] != source_fingerprint(
        prepare_sources(list(reversed(sources)))
    )
    for src, row in zip(sources, snap["confirmed_sources"]):
        assert row["source_fingerprint"] == source_fingerprint([source_to_item(src)])
        assert row["blueprint_fingerprint"] == fingerprint(row["canonical_blueprint"])


@pytest.mark.parametrize(
    "modes", [["NUMERICAL"], ["parameter_variation"], ["context_swap"], [], ["NONE"]]
)
async def test_public_modes(db, modes):
    snap = await publish(db)
    result = await rpc(
        db.owner, "save_generation_config", db.sid, 1, modes, ORDERING, snap["manifest"]
    )
    assert result["config"]["active_variation_modes"] == ([] if modes == ["NONE"] else modes)


@pytest.mark.parametrize(
    "modes",
    [
        ["none"],
        [" NONE "],
        ["NONE", "context_swap"],
        ["STRUCTURAL"],
        ["variable_inversion"],
        ["context"],
        ["unknown"],
        [" NUMERICAL "],
        [None],
    ],
)
async def test_reject_unpublished_modes(db, modes):
    snap = await publish(db)
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await rpc(db.owner, "save_generation_config", db.sid, 1, modes, ORDERING, snap["manifest"])


async def test_manifest_required_and_source_change(db):
    snap = await publish(db)
    for expected in (None, {"confirmation_id": str(uuid4()), "sources": []}):
        with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
            await rpc(db.owner, "save_generation_config", db.sid, 1, [], ORDERING, expected)
    await db.admin.execute(
        "UPDATE source_questions SET raw_content=raw_content||'changed' WHERE id=$1::uuid",
        db.rows[0]["id"],
    )
    with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_READY"):
        await rpc(db.owner, "save_generation_config", db.sid, 1, [], ORDERING, snap["manifest"])


async def test_claim_retry_preserves_context_quota_and_full_result(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    result = result_for(db, job)
    await persist(db, job, result)
    await rpc(db.worker, "reserve_generation_quota", db.sid, 1, job["job_id"])
    await rpc(db.worker, "finish_generation_job", db.sid, "partial_generated", job["job_id"])
    retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert retry["job_id"] != job["job_id"]
    assert retry["snapshot_id"] == job["snapshot_id"] and retry["context"] == job["context"]
    assert retry["starting_quota"] == 1 and len(retry["committed_targets"]) == 1
    loaded = await rpc(db.worker, "load_generation_completed_results", db.sid)
    assert loaded["completed"][0]["raw_result"] == result
    with pytest.raises(asyncpg.PostgresError, match="Fencing"):
        await persist(db, job, result)
    assert (await persist(db, retry, result))["replayed"]


async def test_immutable_success_failed_retry_and_finish(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    success = result_for(db, job)
    await persist(db, job, success)
    assert (await persist(db, job, success))["replayed"]
    changed = deepcopy(success)
    changed["candidate"]["question_text"] += " changed"
    with pytest.raises(asyncpg.PostgresError, match="immutable"):
        await persist(db, job, changed)
    with pytest.raises(asyncpg.PostgresError, match="immutable"):
        await persist(db, job, result_for(db, job, success=False))
    await persist(db, job, result_for(db, job, 1, success=False))
    loaded = await rpc(db.worker, "load_generation_completed_results", db.sid)
    assert len(loaded["completed"]) == len(loaded["failures"]) == 1
    with pytest.raises(asyncpg.PostgresError, match="incomplete"):
        await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    await persist(db, job, result_for(db, job, 1))
    assert (await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"]))[
        "status"
    ] == "generated"


@pytest.mark.parametrize(
    "override",
    [
        {"version": 2},
        {"source": str(uuid4())},
        {"question_no": 99},
        {"seed": 42},
        {"session": str(uuid4())},
        {"token": str(uuid4())},
    ],
)
async def test_invalid_slots(db, override):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    with pytest.raises(asyncpg.PostgresError):
        await persist(db, job, result_for(db, job), **override)
    assert await db.admin.fetchval("SELECT count(*) FROM generation_target_results") == 0
    assert await db.admin.fetchval("SELECT count(*) FROM version_questions") == 0


async def test_claim_concurrency(db):
    await configure(db)
    peer = await asyncpg.connect(db.dsn)
    await role(peer, "authenticated")
    try:
        results = await asyncio.gather(
            rpc(db.owner, "claim_generation_job", db.sid, False),
            rpc(peer, "claim_generation_job", db.sid, False),
            return_exceptions=True,
        )
        assert sum(isinstance(r, dict) for r in results) == 1
        assert await db.admin.fetchval("SELECT count(*) FROM generation_job_snapshots") == 1
    finally:
        await peer.close()


async def test_timestamp_failure_rolls_back_both_stores(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    before = await db.admin.fetchval(
        "SELECT updated_at FROM exam_sessions WHERE id=$1::uuid", db.sid
    )
    await db.admin.execute("""CREATE FUNCTION public.test_fail_timestamp() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN RAISE EXCEPTION 'injected timestamp failure'; END $$;
 CREATE TRIGGER z_test_fail BEFORE UPDATE ON exam_sessions FOR EACH ROW EXECUTE FUNCTION test_fail_timestamp();""")
    with pytest.raises(asyncpg.PostgresError, match="injected"):
        await persist(db, job, result_for(db, job))
    assert await db.admin.fetchval("SELECT count(*) FROM version_questions") == 0
    assert await db.admin.fetchval("SELECT count(*) FROM generation_target_results") == 0
    assert (
        await db.admin.fetchval("SELECT updated_at FROM exam_sessions WHERE id=$1::uuid", db.sid)
        == before
    )


async def test_acl_same_transaction_and_jwt_spoof(db):
    await configure(db)
    async with db.owner.transaction():
        await rpc(db.owner, "claim_generation_job", db.sid, False)
        with pytest.raises(asyncpg.PostgresError):
            async with db.owner.transaction():
                await db.owner.execute(
                    "UPDATE exam_sessions SET gemini_call_count=0 WHERE id=$1::uuid", db.sid
                )
    await db.owner.execute("SELECT set_config('request.jwt.claim.role','service_role',false)")
    await db.owner.execute("SELECT set_config('request.jwt.claim.sub',$1,false)", str(uuid4()))
    with pytest.raises(asyncpg.PostgresError, match="Access denied"):
        await rpc(db.owner, "get_generation_source_snapshot", db.sid)
    for name in ("anon", "authenticated"):
        await role(db.owner, name)
        with pytest.raises(asyncpg.PostgresError):
            await db.owner.fetchval(
                "SELECT public.finish_generation_job($1::uuid,'generated',NULL)", db.sid
            )


async def test_migration_replay_preserves_result(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    await persist(db, job, result_for(db, job))
    before = await db.admin.fetchval("SELECT row_to_json(r)::text FROM generation_target_results r")
    await db.admin.execute(
        (ROOT / "backend/migrations/015_stage2_canonical_w2_integration.sql").read_text(
            encoding="utf-8"
        )
    )
    await db.admin.execute(
        (ROOT / "backend/migrations/016_stage2_original_clone.sql").read_text(encoding="utf-8")
    )
    assert (
        await db.admin.fetchval("SELECT row_to_json(r)::text FROM generation_target_results r")
        == before
    )
    assert (
        await db.admin.fetchval(
            "SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname='save_generation_config'"
        )
        == 1
    )


async def test_hash_mapper_ai_fixture_and_english_parity(db):
    fixture = json.loads(
        (ROOT / "backend/tests/fixtures/w2_ai_contract.json").read_text(encoding="utf-8-sig")
    )
    inputs = fixture["source_hashes"]["ordered_sources"]
    inputs += [{**inputs[0], "question_text": "Find the answer", "solution": " \n "}]
    for raw in inputs:
        src = SourceQuestion.model_validate(raw)
        item = source_to_item(src)
        sql_item = json.loads(
            await db.admin.fetchval(
                "SELECT public._generation_source_item($1::jsonb)", json.dumps(src.model_dump())
            )
        )
        assert sql_item == item
        assert await db.admin.fetchval(
            "SELECT public._generation_json($1::jsonb)", json.dumps(item, ensure_ascii=False)
        ) == canonical(item)


@pytest.mark.parametrize("db", ["upgrade"], indirect=True)
async def test_upgrade_preserves_existing_config_and_legacy_data(db):
    assert (
        await db.admin.fetchval("SELECT title FROM exam_sessions WHERE id=$1::uuid", db.sid) == "W2"
    )
    assert (
        await db.admin.fetchval(
            "SELECT n_versions FROM generation_configs WHERE session_id=$1::uuid", db.sid
        )
        == 2
    )
    assert (
        await db.admin.fetchval(
            "SELECT count(*) FROM source_questions WHERE session_id=$1::uuid", db.sid
        )
        == 2
    )
    assert await db.admin.fetchval(
        "SELECT source_manifest IS NULL FROM generation_configs WHERE session_id=$1::uuid", db.sid
    )


async def test_old_ready_manifest_rejected_after_new_blueprint_revision(db):
    snap = await publish(db)
    await db.admin.execute("""WITH old AS (
      SELECT * FROM canonical_blueprint_revisions LIMIT 1
    ), new AS (
      INSERT INTO canonical_blueprint_revisions(blueprint_revision_id,source_revision_id,source_question_id,canonical_blueprint,schema_version)
      SELECT gen_random_uuid(),source_revision_id,source_question_id,canonical_blueprint,schema_version FROM old RETURNING *
    ) UPDATE source_artifact_heads h SET blueprint_revision_id=n.blueprint_revision_id FROM new n WHERE h.source_question_id=n.source_question_id""")
    assert (await rpc(db.owner, "get_generation_source_snapshot", db.sid))["ready"]
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await rpc(db.owner, "save_generation_config", db.sid, 1, [], ORDERING, snap["manifest"])


async def test_no_display_only_completion_or_legacy_write_bypass(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    await persist(db, job, result_for(db, job))
    await persist(db, job, result_for(db, job, 1))
    await db.admin.execute(
        "DELETE FROM generation_target_results WHERE source_question_id=$1::uuid", db.rows[1]["id"]
    )
    with pytest.raises(asyncpg.PostgresError, match="incomplete"):
        await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    assert (
        len((await rpc(db.worker, "load_generation_completed_results", db.sid))["completed"]) == 1
    )
    with pytest.raises(asyncpg.PostgresError, match="persist_generation_result"):
        await db.worker.fetchval(
            "SELECT public.persist_version_question($1::uuid,$2::uuid,1,$3::uuid,1,'bypass','[]','A',NULL,false)",
            db.sid,
            job["job_id"],
            db.rows[0]["id"],
        )


async def test_claim_rolls_back_snapshot_on_state_transition_failure(db):
    await configure(db)
    await db.admin.execute("""CREATE FUNCTION public.test_fail_claim() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'injected claim failure'; END $$;
      CREATE TRIGGER z_test_fail_claim BEFORE UPDATE ON exam_sessions FOR EACH ROW EXECUTE FUNCTION test_fail_claim();""")
    with pytest.raises(asyncpg.PostgresError, match="injected"):
        await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert await db.admin.fetchval("SELECT count(*) FROM generation_job_snapshots") == 0
    assert (
        await db.admin.fetchval("SELECT status FROM exam_sessions WHERE id=$1::uuid", db.sid)
        == "configured"
    )


async def test_quota_cap_and_worker_only_rpc_acl(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    await rpc(db.worker, "reserve_generation_quota", db.sid, 250, job["job_id"])
    with pytest.raises(asyncpg.PostgresError):
        await rpc(db.worker, "reserve_generation_quota", db.sid, 1, job["job_id"])
    for signature in (
        "public.persist_generation_result(uuid,uuid,int,uuid,int,boolean,text,int,int,text,jsonb,text,jsonb,text,text,boolean)",
        "public.reserve_generation_quota(uuid,int,uuid)",
        "public.finish_generation_job(uuid,text,uuid)",
        "public._generation_legacy_claim(uuid,boolean)",
    ):
        assert not await db.admin.fetchval(
            "SELECT has_function_privilege('authenticated',$1,'EXECUTE')", signature
        )
        assert not await db.admin.fetchval(
            "SELECT has_function_privilege('anon',$1,'EXECUTE')", signature
        )


async def test_legacy_modes_match_exact_stored_ids(db):
    await db.admin.execute(
        "UPDATE exam_sessions SET status='blueprinted' WHERE id=$1::uuid", db.sid
    )
    for row, modes in zip(db.rows, [[" NUMERICAL "], ["NUMERICAL"]]):
        await db.admin.execute(
            "INSERT INTO question_blueprints(source_question_id,confirmed_at,variation_modes) VALUES($1::uuid,now(),$2::jsonb)",
            row["id"],
            json.dumps(modes),
        )
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await rpc(db.owner, "save_generation_config", db.sid, 1, ["NUMERICAL"], ORDERING, None)
    await rpc(db.owner, "save_generation_config", db.sid, 1, [], ORDERING, None)
    legacy = await rpc(db.owner, "claim_generation_job", db.sid, False)
    assert "snapshot_id" not in legacy


@pytest.mark.parametrize("mutation", ["missing", "malformed", "bad_fingerprint"])
async def test_not_ready_canonical_evidence(db, mutation):
    await publish(db)
    if mutation == "missing":
        await db.admin.execute("UPDATE source_artifact_heads SET blueprint_revision_id=NULL")
    elif mutation == "malformed":
        await db.admin.execute(
            "UPDATE canonical_blueprint_revisions SET canonical_blueprint=jsonb_set(canonical_blueprint,'{requirement,variation_policy,allowed_transformations}','{}')"
        )
    else:
        await db.admin.execute(
            "UPDATE source_artifact_revisions SET source_fingerprint=repeat('0',64)"
        )
    snap = await rpc(db.owner, "get_generation_source_snapshot", db.sid)
    assert not snap["ready"]
    with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_READY"):
        await rpc(db.owner, "save_generation_config", db.sid, 1, [], ORDERING, None)


async def test_forced_table_grant_and_manual_guc_cannot_bypass_guards(db):
    await configure(db)
    await db.admin.execute("GRANT UPDATE ON exam_sessions TO authenticated")
    await db.owner.execute("SELECT set_config('app.internal_worker_rpc','true',false)")
    with pytest.raises(asyncpg.PostgresError):
        await db.owner.execute(
            "UPDATE exam_sessions SET gemini_call_count=0,active_job_id=gen_random_uuid() WHERE id=$1::uuid",
            db.sid,
        )
    with pytest.raises(asyncpg.PostgresError):
        await db.owner.execute(
            "INSERT INTO exam_sessions(user_id,title,status,active_job_id) VALUES($1::uuid,'forged','generating',gen_random_uuid())",
            OWNER,
        )


async def test_permission_verification_script(db):
    await db.admin.execute(
        (ROOT / "backend/tests/verify_migration_004_permissions.sql").read_text(
            encoding="utf-8-sig"
        )
    )


async def test_concurrent_persist_same_target_is_one_commit_and_one_replay(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    result = result_for(db, job)
    peer = await asyncpg.connect(db.dsn)
    await role(peer)
    try:
        env = SimpleNamespace(**{**vars(db), "worker": peer})
        responses = await asyncio.gather(persist(db, job, result), persist(env, job, result))
        assert sorted(response["replayed"] for response in responses) == [False, True]
        assert await db.admin.fetchval("SELECT count(*) FROM generation_target_results") == 1
        assert await db.admin.fetchval("SELECT count(*) FROM version_questions") == 1
    finally:
        await peer.close()


async def test_retry_rejects_changed_config_and_missing_snapshot(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    await rpc(db.worker, "finish_generation_job", db.sid, "failed", job["job_id"])
    await db.admin.execute(
        "UPDATE generation_configs SET n_versions=2 WHERE session_id=$1::uuid", db.sid
    )
    with pytest.raises(asyncpg.PostgresError, match="incompatible"):
        await rpc(db.owner, "claim_generation_job", db.sid, True)
    await db.admin.execute("DELETE FROM generation_job_snapshots WHERE session_id=$1::uuid", db.sid)
    with pytest.raises(asyncpg.PostgresError, match="missing"):
        await rpc(db.owner, "claim_generation_job", db.sid, True)


async def test_w2_output_remains_reviewable_shufflable_and_approvable(db):
    from tests.migrations.test_shuffle_writer_adversarial import payload, snapshot

    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    for index in range(2):
        await persist(db, job, result_for(db, job, index))
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    for question in await db.admin.fetch("SELECT id FROM version_questions"):
        await db.owner.fetchval(
            "SELECT public.review_accept_question($1::uuid,$2::uuid,$3::uuid)",
            db.sid,
            question["id"],
            uuid4(),
        )
    data = payload(db.sid, await snapshot(db.admin, db.sid))
    data["actor_id"] = OWNER
    await db.worker.fetchval(
        "SELECT public.finalize_persist_shuffle($1::uuid,$2::jsonb)", db.sid, json.dumps(data)
    )
    approved = json.loads(
        await db.owner.fetchval(
            "SELECT public.finalize_approve_session($1::uuid,NULL,NULL)", db.sid
        )
    )
    assert approved["status"] == "approved"
    with pytest.raises(asyncpg.PostgresError):
        await db.owner.execute("UPDATE exam_sessions SET title='changed' WHERE id=$1::uuid", db.sid)


async def test_rpc_receipt_for_worker_handoff(db):
    snap = await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    result = result_for(db, job)
    persisted = await persist(db, job, result)
    await persist(db, job, result_for(db, job, 1, success=False))
    resumed = await rpc(db.worker, "load_generation_completed_results", db.sid)
    assert resumed["completed"][0]["raw_result"] == result
    assert len(resumed["failures"]) == 1
    output = os.environ.get("TASK207_CONTRACT_OUTPUT")
    if output:
        # Explicit opt-in artifact from actual SQL responses; no credentials.
        receipt = {
            "provenance": "Real PostgreSQL RPC excerpt; offline AI fixture; synthetic slot/version request hash, not GenerationService cache evidence",
            "synthetic_request_fingerprint": True,
            "source_snapshot": snap,
            "claim": job,
            "persist": persisted,
            "resume": resumed,
        }
        receipt = deepcopy(receipt)
        receipt["omitted_fields"] = [
            "source_snapshot.confirmed_sources[].canonical_blueprint",
            "claim.context.confirmed_sources",
            "resume.context.confirmed_sources",
        ]
        for source in receipt["source_snapshot"]["confirmed_sources"]:
            source.pop("canonical_blueprint")
        receipt["claim"]["context"].pop("confirmed_sources")
        receipt["resume"]["context"].pop("confirmed_sources")
        Path(output).write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


async def test_legitimate_owner_create_metadata_update_and_delete(db):
    row = await db.owner.fetchrow(
        "INSERT INTO exam_sessions(user_id,title,subject,grade) VALUES($1::uuid,'draft','Toán',12) RETURNING id,status,gemini_call_count",
        OWNER,
    )
    assert row["status"] == "draft" and row["gemini_call_count"] == 0
    await db.owner.execute("UPDATE exam_sessions SET title='edited' WHERE id=$1::uuid", row["id"])
    assert (
        await db.owner.fetchval("SELECT title FROM exam_sessions WHERE id=$1::uuid", row["id"])
        == "edited"
    )
    await db.owner.execute("DELETE FROM exam_sessions WHERE id=$1::uuid", row["id"])
    assert (
        await db.admin.fetchval("SELECT count(*) FROM exam_sessions WHERE id=$1::uuid", row["id"])
        == 0
    )


async def test_mode_must_be_supported_by_every_canonical_source(db):
    await publish(db)
    await db.admin.execute(
        """UPDATE canonical_blueprint_revisions SET canonical_blueprint=jsonb_set(
        canonical_blueprint,'{requirement,variation_policy,allowed_transformations}','[{"dimension":"values"}]')
        WHERE source_question_id=$1::uuid""",
        db.rows[1]["id"],
    )
    snap = await rpc(db.owner, "get_generation_source_snapshot", db.sid)
    assert snap["ready"]
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await rpc(
            db.owner,
            "save_generation_config",
            db.sid,
            1,
            ["context_swap"],
            ORDERING,
            snap["manifest"],
        )
    await rpc(
        db.owner,
        "save_generation_config",
        db.sid,
        1,
        ["NUMERICAL", "parameter_variation", "NUMERICAL"],
        ORDERING,
        snap["manifest"],
    )
    config = await db.admin.fetchrow(
        "SELECT active_variation_modes,canonical_dimensions FROM generation_configs WHERE session_id=$1::uuid",
        db.sid,
    )
    assert json.loads(config["active_variation_modes"]) == ["NUMERICAL", "parameter_variation"]
    assert json.loads(config["canonical_dimensions"]) == ["values"]


@pytest.mark.parametrize(
    "value",
    [
        0,
        0.0,
        1.0,
        -0.0,
        0.1,
        -12.5,
        1e-4,
        1e-5,
        1e-7,
        1e15,
        1e16,
        1e20,
        1e-300,
        5e-324,
        1.7976931348623157e308,
        9007199254740993,
        10**80 + 1,
    ],
)
async def test_numeric_json_matches_python_after_database_roundtrip(db, value):
    supplied = {"z": [value, {"tiếng Việt": value}], "a": True, "none": None}
    stored = json.loads(await db.admin.fetchval("SELECT $1::jsonb::text", json.dumps(supplied)))
    expected = canonical(stored)
    for precision in (-1, 3):
        await db.admin.execute(f"SET extra_float_digits={precision}")
        actual = await db.admin.fetchval(
            "SELECT public._generation_json($1::jsonb)", json.dumps(stored)
        )
        assert actual == expected


async def test_f11_small_tolerance_persists_python_fingerprint_and_resumes(db):
    for blueprint in db.blueprints:
        blueprint["requirement"]["response_spec"]["grading"]["numeric_tolerance"] = {
            "absolute": 1e-7,
            "relative": 0.0,
        }
    snapshot = await configure(db)
    for source in snapshot["confirmed_sources"]:
        assert source["blueprint_fingerprint"] == fingerprint(source["canonical_blueprint"])
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    result = result_for(db, job)
    expected = fingerprint(job["context"]["confirmed_sources"][0]["canonical_blueprint"])
    assert result["candidate"]["blueprint_fingerprint"] == expected
    bad = deepcopy(result)
    bad["candidate"]["blueprint_fingerprint"] = "0" * 64
    with pytest.raises(asyncpg.PostgresError, match="invalid successful result"):
        await persist(db, job, bad)
    assert await db.admin.fetchval("SELECT count(*) FROM generation_target_results") == 0
    assert await db.admin.fetchval("SELECT count(*) FROM version_questions") == 0
    await persist(db, job, result)
    assert (await persist(db, job, result))["replayed"]
    saved = await db.admin.fetchval("SELECT row_to_json(r)::text FROM generation_target_results r")
    await db.admin.execute(
        (ROOT / "backend/migrations/015_stage2_canonical_w2_integration.sql").read_text(
            encoding="utf-8"
        )
    )
    assert (
        await db.admin.fetchval("SELECT row_to_json(r)::text FROM generation_target_results r")
        == saved
    )
    await rpc(db.worker, "finish_generation_job", db.sid, "partial_generated", job["job_id"])
    retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert retry["snapshot_id"] == job["snapshot_id"]
    assert retry["context"] == job["context"]
    resumed = await rpc(db.worker, "load_generation_completed_results", db.sid)
    assert resumed["completed"][0]["raw_result"] == result
    assert (await persist(db, retry, result))["replayed"]


@pytest.mark.parametrize(
    "literal",
    [
        "10000000000000000.0",
        "100000000000000000000000.0",
        "1.234567890123456789012345",
        "-1e-400",
        "1e-400",
        "2.4703282292062328e-324",
    ],
)
async def test_decimal_storage_preserves_python_float_semantics(db, literal):
    stored = await db.admin.fetchval("SELECT $1::jsonb::text", literal)
    actual = await db.admin.fetchval("SELECT public._generation_json($1::jsonb)", stored)
    assert actual == canonical(json.loads(stored))


async def test_seeded_binary64_sample_matches_python(db):
    import math
    import random
    import struct
    from decimal import Decimal

    random_bits = random.Random(207)
    for _ in range(256):
        value = struct.unpack(">d", random_bits.getrandbits(64).to_bytes(8, "big"))[0]
        if not math.isfinite(value):
            continue
        literal = format(Decimal.from_float(value), "f")
        if "." not in literal:
            literal += ".0"
        stored = await db.admin.fetchval("SELECT $1::jsonb::text", literal)
        assert await db.admin.fetchval(
            "SELECT public._generation_json($1::jsonb)", stored
        ) == canonical(json.loads(stored))

"""Original Clone SQL contract; no worker/AI implementation or provider doubles."""

import asyncio
import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.generation.service import fingerprint
from tests.migrations.test_generation_w2 import (
    ROOT,
    asyncpg,
    configure,
    persist,
    result_for,
    role,
    rpc,
)
from tests.migrations.test_generation_w2 import (
    db as db,
)

pytestmark = pytest.mark.asyncio
MIGRATION = ROOT / "backend/migrations/011_stage2_original_clone.sql"


def clone_record(job, index=0, version=1):
    src = job["context"]["confirmed_sources"][index]
    source = src["confirmed_input"]
    return dict(
        result_kind="ORIGINAL_CLONE",
        snapshot_id=job["snapshot_id"],
        version_index=version,
        source_question_id=src["source_question_id"],
        question_no=src["question_no"],
        source_revision_id=src["source_revision_id"],
        source_fingerprint=src["source_fingerprint"],
        blueprint_revision_id=src["blueprint_revision_id"],
        confirmed_source_hash=job["context"]["confirmed_source_hash"],
        seed=job["context"]["base_seed"] + version * 1000 + index,
        content=source["question_text"],
        options=source["options"],
        correct_key=source["correct_answer"],
        solution_md=source.get("solution"),
    )


async def save(env, job, record=None, conn=None, **overrides):
    args = dict(session=env.sid, token=job["job_id"], raw=record or clone_record(job))
    args.update(overrides)
    return await rpc(conn or env.worker, "persist_generation_clone", *args.values())


async def start(env, versions=2):
    await configure(env, modes=[], versions=versions)
    return await rpc(env.owner, "claim_generation_job", env.sid, False)


async def assert_empty(env):
    for table in ("generation_target_results", "version_questions", "exam_versions"):
        assert await env.admin.fetchval(f"SELECT count(*) FROM {table}") == 0


@pytest.mark.parametrize("solution", [None, "", "Đáp án A; giữ nguyên $x^2$."])
async def test_clone_matrix_resume_and_finish_without_quota_or_ai(db, solution):
    for row, blueprint in zip(db.rows, db.blueprints):
        row["solution_md"] = solution
        if solution:
            qid = blueprint["requirement"]["source"]["question_id"]
            blueprint["requirement"]["source"]["supplied_solution"] = [
                {"id": qid + ".solution", "type": "text", "text": solution}
            ]
    await db.admin.execute("UPDATE source_questions SET solution_md=$1", solution)
    job = await start(db)
    # The existing producer normalizes absent solutions to an empty string.
    frozen_solution = job["context"]["confirmed_sources"][0]["confirmed_input"].get("solution")
    assert frozen_solution == (solution or "")
    # A pre-existing uncertain charge is retained; clone adds no charge or AI proof.
    await db.admin.execute("UPDATE exam_sessions SET gemini_call_count=7")
    first_receipt = None
    for version in (1, 2):
        for index in (0, 1):
            record = clone_record(job, index, version)
            receipt = await save(db, job, record)
            if version == 1 and index == 0:
                first_receipt = receipt
            assert receipt["result_kind"] == "ORIGINAL_CLONE" and not receipt["replayed"]
            assert receipt["clone_fingerprint"] == fingerprint(record)
    loaded = await rpc(db.owner, "load_generation_completed_results", db.sid)
    assert len(loaded["completed"]) == 4 and loaded["failures"] == []
    for row in loaded["completed"]:
        record = row["raw_result"]
        assert row["result_kind"] == record["result_kind"] == "ORIGINAL_CLONE"
        assert row["request_fingerprint"] is None and row["clone_fingerprint"] == fingerprint(
            record
        )
        assert record["solution_md"] == frozen_solution
        assert not {"candidate", "validation", "request_fingerprint"} & record.keys()
    assert await db.admin.fetchval(
        "SELECT bool_and(attempts=0 AND request_fingerprint IS NULL) FROM generation_target_results"
    )
    assert await db.admin.fetchval(
        "SELECT bool_and(validation_report='{}'::jsonb) FROM version_questions"
    )
    assert await db.admin.fetchval(
        "SELECT bool_and(canonical_solution_md IS NOT DISTINCT FROM $1::text AND solution_md IS NOT DISTINCT FROM $1::text) FROM version_questions",
        frozen_solution,
    )
    finished = await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    assert finished["status"] == "generated"
    assert await db.admin.fetchval("SELECT gemini_call_count FROM exam_sessions") == 7
    output = os.environ.get("TASK207_CLONE_CONTRACT_OUTPUT")
    if output and solution:
        Path(output).write_text(
            json.dumps(
                dict(
                    evidence="Actual PostgreSQL RPC outputs; synthetic source data; no worker/provider E2E",
                    omitted_fields=["claim.context", "resume.context", "resume.completed[1:]"],
                    claim={k: v for k, v in job.items() if k != "context"},
                    request=dict(
                        p_session_id=db.sid,
                        p_job_token=job["job_id"],
                        p_clone_record=clone_record(job),
                    ),
                    response=first_receipt,
                    resume={k: v for k, v in loaded.items() if k != "context"}
                    | {"completed": loaded["completed"][:1]},
                    finish=finished,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


async def test_clone_restart_retry_fences_old_token_and_keeps_committed_record(db):
    job = await start(db)
    record = clone_record(job)
    first = await save(db, job, record)
    before = await db.admin.fetchval("SELECT row_to_json(r)::text FROM generation_target_results r")
    with pytest.raises(asyncpg.PostgresError, match="incomplete"):
        await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    await rpc(db.worker, "finish_generation_job", db.sid, "partial_generated", job["job_id"])
    # Frozen confirmed source remains authoritative when live source text changes.
    await db.admin.execute("UPDATE source_questions SET raw_content=raw_content||' live edit'")
    retry = await rpc(db.owner, "claim_generation_job", db.sid, True)
    assert retry["snapshot_id"] == job["snapshot_id"] and retry["context"] == job["context"]
    assert retry["committed_targets"] == [
        dict(
            version_code="101",
            version_index=1,
            source_question_id=record["source_question_id"],
            question_no=record["question_no"],
            result_kind="ORIGINAL_CLONE",
        )
    ]
    conn = await asyncpg.connect(db.dsn)
    try:
        await role(conn)
        loaded = await rpc(conn, "load_generation_completed_results", db.sid)
        assert loaded["completed"][0]["raw_result"] == record
        with pytest.raises(asyncpg.PostgresError, match="Fencing"):
            await save(db, job, record, conn=conn)
        replay = await save(db, retry, record, conn=conn)
        assert replay["replayed"] and replay["version_question_id"] == first["version_question_id"]
        for version, index in ((1, 1), (2, 0), (2, 1)):
            await save(db, retry, clone_record(retry, index, version), conn=conn)
        await rpc(conn, "finish_generation_job", db.sid, "generated", retry["job_id"])
    finally:
        await conn.close()
    assert (
        await db.admin.fetchval(
            "SELECT row_to_json(r)::text FROM generation_target_results r WHERE version_index=1 AND question_no=1"
        )
        == before
    )
    assert await db.admin.fetchval("SELECT count(*) FROM version_questions") == 4


@pytest.mark.parametrize(
    "change",
    [
        {"result_kind": "AI_RESULT"},
        {"snapshot_id": str(uuid4())},
        {"source_revision_id": str(uuid4())},
        {"blueprint_revision_id": str(uuid4())},
        {"source_question_id": str(uuid4())},
        {"source_fingerprint": "0" * 64},
        {"confirmed_source_hash": "0" * 64},
        {"version_index": 3},
        {"version_index": "1"},
        {"version_index": None},
        {"question_no": 99},
        {"question_no": 1.0},
        {"seed": 42},
        {"seed": 1100.0},
        {"content": "changed"},
        {"options": ["A", "B", "C"]},
        {"correct_key": "Z"},
        {"solution_md": "invented"},
        {"validation": {"checks": []}},
    ],
)
async def test_clone_rejects_wrong_identity_provenance_or_payload(db, change):
    job = await start(db)
    record = clone_record(job)
    record.update(change)
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await save(db, job, record)
    await assert_empty(db)
    assert await db.admin.fetchval("SELECT gemini_call_count FROM exam_sessions") == 0


async def test_clone_conflict_and_ai_writer_cannot_overwrite_success(db):
    job = await start(db)
    record = clone_record(job)
    await save(db, job, record)
    before = await db.admin.fetchval("SELECT row_to_json(r)::text FROM generation_target_results r")
    changed = deepcopy(record)
    changed["content"] += " changed"
    with pytest.raises(asyncpg.PostgresError, match="ERR_CONFIG_CONFLICT"):
        await save(db, job, changed)
    with pytest.raises(asyncpg.PostgresError, match="immutable"):
        await persist(db, job, result_for(db, job))
    assert (
        await db.admin.fetchval("SELECT row_to_json(r)::text FROM generation_target_results r")
        == before
    )


@pytest.mark.parametrize("success", [False, True])
async def test_clone_retries_failed_slot_but_preserves_ai_success(db, success):
    job = await start(db)
    # Compatibility probe for a slot written through the unchanged 010 AI RPC.
    await persist(db, job, result_for(db, job, success=success))
    if success:
        with pytest.raises(asyncpg.PostgresError, match="immutable"):
            await save(db, job)
    else:
        await save(db, job)
        loaded = await rpc(db.worker, "load_generation_completed_results", db.sid)
        assert loaded["failures"] == []
        assert loaded["completed"][0]["result_kind"] == "ORIGINAL_CLONE"
        assert loaded["completed"][0]["request_fingerprint"] is None


async def test_clone_acl_nonclone_config_and_wrong_session(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    with pytest.raises(asyncpg.PostgresError, match="modes"):
        await save(db, job)
    with pytest.raises(asyncpg.PostgresError, match="Session not found"):
        await save(db, job, session=str(uuid4()))
    for principal in ("anon", "authenticated"):
        await role(db.owner, principal)
        await db.owner.execute("SELECT set_config('request.jwt.claim.role','service_role',false)")
        with pytest.raises(asyncpg.PostgresError):
            await save(db, job, conn=db.owner)
        for signature in (
            "persist_generation_clone(uuid,uuid,jsonb)",
            "_generation_committed(uuid,uuid)",
            "_generation_claim_010(uuid,boolean)",
            "_generation_finish_010(uuid,text,uuid)",
        ):
            assert not await db.admin.fetchval(
                "SELECT has_function_privilege($1,$2,'EXECUTE')", principal, "public." + signature
            )
    # Even an accidental EXECUTE grant cannot turn a forged JWT GUC into a worker.
    await db.admin.execute(
        "GRANT EXECUTE ON FUNCTION persist_generation_clone(uuid,uuid,jsonb) TO authenticated"
    )
    with pytest.raises(asyncpg.PostgresError, match="Worker only"):
        await save(db, job, conn=db.owner)
    await assert_empty(db)


@pytest.mark.parametrize(
    "field,value",
    [
        ("options", {}),
        ("options", [1, "B", "C", "D"]),
        ("options", ["A"]),
        ("correct_answer", None),
        ("question_text", ""),
        ("solution", {}),
    ],
)
async def test_clone_malformed_frozen_source_no_write(db, field, value):
    job = await start(db)
    context = deepcopy(job["context"])
    context["confirmed_sources"][0]["confirmed_input"][field] = value
    # Admin corruption probes: API roles cannot write frozen snapshots.
    await db.admin.execute(
        "UPDATE generation_job_snapshots SET snapshot_payload=$1::jsonb", json.dumps(context)
    )
    with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_READY"):
        await save(db, job)
    await assert_empty(db)


async def test_clone_transaction_failure_rolls_back_projection_and_result(db):
    job = await start(db)
    await db.admin.execute("""CREATE FUNCTION public.test_fail_clone() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'injected clone failure'; END $$;
    CREATE TRIGGER z_test_fail BEFORE UPDATE ON exam_sessions FOR EACH ROW EXECUTE FUNCTION test_fail_clone();""")
    with pytest.raises(asyncpg.PostgresError, match="injected clone failure"):
        await save(db, job)
    await assert_empty(db)
    assert await db.admin.fetchval("SELECT active_job_id::text FROM exam_sessions") == job["job_id"]


@pytest.mark.parametrize(
    "mutation", ["content=content||'changed'", "question_no=99", "is_current=false"]
)
async def test_clone_finish_and_resume_require_intact_exact_projection(db, mutation):
    job = await start(db, versions=1)
    for index in (0, 1):
        await save(db, job, clone_record(job, index))
    await db.admin.execute(f"UPDATE version_questions SET {mutation} WHERE question_no=1")
    assert (
        len((await rpc(db.worker, "load_generation_completed_results", db.sid))["completed"]) == 1
    )
    with pytest.raises(asyncpg.PostgresError, match="incomplete"):
        await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])
    with pytest.raises(asyncpg.PostgresError, match="projection changed"):
        await save(db, job)
    assert await db.admin.fetchval("SELECT count(*) FROM generation_target_results") == 2


async def test_clone_concurrent_lost_response_replay(db):
    job = await start(db)
    conn = await asyncpg.connect(db.dsn)
    try:
        await role(conn)
        results = await asyncio.gather(save(db, job), save(db, job, conn=conn))
        assert sorted(r["replayed"] for r in results) == [False, True]
        assert results[0]["version_question_id"] == results[1]["version_question_id"]
    finally:
        await conn.close()
    assert await db.admin.fetchval("SELECT count(*) FROM version_questions") == 1


@pytest.mark.parametrize("db", ["pre_clone"], indirect=True)
async def test_clone_forward_upgrade_preserves_ai_and_chain_replay(db):
    await configure(db)
    job = await rpc(db.owner, "claim_generation_job", db.sid, False)
    ai = result_for(db, job)
    await persist(db, job, ai)
    before = await db.admin.fetchval("SELECT raw_result::text FROM generation_target_results")
    await db.admin.execute(MIGRATION.read_text(encoding="utf-8"))
    await db.admin.execute(MIGRATION.read_text(encoding="utf-8"))
    assert (
        await db.admin.fetchval("SELECT raw_result::text FROM generation_target_results") == before
    )
    loaded = await rpc(db.worker, "load_generation_completed_results", db.sid)
    assert loaded["completed"][0]["result_kind"] == "AI_RESULT"
    assert loaded["completed"][0]["raw_result"] == ai
    assert loaded["completed"][0]["request_fingerprint"] == ai["request_fingerprint"]
    assert loaded["completed"][0]["clone_fingerprint"] is None
    await persist(db, job, result_for(db, job, index=1))
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])


async def test_clone_replay_migrations_preserves_results_and_resume(db):
    job = await start(db, versions=1)
    for index in (0, 1):
        await save(db, job, clone_record(job, index))
    before = await db.admin.fetchval(
        "SELECT jsonb_agg(to_jsonb(r) ORDER BY question_no)::text FROM generation_target_results r"
    )
    for _ in range(2):
        await db.admin.execute(
            (ROOT / "backend/migrations/010_stage2_canonical_w2_integration.sql").read_text(
                encoding="utf-8"
            )
        )
        await db.admin.execute(MIGRATION.read_text(encoding="utf-8"))
    assert (
        await db.admin.fetchval(
            "SELECT jsonb_agg(to_jsonb(r) ORDER BY question_no)::text FROM generation_target_results r"
        )
        == before
    )
    assert (
        len((await rpc(db.worker, "load_generation_completed_results", db.sid))["completed"]) == 2
    )
    assert (await save(db, job))["replayed"]
    await rpc(db.worker, "finish_generation_job", db.sid, "generated", job["job_id"])

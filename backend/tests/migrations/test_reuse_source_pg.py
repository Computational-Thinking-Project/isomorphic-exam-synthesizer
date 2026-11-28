"""EXT-02 Step 7 core: reuse_session_source (migration 028c) on real PostgreSQL.

Uses the opt-in disposable W2 fixture (RUN_TASK207_REAL_DB_TESTS). No EXT-04 tables yet.
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests.migrations.test_generation_w2 import OWNER, ROOT, TYPES, asyncpg, role, rpc
from tests.migrations.test_generation_w2 import db as db  # noqa: F401
from tests.migrations.test_shuffle_only_confirm_pg import generated_shuffle_only
from tests.migrations.test_shuffle_only_confirm_pg import migrate as migrate_028b

pytestmark = [pytest.mark.asyncio, pytest.mark.parametrize("db", ["w4"], indirect=True)]
SQL_028C = ROOT / "backend/migrations/028c_ext02_reuse_source.sql"
TYPES["confirm_shuffle_only_copies"] = ["uuid"]
TYPES["reuse_session_source"] = ["uuid", "text", "uuid", "text", "text"]
PLACEHOLDER = "Không có lời giải cho câu hỏi này."
FIXTURE = Path(__file__).resolve().parents[3] / "docs/tasks/fixtures/I-EXT-03.json"


async def migrate(db):
    await migrate_028b(db)
    await db.admin.execute(SQL_028C.read_text(encoding="utf-8"))


async def approved_session(db):
    """Shuffle-only round confirmed, shuffled (both flags on) and approved through the real RPCs."""
    from app.services.finalize.shuffle_input import prepare_shuffle

    await generated_shuffle_only(db)
    await db.admin.execute(
        "UPDATE generation_configs SET ordering_preferences='{\"shuffle_questions\":true,\"shuffle_options\":true}'"
        " WHERE session_id=$1::uuid", db.sid,
    )
    await rpc(db.owner, "confirm_shuffle_only_copies", db.sid)

    async def rows(table):
        return [json.loads(r[0]) for r in await db.owner.fetch(f"SELECT to_jsonb(t) FROM {table} t")]

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
    return await db.admin.fetchval(
        "SELECT id::text FROM exam_versions WHERE session_id=$1::uuid AND version_code='101'", db.sid
    )


async def reuse(db, source_type, version_id, key, mode="shuffle_only", conn=None):
    return await rpc(conn or db.owner, "reuse_session_source", db.sid, source_type, version_id, mode, key)


async def new_sources(db, session_id):
    return [dict(r) for r in await db.admin.fetch(
        "SELECT question_no, raw_content, options::text AS options, correct_key, solution_md"
        " FROM source_questions WHERE session_id=$1::uuid ORDER BY question_no", session_id,
    )]


async def session_count(db):
    return await db.admin.fetchval("SELECT count(*) FROM exam_sessions")


async def test_reuse_version_copies_post_shuffle_projection(db):
    await migrate(db)
    version_id = await approved_session(db)
    result = await reuse(db, "version", version_id, "reuse-version-1")
    assert result["status"] == "draft" and result["next_step"] == "confirm_source"
    assert result["generation_mode"] == "shuffle_only" and result["replayed"] is False
    projection = [dict(r) for r in await db.admin.fetch(
        "SELECT question_no, content, options::text AS options, correct_key, solution_md, canonical_question_no"
        " FROM version_questions WHERE version_id=$1::uuid AND is_current ORDER BY question_no", version_id,
    )]
    assert result["source"]["new_source_order"] == [row["canonical_question_no"] for row in projection]
    copied = await new_sources(db, result["session_id"])
    assert [row["question_no"] for row in copied] == list(range(1, len(projection) + 1))
    for old, new in zip(projection, copied):
        assert new["raw_content"] == old["content"]
        assert json.loads(new["options"]) == json.loads(old["options"])  # display order kept
        assert new["correct_key"] == old["correct_key"]  # display key
        expected_solution = None if old["solution_md"] in (None, "", PLACEHOLDER) else old["solution_md"]
        assert new["solution_md"] == expected_solution
    title = await db.admin.fetchval("SELECT title FROM exam_sessions WHERE id=$1::uuid", db.sid)
    assert await db.admin.fetchval(
        "SELECT title FROM exam_sessions WHERE id=$1::uuid", result["session_id"]
    ) == title
    assert await db.admin.fetchval(
        "SELECT status FROM exam_sessions WHERE id=$1::uuid", db.sid
    ) == "approved"  # the source round is never reopened


async def test_reuse_original_copies_frozen_confirmed_source(db):
    await migrate(db)
    await approved_session(db)
    result = await reuse(db, "original", None, "reuse-original-1", mode="ai_generation")
    frozen = json.loads(await db.admin.fetchval(
        "SELECT snapshot_payload->'confirmed_sources' FROM generation_job_snapshots WHERE session_id=$1::uuid", db.sid
    ))
    copied = await new_sources(db, result["session_id"])
    assert len(copied) == len(frozen)
    for source, new in zip(frozen, copied):
        assert new["raw_content"] == source["confirmed_input"]["question_text"]
        assert json.loads(new["options"]) == source["confirmed_input"]["options"]
        assert new["correct_key"] == source["confirmed_input"]["correct_answer"]
    assert result["source"]["new_source_order"] == [source["question_no"] for source in frozen]


async def test_idempotent_replay_and_conflict(db):
    await migrate(db)
    version_id = await approved_session(db)
    first = await reuse(db, "version", version_id, "same-key")
    count = await session_count(db)
    replay = await reuse(db, "version", version_id, "same-key")
    assert replay == {**first, "replayed": True}
    assert await session_count(db) == count
    with pytest.raises(asyncpg.PostgresError, match="ERR_IDEMPOTENCY_CONFLICT"):
        await reuse(db, "version", version_id, "same-key", mode="ai_generation")
    assert await session_count(db) == count


async def test_foreign_user_cannot_reuse(db):
    await migrate(db)
    version_id = await approved_session(db)
    count = await session_count(db)
    await role(db.owner, "authenticated", str(uuid4()))
    with pytest.raises(asyncpg.PostgresError, match="Session not found"):
        await reuse(db, "version", version_id, "foreign-key")
    await role(db.owner, "anon", str(uuid4()))
    with pytest.raises(asyncpg.PostgresError, match="permission denied"):
        await reuse(db, "version", version_id, "anon-key")
    assert await session_count(db) == count


async def test_non_approved_source_and_foreign_version_are_rejected(db):
    await migrate(db)
    await generated_shuffle_only(db)
    await rpc(db.owner, "confirm_shuffle_only_copies", db.sid)  # reviewed, not approved
    version_id = await db.admin.fetchval("SELECT id::text FROM exam_versions LIMIT 1")
    count = await session_count(db)
    with pytest.raises(asyncpg.PostgresError, match="ERR_SOURCE_NOT_APPROVED"):
        await reuse(db, "version", version_id, "not-approved")
    for source_type, version in (("version", str(uuid4())), ("version", None), ("original", version_id)):
        with pytest.raises(asyncpg.PostgresError):
            await reuse(db, source_type, version, f"bad-{uuid4()}")
    assert await session_count(db) == count


async def test_failure_rolls_back_everything(db):
    await migrate(db)
    version_id = await approved_session(db)
    count = await session_count(db)
    await db.admin.execute("""
        CREATE FUNCTION public._test_fail_insert() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.question_no = 2 THEN RAISE EXCEPTION 'TEST_FORCED_FAILURE'; END IF; RETURN NEW; END $$;
        CREATE TRIGGER test_fail_insert BEFORE INSERT ON public.source_questions
          FOR EACH ROW EXECUTE FUNCTION public._test_fail_insert();
    """)
    with pytest.raises(asyncpg.PostgresError, match="TEST_FORCED_FAILURE"):
        await reuse(db, "version", version_id, "rollback-key")
    assert await session_count(db) == count
    assert await db.admin.fetchval("SELECT count(*) FROM ext02_reuse_receipts") == 0


async def test_more_than_twenty_questions_rejected_before_any_write(db):
    await migrate(db)
    await approved_session(db)
    await db.admin.execute(
        "UPDATE generation_job_snapshots SET snapshot_payload=jsonb_set(snapshot_payload,'{confirmed_sources}',"
        "(SELECT jsonb_agg(x) FROM generate_series(1,21) g, LATERAL (SELECT snapshot_payload->'confirmed_sources'->0) s(x)))"
        " WHERE session_id=$1::uuid", db.sid,
    )
    count = await session_count(db)
    with pytest.raises(asyncpg.PostgresError, match="1-20 questions"):
        await reuse(db, "original", None, "too-many")
    assert await session_count(db) == count


async def test_receipt_matches_i_ext_03_reuse_example_shape(db):
    await migrate(db)
    version_id = await approved_session(db)
    result = await reuse(db, "version", version_id, "shape-key")
    example = next(
        case for case in json.loads(FIXTURE.read_text(encoding="utf-8"))["reuse_examples"]
        if case["case"] == "reuse_approved_version_shuffle_only"
    )["response_201"]
    assert {"session_id", "status", "next_step", "source"} <= set(result)
    assert {"source_type", "source_version_id", "new_source_order"} <= set(result["source"])
    assert set(example["source"]) <= set(result["source"])
    assert result["status"] == example["status"]


async def test_missing_source_solution_placeholder_becomes_null_in_new_source(db):
    """I-EXT-03 v3: the placeholder in the projection is stored as NULL in the new source input."""
    await migrate(db)
    db.rows[1]["solution_md"] = None
    await db.admin.execute("UPDATE source_questions SET solution_md=NULL WHERE id=$1::uuid", db.rows[1]["id"])
    version_id = await approved_session(db)
    placeholders = await db.admin.fetchval(
        "SELECT count(*) FROM version_questions WHERE version_id=$1::uuid AND is_current AND solution_md=$2",
        version_id, PLACEHOLDER,
    )
    assert placeholders >= 1
    result = await reuse(db, "version", version_id, "placeholder-key")
    copied = await new_sources(db, result["session_id"])
    assert sum(row["solution_md"] is None for row in copied) == placeholders
    assert all(row["solution_md"] != PLACEHOLDER for row in copied)

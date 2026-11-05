"""Review F01-F03 regression on real PostgreSQL with migrations 006 through 009.

Requires the existing explicit disposable writer opt-in; no shared database.
"""

import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pytest

from tests.migrations.test_shuffle_writer_adversarial import (
    OWNER,
    payload,
    persist,
    state,
    wait_blocked,
)
from tests.migrations.test_shuffle_writer_adversarial import db as writer_database

# Re-export the shared disposable fixture under its dependency name.
db = writer_database

asyncpg = pytest.importorskip("asyncpg")
pytestmark = pytest.mark.asyncio


async def approve(conn, sid):
    return json.loads(
        await conn.fetchval("SELECT public.finalize_approve_session($1::uuid,NULL,NULL)", sid)
    )


@pytest.mark.parametrize(
    "operation",
    [
        "unlock",
        "title",
        "delete_session",
        "version",
        "question",
        "key",
        "audit",
        "source",
        "blueprint",
        "config",
        "insert_source",
        "profile_cascade",
        "truncate",
    ],
)
async def test_f01_owner_dml_after_approval_never_changes_state(db, operation):
    admin, owner, _, sid, data = db
    await persist(owner, sid, data)
    await approve(owner, sid)
    vid = data["versions"][0]["version_id"]
    qid = data["versions"][0]["questions"][0]["id"]
    source = data["snapshot"]["sources"][0]["id"]
    commands = {
        "unlock": (
            "UPDATE public.exam_sessions SET status='reviewed',approved_at=NULL WHERE id=$1::uuid",
            sid,
        ),
        "title": ("UPDATE public.exam_sessions SET title='tampered' WHERE id=$1::uuid", sid),
        "delete_session": ("DELETE FROM public.exam_sessions WHERE id=$1::uuid", sid),
        "version": ("UPDATE public.exam_versions SET is_finalized=false WHERE id=$1::uuid", vid),
        "question": ("UPDATE public.version_questions SET correct_key='A' WHERE id=$1::uuid", qid),
        "key": ("DELETE FROM public.answer_keys WHERE version_id=$1::uuid", vid),
        "audit": ("DELETE FROM public.review_logs WHERE session_id=$1::uuid", sid),
        "source": (
            "UPDATE public.source_questions SET raw_content='tampered' WHERE id=$1::uuid",
            source,
        ),
        "blueprint": (
            "UPDATE public.question_blueprints SET confirmed_at=NULL WHERE source_question_id=$1::uuid",
            source,
        ),
        "config": (
            "UPDATE public.generation_configs SET n_versions=1 WHERE session_id=$1::uuid",
            sid,
        ),
        "insert_source": (
            "INSERT INTO public.source_questions(session_id,question_no,raw_content,options,correct_key) VALUES($1::uuid,99,'tampered','[]','A')",
            sid,
        ),
        "profile_cascade": ("DELETE FROM public.users WHERE id=$1::uuid", OWNER),
        "truncate": ("TRUNCATE public.answer_keys", None),
    }
    sql, arg = commands[operation]
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError):
        await owner.execute(sql, *([] if arg is None else [arg]))
    assert await state(admin) == before


@pytest.mark.parametrize("field", ["status", "approved_at", "gemini_review_calls", "user_id"])
async def test_f01_lifecycle_fields_cannot_be_forged_before_approval(db, field):
    admin, owner, _, sid, _ = db
    assignments = {
        "status": "status='approved'",
        "approved_at": "approved_at=now()",
        "gemini_review_calls": "gemini_review_calls=0+1",
        "user_id": f"user_id='{uuid4()}'::uuid",
    }
    before = await state(admin)
    await owner.execute("SELECT set_config('request.jwt.claim.role','service_role',false)")
    with pytest.raises(asyncpg.PostgresError, match="ERR_DIRECT_LIFECYCLE_MUTATION"):
        await owner.execute(
            f"UPDATE public.exam_sessions SET {assignments[field]} WHERE id=$1::uuid", sid
        )
    assert await state(admin) == before


async def test_f01_legitimate_create_metadata_and_draft_delete_still_work(db):
    _, owner, _, _, _ = db
    sid = str(uuid4())
    await owner.execute(
        "INSERT INTO public.exam_sessions(id,user_id,title) VALUES($1::uuid,$2::uuid,'draft')",
        sid,
        OWNER,
    )
    await owner.execute("UPDATE public.exam_sessions SET title='edited' WHERE id=$1::uuid", sid)
    assert (
        await owner.fetchval("SELECT title FROM public.exam_sessions WHERE id=$1::uuid", sid)
        == "edited"
    )
    await owner.execute("DELETE FROM public.exam_sessions WHERE id=$1::uuid", sid)


async def test_f01_cannot_insert_fake_approved_session(db):
    admin, owner, _, _, _ = db
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError, match="ERR_DIRECT_LIFECYCLE_MUTATION"):
        await owner.execute(
            "INSERT INTO public.exam_sessions(id,user_id,title,status,approved_at) VALUES($1::uuid,$2::uuid,'fake','approved',now())",
            str(uuid4()),
            OWNER,
        )
    assert await state(admin) == before


@pytest.mark.parametrize("corruption", ["key", "canonical", "display_slot", "duplicate_display"])
async def test_f02_approval_rejects_wrong_actual_display_mapping_without_audit(db, corruption):
    admin, owner, _, sid, data = db
    await persist(owner, sid, data)
    v = data["versions"][0]
    q = v["questions"][0]
    if corruption == "key":
        wrong = next(c for c in "ABCD" if c != q["display_correct_key"])
        await admin.execute(
            "UPDATE public.answer_keys SET correct_option=$3,display_correct_key=$3 WHERE version_id=$1::uuid AND display_no=$2",
            v["version_id"],
            q["display_no"],
            wrong,
        )
    elif corruption == "canonical":
        # Swap the canonical IDs; set coverage remains structurally valid.
        await admin.execute(
            "UPDATE public.answer_keys SET canonical_question_no=CASE canonical_question_no WHEN 1 THEN 2 WHEN 2 THEN 1 ELSE canonical_question_no END WHERE version_id=$1::uuid",
            v["version_id"],
        )
    elif corruption == "display_slot":
        await admin.execute(
            "UPDATE public.version_questions SET question_no=99 WHERE id=$1::uuid", q["id"]
        )
    else:
        await admin.execute(
            "UPDATE public.version_questions SET question_no=$2 WHERE version_id=$1::uuid AND is_current",
            v["version_id"],
            q["display_no"],
        )
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError, match="ERR_INCONSISTENT_ANSWER_KEYS"):
        await approve(owner, sid)
    assert await state(admin) == before


async def test_f02_valid_approval_replay_keeps_audit_and_timestamp(db):
    admin, owner, _, sid, data = db
    await persist(owner, sid, data)
    first = await approve(owner, sid)
    before = await state(admin)
    again = await approve(owner, sid)
    assert first["approved_at"] == again["approved_at"]
    assert await state(admin) == before


@pytest.mark.parametrize("claimed_role", ["authenticated", "service_role"])
async def test_f03_owner_cannot_submit_alternate_permutation_even_with_forged_claim(
    db, claimed_role
):
    admin, owner, _, sid, expected = db
    alternate = deepcopy(expected["snapshot"])
    alternate["config"]["ordering_preferences"] = {
        "shuffle_questions": False,
        "shuffle_options": False,
    }
    forged = payload(sid, alternate)
    forged["snapshot"] = expected["snapshot"]
    forged["actor_id"] = OWNER
    assert forged["versions"] != expected["versions"]
    await owner.execute("SELECT set_config('request.jwt.claim.role',$1,false)", claimed_role)
    before = await state(admin)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await owner.fetchval(
            "SELECT public.finalize_persist_shuffle($1::uuid,$2::jsonb)", sid, json.dumps(forged)
        )
    assert await state(admin) == before


@pytest.mark.parametrize("actor", [None, "other", "malformed"])
async def test_f03_trusted_writer_still_validates_actor_ownership(db, actor):
    admin, _, peer, sid, data = db
    data["actor_id"] = None if actor is None else (str(uuid4()) if actor == "other" else "bad")
    await peer.execute("SET ROLE service_role")
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError, match="ERR_(UNAUTHORIZED|SHUFFLE_INPUT_INCOMPLETE)"):
        await peer.fetchval(
            "SELECT public.finalize_persist_shuffle($1::uuid,$2::jsonb)", sid, json.dumps(data)
        )
    assert await state(admin) == before


@pytest.mark.parametrize("mutation", ["update", "delete", "insert"])
async def test_f03_finalized_policy_cannot_be_changed_behind_receipt(db, mutation):
    admin, owner, _, sid, data = db
    await persist(owner, sid, data)
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError, match="ERR_SHUFFLE_CONFIGURATION_LOCKED"):
        sql = {
            "update": "UPDATE public.generation_configs SET ordering_preferences='{}' WHERE session_id=$1::uuid",
            "delete": "DELETE FROM public.generation_configs WHERE session_id=$1::uuid",
            "insert": "INSERT INTO public.generation_configs(session_id,n_versions) VALUES($1::uuid,2)",
        }[mutation]
        await owner.execute(sql, sid)
    assert await state(admin) == before


async def test_f01_approval_serializes_with_direct_config_write(db):
    admin, owner, peer, sid, data = db
    await persist(owner, sid, data)
    tx = owner.transaction()
    await tx.start()
    task = None
    try:
        await approve(owner, sid)
        task = asyncio.create_task(
            peer.execute(
                "UPDATE public.generation_configs SET n_versions=1 WHERE session_id=$1::uuid", sid
            )
        )
        await wait_blocked(admin, peer, owner)
        await tx.commit()
        before = await state(admin)
        with pytest.raises(asyncpg.PostgresError, match="ERR_SESSION_LOCKED"):
            await asyncio.wait_for(task, 5)
        assert await state(admin) == before
    finally:
        if owner.is_in_transaction():
            await tx.rollback()
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_f01_column_grants_and_rpc_acl_are_revoked(db):
    admin = db[0]
    for table in ("exam_versions", "version_questions", "answer_keys", "review_logs"):
        assert not await admin.fetchval(
            "SELECT has_table_privilege('authenticated',$1,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')",
            "public." + table,
        )
    assert not await admin.fetchval(
        "SELECT has_column_privilege('authenticated','public.version_questions','correct_key','UPDATE')"
    )
    assert not await admin.fetchval(
        "SELECT has_function_privilege('authenticated','public.finalize_persist_shuffle(uuid,jsonb)','EXECUTE')"
    )
    assert await admin.fetchval(
        "SELECT has_function_privilege('service_role','public.finalize_persist_shuffle(uuid,jsonb)','EXECUTE')"
    )


async def test_f01_owner_read_policies_remain_isolated(db):
    _, owner, _, sid, data = db
    await persist(owner, sid, data)
    assert (
        await owner.fetchval(
            "SELECT count(*) FROM public.exam_versions WHERE session_id=$1::uuid", sid
        )
        == 2
    )
    await owner.execute("SELECT set_config('request.jwt.claim.sub',$1,false)", str(uuid4()))
    assert (
        await owner.fetchval(
            "SELECT count(*) FROM public.exam_versions WHERE session_id=$1::uuid", sid
        )
        == 0
    )
    assert (
        await owner.fetchval(
            "SELECT count(*) FROM public.answer_keys WHERE version_id=$1::uuid",
            data["versions"][0]["version_id"],
        )
        == 0
    )


@pytest.mark.parametrize(
    "table", ["exam_sessions", "exam_versions", "version_questions", "answer_keys"]
)
async def test_f01_late_service_dml_also_respects_content_lock(db, table):
    admin, owner, peer, sid, data = db
    # Model Supabase's broad service table grants; RPC EXECUTE remains separate.
    await admin.execute(
        "GRANT SELECT,INSERT,UPDATE,DELETE ON public.exam_sessions,public.exam_versions,public.version_questions,public.answer_keys TO service_role"
    )
    await persist(owner, sid, data)
    await approve(owner, sid)
    await peer.execute("SET ROLE service_role")
    vid = data["versions"][0]["version_id"]
    qid = data["versions"][0]["questions"][0]["id"]
    sql, arg = {
        "exam_sessions": (
            "UPDATE public.exam_sessions SET status='reviewed',approved_at=NULL WHERE id=$1::uuid",
            sid,
        ),
        "exam_versions": (
            "UPDATE public.exam_versions SET is_finalized=false WHERE id=$1::uuid",
            vid,
        ),
        "version_questions": (
            "UPDATE public.version_questions SET content='late worker' WHERE id=$1::uuid",
            qid,
        ),
        "answer_keys": ("DELETE FROM public.answer_keys WHERE version_id=$1::uuid", vid),
    }[table]
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError, match="ERR_SESSION_LOCKED"):
        await peer.execute(sql, arg)
    assert await state(admin) == before


async def test_f03_http_ignores_caller_supplied_actor_and_permutation(db):
    import os

    from fastapi.testclient import TestClient

    from app.api.dependencies import get_current_user, get_service_db, get_user_db
    from app.main import app
    from app.models.schemas import CurrentUser
    from tests.services.test_finalize_real_db_integration import AsyncpgSupabaseAdapter

    admin, _, _, sid, data = db
    dsn = os.environ["TASK305_WRITER_TEST_DSN"]
    alternate = deepcopy(data["snapshot"])
    alternate["config"]["ordering_preferences"] = {
        "shuffle_questions": False,
        "shuffle_options": False,
    }
    forged = payload(sid, alternate)
    forged["actor_id"] = str(uuid4())
    assert forged["versions"] != data["versions"]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=OWNER, email="test@example.invalid", name="Teacher", access_token="test"
    )
    app.dependency_overrides[get_user_db] = lambda: AsyncpgSupabaseAdapter(dsn, actor=OWNER)
    app.dependency_overrides[get_service_db] = lambda: AsyncpgSupabaseAdapter(
        dsn, role="service_role", actor=OWNER
    )
    try:
        response = TestClient(app).post(f"/api/sessions/{sid}/finalize/shuffle", json=forged)
        assert response.status_code == 200, response.text
        for version in data["versions"]:
            actual = await admin.fetchval(
                "SELECT permutations FROM public.exam_versions WHERE id=$1::uuid",
                version["version_id"],
            )
            assert json.loads(actual) == version["permutations"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("foundation", ["fresh", "legacy"])
async def test_forward_upgrade_009_is_atomic_replayable_and_preserves_data(db, foundation):
    import os
    from pathlib import Path

    admin = db[0]
    database = "task305_test_upgrade_" + uuid4().hex
    await admin.execute(f'CREATE DATABASE "{database}"')
    conn = None
    try:
        dsn = os.environ["TASK305_WRITER_TEST_DSN"].rsplit("/", 1)[0] + "/" + database
        conn = await asyncpg.connect(dsn)
        assert await conn.fetchval("SELECT current_database()") == database
        root = Path(__file__).resolve().parents[2]
        for file in (
            root / "tests/migrations/task305_shuffle_bootstrap.sql",
            root
            / (
                "scripts/schema.sql"
                if foundation == "fresh"
                else "tests/migrations/fixtures/legacy_schema.sql"
            ),
            root / "migrations/006_stage3_review_and_shuffle.sql",
            root / "migrations/007_finalize_approve_session_rpc.sql",
            root / "migrations/008_finalize_persist_shuffle_rpc.sql",
        ):
            await conn.execute(file.read_text(encoding="utf-8-sig"))
        smoke = (root / "tests/migrations/task305_shuffle_smoke.sql").read_text(
            encoding="utf-8-sig"
        )
        await conn.execute(
            "INSERT INTO auth.users(id,email) VALUES('00000000-0000-0000-0000-000000000001','fixture@example.invalid') ON CONFLICT DO NOTHING; INSERT INTO public.users(id,email) VALUES('00000000-0000-0000-0000-000000000001','fixture@example.invalid') ON CONFLICT DO NOTHING"
        )
        await conn.execute(
            "\n".join(
                line
                for line in smoke.splitlines()
                if not line.startswith(("\\", "INSERT INTO auth.users"))
            )
        )
        await conn.execute(
            "GRANT SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES ON public.exam_sessions,public.exam_versions,public.version_questions,public.answer_keys,public.review_logs,public.source_questions,public.question_blueprints,public.generation_configs,public.users TO authenticated; GRANT UPDATE(correct_key) ON public.version_questions TO authenticated"
        )
        before = await state(conn)
        definition = await conn.fetchval(
            "SELECT pg_get_functiondef('public.finalize_persist_shuffle(uuid,jsonb)'::regprocedure)"
        )
        sql = (root / "migrations/009_finalize_security_boundary.sql").read_text(
            encoding="utf-8-sig"
        )
        assert sql.count("\nCOMMIT;") == 1
        fault = sql.replace(
            "\nCOMMIT;", "\nDO $$ BEGIN RAISE EXCEPTION 'UPGRADE_FAULT'; END $$;\nCOMMIT;"
        )
        with pytest.raises(asyncpg.PostgresError, match="UPGRADE_FAULT"):
            await conn.execute(fault)
        await conn.execute("ROLLBACK")
        assert await state(conn) == before
        assert (
            await conn.fetchval(
                "SELECT pg_get_functiondef('public.finalize_persist_shuffle(uuid,jsonb)'::regprocedure)"
            )
            == definition
        )
        assert await conn.fetchval(
            "SELECT has_function_privilege('authenticated','public.finalize_persist_shuffle(uuid,jsonb)','EXECUTE')"
        )
        assert await conn.fetchval(
            "SELECT has_column_privilege('authenticated','public.version_questions','correct_key','UPDATE')"
        )
        for _ in range(2):
            await conn.execute(sql)
            assert await state(conn) == before
            assert not await conn.fetchval(
                "SELECT has_function_privilege('authenticated','public.finalize_persist_shuffle(uuid,jsonb)','EXECUTE')"
            )
            assert not await conn.fetchval(
                "SELECT has_column_privilege('authenticated','public.version_questions','correct_key','UPDATE')"
            )
            assert await conn.fetchval(
                "SELECT has_function_privilege('service_role','public.finalize_persist_shuffle(uuid,jsonb)','EXECUTE')"
            )
        data = json.loads(await conn.fetchval("SELECT public.test_shuffle_payload()"))
        data["actor_id"] = OWNER
        await conn.execute("SET ROLE service_role")
        receipt = await conn.fetchval(
            "SELECT public.finalize_persist_shuffle($1::uuid,$2::jsonb)",
            "10000000-0000-0000-0000-000000000001",
            json.dumps(data),
        )
        assert json.loads(receipt)["is_finalized"] is True
        await conn.execute("RESET ROLE")
        assert await state(conn) == before
    finally:
        if conn:
            await conn.close()
        await admin.execute(f'DROP DATABASE "{database}"')

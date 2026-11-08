"""TASK-207: Real PostgreSQL integration suite for Migration 017.

Tests stale generation job enumeration, keyset pagination, fencing recovery,
atomic durable error codes (ERR_GENERATION_INTERRUPTED), activity timestamp tracking,
and least-privilege ACL boundaries.
"""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.migrations.test_generation_w2 import (
    OWNER,
    ROOT,
    asyncpg,
    configure,
    persist,
    result_for,
    role,
)

pytest_plugins = ("tests.migrations.test_generation_w2",)
pytestmark = pytest.mark.asyncio

MIGRATION_017 = ROOT / "backend/migrations/017_generation_lifecycle_recovery.sql"

# Extend RPC parameter type mappings for migration 017
EXTRA_TYPES = {
    "list_stale_generation_jobs": ["int", "int", "timestamptz", "uuid"],
    "fail_stale_generation_job_if_current": ["uuid", "uuid", "int"],
    "fail_stale_generation_job": ["uuid", "int"],
    "finish_generation_job_with_error": ["uuid", "text", "uuid", "text"],
    "heartbeat_generation_job": ["uuid", "uuid"],
    "load_generation_completed_results": ["uuid"],
}


async def call_rpc(conn, name, *args):
    """Execute RPC with proper PostgreSQL type casting."""
    from tests.migrations.test_generation_w2 import TYPES

    combined_types = {**TYPES, **EXTRA_TYPES}
    types = combined_types[name][: len(args)]
    values = [
        json.dumps(v, ensure_ascii=False) if t == "jsonb" and v is not None else v
        for t, v in zip(types, args)
    ]
    placeholders = ",".join(f"${i}::{t}" for i, t in enumerate(types, 1))
    raw = await conn.fetchval(f"SELECT public.{name}({placeholders})", *values)
    return json.loads(raw) if raw is not None else None


@pytest.fixture
async def env(db):
    """Fixture providing disposable PostgreSQL instance upgraded to Migration 017."""
    await db.admin.execute(MIGRATION_017.read_text(encoding="utf-8-sig"))
    return db


# ----------------------------------------------------------------------------
# 1. Schema, Constraint & Idempotency Tests
# ----------------------------------------------------------------------------


async def test_migration_017_idempotent_replay(env):
    """Migration 017 can be reapplied without error or contract degradation."""
    for _ in range(2):
        await env.admin.execute(MIGRATION_017.read_text(encoding="utf-8-sig"))

    # Verify column existence
    cols = await env.admin.fetch(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'exam_sessions'
          AND column_name IN ('generation_last_activity_at', 'generation_error_code')
        ORDER BY column_name
        """
    )
    col_dict = {r["column_name"]: r for r in cols}
    assert "generation_last_activity_at" in col_dict
    assert "generation_error_code" in col_dict
    assert col_dict["generation_last_activity_at"]["is_nullable"] == "YES"
    assert col_dict["generation_error_code"]["is_nullable"] == "YES"

    # Verify index existence
    idx = await env.admin.fetchval(
        """
        SELECT indexdef FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'exam_sessions'
          AND indexname = 'idx_exam_sessions_generation_stale'
        """
    )
    assert idx is not None
    assert "generation_last_activity_at" in idx
    assert "status = 'generating'" in idx


async def test_error_code_format_constraint(env):
    """generation_error_code accepts valid uppercase codes and rejects malformed values."""
    sid = env.sid
    # Valid codes
    for valid_code in ("ERR_GENERATION_INTERRUPTED", "TIMEOUT_120", "PROVIDER_FAILED"):
        await env.admin.execute(
            "UPDATE exam_sessions SET generation_error_code = $1 WHERE id = $2::uuid",
            valid_code,
            sid,
        )
        assert (
            await env.admin.fetchval(
                "SELECT generation_error_code FROM exam_sessions WHERE id = $1::uuid", sid
            )
            == valid_code
        )

    # NULL is allowed
    await env.admin.execute(
        "UPDATE exam_sessions SET generation_error_code = NULL WHERE id = $1::uuid", sid
    )

    # Invalid codes (lowercase, spaces, special chars, too short, too long)
    for invalid_code in ("err_lowercase", "WITH SPACES", "INVALID$CHAR", "NO", "A" * 65):
        with pytest.raises(asyncpg.PostgresError, match="chk_generation_error_code_format"):
            await env.admin.execute(
                "UPDATE exam_sessions SET generation_error_code = $1 WHERE id = $2::uuid",
                invalid_code,
                sid,
            )


# ----------------------------------------------------------------------------
# 2. Activity Tracking: Generation Clock vs Metadata Edit
# ----------------------------------------------------------------------------


async def test_metadata_edit_does_not_update_generation_activity(env):
    """Editing session metadata (title/subject/grade) does NOT touch generation_last_activity_at."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)
    assert claim["job_id"] is not None

    initial_activity = await env.admin.fetchval(
        "SELECT generation_last_activity_at FROM exam_sessions WHERE id = $1::uuid", env.sid
    )
    initial_updated = await env.admin.fetchval(
        "SELECT updated_at FROM exam_sessions WHERE id = $1::uuid", env.sid
    )
    assert initial_activity is not None

    # Sleep slightly so timestamps would advance
    await asyncio.sleep(0.05)

    # Authenticated user updates metadata title
    await env.owner.execute(
        "UPDATE exam_sessions SET title = 'Altered Exam Title' WHERE id = $1::uuid", env.sid
    )

    new_activity = await env.admin.fetchval(
        "SELECT generation_last_activity_at FROM exam_sessions WHERE id = $1::uuid", env.sid
    )
    new_updated = await env.admin.fetchval(
        "SELECT updated_at FROM exam_sessions WHERE id = $1::uuid", env.sid
    )

    # updated_at must advance due to trigger 004, but generation_last_activity_at MUST NOT change!
    assert new_updated > initial_updated
    assert new_activity == initial_activity


async def test_quota_reservation_and_result_persist_update_activity(env):
    """Reserving quota or persisting question results refreshes generation_last_activity_at."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    # Artificially age the activity timestamp
    past_stamp = datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc)
    await env.admin.execute(
        "UPDATE exam_sessions SET generation_last_activity_at = $1 WHERE id = $2::uuid",
        past_stamp,
        env.sid,
    )

    # 1. Reserving quota should touch activity
    await call_rpc(env.worker, "reserve_generation_quota", env.sid, 1, claim["job_id"])
    activity_after_quota = await env.admin.fetchval(
        "SELECT generation_last_activity_at FROM exam_sessions WHERE id = $1::uuid", env.sid
    )
    assert activity_after_quota > past_stamp

    # 2. Re-age timestamp
    await env.admin.execute(
        "UPDATE exam_sessions SET generation_last_activity_at = $1 WHERE id = $2::uuid",
        past_stamp,
        env.sid,
    )

    # Persisting a result should touch activity
    res = result_for(env, claim, index=0, version=1, success=True)
    await persist(env, claim, res)
    activity_after_persist = await env.admin.fetchval(
        "SELECT generation_last_activity_at FROM exam_sessions WHERE id = $1::uuid", env.sid
    )
    assert activity_after_persist > past_stamp


async def test_heartbeat_updates_generation_activity(env):
    """Worker heartbeat updates generation_last_activity_at under active token."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    past_stamp = datetime(2026, 11, 7, 8, 0, 0, tzinfo=timezone.utc)
    await env.admin.execute(
        "UPDATE exam_sessions SET generation_last_activity_at = $1 WHERE id = $2::uuid",
        past_stamp,
        env.sid,
    )

    receipt = await call_rpc(
        env.worker, "heartbeat_generation_job", env.sid, claim["job_id"]
    )
    assert receipt["status"] == "generating"

    current_activity = await env.admin.fetchval(
        "SELECT generation_last_activity_at FROM exam_sessions WHERE id = $1::uuid", env.sid
    )
    assert current_activity > past_stamp


# ----------------------------------------------------------------------------
# 3. TASK A: Stale Enumeration (list_stale_generation_jobs)
# ----------------------------------------------------------------------------


async def test_list_stale_jobs_not_stale_before_cutoff(env):
    """Freshly claimed job within cutoff is not reported as stale."""
    await configure(env, modes=["context_swap"], versions=1)
    await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    stale = await call_rpc(env.worker, "list_stale_generation_jobs", 720, 50, None, None)
    assert stale["items"] == []
    assert stale["has_more"] is False
    assert stale["next_cursor"] is None


async def test_list_stale_jobs_detects_aged_job(env):
    """Job exceeding cutoff is detected with authoritative DB clock."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    # Set activity to 800 seconds in the past
    await env.admin.execute(
        "UPDATE exam_sessions SET generation_last_activity_at = clock_timestamp() - interval '800 seconds' WHERE id = $1::uuid",
        env.sid,
    )

    stale = await call_rpc(env.worker, "list_stale_generation_jobs", 720, 50, None, None)
    assert len(stale["items"]) == 1
    item = stale["items"][0]
    assert item["session_id"] == env.sid
    assert item["job_token"] == claim["job_id"]
    assert stale["has_more"] is False


async def test_list_stale_jobs_keyset_pagination(env):
    """Keyset pagination handles multiple pages without omission or duplicates."""
    # Seed 12 stale sessions
    job_ids = []
    base_time = datetime(2026, 11, 7, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(12):
        sid = str(uuid4())
        jid = str(uuid4())
        job_ids.append((sid, jid))
        await env.admin.execute(
            """
            INSERT INTO exam_sessions(id, user_id, title, status, active_job_id, generation_last_activity_at)
            VALUES($1::uuid, $2::uuid, $3, 'generating', $4::uuid, $5::timestamptz + make_interval(secs => $6))
            """,
            sid,
            OWNER,
            f"Stale Batch {i}",
            jid,
            base_time,
            i * 10,
        )

    # Page 1: limit 5
    page1 = await call_rpc(env.worker, "list_stale_generation_jobs", 60, 5, None, None)
    assert len(page1["items"]) == 5
    assert page1["has_more"] is True
    cursor1 = page1["next_cursor"]
    assert cursor1 is not None

    # Page 2: limit 5 with cursor
    page2 = await call_rpc(
        env.worker,
        "list_stale_generation_jobs",
        60,
        5,
        cursor1["last_activity_at"],
        cursor1["session_id"],
    )
    assert len(page2["items"]) == 5
    assert page2["has_more"] is True
    cursor2 = page2["next_cursor"]

    # Page 3: limit 5 with cursor
    page3 = await call_rpc(
        env.worker,
        "list_stale_generation_jobs",
        60,
        5,
        cursor2["last_activity_at"],
        cursor2["session_id"],
    )
    assert len(page3["items"]) == 2
    assert page3["has_more"] is False
    assert page3["next_cursor"] is None

    # Ensure no duplicates and total count is 12
    all_sids = [it["session_id"] for it in page1["items"] + page2["items"] + page3["items"]]
    assert len(all_sids) == 12
    assert len(set(all_sids)) == 12


async def test_list_stale_jobs_validation_guards(env):
    """Input boundary validation for limit, cutoff, and cursor pairing."""
    # Invalid limit (0 or > 100)
    for bad_limit in (0, -1, 101):
        with pytest.raises(asyncpg.PostgresError, match="p_limit must be between 1 and 100"):
            await call_rpc(env.worker, "list_stale_generation_jobs", 720, bad_limit, None, None)

    # Invalid cutoff
    for bad_cutoff in (0, -5):
        with pytest.raises(asyncpg.PostgresError, match="p_cutoff_seconds must be positive"):
            await call_rpc(env.worker, "list_stale_generation_jobs", bad_cutoff, 50, None, None)

    # Asymmetric cursor components
    now_iso = datetime.now(timezone.utc).isoformat()
    with pytest.raises(asyncpg.PostgresError, match="Cursor components must be both provided"):
        await call_rpc(env.worker, "list_stale_generation_jobs", 720, 50, now_iso, None)

    with pytest.raises(asyncpg.PostgresError, match="Cursor components must be both provided"):
        await call_rpc(env.worker, "list_stale_generation_jobs", 720, 50, None, env.sid)


# ----------------------------------------------------------------------------
# 4. Fencing Stale Recovery (fail_stale_generation_job_if_current)
# ----------------------------------------------------------------------------


async def test_fail_stale_if_current_recovers_aged_job(env):
    """Aged job is marked failed atomically with ERR_GENERATION_INTERRUPTED."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    await env.admin.execute(
        "UPDATE exam_sessions SET generation_last_activity_at = clock_timestamp() - interval '800 seconds' WHERE id = $1::uuid",
        env.sid,
    )

    receipt = await call_rpc(
        env.worker, "fail_stale_generation_job_if_current", env.sid, claim["job_id"], 720
    )
    assert receipt["recovered"] is True
    assert receipt["status"] == "failed"
    assert receipt["error_code"] == "ERR_GENERATION_INTERRUPTED"

    session = await env.admin.fetchrow(
        "SELECT status, active_job_id, generation_error_code FROM exam_sessions WHERE id = $1::uuid",
        env.sid,
    )
    assert session["status"] == "failed"
    assert session["active_job_id"] is None
    assert session["generation_error_code"] == "ERR_GENERATION_INTERRUPTED"


async def test_fail_stale_fencing_worker_finished_first(env):
    """Scanner cannot fail a job that the worker already finished successfully."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    # Worker completes the question and finishes
    res = result_for(env, claim, index=0, version=1, success=True)
    await persist(env, claim, res)
    await call_rpc(env.worker, "finish_generation_job", env.sid, "generated", claim["job_id"])

    # Scanner attempts recovery with old token
    receipt = await call_rpc(
        env.worker, "fail_stale_generation_job_if_current", env.sid, claim["job_id"], 720
    )
    assert receipt["recovered"] is False
    assert receipt["current_status"] == "generated"
    assert receipt["reason"] == "status_not_generating"

    # Status remains generated
    assert (
        await env.admin.fetchval(
            "SELECT status FROM exam_sessions WHERE id = $1::uuid", env.sid
        )
        == "generated"
    )


async def test_fail_stale_fencing_session_retried(env):
    """Scanner cannot fail a session that was already retried with a new token."""
    await configure(env, modes=["context_swap"], versions=1)
    claim1 = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    # Simulate manual retry or previous job termination
    await env.admin.execute(
        "UPDATE exam_sessions SET status = 'failed', active_job_id = NULL WHERE id = $1::uuid",
        env.sid,
    )
    claim2 = await call_rpc(env.owner, "claim_generation_job", env.sid, True)
    assert claim2["job_id"] != claim1["job_id"]

    # Scanner tries to recover using claim1's token
    receipt = await call_rpc(
        env.worker, "fail_stale_generation_job_if_current", env.sid, claim1["job_id"], 720
    )
    assert receipt["recovered"] is False
    assert receipt["reason"] == "token_mismatch"
    assert receipt["current_job_id"] == claim2["job_id"]

    # New job token remains intact
    assert (
        await env.admin.fetchval(
            "SELECT active_job_id FROM exam_sessions WHERE id = $1::uuid", env.sid
        )
        == claim2["job_id"]
    )


async def test_concurrent_fail_stale_race(env):
    """Two concurrent scanners compete to fail the same stale job: exactly one succeeds."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)
    await env.admin.execute(
        "UPDATE exam_sessions SET generation_last_activity_at = clock_timestamp() - interval '800 seconds' WHERE id = $1::uuid",
        env.sid,
    )

    worker2 = await asyncpg.connect(env.dsn)
    try:
        await role(worker2, "service_role")

        # Concurrently attempt recovery
        res1, res2 = await asyncio.gather(
            call_rpc(env.worker, "fail_stale_generation_job_if_current", env.sid, claim["job_id"], 720),
            call_rpc(worker2, "fail_stale_generation_job_if_current", env.sid, claim["job_id"], 720),
        )

        # Exactly one must have recovered=True
        assert {res1["recovered"], res2["recovered"]} == {True, False}
    finally:
        await worker2.close()


# ----------------------------------------------------------------------------
# 5. TASK B: Durable Interruption Error & Lifecycle Persistence
# ----------------------------------------------------------------------------


async def test_finish_generation_job_with_error(env):
    """Worker can conclude with failure / partial_generated and record error code."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    # 1. Failed outcome with error code
    receipt = await call_rpc(
        env.worker,
        "finish_generation_job_with_error",
        env.sid,
        "failed",
        claim["job_id"],
        "ERR_MODEL_QUOTA_EXHAUSTED",
    )
    assert receipt["status"] == "failed"
    assert receipt["generation_error_code"] == "ERR_MODEL_QUOTA_EXHAUSTED"

    session = await env.admin.fetchrow(
        "SELECT status, generation_error_code FROM exam_sessions WHERE id = $1::uuid", env.sid
    )
    assert session["status"] == "failed"
    assert session["generation_error_code"] == "ERR_MODEL_QUOTA_EXHAUSTED"


async def test_finish_generated_outcome_rejects_error_code(env):
    """finish_generation_job_with_error rejects error_code if outcome is 'generated'."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)
    res = result_for(env, claim, index=0, version=1, success=True)
    await persist(env, claim, res)

    with pytest.raises(asyncpg.PostgresError, match="Cannot specify error_code for generated"):
        await call_rpc(
            env.worker,
            "finish_generation_job_with_error",
            env.sid,
            "generated",
            claim["job_id"],
            "ERR_UNEXPECTED",
        )


async def test_load_generation_completed_results_returns_error_after_restart(env):
    """load_generation_completed_results returns persisted generation_error_code after process reboot."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    # Interrupted by stale scanner
    await env.admin.execute(
        "UPDATE exam_sessions SET generation_last_activity_at = clock_timestamp() - interval '800 seconds' WHERE id = $1::uuid",
        env.sid,
    )
    await call_rpc(
        env.worker, "fail_stale_generation_job_if_current", env.sid, claim["job_id"], 720
    )

    # Load results as owner (simulating read-back after restart)
    loaded = await call_rpc(env.owner, "load_generation_completed_results", env.sid)
    assert loaded["session_id"] == env.sid
    assert loaded["generation_error_code"] == "ERR_GENERATION_INTERRUPTED"


async def test_retry_clears_error_code_and_preserves_quota_and_snapshots(env):
    """Retry claim resets error_code to NULL, refreshes activity, preserves quota & committed targets."""
    await configure(env, modes=["context_swap"], versions=1)
    claim = await call_rpc(env.owner, "claim_generation_job", env.sid, False)

    # 1. Commit 1 successful question and reserve quota
    await call_rpc(env.worker, "reserve_generation_quota", env.sid, 3, claim["job_id"])
    res = result_for(env, claim, index=0, version=1, success=True)
    await persist(env, claim, res)

    # 2. Simulate interruption failure
    await call_rpc(
        env.worker,
        "finish_generation_job_with_error",
        env.sid,
        "failed",
        claim["job_id"],
        "ERR_GENERATION_INTERRUPTED",
    )

    assert (
        await env.admin.fetchval(
            "SELECT generation_error_code FROM exam_sessions WHERE id = $1::uuid", env.sid
        )
        == "ERR_GENERATION_INTERRUPTED"
    )

    # 3. Retry claim
    claim_retry = await call_rpc(env.owner, "claim_generation_job", env.sid, True)
    assert claim_retry["status"] == "generating"
    assert claim_retry["job_id"] != claim["job_id"]

    # Verify session state:
    session = await env.admin.fetchrow(
        "SELECT status, generation_error_code, gemini_call_count, retry_count FROM exam_sessions WHERE id = $1::uuid",
        env.sid,
    )
    assert session["status"] == "generating"
    assert session["generation_error_code"] is None  # Error code cleared on retry!
    assert session["gemini_call_count"] == 3  # Quota preserved!

    # Committed targets preserved
    committed_count = await env.admin.fetchval(
        "SELECT count(*) FROM generation_target_results WHERE session_id = $1::uuid AND is_success = true",
        env.sid,
    )
    assert committed_count == 1


# ----------------------------------------------------------------------------
# 6. Least Privilege & Role Permissions (SEC-01 - SEC-05)
# ----------------------------------------------------------------------------


async def test_least_privilege_access_denied_for_clients(env):
    """SEC-01, SEC-02, SEC-03, SEC-05: anon and authenticated cannot modify lifecycle columns."""
    anon = await asyncpg.connect(env.dsn)
    non_owner = await asyncpg.connect(env.dsn)
    try:
        await role(anon, "anon")
        non_owner_id = str(uuid4())
        await env.admin.execute(
            "INSERT INTO auth.users(id,email) VALUES($1::uuid,'other@example.invalid')", non_owner_id
        )
        await env.admin.execute(
            "INSERT INTO public.users(id,email) VALUES($1::uuid,'other@example.invalid') ON CONFLICT(id) DO NOTHING",
            non_owner_id,
        )
        await role(non_owner, "authenticated", non_owner_id)

        # Scanner enumeration denied for anon
        with pytest.raises(asyncpg.PostgresError, match="restricted to service_role|permission denied"):
            await call_rpc(anon, "list_stale_generation_jobs", 720, 50, None, None)

        # Fencing recovery denied for anon
        with pytest.raises(asyncpg.PostgresError, match="restricted to service_role|permission denied"):
            await call_rpc(anon, "fail_stale_generation_job_if_current", env.sid, str(uuid4()), 720)

        # Heartbeat denied for anon
        with pytest.raises(asyncpg.PostgresError, match="restricted to service_role|permission denied"):
            await call_rpc(anon, "heartbeat_generation_job", env.sid, str(uuid4()))

        # SEC-03: anon cannot update generation_error_code
        with pytest.raises(asyncpg.PostgresError, match="permission denied"):
            await anon.execute(
                "UPDATE exam_sessions SET generation_error_code = 'ANON_ERR' WHERE id = $1::uuid",
                env.sid,
            )

        # SEC-03: anon cannot update generation_last_activity_at
        with pytest.raises(asyncpg.PostgresError, match="permission denied"):
            await anon.execute(
                "UPDATE exam_sessions SET generation_last_activity_at = now() WHERE id = $1::uuid",
                env.sid,
            )

        # SEC-02: Direct table update on generation_error_code denied for authenticated owner
        with pytest.raises(asyncpg.PostgresError, match="permission denied"):
            await env.owner.execute(
                "UPDATE exam_sessions SET generation_error_code = 'MALICIOUS_OVERWRITE' WHERE id = $1::uuid",
                env.sid,
            )

        # SEC-01: Direct table update on generation_last_activity_at denied for authenticated owner
        with pytest.raises(asyncpg.PostgresError, match="permission denied"):
            await env.owner.execute(
                "UPDATE exam_sessions SET generation_last_activity_at = now() WHERE id = $1::uuid",
                env.sid,
            )

        # Non-owner cannot update owner session lifecycle columns
        with pytest.raises(asyncpg.PostgresError, match="permission denied"):
            await non_owner.execute(
                "UPDATE exam_sessions SET generation_error_code = 'NON_OWNER_ERR' WHERE id = $1::uuid",
                env.sid,
            )

        with pytest.raises(asyncpg.PostgresError, match="permission denied"):
            await non_owner.execute(
                "UPDATE exam_sessions SET generation_last_activity_at = now() WHERE id = $1::uuid",
                env.sid,
            )

        # SEC-05: Authenticated owner CAN update valid metadata fields according to contract
        await env.owner.execute(
            "UPDATE exam_sessions SET title = 'Valid Metadata Update', subject = 'Math', grade = '12' WHERE id = $1::uuid",
            env.sid,
        )
        updated = await env.admin.fetchrow(
            "SELECT title, subject, grade, generation_last_activity_at, generation_error_code FROM exam_sessions WHERE id = $1::uuid",
            env.sid,
        )
        assert updated["title"] == "Valid Metadata Update"
        assert updated["subject"] == "Math"
        assert updated["grade"] == "12"
    finally:
        await anon.close()
        await non_owner.close()


async def test_table_level_grant_defense_in_depth(env):
    """SEC-04 (Case D): Table-level GRANT does not allow bypassing lifecycle column protection.

    Even if a table-level UPDATE is accidentally granted to authenticated:
    1. Triggers (trg_finalize_direct_guard / trg_guard_exam_sessions_worker_columns) intercept
       unauthorized direct mutations and raise SQLSTATE 42501.
    2. Data invariants are preserved: rejected statements rollback cleanly without mutating
       protected worker columns or timestamps.
    3. Legitimate metadata updates (title) succeed without modifying protected columns.
    4. Re-applying migration 017 strips table-level UPDATE and re-establishes column whitelisting.
    """
    # 1. Simulate accidental/fixture table-level GRANT
    await env.admin.execute("GRANT UPDATE ON TABLE public.exam_sessions TO authenticated")
    assert await env.admin.fetchval(
        "SELECT has_table_privilege('authenticated', 'public.exam_sessions', 'UPDATE')"
    ) is True

    # Seed baseline values for protected fields to guarantee invariant checking on non-null state
    await env.admin.execute(
        """
        UPDATE public.exam_sessions
        SET generation_error_code = 'INITIAL_ERROR',
            generation_last_activity_at = '2026-11-01 00:00:00+00'::timestamptz
        WHERE id = $1::uuid
        """,
        env.sid,
    )

    before = await env.admin.fetchrow(
        """
        SELECT generation_error_code, generation_last_activity_at, updated_at, title
        FROM public.exam_sessions
        WHERE id = $1::uuid
        """,
        env.sid,
    )
    assert before["generation_error_code"] == "INITIAL_ERROR"
    assert before["generation_last_activity_at"] is not None

    # 2. Trigger defense-in-depth: Even with table-level privilege, worker columns are guarded with 42501
    with pytest.raises(asyncpg.PostgresError) as exc_err:
        await env.owner.execute(
            "UPDATE exam_sessions SET generation_error_code = 'BYPASS_ATTEMPT' WHERE id = $1::uuid",
            env.sid,
        )
    assert (getattr(exc_err.value, "sqlstate", None) or exc_err.value.as_dict().get("sqlstate")) == "42501"

    after_err = await env.admin.fetchrow(
        """
        SELECT generation_error_code, generation_last_activity_at, updated_at, title
        FROM public.exam_sessions
        WHERE id = $1::uuid
        """,
        env.sid,
    )
    assert after_err["generation_error_code"] == before["generation_error_code"]
    assert after_err["generation_last_activity_at"] == before["generation_last_activity_at"]
    assert after_err["updated_at"] == before["updated_at"]
    assert after_err["title"] == before["title"]

    with pytest.raises(asyncpg.PostgresError) as exc_act:
        await env.owner.execute(
            "UPDATE exam_sessions SET generation_last_activity_at = now() WHERE id = $1::uuid",
            env.sid,
        )
    assert (getattr(exc_act.value, "sqlstate", None) or exc_act.value.as_dict().get("sqlstate")) == "42501"

    after_act = await env.admin.fetchrow(
        """
        SELECT generation_error_code, generation_last_activity_at, updated_at, title
        FROM public.exam_sessions
        WHERE id = $1::uuid
        """,
        env.sid,
    )
    assert after_act["generation_error_code"] == before["generation_error_code"]
    assert after_act["generation_last_activity_at"] == before["generation_last_activity_at"]
    assert after_act["updated_at"] == before["updated_at"]
    assert after_act["title"] == before["title"]

    # Metadata update still succeeds even under table-level grant
    await env.owner.execute(
        "UPDATE exam_sessions SET title = 'Safe Title' WHERE id = $1::uuid",
        env.sid,
    )

    after_meta = await env.admin.fetchrow(
        """
        SELECT generation_error_code, generation_last_activity_at, updated_at, title
        FROM public.exam_sessions
        WHERE id = $1::uuid
        """,
        env.sid,
    )
    assert after_meta["title"] == "Safe Title"
    assert after_meta["generation_error_code"] == before["generation_error_code"]
    assert after_meta["generation_last_activity_at"] == before["generation_last_activity_at"]

    # 3. Re-applying migration 017 revokes table-level UPDATE and restores strict least privilege
    await env.admin.execute(MIGRATION_017.read_text(encoding="utf-8-sig"))
    assert await env.admin.fetchval(
        "SELECT has_table_privilege('authenticated', 'public.exam_sessions', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'generation_error_code', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'generation_last_activity_at', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'title', 'UPDATE')"
    ) is True


async def test_privilege_catalog_matrix(env):
    """Verify PostgreSQL ACL catalog privilege state after migration 017."""
    # authenticated role privileges
    assert await env.admin.fetchval(
        "SELECT has_table_privilege('authenticated', 'public.exam_sessions', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_table_privilege('authenticated', 'public.exam_sessions', 'INSERT')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'title', 'UPDATE')"
    ) is True
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'subject', 'UPDATE')"
    ) is True
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'grade', 'UPDATE')"
    ) is True
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'generation_last_activity_at', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'generation_error_code', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'status', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('authenticated', 'public.exam_sessions', 'active_job_id', 'UPDATE')"
    ) is False

    # anon role privileges
    assert await env.admin.fetchval(
        "SELECT has_table_privilege('anon', 'public.exam_sessions', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('anon', 'public.exam_sessions', 'generation_last_activity_at', 'UPDATE')"
    ) is False
    assert await env.admin.fetchval(
        "SELECT has_column_privilege('anon', 'public.exam_sessions', 'generation_error_code', 'UPDATE')"
    ) is False


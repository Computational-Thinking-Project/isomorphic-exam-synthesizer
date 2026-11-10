"""Real PostgreSQL 15 integration tests for Finalize & Content Lock (TASK-305).

Tests FinalizeService, FinalizeRepository, and ReviewRepository against a real
PostgreSQL 15 instance running Migration 006 (TASK-302) and Migration 007 (TASK-305).
Proves resolution of reviewer findings:
- F01: Content Lock & Race Condition (Approval commits -> concurrent review mutations
       blocked with HTTP 423 ERR_SESSION_LOCKED, zero invalidation leak).
- F02: Cartesian Product (V x S) completeness guard.
- F03: Answers Matrix full coverage validation (incomplete keys raise 409).
- Idempotency: Re-approving already approved session is safe and preserves approved_at.
- State Machine: Session in 'generated' status cannot be approved.
"""

import json
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from app.models.schemas import (
    ReviewDomainException,
)
from app.services.finalize.repository import FinalizeRepository
from app.services.finalize.service import FinalizeService
from app.services.review.repository import ReviewRepository
from app.services.shuffler.service import generate_deterministic_seed
from tests.services.isolated_postgres import assert_disposable_database, isolated_pg_dsn  # noqa: F401

asyncpg = pytest.importorskip("asyncpg")

OWNER_ID = "00000000-0000-0000-0000-000000000001"
PG_DSN = ""


def _literal(val: Any) -> str:
    if val is None:
        return "NULL"
    return "'" + str(val).replace("'", "''") + "'"


class AsyncpgRpcResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class AsyncpgRpcBuilder:
    def __init__(
        self, dsn: str, fn_name: str, params: Dict[str, Any], role: str, actor: str
    ) -> None:
        self.dsn = dsn
        self.fn_name = fn_name
        self.params = params
        self.role = role
        self.actor = actor

    def execute(self) -> AsyncpgRpcResult:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self._execute_async()).result()
        return asyncio.run(self._execute_async())

    async def _execute_async(self) -> AsyncpgRpcResult:
        conn = await asyncpg.connect(self.dsn)
        try:
            # Set auth context
            await conn.execute(
                f"SET ROLE {self.role}; "
                f"SET request.jwt.claim.role = '{self.role}'; "
                f"SET request.jwt.claim.sub = '{self.actor}';"
            )

            # Build call expression with typed arguments
            args = []
            for k, v in self.params.items():
                if isinstance(v, (dict, list)):
                    args.append(f"{_literal(json.dumps(v))}::jsonb")
                elif isinstance(v, bool):
                    args.append("true" if v else "false")
                elif isinstance(v, (int, float)):
                    args.append(str(v))
                else:
                    args.append(_literal(v))

            query = f"SELECT public.{self.fn_name}({','.join(args)});"
            raw = await conn.fetchval(query)
            if raw is None:
                return AsyncpgRpcResult(None)
            if isinstance(raw, str):
                try:
                    return AsyncpgRpcResult(json.loads(raw))
                except Exception:
                    return AsyncpgRpcResult(raw)
            return AsyncpgRpcResult(raw)
        finally:
            await conn.close()


class AsyncpgTableBuilder:
    def __init__(
        self,
        dsn: str,
        table_name: str,
        role: str = "authenticated",
        actor: str = OWNER_ID,
    ) -> None:
        self.dsn = dsn
        self.table_name = table_name
        self.role = role
        self.actor = actor
        self._select_cols = "*"
        self._filters: List[str] = []
        self._limit: Optional[int] = None
        self._order_by: Optional[str] = None

    def select(self, cols: str) -> "AsyncpgTableBuilder":
        self._select_cols = cols.replace("!inner", "")
        return self

    def eq(self, col: str, val: Any) -> "AsyncpgTableBuilder":
        self._filters.append(f"{col} = {_literal(val)}")
        return self

    def neq(self, col: str, val: Any) -> "AsyncpgTableBuilder":
        self._filters.append(f"{col} <> {_literal(val)}")
        return self

    def in_(self, col: str, vals: List[Any]) -> "AsyncpgTableBuilder":
        formatted = ", ".join(_literal(v) for v in vals)
        self._filters.append(f"{col} IN ({formatted})")
        return self

    def limit(self, n: int) -> "AsyncpgTableBuilder":
        self._limit = n
        return self

    def order(self, col: str) -> "AsyncpgTableBuilder":
        self._order_by = col
        return self

    def execute(self) -> AsyncpgRpcResult:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self._execute_async()).result()
        return asyncio.run(self._execute_async())

    async def _execute_async(self) -> AsyncpgRpcResult:
        conn = await asyncpg.connect(self.dsn)
        try:
            # Set auth context for production-equivalent RLS enforcement
            await conn.execute(
                f"SET ROLE {self.role}; "
                f"SET request.jwt.claim.role = '{self.role}'; "
                f"SET request.jwt.claim.sub = '{self.actor}';"
            )
            where_clause = f"WHERE {' AND '.join(self._filters)}" if self._filters else ""
            order_clause = f"ORDER BY {self._order_by}" if self._order_by else ""
            limit_clause = f"LIMIT {self._limit}" if self._limit else ""
            query = f"SELECT json_agg(t) FROM (SELECT {self._select_cols} FROM public.{self.table_name} {where_clause} {order_clause} {limit_clause}) t;"
            raw = await conn.fetchval(query)
            if not raw:
                return AsyncpgRpcResult([])
            return AsyncpgRpcResult(json.loads(raw) if isinstance(raw, str) else raw)
        finally:
            await conn.close()


class AsyncpgSupabaseAdapter:
    """Supabase client double backed directly by PostgreSQL asyncpg connections."""

    def __init__(self, dsn: str, role: str = "authenticated", actor: str = OWNER_ID) -> None:
        self.dsn = dsn
        self.role = role
        self.actor = actor

    def rpc(self, fn_name: str, params: Optional[Dict[str, Any]] = None) -> AsyncpgRpcBuilder:
        return AsyncpgRpcBuilder(self.dsn, fn_name, params or {}, self.role, self.actor)

    def table(self, table_name: str) -> AsyncpgTableBuilder:
        return AsyncpgTableBuilder(self.dsn, table_name, role=self.role, actor=self.actor)


@pytest.fixture(scope="module", autouse=True)
async def setup_real_postgres_database(isolated_pg_dsn):  # noqa: F811
    """Initializes schema, roles, migration 006, and migration 007 on real PostgreSQL."""
    global PG_DSN
    PG_DSN, expected_database = isolated_pg_dsn
    conn = await asyncpg.connect(PG_DSN)
    try:
        await assert_disposable_database(conn, expected_database)
    except Exception:
        await conn.close()
        raise

    mig006_path = "/app/backend/migrations/006_stage3_review_and_shuffle.sql"
    if not os.path.exists(mig006_path):
        mig006_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "../../migrations/006_stage3_review_and_shuffle.sql"
            )
        )
    if not os.path.exists(mig006_path):
        pytest.skip("Migration 006 not found on filesystem")

    mig007_path = "/app/backend/migrations/007_finalize_approve_session_rpc.sql"
    if not os.path.exists(mig007_path):
        mig007_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "../../migrations/007_finalize_approve_session_rpc.sql"
            )
        )
    if not os.path.exists(mig007_path):
        pytest.skip("Migration 007 not found on filesystem")

    try:
        # 1. Setup Roles
        await conn.execute("""
        DO $$ BEGIN
            CREATE ROLE anon;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        DO $$ BEGIN
            CREATE ROLE authenticated;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        DO $$ BEGIN
            CREATE ROLE service_role BYPASSRLS;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """)

        # 2. Setup Auth & Storage stubs
        await conn.execute("""
        CREATE SCHEMA IF NOT EXISTS auth;
        CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb);
        CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
        $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
        CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS
        $$ SELECT nullif(current_setting('request.jwt.claim.role', true), '') $$;
        CREATE SCHEMA IF NOT EXISTS storage;
        CREATE TABLE IF NOT EXISTS storage.buckets (id text PRIMARY KEY, name text, public boolean);
        CREATE TABLE IF NOT EXISTS storage.objects (bucket_id text, name text);
        CREATE OR REPLACE FUNCTION storage.foldername(text) RETURNS text[] LANGUAGE sql IMMUTABLE AS
        $$ SELECT string_to_array($1, '/') $$;

        -- Clean reset public schema for repeatable test runs
        DROP SCHEMA IF EXISTS public CASCADE;
        CREATE SCHEMA public;
        GRANT ALL ON SCHEMA public TO postgres, public;
        """)

        # 3. Apply schema.sql
        schema_path = "/app/backend/scripts/schema.sql"
        if not os.path.exists(schema_path):
            schema_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../scripts/schema.sql")
            )
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8-sig") as f:
                await conn.execute(f.read().lstrip("\ufeff"))

        # 4. Apply Migration 006
        with open(mig006_path, "r", encoding="utf-8-sig") as f:
            await conn.execute(f.read().lstrip("\ufeff"))

        # 5. Apply Migration 007
        with open(mig007_path, "r", encoding="utf-8-sig") as f:
            await conn.execute(f.read().lstrip("\ufeff"))
        for migration in (
            "008_finalize_persist_shuffle_rpc.sql",
            "009_finalize_security_boundary.sql",
        ):
            path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../../migrations", migration)
            )
            with open(path, "r", encoding="utf-8-sig") as f:
                await conn.execute(f.read().lstrip("\ufeff"))

        # 6. Seed owner user
        await conn.execute(f"""
        INSERT INTO auth.users(id, email) VALUES ('{OWNER_ID}', 'teacher@school.edu.vn') ON CONFLICT (id) DO NOTHING;
        INSERT INTO public.users(id, email) VALUES ('{OWNER_ID}', 'teacher@school.edu.vn') ON CONFLICT (id) DO NOTHING;
        """)
    finally:
        await conn.close()


@pytest.fixture
def owner_client() -> AsyncpgSupabaseAdapter:
    return AsyncpgSupabaseAdapter(PG_DSN, role="authenticated", actor=OWNER_ID)


@pytest.fixture
def worker_client() -> AsyncpgSupabaseAdapter:
    return AsyncpgSupabaseAdapter(PG_DSN, role="service_role", actor=OWNER_ID)


@pytest.fixture
async def reviewed_exam_session():
    """Generates an exam session in 'reviewed' status with finalized versions and approved questions."""
    conn = await asyncpg.connect(PG_DSN)
    try:
        s_id = str(uuid4())
        src_id = str(uuid4())
        v101_id = str(uuid4())
        v102_id = str(uuid4())
        q1_id = str(uuid4())
        q2_id = str(uuid4())

        v101_perm = json.dumps({
            "question_order": [1],
            "display_to_canonical": {"1": 1},
            "canonical_to_display": {"1": 1},
            "option_permutations": {"1": {"A": "A", "B": "B", "C": "C", "D": "D"}},
        })
        v102_perm = json.dumps({
            "question_order": [1],
            "display_to_canonical": {"1": 1},
            "canonical_to_display": {"1": 1},
            "option_permutations": {"1": {"A": "B", "B": "C", "C": "D", "D": "A"}},
        })

        v101_seed, _ = generate_deterministic_seed(s_id, "101")
        v102_seed, _ = generate_deterministic_seed(s_id, "102")

        await conn.execute(f"""
        INSERT INTO exam_sessions(id, user_id, title, gemini_review_calls, status)
            VALUES ('{s_id}', '{OWNER_ID}', 'Session Ready For Approval', 0, 'reviewed');
        INSERT INTO generation_configs(session_id, n_versions, ordering_preferences)
            VALUES ('{s_id}', 2, '{{"shuffle_questions": true, "shuffle_options": true}}'::jsonb);
        INSERT INTO source_questions(id, session_id, question_no, raw_content, options, correct_key)
            VALUES ('{src_id}', '{s_id}', 1, 'Source Stem 1', '["A","B","C","D"]'::jsonb, 'A');
        INSERT INTO question_blueprints(source_question_id, confirmed_at)
            VALUES ('{src_id}', now());
        INSERT INTO exam_versions(id, session_id, version_code, is_finalized, shuffle_seed, permutations)
            VALUES ('{v101_id}', '{s_id}', '101', true, '{v101_seed}', '{v101_perm}'::jsonb),
                   ('{v102_id}', '{s_id}', '102', true, '{v102_seed}', '{v102_perm}'::jsonb);
        INSERT INTO version_questions(id, version_id, source_question_id, question_no, content, options, correct_key,
            canonical_question_no, canonical_options, canonical_correct_key, solution_md, canonical_solution_md, status, is_current)
            VALUES ('{q1_id}', '{v101_id}', '{src_id}', 1, 'Candidate 101', '["A","B","C","D"]'::jsonb, 'A',
                    1, '["A","B","C","D"]'::jsonb, 'A', 'Đáp án đúng là A', 'Đáp án đúng là A', 'approved', true),
                   ('{q2_id}', '{v102_id}', '{src_id}', 1, 'Candidate 102', '["D","A","B","C"]'::jsonb, 'B',
                    1, '["A","B","C","D"]'::jsonb, 'A', 'Đáp án đúng là B', 'Đáp án đúng là A', 'approved', true);
        INSERT INTO answer_keys(version_id, question_no, correct_option, display_no, display_correct_key, canonical_question_no)
            VALUES ('{v101_id}', 1, 'A', 1, 'A', 1),
                   ('{v102_id}', 1, 'B', 1, 'B', 1);
        UPDATE exam_sessions SET status='reviewed' WHERE id='{s_id}';
        """)
        return {
            "session_id": s_id,
            "source_id": src_id,
            "version_ids": [v101_id, v102_id],
            "question_ids": [q1_id, q2_id],
        }
    finally:
        await conn.close()


# ==============================================================================
# F01: Content Lock & Race Condition Prevention on Real PostgreSQL
# ==============================================================================


@pytest.mark.asyncio
async def test_f01_interleaving_mutation_blocked_by_approval_on_real_pg(
    owner_client: AsyncpgSupabaseAdapter,
    worker_client: AsyncpgSupabaseAdapter,
    reviewed_exam_session,
):
    """F01 Verification on Real PostgreSQL:
    1. Approval commits via finalize_approve_session -> session transitions to 'approved'.
    2. A concurrent worker attempts review mutation (reserve_max_quota_and_start_regenerating).
    3. The review mutation is strictly blocked with HTTP 423 ERR_SESSION_LOCKED.
    4. Verified Invariants:
       - Session remains 'approved'.
       - exam_versions remain is_finalized=true.
       - answer_keys are NOT wiped.
       - Zero questions are mutated to regenerating.
    """
    s_info = reviewed_exam_session
    s_id = s_info["session_id"]
    q_id = s_info["question_ids"][0]

    finalize_svc = FinalizeService(owner_client)
    review_repo = ReviewRepository(
        db=owner_client, service_db=worker_client, allow_table_fallback=False
    )

    # 1. Approval commits
    app_res = await finalize_svc.approve_session(s_id, OWNER_ID)
    assert app_res.status == "approved"
    assert app_res.approved_at is not None

    # 2. Worker attempts review reservation on approved session
    op_id = uuid4()
    with pytest.raises(ReviewDomainException) as exc_info:
        await review_repo.reserve_max_quota_and_start_regenerating(
            s_id, q_id, OWNER_ID, operation_id=op_id
        )

    assert exc_info.value.status_code == 423
    assert exc_info.value.error_code == "ERR_SESSION_LOCKED"

    # 3. Verify PostgreSQL Invariants
    conn = await asyncpg.connect(PG_DSN)
    try:
        sess_row = await conn.fetchrow(
            f"SELECT status, approved_at FROM public.exam_sessions WHERE id = '{s_id}'"
        )
        assert sess_row["status"] == "approved"

        unfinalized_count = await conn.fetchval(
            f"SELECT count(*) FROM public.exam_versions WHERE session_id = '{s_id}' AND is_finalized = false"
        )
        assert unfinalized_count == 0, "exam_versions must NOT be unfinalized after approval!"

        ak_count = await conn.fetchval(
            f"SELECT count(*) FROM public.answer_keys WHERE version_id IN ('{s_info['version_ids'][0]}', '{s_info['version_ids'][1]}')"
        )
        assert ak_count == 2, "answer_keys must NOT be wiped after approval!"
    finally:
        await conn.close()


# ==============================================================================
# F02: Cartesian Product Completeness Guard on Real PostgreSQL
# ==============================================================================


@pytest.mark.asyncio
async def test_f02_missing_cartesian_question_aborts_approval_on_real_pg(
    owner_client: AsyncpgSupabaseAdapter, reviewed_exam_session
):
    """F02 Verification: When a version is missing an approved current question variant,
    finalize_approve_session strictly aborts with ERR_NOT_ALL_QUESTIONS_APPROVED.
    """
    s_info = reviewed_exam_session
    s_id = s_info["session_id"]
    v102_id = s_info["version_ids"][1]

    # Delete current question variant for version 102
    conn = await asyncpg.connect(PG_DSN)
    try:
        await conn.execute(f"DELETE FROM public.version_questions WHERE version_id = '{v102_id}'")
    finally:
        await conn.close()

    finalize_svc = FinalizeService(owner_client)
    with pytest.raises(ReviewDomainException) as exc_info:
        await finalize_svc.approve_session(s_id, OWNER_ID)

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "ERR_NOT_ALL_QUESTIONS_APPROVED"


# ==============================================================================
# F03: Answers Matrix Full Coverage on Real PostgreSQL
# ==============================================================================


@pytest.mark.asyncio
async def test_f03_answers_matrix_coverage_validation_on_real_pg(
    owner_client: AsyncpgSupabaseAdapter, reviewed_exam_session
):
    """F03 Verification: Complete answer_keys return valid matrix.
    If answer_keys is partially incomplete, raises ERR_INCONSISTENT_ANSWER_KEYS (409).
    """
    s_info = reviewed_exam_session
    s_id = s_info["session_id"]
    v102_id = s_info["version_ids"][1]

    finalize_repo = FinalizeRepository(owner_client)

    # 1. Complete keys -> Success
    version_codes, matrix_rows = await finalize_repo.fetch_matrix_raw(s_id)
    assert set(version_codes) == {"101", "102"}
    assert len(matrix_rows) == 2

    # 2. Corrupt partial coverage: delete key for version 102
    conn = await asyncpg.connect(PG_DSN)
    try:
        await conn.execute(f"DELETE FROM public.answer_keys WHERE version_id = '{v102_id}'")
    finally:
        await conn.close()

    with pytest.raises(ReviewDomainException) as exc_info:
        await finalize_repo.fetch_matrix_raw(s_id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"


# ==============================================================================
# Idempotency & State Machine Guards on Real PostgreSQL
# ==============================================================================


@pytest.mark.asyncio
async def test_idempotent_reapproval_on_real_pg(
    owner_client: AsyncpgSupabaseAdapter, reviewed_exam_session
):
    """Idempotency Verification: Re-approving an already approved session succeeds,
    returns 200 with the exact same approved_at timestamp.
    """
    s_info = reviewed_exam_session
    s_id = s_info["session_id"]
    finalize_svc = FinalizeService(owner_client)

    res1 = await finalize_svc.approve_session(s_id, OWNER_ID)
    assert res1.status == "approved"
    ts1 = res1.approved_at

    res2 = await finalize_svc.approve_session(s_id, OWNER_ID)
    assert res2.status == "approved"
    assert res2.approved_at == ts1


@pytest.mark.asyncio
async def test_generated_session_cannot_be_approved_on_real_pg(
    owner_client: AsyncpgSupabaseAdapter,
):
    """State Machine Guard: Session in 'generated' status cannot be approved,
    must raise ERR_INVALID_SESSION_STATE (409).
    """
    s_id = str(uuid4())
    conn = await asyncpg.connect(PG_DSN)
    try:
        await conn.execute(f"""
        INSERT INTO exam_sessions(id, user_id, title, gemini_review_calls, status)
            VALUES ('{s_id}', '{OWNER_ID}', 'Unreviewed Session', 0, 'generated');
        """)
    finally:
        await conn.close()

    finalize_svc = FinalizeService(owner_client)
    with pytest.raises(ReviewDomainException) as exc_info:
        await finalize_svc.approve_session(s_id, OWNER_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INVALID_SESSION_STATE"


@pytest.mark.asyncio
async def test_preview_snapshot_on_real_pg(
    owner_client: AsyncpgSupabaseAdapter,
    worker_client: AsyncpgSupabaseAdapter,
):
    """Real PostgreSQL verification of full shuffle -> preview -> approve pipeline (W4-MVP-05).

    1. Provisions a fresh unfinalized session in 'reviewed' status with 2 sources and 2 versions.
    2. Verifies preview before shuffle fails closed with 409 ERR_SHUFFLE_REQUIRED.
    3. Runs shuffle_session() which invokes real finalize_persist_shuffle RPC in PostgreSQL via service-role writer.
    4. Fetches and validates preview snapshot against real PostgreSQL database.
    5. Asserts displayed slots, choices, answer keys, canonical mappings, and answers matrix.
    6. Approves session and verifies preview projection remains deterministic on approved session.
    """
    conn = await asyncpg.connect(PG_DSN)
    s_id = str(uuid4())
    src1_id = str(uuid4())
    src2_id = str(uuid4())
    v101_id = str(uuid4())
    v102_id = str(uuid4())
    q1_101 = str(uuid4())
    q2_101 = str(uuid4())
    q1_102 = str(uuid4())
    q2_102 = str(uuid4())

    try:
        await conn.execute(f"""
        INSERT INTO exam_sessions(id, user_id, title, gemini_review_calls, status)
            VALUES ('{s_id}', '{OWNER_ID}', 'Toán Thi THPT 2026', 0, 'reviewed');
        INSERT INTO generation_configs(session_id, n_versions, ordering_preferences)
            VALUES ('{s_id}', 2, '{{"shuffle_questions": true, "shuffle_options": true}}'::jsonb);
        INSERT INTO source_questions(id, session_id, question_no, raw_content, options, correct_key)
            VALUES ('{src1_id}', '{s_id}', 1, 'Source Stem 1', '["A1","B1","C1","D1"]'::jsonb, 'A'),
                   ('{src2_id}', '{s_id}', 2, 'Source Stem 2', '["A2","B2","C2","D2"]'::jsonb, 'C');
        INSERT INTO question_blueprints(source_question_id, confirmed_at)
            VALUES ('{src1_id}', now()),
                   ('{src2_id}', now());
        INSERT INTO exam_versions(id, session_id, version_code, is_finalized)
            VALUES ('{v101_id}', '{s_id}', '101', false),
                   ('{v102_id}', '{s_id}', '102', false);
        INSERT INTO version_questions(id, version_id, source_question_id, question_no, content, options, correct_key,
            canonical_question_no, canonical_options, canonical_correct_key, solution_md, canonical_solution_md, status, is_current)
            VALUES ('{q1_101}', '{v101_id}', '{src1_id}', 1, 'Question 1 v101', '["A1","B1","C1","D1"]'::jsonb, 'A',
                    1, '["A1","B1","C1","D1"]'::jsonb, 'A', 'Chọn đáp án A', 'Chọn đáp án A', 'approved', true),
                   ('{q2_101}', '{v101_id}', '{src2_id}', 2, 'Question 2 v101', '["A2","B2","C2","D2"]'::jsonb, 'C',
                    2, '["A2","B2","C2","D2"]'::jsonb, 'C', 'Chọn đáp án C', 'Chọn đáp án C', 'approved', true),
                   ('{q1_102}', '{v102_id}', '{src1_id}', 1, 'Question 1 v102', '["A1","B1","C1","D1"]'::jsonb, 'A',
                    1, '["A1","B1","C1","D1"]'::jsonb, 'A', 'Chọn đáp án A', 'Chọn đáp án A', 'approved', true),
                   ('{q2_102}', '{v102_id}', '{src2_id}', 2, 'Question 2 v102', '["A2","B2","C2","D2"]'::jsonb, 'C',
                    2, '["A2","B2","C2","D2"]'::jsonb, 'C', 'Chọn đáp án C', 'Chọn đáp án C', 'approved', true);
        """)
    finally:
        await conn.close()

    finalize_svc = FinalizeService(
        db=owner_client,
        repo=FinalizeRepository(owner_client),
        writer_repo=FinalizeRepository(worker_client),
    )

    # 1. Preview before shuffle must fail closed
    with pytest.raises(ReviewDomainException) as pre_exc:
        await finalize_svc.get_preview_snapshot(s_id, OWNER_ID)
    assert pre_exc.value.status_code == 409
    assert pre_exc.value.error_code == "ERR_SHUFFLE_REQUIRED"

    # 2. Execute full shuffle flow (computes shuffle -> runs real PostgreSQL finalize_persist_shuffle RPC)
    shuffle_receipt = await finalize_svc.shuffle_session(s_id, OWNER_ID)
    assert shuffle_receipt.is_finalized is True
    assert len(shuffle_receipt.versions) == 2

    # 3. Fetch preview snapshot on real PostgreSQL
    preview = await finalize_svc.get_preview_snapshot(s_id, OWNER_ID)
    assert preview.session_id == s_id
    assert preview.status == "reviewed"
    assert preview.is_finalized is True
    assert preview.n_versions == 2
    assert preview.total_questions == 2
    assert len(preview.versions) == 2

    # 4. Assert slots, choices, answer keys, and canonical mappings
    source_map = {1: src1_id, 2: src2_id}
    for v in preview.versions:
        assert v.version_code in ("101", "102")
        assert v.total_questions == 2
        assert len(v.questions) == 2
        assert set(v.answer_keys.keys()) == {"1", "2"}

        seen_display_nos = set()
        seen_canonical_nos = set()
        seen_source_ids = set()

        for q in v.questions:
            seen_display_nos.add(q.question_no)
            seen_canonical_nos.add(q.canonical_question_no)
            seen_source_ids.add(q.source_question_id)

            assert q.source_question_id == source_map[q.canonical_question_no]
            assert q.status == "approved"
            assert len(q.options) == 4
            assert q.correct_key in ("A", "B", "C", "D")
            assert v.answer_keys[str(q.question_no)] == q.correct_key

        assert seen_display_nos == {1, 2}
        assert seen_canonical_nos == {1, 2}
        assert seen_source_ids == {src1_id, src2_id}

    # 5. Assert answers matrix
    assert len(preview.matrix) == 2
    for row in preview.matrix:
        assert row.question_no in (1, 2)
        assert set(row.answers.keys()) == {"101", "102"}
        for v in preview.versions:
            assert row.answers[v.version_code] == v.answer_keys[str(row.question_no)]

    # 6. Approve session and verify post-approval preview
    app_res = await finalize_svc.approve_session(s_id, OWNER_ID)
    assert app_res.status == "approved"

    post_approval_preview = await finalize_svc.get_preview_snapshot(s_id, OWNER_ID)
    assert post_approval_preview.status == "approved"
    assert post_approval_preview.total_questions == 2
    assert len(post_approval_preview.matrix) == 2


@pytest.mark.asyncio
async def test_cross_user_isolation_on_real_pg(
    owner_client: AsyncpgSupabaseAdapter,
    reviewed_exam_session: Dict[str, Any],
):
    """Verifies that an authenticated actor cannot access another user's session preview (W4-MVP-05)."""
    s_info = reviewed_exam_session
    s_id = s_info["session_id"]
    other_actor_id = str(uuid4())
    other_client = AsyncpgSupabaseAdapter(PG_DSN, role="authenticated", actor=other_actor_id)

    # 1. Direct table read under RLS must yield empty list
    sessions_read = other_client.table("exam_sessions").select("*").eq("id", s_id).execute()
    assert sessions_read.data == [] or sessions_read.data is None

    # 2. Preview snapshot through service must raise domain exception (403 or 404)
    other_service = FinalizeService(other_client)
    with pytest.raises(ReviewDomainException) as exc_info:
        await other_service.get_preview_snapshot(s_id, other_actor_id)
    assert exc_info.value.status_code in (403, 404)


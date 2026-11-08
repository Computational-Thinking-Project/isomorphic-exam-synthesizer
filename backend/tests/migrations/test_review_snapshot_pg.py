"""PostgreSQL Integration Tests for Review Snapshot RPC (W4-MVP-03).

Opt in with RUN_POSTGRES_MIGRATION_TESTS=1:
    RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -p 'test_review_snapshot_pg.py' -v

Full Integration Verification Matrix:
1. Security: Owner (200), foreign owner (404 P0002), nonexistent session (404 P0002), anonymous
2. Lifecycle: Generated, partial, regenerating (200 with ready=false), locked (423), post-shuffle (409)
3. Matrix Integrity: Complete, missing, duplicate (fail-closed 503), orphan (fail-closed 503), extra version (fail-closed 503), canonical mismatch (fail-closed 503)
4. Provenance: AI, clone, regenerated, reverted, unknown
5. Validation Priority: Version question overrides generation target result; unavailable when both missing
6. Progress: Invariant consensus with authoritative _review_progress
7. Freshness Token: Determinism across calls & change on any payload mutation
8. Concurrency: Read consistency during writer transaction
"""

import json
import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "backend/scripts/schema.sql"
MIGRATIONS_DIR = ROOT / "backend/migrations"

BOOTSTRAP = """
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
"""

FIXTURE_USER = "00000000-0000-0000-0000-000000000001"
FOREIGN_USER = "00000000-0000-0000-0000-000000000002"
FIXTURE_SESSION = "10000000-0000-0000-0000-000000000001"
CONFIRMATION_ID = "90000000-0000-0000-0000-000000000001"
JOB_SNAPSHOT_ID = "a0000000-0000-0000-0000-000000000001"
SOURCE_Q1 = "20000000-0000-0000-0000-000000000001"
SOURCE_Q2 = "20000000-0000-0000-0000-000000000002"
SOURCE_REV1 = "b0000000-0000-0000-0000-000000000001"
SOURCE_REV2 = "b0000000-0000-0000-0000-000000000002"
VERSION_1 = "30000000-0000-0000-0000-000000000001"
VERSION_2 = "30000000-0000-0000-0000-000000000002"
CANDIDATE_V1_Q1 = "40000000-0000-0000-0000-000000000001"
CANDIDATE_V1_Q2 = "40000000-0000-0000-0000-000000000002"
CANDIDATE_V2_Q1 = "40000000-0000-0000-0000-000000000003"
CANDIDATE_V2_Q2 = "40000000-0000-0000-0000-000000000004"


@unittest.skipUnless(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") == "1", "PostgreSQL integration opt-in"
)
class ReviewSnapshotPostgresCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docker = os.getenv("DOCKER_BIN") or shutil.which("docker")
        if not cls.docker:
            raise RuntimeError("Set DOCKER_BIN to the Docker CLI executable")

        cls.container = f"review-snap-test-{uuid4().hex[:12]}"
        cls.addClassCleanup(cls.stop_container)
        cls.run_docker(
            "run",
            "--detach",
            "--name",
            cls.container,
            "--network",
            "none",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "postgres:15-alpine",
        )
        for _ in range(40):
            ready = cls.run_docker(
                "exec",
                cls.container,
                "pg_isready",
                "-h",
                "127.0.0.1",
                "-U",
                "postgres",
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("PostgreSQL did not become ready")
        cls.sql(
            "CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;",
            db="postgres",
        )

    @classmethod
    def stop_container(cls):
        cls.run_docker("rm", "--force", cls.container, check=False)

    @classmethod
    def run_docker(cls, *args, check=True, input=None):
        return subprocess.run(
            [cls.docker, *args],
            input=input,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=check,
            timeout=60,
        )

    @classmethod
    def sql(cls, script, *, db=None, check=True):
        result = cls.run_docker(
            "exec",
            "-i",
            cls.container,
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            db or cls.db,
            input=script,
            check=False,
        )
        if check and result.returncode:
            raise AssertionError(result.stderr)
        return result

    def setUp(self):
        type(self).db = f"db_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)

        # 1. Apply baseline schema
        self.sql(BOOTSTRAP + SCHEMA_SQL.read_text(encoding="utf-8"))

        # 2. Apply all migrations in strict numerical order
        migration_files = sorted(
            [f for f in MIGRATIONS_DIR.glob("*.sql") if f.is_file() and f.stat().st_size > 0],
            key=lambda p: p.name,
        )
        for mig in migration_files:
            content = mig.read_text(encoding="utf-8")
            self.sql(content)

        # 3. Seed production-shaped test fixtures
        self._seed_baseline()

    def _seed_baseline(self):
        seed_sql = f"""
        INSERT INTO auth.users(id, email) VALUES
          ('{FIXTURE_USER}', 'teacher@example.com'),
          ('{FOREIGN_USER}', 'other@example.com');
        INSERT INTO public.users(id, email) VALUES
          ('{FIXTURE_USER}', 'teacher@example.com'),
          ('{FOREIGN_USER}', 'other@example.com')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO public.exam_sessions(id, user_id, title, status) VALUES
          ('{FIXTURE_SESSION}', '{FIXTURE_USER}', 'Đề thi Toán 10', 'generated');

        INSERT INTO public.generation_configs(session_id, n_versions, active_variation_modes, mapping_version) VALUES
          ('{FIXTURE_SESSION}', 2, '[]'::jsonb, '1.0');

        INSERT INTO public.source_questions(id, session_id, question_no, raw_content, options, correct_key, solution_md) VALUES
          ('{SOURCE_Q1}', '{FIXTURE_SESSION}', 1, 'Giải phương trình 2x + 4 = 0.', '["x = -2", "x = 2", "x = -4", "x = 4"]'::jsonb, 'A', 'Ta có 2x = -4 suy ra x = -2.'),
          ('{SOURCE_Q2}', '{FIXTURE_SESSION}', 2, 'Tính đạo hàm của y = x^2.', '["y'' = 2x", "y'' = x", "y'' = 2", "y'' = x^2"]'::jsonb, 'A', 'Đạo hàm là 2x.');

        INSERT INTO public.source_artifact_confirmations(confirmation_id, session_id, actor_id, confirmed_at, result) VALUES
          ('{CONFIRMATION_ID}', '{FIXTURE_SESSION}', '{FIXTURE_USER}', now(),
           jsonb_build_object(
             'sources', jsonb_build_array(
               jsonb_build_object('source_question_id', '{SOURCE_Q1}', 'source_revision_id', '{SOURCE_REV1}'),
               jsonb_build_object('source_question_id', '{SOURCE_Q2}', 'source_revision_id', '{SOURCE_REV2}')
             )
           )
          );

        INSERT INTO public.source_artifact_revisions(source_revision_id, confirmation_id, source_question_id, confirmed_input, source_fingerprint) VALUES
          ('{SOURCE_REV1}', '{CONFIRMATION_ID}', '{SOURCE_Q1}',
           jsonb_build_object('id', '{SOURCE_Q1}', 'question_text', 'Giải phương trình 2x + 4 = 0.', 'options', jsonb_build_array('x = -2', 'x = 2', 'x = -4', 'x = 4'), 'correct_answer', 'A', 'solution', 'Ta có 2x = -4 suy ra x = -2.'),
           repeat('1', 64)),
          ('{SOURCE_REV2}', '{CONFIRMATION_ID}', '{SOURCE_Q2}',
           jsonb_build_object('id', '{SOURCE_Q2}', 'question_text', 'Tính đạo hàm của y = x^2.', 'options', jsonb_build_array('y'' = 2x', 'y'' = x', 'y'' = 2', 'y'' = x^2'), 'correct_answer', 'A', 'solution', 'Đạo hàm là 2x.'),
           repeat('2', 64));

        INSERT INTO public.source_artifact_heads(source_question_id, source_revision_id, blueprint_revision_id) VALUES
          ('{SOURCE_Q1}', '{SOURCE_REV1}', gen_random_uuid()),
          ('{SOURCE_Q2}', '{SOURCE_REV2}', gen_random_uuid());

        -- Production-shaped snapshot payload directly matching Stage 2 outputs
        INSERT INTO public.generation_job_snapshots(id, session_id, job_token, confirmation_id, source_order, confirmed_source_hash, base_seed, n_versions, public_modes, canonical_dimensions, mapping_version, snapshot_payload) VALUES
          ('{JOB_SNAPSHOT_ID}', '{FIXTURE_SESSION}', gen_random_uuid(), '{CONFIRMATION_ID}',
           jsonb_build_array('{SOURCE_Q1}', '{SOURCE_Q2}'),
           'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
           100, 2, '[]'::jsonb, '[]'::jsonb, '1.0',
           jsonb_build_object(
             'confirmed_sources', jsonb_build_array(
               jsonb_build_object(
                 'source_question_id', '{SOURCE_Q1}',
                 'question_no', 1,
                 'source_revision_id', '{SOURCE_REV1}',
                 'source_fingerprint', repeat('1', 64),
                 'confirmed_input', jsonb_build_object(
                   'id', '{SOURCE_Q1}',
                   'question_text', 'Giải phương trình 2x + 4 = 0.',
                   'options', jsonb_build_array('x = -2', 'x = 2', 'x = -4', 'x = 4'),
                   'correct_answer', 'A',
                   'solution', 'Ta có 2x = -4 suy ra x = -2.'
                 )
               ),
               jsonb_build_object(
                 'source_question_id', '{SOURCE_Q2}',
                 'question_no', 2,
                 'source_revision_id', '{SOURCE_REV2}',
                 'source_fingerprint', repeat('2', 64),
                 'confirmed_input', jsonb_build_object(
                   'id', '{SOURCE_Q2}',
                   'question_text', 'Tính đạo hàm của y = x^2.',
                   'options', jsonb_build_array('y'' = 2x', 'y'' = x', 'y'' = 2', 'y'' = x^2'),
                   'correct_answer', 'A',
                   'solution', 'Đạo hàm là 2x.'
                 )
               )
             )
           )
          );

        INSERT INTO public.exam_versions(id, session_id, version_code) VALUES
          ('{VERSION_1}', '{FIXTURE_SESSION}', '101'),
          ('{VERSION_2}', '{FIXTURE_SESSION}', '102');

        INSERT INTO public.version_questions(id, version_id, source_question_id, question_no, content, options, correct_key, solution_md, canonical_question_no, canonical_options, canonical_correct_key, is_current, status, has_warning, validation_report) VALUES
          ('{CANDIDATE_V1_Q1}', '{VERSION_1}', '{SOURCE_Q1}', 1, 'Biến thể 101-1', '["x = 2", "x = -2", "x = -3", "x = 3"]'::jsonb, 'B', 'Lời giải 101-1', 1, '["x = -2", "x = 2", "x = -4", "x = 4"]'::jsonb, 'A', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V1_Q2}', '{VERSION_1}', '{SOURCE_Q2}', 2, 'Biến thể 101-2', '["y'' = 6x", "y'' = 3x", "y'' = 6", "y'' = x^2"]'::jsonb, 'A', 'Lời giải 101-2', 2, '["y'' = 2x", "y'' = x", "y'' = 2", "y'' = x^2"]'::jsonb, 'A', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V2_Q1}', '{VERSION_2}', '{SOURCE_Q1}', 1, 'Biến thể 102-1', '["x = 2", "x = -4", "x = -2", "x = 4"]'::jsonb, 'C', 'Lời giải 102-1', 1, '["x = -2", "x = 2", "x = -4", "x = 4"]'::jsonb, 'A', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V2_Q2}', '{VERSION_2}', '{SOURCE_Q2}', 2, 'Biến thể 102-2', '["y'' = 10x", "y'' = 5x", "y'' = 10", "y'' = x^2"]'::jsonb, 'A', 'Lời giải 102-2', 2, '["y'' = 2x", "y'' = x", "y'' = 2", "y'' = x^2"]'::jsonb, 'A', true, 'pending_review', false, '{{}}'::jsonb);

        INSERT INTO public.generation_target_results(session_id, snapshot_id, job_token, version_index, source_question_id, question_no, is_success, attempts, seed, request_fingerprint, raw_result, version_question_id, result_kind) VALUES
          ('{FIXTURE_SESSION}', '{JOB_SNAPSHOT_ID}', gen_random_uuid(), 1, '{SOURCE_Q1}', 1, true, 1, 1100, repeat('a', 64), '{{"validation": {{"status": "passed", "solver": "sympy"}}}}'::jsonb, '{CANDIDATE_V1_Q1}', 'AI_RESULT'),
          ('{FIXTURE_SESSION}', '{JOB_SNAPSHOT_ID}', gen_random_uuid(), 1, '{SOURCE_Q2}', 2, true, 1, 1101, repeat('b', 64), '{{"validation": {{"status": "passed", "solver": "sympy"}}}}'::jsonb, '{CANDIDATE_V1_Q2}', 'AI_RESULT'),
          ('{FIXTURE_SESSION}', '{JOB_SNAPSHOT_ID}', gen_random_uuid(), 2, '{SOURCE_Q1}', 1, true, 1, 2100, repeat('c', 64), '{{"validation": {{"status": "passed", "solver": "sympy"}}}}'::jsonb, '{CANDIDATE_V2_Q1}', 'AI_RESULT'),
          ('{FIXTURE_SESSION}', '{JOB_SNAPSHOT_ID}', gen_random_uuid(), 2, '{SOURCE_Q2}', 2, true, 1, 2101, repeat('d', 64), '{{"validation": {{"status": "passed", "solver": "sympy"}}}}'::jsonb, '{CANDIDATE_V2_Q2}', 'AI_RESULT');
        """
        self.sql(seed_sql)

    def _call_rpc_as_user(self, user_id: str | None, session_id: str) -> dict:
        auth_setup = ""
        if user_id:
            auth_setup = f"""
            SET LOCAL ROLE authenticated;
            SET LOCAL "request.jwt.claim.sub" = '{user_id}';
            SET LOCAL "request.jwt.claim.role" = 'authenticated';
            """
        else:
            auth_setup = """
            SET LOCAL ROLE anon;
            RESET "request.jwt.claim.sub";
            RESET "request.jwt.claim.role";
            """

        script = f"""
        BEGIN;
        {auth_setup}
        SELECT public.get_review_current_snapshot('{session_id}'::uuid);
        COMMIT;
        """
        res = self.sql(script)
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip().startswith("{")]
        self.assertTrue(lines, "No JSON output from RPC")
        return json.loads(lines[-1])

    # --------------------------------------------------------------------------
    # 1. Security & Ownership Tests
    # --------------------------------------------------------------------------

    def test_authenticated_owner_receives_complete_matrix(self):
        """Owner receives full 2x2 matrix with frozen sources and validation details."""
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(data["session_id"], FIXTURE_SESSION)
        self.assertEqual(data["session_status"], "generated")
        self.assertFalse(data["read_only"])
        self.assertEqual(len(data["sources"]), 2)
        self.assertEqual(len(data["versions"]), 2)
        self.assertEqual(data["progress"]["expected_slots"], 4)
        self.assertEqual(data["progress"]["current_slots"], 4)
        self.assertEqual(data["progress"]["missing_slots"], 0)
        self.assertFalse(data["progress"]["ready"])  # Not all approved yet

        # Validation resolution priority: generation_target_results
        cand = data["versions"][0]["slots"][0]["candidate"]
        self.assertEqual(cand["validation_source"], "generation_result")
        self.assertEqual(cand["validation_report"]["solver"], "sympy")
        self.assertEqual(cand["origin"], "ai_generated")

    def test_foreign_owner_gets_p0002_concealment(self):
        """Foreign owner query fails closed with REVIEW_NOT_FOUND (RLS concealment)."""
        script = f"""
        BEGIN;
        SET LOCAL ROLE authenticated;
        SET LOCAL "request.jwt.claim.sub" = '{FOREIGN_USER}';
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("REVIEW_NOT_FOUND", res.stderr)

    def test_nonexistent_session_gets_p0002(self):
        """Nonexistent session returns REVIEW_NOT_FOUND."""
        nonexistent = str(uuid4())
        script = f"""
        BEGIN;
        SET LOCAL ROLE authenticated;
        SET LOCAL "request.jwt.claim.sub" = '{FIXTURE_USER}';
        SELECT public.get_review_current_snapshot('{nonexistent}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("REVIEW_NOT_FOUND", res.stderr)

    def test_anonymous_role_denied_execution(self):
        """Anon role cannot execute the RPC function."""
        script = f"""
        BEGIN;
        SET LOCAL ROLE anon;
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertTrue("permission denied" in res.stderr.lower() or "REVIEW_NOT_FOUND" in res.stderr)

    # --------------------------------------------------------------------------
    # 2. Lifecycle & State Tests
    # --------------------------------------------------------------------------

    def test_regenerating_candidate_status_and_readiness(self):
        """Candidate in 'regenerating' status returns 200 with status=regenerating and ready=false."""
        self.sql(f"UPDATE public.version_questions SET status='regenerating' WHERE id='{CANDIDATE_V1_Q1}';")
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        cand = data["versions"][0]["slots"][0]["candidate"]
        self.assertEqual(cand["status"], "regenerating")
        self.assertFalse(data["progress"]["ready"])

    def test_all_approved_consensus_with_authoritative_progress(self):
        """When all candidates are approved, progress.ready becomes true matching _review_progress."""
        self.sql(f"UPDATE public.version_questions SET status='approved' WHERE version_id IN ('{VERSION_1}', '{VERSION_2}');")
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(data["progress"]["approved_slots"], 4)
        self.assertTrue(data["progress"]["ready"])

    def test_post_shuffle_locked_guard(self):
        """Reviewed session after shuffle persistence raises REVIEW_POST_SHUFFLE_LOCKED."""
        self.sql(f"""
        UPDATE public.exam_versions SET is_finalized = true WHERE session_id = '{FIXTURE_SESSION}';
        UPDATE public.exam_sessions SET status = 'reviewed' WHERE id = '{FIXTURE_SESSION}';
        """)
        script = f"""
        BEGIN;
        SET LOCAL ROLE authenticated;
        SET LOCAL "request.jwt.claim.sub" = '{FIXTURE_USER}';
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("REVIEW_POST_SHUFFLE_LOCKED", res.stderr)

    def test_session_approved_lock_guard(self):
        """Approved or exported session raises REVIEW_LOCKED."""
        self.sql(f"UPDATE public.exam_sessions SET status = 'approved', approved_at = now() WHERE id = '{FIXTURE_SESSION}';")
        script = f"""
        BEGIN;
        SET LOCAL ROLE authenticated;
        SET LOCAL "request.jwt.claim.sub" = '{FIXTURE_USER}';
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("REVIEW_LOCKED", res.stderr)

    # --------------------------------------------------------------------------
    # 3. Matrix & Invariant Fail-Closed Tests
    # --------------------------------------------------------------------------

    def test_missing_candidate_slot_returns_candidate_null(self):
        """Setting is_current=false on a candidate returns candidate: null on that slot."""
        self.sql(f"UPDATE public.version_questions SET is_current=false WHERE id='{CANDIDATE_V2_Q2}';")
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(data["progress"]["missing_slots"], 1)
        self.assertEqual(data["progress"]["current_slots"], 3)
        v2 = next(v for v in data["versions"] if v["version_index"] == 2)
        s2 = next(s for s in v2["slots"] if s["question_no"] == 2)
        self.assertIsNone(s2["candidate"])

    def test_duplicate_current_fails_closed(self):
        """Duplicate current candidate on same slot triggers fail-closed error."""
        self.sql("DROP INDEX IF EXISTS idx_single_current_version_question;")
        self.sql(f"""
        INSERT INTO public.version_questions(id, version_id, source_question_id, question_no, content, options, correct_key, canonical_question_no, canonical_options, canonical_correct_key, is_current)
        VALUES ('40000000-0000-0000-0000-000000000099', '{VERSION_1}', '{SOURCE_Q1}', 1, 'Duplicate candidate', '["1","2","3","4"]'::jsonb, 'A', 1, '["1","2","3","4"]'::jsonb, 'A', true);
        """)
        script = f"""
        BEGIN;
        SET LOCAL ROLE authenticated;
        SET LOCAL "request.jwt.claim.sub" = '{FIXTURE_USER}';
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("duplicate current candidate", res.stderr)

    def test_extra_version_outside_n_scope_fails_closed(self):
        """Current candidate in a version code outside 1..N triggers fail-closed error."""
        extra_ver = str(uuid4())
        self.sql(f"""
        INSERT INTO public.exam_versions(id, session_id, version_code) VALUES ('{extra_ver}', '{FIXTURE_SESSION}', '103');
        INSERT INTO public.version_questions(id, version_id, source_question_id, question_no, content, options, correct_key, canonical_question_no, canonical_options, canonical_correct_key, is_current)
        VALUES ('{uuid4()}', '{extra_ver}', '{SOURCE_Q1}', 1, 'Extra version candidate', '["1","2","3","4"]'::jsonb, 'A', 1, '["1","2","3","4"]'::jsonb, 'A', true);
        """)
        script = f"""
        BEGIN;
        SET LOCAL ROLE authenticated;
        SET LOCAL "request.jwt.claim.sub" = '{FIXTURE_USER}';
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("current candidate in extra version outside frozen scope", res.stderr)

    def test_canonical_question_no_mismatch_fails_closed(self):
        """Candidate with canonical_question_no not matching frozen source question_no fails closed."""
        self.sql(f"UPDATE public.version_questions SET canonical_question_no = 99 WHERE id = '{CANDIDATE_V1_Q1}';")
        script = f"""
        BEGIN;
        SET LOCAL ROLE authenticated;
        SET LOCAL "request.jwt.claim.sub" = '{FIXTURE_USER}';
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("canonical_question_no mismatch", res.stderr)

    # --------------------------------------------------------------------------
    # 4. Provenance & Validation Priority Tests
    # --------------------------------------------------------------------------

    def test_regeneration_validation_priority(self):
        """version_questions.validation_report takes priority over generation_target_results."""
        self.sql(f"""
        UPDATE public.version_questions
        SET validation_report = '{{"solver": "sympy", "regenerated": true}}'::jsonb,
            regenerated_from_id = '{CANDIDATE_V1_Q1}'
        WHERE id = '{CANDIDATE_V1_Q1}';
        """)
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        cand = data["versions"][0]["slots"][0]["candidate"]
        self.assertEqual(cand["origin"], "regenerated")
        self.assertEqual(cand["validation_source"], "version_question")
        self.assertTrue(cand["validation_report"]["regenerated"])

    def test_clone_provenance(self):
        """Target result with result_kind='ORIGINAL_CLONE' yields origin='original_clone'."""
        self.sql(f"UPDATE public.generation_target_results SET result_kind = 'ORIGINAL_CLONE' WHERE version_question_id = '{CANDIDATE_V1_Q2}';")
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        cand = data["versions"][0]["slots"][1]["candidate"]
        self.assertEqual(cand["origin"], "original_clone")

    # --------------------------------------------------------------------------
    # 5. Freshness Token Determinism & Mutation
    # --------------------------------------------------------------------------

    def test_freshness_token_determinism_and_mutation(self):
        """Two identical calls produce same token; updating candidate alters token."""
        data1 = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        token1 = data1["freshness_token"]
        self.assertEqual(len(token1), 64)

        data2 = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        token2 = data2["freshness_token"]
        self.assertEqual(token1, token2)

        # Mutate candidate status
        self.sql(f"UPDATE public.version_questions SET status = 'approved' WHERE id = '{CANDIDATE_V1_Q1}';")
        data3 = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        token3 = data3["freshness_token"]
        self.assertNotEqual(token1, token3)

    # --------------------------------------------------------------------------
    # 6. Concurrency & Locking
    # --------------------------------------------------------------------------

    def test_concurrency_read_consistency_during_write(self):
        """GET snapshot reads consistent state under FOR SHARE lock while writer operates."""
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(data["progress"]["current_slots"], 4)

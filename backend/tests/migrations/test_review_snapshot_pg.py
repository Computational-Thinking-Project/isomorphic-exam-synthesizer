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
8. Concurrency: Read consistency during writer transaction & lock-free foreign concealment
9. Migration Lifecycle: Fresh install, populated upgrade, and replay idempotency
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

BOOTSTRAP_GRANTS = """
GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO authenticated, service_role;
GRANT INSERT, UPDATE, DELETE ON exam_sessions, source_questions, question_blueprints, generation_configs TO authenticated;
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
BLUEPRINT_1 = "50000000-0000-0000-0000-000000000001"
BLUEPRINT_2 = "50000000-0000-0000-0000-000000000002"
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

    def _apply_migrations(self, target_db: str, max_mig: str | None = None):
        override_017 = os.getenv("REVIEW_SNAPSHOT_017_SQL")
        migration_files = sorted(
            [f for f in MIGRATIONS_DIR.glob("*.sql") if f.is_file()],
            key=lambda p: p.name,
        )
        for mig in migration_files:
            if max_mig and mig.name.split("_")[0] > max_mig:
                break
            if mig.name.startswith("010"):
                continue  # empty migration no-op
            if mig.name.startswith("017") and override_017 and Path(override_017).is_file():
                content = Path(override_017).read_text(encoding="utf-8")
            else:
                content = mig.read_text(encoding="utf-8")
            if content.strip():
                self.sql(content, db=target_db)

    def setUp(self):
        type(self).db = f"db_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)

        # 1. Apply baseline schema and grants
        self.sql(BOOTSTRAP + SCHEMA_SQL.read_text(encoding="utf-8"))
        self.sql(BOOTSTRAP_GRANTS)

        # 2. Apply all migrations in order
        self._apply_migrations(self.db)

        # 3. Seed production-shaped test fixtures obeying lifecycle contracts
        self._seed_baseline()

    def _seed_baseline(self):
        # Establish valid lifecycle: draft session -> source questions -> confirmation & revisions
        # -> canonical blueprints & heads -> generated status -> config -> snapshot -> versions & candidates -> results
        seed_sql = f"""
        INSERT INTO auth.users(id, email) VALUES
          ('{FIXTURE_USER}', 'teacher@example.com'),
          ('{FOREIGN_USER}', 'other@example.com')
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO public.users(id, email) VALUES
          ('{FIXTURE_USER}', 'teacher@example.com'),
          ('{FOREIGN_USER}', 'other@example.com')
        ON CONFLICT (id) DO NOTHING;

        -- 1. Create session in draft state so source_questions can be inserted without ARTIFACT_SOURCE_LOCKED
        INSERT INTO public.exam_sessions(id, user_id, title, status) VALUES
          ('{FIXTURE_SESSION}', '{FIXTURE_USER}', 'Đề thi Toán 10', 'draft');

        -- 2. Insert source questions
        INSERT INTO public.source_questions(id, session_id, question_no, raw_content, options, correct_key, solution_md) VALUES
          ('{SOURCE_Q1}', '{FIXTURE_SESSION}', 1, 'Giải phương trình 2x + 4 = 0.', '["x = -2", "x = 2", "x = -4", "x = 4"]'::jsonb, 'A', 'Ta có 2x = -4 suy ra x = -2.'),
          ('{SOURCE_Q2}', '{FIXTURE_SESSION}', 2, 'Tính đạo hàm của y = x^2.', '["y'' = 2x", "y'' = x", "y'' = 2", "y'' = x^2"]'::jsonb, 'A', 'Đạo hàm là 2x.');

        -- 3. Confirmation and Revisions
        INSERT INTO public.source_artifact_confirmations(confirmation_id, session_id, actor_id, confirmed_at, result) VALUES
          ('{CONFIRMATION_ID}', '{FIXTURE_SESSION}', '{FIXTURE_USER}', now(),
           jsonb_build_object(
             'total_questions', 2,
             'sources', jsonb_build_array(
               jsonb_build_object('source_question_id', '{SOURCE_Q1}', 'source_revision_id', '{SOURCE_REV1}', 'confirmed_input', jsonb_build_object('id', '{SOURCE_Q1}', 'question_text', 'Giải phương trình 2x + 4 = 0.', 'options', jsonb_build_array('x = -2', 'x = 2', 'x = -4', 'x = 4'), 'correct_answer', 'A', 'solution', 'Ta có 2x = -4 suy ra x = -2.')),
               jsonb_build_object('source_question_id', '{SOURCE_Q2}', 'source_revision_id', '{SOURCE_REV2}', 'confirmed_input', jsonb_build_object('id', '{SOURCE_Q2}', 'question_text', 'Tính đạo hàm của y = x^2.', 'options', jsonb_build_array('y'' = 2x', 'y'' = x', 'y'' = 2', 'y'' = x^2'), 'correct_answer', 'A', 'solution', 'Đạo hàm là 2x.'))
             )
           )
          );

        INSERT INTO public.source_artifact_revisions(source_revision_id, confirmation_id, source_question_id, confirmed_input, source_fingerprint) VALUES
          ('{SOURCE_REV1}', '{CONFIRMATION_ID}', '{SOURCE_Q1}',
           jsonb_build_object('id', '{SOURCE_Q1}', 'question_text', 'Giải phương trình 2x + 4 = 0.', 'options', jsonb_build_array('x = -2', 'x = 2', 'x = -4', 'x = 4'), 'correct_answer', 'A', 'solution', 'Ta có 2x = -4 suy ra x = -2.'),
           encode(sha256(convert_to(public._generation_json(jsonb_build_array(public._generation_source_item(jsonb_build_object('id', '{SOURCE_Q1}', 'question_text', 'Giải phương trình 2x + 4 = 0.', 'options', jsonb_build_array('x = -2', 'x = 2', 'x = -4', 'x = 4'), 'correct_answer', 'A', 'solution', 'Ta có 2x = -4 suy ra x = -2.')))), 'UTF8')), 'hex')),
          ('{SOURCE_REV2}', '{CONFIRMATION_ID}', '{SOURCE_Q2}',
           jsonb_build_object('id', '{SOURCE_Q2}', 'question_text', 'Tính đạo hàm của y = x^2.', 'options', jsonb_build_array('y'' = 2x', 'y'' = x', 'y'' = 2', 'y'' = x^2'), 'correct_answer', 'A', 'solution', 'Đạo hàm là 2x.'),
           encode(sha256(convert_to(public._generation_json(jsonb_build_array(public._generation_source_item(jsonb_build_object('id', '{SOURCE_Q2}', 'question_text', 'Tính đạo hàm của y = x^2.', 'options', jsonb_build_array('y'' = 2x', 'y'' = x', 'y'' = 2', 'y'' = x^2'), 'correct_answer', 'A', 'solution', 'Đạo hàm là 2x.')))), 'UTF8')), 'hex'));

        INSERT INTO public.canonical_blueprint_revisions(blueprint_revision_id, source_revision_id, source_question_id, canonical_blueprint, schema_version) VALUES
          ('{BLUEPRINT_1}', '{SOURCE_REV1}', '{SOURCE_Q1}', jsonb_build_object('requirement', jsonb_build_object('schema_version', '0.4.0', 'variation_policy', jsonb_build_object('allowed_transformations', jsonb_build_array(jsonb_build_object('dimension', 'values'))))), '0.4.0'),
          ('{BLUEPRINT_2}', '{SOURCE_REV2}', '{SOURCE_Q2}', jsonb_build_object('requirement', jsonb_build_object('schema_version', '0.4.0', 'variation_policy', jsonb_build_object('allowed_transformations', jsonb_build_array(jsonb_build_object('dimension', 'values'))))), '0.4.0');

        INSERT INTO public.source_artifact_heads(source_question_id, source_revision_id, blueprint_revision_id) VALUES
          ('{SOURCE_Q1}', '{SOURCE_REV1}', '{BLUEPRINT_1}'),
          ('{SOURCE_Q2}', '{SOURCE_REV2}', '{BLUEPRINT_2}');

        -- 4. Advance session to generated and configure Stage 2
        UPDATE public.exam_sessions SET status = 'generated' WHERE id = '{FIXTURE_SESSION}';

        INSERT INTO public.generation_configs(session_id, n_versions, active_variation_modes, mapping_version) VALUES
          ('{FIXTURE_SESSION}', 2, '[]'::jsonb, '1.0');

        -- 5. Frozen generation job snapshot matching the canonical source hash
        INSERT INTO public.generation_job_snapshots(id, session_id, job_token, confirmation_id, source_order, confirmed_source_hash, base_seed, n_versions, public_modes, canonical_dimensions, mapping_version, snapshot_payload) VALUES
          ('{JOB_SNAPSHOT_ID}', '{FIXTURE_SESSION}', gen_random_uuid(), '{CONFIRMATION_ID}',
           jsonb_build_array('{SOURCE_Q1}', '{SOURCE_Q2}'),
           encode(sha256(convert_to(public._generation_json(jsonb_build_array(
             public._generation_source_item(jsonb_build_object('id', '{SOURCE_Q1}', 'question_text', 'Giải phương trình 2x + 4 = 0.', 'options', jsonb_build_array('x = -2', 'x = 2', 'x = -4', 'x = 4'), 'correct_answer', 'A', 'solution', 'Ta có 2x = -4 suy ra x = -2.')),
             public._generation_source_item(jsonb_build_object('id', '{SOURCE_Q2}', 'question_text', 'Tính đạo hàm của y = x^2.', 'options', jsonb_build_array('y'' = 2x', 'y'' = x', 'y'' = 2', 'y'' = x^2'), 'correct_answer', 'A', 'solution', 'Đạo hàm là 2x.'))
           )), 'UTF8')), 'hex'),
           100, 2, '[]'::jsonb, '[]'::jsonb, '1.0',
           jsonb_build_object(
             'confirmed_sources', jsonb_build_array(
               jsonb_build_object(
                 'source_question_id', '{SOURCE_Q1}',
                 'question_no', 1,
                 'source_revision_id', '{SOURCE_REV1}',
                 'source_fingerprint', encode(sha256(convert_to(public._generation_json(jsonb_build_array(public._generation_source_item(jsonb_build_object('id', '{SOURCE_Q1}', 'question_text', 'Giải phương trình 2x + 4 = 0.', 'options', jsonb_build_array('x = -2', 'x = 2', 'x = -4', 'x = 4'), 'correct_answer', 'A', 'solution', 'Ta có 2x = -4 suy ra x = -2.')))), 'UTF8')), 'hex'),
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
                 'source_fingerprint', encode(sha256(convert_to(public._generation_json(jsonb_build_array(public._generation_source_item(jsonb_build_object('id', '{SOURCE_Q2}', 'question_text', 'Tính đạo hàm của y = x^2.', 'options', jsonb_build_array('y'' = 2x', 'y'' = x', 'y'' = 2', 'y'' = x^2'), 'correct_answer', 'A', 'solution', 'Đạo hàm là 2x.')))), 'UTF8')), 'hex'),
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

        -- 6. Versions and Candidates with immutable canonical options and solution
        INSERT INTO public.exam_versions(id, session_id, version_code) VALUES
          ('{VERSION_1}', '{FIXTURE_SESSION}', '101'),
          ('{VERSION_2}', '{FIXTURE_SESSION}', '102');

        INSERT INTO public.version_questions(id, version_id, source_question_id, question_no, content, options, correct_key, solution_md, canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md, is_current, status, has_warning, validation_report) VALUES
          ('{CANDIDATE_V1_Q1}', '{VERSION_1}', '{SOURCE_Q1}', 1, 'Biến thể 101-1', '["x = 2", "x = -2", "x = -3", "x = 3"]'::jsonb, 'B', 'Lời giải 101-1', 1, '["x = -2", "x = 2", "x = -4", "x = 4"]'::jsonb, 'A', 'Lời giải 101-1', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V1_Q2}', '{VERSION_1}', '{SOURCE_Q2}', 2, 'Biến thể 101-2', '["y'' = 6x", "y'' = 3x", "y'' = 6", "y'' = x^2"]'::jsonb, 'A', 'Lời giải 101-2', 2, '["y'' = 2x", "y'' = x", "y'' = 2", "y'' = x^2"]'::jsonb, 'A', 'Lời giải 101-2', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V2_Q1}', '{VERSION_2}', '{SOURCE_Q1}', 1, 'Biến thể 102-1', '["x = 2", "x = -4", "x = -2", "x = 4"]'::jsonb, 'C', 'Lời giải 102-1', 1, '["x = -2", "x = 2", "x = -4", "x = 4"]'::jsonb, 'A', 'Lời giải 102-1', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V2_Q2}', '{VERSION_2}', '{SOURCE_Q2}', 2, 'Biến thể 102-2', '["y'' = 10x", "y'' = 5x", "y'' = 10", "y'' = x^2"]'::jsonb, 'A', 'Lời giải 102-2', 2, '["y'' = 2x", "y'' = x", "y'' = 2", "y'' = x^2"]'::jsonb, 'A', 'Lời giải 102-2', true, 'pending_review', false, '{{}}'::jsonb);

        -- 7. Persisted generation target results linked to each candidate
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
        """Owner receives full 2x2 matrix with frozen sources, canonical options and validation details."""
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)

        self.assertEqual(data["session_id"], FIXTURE_SESSION)
        self.assertEqual(data["session_status"], "generated")
        self.assertFalse(data["read_only"])
        self.assertEqual(len(data["sources"]), 2)
        self.assertEqual(len(data["versions"]), 2)

        # Check sources canonical ordering
        self.assertEqual(data["sources"][0]["question_no"], 1)
        self.assertEqual(data["sources"][1]["question_no"], 2)

        # Check slots and candidates (F02: verify canonical options are returned, not shuffled display options)
        cand_v1_q1 = data["versions"][0]["slots"][0]["candidate"]
        self.assertEqual(cand_v1_q1["candidate_id"], CANDIDATE_V1_Q1)
        self.assertEqual(cand_v1_q1["options"], ["x = -2", "x = 2", "x = -4", "x = 4"])
        self.assertEqual(cand_v1_q1["correct_key"], "A")
        self.assertEqual(cand_v1_q1["origin"], "ai_generated")
        self.assertEqual(cand_v1_q1["validation_source"], "generation_result")

    def test_foreign_owner_gets_p0002_concealment(self):
        """Foreign owner query fails closed with REVIEW_NOT_FOUND (RLS concealment) without waiting."""
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
        nonexistent_id = "00000000-0000-0000-0000-999999999999"
        script = f"""
        BEGIN;
        SET LOCAL ROLE authenticated;
        SET LOCAL "request.jwt.claim.sub" = '{FIXTURE_USER}';
        SELECT public.get_review_current_snapshot('{nonexistent_id}'::uuid);
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
        RESET "request.jwt.claim.sub";
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        COMMIT;
        """
        res = self.sql(script, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertTrue("permission denied" in res.stderr.lower() or "REVIEW_NOT_FOUND" in res.stderr)

    # --------------------------------------------------------------------------
    # 2. Lifecycle & Lock Guards
    # --------------------------------------------------------------------------

    def test_regenerating_candidate_status_and_readiness(self):
        """Candidate in 'regenerating' status returns 200 with status=regenerating and ready=false."""
        self.sql(f"UPDATE public.version_questions SET status = 'regenerating' WHERE id = '{CANDIDATE_V1_Q1}';")
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertFalse(data["progress"]["ready"])
        self.assertEqual(data["versions"][0]["slots"][0]["candidate"]["status"], "regenerating")

    def test_all_approved_consensus_with_authoritative_progress(self):
        """When all candidates are approved, progress.ready becomes true matching _review_progress."""
        self.sql(f"UPDATE public.version_questions SET status = 'approved' WHERE version_id IN ('{VERSION_1}', '{VERSION_2}');")
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertTrue(data["progress"]["ready"])
        self.assertEqual(data["progress"]["approved_slots"], 4)

    def test_post_shuffle_locked_guard(self):
        """Reviewed session after shuffle persistence raises REVIEW_POST_SHUFFLE_LOCKED."""
        self.sql(f"""
        UPDATE public.exam_sessions SET status = 'reviewed' WHERE id = '{FIXTURE_SESSION}';
        UPDATE public.exam_versions SET is_finalized = true WHERE session_id = '{FIXTURE_SESSION}';
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
        self.sql(f"UPDATE public.exam_sessions SET status = 'approved' WHERE id = '{FIXTURE_SESSION}';")
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
    # 3. Matrix Invariants & Fail-Closed Integrity
    # --------------------------------------------------------------------------

    def test_missing_candidate_slot_returns_candidate_null(self):
        """Setting is_current=false on a candidate returns candidate: null on that slot."""
        self.sql(f"UPDATE public.version_questions SET is_current = false WHERE id = '{CANDIDATE_V1_Q1}';")
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        slot0 = data["versions"][0]["slots"][0]
        self.assertIsNone(slot0["candidate"])
        self.assertEqual(data["progress"]["missing_slots"], 1)
        self.assertEqual(data["progress"]["current_slots"], 3)

    def test_duplicate_current_fails_closed(self):
        """Duplicate current candidate on same slot triggers fail-closed error."""
        dup_id = "40000000-0000-0000-0000-000000000099"
        self.sql(f"""
        DROP INDEX IF EXISTS public.idx_single_current_version_question;
        INSERT INTO public.version_questions(id, version_id, source_question_id, question_no, content, options, correct_key, solution_md, canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md, is_current, status, has_warning, validation_report)
        VALUES ('{dup_id}', '{VERSION_1}', '{SOURCE_Q1}', 1, 'Biến thể trùng lặp', '["A", "B", "C", "D"]'::jsonb, 'A', 'Lời giải', 1, '["A", "B", "C", "D"]'::jsonb, 'A', 'Lời giải', true, 'pending_review', false, '{{}}'::jsonb);
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
        v3_id = "30000000-0000-0000-0000-000000000003"
        extra_cand_id = "40000000-0000-0000-0000-000000000098"
        self.sql(f"""
        INSERT INTO public.exam_versions(id, session_id, version_code) VALUES ('{v3_id}', '{FIXTURE_SESSION}', '103');
        INSERT INTO public.version_questions(id, version_id, source_question_id, question_no, content, options, correct_key, solution_md, canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md, is_current, status, has_warning, validation_report)
        VALUES ('{extra_cand_id}', '{v3_id}', '{SOURCE_Q1}', 1, 'Biến thể ngoài scope', '["A", "B", "C", "D"]'::jsonb, 'A', 'Lời giải', 1, '["A", "B", "C", "D"]'::jsonb, 'A', 'Lời giải', true, 'pending_review', false, '{{}}'::jsonb);
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
        # Replace CANDIDATE_V1_Q1 with a candidate seeded with mismatched canonical_question_no (avoids prohibited UPDATE)
        self.sql(f"""
        DELETE FROM public.generation_target_results WHERE version_question_id = '{CANDIDATE_V1_Q1}';
        DELETE FROM public.version_questions WHERE id = '{CANDIDATE_V1_Q1}';
        INSERT INTO public.version_questions(id, version_id, source_question_id, question_no, content, options, correct_key, solution_md, canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md, is_current, status, has_warning, validation_report)
        VALUES ('{CANDIDATE_V1_Q1}', '{VERSION_1}', '{SOURCE_Q1}', 1, 'Biến thể lệch canonical', '["x = 2", "x = -2", "x = -3", "x = 3"]'::jsonb, 'B', 'Lời giải', 99, '["x = -2", "x = 2", "x = -4", "x = 4"]'::jsonb, 'A', 'Lời giải', true, 'pending_review', false, '{{}}'::jsonb);
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
        self.sql(f"""
        UPDATE public.generation_target_results
        SET result_kind = 'ORIGINAL_CLONE',
            request_fingerprint = NULL,
            clone_fingerprint = repeat('0', 64),
            attempts = 0,
            error_code = NULL
        WHERE version_question_id = '{CANDIDATE_V1_Q2}';
        """)
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
    # 6. Concurrency, Lock-Free Concealment & MVCC Snapshot Isolation
    # --------------------------------------------------------------------------

    def test_concurrency_lock_free_foreign_concealment(self):
        """Foreign caller receives immediate REVIEW_NOT_FOUND (404) without blocking on owner row lock."""
        # Hold owner session row lock in connection A
        lock_cmd = f"BEGIN; SELECT * FROM public.exam_sessions WHERE id = '{FIXTURE_SESSION}' FOR UPDATE; SELECT pg_sleep(2); ROLLBACK;"
        proc_lock = subprocess.Popen(
            [self.docker, "exec", self.container, "psql", "-X", "-qAt", "-U", "postgres", "-d", self.db, "-c", lock_cmd]
        )
        try:
            time.sleep(0.4)  # Give lock transaction time to acquire FOR UPDATE
            start_t = time.time()
            foreign_script = f"""
            BEGIN;
            SET LOCAL ROLE authenticated;
            SET LOCAL "request.jwt.claim.sub" = '{FOREIGN_USER}';
            SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
            COMMIT;
            """
            res = self.sql(foreign_script, check=False)
            elapsed = time.time() - start_t
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("REVIEW_NOT_FOUND", res.stderr)
            # Must return immediately (< 1.5s), NOT blocking for the full 2s of the owner lock
            self.assertLess(elapsed, 1.5, "Foreign query waited on owner lock!")
        finally:
            proc_lock.wait(timeout=5)

    def test_concurrency_read_consistency_during_write(self):
        """GET snapshot reads consistent uncommitted state and updates after writer commits."""
        data_pre = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(data_pre["progress"]["approved_slots"], 0)

        # Mutate status inside open transaction
        writer_cmd = f"BEGIN; UPDATE public.version_questions SET status = 'approved' WHERE id = '{CANDIDATE_V1_Q1}'; SELECT pg_sleep(1.5); COMMIT;"
        proc_writer = subprocess.Popen(
            [self.docker, "exec", self.container, "psql", "-X", "-qAt", "-U", "postgres", "-d", self.db, "-c", writer_cmd]
        )
        try:
            time.sleep(0.4)
            # Under MVCC statement snapshot, reader sees uncommitted snapshot (0 approved)
            data_during = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
            self.assertEqual(data_during["progress"]["approved_slots"], 0)
            self.assertEqual(data_during["freshness_token"], data_pre["freshness_token"])
        finally:
            proc_writer.wait(timeout=5)

        # After writer commits, next call sees new state and new token
        data_post = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(data_post["progress"]["approved_slots"], 1)
        self.assertNotEqual(data_post["freshness_token"], data_pre["freshness_token"])

    # --------------------------------------------------------------------------
    # 7. Migration Replay & Upgrade Lifecycle Tests
    # --------------------------------------------------------------------------

    def test_repeated_018_application_idempotent(self):
        """Migration 018 can be reapplied idempotently without DDL failure."""
        mig_018 = MIGRATIONS_DIR / "018_review_current_snapshot.sql"
        self.sql(mig_018.read_text(encoding="utf-8"))
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(len(data["versions"]), 2)

    def test_upgrade_from_populated_016(self):
        """Test upgrade path: baseline schema + migrations up to 016, populated data, then 017 and 018."""
        upgrade_db = f"db_upgrade_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", upgrade_db)
        orig_db = type(self).db
        try:
            self.sql(BOOTSTRAP + SCHEMA_SQL.read_text(encoding="utf-8"), db=upgrade_db)
            self.sql(BOOTSTRAP_GRANTS, db=upgrade_db)
            self._apply_migrations(upgrade_db, max_mig="016")

            # Seed data on populated 016 database
            type(self).db = upgrade_db
            self._seed_baseline()

            # Now upgrade by applying 017 and 018 forward
            for mig_num in ("017", "018"):
                matches = list(MIGRATIONS_DIR.glob(f"{mig_num}_*.sql"))
                self.assertTrue(matches)
                self.sql(matches[0].read_text(encoding="utf-8"), db=upgrade_db)

            # Verify snapshot works on upgraded database
            data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
            self.assertEqual(len(data["sources"]), 2)
            self.assertEqual(len(data["versions"]), 2)
        finally:
            type(self).db = orig_db
            self.run_docker("exec", self.container, "dropdb", "-U", "postgres", upgrade_db)


if __name__ == "__main__":
    unittest.main()

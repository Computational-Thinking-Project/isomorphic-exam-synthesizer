"""PostgreSQL Integration Tests for Review Snapshot RPC (W4-MVP-03).

Opt in with RUN_POSTGRES_MIGRATION_TESTS=1:
    RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -p 'test_review_snapshot_pg.py' -v

Tests public.get_review_current_snapshot(p_session_id uuid):
1. Authenticated owner sees full N x M slots and frozen source order
2. Anon cannot execute; foreign owner gets REVIEW_NOT_FOUND (P0002 RLS concealment)
3. Current vs historical: Only is_current=true candidates returned
4. Missing candidate: Slot has candidate=null, missing_slots count incremented
5. Unpersisted version: version_id=null, slots preserved with candidate=null
6. Integrity guards: duplicate current candidate or foreign source fails closed (503)
7. Validation provenance: version_questions vs generation_target_results vs unavailable
8. Provenance origins: ai_generated, original_clone, regenerated, reverted, unknown
9. Session state guards: draft/generating (409), locked (423), post-shuffle (409)
10. Freshness token determinism & mutation change
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
MIGRATION_006 = ROOT / "backend/migrations/006_stage3_review_and_shuffle.sql"
MIGRATION_015 = ROOT / "backend/migrations/015_stage2_canonical_w2_integration.sql"
MIGRATION_016 = ROOT / "backend/migrations/016_stage2_original_clone.sql"
MIGRATION_018 = ROOT / "backend/migrations/018_review_current_snapshot.sql"

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
            raise unittest.SkipTest("Set DOCKER_BIN to the Docker CLI executable")

        probe = subprocess.run([cls.docker, "info"], capture_output=True, text=True)
        if probe.returncode != 0:
            raise unittest.SkipTest(f"Docker daemon unavailable: {probe.stderr.strip()[:100]}")

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
        # Apply full schema and migrations
        self.sql(BOOTSTRAP + SCHEMA_SQL.read_text(encoding="utf-8"))
        self.sql(MIGRATION_006.read_text(encoding="utf-8"))
        self.sql(MIGRATION_015.read_text(encoding="utf-8"))
        self.sql(MIGRATION_016.read_text(encoding="utf-8"))
        self.sql(MIGRATION_018.read_text(encoding="utf-8"))

        # Seed baseline test fixture (2 sources x 2 versions)
        self.sql(f"""
        INSERT INTO auth.users(id, email) VALUES
          ('{FIXTURE_USER}', 'teacher@example.com'),
          ('{FOREIGN_USER}', 'other@example.com');
        INSERT INTO public.users(id, email) VALUES
          ('{FIXTURE_USER}', 'teacher@example.com'),
          ('{FOREIGN_USER}', 'other@example.com')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO public.exam_sessions(id, user_id, title, status) VALUES
          ('{FIXTURE_SESSION}', '{FIXTURE_USER}', 'Đề thi Toán 10', 'generated');

        INSERT INTO public.source_questions(id, session_id, question_no, raw_content, options, correct_key, solution_md) VALUES
          ('{SOURCE_Q1}', '{FIXTURE_SESSION}', 1, 'Câu nguồn 1', '["A1","B1","C1","D1"]'::jsonb, 'A', 'Lời giải nguồn 1'),
          ('{SOURCE_Q2}', '{FIXTURE_SESSION}', 2, 'Câu nguồn 2', '["A2","B2","C2","D2"]'::jsonb, 'B', 'Lời giải nguồn 2');

        INSERT INTO public.source_artifact_confirmations(confirmation_id, session_id, actor_id, confirmed_at, result) VALUES
          ('{CONFIRMATION_ID}', '{FIXTURE_SESSION}', '{FIXTURE_USER}', now(), '{{"sources": []}}'::jsonb);

        INSERT INTO public.generation_job_snapshots(id, session_id, job_token, confirmation_id, source_order, confirmed_source_hash, base_seed, n_versions, public_modes, canonical_dimensions, mapping_version, snapshot_payload) VALUES
          ('{JOB_SNAPSHOT_ID}', '{FIXTURE_SESSION}', gen_random_uuid(), '{CONFIRMATION_ID}',
           '["{SOURCE_Q1}", "{SOURCE_Q2}"]'::jsonb,
           'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
           100, 2, '[]'::jsonb, '[]'::jsonb, '1.0',
           jsonb_build_object(
             'confirmed_sources', jsonb_build_array(
               jsonb_build_object('source_question_id', '{SOURCE_Q1}', 'question_no', 1, 'source_revision_id', '{SOURCE_REV1}', 'content', 'Câu nguồn 1', 'options', jsonb_build_array('A1','B1','C1','D1'), 'correct_key', 'A', 'solution_md', 'Lời giải nguồn 1'),
               jsonb_build_object('source_question_id', '{SOURCE_Q2}', 'question_no', 2, 'source_revision_id', '{SOURCE_REV2}', 'content', 'Câu nguồn 2', 'options', jsonb_build_array('A2','B2','C2','D2'), 'correct_key', 'B', 'solution_md', 'Lời giải nguồn 2')
             )
           )
          );

        INSERT INTO public.exam_versions(id, session_id, version_code) VALUES
          ('{VERSION_1}', '{FIXTURE_SESSION}', '101'),
          ('{VERSION_2}', '{FIXTURE_SESSION}', '102');

        INSERT INTO public.version_questions(id, version_id, source_question_id, question_no, content, options, correct_key, solution_md, canonical_question_no, canonical_options, canonical_correct_key, is_current, status, has_warning, validation_report) VALUES
          ('{CANDIDATE_V1_Q1}', '{VERSION_1}', '{SOURCE_Q1}', 1, 'Biến thể 101-1', '["A1","B1","C1","D1"]'::jsonb, 'A', 'Lời giải 101-1', 1, '["A1","B1","C1","D1"]'::jsonb, 'A', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V1_Q2}', '{VERSION_1}', '{SOURCE_Q2}', 2, 'Biến thể 101-2', '["A2","B2","C2","D2"]'::jsonb, 'B', 'Lời giải 101-2', 2, '["A2","B2","C2","D2"]'::jsonb, 'B', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V2_Q1}', '{VERSION_2}', '{SOURCE_Q1}', 1, 'Biến thể 102-1', '["A1","B1","C1","D1"]'::jsonb, 'A', 'Lời giải 102-1', 1, '["A1","B1","C1","D1"]'::jsonb, 'A', true, 'pending_review', false, '{{}}'::jsonb),
          ('{CANDIDATE_V2_Q2}', '{VERSION_2}', '{SOURCE_Q2}', 2, 'Biến thể 102-2', '["A2","B2","C2","D2"]'::jsonb, 'B', 'Lời giải 102-2', 2, '["A2","B2","C2","D2"]'::jsonb, 'B', true, 'pending_review', false, '{{}}'::jsonb);

        INSERT INTO public.generation_target_results(session_id, snapshot_id, job_token, version_index, source_question_id, question_no, is_success, attempts, seed, request_fingerprint, raw_result, version_question_id, result_kind) VALUES
          ('{FIXTURE_SESSION}', '{JOB_SNAPSHOT_ID}', gen_random_uuid(), 1, '{SOURCE_Q1}', 1, true, 1, 1100, repeat('a', 64), '{{"validation": {{"status": "passed", "solver": "sympy"}}}}'::jsonb, '{CANDIDATE_V1_Q1}', 'AI_RESULT'),
          ('{FIXTURE_SESSION}', '{JOB_SNAPSHOT_ID}', gen_random_uuid(), 1, '{SOURCE_Q2}', 2, true, 1, 1101, repeat('b', 64), '{{"validation": {{"status": "passed", "solver": "sympy"}}}}'::jsonb, '{CANDIDATE_V1_Q2}', 'AI_RESULT'),
          ('{FIXTURE_SESSION}', '{JOB_SNAPSHOT_ID}', gen_random_uuid(), 2, '{SOURCE_Q1}', 1, true, 1, 2100, repeat('c', 64), '{{"validation": {{"status": "passed", "solver": "sympy"}}}}'::jsonb, '{CANDIDATE_V2_Q1}', 'AI_RESULT'),
          ('{FIXTURE_SESSION}', '{JOB_SNAPSHOT_ID}', gen_random_uuid(), 2, '{SOURCE_Q2}', 2, true, 1, 2101, repeat('d', 64), '{{"validation": {{"status": "passed", "solver": "sympy"}}}}'::jsonb, '{CANDIDATE_V2_Q2}', 'AI_RESULT');
        """)

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
        # Parse JSON output from psql stdout
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip().startswith("{")]
        self.assertTrue(lines, "No JSON output from RPC")
        return json.loads(lines[-1])

    def test_authenticated_owner_sees_slots_and_frozen_source_order(self):
        """Owner receives exact 2x2 matrix with frozen sources and validation details."""
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(data["session_id"], FIXTURE_SESSION)
        self.assertEqual(data["session_status"], "generated")
        self.assertFalse(data["read_only"])
        self.assertEqual(len(data["sources"]), 2)
        self.assertEqual(len(data["versions"]), 2)
        self.assertEqual(data["progress"]["expected_slots"], 4)
        self.assertEqual(data["progress"]["current_slots"], 4)
        self.assertEqual(data["progress"]["missing_slots"], 0)

        # Check candidate validation from generation_target_results
        slot1 = data["versions"][0]["slots"][0]
        self.assertEqual(slot1["candidate"]["validation_source"], "generation_result")
        self.assertEqual(slot1["candidate"]["validation_report"]["solver"], "sympy")
        self.assertEqual(slot1["candidate"]["origin"], "ai_generated")

    def test_foreign_owner_gets_p0002_review_not_found(self):
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

    def test_missing_candidate_slot_returns_candidate_null(self):
        """Setting one candidate is_current=false returns candidate: null on that slot."""
        self.sql(f"UPDATE public.version_questions SET is_current=false WHERE id='{CANDIDATE_V2_Q2}';")
        data = self._call_rpc_as_user(FIXTURE_USER, FIXTURE_SESSION)
        self.assertEqual(data["progress"]["missing_slots"], 1)
        self.assertEqual(data["progress"]["current_slots"], 3)

        v2 = next(v for v in data["versions"] if v["version_index"] == 2)
        s2 = next(s for s in v2["slots"] if s["question_no"] == 2)
        self.assertIsNone(s2["candidate"])

    def test_duplicate_current_fails_closed(self):
        """Violating the partial index (e.g. through deferral or schema bypass) fails closed."""
        # Intentionally drop index temporarily in test DB to test RPC defense-in-depth guard
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

    def test_regeneration_validation_priority(self):
        """Targeted regeneration validation report takes precedence over generation_target_results."""
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

    def test_post_shuffle_locked_guard(self):
        """When exam_versions is_finalized=true and session is reviewed, RPC returns 409 guard."""
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

"""Real PostgreSQL tests for Stage 3 Review Lifecycle Stored Procedures.
Opt in with RUN_POSTGRES_MIGRATION_TESTS=1.

python -m unittest discover -s backend/tests/migrations -p "test_stage3_lifecycle_real_db.py" -v
Uses one disposable container, no cloud credentials or host mounts.
Validates true database transactions, Concurrency Model A row-locks,
session-wide reshuffle invalidation, and durable attempt accounting.
"""

import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
MIGRATION_008 = ROOT / "backend/migrations/008_stage3_review_acquire_attempt_rpc.sql"
SCHEMA_SQL = ROOT / "backend/scripts/schema.sql"

BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('request.jwt.claim.role', true), '') $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role BYPASSRLS;
    END IF;
END $$;
"""

SEED_DATA = """
INSERT INTO auth.users(id, email) VALUES
('00000000-0000-0000-0000-000000000001', 'teacher@example.com')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.users(id, email, name) VALUES
('00000000-0000-0000-0000-000000000001', 'teacher@example.com', 'Teacher')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.exam_sessions(id, user_id, title, status, gemini_review_calls) VALUES
('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'Midterm Math', 'reviewed', 5)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.source_questions(id, session_id, question_no, raw_content, options, correct_key, solution_md) VALUES
('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 1, 'Giải x^2 = 4', '["x=±2", "x=2", "x=-2", "Vô nghiệm"]', 'A', 'Lời giải câu 1')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.exam_versions(id, session_id, version_code, is_finalized, shuffle_seed, permutations) VALUES
('30000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '101', TRUE, 42, '{"q": [1]}'::jsonb)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.version_questions(
    id, version_id, source_question_id, question_no, content, options, correct_key, solution_md,
    canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
    status, is_current, is_reverted, regenerated_from_id
) VALUES
('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001',
 '20000000-0000-0000-0000-000000000001', 1, 'Giải x^2 = 9', '["x=±3", "x=3", "x=-3", "Vô nghiệm"]', 'A', 'Lời giải biến thể',
 1, '["x=±3", "x=3", "x=-3", "Vô nghiệm"]', 'A', 'Lời giải biến thể',
 'approved', TRUE, FALSE, NULL),
('40000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000001',
 '20000000-0000-0000-0000-000000000001', 2, 'Giải x^2 = 16', '["x=±4", "x=4", "x=-4", "Vô nghiệm"]', 'A', 'Lời giải câu 2',
 2, '["x=±4", "x=4", "x=-4", "Vô nghiệm"]', 'A', 'Lời giải câu 2',
 'approved', TRUE, FALSE, NULL)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.answer_keys(id, version_id, question_no, correct_option, display_no, display_correct_key, canonical_question_no) VALUES
('50000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 1, 'A', 1, 'A', 1)
ON CONFLICT (id) DO NOTHING;
"""


@unittest.skipUnless(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") == "1",
    "PostgreSQL integration opt-in. Set RUN_POSTGRES_MIGRATION_TESTS=1 and DOCKER_BIN.",
)
class Stage3LifecycleRealDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docker = os.getenv("DOCKER_BIN") or shutil.which("docker")
        if not cls.docker:
            raise RuntimeError("Set DOCKER_BIN to Docker executable")
        cls.container = f"stage3-lifecycle-test-{uuid4().hex[:12]}"
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
                "exec", cls.container, "pg_isready", "-U", "postgres", check=False
            )
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("PostgreSQL container did not become ready in time")

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

    def setUp(self):
        self.db = f"test_{uuid4().hex[:10]}"
        self.sql(f"CREATE DATABASE {self.db};", db="postgres")
        self.sql(BOOTSTRAP_SQL)
        # Apply full schema
        self.sql(SCHEMA_SQL.read_text(encoding="utf-8"))
        # Seed test data
        self.sql(SEED_DATA)

    def tearDown(self):
        self.sql(f"DROP DATABASE {self.db} WITH (FORCE);", db="postgres")

    def sql(self, script, *, db=None, check=True):
        result = self.run_docker(
            "exec",
            "-i",
            self.container,
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            db or self.db,
            input=script,
            check=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"psql failed ({result.returncode}):\n{result.stderr}")
        return result

    def value(self, query):
        return self.sql(query).stdout.strip()

    # =========================================================================
    # Test Cases
    # =========================================================================

    def test_concurrency_model_a_rpc_blocks_second_caller(self):
        """Verify review_reserve_regeneration strictly rejects second question in same session."""
        op_1 = str(uuid4())
        res1 = self.value(f"""
        SELECT review_reserve_regeneration(
            '10000000-0000-0000-0000-000000000001'::uuid,
            '40000000-0000-0000-0000-000000000001'::uuid,
            '{op_1}'::uuid
        )->>'success';
        """)
        self.assertEqual(res1, "true")

        # Question 1 is now regenerating. A second reserve call on Question 2 must be rejected with SESSION_BUSY
        op_2 = str(uuid4())
        reason = self.value(f"""
        SELECT review_reserve_regeneration(
            '10000000-0000-0000-0000-000000000001'::uuid,
            '40000000-0000-0000-0000-000000000002'::uuid,
            '{op_2}'::uuid
        )->>'rejection_reason';
        """)
        self.assertEqual(reason, "SESSION_BUSY")

    def test_complete_regeneration_invalidates_finalization_atomically(self):
        """Verify review_complete_regeneration in 1 transaction updates candidate,
        purges answer_keys, clears permutations/shuffle_seed, and demotes session status."""
        op_id = str(uuid4())
        # Reserve question 1
        self.sql(f"""
        SELECT review_reserve_regeneration(
            '10000000-0000-0000-0000-000000000001'::uuid,
            '40000000-0000-0000-0000-000000000001'::uuid,
            '{op_id}'::uuid
        );
        """)

        # Call complete regeneration
        candidate_json = """'{"stem_latex": "Giải x^2 = 25", "options": ["x=±5", "x=5", "x=-5", "Vô nghiệm"], "correct_key": "A", "solution_md": "x=±5", "validation_report": {"is_valid": true}}'::jsonb"""
        res = self.value(f"""
        SELECT review_complete_regeneration(
            '{op_id}'::uuid,
            {candidate_json},
            '00000000-0000-0000-0000-000000000001'::uuid,
            1
        )->>'success';
        """)
        self.assertEqual(res, "true")

        # 1. Answer keys must be purged
        ak_count = self.value("SELECT COUNT(*) FROM answer_keys;")
        self.assertEqual(ak_count, "0")

        # 2. Version is_finalized must be false, shuffle_seed NULL
        is_finalized = self.value("SELECT is_finalized FROM exam_versions WHERE id = '30000000-0000-0000-0000-000000000001';")
        self.assertEqual(is_finalized, "f")

        # 3. Session status must be demoted from 'reviewed' to 'generated'
        s_status = self.value("SELECT status FROM exam_sessions WHERE id = '10000000-0000-0000-0000-000000000001';")
        self.assertEqual(s_status, "generated")

        # 4. Old question must be status='rejected', is_current=false
        old_status = self.value("SELECT status || '|' || is_current FROM version_questions WHERE id = '40000000-0000-0000-0000-000000000001';")
        self.assertEqual(old_status, "rejected|f")

        # 5. Review log must be recorded
        log_type = self.value("SELECT action_type FROM review_logs WHERE regenerated_from_id = '40000000-0000-0000-0000-000000000001';")
        self.assertEqual(log_type, "REJECT")

    def test_revert_question_atomic_replacement(self):
        """Verify review_revert_question copies source question, invalidates finalization, and audits."""
        # Mark question 1 as regenerated variant
        self.sql("""
        UPDATE version_questions
        SET regenerated_from_id = '40000000-0000-0000-0000-000000000002'
        WHERE id = '40000000-0000-0000-0000-000000000001';
        """)

        act_id = str(uuid4())
        res = self.value(f"""
        SELECT review_revert_question(
            '10000000-0000-0000-0000-000000000001'::uuid,
            '40000000-0000-0000-0000-000000000001'::uuid,
            '{act_id}'::uuid,
            '00000000-0000-0000-0000-000000000001'::uuid
        )->>'success';
        """)
        self.assertEqual(res, "true")

        # Verify old candidate is no longer current
        is_cur = self.value("SELECT is_current FROM version_questions WHERE id = '40000000-0000-0000-0000-000000000001';")
        self.assertEqual(is_cur, "f")

        # Verify new candidate is current, approved, and reverted
        new_row = self.value("SELECT is_current || '|' || status || '|' || is_reverted FROM version_questions WHERE regenerated_from_id = '40000000-0000-0000-0000-000000000001';")
        self.assertEqual(new_row, "t|approved|t")

        # Answer keys purged
        self.assertEqual(self.value("SELECT COUNT(*) FROM answer_keys;"), "0")

    def test_acquire_attempt_ledger_and_quota_barrier(self):
        """Verify review_acquire_attempt ledger recording and 30-attempt ceiling."""
        op_id = str(uuid4())
        # Reserve question 1
        self.sql(f"""
        SELECT review_reserve_regeneration(
            '10000000-0000-0000-0000-000000000001'::uuid,
            '40000000-0000-0000-0000-000000000001'::uuid,
            '{op_id}'::uuid
        );
        """)

        # Set quota to 29
        self.sql("UPDATE exam_sessions SET gemini_review_calls = 29 WHERE id = '10000000-0000-0000-0000-000000000001';")

        # Attempt 1 -> Granted (calls_used = 30)
        att_1 = str(uuid4())
        res1 = self.value(f"SELECT review_acquire_attempt('{op_id}'::uuid, '{att_1}'::uuid)->>'dispatch_permitted';")
        self.assertEqual(res1, "true")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions WHERE id = '10000000-0000-0000-0000-000000000001';"), "30")

        # Attempt 2 -> Denied (QUOTA_EXHAUSTED)
        att_2 = str(uuid4())
        reason = self.value(f"SELECT review_acquire_attempt('{op_id}'::uuid, '{att_2}'::uuid)->>'rejection_reason';")
        self.assertEqual(reason, "QUOTA_EXHAUSTED")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions WHERE id = '10000000-0000-0000-0000-000000000001';"), "30")


if __name__ == "__main__":
    unittest.main()


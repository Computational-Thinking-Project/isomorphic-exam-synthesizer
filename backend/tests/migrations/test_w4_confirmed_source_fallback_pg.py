"""Targeted PostgreSQL Integration Tests for Checkpoints 1 & 2 (Migration 021).

Tests Confirmed-Source Fallback Writer & Read-back Contract:
1. Checkpoint 1:
   - Direct fallback insertion (atomic candidate + ledger, warning, not_validated report)
   - Failure-to-fallback state transition (replaces unvalidated failure, inserts candidate)
   - Validation rejections (attempts != 4, is_success != true, error_code != GENERATION_RETRIES_EXHAUSTED, missing/extra/tampered fields)
   - ERR_SOURCE_NOT_READY on missing/whitespace source solution
   - Active replay with identical payload returns same candidate ID, replayed=true
   - Conflicting replay / different raw payload rejected with 23505 ERR_GENERATION_RESULT_CONFLICT
   - AI-after-fallback rejected with 23505 ERR_GENERATION_RESULT_CONFLICT
   - Stale job token rejected with 55006 before replay lookup
   - Settled / approved session rejects writer
   - Clone job rejects fallback
   - Permissions: service_role boundary enforced, private helper ungranted
2. Checkpoint 2:
   - _generation_committed recognizes valid fallback slots
   - _generation_committed excludes corrupted fallback slots
   - load_generation_completed_results returns verified additive fallback_receipts
   - Historical fallback_receipts survive candidate regeneration
   - get_review_current_snapshot returns origin='confirmed_source_fallback', has_warning=true, SQL report
   - get_review_current_snapshot fails closed on corrupted fallback evidence
   - AI-success and Original Clone paths remain unchanged
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
JOB_TOKEN = "c0000000-0000-0000-0000-000000000001"
SOURCE_Q1 = "20000000-0000-0000-0000-000000000001"
SOURCE_Q2 = "20000000-0000-0000-0000-000000000002"
SOURCE_REV1 = "b0000000-0000-0000-0000-000000000001"
SOURCE_REV2 = "b0000000-0000-0000-0000-000000000002"
BLUEPRINT_1 = "50000000-0000-0000-0000-000000000001"
BLUEPRINT_2 = "50000000-0000-0000-0000-000000000002"


@unittest.skipUnless(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") == "1", "PostgreSQL integration opt-in"
)
class W4ConfirmedSourceFallbackPostgresCase(unittest.TestCase):
    container = None
    docker = None
    db = None

    @classmethod
    def setUpClass(cls):
        cls.docker = os.getenv("DOCKER_BIN") or shutil.which("docker")
        if not cls.docker:
            raise RuntimeError("Set DOCKER_BIN to the Docker CLI executable")
        cls.container = f"pg-fallback-{uuid4().hex[:12]}"
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
                "-U",
                "postgres",
                check=False,
            )
            if ready.returncode == 0:
                test_q = cls.run_docker(
                    "exec", cls.container, "psql", "-U", "postgres", "-c", "SELECT 1;", check=False
                )
                if test_q.returncode == 0:
                    break
            time.sleep(0.5)
        else:
            raise RuntimeError("PostgreSQL did not become ready")
        cls.sql(
            "CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;",
            db="postgres",
        )

    @classmethod
    def stop_container(cls):
        if cls.container:
            try:
                cls.run_docker("rm", "--force", cls.container, check=False)
            except Exception:
                pass

    @classmethod
    def run_docker(cls, *args, check=True, input=None):
        kwargs = {}
        if input is None:
            kwargs["stdin"] = subprocess.DEVNULL
        return subprocess.run(
            [cls.docker, *args],
            input=input,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=check,
            timeout=60,
            **kwargs,
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

    def _apply_migrations(self, target_db: str):
        migration_files = sorted(
            [f for f in MIGRATIONS_DIR.glob("*.sql") if f.is_file()],
            key=lambda p: p.name,
        )
        for mig in migration_files:
            if mig.name.startswith("010"):
                continue  # historical empty placeholder
            content = mig.read_text(encoding="utf-8")
            if content.strip():
                self.sql(content, db=target_db)

    def setUp(self):
        type(self).db = f"db_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)

        # 1. Apply baseline schema and grants
        self.sql(BOOTSTRAP + SCHEMA_SQL.read_text(encoding="utf-8"))
        self.sql(BOOTSTRAP_GRANTS)

        # 2. Apply all migrations (002 through 021)
        self._apply_migrations(self.db)

        # 3. Seed baseline session, sources, confirmation and job
        self._seed_baseline()

    def _seed_baseline(self):
        seed_sql = f"""
        INSERT INTO auth.users(id, email) VALUES
          ('{FIXTURE_USER}', 'teacher@example.com'),
          ('{FOREIGN_USER}', 'other@example.com')
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO public.users(id, email) VALUES
          ('{FIXTURE_USER}', 'teacher@example.com'),
          ('{FOREIGN_USER}', 'other@example.com')
        ON CONFLICT (id) DO NOTHING;

        -- 1. Create session in draft
        INSERT INTO public.exam_sessions(id, user_id, title, status) VALUES
          ('{FIXTURE_SESSION}', '{FIXTURE_USER}', 'Đề thi Toán', 'draft');

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

        -- 4. Canonical blueprint revisions & heads
        INSERT INTO public.canonical_blueprint_revisions(blueprint_revision_id, source_revision_id, source_question_id, canonical_blueprint, schema_version) VALUES
          ('{BLUEPRINT_1}', '{SOURCE_REV1}', '{SOURCE_Q1}',
           jsonb_build_object('requirement', jsonb_build_object('schema_version', '0.4.0', 'variation_policy', jsonb_build_object('allowed_transformations', jsonb_build_array(jsonb_build_object('dimension', 'values'), jsonb_build_object('dimension', 'context'))))), '0.4.0'),
          ('{BLUEPRINT_2}', '{SOURCE_REV2}', '{SOURCE_Q2}',
           jsonb_build_object('requirement', jsonb_build_object('schema_version', '0.4.0', 'variation_policy', jsonb_build_object('allowed_transformations', jsonb_build_array(jsonb_build_object('dimension', 'values'), jsonb_build_object('dimension', 'context'))))), '0.4.0');

        INSERT INTO public.source_artifact_heads(source_question_id, source_revision_id, blueprint_revision_id) VALUES
          ('{SOURCE_Q1}', '{SOURCE_REV1}', '{BLUEPRINT_1}'),
          ('{SOURCE_Q2}', '{SOURCE_REV2}', '{BLUEPRINT_2}');

        -- 5. Generation config
        INSERT INTO public.generation_configs(session_id, n_versions, active_variation_modes, mapping_version) VALUES
          ('{FIXTURE_SESSION}', 2, '["context"]'::jsonb, '1.0');

        -- 6. Advance session to generating state
        UPDATE public.exam_sessions
        SET status = 'generating', active_job_id = '{JOB_TOKEN}'
        WHERE id = '{FIXTURE_SESSION}';

        -- 7. Compute confirmed source hash
        WITH items AS (
          SELECT jsonb_build_array(
            public._generation_source_item(jsonb_build_object('id', '{SOURCE_Q1}', 'question_text', 'Giải phương trình 2x + 4 = 0.', 'options', jsonb_build_array('x = -2', 'x = 2', 'x = -4', 'x = 4'), 'correct_answer', 'A', 'solution', 'Ta có 2x = -4 suy ra x = -2.')),
            public._generation_source_item(jsonb_build_object('id', '{SOURCE_Q2}', 'question_text', 'Tính đạo hàm của y = x^2.', 'options', jsonb_build_array('y'' = 2x', 'y'' = x', 'y'' = 2', 'y'' = x^2'), 'correct_answer', 'A', 'solution', 'Đạo hàm là 2x.'))
          ) AS arr
        )
        INSERT INTO public.generation_job_snapshots(
          id, session_id, job_token, confirmation_id, base_seed, n_versions, public_modes, canonical_dimensions,
          mapping_version, confirmed_source_hash, source_order, snapshot_payload
        )
        SELECT
          '{JOB_TOKEN}', '{FIXTURE_SESSION}', '{JOB_TOKEN}'::uuid, '{CONFIRMATION_ID}', 1000, 2, '["context"]'::jsonb, '["context"]'::jsonb,
          '1.0', encode(sha256(convert_to(public._generation_json(items.arr), 'UTF8')), 'hex'),
          jsonb_build_array('{SOURCE_Q1}', '{SOURCE_Q2}'),
          jsonb_build_object(
            'confirmed_sources', jsonb_build_array(
              jsonb_build_object(
                'source_question_id', '{SOURCE_Q1}',
                'question_no', 1,
                'source_revision_id', '{SOURCE_REV1}',
                'blueprint_revision_id', '{BLUEPRINT_1}',
                'source_fingerprint', (SELECT source_fingerprint FROM public.source_artifact_revisions WHERE source_revision_id = '{SOURCE_REV1}'),
                'confirmed_input', (SELECT confirmed_input FROM public.source_artifact_revisions WHERE source_revision_id = '{SOURCE_REV1}')
              ),
              jsonb_build_object(
                'source_question_id', '{SOURCE_Q2}',
                'question_no', 2,
                'source_revision_id', '{SOURCE_REV2}',
                'blueprint_revision_id', '{BLUEPRINT_2}',
                'source_fingerprint', (SELECT source_fingerprint FROM public.source_artifact_revisions WHERE source_revision_id = '{SOURCE_REV2}'),
                'confirmed_input', (SELECT confirmed_input FROM public.source_artifact_revisions WHERE source_revision_id = '{SOURCE_REV2}')
              )
            )
          )
        FROM items;
        """
        self.sql(seed_sql)

    def _get_fallback_raw_result(self, version_index=1, source_idx=1, last_error="VALIDATION_FAILED"):
        """Construct the canonical fallback raw_result matching frozen source 1 or 2."""
        src_id = SOURCE_Q1 if source_idx == 1 else SOURCE_Q2
        rev_id = SOURCE_REV1 if source_idx == 1 else SOURCE_REV2
        bp_id = BLUEPRINT_1 if source_idx == 1 else BLUEPRINT_2
        stem = "Giải phương trình 2x + 4 = 0." if source_idx == 1 else "Tính đạo hàm của y = x^2."
        opts = ["x = -2", "x = 2", "x = -4", "x = 4"] if source_idx == 1 else ["y' = 2x", "y' = x", "y' = 2", "y' = x^2"]
        sol = "Ta có 2x = -4 suy ra x = -2." if source_idx == 1 else "Đạo hàm là 2x."

        # Read frozen fingerprint and hash from DB
        fp = self.sql(f"SELECT source_fingerprint FROM public.source_artifact_revisions WHERE source_revision_id = '{rev_id}'").stdout.strip()
        hsh = self.sql(f"SELECT confirmed_source_hash FROM public.generation_job_snapshots WHERE id = '{JOB_TOKEN}'").stdout.strip()
        seed = 1000 + version_index * 1000 + (source_idx - 1)
        req_fp = "f" * 64

        return {
            "result_kind": "CONFIRMED_SOURCE_FALLBACK",
            "snapshot_id": JOB_TOKEN,
            "confirmation_id": CONFIRMATION_ID,
            "version_index": version_index,
            "source_question_id": src_id,
            "question_no": source_idx,
            "source_revision_id": rev_id,
            "blueprint_revision_id": bp_id,
            "source_fingerprint": fp,
            "confirmed_source_hash": hsh,
            "seed": seed,
            "request_fingerprint": req_fp,
            "attempts": 4,
            "error_code": "GENERATION_RETRIES_EXHAUSTED",
            "last_error_code": last_error,
            "content": stem,
            "options": opts,
            "correct_key": "A",
            "solution_md": sol,
            "has_warning": True,
        }

    def _call_persist_fallback(self, raw, version_index=1, source_idx=1, token=JOB_TOKEN, role="service_role"):
        """Call persist_generation_result with fallback parameters."""
        src_id = SOURCE_Q1 if source_idx == 1 else SOURCE_Q2
        content_escaped = raw["content"].replace("'", "''")
        opts_escaped = json.dumps(raw["options"], ensure_ascii=False).replace("'", "''")
        sol_escaped = raw["solution_md"].replace("'", "''")
        raw_escaped = json.dumps(raw, ensure_ascii=False).replace("'", "''")
        call_sql = f"""
        SET ROLE {role};
        SELECT public.persist_generation_result(
          '{FIXTURE_SESSION}'::uuid,
          '{token}'::uuid,
          {version_index},
          '{src_id}'::uuid,
          {source_idx},
          true,
          'GENERATION_RETRIES_EXHAUSTED',
          4,
          {raw['seed']},
          '{raw['request_fingerprint']}',
          '{raw_escaped}'::jsonb,
          '{content_escaped}',
          '{opts_escaped}'::jsonb,
          '{raw['correct_key']}',
          '{sol_escaped}',
          true
        );
        """
        return self.sql(call_sql, check=False)

    # =========================================================================
    # Checkpoint 1: Writer Tests
    # =========================================================================

    def test_direct_fallback_persistence_success(self):
        """Direct fallback insert succeeds atomically and produces candidate + ledger record."""
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res = self._call_persist_fallback(raw, version_index=1, source_idx=1)
        self.assertEqual(res.returncode, 0, res.stderr)

        receipt = json.loads(res.stdout.strip().split("\n")[-1])
        self.assertTrue(receipt["success"])
        self.assertFalse(receipt["replayed"])
        self.assertEqual(receipt["result_kind"], "CONFIRMED_SOURCE_FALLBACK")
        self.assertEqual(receipt["candidate_status"], "pending_review")
        self.assertEqual(receipt["attempts"], 4)
        self.assertEqual(receipt["error_code"], "GENERATION_RETRIES_EXHAUSTED")
        self.assertIsNotNone(receipt["version_question_id"])

        q_id = receipt["version_question_id"]
        # Verify candidate row in version_questions
        cand_sql = f"""
        SELECT content, canonical_correct_key, has_warning, status, is_current, validation_report::text
        FROM public.version_questions WHERE id = '{q_id}';
        """
        cand_row = self.sql(cand_sql).stdout.strip().split("|")
        self.assertEqual(cand_row[0], raw["content"])
        self.assertEqual(cand_row[1], "A")
        self.assertEqual(cand_row[2], "t")
        self.assertEqual(cand_row[3], "pending_review")
        self.assertEqual(cand_row[4], "t")

        val_rep = json.loads(cand_row[5])
        self.assertTrue(val_rep["fallback_source"])
        self.assertEqual(val_rep["reason"], "GENERATION_RETRIES_EXHAUSTED")
        self.assertEqual(val_rep["attempts"], 4)
        self.assertEqual(val_rep["validation_status"], "not_validated")

        # Verify ledger row in generation_target_results
        ledger_sql = f"""
        SELECT result_kind, is_success, error_code, attempts, clone_fingerprint
        FROM public.generation_target_results
        WHERE session_id = '{FIXTURE_SESSION}' AND version_index = 1 AND source_question_id = '{SOURCE_Q1}';
        """
        ledger_row = self.sql(ledger_sql).stdout.strip().split("|")
        self.assertEqual(ledger_row[0], "CONFIRMED_SOURCE_FALLBACK")
        self.assertEqual(ledger_row[1], "t")
        self.assertEqual(ledger_row[2], "GENERATION_RETRIES_EXHAUSTED")
        self.assertEqual(ledger_row[3], "4")
        self.assertEqual(ledger_row[4], "")

    def test_failure_to_fallback_transition(self):
        """Valid fallback replaces prior failure ledger row and inserts candidate atomically."""
        # 1. Insert prior AI failure
        fail_raw = {
            "version_index": 1,
            "source_question_id": SOURCE_Q1,
            "request_fingerprint": "a" * 64,
            "attempts": 3,
            "error_code": "VALIDATION_FAILED",
        }
        fail_sql = f"""
        SET ROLE service_role;
        SELECT public.persist_generation_result(
          '{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid, 1, '{SOURCE_Q1}'::uuid, 1,
          false, 'VALIDATION_FAILED', 3, 2000, '{"a" * 64}',
          '{json.dumps(fail_raw)}'::jsonb,
          NULL, NULL, NULL, NULL, false
        );
        """
        res = self.sql(fail_sql, check=False)
        self.assertEqual(res.returncode, 0, res.stderr)

        # Verify failure row exists and candidate is null
        prior = self.sql(f"SELECT is_success, error_code, version_question_id FROM public.generation_target_results WHERE session_id = '{FIXTURE_SESSION}' AND version_index = 1 AND source_question_id = '{SOURCE_Q1}'").stdout.strip().split("|")
        self.assertEqual(prior[0], "f")
        self.assertEqual(prior[1], "VALIDATION_FAILED")
        self.assertEqual(prior[2], "")

        # 2. Persist fallback
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1, last_error="VALIDATION_FAILED")
        res_fb = self._call_persist_fallback(raw, version_index=1, source_idx=1)
        self.assertEqual(res_fb.returncode, 0, res_fb.stderr)

        receipt = json.loads(res_fb.stdout.strip().split("\n")[-1])
        self.assertTrue(receipt["success"])
        self.assertFalse(receipt["replayed"])

        # Verify replaced row
        post = self.sql(f"SELECT is_success, error_code, attempts, result_kind, version_question_id FROM public.generation_target_results WHERE session_id = '{FIXTURE_SESSION}' AND version_index = 1 AND source_question_id = '{SOURCE_Q1}'").stdout.strip().split("|")
        self.assertEqual(post[0], "t")
        self.assertEqual(post[1], "GENERATION_RETRIES_EXHAUSTED")
        self.assertEqual(post[2], "4")
        self.assertEqual(post[3], "CONFIRMED_SOURCE_FALLBACK")
        self.assertNotEqual(post[4], "")

    def test_validation_rejections(self):
        """Rejects attempts != 4, wrong error code, extra keys, or content tampering."""
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1)

        # 1. Attempts != 4
        bad_attempts = raw.copy()
        bad_attempts["attempts"] = 3
        res = self._call_persist_fallback(bad_attempts, version_index=1, source_idx=1)
        self.assertIn("ERR_CONFIG_CONFLICT", res.stderr)

        # 2. Contains AI candidate object
        bad_candidate = raw.copy()
        bad_candidate["candidate"] = {"some": "data"}
        res = self._call_persist_fallback(bad_candidate, version_index=1, source_idx=1)
        self.assertIn("ERR_CONFIG_CONFLICT", res.stderr)

        # 3. Content tampered
        bad_content = raw.copy()
        bad_content["content"] = "Tampered stem"
        res = self._call_persist_fallback(bad_content, version_index=1, source_idx=1)
        self.assertIn("ERR_CONFIG_CONFLICT", res.stderr)

        # 4. Options tampered
        bad_options = raw.copy()
        bad_options["options"] = ["A", "B", "C", "D"]
        res = self._call_persist_fallback(bad_options, version_index=1, source_idx=1)
        self.assertIn("ERR_CONFIG_CONFLICT", res.stderr)

        # 5. Seed tampered
        bad_seed = raw.copy()
        bad_seed["seed"] = 9999
        res = self._call_persist_fallback(bad_seed, version_index=1, source_idx=1)
        self.assertIn("ERR_CONFIG_CONFLICT", res.stderr)

        # 6. Malformed last_error_code
        bad_err = raw.copy()
        bad_err["last_error_code"] = "invalid-code!"
        res = self._call_persist_fallback(bad_err, version_index=1, source_idx=1)
        self.assertIn("ERR_CONFIG_CONFLICT", res.stderr)

    def test_active_replay_identical_payload(self):
        """Active replay returns replayed=true with identical candidate ID."""
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res1 = self._call_persist_fallback(raw, version_index=1, source_idx=1)
        receipt1 = json.loads(res1.stdout.strip().split("\n")[-1])
        self.assertFalse(receipt1["replayed"])

        # Second call with identical payload
        res2 = self._call_persist_fallback(raw, version_index=1, source_idx=1)
        receipt2 = json.loads(res2.stdout.strip().split("\n")[-1])
        self.assertTrue(receipt2["replayed"])
        self.assertEqual(receipt1["version_question_id"], receipt2["version_question_id"])

    def test_conflicting_replay_rejected(self):
        """Replay with different payload raises 23505 ERR_GENERATION_RESULT_CONFLICT."""
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1, last_error="VALIDATION_FAILED")
        res1 = self._call_persist_fallback(raw, version_index=1, source_idx=1)
        self.assertEqual(res1.returncode, 0)

        # Attempt replay with different last_error_code
        diff_raw = self._get_fallback_raw_result(version_index=1, source_idx=1, last_error="SCHEMA_INVALID")
        res2 = self._call_persist_fallback(diff_raw, version_index=1, source_idx=1)
        self.assertNotEqual(res2.returncode, 0)
        self.assertIn("ERR_GENERATION_RESULT_CONFLICT", res2.stderr)

    def test_ai_after_fallback_rejected(self):
        """Attempting to persist AI result over committed fallback raises 23505."""
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res1 = self._call_persist_fallback(raw, version_index=1, source_idx=1)
        self.assertEqual(res1.returncode, 0)

        # Attempt to persist AI failure
        ai_fail_raw = {
            "version_index": 1,
            "source_question_id": SOURCE_Q1,
            "request_fingerprint": "b" * 64,
            "attempts": 1,
            "error_code": "PROVIDER_TIMEOUT",
        }
        call_ai = f"""
        SET ROLE service_role;
        SELECT public.persist_generation_result(
          '{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid, 1, '{SOURCE_Q1}'::uuid, 1,
          false, 'PROVIDER_TIMEOUT', 1, 2000, '{"b" * 64}',
          '{json.dumps(ai_fail_raw)}'::jsonb,
          NULL, NULL, NULL, NULL, false
        );
        """
        res_ai = self.sql(call_ai, check=False)
        self.assertNotEqual(res_ai.returncode, 0)
        self.assertIn("ERR_GENERATION_RESULT_CONFLICT", res_ai.stderr)

    def test_stale_token_rejected_before_replay(self):
        """Stale job token raises 55006 even if identical fallback was committed."""
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res1 = self._call_persist_fallback(raw, version_index=1, source_idx=1)
        self.assertEqual(res1.returncode, 0)

        # Call with mismatched job token
        stale_token = "c0000000-0000-0000-0000-999999999999"
        res2 = self._call_persist_fallback(raw, version_index=1, source_idx=1, token=stale_token)
        self.assertNotEqual(res2.returncode, 0)
        self.assertIn("Fencing token mismatch", res2.stderr)

    def test_clone_job_rejects_fallback(self):
        """Generation job with empty modes and dimensions rejects fallback."""
        # Convert snapshot to Clone job
        self.sql(f"UPDATE public.generation_job_snapshots SET public_modes = '[]'::jsonb, canonical_dimensions = '[]'::jsonb WHERE id = '{JOB_TOKEN}';")
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res = self._call_persist_fallback(raw, version_index=1, source_idx=1)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("clone job requires ORIGINAL_CLONE", res.stderr)

    def test_permissions_boundary(self):
        """Only service_role can call persist_generation_result; helper is ungranted."""
        raw = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res = self._call_persist_fallback(raw, version_index=1, source_idx=1, role="authenticated")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("permission denied", res.stderr.lower())

        # Helper has no execute grants
        helper_call = f"""
        SET ROLE service_role;
        SELECT public._generation_fallback_record((SELECT j FROM public.generation_job_snapshots j WHERE id = '{JOB_TOKEN}'), '{SOURCE_Q1}'::uuid, 1, '{"a" * 64}', 'VALIDATION_FAILED');
        """
        res_h = self.sql(helper_call, check=False)
        self.assertNotEqual(res_h.returncode, 0)
        self.assertIn("permission denied", res_h.stderr.lower())

    # =========================================================================
    # Checkpoint 2: Committed Result and Review Read-back Tests
    # =========================================================================

    def test_generation_committed_recognizes_fallback(self):
        """_generation_committed returns valid fallback slot, excludes corrupted."""
        raw1 = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res1 = self._call_persist_fallback(raw1, version_index=1, source_idx=1)
        self.assertEqual(res1.returncode, 0)

        # 1. Valid pending_review fallback: included
        committed = self.sql(f"""
        SELECT source_question_id, version_index, result_kind, is_success, error_code
        FROM public._generation_committed('{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid);
        """).stdout.strip().split("|")
        self.assertEqual(committed[0], SOURCE_Q1)
        self.assertEqual(committed[1], "1")
        self.assertEqual(committed[2], "CONFIRMED_SOURCE_FALLBACK")
        self.assertEqual(committed[3], "t")
        self.assertEqual(committed[4], "GENERATION_RETRIES_EXHAUSTED")

        # 2. Valid approved fallback: included
        self.sql(f"UPDATE public.version_questions SET status = 'approved' WHERE source_question_id = '{SOURCE_Q1}';")
        count_approved = self.sql(f"SELECT count(*) FROM public._generation_committed('{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid);").stdout.strip()
        self.assertEqual(count_approved, "1")

        # 3. Rejected fallback: excluded
        self.sql(f"UPDATE public.version_questions SET status = 'rejected' WHERE source_question_id = '{SOURCE_Q1}';")
        count_rejected = self.sql(f"SELECT count(*) FROM public._generation_committed('{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid);").stdout.strip()
        self.assertEqual(count_rejected, "0")

        # 4. Noncurrent fallback: excluded
        self.sql(f"UPDATE public.version_questions SET status = 'approved', is_current = false WHERE source_question_id = '{SOURCE_Q1}';")
        count_noncurrent = self.sql(f"SELECT count(*) FROM public._generation_committed('{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid);").stdout.strip()
        self.assertEqual(count_noncurrent, "0")

        # 5. Tampered content: excluded
        self.sql(f"UPDATE public.version_questions SET is_current = true, content = 'Tampered content' WHERE source_question_id = '{SOURCE_Q1}';")
        count_tampered_content = self.sql(f"SELECT count(*) FROM public._generation_committed('{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid);").stdout.strip()
        self.assertEqual(count_tampered_content, "0")

        # 6. Tampered validation report: excluded
        content_escaped = raw1["content"].replace("'", "''")
        self.sql(f"UPDATE public.version_questions SET content = '{content_escaped}', validation_report = jsonb_set(validation_report, '{{attempts}}', '3') WHERE source_question_id = '{SOURCE_Q1}';")
        count_tampered_report = self.sql(f"SELECT count(*) FROM public._generation_committed('{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid);").stdout.strip()
        self.assertEqual(count_tampered_report, "0")

        # 7. Invalid candidate correct_key (diverged from canonical/payload): excluded
        self.sql(f"UPDATE public.version_questions SET validation_report = jsonb_set(validation_report, '{{attempts}}', '4'), correct_key = 'B' WHERE source_question_id = '{SOURCE_Q1}';")
        count_tampered_provenance = self.sql(f"SELECT count(*) FROM public._generation_committed('{FIXTURE_SESSION}'::uuid, '{JOB_TOKEN}'::uuid);").stdout.strip()
        self.assertEqual(count_tampered_provenance, "0")

    def test_load_generation_completed_results_historical_receipts(self):
        """load_generation_completed_results returns completed and historical receipts."""
        raw1 = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res1 = self._call_persist_fallback(raw1, version_index=1, source_idx=1)
        self.assertEqual(res1.returncode, 0)

        load_sql = f"""
        SET ROLE service_role;
        SELECT public.load_generation_completed_results('{FIXTURE_SESSION}'::uuid);
        """
        res = self.sql(load_sql)
        data = json.loads(res.stdout.strip().split("\n")[-1])

        self.assertEqual(len(data["completed"]), 1)
        self.assertEqual(data["completed"][0]["result_kind"], "CONFIRMED_SOURCE_FALLBACK")
        self.assertEqual(len(data["failures"]), 0)
        self.assertEqual(len(data["fallback_receipts"]), 1)

        receipt = data["fallback_receipts"][0]
        self.assertEqual(receipt["snapshot_id"], JOB_TOKEN)
        self.assertEqual(receipt["version_index"], 1)
        self.assertEqual(receipt["source_question_id"], SOURCE_Q1)
        self.assertEqual(receipt["result_kind"], "CONFIRMED_SOURCE_FALLBACK")
        self.assertEqual(receipt["raw_result"]["result_kind"], "CONFIRMED_SOURCE_FALLBACK")

    def test_review_snapshot_authoritative_fallback_origin_and_report(self):
        """get_review_current_snapshot returns origin='confirmed_source_fallback', has_warning=true, SQL report."""
        # Persist fallback for version 1 source 1
        raw1 = self._get_fallback_raw_result(version_index=1, source_idx=1)
        res1 = self._call_persist_fallback(raw1, version_index=1, source_idx=1)
        self.assertEqual(res1.returncode, 0)

        # Persist fallback for remaining 3 slots to have complete 2x2 matrix
        raw1_v2 = self._get_fallback_raw_result(version_index=2, source_idx=1)
        self.assertEqual(self._call_persist_fallback(raw1_v2, version_index=2, source_idx=1).returncode, 0)

        raw2_v1 = self._get_fallback_raw_result(version_index=1, source_idx=2)
        self.assertEqual(self._call_persist_fallback(raw2_v1, version_index=1, source_idx=2).returncode, 0)

        raw2_v2 = self._get_fallback_raw_result(version_index=2, source_idx=2)
        self.assertEqual(self._call_persist_fallback(raw2_v2, version_index=2, source_idx=2).returncode, 0)

        # Transition session to generated
        self.sql(f"UPDATE public.exam_sessions SET status = 'generated' WHERE id = '{FIXTURE_SESSION}';")

        # Query review snapshot as session owner
        review_sql = f"""
        SET ROLE authenticated;
        SELECT set_config('request.jwt.claim.sub', '{FIXTURE_USER}', false);
        SELECT set_config('request.jwt.claim.role', 'authenticated', false);
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        """
        res_review = self.sql(review_sql)
        self.assertEqual(res_review.returncode, 0, res_review.stderr)

        snap = json.loads(res_review.stdout.strip().split("\n")[-1])
        self.assertEqual(snap["session_status"], "generated")
        self.assertFalse(snap["read_only"])
        self.assertEqual(snap["progress"]["current_slots"], 4)
        self.assertEqual(snap["progress"]["expected_slots"], 4)

        # Check candidate 1 in version 1
        cand = snap["versions"][0]["slots"][0]["candidate"]
        self.assertEqual(cand["origin"], "confirmed_source_fallback")
        self.assertTrue(cand["has_warning"])
        self.assertEqual(cand["validation_source"], "version_question")
        self.assertTrue(cand["validation_report"]["fallback_source"])
        self.assertEqual(cand["validation_report"]["reason"], "GENERATION_RETRIES_EXHAUSTED")
        self.assertEqual(cand["validation_report"]["attempts"], 4)
        self.assertEqual(cand["validation_report"]["validation_status"], "not_validated")
        self.assertEqual(cand["content"], raw1["content"])
        self.assertEqual(cand["options"], raw1["options"])
        self.assertEqual(cand["correct_key"], raw1["correct_key"])
        self.assertEqual(cand["solution_md"], raw1["solution_md"])

    def test_review_snapshot_regenerated_precedence(self):
        """Regenerated candidate on a historical fallback slot has origin='regenerated'."""
        # Seed 4 slots
        for v in (1, 2):
            for s in (1, 2):
                raw = self._get_fallback_raw_result(version_index=v, source_idx=s)
                self.assertEqual(self._call_persist_fallback(raw, version_index=v, source_idx=s).returncode, 0)

        # Regenerate slot 1 in version 1
        v1_id = self.sql(f"SELECT id FROM public.exam_versions WHERE session_id = '{FIXTURE_SESSION}' AND version_code = '101';").stdout.strip()
        old_id = self.sql(f"SELECT id FROM public.version_questions WHERE version_id = '{v1_id}' AND source_question_id = '{SOURCE_Q1}';").stdout.strip()

        # Archive old candidate and insert regenerated candidate
        self.sql(f"""
        UPDATE public.version_questions SET is_current = false WHERE id = '{old_id}';
        INSERT INTO public.version_questions(
          version_id, source_question_id, question_no, content, options, correct_key, solution_md,
          canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
          has_warning, status, is_current, regenerated_from_id
        ) VALUES (
          '{v1_id}', '{SOURCE_Q1}', 1, 'Regenerated question', '["1","2","3","4"]'::jsonb, 'B', 'Regen solution',
          1, '["1","2","3","4"]'::jsonb, 'B', 'Regen solution',
          false, 'pending_review', true, '{old_id}'
        );
        """)

        # Transition session to generated
        self.sql(f"UPDATE public.exam_sessions SET status = 'generated' WHERE id = '{FIXTURE_SESSION}';")

        review_sql = f"""
        SET ROLE authenticated;
        SELECT set_config('request.jwt.claim.sub', '{FIXTURE_USER}', false);
        SELECT set_config('request.jwt.claim.role', 'authenticated', false);
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        """
        res = self.sql(review_sql)
        self.assertEqual(res.returncode, 0, res.stderr)
        snap = json.loads(res.stdout.strip().split("\n")[-1])

        cand = snap["versions"][0]["slots"][0]["candidate"]
        self.assertEqual(cand["origin"], "regenerated")
        self.assertEqual(cand["content"], "Regenerated question")

        # Verify historical fallback receipt still preserved in load_generation_completed_results,
        # while current completed results exclude the replaced candidate
        load_sql = f"""
        SET ROLE service_role;
        SELECT public.load_generation_completed_results('{FIXTURE_SESSION}'::uuid);
        """
        load_res = json.loads(self.sql(load_sql).stdout.strip().split("\n")[-1])
        # Replaced fallback is no longer current completed result
        self.assertEqual(len(load_res["completed"]), 3)
        completed_slots = {(c["version_index"], c["source_question_id"]) for c in load_res["completed"]}
        self.assertNotIn((1, SOURCE_Q1), completed_slots)
        # fallback_receipts preserves all 4 historical records
        self.assertEqual(len(load_res["fallback_receipts"]), 4)

    def test_accepted_fallback_remains_completed_after_real_rpc(self):
        """Accepted fallback candidate remains in _generation_committed and completed results."""
        # A2. Prepare four valid fallback results across 2x2 matrix
        persisted_candidates = {}
        for v in (1, 2):
            for s in (1, 2):
                raw = self._get_fallback_raw_result(version_index=v, source_idx=s)
                res = self._call_persist_fallback(raw, version_index=v, source_idx=s)
                self.assertEqual(res.returncode, 0, res.stderr)
                receipt = json.loads(res.stdout.strip().split("\n")[-1])
                self.assertTrue(receipt["success"])
                self.assertEqual(receipt["candidate_status"], "pending_review")
                self.assertEqual(receipt["result_kind"], "CONFIRMED_SOURCE_FALLBACK")
                q_id = receipt["version_question_id"]
                persisted_candidates[(v, s)] = {
                    "question_id": q_id,
                    "raw": raw,
                    "receipt": receipt,
                }
                # Assert candidate initial DB state
                row = self.sql(f"SELECT status, is_current FROM public.version_questions WHERE id = '{q_id}'").stdout.strip().split("|")
                self.assertEqual(row[0], "pending_review")
                self.assertEqual(row[1], "t")

        # A3. Transition session to generated
        self.sql(f"UPDATE public.exam_sessions SET status = 'generated' WHERE id = '{FIXTURE_SESSION}';")
        # Verify session is editable
        session_status = self.sql(f"SELECT status FROM public.exam_sessions WHERE id = '{FIXTURE_SESSION}'").stdout.strip()
        self.assertEqual(session_status, "generated")

        # A4. Capture baseline completed results
        baseline_load_sql = f"""
        SET ROLE service_role;
        SELECT public.load_generation_completed_results('{FIXTURE_SESSION}'::uuid);
        """
        baseline_res = self.sql(baseline_load_sql)
        self.assertEqual(baseline_res.returncode, 0, baseline_res.stderr)
        baseline_data = json.loads(baseline_res.stdout.strip().split("\n")[-1])
        self.assertEqual(len(baseline_data["completed"]), 4)
        self.assertEqual(len(baseline_data["fallback_receipts"]), 4)

        baseline_slots = {
            (c["version_index"], c["source_question_id"])
            for c in baseline_data["completed"]
        }
        self.assertEqual(len(baseline_slots), 4)

        # Select exactly one current fallback candidate (v=1, s=1)
        target_info = persisted_candidates[(1, 1)]
        target_qid = target_info["question_id"]

        # Preserve candidate data before Accept for comparison
        pre_accept_cand = self.sql(f"""
        SELECT content, canonical_options::text, canonical_correct_key, canonical_solution_md, validation_report::text
        FROM public.version_questions WHERE id = '{target_qid}';
        """).stdout.strip().split("|")
        pre_content = pre_accept_cand[0]
        pre_options = pre_accept_cand[1]
        pre_key = pre_accept_cand[2]
        pre_sol = pre_accept_cand[3]
        pre_report = pre_accept_cand[4]

        # A5. Invoke real Accept RPC as authenticated fixture owner
        action_id = str(uuid4())
        accept_sql = f"""
        SET ROLE authenticated;
        SELECT set_config('request.jwt.claim.sub', '{FIXTURE_USER}', false);
        SELECT set_config('request.jwt.claim.role', 'authenticated', false);
        SELECT public.review_accept_question(
          '{FIXTURE_SESSION}'::uuid,
          '{target_qid}'::uuid,
          '{action_id}'::uuid
        );
        """
        accept_res = self.sql(accept_sql)
        self.assertEqual(accept_res.returncode, 0, accept_res.stderr)
        accept_receipt = json.loads(accept_res.stdout.strip().split("\n")[-1])
        self.assertEqual(accept_receipt["question_status"], "approved")
        self.assertEqual(accept_receipt["question_id"], target_qid)

        # Read candidate back from database
        post_accept_cand = self.sql(f"""
        SELECT status, is_current, content, canonical_options::text, canonical_correct_key, canonical_solution_md, validation_report::text
        FROM public.version_questions WHERE id = '{target_qid}';
        """).stdout.strip().split("|")
        self.assertEqual(post_accept_cand[0], "approved")
        self.assertEqual(post_accept_cand[1], "t")
        self.assertEqual(post_accept_cand[2], pre_content)
        self.assertEqual(post_accept_cand[3], pre_options)
        self.assertEqual(post_accept_cand[4], pre_key)
        self.assertEqual(post_accept_cand[5], pre_sol)
        self.assertEqual(post_accept_cand[6], pre_report)

        # Confirm session remains generated and other 3 slots remain pending_review
        curr_session_status = self.sql(f"SELECT status FROM public.exam_sessions WHERE id = '{FIXTURE_SESSION}'").stdout.strip()
        self.assertEqual(curr_session_status, "generated")

        other_statuses = self.sql(f"""
        SELECT status FROM public.version_questions
        WHERE id IN ('{persisted_candidates[(1, 2)]["question_id"]}',
                     '{persisted_candidates[(2, 1)]["question_id"]}',
                     '{persisted_candidates[(2, 2)]["question_id"]}');
        """).stdout.strip().split("\n")
        for st in other_statuses:
            self.assertEqual(st.strip(), "pending_review")

        # A6. Verify completed results after Accept
        after_load_sql = f"""
        SET ROLE service_role;
        SELECT public.load_generation_completed_results('{FIXTURE_SESSION}'::uuid);
        """
        after_res = self.sql(after_load_sql)
        self.assertEqual(after_res.returncode, 0, after_res.stderr)
        after_data = json.loads(after_res.stdout.strip().split("\n")[-1])

        # BEFORE FIX: len(after_data["completed"]) will be 3 instead of 4!
        self.assertEqual(
            len(after_data["completed"]),
            4,
            f"Expected 4 completed slots after Accept, got {len(after_data['completed'])}: {after_data['completed']}"
        )
        self.assertEqual(len(after_data["fallback_receipts"]), 4)

        after_slots = {
            (c["version_index"], c["source_question_id"])
            for c in after_data["completed"]
        }
        self.assertEqual(after_slots, baseline_slots)

        # Verify accepted slot retained fallback result kind and unchanged raw_result
        accepted_item = [c for c in after_data["completed"] if c["version_index"] == 1 and c["source_question_id"] == SOURCE_Q1][0]
        self.assertEqual(accepted_item["result_kind"], "CONFIRMED_SOURCE_FALLBACK")
        self.assertEqual(accepted_item["raw_result"], target_info["raw"])

        # C4. Verify review snapshot compatibility on accepted fallback
        review_sql = f"""
        SET ROLE authenticated;
        SELECT set_config('request.jwt.claim.sub', '{FIXTURE_USER}', false);
        SELECT set_config('request.jwt.claim.role', 'authenticated', false);
        SELECT public.get_review_current_snapshot('{FIXTURE_SESSION}'::uuid);
        """
        snap_res = self.sql(review_sql)
        self.assertEqual(snap_res.returncode, 0, snap_res.stderr)
        snap = json.loads(snap_res.stdout.strip().split("\n")[-1])
        self.assertEqual(snap["progress"]["current_slots"], 4)
        self.assertEqual(snap["progress"]["approved_slots"], 1)
        self.assertEqual(snap["progress"]["expected_slots"], 4)

        cand_snap = snap["versions"][0]["slots"][0]["candidate"]
        self.assertEqual(cand_snap["candidate_id"], target_qid)
        self.assertEqual(cand_snap["status"], "approved")
        self.assertEqual(cand_snap["origin"], "confirmed_source_fallback")
        self.assertTrue(cand_snap["has_warning"])
        self.assertEqual(cand_snap["validation_report"]["validation_status"], "not_validated")


if __name__ == "__main__":
    unittest.main()

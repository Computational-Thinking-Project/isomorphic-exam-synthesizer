"""PostgreSQL 15 migration chain and RPC tests for EXT-01 Package 02 (028_ext01_review_reasons.sql).

Opt in with RUN_POSTGRES_MIGRATION_TESTS=1:
    RUN_POSTGRES_MIGRATION_TESTS=1 python -m pytest backend/tests/migrations/test_ext01_review_reasons_pg.py -v -s

Covers A02-04, A02-05, A02-06, A02-07, A02-08, A02-17, A02-19, A02-23, A02-30
using a disposable network-none postgres:15-alpine container.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

try:
    from tests.migrations.artifact_fixtures import artifact_payload
except ImportError:
    from artifact_fixtures import artifact_payload  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "backend/scripts/schema.sql"
MIGRATIONS_DIR = ROOT / "backend/migrations"

OWNER = "00000000-0000-0000-0000-000000000001"
FOREIGN = "00000000-0000-0000-0000-000000000002"
SID = "10000000-0000-0000-0000-000000000001"
SOURCE = "20000000-0000-0000-0000-000000000001"
VERSION = "30000000-0000-0000-0000-000000000001"
QID = "40000000-0000-0000-0000-000000000001"

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


def literal(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def candidate_payload(calls: int = 1) -> dict[str, object]:
    return {
        "stem_latex": "Tinh nghiem cua $x - 5 = 0$.",
        "options": ["1", "3", "5", "7"],
        "correct_key": "C",
        "solution_md": "Ta co $x = 5$.",
        "validation_report": {
            "is_valid": True,
            "math_verified": False,
            "requires_teacher_review": True,
            "checks": [],
            "warnings": [],
        },
        "api_calls_count": calls,
    }


@unittest.skipUnless(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") == "1", "PostgreSQL integration opt-in"
)
class Ext01ReviewReasonsPgTests(unittest.TestCase):
    db: str = "postgres"
    docker: str = ""
    container: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        docker = os.getenv("DOCKER_BIN") or shutil.which("docker")
        if not docker:
            raise RuntimeError("Set DOCKER_BIN to the Docker CLI executable")
        cls.docker = docker
        cls.container = f"ext01-m2-pg-{uuid4().hex[:12]}"
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
            os.getenv("POSTGRES_MIGRATION_TEST_IMAGE", "postgres:15-alpine"),
        )
        for _ in range(60):
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
    def stop_container(cls) -> None:
        cls.run_docker("rm", "--force", cls.container, check=False)

    @classmethod
    def run_docker(
        cls, *args: str, check: bool = True, input: str | None = None
    ) -> subprocess.CompletedProcess[str]:
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
    def sql(
        cls, script: str, *, db: str | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = cls.run_docker(
            "exec",
            "-i",
            cls.container,
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            "VERBOSITY=verbose",
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

    @classmethod
    def value(cls, sql_expr: str) -> str:
        return cls.sql(sql_expr).stdout.strip()

    def _apply_migrations(self, *, max_prefix: str = "028") -> None:
        migration_files = sorted(
            [f for f in MIGRATIONS_DIR.glob("*.sql") if f.is_file()],
            key=lambda p: p.name,
        )
        applied = []
        for mig in migration_files:
            prefix = mig.name.split("_")[0]
            if prefix > max_prefix:
                break
            content = mig.read_text(encoding="utf-8").lstrip("\ufeff")
            if content.strip():
                self.sql(content)
                applied.append(mig.name)
        self.assertIn("028_ext01_review_reasons.sql" if max_prefix >= "028" else "027_my_session_status_counts.sql", applied)

    def _seed_session(self) -> None:
        artifact, publication = artifact_payload(SOURCE)
        source = artifact["confirmed_input"]
        confirmation_id = str(uuid4())
        receipt = {
            "confirmation_id": confirmation_id,
            "session_id": SID,
            "actor_id": OWNER,
            "sources": [artifact],
        }
        self.sql(f"""
        INSERT INTO auth.users(id, email) VALUES
          ('{OWNER}', 'owner@example.invalid'),
          ('{FOREIGN}', 'foreign@example.invalid')
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO public.users(id, email) VALUES
          ('{OWNER}', 'owner@example.invalid'),
          ('{FOREIGN}', 'foreign@example.invalid')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO public.exam_sessions(id, user_id, title, status, gemini_review_calls)
          VALUES ('{SID}', '{OWNER}', 'EXT-01 M2 Fixture', 'draft', 0);
        INSERT INTO public.source_questions(id, session_id, question_no, raw_content, options, correct_key, solution_md)
          VALUES (
            '{SOURCE}', '{SID}', 1,
            {literal(source['question_text'])},
            {literal(json.dumps(source['options']))}::jsonb,
            {literal(source['correct_answer'])},
            {literal(source['solution'])}
          );
        INSERT INTO public.question_blueprints(source_question_id, confirmed_at)
          VALUES ('{SOURCE}', now());
        INSERT INTO public.source_artifact_confirmations(confirmation_id, session_id, actor_id, confirmed_at, result)
          VALUES ('{confirmation_id}', '{SID}', '{OWNER}', now(), {literal(json.dumps(receipt))}::jsonb);
        INSERT INTO public.source_artifact_revisions(source_revision_id, confirmation_id, source_question_id, confirmed_input, source_fingerprint)
          VALUES (
            {literal(artifact['source_revision_id'])}, '{confirmation_id}', '{SOURCE}',
            {literal(json.dumps(source))}::jsonb, {literal(artifact['source_fingerprint'])}
          );
        INSERT INTO public.canonical_blueprint_revisions(blueprint_revision_id, source_revision_id, source_question_id, canonical_blueprint, schema_version)
          VALUES (
            {literal(publication['blueprint_revision_id'])},
            {literal(artifact['source_revision_id'])},
            '{SOURCE}',
            {literal(json.dumps(publication['canonical_blueprint']))}::jsonb,
            '0.4.0'
          );
        INSERT INTO public.source_artifact_heads(source_question_id, source_revision_id, blueprint_revision_id)
          VALUES (
            '{SOURCE}',
            {literal(artifact['source_revision_id'])},
            {literal(publication['blueprint_revision_id'])}
          );

        UPDATE public.exam_sessions SET status = 'generated' WHERE id = '{SID}';
        INSERT INTO public.generation_configs(session_id, n_versions, active_variation_modes, mapping_version)
          VALUES ('{SID}', 1, '[]'::jsonb, '1.0');
        INSERT INTO public.exam_versions(id, session_id, version_code)
          VALUES ('{VERSION}', '{SID}', '101');
        INSERT INTO public.version_questions(
          id, version_id, source_question_id, question_no, content, options, correct_key, solution_md,
          canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
          is_current, status
        ) VALUES (
          '{QID}', '{VERSION}', '{SOURCE}', 1, 'Candidate', '["1","2","3","4"]'::jsonb, 'A', NULL,
          1, '["1","2","3","4"]'::jsonb, 'A', NULL, true, 'pending_review'
        );
        """)

    def setUp(self) -> None:
        type(self).db = f"ext01_m2_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP + SCHEMA_SQL.read_text(encoding="utf-8").lstrip("\ufeff"))
        self.sql(BOOTSTRAP_GRANTS)

    @staticmethod
    def auth(role: str = "authenticated", actor: str | None = OWNER) -> str:
        sub_clause = (
            f"SET request.jwt.claim.sub = {literal(actor)};"
            if actor is not None
            else "RESET request.jwt.claim.sub;"
        )
        return (
            f"SET ROLE {role}; "
            f"SET request.jwt.claim.role = {literal(role)}; "
            f"{sub_clause} "
        )

    def call_raw(
        self,
        sql_call: str,
        *,
        role: str = "authenticated",
        actor: str | None = OWNER,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self.sql(self.auth(role, actor) + sql_call, check=check)

    def call_json(
        self,
        sql_call: str,
        *,
        role: str = "authenticated",
        actor: str | None = OWNER,
    ) -> dict:
        res = self.call_raw(sql_call, role=role, actor=actor, check=True)
        return json.loads(res.stdout.strip().splitlines()[-1])

    def lookup(
        self,
        op_id: object,
        reasons_sql: str = "'[]'::jsonb",
        *,
        session_id: object = SID,
        question_id: object = QID,
        role: str = "authenticated",
        actor: str | None = OWNER,
        check: bool = True,
    ):
        expr = (
            f"SELECT public.review_lookup_regeneration("
            f"{literal(session_id)}::uuid, {literal(question_id)}::uuid, "
            f"{literal(op_id)}::uuid, {reasons_sql});"
        )
        if not check:
            return self.call_raw(expr, role=role, actor=actor, check=False)
        return self.call_json(expr, role=role, actor=actor)

    def reserve(
        self,
        op_id: object,
        reasons_sql: str = "'[]'::jsonb",
        *,
        session_id: object = SID,
        question_id: object = QID,
        role: str = "authenticated",
        actor: str | None = OWNER,
        check: bool = True,
    ):
        expr = (
            f"SELECT public.review_reserve_regeneration("
            f"{literal(session_id)}::uuid, {literal(question_id)}::uuid, "
            f"{literal(op_id)}::uuid, {reasons_sql});"
        )
        if not check:
            return self.call_raw(expr, role=role, actor=actor, check=False)
        return self.call_json(expr, role=role, actor=actor)

    def test_full_chain_002_through_028_signatures_acls_and_idempotent_rerun(self) -> None:
        self._apply_migrations(max_prefix="028")
        self._seed_session()

        def assert_metadata() -> None:
            self.assertEqual(
                self.value(
                    "SELECT to_regprocedure('public.review_lookup_regeneration(uuid,uuid,uuid)') IS NULL;"
                ),
                "t",
            )
            self.assertEqual(
                self.value(
                    "SELECT to_regprocedure('public.review_reserve_regeneration(uuid,uuid,uuid)') IS NULL;"
                ),
                "t",
            )
            for fn in ("review_lookup_regeneration", "review_reserve_regeneration"):
                self.assertEqual(
                    self.value(
                        f"SELECT count(*), bool_and(pronargs = 4 AND proargdefaults IS NULL AND prosecdef) "
                        f"FROM pg_proc WHERE pronamespace = 'public'::regnamespace AND proname = '{fn}';"
                    ),
                    "1|t",
                )
                sig = f"public.{fn}(uuid,uuid,uuid,jsonb)"
                self.assertEqual(
                    self.value(f"SELECT has_function_privilege('authenticated', '{sig}', 'EXECUTE');"),
                    "t",
                )
                for denied_role in ("public", "anon", "service_role"):
                    self.assertEqual(
                        self.value(
                            f"SELECT has_function_privilege('{denied_role}', '{sig}', 'EXECUTE');"
                        ),
                        "f",
                    )

            for helper in (
                "public._review_canonical_reasons(jsonb)",
                "public._review_stored_reasons(jsonb)",
            ):
                for role in ("public", "anon", "authenticated", "service_role"):
                    self.assertEqual(
                        self.value(f"SELECT has_function_privilege('{role}', '{helper}', 'EXECUTE');"),
                        "f",
                    )

        assert_metadata()
        before_lookup_def = self.value(
            "SELECT pg_get_functiondef('public.review_lookup_regeneration(uuid,uuid,uuid,jsonb)'::regprocedure);"
        )
        before_reserve_def = self.value(
            "SELECT pg_get_functiondef('public.review_reserve_regeneration(uuid,uuid,uuid,jsonb)'::regprocedure);"
        )

        # Idempotent re-run of 028 (A02-17)
        self.sql((MIGRATIONS_DIR / "028_ext01_review_reasons.sql").read_text(encoding="utf-8"))
        assert_metadata()
        self.assertEqual(
            self.value(
                "SELECT pg_get_functiondef('public.review_lookup_regeneration(uuid,uuid,uuid,jsonb)'::regprocedure);"
            ),
            before_lookup_def,
        )
        self.assertEqual(
            self.value(
                "SELECT pg_get_functiondef('public.review_reserve_regeneration(uuid,uuid,uuid,jsonb)'::regprocedure);"
            ),
            before_reserve_def,
        )

    def test_canonicalization_and_invalid_payloads(self) -> None:
        self._apply_migrations(max_prefix="028")
        self._seed_session()

        for bad_sql in (
            "NULL::jsonb",
            "'null'::jsonb",
            "'{}'::jsonb",
            "'\"INCORRECT_ANSWER\"'::jsonb",
            "'[123]'::jsonb",
            "'[true]'::jsonb",
            "'[null]'::jsonb",
            "'[\"incorrect_answer\"]'::jsonb",
            "'[\"UNKNOWN_CODE\"]'::jsonb",
        ):
            for fn in (self.lookup, self.reserve):
                res = fn(uuid4(), bad_sql, check=False)
                self.assertNotEqual(res.returncode, 0, bad_sql)
                self.assertIn("REVIEW_INVALID_PAYLOAD", res.stderr)
                self.assertIn("22023", res.stderr)

        res_null_op = self.reserve(None, "'[]'::jsonb", check=False)
        self.assertNotEqual(res_null_op.returncode, 0)
        self.assertIn("REVIEW_INVALID_PAYLOAD", res_null_op.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")

        op = uuid4()
        reserved = self.reserve(
            op, "'[\"INCORRECT_SOLUTION\", \"DIFFICULTY_MISMATCH\", \"INCORRECT_SOLUTION\"]'::jsonb"
        )
        self.assertFalse(reserved["replayed"])
        self.assertEqual(reserved["reasons"], ["DIFFICULTY_MISMATCH", "INCORRECT_SOLUTION"])
        self.assertNotIn("reasons", reserved["snapshot"])

        looked_up = self.lookup(op, "'[\"DIFFICULTY_MISMATCH\", \"INCORRECT_SOLUTION\"]'::jsonb")
        self.assertTrue(looked_up["found"])
        self.assertTrue(looked_up["reservation"]["replayed"])
        self.assertEqual(
            looked_up["reservation"]["reasons"], ["DIFFICULTY_MISMATCH", "INCORRECT_SOLUTION"]
        )

    def test_legacy_absent_reasons_upgrade_and_malformed_stored_reasons_fail_closed(self) -> None:
        # Apply up to 027 (legacy 3-arg RPCs), create a legacy reservation without 'reasons', then apply 028.
        self._apply_migrations(max_prefix="027")
        self._seed_session()

        legacy_op = uuid4()
        legacy_res = self.call_json(
            f"SELECT public.review_reserve_regeneration('{SID}'::uuid, '{QID}'::uuid, '{legacy_op}'::uuid);"
        )
        self.assertNotIn("reasons", legacy_res)

        self.sql((MIGRATIONS_DIR / "028_ext01_review_reasons.sql").read_text(encoding="utf-8"))

        # Legacy row missing 'reasons' replays as []
        looked = self.lookup(legacy_op, "'[]'::jsonb")
        self.assertTrue(looked["found"])
        self.assertEqual(looked["reservation"]["reasons"], [])

        replayed = self.reserve(legacy_op, "'[]'::jsonb")
        self.assertTrue(replayed["replayed"])
        self.assertEqual(replayed["reasons"], [])

        # Different reasons against legacy [] receipt raises REVIEW_IDEMPOTENCY_CONFLICT
        for fn in (self.lookup, self.reserve):
            conflict = fn(legacy_op, "'[\"INCORRECT_ANSWER\"]'::jsonb", check=False)
            self.assertNotEqual(conflict.returncode, 0)
            self.assertIn("REVIEW_IDEMPOTENCY_CONFLICT", conflict.stderr)

        # Malformed stored reasons must fail closed with 55000 REVIEW_INVARIANT_VIOLATION (NOT [])
        for bad_stored in (
            "'null'::jsonb",
            "'\"INCORRECT_ANSWER\"'::jsonb",
            "'[123]'::jsonb",
            "'[\"UNKNOWN\"]'::jsonb",
            "'[\"incorrect_answer\"]'::jsonb",
        ):
            self.sql(
                f"UPDATE public.review_operations "
                f"SET reservation_result = jsonb_set(reservation_result, '{{reasons}}', {bad_stored}, true) "
                f"WHERE operation_id = '{legacy_op}';"
            )
            for fn in (self.lookup, self.reserve):
                err = fn(legacy_op, "'[]'::jsonb", check=False)
                self.assertNotEqual(err.returncode, 0, bad_stored)
                self.assertIn("REVIEW_INVARIANT_VIOLATION", err.stderr)
                self.assertIn("55000", err.stderr)

    def test_conflict_checked_before_locked_and_stale_guards_a02_05(self) -> None:
        self._apply_migrations(max_prefix="028")
        self._seed_session()

        op = uuid4()
        self.reserve(op, "'[\"INCORRECT_ANSWER\"]'::jsonb")
        # Make candidate non-current AND lock/approve the session
        self.sql(
            f"UPDATE public.version_questions SET is_current = false, status = 'approved' WHERE id = '{QID}'; "
            f"UPDATE public.exam_sessions SET status = 'approved', approved_at = now() WHERE id = '{SID}';"
        )

        for fn in (self.lookup, self.reserve):
            conflict = fn(op, "'[]'::jsonb", check=False)
            self.assertNotEqual(conflict.returncode, 0)
            self.assertIn("REVIEW_IDEMPOTENCY_CONFLICT", conflict.stderr)
            self.assertNotIn("REVIEW_LOCKED", conflict.stderr)
            self.assertNotIn("REVIEW_STALE", conflict.stderr)

        # Matching reasons still replay cleanly despite locked/stale
        self.assertTrue(self.lookup(op, "'[\"INCORRECT_ANSWER\"]'::jsonb")["found"])
        self.assertTrue(self.reserve(op, "'[\"INCORRECT_ANSWER\"]'::jsonb")["replayed"])

    def test_cross_owner_and_role_concealment_a02_07_08(self) -> None:
        self._apply_migrations(max_prefix="028")
        self._seed_session()

        op = uuid4()
        self.reserve(op, "'[\"INCORRECT_ANSWER\"]'::jsonb")

        # Cross-owner with different reasons must receive REVIEW_NOT_FOUND before conflict/receipt
        for fn in (self.lookup, self.reserve):
            foreign = fn(op, "'[]'::jsonb", actor=FOREIGN, check=False)
            self.assertNotEqual(foreign.returncode, 0)
            self.assertIn("REVIEW_NOT_FOUND", foreign.stderr)
            self.assertIn("P0002", foreign.stderr)
            self.assertNotIn("REVIEW_IDEMPOTENCY_CONFLICT", foreign.stderr)

            unauth = fn(op, "'[]'::jsonb", actor=None, check=False)
            self.assertNotEqual(unauth.returncode, 0)
            self.assertIn("REVIEW_NOT_FOUND", unauth.stderr)

        # Wrong question_id in lookup must return REVIEW_NOT_FOUND before revealing receipt/conflict
        wrong_q = self.lookup(op, "'[]'::jsonb", question_id=uuid4(), check=False)
        self.assertNotEqual(wrong_q.returncode, 0)
        self.assertIn("REVIEW_NOT_FOUND", wrong_q.stderr)

        # anon and service_role cannot execute either 4-arg RPC
        for role in ("anon", "service_role"):
            for fn in (self.lookup, self.reserve):
                denied = fn(op, "'[]'::jsonb", role=role, check=False)
                self.assertNotEqual(denied.returncode, 0)
                self.assertIn("permission denied", denied.stderr)

    def test_concurrent_same_key_race_a02_06(self) -> None:
        self._apply_migrations(max_prefix="028")
        self._seed_session()

        def run_concurrent(script_a: str, script_b: str) -> list[subprocess.CompletedProcess[str]]:
            barrier = Barrier(2)

            def worker(script: str) -> subprocess.CompletedProcess[str]:
                barrier.wait(timeout=10)
                return self.sql(script, check=False)

            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(worker, (script_a, script_b)))

        # Race 1: same operation_id + different reasons -> 1 reserve succeeds, 1 gets REVIEW_IDEMPOTENCY_CONFLICT (never 23505)
        op_diff = uuid4()
        res_diff = run_concurrent(
            self.auth()
            + f"SELECT public.review_reserve_regeneration('{SID}'::uuid, '{QID}'::uuid, '{op_diff}'::uuid, '[\"INCORRECT_ANSWER\"]'::jsonb);",
            self.auth()
            + f"SELECT public.review_reserve_regeneration('{SID}'::uuid, '{QID}'::uuid, '{op_diff}'::uuid, '[\"INVALID_QUESTION\"]'::jsonb);",
        )
        ok = [r for r in res_diff if r.returncode == 0]
        fail = [r for r in res_diff if r.returncode != 0]
        self.assertEqual(len(ok), 1, res_diff)
        self.assertEqual(len(fail), 1, res_diff)
        self.assertIn("REVIEW_IDEMPOTENCY_CONFLICT", fail[0].stderr)
        self.assertNotIn("23505", fail[0].stderr)

        # Clean up active op by failing it so we can test same-reasons race on a fresh operation_id
        self.call_json(
            f"SELECT public.review_fail_regeneration('{op_diff}'::uuid, 'GENERATION_FAILED');",
            role="service_role",
        )

        # Race 2: same operation_id + same reasons -> 1 fresh reserve, 1 replay
        op_same = uuid4()
        script_same = (
            self.auth()
            + f"SELECT public.review_reserve_regeneration('{SID}'::uuid, '{QID}'::uuid, '{op_same}'::uuid, '[\"EQUIVALENT_OPTIONS\"]'::jsonb);"
        )
        res_same = run_concurrent(script_same, script_same)
        for r in res_same:
            self.assertEqual(r.returncode, 0, r.stderr)
        parsed = [json.loads(r.stdout.strip().splitlines()[-1]) for r in res_same]
        self.assertEqual(sorted(p["replayed"] for p in parsed), [False, True])
        self.assertTrue(all(p["reasons"] == ["EQUIVALENT_OPTIONS"] for p in parsed))

    def test_recovery_checks_locked_and_shuffled_sessions_under_db_lock(self):
        self._apply_migrations(max_prefix="028")
        self._seed_session()
        op = uuid4()
        self.reserve(op, "'[]'::jsonb")
        self.sql(f"UPDATE public.review_operations SET expires_at=clock_timestamp()-interval '1 second' WHERE operation_id='{op}';")
        recover = f"SELECT public.review_recover_session('{SID}');"
        for status, expected in [("approved", "REVIEW_LOCKED"), ("reviewed", "REVIEW_POST_SHUFFLE_LOCKED")]:
            self.sql(f"UPDATE public.exam_sessions SET status='{status}' WHERE id='{SID}';"
                     f"UPDATE public.exam_versions SET is_finalized=true WHERE id='{VERSION}';")
            denied = self.call_raw(recover, role="service_role", check=False)
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn(expected, denied.stderr)
            self.assertEqual(self.lookup(op, "'[]'::jsonb")["reservation"]["operation_status"], "active")
        self.sql(f"UPDATE public.exam_sessions SET status='generated' WHERE id='{SID}';"
                 f"UPDATE public.exam_versions SET is_finalized=false WHERE id='{VERSION}';")
        self.assertEqual(self.call_json(recover, role="service_role")["recovered_count"], 1)
        self.assertEqual(self.call_json(recover, role="service_role")["recovered_count"], 0)

    def test_non_empty_reasons_end_to_end_lifecycle_a02_19(self) -> None:
        self._apply_migrations(max_prefix="028")
        self._seed_session()

        op = uuid4()
        reserved = self.reserve(op, "'[\"INCORRECT_SOLUTION\", \"EQUIVALENT_OPTIONS\"]'::jsonb")
        self.assertEqual(reserved["reasons"], ["EQUIVALENT_OPTIONS", "INCORRECT_SOLUTION"])

        permit = self.call_json(
            f"SELECT public.review_acquire_attempt('{op}'::uuid, '{uuid4()}'::uuid);",
            role="service_role",
        )
        self.assertTrue(permit["dispatch_permitted"])

        completed = self.call_json(
            f"SELECT public.review_complete_regeneration('{op}'::uuid, {literal(json.dumps(candidate_payload(1)))}::jsonb);",
            role="service_role",
        )
        self.assertEqual(completed["api_calls_used"], 1)

        looked = self.lookup(op, "'[\"EQUIVALENT_OPTIONS\", \"INCORRECT_SOLUTION\"]'::jsonb")
        self.assertTrue(looked["found"])
        self.assertEqual(looked["reservation"]["operation_status"], "completed")
        self.assertEqual(
            looked["reservation"]["reasons"], ["EQUIVALENT_OPTIONS", "INCORRECT_SOLUTION"]
        )
        self.assertNotIn("reasons", looked["reservation"]["snapshot"])
        original = looked["reservation"]["completion_candidate"]
        self.assertEqual(original, candidate_payload(1))
        self.sql(f"UPDATE public.version_questions SET status='approved', content='Later edit' WHERE id='{completed['question_id']}';")
        replay = self.lookup(op, """'["INCORRECT_SOLUTION","EQUIVALENT_OPTIONS"]'::jsonb""")
        self.assertEqual(replay["reservation"]["completion_candidate"], original)
        self.assertEqual(replay["reservation"]["settlement"], completed)

        conflict = self.lookup(op, "'[]'::jsonb", check=False)
        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn("REVIEW_IDEMPOTENCY_CONFLICT", conflict.stderr)


if __name__ == "__main__":
    unittest.main()

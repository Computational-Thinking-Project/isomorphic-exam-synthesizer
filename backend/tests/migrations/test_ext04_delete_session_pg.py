"""Q07 rehearsal on PostgreSQL 15 with the pinned provider SQL."""

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from test_export_snapshot_pg import OTHER, OWNER, auth
from test_stage3_schema import BOOTSTRAP, ROOT, PostgresCase

BASE = "b29244346094811eaa038fd31fea67969f8f5b7f"
PROVIDER_MIGRATIONS = (
    "68ed813516218ebccdabcdcd9cf626ed84301751:backend/migrations/028_generation_mode.sql",
    "8fb21e6f7e50cd241d0df1543389c2749130bda3:backend/migrations/029_ext01_review_reasons.sql",
    "8fb21e6f7e50cd241d0df1543389c2749130bda3:backend/migrations/029b_ext01_review_mode_policy.sql",
)
DELETE_SCHEMA = Path(__file__).parent / "fixtures/ext04_delete_session.sql"


def git_output(*args):
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8-sig", timeout=20,
    )
    if result.returncode:
        raise AssertionError(
            f"Could not read pinned migration SQL: {result.stderr.strip()}. "
            "See backend/tests/migrations/README.md for the required objects."
        )
    return result.stdout.replace("\ufeff", "")


class TestExt04DeleteSession(PostgresCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_db = f"ext04_delete_template_{uuid4().hex}"
        cls.run_docker("exec", cls.container, "createdb", "-U", "postgres", cls.template_db)
        baseline_paths = git_output("ls-tree", "-r", "--name-only", BASE, "backend/migrations").splitlines()
        baseline_sql = [f"{BASE}:{path}" for path in baseline_paths if path.endswith(".sql")]
        cls.sql(
            BOOTSTRAP + git_output("show", f"{BASE}:backend/scripts/schema.sql"),
            db=cls.template_db,
        )
        cls.sql("""
            GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
            GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated, service_role;
        """, db=cls.template_db)
        cls.sql(
            git_output("show", *baseline_sql, *PROVIDER_MIGRATIONS)
            + DELETE_SCHEMA.read_text(encoding="utf-8"),
            db=cls.template_db,
        )

    def setUp(self):
        type(self).db = f"ext04_delete_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", "-T", self.template_db, self.db)
        self.sid, self.other_sid = uuid4(), uuid4()
        self.source, self.version, self.question, self.operation = (uuid4() for _ in range(4))
        self.call = f"SELECT public.delete_draft_session('{self.sid}');"
        self.sql(f"""
            INSERT INTO auth.users (id, email) VALUES
                ('{OWNER}', 'owner@example.invalid'), ('{OTHER}', 'other@example.invalid');
            INSERT INTO public.users (id, email) VALUES
                ('{OWNER}', 'owner@example.invalid'), ('{OTHER}', 'other@example.invalid')
                ON CONFLICT (id) DO NOTHING;
            INSERT INTO public.exam_sessions (id, user_id, title) VALUES
                ('{self.sid}', '{OWNER}', 'Draft'), ('{self.other_sid}', '{OWNER}', 'Source exam');
            INSERT INTO public.source_questions (id, session_id, question_no, raw_content, options, correct_key) VALUES
                ('{self.source}', '{self.sid}', 1, 'Question', '["a","b","c","d"]', 'A'),
                (gen_random_uuid(), '{self.other_sid}', 1, 'Source', '["a","b","c","d"]', 'A');
            INSERT INTO public.question_blueprints (source_question_id, confirmed_at) VALUES ('{self.source}', now());
        """)

    def seed_review_candidate(self):
        self.sql(f"""
            INSERT INTO public.generation_configs (session_id, n_versions) VALUES ('{self.sid}', 2);
            INSERT INTO public.exam_versions (id, session_id, version_code)
                VALUES ('{self.version}', '{self.sid}', '101');
            INSERT INTO public.version_questions (
                id, version_id, source_question_id, question_no, content, options, correct_key, status,
                canonical_question_no, canonical_options, canonical_correct_key
            ) VALUES (
                '{self.question}', '{self.version}', '{self.source}', 1,
                'Candidate', '["a","b","c","d"]', 'A', 'pending_review', 1, '["a","b","c","d"]', 'A'
            );
            UPDATE public.exam_sessions SET status = 'generated', gemini_review_calls = 1 WHERE id = '{self.sid}';
        """)

    def activate_review(self, lease):
        # Seed a historical reservation accepted by the real recovery helper.
        return f"""
            SELECT id FROM public.exam_sessions WHERE id = '{self.sid}' FOR UPDATE;
            UPDATE public.version_questions SET status = 'regenerating' WHERE id = '{self.question}';
            INSERT INTO public.review_operations (
                operation_id, session_id, question_id, actor_id, prior_status, snapshot, reservation_result, expires_at
            ) VALUES (
                '{self.operation}', '{self.sid}', '{self.question}', '{OWNER}', 'pending_review',
                '{{}}', '{{}}', clock_timestamp() + interval '{lease}'
            );
            INSERT INTO public.review_attempts (attempt_id, operation_id, dispatch_permitted, calls_used, remaining_calls)
                VALUES (gen_random_uuid(), '{self.operation}', true, 1, 29);
        """

    def assert_draft_deleted(self):
        self.assertEqual(self.value("SELECT id FROM public.exam_sessions;"), str(self.other_sid))
        self.assertEqual(self.value("SELECT session_id FROM public.source_questions;"), str(self.other_sid))
        for table in ("question_blueprints", "exam_versions", "version_questions", "review_operations",
                      "review_attempts", "review_logs", "generation_configs"):
            self.assertEqual(self.value(f"SELECT count(*) FROM public.{table};"), "0", table)

    def test_owner_delete_cascades_cleanup_even_for_incomplete_clone(self):
        self.assert_sql_fails(auth(OTHER) + self.call, "ERR_SESSION_NOT_FOUND")
        self.assert_sql_fails(auth() + f"SELECT public.delete_draft_session('{uuid4()}');", "ERR_SESSION_NOT_FOUND")
        self.assert_sql_fails("SET ROLE authenticated;" + self.call, "ERR_AUTH_REQUIRED")
        self.sql(auth() + self.call)
        self.assert_draft_deleted()
        self.assert_sql_fails(auth() + self.call, "ERR_SESSION_NOT_FOUND")

    def test_only_authenticated_can_call_delete_and_neither_path_exposes_recovery(self):
        self.assertEqual(self.value("""
            SELECT d.prosecdef AND NOT r.prosecdef AND d.proowner = r.proowner
            FROM pg_proc d, pg_proc r
            WHERE d.oid = 'public.delete_draft_session(uuid)'::regprocedure
              AND r.oid = 'public._review_recover_expired_locked(uuid)'::regprocedure;
        """), "t")
        for role in ("anon", "authenticated", "service_role"):
            with self.subTest(role=role):
                caller = auth(role=role)
                self.assert_sql_fails(
                    caller + f"DELETE FROM public.exam_sessions WHERE id = '{self.sid}';",
                    "permission denied for table exam_sessions",
                )
                self.assert_sql_fails(
                    caller + f"SELECT public._review_recover_expired_locked('{self.sid}');",
                    "permission denied for function",
                )
                if role != "authenticated":
                    self.assert_sql_fails(caller + self.call, "permission denied for function")
        self.assertEqual(self.value("""
            SELECT has_function_privilege('public', 'public.delete_draft_session(uuid)', 'EXECUTE')
                OR has_table_privilege('public', 'public.exam_sessions', 'DELETE');
        """), "f")

    def test_approved_exported_and_historical_approved_timestamp_are_locked(self):
        for status, approval in (("approved", "NULL"), ("exported", "NULL"), ("draft", "now()")):
            with self.subTest(status=status):
                self.sql(f"UPDATE public.exam_sessions SET status='{status}', approved_at={approval} WHERE id='{self.sid}';")
                self.assert_sql_fails(auth() + self.call, "ERR_SESSION_LOCKED")
        self.assertEqual(self.value(f"SELECT count(*) FROM public.source_questions WHERE id='{self.source}';"), "1")

    def test_idle_reviewed_round_can_be_deleted(self):
        self.seed_review_candidate()
        self.sql(f"""
            UPDATE public.version_questions SET status = 'approved' WHERE id = '{self.question}';
            UPDATE public.exam_sessions SET status = 'reviewed' WHERE id = '{self.sid}';
        """)
        self.sql(auth() + self.call)
        self.assert_draft_deleted()

    def test_expired_review_recovery_rolls_back_with_delete(self):
        self.seed_review_candidate()
        self.sql("BEGIN;" + self.activate_review("-1 second") + "COMMIT;")
        self.assert_sql_fails(auth(OTHER) + self.call, "ERR_SESSION_NOT_FOUND")
        self.assertEqual(self.value(f"SELECT status FROM public.review_operations WHERE operation_id='{self.operation}';"), "active")
        self.sql(f"""
            CREATE FUNCTION public.force_delete_failure() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM public.review_operations
                    WHERE operation_id = '{self.operation}' AND status = 'recovered'
                ) OR NOT EXISTS (
                    SELECT 1 FROM public.review_logs
                    WHERE session_id = OLD.id AND reason = 'STALE_RECOVERY' AND api_calls_used = 1
                      AND user_id = '{OWNER}' AND version_question_id = '{self.question}'
                ) OR NOT EXISTS (
                    SELECT 1 FROM public.version_questions WHERE id = '{self.question}' AND status = 'pending_review'
                ) OR OLD.gemini_review_calls <> 1 THEN
                    RAISE EXCEPTION 'RECOVERY_EVIDENCE_MISSING';
                END IF;
                RAISE EXCEPTION 'FORCED_DELETE_FAILURE_AFTER_RECOVERY';
            END $$;
            CREATE TRIGGER force_delete_failure BEFORE DELETE ON public.exam_sessions
                FOR EACH ROW EXECUTE FUNCTION public.force_delete_failure();
        """)
        self.assert_sql_fails(auth() + self.call, "FORCED_DELETE_FAILURE_AFTER_RECOVERY")
        self.assertEqual(self.value(f"""
            SELECT o.status || '|' || q.status || '|' || s.gemini_review_calls
            FROM public.review_operations o
            JOIN public.version_questions q ON q.id = o.question_id
            JOIN public.exam_sessions s ON s.id = o.session_id
            WHERE o.operation_id = '{self.operation}';
        """), "active|regenerating|1")
        self.assertEqual(self.value("SELECT count(*) FROM public.review_logs;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM public.review_attempts;"), "1")
        self.sql("DROP TRIGGER force_delete_failure ON public.exam_sessions;")
        self.sql(auth() + self.call)
        self.assert_draft_deleted()

    def assert_waiting_call_rechecks_state(self, change, waiting_call, error):
        # The marker is taken after the writer locks the row. The writer commits
        # only after PostgreSQL reports that the second transaction is blocked.
        marker = 74104
        writer = f"""
            BEGIN;
            {change}
            SELECT pg_advisory_xact_lock({marker});
            DO $$
            DECLARE deadline timestamptz := clock_timestamp() + interval '15 seconds';
            BEGIN
                WHILE NOT EXISTS (
                    SELECT 1 FROM pg_stat_activity
                    WHERE application_name = 'ext04_waiter' AND pg_backend_pid() = ANY(pg_blocking_pids(pid))
                ) LOOP
                    IF clock_timestamp() >= deadline THEN
                        RAISE EXCEPTION 'Second transaction never blocked on the writer';
                    END IF;
                    PERFORM pg_stat_clear_snapshot();
                    PERFORM pg_sleep(0.025);
                END LOOP;
            END $$;
            COMMIT;
        """
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(self.sql, writer)
            deadline = time.monotonic() + 10
            while self.value(f"SELECT pg_try_advisory_xact_lock({marker});") == "t":
                if result.done():
                    result.result()
                    self.fail("Writer exited before the second transaction started")
                if time.monotonic() >= deadline:
                    self.fail("Writer did not reach its synchronization marker")
                time.sleep(0.025)
            self.assert_sql_fails(
                "SET application_name = 'ext04_waiter'; SET statement_timeout = '20s';"
                + auth() + waiting_call,
                error,
            )
            result.result(timeout=20)

    def test_delete_rechecks_generation_fence_after_waiting_for_session_writer(self):
        self.assert_waiting_call_rechecks_state(f"""
            UPDATE public.exam_sessions SET status = 'generating', active_job_id = gen_random_uuid()
            WHERE id = '{self.sid}';
        """, self.call, "ERR_SESSION_BUSY_GENERATING")
        self.assertEqual(self.value(f"SELECT status FROM public.exam_sessions WHERE id = '{self.sid}';"), "generating")

    def test_delete_rechecks_approval_after_waiting_for_session_writer(self):
        self.assert_waiting_call_rechecks_state(f"""
            UPDATE public.exam_sessions SET status = 'approved', approved_at = clock_timestamp()
            WHERE id = '{self.sid}';
        """, self.call, "ERR_SESSION_LOCKED")
        self.assertEqual(self.value(f"SELECT status FROM public.exam_sessions WHERE id = '{self.sid}';"), "approved")

    def test_delete_rechecks_live_review_after_waiting_for_session_writer(self):
        self.seed_review_candidate()
        self.assert_waiting_call_rechecks_state(
            self.activate_review("3 minutes"), self.call, "ERR_REVIEW_OPERATION_ACTIVE",
        )
        self.assertEqual(self.value(f"SELECT status FROM public.review_operations WHERE operation_id='{self.operation}';"), "active")

    def test_claim_loses_to_committed_delete(self):
        self.assert_waiting_call_rechecks_state(
            self.call_as_writer(),
            f"SELECT public.claim_generation_job('{self.sid}');",
            "Session not found",
        )
        self.assert_draft_deleted()

    def test_review_reservation_loses_to_committed_delete(self):
        self.seed_review_candidate()
        self.assert_waiting_call_rechecks_state(
            self.call_as_writer(),
            f"SELECT public.review_reserve_regeneration('{self.sid}', '{self.question}', '{self.operation}', '[]');",
            "REVIEW_NOT_FOUND",
        )
        self.assert_draft_deleted()

    def test_approve_loses_to_committed_delete(self):
        self.assert_waiting_call_rechecks_state(
            self.call_as_writer(),
            f"SELECT public.finalize_approve_session('{self.sid}');",
            "ERR_SESSION_NOT_FOUND",
        )
        self.assert_draft_deleted()

    def call_as_writer(self):
        # Reset the role for the writer's pg_stat_activity/pg_blocking_pids synchronization.
        return auth() + self.call + "RESET ROLE;"

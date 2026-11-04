"""PostgreSQL regression for the TASK-302 readiness gate in migration 007."""

from test_stage3_schema import ROOT, PostgresCase


class FinalizeReadinessTests(PostgresCase):
    def test_unconfirmed_source_cannot_be_approved(self):
        self.migrate()
        self.sql((ROOT / "backend/migrations/007_finalize_approve_session_rpc.sql").read_text(encoding="utf-8"))
        self.sql("""
          INSERT INTO generation_configs(session_id,n_versions)
          VALUES ('10000000-0000-0000-0000-000000000001',1);
          UPDATE exam_versions SET is_finalized=true;
          UPDATE version_questions SET status='approved';
          UPDATE exam_sessions SET status='reviewed';
        """)
        result = self.sql("""
          SET request.jwt.claim.role = 'service_role';
          SELECT public.finalize_approve_session(
            '10000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000001',NULL);
        """, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_NOT_ALL_QUESTIONS_APPROVED", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "reviewed")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")

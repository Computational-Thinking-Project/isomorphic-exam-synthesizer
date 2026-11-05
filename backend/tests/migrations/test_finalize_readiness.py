"""PostgreSQL regression for the TASK-302 readiness gate in migration 007."""

from test_stage3_schema import ROOT, PostgresCase


class FinalizeReadinessTests(PostgresCase):
    def ready(self):
        self.migrate()
        self.sql(
            (ROOT / "backend/migrations/007_finalize_approve_session_rpc.sql").read_text(
                encoding="utf-8"
            )
        )
        self.sql("""
          INSERT INTO generation_configs(session_id,n_versions)
          VALUES ('10000000-0000-0000-0000-000000000001',1);
          INSERT INTO question_blueprints(source_question_id,confirmed_at)
          VALUES ('20000000-0000-0000-0000-000000000001',now());
          UPDATE exam_versions SET is_finalized=true;
          UPDATE version_questions SET status='approved';
          UPDATE exam_sessions SET status='reviewed';
        """)

    def approve(self, *, check=True):
        return self.sql(
            """
          SET ROLE service_role;
          SET request.jwt.claim.role = 'service_role';
          SELECT public.finalize_approve_session(
            '10000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000001',NULL);
        """,
            check=check,
        )

    def test_ready_session_with_complete_keys_approves_once(self):
        self.ready()
        self.sql("""
          INSERT INTO answer_keys(version_id,question_no,correct_option,display_no,display_correct_key,canonical_question_no)
          VALUES ('30000000-0000-0000-0000-000000000001',1,'B',1,'B',9);
        """)
        self.approve()
        timestamp = self.value("SELECT approved_at FROM exam_sessions;")
        self.approve()
        self.assertEqual(self.value("SELECT approved_at FROM exam_sessions;"), timestamp)
        self.assertEqual(
            self.value("SELECT count(*) FROM review_logs WHERE action_type='APPROVE_ALL';"), "1"
        )

    def test_ready_session_without_keys_is_rejected_without_writes(self):
        self.ready()
        result = self.approve(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_INCONSISTENT_ANSWER_KEYS", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "reviewed")
        self.assertEqual(self.value("SELECT approved_at IS NULL FROM exam_sessions;"), "t")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")

    def test_authenticated_cannot_forge_service_role_claim(self):
        self.ready()
        self.sql("""
          INSERT INTO answer_keys(version_id,question_no,correct_option,display_no,display_correct_key,canonical_question_no)
          VALUES ('30000000-0000-0000-0000-000000000001',1,'B',1,'B',9);
        """)
        result = self.sql(
            """
          SET ROLE authenticated;
          SET request.jwt.claim.role = 'service_role';
          SET request.jwt.claim.sub = '00000000-0000-0000-0000-000000000002';
          SELECT public.finalize_approve_session(
            '10000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000001',NULL);
        """,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_UNAUTHORIZED", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "reviewed")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")

        json_claims = self.sql(
            """
          SET ROLE authenticated;
          SET request.jwt.claims = '{"role":"service_role","sub":"00000000-0000-0000-0000-000000000002"}';
          SELECT public.finalize_approve_session(
            '10000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000001',NULL);
        """,
            check=False,
        )
        self.assertNotEqual(json_claims.returncode, 0)
        self.assertIn("ERR_UNAUTHORIZED", json_claims.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "reviewed")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")

    def test_authenticated_owner_can_approve(self):
        self.ready()
        self.sql("""
          INSERT INTO answer_keys(version_id,question_no,correct_option,display_no,display_correct_key,canonical_question_no)
          VALUES ('30000000-0000-0000-0000-000000000001',1,'B',1,'B',9);
        """)
        self.sql("""
          SET ROLE authenticated;
          SET request.jwt.claim.role = 'authenticated';
          SET request.jwt.claim.sub = '00000000-0000-0000-0000-000000000001';
          SELECT public.finalize_approve_session(
            '10000000-0000-0000-0000-000000000001',NULL,NULL);
        """)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "approved")
        self.assertEqual(
            self.value("SELECT count(*) FROM review_logs WHERE action_type='APPROVE_ALL';"), "1"
        )

    def test_anon_cannot_execute_approval(self):
        self.ready()
        result = self.sql(
            """
          SET ROLE anon;
          SELECT public.finalize_approve_session(
            '10000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000001',NULL);
        """,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("permission denied", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "reviewed")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")

    def test_unconfirmed_source_cannot_be_approved(self):
        self.migrate()
        self.sql(
            (ROOT / "backend/migrations/007_finalize_approve_session_rpc.sql").read_text(
                encoding="utf-8"
            )
        )
        self.sql("""
          INSERT INTO generation_configs(session_id,n_versions)
          VALUES ('10000000-0000-0000-0000-000000000001',1);
          UPDATE exam_versions SET is_finalized=true;
          UPDATE version_questions SET status='approved';
          UPDATE exam_sessions SET status='reviewed';
        """)
        result = self.sql(
            """
          SET ROLE service_role;
          SET request.jwt.claim.role = 'service_role';
          SELECT public.finalize_approve_session(
            '10000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000001',NULL);
        """,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_NOT_ALL_QUESTIONS_APPROVED", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "reviewed")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")

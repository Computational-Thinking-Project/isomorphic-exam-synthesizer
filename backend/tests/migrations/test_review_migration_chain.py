"""Opt-in integration with the exact upstream migrations, without copying them.

Fetch the pinned commits before running with RUN_UPSTREAM_MIGRATION_TESTS=1.
The normal PostgreSQL suite does not require unmerged upstream Git objects.
"""

import json
import os
import subprocess
import unittest
from uuid import uuid4

from test_review_rpcs import OWNER, QID, SID, SOURCE, candidate, literal
from test_stage3_schema import BOOTSTRAP, ROOT, SEED, PostgresCase
from artifact_fixture import publish_fixture

UPSTREAM = (
    ("31ed3bc71188db537c41b547630a6b9dbf5f270f", "004_save_generation_config_rpc.sql"),
    ("31ed3bc71188db537c41b547630a6b9dbf5f270f", "005_generation_job_operations_rpc.sql"),
    ("d7a3d3f788972f06552cd21a7e7103eceb2f2a55", "007_finalize_approve_session_rpc.sql"),
)


@unittest.skipUnless(
    os.getenv("RUN_UPSTREAM_MIGRATION_TESTS") == "1", "Pinned upstream migrations opt-in"
)
class ReviewMigrationChainTests(PostgresCase):
    @classmethod
    def setUpClass(cls):
        # Read immutable Git blobs. A missing object fails explicitly when opted in;
        # never fall back to a moving branch or silently skip a requested check.
        cls.upstream_sql = [
            subprocess.run(
                ["git", "show", f"{commit}:backend/migrations/{name}"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                timeout=30,
            ).stdout
            for commit, name in UPSTREAM
        ]
        super().setUpClass()

    def setUp(self):
        self.initialize_database()
        self.sql(self.upstream_sql[0])
        self.sql(self.upstream_sql[1])
        self.migrate()
        self.sql(self.upstream_sql[2])
        self.sql(f"""
        UPDATE exam_sessions SET status='generated';
        INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',1);
        INSERT INTO question_blueprints(source_question_id,confirmed_at) VALUES ('{SOURCE}',now());
        """)
        publish_fixture(self, SID, SOURCE, OWNER)

    def initialize_database(self):
        super().setUp()

    def call(self, name, *args, worker=False, check=True):
        role = "service_role" if worker else "authenticated"
        result = self.sql(
            f"SET ROLE {role}; SET request.jwt.claim.role='{role}'; "
            f"SET request.jwt.claim.sub='{OWNER}'; "
            f"SELECT public.{name}({','.join(literal(arg) for arg in args)});",
            check=check,
        )
        return json.loads(result.stdout) if check else result

    def test_upgrade_and_full_chain_replay_preserve_charged_receipt(self):
        op, attempt = uuid4(), uuid4()
        self.call("review_reserve_regeneration", SID, QID, op)
        self.call("review_acquire_attempt", op, attempt, worker=True)
        for script in self.upstream_sql[:2]:
            self.sql(script)
        self.migrate()
        self.sql(self.upstream_sql[2])
        permit = self.call("review_acquire_attempt", op, attempt, worker=True)
        self.assertTrue(permit["replayed"])
        self.assertFalse(permit["dispatch_permitted"])
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "8")
        completed = self.call(
            "review_complete_regeneration", op, json.dumps(candidate(1)), worker=True
        )
        self.assertEqual(completed["api_calls_used"], 1)
        self.assertEqual(self.value("SELECT count(*) FROM review_attempts;"), "1")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
        self.assertEqual(
            self.value("SELECT has_table_privilege('service_role','review_operations','SELECT');"),
            "f",
        )

    def test_recovery_then_real_007_approval_and_006_replay(self):
        self.call("review_accept_question", SID, QID, uuid4())
        op = uuid4()
        self.call("review_reserve_regeneration", SID, QID, op)
        self.call("review_acquire_attempt", op, uuid4(), worker=True)
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        self.assertEqual(
            self.call("review_recover_session", SID, worker=True)["recovered_count"], 1
        )
        self.assertTrue(self.call("review_get_progress", SID)["progress"]["ready"])
        self.sql("UPDATE exam_versions SET is_finalized=true;")
        approved = self.call("finalize_approve_session", SID)
        self.assertEqual(approved["status"], "approved")
        self.migrate()  # Includes the session-level APPROVE_ALL log from actual 007.
        self.assertEqual(
            self.call("finalize_approve_session", SID)["approved_at"], approved["approved_at"]
        )
        self.assertEqual(
            self.call("review_recover_session", SID, worker=True)["recovered_count"], 0
        )
        denied = self.call("review_reserve_regeneration", SID, QID, uuid4(), check=False)
        self.assertIn("REVIEW_LOCKED", denied.stderr)
        self.assertEqual(
            self.value("SELECT count(*) FROM review_logs WHERE action_type='APPROVE_ALL';"), "1"
        )
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "8")

    def test_007_rejects_while_operation_is_active(self):
        self.call("review_accept_question", SID, QID, uuid4())
        self.call("review_reserve_regeneration", SID, QID, uuid4())
        self.sql("UPDATE exam_versions SET is_finalized=true;")
        denied = self.call("finalize_approve_session", SID, check=False)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("ERR_INVALID_SESSION_STATE", denied.stderr)
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
        self.assertEqual(
            self.value("SELECT count(*) FROM review_logs WHERE action_type='APPROVE_ALL';"), "0"
        )


class FreshReviewMigrationChainTests(ReviewMigrationChainTests):
    """Run the same boundaries starting with the product's full initialization SQL."""

    def initialize_database(self):
        type(self).db = f"fresh_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(
            BOOTSTRAP + (ROOT / "backend/scripts/schema.sql").read_text(encoding="utf-8") + SEED
        )

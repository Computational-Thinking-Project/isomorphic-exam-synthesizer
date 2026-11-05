"""TASK-204 Q01, real PostgreSQL 15; opt-in inherited from PostgresCase."""

import json
import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import test_review_rpcs as rpc_fixtures
import test_source_artifacts as artifact_fixtures
from test_review_rpcs import OWNER, SID, SOURCE, literal
from test_stage3_schema import BOOTSTRAP, ROOT

Q01 = ROOT / "backend/migrations/011_source_confirmation_revision.sql"


class SourceRevisionTests(artifact_fixtures.SourceArtifactTests):
    call = artifact_fixtures.SourceArtifactTests.call
    publish = artifact_fixtures.SourceArtifactTests.publish

    def setUp(self):
        artifact_fixtures.SourceArtifactTests.setUp(self)
        for name in (
            "007_finalize_approve_session_rpc.sql",
            "008_finalize_persist_shuffle_rpc.sql",
            "009_finalize_security_boundary.sql",
            "002_replace_source_questions_rpc.sql",
        ):
            self.sql((ROOT / "backend/migrations" / name).read_text(encoding="utf-8"))
        self.sql(Q01.read_text(encoding="utf-8"))
        freeze = ROOT / "backend/migrations/013_source_freeze_guard.sql"
        self.sql(freeze.read_text(encoding="utf-8"))
        self.revision = self.token()

    def token(self):
        return self.value(f"SELECT source_content_revision FROM exam_sessions WHERE id='{SID}';")

    def confirm(self, sources=None, key=None, actor=OWNER, check=True, revision=None):
        # Named args resolve the new overload exactly as PostgREST dispatch does.
        args = dict(
            p_session_id=SID,
            p_actor_id=actor,
            p_confirmation_id=key or self.confirmation_id,
            p_expected_source_revision=revision or self.revision,
            p_sources=json.dumps(self.sources if sources is None else sources),
        )
        sql = (
            rpc_fixtures.ReviewRpcTests.auth("service_role", OWNER)
            + "SELECT public.confirm_source_artifacts("
            + ",".join(f"{k}=>{literal(v)}" for k, v in args.items())
            + ");"
        )
        result = self.sql("SET statement_timeout='6s';" + sql, check=check)
        return json.loads(result.stdout) if check else result

    def preview(self):
        return self.call("get_session_source_preview", SID, worker=False)

    def test_all_mutations_fast_replaces_and_rollback(self):
        last = self.token()
        for statement in (
            "UPDATE source_questions SET raw_content=raw_content||'x'",
            "UPDATE source_questions SET has_security_warning=true",
            f"INSERT INTO source_questions(session_id,question_no,raw_content,options,correct_key) SELECT session_id,2,raw_content,options,correct_key FROM source_questions WHERE id='{SOURCE}'",
            "DELETE FROM source_questions WHERE question_no=2",
        ):
            self.sql(statement)
            self.assertNotEqual(last, self.token())
            last = self.token()
        self.sql("BEGIN; UPDATE source_questions SET raw_content='rollback'; ROLLBACK;")
        self.assertEqual(last, self.token())
        self.sql("UPDATE source_questions SET raw_content=raw_content;")
        self.assertEqual(last, self.token())
        payload = [
            dict(question_no=1, raw_content="New", options=["1", "2", "3", "4"], correct_key="A")
        ]
        replace = f"SELECT replace_source_questions('{SID}',{literal(json.dumps(payload))});"
        # Same transaction: now() timestamps are identical, UUID tokens must differ.
        values = self.value(
            "BEGIN;"
            + replace
            + f"SELECT source_content_revision FROM exam_sessions WHERE id='{SID}';"
            + replace
            + f"SELECT source_content_revision FROM exam_sessions WHERE id='{SID}'; COMMIT;"
        ).splitlines()
        self.assertNotEqual(values[1], values[3])

    def test_stale_no_receipt_valid_replay_acl_and_audit(self):
        self.sql("UPDATE source_questions SET has_security_warning=true;")
        result = self.confirm(check=False)
        self.assertIn("ARTIFACT_STALE", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_confirmations;"), "0")
        self.revision = self.token()
        receipt = self.confirm()
        self.assertEqual(receipt["status"], "blueprinted")
        replay = self.confirm(revision=str(uuid4()))
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["confirmation_id"], receipt["confirmation_id"])
        self.assertEqual(self.value("SELECT count(*) FROM security_events;"), "1")
        for role in ("anon", "authenticated", "service_role"):
            result = self.sql(
                rpc_fixtures.ReviewRpcTests.auth(role, OWNER)
                + f"SELECT confirm_source_artifacts('{SID}'::uuid,'{OWNER}'::uuid,'{uuid4()}'::uuid,now(),'[]'::jsonb);",
                check=False,
            )
            self.assertIn("permission denied", result.stderr)
        self.assertIn(
            "ARTIFACT_OWNER_MISMATCH", self.confirm(actor=str(uuid4()), check=False).stderr
        )

    def test_preview_snapshot_owner_order_and_backfill(self):
        preview = self.preview()
        self.assertEqual(preview["source_revision"], self.revision)
        self.assertEqual(preview["source_questions"][0]["raw_content"], self.row["raw_content"])
        foreign = self.call(
            "get_session_source_preview", SID, worker=False, actor=str(uuid4()), check=False
        )
        self.assertIn("ARTIFACT_NOT_FOUND", foreign.stderr)
        self.sql(f"INSERT INTO exam_sessions(user_id,title) VALUES ('{OWNER}','Clone');")
        self.assertEqual(
            self.value(
                "SELECT count(DISTINCT source_content_revision)=count(*) FROM exam_sessions;"
            ),
            "t",
        )
        # The actual clone DML shape must bump the new parent's default token.
        clone = self.value(f"SELECT id FROM exam_sessions WHERE id<>'{SID}';")
        before = self.value(
            f"SELECT source_content_revision FROM exam_sessions WHERE id='{clone}';"
        )
        self.sql(
            f"INSERT INTO source_questions(session_id,question_no,raw_content,options,correct_key) SELECT '{clone}',question_no,raw_content,options,correct_key FROM source_questions WHERE id='{SOURCE}';"
        )
        self.assertNotEqual(
            before,
            self.value(f"SELECT source_content_revision FROM exam_sessions WHERE id='{clone}';"),
        )

    def hold(self, statement):
        # Wait for the actual backend to enter pg_sleep while holding its lock.
        app = "q01_" + uuid4().hex
        process = subprocess.Popen(
            [
                self.docker,
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
                self.db,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process.stdin.write(
            f"SET application_name='{app}'; BEGIN; {statement}; SELECT pg_sleep(2); COMMIT;\n"
        )
        process.stdin.close()
        process.stdin = None
        for _ in range(60):
            if process.poll() is not None:
                output, err = process.communicate()
                self.fail(f"lock holder exited: {err}")
            if (
                self.value(
                    f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{app}' AND wait_event='PgSleep';"
                )
                == "1"
            ):
                return process
            time.sleep(0.03)
        process.kill()
        self.fail("lock holder did not reach barrier")

    def test_preview_lock_blocks_direct_mutation_and_returns_old_snapshot(self):
        held = self.hold(
            rpc_fixtures.ReviewRpcTests.auth("authenticated", OWNER)
            + f"SELECT get_session_source_preview('{SID}')"
        )
        try:
            with ThreadPoolExecutor() as pool:
                future = pool.submit(
                    self.sql, "UPDATE source_questions SET raw_content='other tab';"
                )
                time.sleep(0.15)
                self.assertFalse(future.done())
                output, err = held.communicate(timeout=8)
                self.assertEqual(held.returncode, 0, err)
                future.result()
            self.assertEqual(json.loads(output.splitlines()[0])["source_revision"], self.revision)
            self.assertNotEqual(self.token(), self.revision)
        finally:
            if held.poll() is None:
                held.kill()

    def test_writer_first_stale_confirm_no_receipt(self):
        held = self.hold("UPDATE source_questions SET solution_md='other tab'")
        try:
            result = self.confirm(check=False)
            held.communicate(timeout=8)
            self.assertIn("ARTIFACT_STALE", result.stderr)
            self.assertEqual(self.value("SELECT count(*) FROM source_artifact_confirmations;"), "0")
        finally:
            if held.poll() is None:
                held.kill()

    def test_confirm_first_replace_refused_and_receipt_replays_on_new_connection(self):
        prepared = literal(json.dumps(self.sources))
        held = self.hold(
            rpc_fixtures.ReviewRpcTests.auth("service_role", OWNER)
            + f"SELECT confirm_source_artifacts('{SID}'::uuid,'{OWNER}'::uuid,'{self.confirmation_id}'::uuid,'{self.revision}'::uuid,{prepared}::jsonb)"
        )
        try:
            result = self.sql(f"SELECT replace_source_questions('{SID}','[]');", check=False)
            held.communicate(timeout=8)
            self.assertIn("not in draft", result.stderr)
            self.assertEqual(self.token(), self.revision)
            self.assertTrue(self.confirm()["replayed"])
        finally:
            if held.poll() is None:
                held.kill()

    def test_upgrade_transaction_rollback_restores_existing_data(self):
        # Separate legacy fixture DB: upgrade DDL and token backfill roll back atomically.
        db = "upgrade_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", "-T", self.db, db)
        script = "ALTER TABLE exam_sessions DROP COLUMN source_content_revision CASCADE;"
        self.sql(script, db=db)
        # Dropping dependent functions is explicit in this disposable clone only.
        self.sql(
            "DROP TRIGGER trg_source_content_revision ON source_questions; DROP FUNCTION _bump_source_content_revision(); DROP FUNCTION get_session_source_preview(uuid); DROP FUNCTION confirm_source_artifacts(uuid,uuid,uuid,uuid,jsonb);",
            db=db,
        )
        migration = Q01.read_text(encoding="utf-8").replace("COMMIT;", "ROLLBACK;")
        self.sql(migration, db=db)
        self.assertEqual(
            self.sql(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='exam_sessions' AND column_name='source_content_revision';",
                db=db,
            ).stdout.strip(),
            "0",
        )

    def test_fresh_current_schema_chain(self):
        db = "fresh_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", db)
        self.sql(
            BOOTSTRAP + (ROOT / "backend/scripts/schema.sql").read_text(encoding="utf-8"), db=db
        )
        for name in (
            "006_stage3_review_and_shuffle.sql",
            "007_finalize_approve_session_rpc.sql",
            "008_finalize_persist_shuffle_rpc.sql",
            "009_finalize_security_boundary.sql",
            "011_source_confirmation_revision.sql",
            "012_source_artifact_supported_modes.sql",
            "013_source_freeze_guard.sql",
        ):
            self.sql((ROOT / "backend/migrations" / name).read_text(encoding="utf-8"), db=db)
        self.assertEqual(
            self.sql(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='exam_sessions' AND column_name='source_content_revision' AND is_nullable='NO';",
                db=db,
            ).stdout.strip(),
            "1",
        )

    def test_owner_cannot_restore_old_token_even_with_table_update_grant(self):
        self.sql("UPDATE source_questions SET has_security_warning=true;")
        current = self.token()
        self.sql(
            "GRANT USAGE ON SCHEMA public TO authenticated; GRANT SELECT,UPDATE ON exam_sessions TO authenticated;"
        )
        result = self.sql(
            rpc_fixtures.ReviewRpcTests.auth("authenticated", OWNER)
            + f"UPDATE exam_sessions SET source_content_revision='{self.revision}' WHERE id='{SID}';",
            check=False,
        )
        self.assertIn("ERR_DIRECT_LIFECYCLE_MUTATION", result.stderr)
        self.assertEqual(current, self.token())

    def test_new_wrapper_rolls_back_receipt_audit_and_state_on_artifact_failure(self):
        self.sql("UPDATE source_questions SET has_security_warning=true;")
        self.revision = self.token()
        self.sql("""CREATE FUNCTION q01_fail_artifact() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'Q01_INJECT_FAILURE'; END $$;
          CREATE TRIGGER q01_fail_artifact BEFORE INSERT ON source_artifact_revisions
          FOR EACH ROW EXECUTE FUNCTION q01_fail_artifact();""")
        result = self.confirm(check=False)
        self.assertIn("Q01_INJECT_FAILURE", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_confirmations;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM security_events;"), "0")
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "draft")
        self.assertEqual(self.token(), self.revision)

    def test_new_wrapper_concurrent_same_key_commits_one_receipt(self):
        from threading import Barrier

        barrier = Barrier(2)

        def confirm():
            barrier.wait(timeout=5)
            return self.confirm()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: confirm(), range(2)))
        self.assertEqual(sorted(r["replayed"] for r in results), [False, True])
        self.assertEqual(len({r["confirmation_id"] for r in results}), 1)
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_confirmations;"), "1")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "1")

    def frozen_snapshot(self):
        return self.value(f"""SELECT jsonb_build_object(
          'session',(SELECT to_jsonb(s) FROM exam_sessions s WHERE id='{SID}'),
          'source',(SELECT jsonb_agg(to_jsonb(q) ORDER BY id) FROM source_questions q WHERE session_id='{SID}'),
          'receipts',(SELECT jsonb_agg(to_jsonb(c) ORDER BY confirmation_id) FROM source_artifact_confirmations c),
          'heads',(SELECT jsonb_agg(to_jsonb(h) ORDER BY source_question_id) FROM source_artifact_heads h),
          'canonical',(SELECT jsonb_agg(to_jsonb(b) ORDER BY blueprint_revision_id) FROM canonical_blueprint_revisions b),
          'audit',(SELECT jsonb_agg(to_jsonb(e) ORDER BY id) FROM security_events e));""")

    def install_source_owner_rls(self):
        # The legacy table-only fixture omits policies; use the actual current ones.
        schema = (ROOT / 'backend/scripts/schema.sql').read_text(encoding='utf-8')
        self.sql('ALTER TABLE exam_sessions ENABLE ROW LEVEL SECURITY; ALTER TABLE source_questions ENABLE ROW LEVEL SECURITY;' +
                 schema[schema.index('-- 4.2. exam_sessions'):schema.index('-- 4.4. question_blueprints')])

    def test_postreview_freeze_preserves_ready_state_for_owner_and_worker(self):
        self.install_source_owner_rls()
        self.sql((ROOT / 'backend/migrations/012_source_artifact_supported_modes.sql').read_text(encoding='utf-8'))
        self.sql('UPDATE source_questions SET has_security_warning=true;')
        self.revision = self.token()
        self.confirm()
        self.publish()
        self.sql('GRANT SELECT,UPDATE ON exam_sessions TO authenticated,service_role; GRANT SELECT,INSERT,UPDATE,DELETE ON source_questions TO authenticated,service_role;')
        state = self.call('get_source_artifacts', SID, worker=False)
        self.assertTrue(state['ready'])
        before = self.frozen_snapshot()
        statements = (
            "UPDATE source_questions SET raw_content='forbidden'",
            "UPDATE source_questions SET has_security_warning=false",
            "UPDATE source_questions SET raw_content=raw_content",
            "DELETE FROM source_questions",
            f"INSERT INTO source_questions(session_id,question_no,raw_content,options,correct_key) VALUES ('{SID}',2,'forbidden','[\"1\",\"2\",\"3\",\"4\"]','A')",
        )
        for role in ('authenticated', 'service_role'):
            for statement in statements:
                with self.subTest(role=role, statement=statement):
                    result = self.sql(rpc_fixtures.ReviewRpcTests.auth(role, OWNER) + statement, check=False)
                    self.assertIn('ARTIFACT_SOURCE_LOCKED', result.stderr)
                    self.assertEqual(self.frozen_snapshot(), before)
                    self.assertEqual(self.call('get_source_artifacts', SID, worker=False), state)

    def test_postreview_draft_warning_clone_cascade_and_foreign_owner(self):
        self.install_source_owner_rls()
        self.sql('GRANT SELECT,UPDATE ON exam_sessions TO authenticated,service_role; GRANT SELECT,INSERT,UPDATE,DELETE ON source_questions TO authenticated,service_role;')
        before = self.token()
        self.sql(rpc_fixtures.ReviewRpcTests.auth('authenticated', OWNER) +
                 f"UPDATE source_questions SET has_security_warning=true WHERE id='{SOURCE}';")
        self.assertNotEqual(before, self.token())
        self.revision = self.token()
        self.sql('UPDATE exam_sessions SET approved_at=clock_timestamp();')
        locked = self.sql("UPDATE source_questions SET has_security_warning=false;", check=False)
        self.assertIn('ARTIFACT_SOURCE_LOCKED', locked.stderr)
        self.assertEqual(self.token(), self.revision)
        self.sql('UPDATE exam_sessions SET approved_at=NULL;')
        foreign = str(uuid4())
        self.sql(rpc_fixtures.ReviewRpcTests.auth('authenticated', foreign) +
                 f"UPDATE source_questions SET raw_content='foreign' WHERE id='{SOURCE}';")
        self.assertEqual(self.token(), self.revision)
        denied = self.sql(rpc_fixtures.ReviewRpcTests.auth('authenticated', foreign) +
            f"INSERT INTO source_questions(session_id,question_no,raw_content,options,correct_key) VALUES ('{SID}',2,'foreign','[\"1\",\"2\",\"3\",\"4\"]','A');", check=False)
        self.assertIn('row-level security', denied.stderr)
        self.confirm()
        self.confirm()
        self.assertEqual(self.value('SELECT count(*) FROM security_events;'), '1')
        clone = str(uuid4())
        self.sql(f"INSERT INTO exam_sessions(id,user_id,title) VALUES ('{clone}','{OWNER}','Clone');")
        self.sql(rpc_fixtures.ReviewRpcTests.auth('authenticated', OWNER) +
            f"INSERT INTO source_questions(session_id,question_no,raw_content,options,correct_key,has_security_warning) SELECT '{clone}',question_no,raw_content,options,correct_key,has_security_warning FROM source_questions WHERE session_id='{SID}';")
        self.assertEqual(self.value(f"SELECT count(*) FROM source_questions WHERE session_id='{clone}';"), '1')
        self.sql(rpc_fixtures.ReviewRpcTests.auth('authenticated', OWNER) +
            f"UPDATE source_questions SET raw_content='draft edit' WHERE session_id='{clone}';")
        self.sql(f"DELETE FROM exam_sessions WHERE id IN ('{SID}','{clone}');")
        self.assertEqual(self.value('SELECT count(*) FROM source_questions;'), '0')

    def test_postreview_confirm_first_direct_writer_is_locked(self):
        prepared = literal(json.dumps(self.sources))
        held = self.hold(rpc_fixtures.ReviewRpcTests.auth('service_role', OWNER) +
            f"SELECT confirm_source_artifacts('{SID}'::uuid,'{OWNER}'::uuid,'{self.confirmation_id}'::uuid,'{self.revision}'::uuid,{prepared}::jsonb)")
        try:
            result = self.sql("SET statement_timeout='6s'; UPDATE source_questions SET has_security_warning=true;", check=False)
            held.communicate(timeout=8)
            self.assertIn('ARTIFACT_SOURCE_LOCKED', result.stderr)
            self.assertEqual(self.token(), self.revision)
            self.assertEqual(self.value('SELECT count(*) FROM source_artifact_confirmations;'), '1')
            self.assertTrue(self.confirm()['replayed'])
        finally:
            if held.poll() is None:
                held.kill()


def load_tests(loader, tests, pattern):
    # Reuse setup helpers without rerunning legacy 006 tests under changed ACLs.
    return unittest.TestSuite(
        SourceRevisionTests(name)
        for name in sorted(SourceRevisionTests.__dict__)
        if name.startswith("test_")
    )

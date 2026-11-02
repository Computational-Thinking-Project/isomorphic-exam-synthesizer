"""Real PostgreSQL tests. Opt in with RUN_POSTGRES_MIGRATION_TESTS=1.

python -m unittest discover -s backend/tests/migrations -v
Uses one disposable container, no network/ports/cloud credentials or host mounts.
"""

import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "backend/migrations/006_stage3_review_and_shuffle.sql"
LEGACY = Path(__file__).parent / "fixtures/legacy_schema.sql"
BOOTSTRAP = """
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('request.jwt.claim.role', true), '') $$;
CREATE SCHEMA storage;
CREATE TABLE storage.buckets (id text PRIMARY KEY, name text, public boolean);
CREATE TABLE storage.objects (bucket_id text, name text);
CREATE FUNCTION storage.foldername(text) RETURNS text[] LANGUAGE sql IMMUTABLE AS
$$ SELECT string_to_array($1, '/') $$;
"""
SEED = """
INSERT INTO auth.users(id,email) VALUES ('00000000-0000-0000-0000-000000000001','fixture@example.invalid');
INSERT INTO public.users(id,email) VALUES ('00000000-0000-0000-0000-000000000001','fixture@example.invalid')
ON CONFLICT (id) DO NOTHING;
INSERT INTO exam_sessions(id,user_id,title,gemini_review_calls) VALUES
('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','Fixture',7);
INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key) VALUES
('20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001',9,'Source','["1","2","3","4"]','A');
INSERT INTO exam_versions(id,session_id,version_code) VALUES
('30000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','101');
INSERT INTO version_questions(id,version_id,source_question_id,question_no,content,options,correct_key,
canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,solution_md) VALUES
('40000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',
'20000000-0000-0000-0000-000000000001',1,'Candidate','["2","1","3","4"]','B',
9,'["1","2","3","4"]','A',NULL,'Display solution');
"""
LEGACY_HISTORY = """
INSERT INTO answer_keys(id,version_id,question_no,correct_option) VALUES
('50000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',1,'B');
INSERT INTO review_logs(id,version_question_id,action_type,reason) VALUES
('60000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001','ACCEPT','Historical reason');
"""


@unittest.skipUnless(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") == "1", "PostgreSQL integration opt-in"
)
class Stage3SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docker = os.getenv("DOCKER_BIN") or shutil.which("docker")
        if not cls.docker:
            raise RuntimeError("Set DOCKER_BIN to the Docker CLI executable")
        cls.container = f"task302-test-{uuid4().hex[:12]}"
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
        type(self).db = f"case_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP + LEGACY.read_text(encoding="utf-8") + SEED)

    def migrate(self, *, check=True):
        return self.sql(MIGRATION.read_text(encoding="utf-8"), check=check)

    def value(self, sql):
        return self.sql(sql).stdout.strip()

    def assert_sql_fails(self, script, expected, *, db=None):
        result = self.sql(script, db=db, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(expected, result.stderr)

    def test_existing_history_upgrade_and_replay_preserve_data(self):
        self.sql(LEGACY_HISTORY)
        self.migrate()
        first = self.value("SELECT row_to_json(l) FROM review_logs l;")
        self.migrate()
        self.assertEqual(first, self.value("SELECT row_to_json(l) FROM review_logs l;"))
        self.assertEqual(
            self.value("SELECT count(*),min(reason),bool_and(user_id IS NULL) FROM review_logs;"),
            "1|Historical reason|t",
        )
        self.assertEqual(
            self.value("SELECT session_id FROM review_logs;"),
            "10000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(
            self.value(
                "SELECT display_no,display_correct_key,canonical_question_no FROM answer_keys;"
            ),
            "1|B|9",
        )
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "7")
        self.assertEqual(
            self.value("SELECT canonical_solution_md IS NULL FROM version_questions;"), "t"
        )

    def test_fresh_full_schema_then_migration_and_replay(self):
        fresh = f"fresh_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", fresh)
        self.sql(
            BOOTSTRAP + (ROOT / "backend/scripts/schema.sql").read_text(encoding="utf-8"), db=fresh
        )
        self.sql(SEED, db=fresh)
        # The initialization schema alone must reject a new missing actor too.
        self.assert_sql_fails(
            """INSERT INTO review_logs(version_question_id,session_id,action_type)
            SELECT q.id,v.session_id,'ACCEPT' FROM version_questions q
            JOIN exam_versions v ON v.id=q.version_id;""",
            "ck_review_logs_actor_required",
            db=fresh,
        )
        self.sql(MIGRATION.read_text(encoding="utf-8"), db=fresh)
        self.sql(MIGRATION.read_text(encoding="utf-8"), db=fresh)
        self.assertEqual(
            self.sql("SELECT count(*) FROM version_questions;", db=fresh).stdout.strip(), "1"
        )

    def test_display_shuffle_preserves_all_canonical_fields(self):
        self.migrate()
        before = self.value(
            "SELECT canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md IS NULL FROM version_questions;"
        )
        self.sql(
            'UPDATE version_questions SET question_no=3,options=\'["4","3","2","1"]\',correct_key=\'D\',solution_md=\'Shuffled\';'
        )
        self.assertEqual(
            before,
            self.value(
                "SELECT canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md IS NULL FROM version_questions;"
            ),
        )
        for assignment in [
            "canonical_question_no=2",
            "canonical_options='[]'",
            "canonical_correct_key='D'",
            "canonical_solution_md='Changed'",
        ]:
            with self.subTest(assignment=assignment):
                self.assert_sql_fails(
                    f"UPDATE version_questions SET {assignment};", "canonical snapshot is immutable"
                )

    def test_new_candidate_can_have_its_own_snapshot_and_history(self):
        self.migrate()
        self.sql("""BEGIN;
        UPDATE version_questions SET is_current=false;
        INSERT INTO version_questions(version_id,source_question_id,question_no,content,options,correct_key,
          canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,regenerated_from_id)
        SELECT version_id,source_question_id,question_no,'New','["5","6","7","8"]','C',
          canonical_question_no,'["5","6","7","8"]','C','New solution',id FROM version_questions;
        COMMIT;""")
        self.assertEqual(
            self.value(
                "SELECT count(*),count(*) FILTER (WHERE is_current) FROM version_questions;"
            ),
            "2|1",
        )
        self.assertEqual(
            self.value("SELECT canonical_correct_key FROM version_questions WHERE is_current;"), "C"
        )
        self.assert_sql_fails(
            "UPDATE version_questions SET is_current=true;", "idx_single_current_version_question"
        )

    def test_both_answer_key_clients_and_conflict_rejection(self):
        self.migrate()
        self.sql("""INSERT INTO answer_keys(version_id,question_no,correct_option)
        VALUES ('30000000-0000-0000-0000-000000000001',1,'B');""")
        self.assertEqual(
            self.value(
                "SELECT display_no,display_correct_key,canonical_question_no FROM answer_keys;"
            ),
            "1|B|9",
        )
        self.sql("DELETE FROM answer_keys;")
        self.sql("""INSERT INTO answer_keys(version_id,display_no,display_correct_key,canonical_question_no)
        VALUES ('30000000-0000-0000-0000-000000000001',1,'B',9);""")
        self.assertEqual(self.value("SELECT question_no,correct_option FROM answer_keys;"), "1|B")
        self.sql("UPDATE answer_keys SET correct_option='C';")
        self.assertEqual(self.value("SELECT display_correct_key FROM answer_keys;"), "C")
        self.sql("UPDATE answer_keys SET display_correct_key='D';")
        self.assertEqual(self.value("SELECT correct_option FROM answer_keys;"), "D")
        self.assert_sql_fails(
            "UPDATE answer_keys SET correct_option='A',display_correct_key='B';",
            "conflicting legacy/display",
        )
        self.assert_sql_fails(
            """INSERT INTO answer_keys(version_id,display_no,display_correct_key,canonical_question_no)
        VALUES ('30000000-0000-0000-0000-000000000001',1,'A',9);""",
            "uq_answer_keys_version_display",
        )

    def test_missing_canonical_after_shuffle_rolls_back_entire_migration(self):
        self.sql(
            "ALTER TABLE version_questions DROP COLUMN canonical_options; UPDATE exam_versions SET is_finalized=true;"
        )
        result = self.migrate(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing canonical data", result.stderr)
        self.assertEqual(
            self.value(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='version_questions' AND column_name='regeneration_id';"
            ),
            "0",
        )

    def test_missing_partial_snapshot_is_not_mixed_with_display_data(self):
        self.sql("ALTER TABLE version_questions DROP COLUMN canonical_options;")
        result = self.migrate(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restore verified canonical snapshot", result.stderr)
        self.assertEqual(
            self.value("SELECT canonical_correct_key,correct_key FROM version_questions;"), "A|B"
        )

    def test_ambiguous_display_mapping_is_not_guessed(self):
        self.sql(
            LEGACY_HISTORY
            + """
        INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key)
          SELECT '20000000-0000-0000-0000-000000000002',session_id,10,raw_content,options,correct_key FROM source_questions;
        INSERT INTO version_questions(version_id,source_question_id,question_no,content,options,correct_key,
          canonical_question_no,canonical_options,canonical_correct_key)
          SELECT version_id,'20000000-0000-0000-0000-000000000002',1,content,options,correct_key,
          10,canonical_options,canonical_correct_key FROM version_questions;
        """
        )
        result = self.migrate(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mapping is missing or ambiguous", result.stderr)

    def test_mismatched_existing_alias_is_not_overwritten(self):
        self.sql(
            LEGACY_HISTORY
            + "ALTER TABLE answer_keys ADD COLUMN display_no int; UPDATE answer_keys SET display_no=3;"
        )
        result = self.migrate(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no value was selected automatically", result.stderr)
        self.assertEqual(self.value("SELECT question_no,display_no FROM answer_keys;"), "1|3")

    def test_partial_upgrade_adds_missing_actor_foreign_key(self):
        self.sql("ALTER TABLE review_logs ADD COLUMN user_id uuid;")
        self.migrate()
        self.assert_sql_fails(
            """INSERT INTO review_logs(version_question_id,session_id,user_id,action_type)
        VALUES ('40000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000099','ACCEPT');""",
            "review_logs_user_id_fkey",
        )

    def test_missing_actor_cannot_be_inserted_even_when_backdated(self):
        self.sql(LEGACY_HISTORY)
        self.migrate()
        for created_at in ["now()", "'2000-01-01'::timestamptz"]:
            with self.subTest(created_at=created_at):
                self.assert_sql_fails(
                    f"""INSERT INTO review_logs(version_question_id,session_id,action_type,created_at)
                    SELECT q.id,v.session_id,'ACCEPT',{created_at} FROM version_questions q
                    JOIN exam_versions v ON v.id=q.version_id;""",
                    "ck_review_logs_actor_required",
                )
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
        self.assertEqual(self.value("SELECT user_id IS NULL FROM review_logs;"), "t")

    def test_known_actor_allowed_but_cannot_be_cleared_later(self):
        self.sql(LEGACY_HISTORY)
        self.migrate()
        self.sql("""INSERT INTO review_logs(version_question_id,session_id,user_id,action_type)
        SELECT q.id,v.session_id,s.user_id,'ACCEPT' FROM version_questions q
        JOIN exam_versions v ON v.id=q.version_id JOIN exam_sessions s ON s.id=v.session_id;""")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "2")
        self.assert_sql_fails(
            "UPDATE review_logs SET user_id=NULL WHERE user_id IS NOT NULL;",
            "ck_review_logs_actor_required",
        )
        self.migrate()
        self.assertEqual(
            self.value(
                "SELECT count(*) FILTER (WHERE user_id IS NULL),count(*) FILTER (WHERE user_id IS NOT NULL) FROM review_logs;"
            ),
            "1|1",
        )
        self.assertEqual(
            self.value(
                "SELECT convalidated FROM pg_constraint WHERE conrelid='review_logs'::regclass AND conname='ck_review_logs_actor_required';"
            ),
            "f",
        )

    def test_historical_null_update_requires_verified_actor(self):
        self.sql(LEGACY_HISTORY)
        self.migrate()
        self.assert_sql_fails(
            "UPDATE review_logs SET reason='Maintenance edit';",
            "ck_review_logs_actor_required",
        )
        # The fixture supplies a verified identity explicitly; production code
        # must not infer that the session owner was the historical actor.
        self.sql("""UPDATE review_logs SET user_id='00000000-0000-0000-0000-000000000001'
        WHERE id='60000000-0000-0000-0000-000000000001';""")
        self.migrate()
        self.assertEqual(
            self.value("SELECT reason,user_id IS NOT NULL FROM review_logs;"),
            "Historical reason|t",
        )

    def test_answer_mapping_missing_rolls_back_without_deleting_history(self):
        self.sql(LEGACY_HISTORY + "UPDATE answer_keys SET question_no=99;")
        result = self.migrate(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mapping is missing or ambiguous", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
        self.assertEqual(
            self.value(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='review_logs' AND column_name='session_id';"
            ),
            "0",
        )

    def test_duplicate_legacy_keys_are_not_silently_deduplicated(self):
        self.sql(
            LEGACY_HISTORY
            + "INSERT INTO answer_keys(version_id,question_no,correct_option) SELECT version_id,question_no,correct_option FROM answer_keys;"
        )
        result = self.migrate(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uq_answer_keys_version_display", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM answer_keys;"), "2")


if __name__ == "__main__":
    unittest.main()

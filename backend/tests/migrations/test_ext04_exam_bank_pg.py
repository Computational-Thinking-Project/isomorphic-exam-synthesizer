"""Rehearse the Bank schema, legacy backfill and capacity contract in PostgreSQL."""

import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from test_export_snapshot_pg import OTHER, OWNER, ExportSnapshotPostgresFixture, auth
from test_ext04_delete_session_pg import BASE, git_output
from test_stage3_schema import BOOTSTRAP, PostgresCase

from app.services.exporter.private_models import ExportClaim
from app.services.exporter.private_service import PrivateExportService

BANK_SCHEMA = Path(__file__).parent / "fixtures/ext04_exam_bank.sql"


class TestExt04ExamBank(PostgresCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_db = f"ext04_bank_template_{uuid4().hex}"
        cls.run_docker("exec", cls.container, "createdb", "-U", "postgres", cls.template_db)
        cls.sql(
            BOOTSTRAP + git_output("show", f"{BASE}:backend/scripts/schema.sql"),
            db=cls.template_db,
        )
        cls.sql("""
            GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
            GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated, service_role;
        """, db=cls.template_db)
        paths = git_output("ls-tree", "-r", "--name-only", BASE, "backend/migrations").splitlines()
        cls.sql(git_output("show", *(f"{BASE}:{path}" for path in paths if path.endswith(".sql"))),
                db=cls.template_db)

    def setUp(self):
        type(self).db = f"ext04_bank_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", "-T", self.template_db, self.db)
        self.approved, self.exported, self.draft, self.foreign, self.version = (uuid4() for _ in range(5))
        self.sql(f"""
            INSERT INTO auth.users (id, email) VALUES
                ('{OWNER}', 'owner@example.invalid'), ('{OTHER}', 'other@example.invalid');
            INSERT INTO public.users (id, email) VALUES
                ('{OWNER}', 'owner@example.invalid'), ('{OTHER}', 'other@example.invalid')
                ON CONFLICT (id) DO NOTHING;
            INSERT INTO public.exam_sessions (id, user_id, title, status, approved_at) VALUES
                ('{self.approved}', '{OWNER}', 'Same name', 'approved', now()),
                ('{self.exported}', '{OWNER}', 'Same name', 'draft', NULL),
                ('{self.draft}', '{OWNER}', 'Draft', 'draft', NULL),
                ('{self.foreign}', '{OTHER}', 'Same name (2)', 'approved', now());
            INSERT INTO public.exam_versions (id, session_id, version_code) VALUES
                ('{self.version}', '{self.approved}', '101'),
                (gen_random_uuid(), '{self.exported}', '007'),
                (gen_random_uuid(), '{self.foreign}', '101');
            INSERT INTO public.source_questions (session_id, question_no, raw_content, options, correct_key)
                VALUES ('{self.exported}', 1, 'Source text', '["a","b","c","d"]', 'A');
            UPDATE public.exam_sessions SET status='exported', approved_at=now() WHERE id='{self.exported}';
            INSERT INTO public.private_export_ledger (
                session_id, packaging_key, revision, packager_version, approved_at, snapshot_title,
                state, phase, token, lease_until, expected
            ) VALUES (
                '{self.exported}', repeat('a', 64), 'sha256:' || repeat('b', 64), 'w4-export-v2',
                now(), 'Same name', 'ready', 'build', gen_random_uuid(), now(),
                jsonb_build_object('sha256', repeat('c', 64), 'filename', 'legacy.zip')
            );
        """)

    def migrate_bank(self):
        self.sql(BANK_SCHEMA.read_text(encoding="utf-8"))

    def table_rows(self, table):
        return json.loads(self.value(
            f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)), '[]') FROM public.{table} t;"
        ))

    def seed_append_draft(self):
        self.sql(f"""
            INSERT INTO public.exam_bank_drafts (
                session_id, owner_id, source_type, source_bank_item_id, source_session_id, source_version_id
            ) SELECT '{self.draft}', '{OWNER}', 'version', bank_item_id, session_id, '{self.version}'
            FROM public.exam_bank_rounds WHERE session_id = '{self.approved}';
        """)

    def test_fresh_bank_starts_empty(self):
        empty_db = f"ext04_empty_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", "-T", self.template_db, empty_db)
        self.sql(BANK_SCHEMA.read_text(encoding="utf-8"), db=empty_db)
        self.assertEqual(
            self.sql("SELECT count(*) FROM public.exam_bank_items;", db=empty_db).stdout.strip(), "0",
        )

    def test_backfill_preserves_identity_and_replays(self):
        source_tables = ("exam_sessions", "exam_versions", "source_questions", "private_export_ledger")
        original = {table: self.table_rows(table) for table in source_tables}
        self.migrate_bank()
        bank_tables = ("exam_bank_items", "exam_bank_rounds", "exam_bank_version_codes")
        first = {table: self.table_rows(table) for table in bank_tables}
        self.migrate_bank()
        self.assertEqual(first, {table: self.table_rows(table) for table in bank_tables})
        self.assertEqual(original, {table: self.table_rows(table) for table in source_tables})
        self.assertEqual(
            self.value("SELECT count(*), count(DISTINCT id) FROM public.exam_bank_items WHERE display_name = 'Same name';"),
            "2|2",
        )
        self.assertEqual(self.value(f"SELECT count(*) FROM public.exam_bank_rounds WHERE session_id = '{self.draft}';"), "0")
        self.assertEqual(self.value("""
            SELECT string_agg(public_version_code, ',' ORDER BY public_version_code)
            FROM public.exam_bank_version_codes;
        """), "007,101,101")
        self.assertEqual(self.value("""
            SELECT bool_and(tags = '{}' AND NOT EXISTS (
                SELECT 1 FROM jsonb_each(metadata) WHERE value <> 'null'::jsonb
            )) FROM public.exam_bank_items;
        """), "t")

    def test_bank_and_mapping_are_visible_only_to_owner_and_cannot_be_written_by_client(self):
        self.migrate_bank()
        self.seed_append_draft()
        for actor, expected in ((OWNER, ("2", "2", "2", "1")), (OTHER, ("1", "1", "1", "0"))):
            for table, count in zip(
                ("exam_bank_items", "exam_bank_rounds", "exam_bank_version_codes", "exam_bank_drafts"), expected
            ):
                self.assertEqual(self.value(auth(actor) + f"SELECT count(*) FROM public.{table};"), count)
        self.assert_sql_fails(auth() + "UPDATE public.exam_bank_items SET display_name='Another title';", "permission denied")
        self.assert_sql_fails(auth() + "SELECT public._backfill_legacy_exam_bank();", "permission denied")
        self.assert_sql_fails(
            auth() + f"SELECT public._bank_capacity_check('{self.draft}', 1);", "permission denied",
        )

    def test_foreign_bank_and_unrelated_versions_cannot_be_bound(self):
        self.migrate_bank()
        self.assert_sql_fails(f"""
            INSERT INTO public.exam_bank_drafts (
                session_id, owner_id, source_type, source_bank_item_id, source_session_id
            ) SELECT '{self.draft}', '{OWNER}', 'original', bank_item_id, session_id
            FROM public.exam_bank_rounds WHERE session_id = '{self.foreign}';
        """, "foreign key constraint")
        self.assert_sql_fails(f"""
            INSERT INTO public.exam_bank_drafts (
                session_id, owner_id, source_type, source_bank_item_id, source_session_id, source_version_id
            ) SELECT '{self.draft}', '{OWNER}', 'version', bank_item_id, session_id, '{self.version}'
            FROM public.exam_bank_rounds WHERE session_id = '{self.exported}';
        """, "foreign key constraint")

    def test_capacity_counts_only_in_domain_codes_and_does_not_write(self):
        self.migrate_bank()
        self.seed_append_draft()
        self.sql(f"""
            CREATE FUNCTION public.test_bank_capacity(uuid, int) RETURNS void
                LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS
                $$ SELECT public._bank_capacity_check($1, $2) $$;
            REVOKE ALL ON FUNCTION public.test_bank_capacity(uuid, int) FROM PUBLIC;
            GRANT EXECUTE ON FUNCTION public.test_bank_capacity(uuid, int) TO authenticated;

            CREATE TEMP TABLE occupied AS
                WITH rounds AS MATERIALIZED (
                    SELECT round_no, gen_random_uuid() AS session_id FROM generate_series(0, 223) round_no
                )
                SELECT code, session_id FROM rounds
                CROSS JOIN LATERAL generate_series(102 + 4 * round_no, 105 + 4 * round_no) code;
            INSERT INTO public.exam_sessions (id, user_id, title, status, approved_at)
                SELECT DISTINCT session_id, '{OWNER}'::uuid, 'Earlier round',
                    'approved'::public.session_status, now() FROM occupied;
            INSERT INTO public.exam_bank_rounds (session_id, bank_item_id, owner_id)
                SELECT DISTINCT o.session_id, b.id, b.owner_id FROM occupied o
                CROSS JOIN public.exam_bank_items b WHERE b.first_session_id = '{self.approved}';
            INSERT INTO public.exam_versions (session_id, version_code)
                SELECT session_id, ((code - 102) % 4 + 101)::text FROM occupied;
            INSERT INTO public.exam_bank_version_codes (version_id, session_id, bank_item_id, public_version_code)
                SELECT v.id, v.session_id, r.bank_item_id, o.code::text FROM occupied o
                JOIN public.exam_versions v ON v.session_id = o.session_id AND v.version_code = ((code - 102) % 4 + 101)::text
                JOIN public.exam_bank_rounds r ON r.session_id = v.session_id;
            WITH v AS (
                INSERT INTO public.exam_versions (session_id, version_code)
                VALUES ('{self.approved}', '007') RETURNING id
            )
            INSERT INTO public.exam_bank_version_codes (version_id, session_id, bank_item_id, public_version_code)
                SELECT v.id, r.session_id, r.bank_item_id, '007' FROM v
                JOIN public.exam_bank_rounds r ON r.session_id = '{self.approved}';
        """)
        before = self.table_rows("exam_bank_version_codes")

        def call(count, actor=OWNER):
            return auth(actor) + f"SELECT public.test_bank_capacity('{self.draft}', {count});"

        self.sql(call(2))
        self.assert_sql_fails(call(3), "ERR_BANK_CAPACITY_EXCEEDED")
        self.assert_sql_fails(call(2, OTHER), "ERR_SESSION_NOT_FOUND")
        self.assert_sql_fails(call(5), "ERR_CONFIG_CONFLICT")
        self.sql(f"UPDATE public.exam_bank_drafts SET save_action='create_new' WHERE session_id='{self.draft}';")
        self.sql(call(4))
        self.sql(f"""
            UPDATE public.exam_bank_drafts SET save_action=NULL, metadata=metadata || '{{"school":"Other"}}'
            WHERE session_id='{self.draft}';
        """)
        self.sql(call(4))
        self.assertEqual(before, self.table_rows("exam_bank_version_codes"))


class TestExt04BankLegacyExport(ExportSnapshotPostgresFixture):
    def test_reapplying_bank_fixture_preserves_the_actual_legacy_projection_and_key(self):
        self.approve()
        before = self.load()
        ledger = Mock()
        ledger.read.return_value = ExportClaim("idle")
        export = PrivateExportService(lambda _ident, _actor: self.load(), ledger, Mock())
        export.status(self.sid, OWNER)
        identity = ledger.read.call_args.args[0]
        sql = BANK_SCHEMA.read_text(encoding="utf-8")
        self.sql(sql)
        self.sql(sql)
        after = self.load()
        self.assertEqual(after, before)
        export.status(self.sid, OWNER)
        self.assertEqual(ledger.read.call_args.args[0], identity)

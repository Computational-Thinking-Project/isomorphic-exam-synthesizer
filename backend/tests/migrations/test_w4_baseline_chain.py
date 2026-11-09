"""Local-only baseline rehearsal; never accepts an external DSN.

RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover \
    -s backend/tests/migrations -p test_w4_baseline_chain.py -v

The five-table case models reported table presence, NOT unknown production DDL.
All rows are synthetic. Each case creates a new database in a network-none
PostgreSQL 15 container via the existing PostgresCase safety boundary.
"""

import json
import re
import subprocess
from uuid import uuid4

from test_stage3_schema import BOOTSTRAP, ROOT, PostgresCase

TABLES = ("users", "exam_sessions", "source_questions", "question_blueprints", "exam_versions")
PR52 = "598b959c69c0f1c6362daed50fd544cb09dd73f7"


class W4BaselineChainTests(PostgresCase):
    def setUp(self):
        type(self).db = "w4_baseline_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP)

    def seed_partial_schema(self):
        schema = (ROOT / "backend/scripts/schema.sql").read_text()
        self.sql(schema[:schema.index("-- 2. TABLES DEFINITION")])
        for table in TABLES:
            match = re.search(
                rf"CREATE TABLE IF NOT EXISTS public\.{table} \(.*?\n\);", schema, re.S
            )
            self.assertIsNotNone(match, table)
            self.sql(match.group())
        # 2 users + 4 sessions + 8 sources + 4 blueprints + 4 versions = 22 rows.
        self.sql("""
            INSERT INTO auth.users(id,email)
              SELECT md5('user'||i)::uuid,'test'||i||'@example.invalid' FROM generate_series(1,2) i;
            INSERT INTO public.users(id,email) SELECT id,email FROM auth.users;
            INSERT INTO exam_sessions(id,user_id,title)
              SELECT md5('session'||i)::uuid,md5('user1')::uuid,'Synthetic '||i FROM generate_series(1,4) i;
            INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key)
              SELECT md5('source'||i)::uuid,md5('session'||((i+1)/2))::uuid,
                     ((i-1)%2)+1,'Synthetic source '||i,'["1","2","3","4"]','A'
              FROM generate_series(1,8) i;
            INSERT INTO question_blueprints(source_question_id)
              SELECT md5('source'||i)::uuid FROM generate_series(1,4) i;
            INSERT INTO exam_versions(session_id,version_code)
              SELECT md5('session'||i)::uuid,'101' FROM generate_series(1,4) i;
        """)
        count = self.value("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
        self.assertEqual(count, "5")
        return self.snapshot()

    def snapshot(self):
        # Later migrations legitimately add columns. Compare every original field
        # and value, including IDs/timestamps; require unchanged row cardinalities.
        return {
            table: json.loads(self.value(
                f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]') FROM public.{table} t"
            )) for table in TABLES
        }

    def apply_chain(self, candidate=False):
        self.sql((ROOT / "backend/scripts/schema.sql").read_text())
        for number in range(2, 17):
            paths = list((ROOT / "backend/migrations").glob(f"{number:03}_*.sql"))
            self.assertEqual(len(paths), 1)
            self.sql(paths[0].read_text())
        if candidate:
            # Read immutable PR bytes; do not copy into numbered migration history.
            sql = subprocess.check_output([
                "git", "show", f"{PR52}:backend/migrations/017_generation_lifecycle_recovery.sql"
            ], cwd=ROOT, text=True)
            self.sql(sql)

    def assert_contract(self, candidate=False):
        for signature in (
            "get_session_source_preview(uuid)",
            "confirm_source_artifacts(uuid,uuid,uuid,uuid,jsonb)",
            "get_generation_source_snapshot(uuid)",
            "save_generation_config(uuid,integer,jsonb,jsonb,jsonb)",
            "persist_generation_clone(uuid,uuid,jsonb)",
        ):
            self.assertEqual(self.value(f"SELECT to_regprocedure('public.{signature}') IS NOT NULL"), "t")
        self.assertEqual(self.value("""
            SELECT has_function_privilege('authenticated',
              'public.save_generation_config(uuid,integer,jsonb,jsonb,jsonb)', 'EXECUTE')
              AND NOT has_function_privilege('anon',
              'public.save_generation_config(uuid,integer,jsonb,jsonb,jsonb)', 'EXECUTE')
        """), "t")
        self.assertEqual(self.value("""
            SELECT relrowsecurity FROM pg_class WHERE oid='public.generation_configs'::regclass
        """), "t")
        self.assertEqual(self.value("""
            SELECT count(*) FROM pg_trigger WHERE tgrelid='public.source_questions'::regclass
              AND tgname='trg_00_source_freeze_guard'
        """), "1")
        if candidate:
            self.assertEqual(self.value("""
                SELECT to_regprocedure('public.list_stale_generation_jobs(integer,integer,timestamp with time zone,uuid)') IS NOT NULL
            """), "t")

    def rehearse(self, populated=False, candidate=False):
        before = self.seed_partial_schema() if populated else None
        self.apply_chain(candidate)
        self.assert_contract(candidate)
        if before is not None:
            after = self.snapshot()
            for table, rows in before.items():
                self.assertEqual(len(after[table]), len(rows), table)
                for old, new in zip(rows, after[table]):
                    self.assertEqual(old, {k: new[k] for k in old}, table)

    def test_fresh_002_through_016(self):
        self.rehearse()

    def test_synthetic_five_table_upgrade_22_rows_preserved(self):
        self.rehearse(populated=True)

    def test_fresh_with_unmerged_candidate_017(self):
        self.rehearse(candidate=True)

    def test_synthetic_upgrade_with_unmerged_candidate_017(self):
        self.rehearse(populated=True, candidate=True)

    def test_fresh_018_privileges_and_replay(self):
        self.apply_chain(candidate=True)
        migration = (ROOT / "backend/migrations/018_w4_source_readiness_config.sql").read_text()
        self.sql(migration)
        self.assert_contract(candidate=True)
        before = self.value("SELECT pg_get_functiondef('public.save_generation_config(uuid,int,jsonb,jsonb,jsonb)'::regprocedure)")
        self.sql(migration)
        self.assertEqual(self.value("SELECT pg_get_functiondef('public.save_generation_config(uuid,int,jsonb,jsonb,jsonb)'::regprocedure)"), before)
        self.assertEqual(self.value("""
            SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace
              AND proname='save_generation_config'
        """), "1")
        self.assertEqual(self.value("""
            SELECT NOT has_table_privilege('authenticated','generation_configs','UPDATE')
              AND NOT has_table_privilege('authenticated','generation_configs','INSERT')
        """), "t")

    def test_018_populated_upgrade_preserves_explicit_historical_config(self):
        self.seed_partial_schema()
        self.apply_chain(candidate=True)
        self.sql("""
            INSERT INTO generation_configs(session_id,n_versions,active_variation_modes,ordering_preferences)
              SELECT id,2,'["NUMERICAL"]','{"shuffle_questions":true,"shuffle_options":true}'
              FROM exam_sessions ORDER BY id LIMIT 1;
        """)
        before = self.value("SELECT jsonb_agg(to_jsonb(c)) FROM generation_configs c")
        sources = self.snapshot()
        self.sql((ROOT / "backend/migrations/018_w4_source_readiness_config.sql").read_text())
        self.assertEqual(self.value("SELECT jsonb_agg(to_jsonb(c)) FROM generation_configs c"), before)
        self.assertEqual(self.snapshot(), sources)
        self.sql("""
            INSERT INTO generation_configs(session_id,n_versions)
              SELECT id,1 FROM exam_sessions WHERE id NOT IN (SELECT session_id FROM generation_configs) LIMIT 1
        """)
        self.assertEqual(json.loads(self.value("SELECT ordering_preferences FROM generation_configs WHERE n_versions=1")),
                         {"shuffle_questions": False, "shuffle_options": False})

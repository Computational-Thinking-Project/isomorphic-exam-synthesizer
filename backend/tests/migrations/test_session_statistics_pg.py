import json
from uuid import uuid4

from test_export_snapshot_pg import OTHER, OWNER, auth
from test_stage3_schema import BOOTSTRAP, ROOT, PostgresCase

EMPTY = "00000000-0000-0000-0000-000000000013"


class TestSessionStatisticsPostgres(PostgresCase):
    def setUp(self):
        type(self).db = "statistics_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP + (ROOT / "backend/scripts/schema.sql").read_text(encoding="utf-8"))
        self.sql("""
            GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
            GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated, service_role;
        """)
        for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
            self.sql(migration.read_text(encoding="utf-8-sig"))

    def counts(self, actor):
        output = self.value(auth(actor) + "SELECT public.get_my_session_status_counts();")
        return {row["status"]: row["count"] for row in json.loads(output.splitlines()[-1])}

    def test_owner_counts_and_invoker_privileges(self):
        self.sql(f"""
            INSERT INTO auth.users(id, email) VALUES
                ('{OWNER}', 'owner@example.invalid'), ('{OTHER}', 'other@example.invalid'),
                ('{EMPTY}', 'empty@example.invalid');
            INSERT INTO public.users(id, email) SELECT id, email FROM auth.users ON CONFLICT DO NOTHING;
            INSERT INTO public.exam_sessions(user_id, title)
                SELECT '{OWNER}', 'Draft ' || n FROM generate_series(1, 1005) AS n;
            INSERT INTO public.exam_sessions(user_id, title) VALUES ('{OTHER}', 'Foreign exam');
            UPDATE public.exam_sessions SET status = 'approved', approved_at = now() WHERE user_id = '{OTHER}';
        """)
        assert self.value("""
            SELECT NOT p.prosecdef AND c.relrowsecurity
            FROM pg_proc AS p CROSS JOIN pg_class AS c
            WHERE p.oid = 'public.get_my_session_status_counts()'::regprocedure
              AND c.oid = 'public.exam_sessions'::regclass;
        """) == "t"
        assert self.counts(OWNER) == {"draft": 1005}
        assert self.counts(OTHER) == {"approved": 1}
        assert self.counts(EMPTY) == {}
        self.assert_sql_fails(
            auth(OWNER, "anon") + "SELECT public.get_my_session_status_counts();",
            "permission denied for function",
        )

        self.sql(f"UPDATE public.exam_sessions SET status = 'exported' WHERE user_id = '{OTHER}';")
        assert self.counts(OTHER) == {"exported": 1}

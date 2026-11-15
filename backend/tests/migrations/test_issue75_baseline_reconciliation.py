"""Focused PostgreSQL 15 tests for Issue #75 / PR #76 baseline reconciliation.

Verifies:
- T01: Partial five-table baseline upgrade via 003b without executing full schema.sql.
- T02: Complete candidate chain execution (003b, 004-019, 021-022) on partial baseline.
- T03: Safe idempotent replay of 003b after full hardening (009, 015, 022).
- T04: Incompatible pre-existing enum rejection (fail closed, atomicity).
- T05: Incompatible pre-existing table rejection (fail closed, retain data).
- T06: Authenticated A/B direct reads (owner read allowed, cross-user read denied).
- T07: Forbidden direct writes after hardening (direct DML denied, RPC allowed).
- T08: Security events isolation (owner read, trusted insert, untrusted write blocked).
- T12: get_session_source_preview contract and authorization on partial upgrade path.
- T13: Real canonical-ready config save, reload, resave and cross-user denial.

Opt in with RUN_POSTGRES_MIGRATION_TESTS=1.
"""

import json
import os
import unittest
from uuid import uuid4

from test_stage3_schema import BOOTSTRAP, ROOT, PostgresCase

TABLES_5 = ("users", "exam_sessions", "source_questions", "question_blueprints", "exam_versions")
TABLES_RECONCILED = ("generation_configs", "version_questions", "answer_keys", "review_logs", "security_events")

USER_A = "00000000-0000-0000-0000-00000000000a"
USER_B = "00000000-0000-0000-0000-00000000000b"
SESSION_A = "10000000-0000-0000-0000-000000000001"
SESSION_B = "10000000-0000-0000-0000-000000000002"
SOURCE_A1 = "20000000-0000-0000-0000-000000000001"
SOURCE_A2 = "20000000-0000-0000-0000-000000000002"
SOURCE_B1 = "20000000-0000-0000-0000-000000000003"
VERSION_A = "30000000-0000-0000-0000-000000000001"
VERSION_B = "30000000-0000-0000-0000-000000000002"

CANDIDATE_CHAIN = [
    "003b_reconcile_baseline.sql",
    "004_save_generation_config_rpc.sql",
    "005_generation_job_operations_rpc.sql",
    "006_stage3_review_and_shuffle.sql",
    "007_finalize_approve_session_rpc.sql",
    "008_finalize_persist_shuffle_rpc.sql",
    "009_finalize_security_boundary.sql",
    # 010 is empty historical migration; intentionally omitted from execution
    "011_source_confirmation_revision.sql",
    "012_source_artifact_supported_modes.sql",
    "013_source_freeze_guard.sql",
    "014_disable_legacy_source_confirmation.sql",
    "015_stage2_canonical_w2_integration.sql",
    "016_stage2_original_clone.sql",
    "017_generation_lifecycle_recovery.sql",
    "018_review_current_snapshot.sql",
    "019_w4_source_readiness_config.sql",
    "021_w4_confirmed_source_fallback.sql",
    "022_w4_generation_solution_guard.sql",
]


@unittest.skipUnless(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") == "1", "PostgreSQL integration opt-in"
)
class Issue75BaselineReconciliationTests(PostgresCase):
    def setUp(self):
        # Override default setUp to avoid loading full legacy schema.
        type(self).db = "issue75_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP)

    def as_role(self, role, user_id, sql_query):
        """Execute a query inside a transaction as a specific role and JWT subject."""
        script = f"""
            BEGIN;
            DO $$ BEGIN
                PERFORM set_config('request.jwt.claim.sub', '{user_id}', true);
                PERFORM set_config('request.jwt.claim.role', '{role}', true);
            END $$;
            SET LOCAL ROLE {role};
            {sql_query};
            COMMIT;
        """
        result = self.sql(script)
        return result.stdout.strip()

    def as_role_fail(self, role, user_id, sql_query):
        """Execute a statement expected to fail as a specific role."""
        script = f"""
            BEGIN;
            DO $$ BEGIN
                PERFORM set_config('request.jwt.claim.sub', '{user_id}', true);
                PERFORM set_config('request.jwt.claim.role', '{role}', true);
            END $$;
            SET LOCAL ROLE {role};
            {sql_query};
            COMMIT;
        """
        return self.sql(script, check=False)

    def seed_five_table_baseline(self):
        """Build a synthetic 5-table schema baseline with historical 002 & 003 applied."""
        self.sql("""
            CREATE TYPE public.session_status AS ENUM (
                'draft', 'blueprinted', 'configured', 'generating', 'partial_generated',
                'generated', 'reviewed', 'approved', 'exported', 'failed'
            );

            CREATE TABLE public.users (
                id UUID PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                avatar_url TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE public.exam_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT 'Toán',
                grade INT NOT NULL DEFAULT 12,
                status public.session_status NOT NULL DEFAULT 'draft',
                gemini_call_count INT NOT NULL DEFAULT 0,
                retry_count INT NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE public.source_questions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
                question_no INT NOT NULL,
                raw_content TEXT NOT NULL,
                options JSONB NOT NULL,
                correct_key TEXT NOT NULL,
                solution_md TEXT,
                has_missing_answer BOOLEAN NOT NULL DEFAULT FALSE,
                has_security_warning BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE public.question_blueprints (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_question_id UUID NOT NULL REFERENCES public.source_questions(id) ON DELETE CASCADE,
                variation_modes JSONB NOT NULL DEFAULT '["NUMERICAL"]'::jsonb,
                confirmed_at TIMESTAMPTZ,
                is_fallback BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE public.exam_versions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
                version_code TEXT NOT NULL,
                is_finalized BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_exam_versions_code UNIQUE (session_id, version_code)
            );

            -- RLS baseline for initial 5 tables
            ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
            ALTER TABLE public.exam_sessions ENABLE ROW LEVEL SECURITY;
            ALTER TABLE public.source_questions ENABLE ROW LEVEL SECURITY;
            ALTER TABLE public.question_blueprints ENABLE ROW LEVEL SECURITY;
            ALTER TABLE public.exam_versions ENABLE ROW LEVEL SECURITY;

            CREATE POLICY "Users can manage own profile" ON public.users
                FOR ALL USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

            CREATE POLICY "Users can manage own exam sessions" ON public.exam_sessions
                FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

            CREATE POLICY "Users can manage source questions in their sessions" ON public.source_questions
                FOR ALL USING (
                    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
                ) WITH CHECK (
                    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
                );

            CREATE POLICY "Users can manage blueprints in their questions" ON public.question_blueprints
                FOR ALL USING (
                    source_question_id IN (
                        SELECT sq.id FROM public.source_questions sq
                        JOIN public.exam_sessions s ON sq.session_id = s.id
                        WHERE s.user_id = auth.uid()
                    )
                ) WITH CHECK (
                    source_question_id IN (
                        SELECT sq.id FROM public.source_questions sq
                        JOIN public.exam_sessions s ON sq.session_id = s.id
                        WHERE s.user_id = auth.uid()
                    )
                );

            CREATE POLICY "Users can manage exam versions in their sessions" ON public.exam_versions
                FOR ALL USING (
                    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
                ) WITH CHECK (
                    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
                );

            -- Default Supabase-compatible table grants
            REVOKE INSERT, UPDATE ON TABLE public.exam_sessions FROM PUBLIC, anon, authenticated;
            GRANT INSERT (user_id, title, subject, grade) ON TABLE public.exam_sessions TO authenticated;
            GRANT UPDATE (title, subject, grade) ON TABLE public.exam_sessions TO authenticated;
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO authenticated;
            GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
        """)

        # Apply historical migrations 002 and 003
        for m_name in ("002_replace_source_questions_rpc.sql", "003_confirm_exam_source_rpc.sql"):
            path = ROOT / "backend/migrations" / m_name
            self.sql(path.read_text(encoding="utf-8"))

        # Seed synthetic records for User A and User B
        self.sql(f"""
            INSERT INTO auth.users(id, email) VALUES
                ('{USER_A}', 'usera@example.invalid'),
                ('{USER_B}', 'userb@example.invalid');

            INSERT INTO public.users(id, email, name) VALUES
                ('{USER_A}', 'usera@example.invalid', 'Teacher A'),
                ('{USER_B}', 'userb@example.invalid', 'Teacher B');

            INSERT INTO public.exam_sessions(id, user_id, title, status) VALUES
                ('{SESSION_A}', '{USER_A}', 'Session A Draft', 'draft'),
                ('{SESSION_B}', '{USER_B}', 'Session B Draft', 'draft');

            INSERT INTO public.source_questions(id, session_id, question_no, raw_content, options, correct_key) VALUES
                ('{SOURCE_A1}', '{SESSION_A}', 1, 'Question A1', '["1","2","3","4"]', 'A'),
                ('{SOURCE_A2}', '{SESSION_A}', 2, 'Question A2', '["5","6","7","8"]', 'B'),
                ('{SOURCE_B1}', '{SESSION_B}', 1, 'Question B1', '["9","10","11","12"]', 'C');

            INSERT INTO public.question_blueprints(source_question_id) VALUES
                ('{SOURCE_A1}'),
                ('{SOURCE_A2}'),
                ('{SOURCE_B1}');

            INSERT INTO public.exam_versions(id, session_id, version_code) VALUES
                ('{VERSION_A}', '{SESSION_A}', '101'),
                ('{VERSION_B}', '{SESSION_B}', '101');
        """)
        return self.snapshot_5_tables()

    def snapshot_5_tables(self):
        return {
            table: json.loads(self.value(
                f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]') FROM public.{table} t"
            )) for table in TABLES_5
        }

    def apply_migration(self, filename):
        path = ROOT / "backend/migrations" / filename
        self.sql(path.read_text(encoding="utf-8"))

    def test_t01_partial_five_table_to_003b_reconciliation(self):
        """T01: 5-table baseline -> 003b: missing tables created, RLS enabled, rows preserved."""
        before = self.seed_five_table_baseline()

        # Apply 003b
        self.apply_migration("003b_reconcile_baseline.sql")

        # Verify all 5 reconciled tables now exist
        for tbl in TABLES_RECONCILED:
            self.assertEqual(
                self.value(f"SELECT to_regclass('public.{tbl}') IS NOT NULL;"),
                "t",
                f"Table {tbl} must exist after 003b"
            )
            # RLS must be enabled
            self.assertEqual(
                self.value(f"SELECT relrowsecurity FROM pg_class WHERE oid = 'public.{tbl}'::regclass;"),
                "t",
                f"RLS must be enabled on {tbl}"
            )

        # Verify enum types exist with expected labels
        self.assertEqual(self.value("SELECT to_regtype('public.question_status') IS NOT NULL;"), "t")
        self.assertEqual(self.value("SELECT to_regtype('public.review_action_type') IS NOT NULL;"), "t")

        # Verify permissions: authenticated has SELECT only, no direct writes
        for tbl in TABLES_RECONCILED:
            self.assertEqual(
                self.value(f"SELECT has_table_privilege('authenticated', 'public.{tbl}', 'SELECT');"),
                "t",
                f"authenticated should have SELECT on {tbl}"
            )
            for priv in ("INSERT", "UPDATE", "DELETE"):
                self.assertEqual(
                    self.value(f"SELECT has_table_privilege('authenticated', 'public.{tbl}', '{priv}');"),
                    "f",
                    f"authenticated must NOT have {priv} on {tbl}"
                )

        # Verify anon has NO permissions on reconciled tables
        for tbl in TABLES_RECONCILED:
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                self.assertEqual(
                    self.value(f"SELECT has_table_privilege('anon', 'public.{tbl}', '{priv}');"),
                    "f",
                    f"anon must NOT have {priv} on {tbl}"
                )

        # Verify owner-read policy on generation_configs
        self.assertEqual(
            self.value("""
                SELECT count(*) FROM pg_policies
                WHERE schemaname = 'public' AND tablename = 'generation_configs'
                  AND policyname = 'generation_configs_owner_read';
            """),
            "1"
        )

        # Verify existing 5-table rows are 100% preserved
        after = self.snapshot_5_tables()
        for tbl in TABLES_5:
            self.assertEqual(len(after[tbl]), len(before[tbl]), f"Row count mismatch on {tbl}")
            for old_row, new_row in zip(before[tbl], after[tbl]):
                self.assertEqual(old_row, {k: new_row[k] for k in old_row}, f"Data mutation on {tbl}")

    def test_t02_partial_five_table_through_full_candidate_chain(self):
        """T02: Partial 5-table baseline -> 003b -> full candidate chain (004-019, 021-022)."""
        before = self.seed_five_table_baseline()

        # Apply the entire candidate chain sequentially
        for m_name in CANDIDATE_CHAIN:
            self.apply_migration(m_name)

        # Assert key contracts after full chain
        for signature in (
            "get_session_source_preview(uuid)",
            "confirm_source_artifacts(uuid,uuid,uuid,uuid,jsonb)",
            "get_generation_source_snapshot(uuid)",
            "save_generation_config(uuid,integer,jsonb,jsonb,jsonb)",
            "persist_generation_clone(uuid,uuid,jsonb)",
            "get_review_current_snapshot(uuid)",
            "list_stale_generation_jobs(integer,integer,timestamp with time zone,uuid)",
        ):
            self.assertEqual(
                self.value(f"SELECT to_regprocedure('public.{signature}') IS NOT NULL;"),
                "t",
                f"RPC public.{signature} must exist"
            )

        # Check source_content_revision column added by 011 with default
        rev_count = self.value("SELECT count(*) FROM exam_sessions WHERE source_content_revision IS NOT NULL;")
        self.assertEqual(rev_count, "2")

        # Verify original rows are preserved across the entire migration chain
        after = self.snapshot_5_tables()
        for tbl in TABLES_5:
            self.assertEqual(len(after[tbl]), len(before[tbl]), f"Row count mismatch on {tbl}")
            for old_row, new_row in zip(before[tbl], after[tbl]):
                self.assertEqual(old_row, {k: new_row[k] for k in old_row}, f"Data mutation on {tbl}")

    def test_t03_replay_003b_after_full_chain_preserves_hardening(self):
        """T03: Replay 003b after full chain does not restore authenticated writes or mutate rows."""
        self.seed_five_table_baseline()
        for m_name in CANDIDATE_CHAIN:
            self.apply_migration(m_name)

        # Capture policies, grants, and rows before replay
        priv_before = {
            tbl: {
                priv: self.value(f"SELECT has_table_privilege('authenticated', 'public.{tbl}', '{priv}');")
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE")
            } for tbl in ("generation_configs", "version_questions", "answer_keys", "review_logs")
        }
        rows_before = self.snapshot_5_tables()

        # Replay 003b in an isolated step
        self.apply_migration("003b_reconcile_baseline.sql")

        # Verify privileges are identical: authenticated STILL CANNOT WRITE
        for tbl, privs in priv_before.items():
            for priv, expected in privs.items():
                actual = self.value(f"SELECT has_table_privilege('authenticated', 'public.{tbl}', '{priv}');")
                self.assertEqual(
                    actual, expected,
                    f"Privilege {priv} on {tbl} changed after 003b replay (was {expected}, now {actual})"
                )
                if priv in ("INSERT", "UPDATE", "DELETE"):
                    self.assertEqual(actual, "f", f"Direct write {priv} on {tbl} must remain denied")

        # Verify data rows unchanged
        rows_after = self.snapshot_5_tables()
        self.assertEqual(rows_before, rows_after)

    def test_t04_incompatible_existing_enum_rejection(self):
        """T04: Pre-existing question_status enum missing required labels fails atomically."""
        self.seed_five_table_baseline()
        # Create an incompatible question_status enum
        self.sql("CREATE TYPE public.question_status AS ENUM ('draft_only', 'archived');")

        # Running 003b must fail with descriptive message
        res = self.sql((ROOT / "backend/migrations/003b_reconcile_baseline.sql").read_text(encoding="utf-8"), check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("003b: existing question_status enum is incompatible, missing labels", res.stderr)

        # Verify rollback: reconciled tables were NOT created
        self.assertEqual(self.value("SELECT to_regclass('public.generation_configs') IS NULL;"), "t")

    def test_t05_incompatible_existing_table_rejection(self):
        """T05: Pre-existing incompatible table (e.g. view) fails atomically and preserves data."""
        before = self.seed_five_table_baseline()
        # Create an incompatible object: generation_configs as a view instead of table
        self.sql("CREATE VIEW public.generation_configs AS SELECT 1 AS dummy;")

        res = self.sql((ROOT / "backend/migrations/003b_reconcile_baseline.sql").read_text(encoding="utf-8"), check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("003b: public.generation_configs exists but is not a regular table", res.stderr)

        # Baseline rows retained
        after = self.snapshot_5_tables()
        self.assertEqual(before, after)

    def test_t06_authenticated_direct_reads_ab_isolation(self):
        """T06: Authenticated User A can read own generation_config; User A cannot read User B's."""
        self.seed_five_table_baseline()
        self.apply_migration("003b_reconcile_baseline.sql")

        # Insert generation configs as service_role for sessions A and B
        self.sql(f"""
            INSERT INTO public.generation_configs(session_id, n_versions) VALUES
                ('{SESSION_A}', 2),
                ('{SESSION_B}', 3);
        """)

        # Execute direct SELECT as User A
        count_a = self.as_role("authenticated", USER_A, "SELECT count(*) FROM public.generation_configs")
        self.assertEqual(count_a, "1", "User A should see exactly 1 generation_config (their own)")

        # Verify User A sees session A's config and NOT session B's config
        visible_session = self.as_role("authenticated", USER_A, "SELECT session_id FROM public.generation_configs")
        self.assertEqual(visible_session, SESSION_A)

        # Execute direct SELECT as User B
        count_b = self.as_role("authenticated", USER_B, "SELECT count(*) FROM public.generation_configs")
        self.assertEqual(count_b, "1", "User B should see exactly 1 generation_config (their own)")

        visible_session_b = self.as_role("authenticated", USER_B, "SELECT session_id FROM public.generation_configs")
        self.assertEqual(visible_session_b, SESSION_B)

    def test_t07_forbidden_direct_writes_after_hardening(self):
        """T07: Authenticated direct INSERT/UPDATE/DELETE on generation_configs fails."""
        self.seed_five_table_baseline()
        for m_name in CANDIDATE_CHAIN:
            self.apply_migration(m_name)

        # Attempt direct INSERT as User A -> Permission Denied
        insert_res = self.as_role_fail(
            "authenticated", USER_A,
            f"INSERT INTO public.generation_configs(session_id, n_versions) VALUES ('{SESSION_A}', 2)"
        )
        self.assertNotEqual(insert_res.returncode, 0)
        self.assertIn("permission denied for table generation_configs", insert_res.stderr)

        # Attempt direct UPDATE as User A -> Permission Denied
        update_res = self.as_role_fail(
            "authenticated", USER_A,
            f"UPDATE public.generation_configs SET n_versions = 4 WHERE session_id = '{SESSION_A}'"
        )
        self.assertNotEqual(update_res.returncode, 0)
        self.assertIn("permission denied for table generation_configs", update_res.stderr)

        # Attempt direct DELETE as User A -> Permission Denied
        delete_res = self.as_role_fail(
            "authenticated", USER_A,
            f"DELETE FROM public.generation_configs WHERE session_id = '{SESSION_A}'"
        )
        self.assertNotEqual(delete_res.returncode, 0)
        self.assertIn("permission denied for table generation_configs", delete_res.stderr)

    def test_t08_security_events_isolation_and_trusted_insert(self):
        """T08: security_events allows service_role insert, owner read, blocks untrusted writes."""
        self.seed_five_table_baseline()
        self.apply_migration("003b_reconcile_baseline.sql")

        for stage in range(2):
            if stage:
                for migration in CANDIDATE_CHAIN[1:]:
                    self.apply_migration(migration)
            with self.subTest(stage="full_chain" if stage else "003b"):
                # 1. Trusted service_role can insert security events
                role_seen = self.as_role("service_role", "", f"""
                    SELECT current_user;
                    INSERT INTO public.security_events (session_id, user_id, event_type, severity, sanitized_detail)
                    VALUES
                        ('{SESSION_A}', '{USER_A}', 'PROMPT_INJECTION_DETECTED', 'WARN', '{{"detail":"test A"}}'),
                        ('{SESSION_B}', '{USER_B}', 'RATE_LIMIT_EXCEEDED', 'INFO', '{{"detail":"test B"}}');
                """)

                self.assertEqual(role_seen, "service_role")

                # BYPASSRLS proves role grants, not the INSERT policy expression.
                # 2. User A can SELECT own security events
                events_a = self.as_role("authenticated", USER_A, "SELECT count(*) FROM public.security_events")
                self.assertEqual(events_a, str(stage + 1), "User A should see only their own security events")

                # 3. User A cannot see User B's events
                user_seen = self.as_role("authenticated", USER_A, "SELECT DISTINCT user_id FROM public.security_events")
                self.assertEqual(user_seen, USER_A)

                # 4. Untrusted authenticated INSERT is denied
                insert_res = self.as_role_fail(
                    "authenticated", USER_A,
                    f"INSERT INTO public.security_events (user_id, event_type, sanitized_detail) VALUES ('{USER_A}', 'FORGED_EVENT', '{{}}')"
                )
                self.assertNotEqual(insert_res.returncode, 0)
                self.assertIn("permission denied for table security_events", insert_res.stderr)

    def test_t13_partial_upgrade_saves_configured_and_reloads(self):
        """Exercise Stage 2, not merely RPC existence, on the partial upgrade."""
        from test_review_rpcs import literal

        from app.models.schemas import SourceQuestion
        from app.services.blueprint.adapters import source_to_item
        from app.services.blueprint.artifacts import (
            prepare_blueprint_artifact,
            prepare_source_artifacts,
        )

        self.seed_five_table_baseline()
        for migration in CANDIDATE_CHAIN:
            self.apply_migration(migration)
        sid = str(uuid4())
        self.sql(f"INSERT INTO exam_sessions(id,user_id,title) VALUES ('{sid}','{USER_A}','Config regression')")
        fixture = json.loads((ROOT / "backend/tests/fixtures/ai_pipeline.json").read_text(encoding="utf-8"))
        original = SourceQuestion.model_validate(fixture["source"])
        source = original.model_copy(update={"id": str(uuid4())})
        blueprint = json.loads(json.dumps(fixture["blueprint"]).replace(
            source_to_item(original)["source"]["question_id"],
            source_to_item(source)["source"]["question_id"],
        ))
        row = dict(id=source.id, session_id=sid, question_no=1,
                   raw_content=source.question_text, options=source.options,
                   correct_key=source.correct_answer, solution_md=source.solution)
        self.sql(f"""
            INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key,solution_md)
            VALUES ('{source.id}','{sid}',1,{literal(source.question_text)},
                    {literal(json.dumps(source.options))}::jsonb,{literal(source.correct_answer)},
                    {literal(source.solution)});
        """)
        def rpc(name, args, role="service_role", actor=USER_A):
            return json.loads(self.as_role(role, actor, f"SELECT public.{name}({args})"))

        sources = prepare_source_artifacts(sid, [row])
        revision = self.value(f"SELECT source_content_revision FROM exam_sessions WHERE id='{sid}'")
        rpc("confirm_source_artifacts", f"p_session_id=>'{sid}',p_actor_id=>'{USER_A}',p_confirmation_id=>'{uuid4()}',p_expected_source_revision=>'{revision}',p_sources=>{literal(json.dumps(sources))}::jsonb")
        publication = prepare_blueprint_artifact(sources[0], blueprint)
        job = str(uuid4())
        publication["producer_job_id"] = job
        rpc("claim_source_production", f"'{sid}','{sources[0]['source_revision_id']}','{job}'")
        rpc("publish_canonical_blueprint", f"'{sid}',{literal(json.dumps(publication))}::jsonb")
        snapshot = rpc("get_generation_source_snapshot", f"'{sid}'", role="authenticated")
        self.assertTrue(snapshot["ready"], snapshot)
        args = (f"'{sid}',2,'[]'::jsonb,'{{\"shuffle_questions\":false,\"shuffle_options\":false}}'::jsonb,"
                f"{literal(json.dumps(snapshot['manifest']))}::jsonb")
        saved = rpc("save_generation_config", args, role="authenticated")
        self.assertEqual(saved["status"], "configured")
        self.assertEqual(self.value(f"SELECT status FROM exam_sessions WHERE id='{sid}'"), "configured")
        config = json.loads(self.as_role("authenticated", USER_A,
            f"SELECT to_jsonb(c) FROM generation_configs c WHERE session_id='{sid}'"))
        self.assertEqual(config["n_versions"], 2)
        self.assertEqual(config["source_manifest"], snapshot["manifest"])
        self.assertEqual(config["ordering_preferences"], {"shuffle_questions": False, "shuffle_options": False})
        again = rpc("save_generation_config", args, role="authenticated")
        self.assertEqual(again["config_id"], saved["config_id"])
        self.assertEqual(self.value(f"SELECT count(*) FROM generation_configs WHERE session_id='{sid}'"), "1")
        before = self.value(f"SELECT to_jsonb(c) FROM generation_configs c WHERE session_id='{sid}'")
        denied = self.as_role_fail("authenticated", USER_B, f"SELECT public.save_generation_config({args})")
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("Access denied", denied.stderr)
        self.assertEqual(self.value(f"SELECT to_jsonb(c) FROM generation_configs c WHERE session_id='{sid}'"), before)

    def test_t12_get_session_source_preview_contract_and_authorization(self):
        """T12: get_session_source_preview works for owner with revision, denies non-owner."""
        self.seed_five_table_baseline()
        for m_name in CANDIDATE_CHAIN:
            self.apply_migration(m_name)

        # Owner (User A) calls get_session_source_preview on Session A
        preview_json = self.as_role(
            "authenticated", USER_A,
            f"SELECT public.get_session_source_preview('{SESSION_A}')"
        )
        preview = json.loads(preview_json)
        self.assertEqual(preview["session"]["id"], SESSION_A)
        self.assertIn("source_content_revision", preview["session"])
        self.assertEqual(preview["source_revision"], preview["session"]["source_content_revision"])
        self.assertEqual(len(preview["source_questions"]), 2)

        # Non-owner (User B) calls get_session_source_preview on Session A -> Denied (ARTIFACT_NOT_FOUND / P0002)
        unauth_res = self.as_role_fail(
            "authenticated", USER_B,
            f"SELECT public.get_session_source_preview('{SESSION_A}')"
        )
        self.assertNotEqual(unauth_res.returncode, 0)
        self.assertTrue(
            "ARTIFACT_NOT_FOUND" in unauth_res.stderr or "P0002" in unauth_res.stderr,
            f"Expected authorization failure, got: {unauth_res.stderr}"
        )

        # EXECUTE privilege check
        self.assertEqual(
            self.value("SELECT has_function_privilege('authenticated', 'public.get_session_source_preview(uuid)', 'EXECUTE');"),
            "t"
        )
        self.assertEqual(
            self.value("SELECT has_function_privilege('anon', 'public.get_session_source_preview(uuid)', 'EXECUTE');"),
            "f"
        )

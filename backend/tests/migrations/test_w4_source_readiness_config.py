"""W4 config contract: GREEN on018; W4_BASELINE_015=1 reproduces old defects.

Run with RUN_POSTGRES_MIGRATION_TESTS=1 using unittest discovery. Supply an
isolated pinned PR30 archive via W4_PR30_CHECKOUT to execute the worker probe.
Real PostgreSQL15, network-none container, no external DSN or Production data.
No xfail/expectedFailure: a successful unsafe write must fail the test.
"""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from uuid import uuid4

import test_review_rpcs as review_fixtures
from test_review_rpcs import OWNER, SID, literal
from test_stage3_schema import BOOTSTRAP, ROOT, PostgresCase

OFF = {"shuffle_questions": False, "shuffle_options": False}
OMITTED = object()


def json_sql(value):
    return literal(json.dumps(value)) + "::jsonb"


class W4SourceReadinessConfigTests(PostgresCase):
    def setUp(self):
        from app.models.schemas import SourceQuestion
        from app.services.blueprint.adapters import source_to_item
        from app.services.blueprint.artifacts import prepare_source_artifacts

        type(self).db = "w4_config_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP)
        baseline = os.getenv("W4_BASELINE_015") == "1"
        schema = subprocess.check_output(["git", "show", "65c536291b0ad23c39e3b7f0615098943117d6e3:backend/scripts/schema.sql"], cwd=ROOT, text=True) if baseline else (ROOT / "backend/scripts/schema.sql").read_text()
        self.sql(schema)
        for number in range(2, 17):
            paths = list((ROOT / "backend/migrations").glob(f"{number:03}_*.sql"))
            self.assertEqual(len(paths), 1)
            self.sql(paths[0].read_text())
        if not baseline:
            self.sql(subprocess.check_output(["git", "show", "598b959c69c0f1c6362daed50fd544cb09dd73f7:backend/migrations/017_generation_lifecycle_recovery.sql"], cwd=ROOT, text=True))
            self.sql((ROOT / "backend/migrations/018_w4_source_readiness_config.sql").read_text())
        self.sql(f"""
            INSERT INTO auth.users(id,email) VALUES ('{OWNER}','w4@example.invalid');
            INSERT INTO public.users(id,email) VALUES ('{OWNER}','w4@example.invalid') ON CONFLICT DO NOTHING;
            INSERT INTO exam_sessions(id,user_id,title) VALUES ('{SID}','{OWNER}','W4 synthetic');
        """)
        fixture = json.loads((ROOT / "backend/tests/fixtures/ai_pipeline.json").read_text())
        source = SourceQuestion.model_validate(fixture["source"])
        old_id = source_to_item(source)["source"]["question_id"]
        rows, self.blueprints = [], []
        for index in range(2):
            src = source.model_copy(update={"id": str(uuid4())})
            new_id = source_to_item(src)["source"]["question_id"]
            self.blueprints.append(json.loads(json.dumps(fixture["blueprint"]).replace(old_id, new_id)))
            row = dict(id=src.id, session_id=SID, question_no=index + 1,
                       raw_content=src.question_text, options=src.options,
                       correct_key=src.correct_answer, solution_md=src.solution)
            rows.append(row)
            solution_sql = "NULL" if src.solution is None else literal(src.solution)
            self.sql(f"""
                INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key,solution_md)
                VALUES ('{src.id}','{SID}',{index + 1},{literal(src.question_text)},
                    {json_sql(src.options)},{literal(src.correct_answer)},{solution_sql});
            """)
        self.sources = prepare_source_artifacts(SID, rows)

    def rpc(self, name, args, role="authenticated", actor=OWNER, check=True):
        result = self.sql(
            "\\set VERBOSITY verbose\n" + review_fixtures.ReviewRpcTests.auth(role, actor)
            + f"SELECT public.{name}({args});", check=check,
        )
        return json.loads(result.stdout) if check else result

    def confirm(self):
        revision = self.value(f"SELECT source_content_revision FROM exam_sessions WHERE id='{SID}'")
        return self.rpc("confirm_source_artifacts",
            f"p_session_id=>'{SID}',p_actor_id=>'{OWNER}',p_confirmation_id=>'{uuid4()}',"
            f"p_expected_source_revision=>'{revision}',p_sources=>{json_sql(self.sources)}",
            role="service_role")

    def ready(self, dimensions=None):
        from app.services.blueprint.artifacts import prepare_blueprint_artifact

        self.confirm()
        for index, (source, blueprint) in enumerate(zip(self.sources, self.blueprints)):
            document = deepcopy(blueprint)
            if dimensions is not None:
                policy = document["requirement"]["variation_policy"]
                policy["allowed_transformations"] = [
                    item for item in policy["allowed_transformations"]
                    if item["dimension"] in dimensions[index]
                ]
            publication = prepare_blueprint_artifact(source, document)
            job = str(uuid4())
            publication["producer_job_id"] = job
            self.rpc("claim_source_production", f"'{SID}','{source['source_revision_id']}','{job}'", role="service_role")
            self.rpc("publish_canonical_blueprint", f"'{SID}',{json_sql(publication)}", role="service_role")
        snap = self.snapshot()
        self.assertTrue(snap["ready"], snap)  # Fixture must really be canonical-ready.
        self.manifest = snap["manifest"]
        return snap

    def snapshot(self):
        return self.rpc("get_generation_source_snapshot", f"'{SID}'")

    def save(self, modes=None, prefs=OFF, manifest=OMITTED, n="2", actor=OWNER):
        expected = getattr(self, "manifest", None) if manifest is OMITTED else manifest
        args = (f"p_session_id=>'{SID}',p_n_versions=>{n},"
                f"p_active_variation_modes=>{json_sql([] if modes is None else modes)},"
                f"p_expected_snapshot=>{json_sql(expected)}")
        if prefs is not OMITTED:
            args += f",p_ordering_preferences=>{json_sql(prefs)}"
        return self.rpc("save_generation_config", args, actor=actor, check=False)

    def writes(self):
        tables = ("exam_sessions", "generation_configs", "generation_job_snapshots",
                  "generation_target_results", "source_artifact_confirmations", "source_artifact_heads")
        return {t: self.value(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]') FROM {t} t")
                if t not in ("source_artifact_confirmations", "source_artifact_heads") else
                self.value(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') FROM {t} t")
                for t in tables}

    def assert_denied(self, before, result, state="22023"):
        self.assertNotEqual(result.returncode, 0,
                            f"unsafe RPC unexpectedly succeeded: {result.stdout}")
        self.assertIn(state, result.stderr)
        self.assertEqual(self.writes(), before, "rejected write changed persisted state")

    def test_no_confirmation_with_legacy_blueprints_cannot_save(self):
        self.sql(f"""
            INSERT INTO question_blueprints(source_question_id,variation_modes,confirmed_at)
              SELECT id,'["NUMERICAL"]',now() FROM source_questions;
            UPDATE exam_sessions SET status='blueprinted' WHERE id='{SID}';
        """)
        self.assertEqual(self.snapshot()["reason"], "NO_CONFIRMATION")
        self.assert_denied(self.writes(), self.save())

    def test_neutral_modes_derive_all_common_dimensions(self):
        self.ready()
        result = self.save()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)["config"]
        # Alias selection stays owner-pending; assert semantics without choosing an alias.
        self.assertEqual(set(config["canonical_dimensions"]), {"values", "context"})
        self.assertTrue(config["active_variation_modes"])

    def test_client_numerical_mode_is_rejected(self):
        self.ready()
        self.assert_denied(self.writes(), self.save(modes=["NUMERICAL"]))

    def test_client_none_cannot_force_original_clone(self):
        self.ready()
        self.assert_denied(self.writes(), self.save(modes=["NONE"]))

    def test_omitted_rpc_preferences_default_off_off(self):
        self.ready()
        result = self.save(prefs=OMITTED)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["config"]["ordering_preferences"], OFF)

    def test_table_default_is_off_off(self):
        self.ready()
        self.sql(f"INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',2)")
        self.assertEqual(json.loads(self.value("SELECT ordering_preferences FROM generation_configs")), OFF)

    def test_extra_ordering_key_rejected(self):
        self.ready()
        self.assert_denied(self.writes(), self.save(prefs={**OFF, "unexpected": True}))

    def test_strict_boolean_and_missing_keys_rejected(self):
        self.ready()
        for prefs in (None, [], {}, {"shuffle_questions": False},
                      {**OFF, "shuffle_questions": "false"},
                      {**OFF, "shuffle_options": 0}, {**OFF, "shuffle_options": None}):
            with self.subTest(prefs=prefs):
                self.assert_denied(self.writes(), self.save(prefs=prefs))

    def test_four_independent_flag_combinations_persist(self):
        self.ready()
        for questions in (False, True):
            for options in (False, True):
                with self.subTest(questions=questions, options=options):
                    prefs = dict(shuffle_questions=questions, shuffle_options=options)
                    result = self.save(prefs=prefs)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["config"]["ordering_preferences"], prefs)

    def test_invalid_n_rejected_without_mutation(self):
        self.ready()
        for n in ("NULL", "0", "5", "-1"):
            with self.subTest(n=n):
                self.assert_denied(self.writes(), self.save(n=n))

    def test_pending_and_failed_canonical_cannot_save(self):
        self.confirm()
        self.assertFalse(self.snapshot()["ready"])
        self.assert_denied(self.writes(), self.save())
        source = self.sources[0]["source_revision_id"]
        job = str(uuid4())
        self.rpc("claim_source_production", f"'{SID}','{source}','{job}'", role="service_role")
        self.rpc("fail_source_production", f"'{SID}','{source}','{job}','FIXTURE_FAILURE'", role="service_role")
        self.assert_denied(self.writes(), self.save())

    def test_missing_and_forged_manifest_cannot_save(self):
        self.ready()
        for manifest in (None, {}, {**self.manifest, "confirmation_id": str(uuid4())}):
            with self.subTest(manifest=manifest):
                self.assert_denied(self.writes(), self.save(manifest=manifest), "55006")

    def test_foreign_owner_cannot_save(self):
        self.ready()
        self.assert_denied(self.writes(), self.save(actor=str(uuid4())), "42501")

    def test_authenticated_cannot_directly_insert_config(self):
        self.ready()
        before = self.writes()
        result = self.sql("\\set VERBOSITY verbose\n" + review_fixtures.ReviewRpcTests.auth()
                          + f"INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',2)", check=False)
        self.assert_denied(before, result, "42501")

    def test_valid_ready_disjoint_policies_allow_clone(self):
        self.ready(dimensions=({"values"}, {"wording"}))
        result = self.save()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)["config"]
        self.assertEqual(config["active_variation_modes"], [])
        self.assertEqual(config["canonical_dimensions"], [])

    def test_intersection_excludes_dimension_missing_from_one_question(self):
        self.ready(dimensions=({"values", "context"}, {"values"}))
        result = self.save()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["config"]["canonical_dimensions"], ["values"])

    def test_empty_policy_cannot_silently_become_clone(self):
        self.ready()
        # Test-admin corruption fixture, never a client mutation or producer bypass.
        # No trigger/ACL is disabled. This models malformed historical evidence.
        self.sql("""
            UPDATE canonical_blueprint_revisions SET canonical_blueprint=jsonb_set(
              canonical_blueprint,'{requirement,variation_policy,allowed_transformations}','[]')
        """)
        status = self.rpc("get_source_artifacts", f"'{SID}'", check=False)
        self.assertNotEqual(status.returncode, 0)
        self.assertIn("22023", status.stderr)
        self.assert_denied(self.writes(), self.save())

    def test_invalid_policy_dimension_cannot_save(self):
        self.ready()
        self.sql("""
            UPDATE canonical_blueprint_revisions SET canonical_blueprint=jsonb_set(
              canonical_blueprint,'{requirement,variation_policy,allowed_transformations}',
              '[{"dimension":"invalid_dimension"}]')
        """)
        self.assertEqual(self.snapshot()["reason"], "INVALID_BLUEPRINT_POLICY")
        self.assert_denied(self.writes(), self.save())

    def test_stale_source_fingerprint_cannot_save(self):
        self.ready()
        self.sql("UPDATE source_artifact_revisions SET source_fingerprint=repeat('0',64)")
        self.assertEqual(self.snapshot()["reason"], "SOURCE_FINGERPRINT_MISMATCH")
        self.assert_denied(self.writes(), self.save())

    def test_snapshot_has_one_dimension_for_both_compatible_aliases(self):
        self.ready(dimensions=({"values"}, {"values"}))
        result = self.save()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)["config"]
        self.assertEqual(config["active_variation_modes"], ["NUMERICAL", "parameter_variation"])
        self.assertEqual(config["canonical_dimensions"], ["values"])
        claim = self.rpc("claim_generation_job", f"'{SID}',false")
        self.assertEqual(claim["context"]["canonical_dimensions"], ["values"])
        self.assertEqual(len(claim["context"]["confirmed_sources"]), 2)

    def test_claimed_job_blocks_even_admin_restored_configurable_status(self):
        self.ready()
        self.assertEqual(self.save().returncode, 0)
        self.rpc("claim_generation_job", f"'{SID}',false")
        # Impossible via public API: exercise snapshot fence independently of status.
        self.sql(f"UPDATE exam_sessions SET status='configured' WHERE id='{SID}'")
        self.assert_denied(self.writes(), self.save(), "55006")

    def test_worker_probe_with_real_sql_receipts(self):
        checkout = os.environ.get("W4_PR30_CHECKOUT")
        if not checkout:
            self.skipTest("explicit pinned isolated PR30 checkout required for worker probe")
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "origin/pr-30"], cwd=ROOT, text=True).strip(),
                         "b6b642225b45e2744fda8826ebc70c8db0a3850e")
        self.ready(dimensions=({"values"}, {"values"}))
        self.assertEqual(self.save().returncode, 0)
        claim = self.rpc("claim_generation_job", f"'{SID}',false")
        loaded = self.rpc("load_generation_completed_results", f"'{SID}'", role="service_role")
        env = {**os.environ, "PYTHONPATH": str(checkout) + "/backend",
               "SUPABASE_URL": "http://127.0.0.1:1", "SUPABASE_ANON_KEY": "fake-local-only",
               "SUPABASE_SERVICE_ROLE_KEY": "fake-local-only"}
        import sys

        probe = subprocess.run([sys.executable, str(ROOT / "backend/tests/migrations/w4_worker_probe.py")],
                               input=json.dumps(dict(claim=claim, loaded=loaded)), text=True,
                               capture_output=True, env=env, cwd=checkout, timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertIn("four unique slots", probe.stdout)

    def test_s04_concurrent_config_saves_serialize(self):
        self.ready()
        barrier = Barrier(2)

        def save(n):
            barrier.wait(timeout=10)
            return self.save(n=str(n))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, (2, 3)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM generation_configs"), "1")
        self.assertIn(self.value("SELECT n_versions FROM generation_configs"), ("2", "3"))
        self.assertEqual(json.loads(self.value("SELECT source_manifest FROM generation_configs")), self.manifest)

    def test_s04_save_and_claim_share_parent_lock(self):
        self.ready()
        self.assertEqual(self.save().returncode, 0)
        barrier = Barrier(2)

        def save():
            barrier.wait(timeout=10)
            return self.save(n="3")

        def claim():
            barrier.wait(timeout=10)
            return self.rpc("claim_generation_job", f"'{SID}',false")

        with ThreadPoolExecutor(max_workers=2) as pool:
            saving, claiming = pool.submit(save), pool.submit(claim)
            result, receipt = saving.result(timeout=30), claiming.result(timeout=30)
        if result.returncode:
            self.assertIn("55006", result.stderr)
            self.assertEqual(receipt["context"]["n_versions"], 2)
        else:
            self.assertEqual(receipt["context"]["n_versions"], 3)
        self.assertEqual(int(self.value("SELECT n_versions FROM generation_configs")), receipt["context"]["n_versions"])
        self.assertEqual(self.value("SELECT count(*) FROM generation_job_snapshots"), "1")
        self.assertEqual(self.value("SELECT status FROM exam_sessions"), "generating")

    def test_s04_persistence_fault_rolls_back(self):
        self.ready()
        self.sql("""
            CREATE FUNCTION public.w4_test_failure() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'injected test write failure' USING ERRCODE='P0001'; END $$;
            CREATE TRIGGER w4_test_failure BEFORE INSERT OR UPDATE ON generation_configs
              FOR EACH ROW EXECUTE FUNCTION public.w4_test_failure();
        """)
        self.assert_denied(self.writes(), self.save(), "P0001")

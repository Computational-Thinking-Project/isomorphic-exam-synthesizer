"""Producer SQL provenance/atomicity on PostgreSQL15 (same explicit Docker opt-in).

Adapted from Duy/TASK-301 commits 68b375f and 553a009. SQL tests use detached shared
fixtures; no backend Python dependencies, Gemini or shared database are used.
"""

import json
from copy import deepcopy
from uuid import uuid4

import test_review_rpcs as rpc_fixtures
from artifact_fixtures import artifact_payload
from test_review_rpcs import OWNER, SID, SOURCE, literal
from test_stage3_schema import ROOT, PostgresCase


class SourceArtifactTests(PostgresCase):
    def setUp(self):
        super().setUp()
        artifact, self.publication = artifact_payload(SOURCE)
        source = artifact["confirmed_input"]
        self.blueprint = self.publication["canonical_blueprint"]
        self.row = dict(
            id=SOURCE,
            session_id=SID,
            raw_content=source["question_text"],
            options=source["options"],
            correct_key=source["correct_answer"],
            solution_md=None,
        )
        self.publication["producer_job_id"] = self.publication["blueprint_revision_id"]
        self.sources = [artifact]
        self.sql(f"""UPDATE source_questions SET raw_content={literal(self.row["raw_content"])},
            options={literal(json.dumps(self.row["options"]))},correct_key='A',solution_md=NULL;""")
        self.migrate()
        self.sql(
            (ROOT / "backend/migrations/003_confirm_exam_source_rpc.sql").read_text(
                encoding="utf-8"
            )
        )
        self.sql(f"INSERT INTO question_blueprints(source_question_id) VALUES ('{SOURCE}');")
        self.confirmation_id = str(uuid4())
        self.timestamp = self.value(f"SELECT updated_at FROM exam_sessions WHERE id='{SID}';")

    def call(self, function, *arguments, worker=True, actor=OWNER, check=True):
        script = rpc_fixtures.ReviewRpcTests.auth(
            "service_role" if worker else "authenticated", actor
        )
        script += f"SELECT public.{function}({','.join(literal(v) for v in arguments)});"
        result = self.sql(script, check=check)
        return json.loads(result.stdout.strip().splitlines()[-1]) if check else result

    def confirm(self, sources=None, key=None, actor=OWNER, check=True):
        return self.call(
            "confirm_source_artifacts",
            SID,
            actor,
            key or self.confirmation_id,
            self.timestamp,
            json.dumps(self.sources if sources is None else sources),
            check=check,
        )

    def publish(self, publication=None, check=True):
        publication = publication or self.publication
        exists = self.value(
            f"SELECT count(*) FROM canonical_blueprint_revisions WHERE blueprint_revision_id={literal(publication['blueprint_revision_id'])};"
        )
        if exists == "0":
            claimed = self.call(
                "claim_source_production",
                SID,
                publication["source_revision_id"],
                publication["producer_job_id"],
                check=check,
            )
            if not check and claimed.returncode:
                return claimed
        return self.call("publish_canonical_blueprint", SID, json.dumps(publication), check=check)

    def test_confirmation_records_exact_python_input_hash_actor_and_pending_canonical(self):
        receipt = self.confirm()
        self.assertEqual(receipt["sources"], self.sources)
        self.assertEqual(receipt["actor_id"], OWNER)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "blueprinted")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "1")
        self.assertEqual(
            self.value("SELECT count(*) FROM question_blueprints WHERE confirmed_at IS NOT NULL;"),
            "0",
        )
        self.assertEqual(receipt["total_blueprints"], 0)
        self.assertEqual(receipt["canonical_status"], "pending")
        saved = json.loads(self.value("SELECT confirmed_input FROM source_artifact_revisions;"))
        self.assertEqual(saved, self.sources[0]["confirmed_input"])
        self.assertEqual(
            self.value("SELECT source_fingerprint FROM source_artifact_revisions;"),
            self.sources[0]["source_fingerprint"],
        )

    def test_mismatch_rolls_back_without_confirmation_or_stage_transition(self):
        changed = deepcopy(self.sources)
        changed[0]["confirmed_input"]["solution"] = "Not the teacher-confirmed source"
        result = self.confirm(changed, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ARTIFACT_SOURCE_MISMATCH", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "draft")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_confirmations;"), "0")

    def test_live_source_edit_after_python_preparation_is_detected(self):
        self.sql("UPDATE source_questions SET solution_md='Concurrent edit';")
        result = self.confirm(check=False)
        self.assertIn("ARTIFACT_SOURCE_MISMATCH", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "0")

    def test_authenticated_cannot_forge_hash_and_worker_cannot_scan_private_storage(self):
        result = self.call(
            "confirm_source_artifacts",
            SID,
            OWNER,
            self.confirmation_id,
            self.timestamp,
            json.dumps(self.sources),
            worker=False,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("permission denied", result.stderr)
        for role in ("authenticated", "service_role"):
            result = self.sql(
                rpc_fixtures.ReviewRpcTests.auth(role) + "SELECT * FROM source_artifact_revisions;",
                check=False,
            )
            self.assertIn("permission denied", result.stderr)
        result = self.confirm(actor=str(uuid4()), check=False)
        self.assertIn("ARTIFACT_OWNER_MISMATCH", result.stderr)

    def test_confirmation_artifact_failure_rolls_back_source_transition_and_security_audit(self):
        self.sql("""UPDATE source_questions SET has_security_warning=true;
          CREATE FUNCTION fail_artifact_insert() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'INJECT_ARTIFACT_FAILURE'; END $$;
          CREATE TRIGGER fail_artifact BEFORE INSERT ON source_artifact_revisions
          FOR EACH ROW EXECUTE FUNCTION fail_artifact_insert();""")
        result = self.confirm(check=False)
        self.assertIn("INJECT_ARTIFACT_FAILURE", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "draft")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_confirmations;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM security_events;"), "0")
        self.assertEqual(
            self.value("SELECT count(*) FROM question_blueprints WHERE confirmed_at IS NOT NULL;"),
            "0",
        )

    def test_confirmation_replay_after_lock_is_read_only_and_payload_rebinding_fails(self):
        first = self.confirm()
        self.sql("UPDATE exam_sessions SET status='approved',approved_at=now();")
        replay = self.confirm()
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["sources"], first["sources"])
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "1")
        changed = deepcopy(self.sources)
        changed[0]["source_fingerprint"] = "f" * 64
        self.assertIn("ARTIFACT_IDEMPOTENCY_CONFLICT", self.confirm(changed, check=False).stderr)

    def test_publication_stores_full_canonical_revision_and_replays_without_repointing(self):
        self.confirm()
        first = self.publish()
        self.assertFalse(first["replayed"])
        stored = json.loads(
            self.value("SELECT canonical_blueprint FROM canonical_blueprint_revisions;")
        )
        self.assertEqual(stored, self.blueprint)
        self.assertTrue(self.publish()["replayed"])
        self.assertEqual(self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "1")
        self.sql("UPDATE source_questions SET solution_md='Changed after publication';")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_heads;"), "0")
        self.assertEqual(self.value("SELECT confirmed_at IS NULL FROM question_blueprints;"), "t")
        self.assertTrue(self.publish()["replayed"])
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_heads;"), "0")

    def test_changed_revision_rejects_late_publication_even_after_edit_and_revert(self):
        self.confirm()
        self.sql(
            "UPDATE source_questions SET solution_md='Changed'; UPDATE source_questions SET solution_md=NULL;"
        )
        result = self.publish(check=False)
        self.assertIn("ARTIFACT_STALE", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "0")

    def test_publication_pointer_and_document_rollback_together(self):
        self.confirm()
        self.call(
            "claim_source_production",
            SID,
            self.publication["source_revision_id"],
            self.publication["producer_job_id"],
        )
        self.sql("""CREATE FUNCTION fail_head_update() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'INJECT_HEAD_FAILURE'; END $$;
          CREATE TRIGGER fail_head BEFORE UPDATE ON source_artifact_heads
          FOR EACH ROW EXECUTE FUNCTION fail_head_update();""")
        result = self.publish(check=False)
        self.assertIn("INJECT_HEAD_FAILURE", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "0")
        self.assertEqual(
            self.value("SELECT blueprint_revision_id IS NULL FROM source_artifact_heads;"), "t"
        )

    def test_publication_rejects_locked_session_and_migration_replay_retains_artifacts(self):
        self.confirm()
        self.publish()
        self.migrate()
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "1")
        self.assertEqual(self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "1")
        self.sql("UPDATE exam_sessions SET approved_at=now();")
        new = self.publication | {"blueprint_revision_id": str(uuid4())}
        self.assertIn("ARTIFACT_LOCKED", self.publish(new, check=False).stderr)

    def test_read_state_is_owner_scoped_read_only_and_invalidates_with_source_set(self):
        self.confirm()
        before = self.value("SELECT updated_at FROM exam_sessions;")
        pending = self.call("get_source_artifacts", SID, worker=False)
        self.assertFalse(pending["ready"])
        self.assertEqual(pending["pending_source_question_ids"], [SOURCE])
        self.assertEqual(self.value("SELECT updated_at FROM exam_sessions;"), before)
        self.assertIn(
            "ARTIFACT_NOT_FOUND",
            self.call(
                "get_source_artifacts", SID, worker=False, actor=str(uuid4()), check=False
            ).stderr,
        )
        self.publish()
        self.assertTrue(self.call("get_source_artifacts", SID)["ready"])
        self.sql(f"""INSERT INTO source_questions(session_id,question_no,raw_content,options,correct_key)
          VALUES ('{SID}',10,'Extra','["1","2","3","4"]','A');""")
        self.assertIn("ARTIFACT_STALE", self.call("get_source_artifacts", SID, check=False).stderr)

    def test_removed_source_keeps_revision_history_until_session_deletion(self):
        self.confirm()
        self.publish()
        self.sql(f"DELETE FROM source_questions WHERE id='{SOURCE}';")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_heads;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "1")
        self.assertEqual(self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "1")
        self.assertTrue(self.publish()["replayed"])
        self.sql(f"DELETE FROM exam_sessions WHERE id='{SID}';")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_confirmations;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "0")

    def test_review_progress_returns_same_snapshot_unapproved_ids(self):
        self.confirm()
        self.sql(f"INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',1);")
        result = self.call("review_get_progress", SID, worker=False)
        progress = result["progress"]
        self.assertEqual(
            len(progress["unapproved_question_ids"]),
            progress["current_slots"] - progress["approved_slots"],
        )
        self.assertEqual(progress["unapproved_question_ids"], [rpc_fixtures.QID])

    def test_concurrent_confirmation_replays_one_committed_revision(self):
        script = rpc_fixtures.ReviewRpcTests.auth("service_role") + (
            f"SELECT confirm_source_artifacts('{SID}','{OWNER}','{self.confirmation_id}',"
            f"{literal(self.timestamp)},{literal(json.dumps(self.sources))});"
        )
        responses = rpc_fixtures.ReviewRpcTests.concurrent(self, script, script)
        self.assertTrue(all(r.returncode == 0 for r in responses), [r.stderr for r in responses])
        receipts = [json.loads(r.stdout) for r in responses]
        self.assertEqual(sorted(r["replayed"] for r in receipts), [False, True])
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "1")

    def test_concurrent_publication_replays_one_document_and_pointer(self):
        self.confirm()
        self.call(
            "claim_source_production",
            SID,
            self.publication["source_revision_id"],
            self.publication["producer_job_id"],
        )
        script = rpc_fixtures.ReviewRpcTests.auth("service_role") + (
            f"SELECT publish_canonical_blueprint('{SID}',{literal(json.dumps(self.publication))});"
        )
        responses = rpc_fixtures.ReviewRpcTests.concurrent(self, script, script)
        self.assertTrue(all(r.returncode == 0 for r in responses), [r.stderr for r in responses])
        receipts = [json.loads(r.stdout) for r in responses]
        self.assertEqual(sorted(r["replayed"] for r in receipts), [False, True])
        self.assertEqual(self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "1")

    def test_bootstrap_needs_neither_legacy_row_nor_old_confirmation_function(self):
        self.sql(
            "DELETE FROM question_blueprints; DROP FUNCTION confirm_exam_source(UUID,INT,BOOLEAN,TIMESTAMPTZ);"
        )
        receipt = self.confirm()
        self.assertEqual(receipt["canonical_status"], "pending")
        self.assertFalse(self.call("get_source_artifacts", SID)["ready"])
        self.assertEqual(self.value("SELECT count(*) FROM question_blueprints;"), "0")
        self.publish()
        self.assertTrue(self.call("get_source_artifacts", SID)["ready"])
        self.sql(f"INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',1);")
        progress = self.call("review_get_progress", SID, worker=False)["progress"]
        self.assertEqual(progress["expected_slots"], 1)
        self.sql("UPDATE version_questions SET status='approved';")
        self.assertTrue(self.call("review_get_progress", SID, worker=False)["progress"]["ready"])

    def test_bootstrap_silent_security_audit_is_atomic_and_replay_does_not_duplicate(self):
        self.sql(
            "UPDATE source_questions SET has_security_warning=true; DELETE FROM question_blueprints;"
        )
        self.confirm()
        self.confirm()
        self.assertEqual(
            self.value(
                "SELECT count(*) FROM security_events WHERE event_type='PROMPT_INJECTION_DETECTED';"
            ),
            "1",
        )

    def test_publication_and_reservation_share_the_session_lock(self):
        self.confirm()
        self.call(
            "claim_source_production",
            SID,
            self.publication["source_revision_id"],
            self.publication["producer_job_id"],
        )
        self.sql(
            f"UPDATE exam_sessions SET status='generated'; INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',1);"
        )
        publish = (
            rpc_fixtures.ReviewRpcTests.auth("service_role")
            + f"SELECT publish_canonical_blueprint('{SID}',{literal(json.dumps(self.publication))});"
        )
        reserve = (
            rpc_fixtures.ReviewRpcTests.auth()
            + f"SELECT review_reserve_regeneration('{SID}','{rpc_fixtures.QID}','{uuid4()}');"
        )
        publication, reservation = rpc_fixtures.ReviewRpcTests.concurrent(self, publish, reserve)
        self.assertEqual(publication.returncode, 0, publication.stderr)
        if reservation.returncode:
            self.assertIn("REVIEW_SOURCE_MISMATCH", reservation.stderr)
            self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")
        else:
            self.assertEqual(
                json.loads(reservation.stdout)["snapshot"]["blueprint_revision_id"],
                self.publication["blueprint_revision_id"],
            )
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "7")

    def test_locked_confirmation_does_not_create_new_revision_but_replays_old(self):
        first = self.confirm()
        self.sql("UPDATE exam_sessions SET status='approved',approved_at=now();")
        self.assertTrue(self.confirm()["replayed"])
        self.assertIn("ARTIFACT_LOCKED", self.confirm(key=str(uuid4()), check=False).stderr)
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_revisions;"), "1")
        self.assertEqual(self.confirm()["sources"], first["sources"])

    def test_producer_claim_race_grants_one_owner_and_lease_exceeds_extraction(self):
        self.confirm()
        revision = self.sources[0]["source_revision_id"]
        scripts = [
            rpc_fixtures.ReviewRpcTests.auth("service_role")
            + f"SELECT claim_source_production('{SID}','{revision}','{uuid4()}');"
            for _ in range(2)
        ]
        responses = rpc_fixtures.ReviewRpcTests.concurrent(self, *scripts)
        self.assertTrue(all(r.returncode == 0 for r in responses), [r.stderr for r in responses])
        self.assertEqual(
            sorted(json.loads(r.stdout)["status"] for r in responses), ["busy", "claimed"]
        )
        self.assertEqual(
            self.value(
                "SELECT producer_expires_at>clock_timestamp()+interval '360 seconds' FROM source_artifact_heads;"
            ),
            "t",
        )

    def test_stale_timestamp_and_missing_answers_rollback_confirmation(self):
        self.timestamp = "2000-01-01T00:00:00Z"
        self.assertIn("ARTIFACT_STALE", self.confirm(check=False).stderr)
        self.timestamp = self.value(f"SELECT updated_at FROM exam_sessions WHERE id='{SID}';")
        self.sql("UPDATE source_questions SET has_missing_answer=true;")
        self.assertIn("ARTIFACT_SOURCE_MISMATCH", self.confirm(check=False).stderr)
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_confirmations;"), "0")
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "draft")

    def test_expired_producer_cannot_publish_or_fail_new_job(self):
        self.confirm()
        revision = self.sources[0]["source_revision_id"]
        old = self.publication["producer_job_id"]
        self.call("claim_source_production", SID, revision, old)
        self.sql(
            "UPDATE source_artifact_heads SET producer_expires_at=clock_timestamp()-interval '1 second';"
        )
        new = str(uuid4())
        self.call("claim_source_production", SID, revision, new)
        result = self.call(
            "publish_canonical_blueprint", SID, json.dumps(self.publication), check=False
        )
        self.assertIn("ARTIFACT_STALE", result.stderr)
        self.assertEqual(
            self.call("fail_source_production", SID, revision, old, "PRODUCER_CANCELLED"),
            {"settled": False},
        )
        self.assertEqual(self.value("SELECT producer_job_id FROM source_artifact_heads;"), new)
        publication = self.publication | {"producer_job_id": new, "blueprint_revision_id": new}
        self.publish(publication)
        self.assertTrue(self.call("get_source_artifacts", SID)["ready"])

    def test_producer_status_is_read_only_and_failed_job_can_be_retried(self):
        self.confirm()
        revision, job = self.sources[0]["source_revision_id"], str(uuid4())
        self.call("claim_source_production", SID, revision, job)
        state = self.call("get_source_artifacts", SID, worker=False)
        self.assertEqual(state["production"][0]["status"], "running")
        self.call("fail_source_production", SID, revision, job, "BLUEPRINT_PRODUCTION_FAILED")
        state = self.call("get_source_artifacts", SID, worker=False)
        self.assertEqual(state["production"][0]["status"], "failed")
        job2 = str(uuid4())
        self.call("claim_source_production", SID, revision, job2)
        before = self.value("SELECT row_to_json(h) FROM source_artifact_heads h;")
        self.call("get_source_artifacts", SID, worker=False)
        self.assertEqual(before, self.value("SELECT row_to_json(h) FROM source_artifact_heads h;"))
        self.assertEqual(
            self.call("get_source_artifacts", SID)["production"][0]["status"], "running"
        )

    def test_producer_claim_and_failure_require_worker_acl(self):
        self.confirm()
        revision, job = self.sources[0]["source_revision_id"], str(uuid4())
        result = self.call("claim_source_production", SID, revision, job, worker=False, check=False)
        self.assertIn("permission denied", result.stderr)

        result = self.call(
            "fail_source_production", SID, revision, job, "FAILED", worker=False, check=False
        )
        self.assertIn("permission denied", result.stderr)

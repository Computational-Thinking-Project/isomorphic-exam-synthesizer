"""Frozen confirmed-artifact review contracts on independent PostgreSQL connections."""

import json
import os
from pathlib import Path
from uuid import uuid4

import test_review_rpcs as rpc_fixtures
from artifact_fixtures import seed_artifacts
from test_review_rpcs import OWNER, QID, SID, SOURCE, candidate, literal
from test_stage3_schema import PostgresCase


class ReviewArtifactTests(PostgresCase):
    def setUp(self):
        super().setUp()
        self.migrate()
        self.sql(f"""UPDATE exam_sessions SET status='generated',gemini_review_calls=0;
          INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',1);
          INSERT INTO question_blueprints(source_question_id,confirmed_at) VALUES ('{SOURCE}',now());""")
        self.artifact, self.publication = seed_artifacts(self, SID, SOURCE, OWNER)

    auth = staticmethod(rpc_fixtures.ReviewRpcTests.auth)
    call = rpc_fixtures.ReviewRpcTests.call
    reserve = rpc_fixtures.ReviewRpcTests.reserve
    permit = rpc_fixtures.ReviewRpcTests.permit
    complete = rpc_fixtures.ReviewRpcTests.complete
    fail = rpc_fixtures.ReviewRpcTests.fail
    expect_error = rpc_fixtures.ReviewRpcTests.expect_error
    concurrent = rpc_fixtures.ReviewRpcTests.concurrent

    def publish(self, publication=None, check=True):
        return self.call(
            "publish_canonical_blueprint",
            SID,
            json.dumps(publication or self.publication),
            worker=True,
            check=check,
        )

    def test_rpc_freezes_persisted_revisions_and_consistent_canonical_candidate(self):
        peer, peer_version, history = (str(uuid4()) for _ in range(3))
        self.sql(f"""UPDATE generation_configs SET n_versions=2;
          INSERT INTO exam_versions(id,session_id,version_code) VALUES ('{peer_version}','{SID}','102');
          INSERT INTO version_questions(id,version_id,source_question_id,question_no,content,options,correct_key,
            canonical_question_no,canonical_options,canonical_correct_key,is_current)
          VALUES ('{peer}','{peer_version}','{SOURCE}',1,'Peer','["4","3","2","1"]','D',
             9,'["1","2","3","4"]','A',true),
            ('{history}','{peer_version}','{SOURCE}',1,'Historical peer','["1","2","3","4"]','A',
             9,'["1","2","3","4"]','A',false);""")
        receipt = self.reserve()
        frozen = receipt["snapshot"]
        self.assertEqual(frozen["source_revision_id"], self.artifact["source_revision_id"])
        self.assertEqual(frozen["blueprint_source_revision_id"], frozen["source_revision_id"])
        self.assertEqual(frozen["blueprint_revision_id"], self.publication["blueprint_revision_id"])
        self.assertEqual(
            frozen["source_snapshot"],
            self.artifact["confirmed_input"]
            | {"content_hash": self.artifact["source_fingerprint"]},
        )
        self.assertEqual(frozen["blueprint"], self.publication["canonical_blueprint"])
        current = frozen["current_variant"]
        self.assertEqual(current["id"], QID)
        self.assertEqual(current["options"], ["1", "2", "3", "4"])
        self.assertEqual(current["correct_key"], "A")
        self.assertIsNone(
            current["solution_md"]
        )  # never mix display solution with canonical options
        self.assertEqual([p["id"] for p in frozen["peer_variants"]], [peer])
        self.assertEqual(frozen["peer_variants"][0]["correct_key"], "A")
        # Explicit opt-in emits the actual SQL receipt for consumer handoff. Tests
        # never overwrite committed fixtures or fabricate an RPC response.
        if directory := os.getenv("REVIEW_RPC_FIXTURE_DIR"):
            target = Path(directory).resolve()
            target.mkdir(parents=True, exist_ok=True)
            (target / "reservation.json").write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def test_legacy_confirmed_row_without_artifacts_cannot_reserve(self):
        self.sql("DELETE FROM source_artifact_heads; DELETE FROM source_artifact_confirmations;")
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_reserve_regeneration", SID, QID, uuid4()
        )
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "0")
        self.sql("UPDATE source_questions SET raw_content='Changed legacy source';")
        self.assertEqual(self.value("SELECT confirmed_at IS NULL FROM question_blueprints;"), "t")

    def test_pending_publication_cannot_reserve_or_charge(self):
        self.sql("UPDATE source_artifact_heads SET blueprint_revision_id=NULL;")
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_reserve_regeneration", SID, QID, uuid4()
        )
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")

    def test_wrong_source_binding_is_rejected_before_reservation(self):
        self.sql(
            "UPDATE source_artifact_revisions SET confirmed_input=jsonb_set(confirmed_input,'{solution}','\"Corrupt\"');"
        )
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_reserve_regeneration", SID, QID, uuid4()
        )
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")

    def test_new_blueprint_revision_denies_old_permits_and_completion(self):
        receipt = self.reserve()
        op = receipt["operation_id"]
        self.permit(op)
        self.publish(self.publication | {"blueprint_revision_id": str(uuid4())})
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_acquire_attempt", op, uuid4(), worker=True
        )
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH",
            "review_complete_regeneration",
            op,
            json.dumps(candidate(1)),
            worker=True,
        )
        self.assertEqual(self.reserve(op)["snapshot"], receipt["snapshot"])
        self.assertEqual(self.fail(op)["api_calls_used"], 1)
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")

    def test_edit_and_revert_never_revives_old_revision_and_recovery_retains_charge(self):
        receipt = self.reserve()
        op = receipt["operation_id"]
        self.permit(op)
        original = self.artifact["confirmed_input"]["question_text"]
        self.sql(
            f"UPDATE source_questions SET raw_content='Changed'; UPDATE source_questions SET raw_content={literal(original)};"
        )
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_acquire_attempt", op, uuid4(), worker=True
        )
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_heads;"), "0")
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        settled = self.call("review_recover_session", SID, worker=True)
        self.assertEqual(settled["recovered_count"], 1)
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")
        self.assertEqual(self.reserve(op)["snapshot"], receipt["snapshot"])
        self.assertFalse(self.call("review_get_progress", SID)["progress"]["ready"])

    def test_missing_answer_flag_invalidates_artifacts_and_blocks_dispatch(self):
        op = self.reserve()["operation_id"]
        self.sql("UPDATE source_questions SET has_missing_answer=true;")
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_acquire_attempt", op, uuid4(), worker=True
        )
        self.fail(op)
        self.assertEqual(self.value("SELECT count(*) FROM source_artifact_heads;"), "0")

    def test_legacy_receipt_replays_unchanged_but_cannot_dispatch_and_can_settle(self):
        receipt = self.reserve()
        op = receipt["operation_id"]
        legacy = receipt["snapshot"] | {"format": "database_rows"}
        old = receipt | {"snapshot": legacy}
        self.sql(
            f"UPDATE review_operations SET snapshot={literal(json.dumps(legacy))},reservation_result={literal(json.dumps(old))};"
        )
        self.migrate()
        replay = self.reserve(op)
        self.assertEqual(replay["snapshot"], legacy)
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_acquire_attempt", op, uuid4(), worker=True
        )
        self.assertEqual(self.fail(op)["api_calls_used"], 0)
        self.assertEqual(self.value("SELECT count(*) FROM review_attempts;"), "0")

    def test_publication_reservation_race_never_dispatches_superseded_revision(self):
        publication = self.publication | {"blueprint_revision_id": str(uuid4())}
        op = str(uuid4())
        results = self.concurrent(
            self.auth() + f"SELECT review_reserve_regeneration('{SID}','{QID}','{op}');",
            self.auth("service_role")
            + f"SELECT publish_canonical_blueprint('{SID}',{literal(json.dumps(publication))});",
        )
        self.assertTrue(all(r.returncode == 0 for r in results), [r.stderr for r in results])
        frozen = json.loads(results[0].stdout)["snapshot"]
        if frozen["blueprint_revision_id"] == publication["blueprint_revision_id"]:
            self.assertTrue(self.permit(op)["dispatch_permitted"])
        else:
            self.expect_error(
                "REVIEW_SOURCE_MISMATCH", "review_acquire_attempt", op, uuid4(), worker=True
            )
            self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "0")

    def test_content_locks_cover_source_and_new_publication_but_allow_readonly_replay(self):
        self.sql("UPDATE exam_sessions SET status='approved',approved_at=now();")
        result = self.sql("UPDATE source_questions SET solution_md='Forbidden';", check=False)
        self.assertIn("ARTIFACT_LOCKED", result.stderr)
        result = self.publish(
            self.publication | {"blueprint_revision_id": str(uuid4())}, check=False
        )
        self.assertIn("ARTIFACT_LOCKED", result.stderr)
        self.assertTrue(self.publish()["replayed"])

    def test_progress_ids_include_regenerating_and_exclude_history(self):
        self.reserve()
        p = self.call("review_get_progress", SID)["progress"]
        self.assertEqual(p["unapproved_question_ids"], [QID])
        self.assertEqual(
            len(p["unapproved_question_ids"]), p["current_slots"] - p["approved_slots"]
        )
        self.assertEqual(p["regenerating_slots"], 1)

    def test_artifact_helpers_and_all_storage_remain_private(self):
        for role in ("anon", "authenticated", "service_role"):
            for table in (
                "source_artifact_confirmations",
                "source_artifact_revisions",
                "canonical_blueprint_revisions",
                "source_artifact_heads",
            ):
                self.assert_sql_fails(
                    self.auth(role) + f"SELECT * FROM {table};", "permission denied"
                )
            self.assert_sql_fails(
                self.auth(role) + f"SELECT _review_frozen_artifacts('{SID}','{QID}');",
                "permission denied",
            )

    def test_insert_source_into_locked_session_is_rejected(self):
        self.sql("UPDATE exam_sessions SET status='exported';")
        result = self.sql(
            f"INSERT INTO source_questions(session_id,question_no,raw_content,options,correct_key) VALUES ('{SID}',10,'Extra','[\"1\",\"2\",\"3\",\"4\"]','A');",
            check=False,
        )
        self.assertIn("ARTIFACT_LOCKED", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM source_questions;"), "1")

    def test_added_source_invalidates_whole_confirmation_for_new_regeneration(self):
        self.sql(
            f"INSERT INTO source_questions(session_id,question_no,raw_content,options,correct_key) VALUES ('{SID}',10,'Extra','[\"1\",\"2\",\"3\",\"4\"]','A');"
        )
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_reserve_regeneration", SID, QID, uuid4()
        )
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")

    def test_permit_publication_race_keeps_charge_only_if_permit_won(self):
        op = self.reserve()["operation_id"]
        publication = self.publication | {"blueprint_revision_id": str(uuid4())}
        results = self.concurrent(
            self.auth("service_role") + f"SELECT review_acquire_attempt('{op}','{uuid4()}');",
            self.auth("service_role")
            + f"SELECT publish_canonical_blueprint('{SID}',{literal(json.dumps(publication))});",
        )
        self.assertEqual(results[1].returncode, 0, results[1].stderr)
        used = int(self.value("SELECT gemini_review_calls FROM exam_sessions;"))
        if results[0].returncode:
            self.assertIn("REVIEW_SOURCE_MISMATCH", results[0].stderr)
            self.assertEqual(used, 0)
        else:
            self.assertTrue(json.loads(results[0].stdout)["dispatch_permitted"])
            self.assertEqual(used, 1)
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH",
            "review_complete_regeneration",
            op,
            json.dumps(candidate(used)),
            worker=True,
        )
        self.assertEqual(self.fail(op)["api_calls_used"], used)

    def test_completion_publication_race_never_commits_stale_completion(self):
        op = self.reserve()["operation_id"]
        self.permit(op)
        publication = self.publication | {"blueprint_revision_id": str(uuid4())}
        results = self.concurrent(
            self.auth("service_role")
            + f"SELECT review_complete_regeneration('{op}',{literal(json.dumps(candidate(1)))});",
            self.auth("service_role")
            + f"SELECT publish_canonical_blueprint('{SID}',{literal(json.dumps(publication))});",
        )
        self.assertEqual(results[1].returncode, 0, results[1].stderr)
        if results[0].returncode:
            self.assertIn("REVIEW_SOURCE_MISMATCH", results[0].stderr)
            self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")
            self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
            self.fail(op)
        else:
            self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
            self.assertEqual(self.value("SELECT status FROM review_operations;"), "completed")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")

    def test_removing_source_cannot_make_stale_confirmed_exam_ready(self):
        source2, question2 = str(uuid4()), str(uuid4())
        self.sql(f"""INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key)
          VALUES ('{source2}','{SID}',10,'Second','["1","2","3","4"]','A');
          INSERT INTO question_blueprints(source_question_id,confirmed_at) VALUES ('{source2}',now());
          INSERT INTO version_questions(id,version_id,source_question_id,question_no,content,options,correct_key,
            canonical_question_no,canonical_options,canonical_correct_key)
          SELECT '{question2}',version_id,'{source2}',2,'Second candidate','["1","2","3","4"]','A',
            10,'["1","2","3","4"]','A' FROM version_questions WHERE id='{QID}';""")
        artifact2, _ = seed_artifacts(self, SID, source2, OWNER)
        # Model one whole-exam confirmation, as the real RPC records. Merge the
        # isolated trusted fixture revisions without changing either hash/body.
        self.sql(f"""UPDATE source_artifact_confirmations SET result=jsonb_set(result,'{{sources}}',
            (result->'sources') || {literal(json.dumps([artifact2]))}::jsonb)
          WHERE confirmation_id=(SELECT confirmation_id FROM source_artifact_revisions
            WHERE source_revision_id='{self.artifact["source_revision_id"]}');
          UPDATE source_artifact_revisions SET confirmation_id=(SELECT confirmation_id FROM source_artifact_revisions
            WHERE source_revision_id='{self.artifact["source_revision_id"]}')
          WHERE source_revision_id='{artifact2["source_revision_id"]}';
          DELETE FROM source_artifact_confirmations WHERE confirmation_id NOT IN
            (SELECT confirmation_id FROM source_artifact_revisions);
          UPDATE version_questions SET status='approved';""")
        self.assertTrue(self.call("review_get_progress", SID)["progress"]["ready"])
        self.sql("UPDATE exam_sessions SET status='reviewed';")
        self.sql(f"DELETE FROM source_questions WHERE id='{source2}';")
        result = self.call("review_get_progress", SID)["progress"]
        self.assertEqual(result["approved_slots"], result["expected_slots"])
        self.assertFalse(result["ready"])
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "generated")

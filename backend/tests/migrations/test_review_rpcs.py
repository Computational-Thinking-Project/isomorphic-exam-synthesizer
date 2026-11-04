"""Real independent PostgreSQL connections; no AI, HTTP or Supabase query mocks."""

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from artifact_fixture import publish_fixture
from test_stage3_schema import PostgresCase

SID = "10000000-0000-0000-0000-000000000001"
QID = "40000000-0000-0000-0000-000000000001"
OWNER = "00000000-0000-0000-0000-000000000001"
SOURCE = "20000000-0000-0000-0000-000000000001"
VERSION = "30000000-0000-0000-0000-000000000001"


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def candidate(calls=0):
    return {
        "stem_latex": "New candidate",
        "options": ["10", "20", "30", "40"],
        "correct_key": "C",
        "solution_md": "The answer is C.",
        "validation_report": {
            "is_valid": True,
            "math_verified": False,
            "requires_teacher_review": True,
            "checks": [],
            "warnings": [],
        },
        "api_calls_count": calls,
    }


class ReviewRpcTests(PostgresCase):
    def test_rpc_frozen_json_passes_strict_validator_and_uses_canonical_options(self):
        from app.services.review.receipts import reservation_receipt
        from app.services.review.validation import frozen_inputs

        op = uuid4()
        raw = self.reserve(op)
        inputs = frozen_inputs(reservation_receipt(raw, SID, QID, op))
        self.assertEqual(inputs["current_variant"]["options"], ["1", "2", "3", "4"])
        self.assertEqual(inputs["current_variant"]["correct_key"], "A")
        self.assertIsNone(inputs["current_variant"]["solution_md"])
        self.assertEqual(
            self.value(f"SELECT options->>0 FROM version_questions WHERE id='{QID}';"), "2"
        )

    def test_absent_pending_or_corrupt_artifacts_never_reserve_or_charge(self):
        self.sql("UPDATE source_artifact_heads SET blueprint_revision_id=NULL;")
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_reserve_regeneration", SID, QID, uuid4()
        )
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "0")
        self.sql("DELETE FROM source_artifact_heads;")
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_reserve_regeneration", SID, QID, uuid4()
        )

    def test_reconfirmation_after_edit_revert_does_not_rebind_existing_operation(self):
        op = uuid4()
        original = self.reserve(op)
        self.sql(
            "UPDATE source_questions SET solution_md='edit'; UPDATE source_questions SET solution_md=NULL;"
        )
        publish_fixture(self, SID, SOURCE, OWNER)
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_acquire_attempt", op, uuid4(), worker=True
        )
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH",
            "review_complete_regeneration",
            op,
            json.dumps(candidate()),
            worker=True,
        )
        self.assertEqual(self.reserve(op)["snapshot"], original["snapshot"])
        self.assertEqual(self.fail(op)["api_calls_used"], 0)

    def test_lookup_missing_operation_is_read_only(self):
        before = self.value("SELECT row_to_json(s) FROM exam_sessions s;")
        result = self.call("review_lookup_regeneration", SID, QID, uuid4())
        self.assertEqual(result, {"found": False})
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")
        self.assertEqual(self.value("SELECT row_to_json(s) FROM exam_sessions s;"), before)

    def test_lookup_completed_receipt_after_approval_does_not_change_state(self):
        op = uuid4()
        self.reserve(op)
        completed = self.complete(op)
        self.sql("UPDATE exam_sessions SET status='approved',approved_at=now();")
        before = self.value("SELECT row_to_json(s) FROM exam_sessions s;")
        result = self.call("review_lookup_regeneration", SID, QID, op)
        self.assertTrue(result["found"])
        self.assertEqual(result["reservation"]["operation_status"], "completed")
        self.assertEqual(result["reservation"]["settlement"], completed)
        self.assertEqual(self.value("SELECT row_to_json(s) FROM exam_sessions s;"), before)

    def test_lookup_requires_owner_and_never_grants_worker_receipt_access(self):
        op = uuid4()
        self.reserve(op)
        self.expect_error(
            "REVIEW_NOT_FOUND", "review_lookup_regeneration", SID, QID, op, actor=str(uuid4())
        )
        self.expect_error(
            "permission denied", "review_lookup_regeneration", SID, QID, op, worker=True
        )

    def setUp(self):
        super().setUp()
        self.migrate()
        self.sql(f"""
        UPDATE exam_sessions SET status='generated',gemini_review_calls=0;
        INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',1);
        INSERT INTO question_blueprints(source_question_id,confirmed_at) VALUES ('{SOURCE}',now());
        """)
        publish_fixture(self, SID, SOURCE, OWNER)

    @staticmethod
    def auth(role="authenticated", actor=OWNER):
        return (
            f"SET ROLE {role}; SET request.jwt.claim.role={literal(role)}; "
            f"SET request.jwt.claim.sub={literal(actor)}; "
        )

    def call(self, name, *args, worker=False, actor=OWNER, check=True):
        expression = f"SELECT public.{name}({','.join(literal(arg) for arg in args)});"
        response = self.sql(
            self.auth("service_role" if worker else "authenticated", actor) + expression,
            check=check,
        )
        if not check:
            return response
        return json.loads(response.stdout.strip().splitlines()[-1])

    def reserve(self, op=None, question=QID):
        op = op or uuid4()
        return self.call("review_reserve_regeneration", SID, question, op)

    def permit(self, op, attempt=None):
        return self.call("review_acquire_attempt", op, attempt or uuid4(), worker=True)

    def complete(self, op, payload=None, check=True):
        return self.call(
            "review_complete_regeneration",
            op,
            json.dumps(payload or candidate()),
            worker=True,
            check=check,
        )

    def fail(self, op):
        return self.call("review_fail_regeneration", op, "GENERATION_FAILED", worker=True)

    def expect_error(self, code, name, *args, worker=False, actor=OWNER):
        result = self.call(name, *args, worker=worker, actor=actor, check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(code, result.stderr)

    def concurrent(self, *scripts):
        # Each docker exec opens a separate psql connection and database transaction.
        barrier = Barrier(len(scripts))

        def run(script):
            barrier.wait(timeout=10)
            return self.sql(script, check=False)

        with ThreadPoolExecutor(max_workers=len(scripts)) as executor:
            return list(executor.map(run, scripts))

    def test_reserve_replay_binding_no_upfront_charge_and_frozen_rows(self):
        op = uuid4()
        first = self.reserve(op)
        second = self.reserve(op)
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["snapshot"], second["snapshot"])
        self.assertEqual(first["snapshot"]["format"], "confirmed_artifacts_v1")
        self.assertEqual(
            first["snapshot"]["source_snapshot"]["content_hash"],
            first["snapshot"]["blueprint_source_fingerprint"],
        )
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "1")
        self.expect_error(
            "REVIEW_IDEMPOTENCY_CONFLICT", "review_reserve_regeneration", SID, uuid4(), op
        )

    def test_permits_26_to_30_then_deny_and_restart_replay(self):
        self.sql("UPDATE exam_sessions SET gemini_review_calls=26;")
        op = self.reserve()["operation_id"]
        attempt = uuid4()
        first = self.permit(op, attempt)
        self.assertEqual(first["calls_used"], 27)
        # Every call uses a new psql process; nothing relies on Python instance state.
        replay = self.permit(op, attempt)
        self.assertFalse(replay["dispatch_permitted"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["calls_used"], 27)
        for expected in (28, 29, 30):
            self.assertEqual(self.permit(op)["calls_used"], expected)
        self.assertFalse(self.permit(op)["dispatch_permitted"])
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "30")
        self.assertEqual(
            self.value("SELECT count(*) FROM review_attempts WHERE dispatch_permitted;"), "4"
        )

    def test_four_per_operation_ceiling_and_failure_keeps_charge(self):
        op = self.reserve()["operation_id"]
        for _ in range(4):
            self.assertTrue(self.permit(op)["dispatch_permitted"])
        self.assertFalse(self.permit(op)["dispatch_permitted"])
        self.assertEqual(self.fail(op)["api_calls_used"], 4)
        self.assertTrue(self.fail(op)["replayed"])
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "4")
        self.assertEqual(self.value("SELECT status FROM version_questions;"), "pending_review")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")

    def test_lost_permit_response_reconciles_without_adapter_count_or_refund(self):
        op = self.reserve()["operation_id"]
        self.permit(op)  # Simulate a committed grant whose reply never reaches the adapter.
        outcome = self.call("review_fail_regeneration", op, "REVIEW_PERMIT_UNCERTAIN", worker=True)
        self.assertEqual(outcome["api_calls_used"], 1)
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")
        self.assertEqual(self.value("SELECT api_calls_used FROM review_logs;"), "1")
        self.expect_error("REVIEW_STALE", "review_acquire_attempt", op, uuid4(), worker=True)

    def test_last_session_permit_race_grants_exactly_one(self):
        self.sql("UPDATE exam_sessions SET gemini_review_calls=29;")
        op = self.reserve()["operation_id"]
        scripts = [
            self.auth("service_role") + f"SELECT review_acquire_attempt('{op}','{uuid4()}');"
            for _ in range(2)
        ]
        results = self.concurrent(*scripts)
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        grants = [json.loads(result.stdout.strip()) for result in results]
        self.assertEqual(sum(grant["dispatch_permitted"] for grant in grants), 1)
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "30")

    def test_same_attempt_race_grants_once_and_replays_once(self):
        op = self.reserve()["operation_id"]
        attempt = uuid4()
        script = self.auth("service_role") + f"SELECT review_acquire_attempt('{op}','{attempt}');"
        results = self.concurrent(script, script)
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        permits = [json.loads(result.stdout.strip()) for result in results]
        self.assertEqual(sum(p["dispatch_permitted"] for p in permits), 1)
        self.assertEqual(sum(p["replayed"] for p in permits), 1)
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")

    def test_reservation_race_only_one_active_operation(self):
        scripts = [
            self.auth() + f"SELECT review_reserve_regeneration('{SID}','{QID}','{uuid4()}');"
            for _ in range(2)
        ]
        results = self.concurrent(*scripts)
        self.assertEqual(sum(r.returncode == 0 for r in results), 1)
        self.assertIn("REVIEW_BUSY", next(r.stderr for r in results if r.returncode))
        self.assertEqual(
            self.value("SELECT count(*) FROM review_operations WHERE status='active';"), "1"
        )

    def test_completion_owns_new_canonical_audit_invalidation_and_replay(self):
        self.sql(f"""UPDATE exam_versions SET is_finalized=true,shuffle_seed='old',permutations='{{}}';
        INSERT INTO answer_keys(version_id,question_no,correct_option) VALUES ('{VERSION}',1,'B');""")
        op = self.reserve()["operation_id"]
        self.permit(op)
        result = self.complete(op, candidate(1))
        self.assertNotEqual(result["question_id"], QID)
        self.assertEqual(result["invalidated_version_ids"], [VERSION])
        self.assertEqual(
            self.value(
                "SELECT canonical_correct_key,status FROM version_questions WHERE is_current;"
            ),
            "C|pending_review",
        )
        self.assertEqual(
            self.value(f"SELECT canonical_correct_key FROM version_questions WHERE id='{QID}';"),
            "A",
        )
        self.assertEqual(self.value("SELECT count(*) FROM answer_keys;"), "0")
        self.assertEqual(
            self.value(
                "SELECT is_finalized,shuffle_seed IS NULL,permutations IS NULL FROM exam_versions;"
            ),
            "f|t|t",
        )
        self.assertEqual(
            self.value("SELECT user_id,api_calls_used FROM review_logs;"), f"{OWNER}|1"
        )
        self.assertTrue(self.complete(op, candidate(1))["replayed"])
        self.assertEqual(self.value("SELECT count(*) FROM version_questions;"), "2")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
        changed = candidate(1)
        changed["stem_latex"] = "Different payload"
        self.expect_error(
            "REVIEW_IDEMPOTENCY_CONFLICT",
            "review_complete_regeneration",
            op,
            json.dumps(changed),
            worker=True,
        )

    def test_complete_then_accept_and_revert_restore_root_without_snapshot_mutation(self):
        op = self.reserve()["operation_id"]
        new_id = self.complete(op)[
            "question_id"
        ]  # Explicit zero-provider-call integration fixture.
        accepted = self.call("review_accept_question", SID, new_id, uuid4())
        self.assertTrue(accepted["progress"]["ready"])
        action = uuid4()
        reverted = self.call("review_revert_question", SID, new_id, action)
        self.assertEqual(reverted["question_id"], QID)
        self.assertEqual(reverted["session_status"], "reviewed")
        self.assertTrue(self.call("review_revert_question", SID, new_id, action)["replayed"])
        self.assertEqual(
            self.value("SELECT count(*) FROM version_questions WHERE is_current;"), "1"
        )
        self.assertEqual(
            self.value("SELECT canonical_correct_key FROM version_questions WHERE is_current;"), "A"
        )
        self.expect_error("REVIEW_STALE", "review_accept_question", SID, new_id, uuid4())

    def test_revert_first_candidate_is_idempotent_approval(self):
        action = uuid4()
        first = self.call("review_revert_question", SID, QID, action)
        second = self.call("review_revert_question", SID, QID, action)
        self.assertTrue(first["progress"]["ready"])
        self.assertTrue(second["replayed"])
        self.call("review_revert_question", SID, QID, uuid4())
        self.assertEqual(self.value("SELECT count(*) FROM version_questions;"), "1")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
        self.expect_error("REVIEW_IDEMPOTENCY_CONFLICT", "review_accept_question", SID, QID, action)

    def test_recovery_expiry_replay_and_late_worker_cannot_own_new_reservation(self):
        op = self.reserve()["operation_id"]
        self.permit(op)
        self.assertFalse(self.call("review_recover_regeneration", op, worker=True)["recovered"])
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        recovered = self.call("review_recover_regeneration", op, worker=True)
        self.assertTrue(recovered["recovered"])
        self.assertEqual(recovered["api_calls_used"], 1)
        self.assertTrue(self.call("review_recover_regeneration", op, worker=True)["replayed"])
        new_op = self.reserve()["operation_id"]
        self.expect_error(
            "REVIEW_STALE",
            "review_complete_regeneration",
            op,
            json.dumps(candidate(1)),
            worker=True,
        )
        self.expect_error(
            "REVIEW_STALE", "review_fail_regeneration", op, "GENERATION_FAILED", worker=True
        )
        self.assertEqual(
            self.value("SELECT operation_id FROM review_operations WHERE status='active';"), new_op
        )
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")

    def test_recovery_race_only_one_audit_and_no_refund(self):
        op = self.reserve()["operation_id"]
        self.permit(op)
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        script = self.auth("service_role") + f"SELECT review_recover_regeneration('{op}');"
        results = self.concurrent(script, script)
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(json.loads(r.stdout.strip())["replayed"] for r in results), 1)
        self.assertEqual(self.value("SELECT count(*),sum(api_calls_used) FROM review_logs;"), "1|1")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")

    def test_source_change_blocks_dispatch_and_completion_but_can_fail_safely(self):
        op = self.reserve()["operation_id"]
        self.sql("UPDATE source_questions SET raw_content='Changed after reservation';")
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_acquire_attempt", op, uuid4(), worker=True
        )
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH",
            "review_complete_regeneration",
            op,
            json.dumps(candidate()),
            worker=True,
        )
        self.assertEqual(self.fail(op)["api_calls_used"], 0)

    def test_payload_validation_and_success_count_mismatch_leave_current_intact(self):
        op = self.reserve()["operation_id"]
        self.permit(op)
        mutations = [
            {"api_calls_count": 0},
            {"options": ["x"]},
            {"options": ["x", "x", "y", "z"]},
            {"correct_key": "E"},
            {"content": "Mismatched alias"},
            {"validation_report": {"is_valid": False}},
            {"stem_latex": ""},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                invalid = {**candidate(1), **mutation}
                self.expect_error(
                    "REVIEW_INVALID_PAYLOAD",
                    "review_complete_regeneration",
                    op,
                    json.dumps(invalid),
                    worker=True,
                )
        self.assertEqual(
            self.value("SELECT id,status FROM version_questions WHERE is_current;"),
            f"{QID}|regenerating",
        )
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")

    def inject_failure(self, table, event):
        self.sql(f"""CREATE FUNCTION injected_failure() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'injected transaction failure'; END $$;
        CREATE TRIGGER injected_failure BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION injected_failure();""")

    def test_audit_failure_rolls_back_completion_but_not_previously_charged_permit(self):
        op = self.reserve()["operation_id"]
        self.permit(op)
        self.inject_failure("review_logs", "INSERT")
        result = self.complete(op, candidate(1), check=False)
        self.assertIn("injected transaction failure", result.stderr)
        self.assertEqual(
            self.value("SELECT count(*),bool_and(is_current) FROM version_questions;"), "1|t"
        )
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")

    def test_invalidation_failure_rolls_back_candidate_audit_and_settlement(self):
        self.sql(
            f"INSERT INTO answer_keys(version_id,question_no,correct_option) VALUES ('{VERSION}',1,'B');"
        )
        op = self.reserve()["operation_id"]
        self.inject_failure("answer_keys", "DELETE")
        result = self.complete(op, check=False)
        self.assertIn("injected transaction failure", result.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM version_questions;"), "1")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")
        self.assertEqual(self.value("SELECT count(*) FROM answer_keys;"), "1")
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")

    def test_reserve_candidate_write_failure_leaves_no_operation_or_charge(self):
        self.inject_failure("version_questions", "UPDATE")
        self.expect_error(
            "injected transaction failure", "review_reserve_regeneration", SID, QID, uuid4()
        )
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")
        self.assertEqual(self.value("SELECT status FROM version_questions;"), "pending_review")

    def test_progress_checks_missing_versions_sources_and_is_read_only(self):
        self.sql(
            "UPDATE generation_configs SET n_versions=2; UPDATE version_questions SET status='approved';"
        )
        progress = self.call("review_get_progress", SID)["progress"]
        self.assertEqual(progress["expected_slots"], 2)
        self.assertEqual(progress["missing_slots"], 1)
        self.assertFalse(progress["ready"])
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "generated")
        self.call("review_accept_question", SID, QID, uuid4())
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "generated")
        self.sql("UPDATE generation_configs SET n_versions=1;")
        self.call("review_accept_question", SID, QID, uuid4())
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "reviewed")

    def test_ambiguous_or_unconfirmed_config_fails_without_reservation(self):
        self.sql(f"INSERT INTO generation_configs(session_id,n_versions) VALUES ('{SID}',1);")
        self.expect_error(
            "REVIEW_SOURCE_MISMATCH", "review_reserve_regeneration", SID, QID, uuid4()
        )
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")

    def test_other_owner_unknown_operation_and_role_boundaries(self):
        stranger = "00000000-0000-0000-0000-000000000099"
        self.expect_error("REVIEW_NOT_FOUND", "review_get_progress", SID, actor=stranger)
        self.expect_error(
            "REVIEW_NOT_FOUND", "review_reserve_regeneration", SID, QID, uuid4(), actor=stranger
        )
        self.expect_error(
            "REVIEW_NOT_FOUND", "review_acquire_attempt", uuid4(), uuid4(), worker=True
        )
        self.expect_error("permission denied", "review_acquire_attempt", uuid4(), uuid4())
        self.expect_error("permission denied", "review_get_progress", SID, worker=True)
        for role in ("anon", "authenticated", "service_role"):
            self.assert_sql_fails(
                self.auth(role) + "SELECT * FROM review_attempts;", "permission denied"
            )
            self.assertEqual(
                self.value(
                    f"SELECT has_function_privilege('{role}','public._review_recalculate(uuid)','EXECUTE');"
                ),
                "f",
            )

    def test_new_mutations_locked_but_committed_receipts_reconcile_after_approval(self):
        action = uuid4()
        self.call("review_accept_question", SID, QID, action)
        self.sql("UPDATE exam_sessions SET status='approved',approved_at=now();")
        self.assertTrue(self.call("review_accept_question", SID, QID, action)["replayed"])
        self.expect_error("REVIEW_LOCKED", "review_reserve_regeneration", SID, QID, uuid4())
        self.expect_error("REVIEW_LOCKED", "review_revert_question", SID, QID, uuid4())

    def test_approval_transaction_committing_first_blocks_waiting_reserve(self):
        # Keep a transaction open in psql. Wait for evidence from the server,
        # not a timing assumption, that reserve is blocked on this parent's lock.
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
            encoding="utf-8",
        )
        try:
            process.stdin.write(
                f"BEGIN; SELECT id FROM exam_sessions WHERE id='{SID}' FOR UPDATE;\n"
            )
            process.stdin.flush()
            with ThreadPoolExecutor(max_workers=2) as executor:
                self.assertEqual(
                    executor.submit(process.stdout.readline).result(timeout=10).strip(), SID
                )
                name = "reserve_" + uuid4().hex
                future = executor.submit(
                    self.sql,
                    self.auth()
                    + f"SET application_name='{name}'; SELECT review_reserve_regeneration('{SID}','{QID}','{uuid4()}');",
                    check=False,
                )
                released = False
                try:
                    deadline = time.monotonic() + 10
                    while (
                        self.value(
                            f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{name}' AND cardinality(pg_blocking_pids(pid))>0;"
                        )
                        != "1"
                    ):
                        if future.done() or time.monotonic() > deadline:
                            self.fail("Reserve did not wait on the parent's transaction lock")
                        time.sleep(0.02)
                    process.stdin.write(
                        "UPDATE exam_sessions SET status='approved',approved_at=now(); COMMIT;\n"
                    )
                    process.stdin.flush()
                    released = True
                finally:
                    if not released:
                        process.stdin.write("ROLLBACK;\n")
                        process.stdin.flush()
                result = future.result(timeout=10)
            self.assertIn("REVIEW_LOCKED", result.stderr)
        finally:
            # Closing stdin ends the psql transaction even on a failed assertion.
            process.stdin.close()
            process.stdin = None
            process.communicate(timeout=15)
        self.assertEqual(self.value("SELECT count(*) FROM review_operations;"), "0")

    def test_attempt_id_cannot_be_rebound_to_another_operation(self):
        first_op = self.reserve()["operation_id"]
        attempt = uuid4()
        self.permit(first_op, attempt)
        self.fail(first_op)
        second_op = self.reserve()["operation_id"]
        self.expect_error(
            "REVIEW_IDEMPOTENCY_CONFLICT", "review_acquire_attempt", second_op, attempt, worker=True
        )
        self.expect_error(
            "REVIEW_NOT_FOUND", "review_acquire_attempt", uuid4(), uuid4(), worker=True
        )
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")

    def test_accept_other_slot_while_regeneration_active_cannot_mark_reviewed(self):
        second_q = uuid4()
        self.sql(f"""UPDATE generation_configs SET n_versions=2;
        INSERT INTO exam_versions(id,session_id,version_code) VALUES ('{uuid4()}','{SID}','102');
        INSERT INTO version_questions(id,version_id,source_question_id,question_no,content,options,correct_key,
          canonical_question_no,canonical_options,canonical_correct_key)
        SELECT '{second_q}',v.id,'{SOURCE}',1,'Peer','["1","2","3","4"]','A',9,'["1","2","3","4"]','A'
        FROM exam_versions v WHERE version_code='102';""")
        op = self.reserve()["operation_id"]
        accepted = self.call("review_accept_question", SID, second_q, uuid4())
        self.assertFalse(accepted["progress"]["ready"])
        self.assertEqual(accepted["progress"]["regenerating_slots"], 1)
        self.expect_error("REVIEW_BUSY", "review_revert_question", SID, QID, uuid4())
        self.fail(op)

    def test_expired_lease_blocks_new_permit_and_complete_without_auto_recovery(self):
        op = self.reserve()["operation_id"]
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        self.expect_error("REVIEW_STALE", "review_acquire_attempt", op, uuid4(), worker=True)
        self.expect_error(
            "REVIEW_STALE", "review_complete_regeneration", op, json.dumps(candidate()), worker=True
        )
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
        self.assertEqual(self.value("SELECT count(*) FROM review_attempts;"), "0")
        self.assertTrue(self.call("review_recover_regeneration", op, worker=True)["recovered"])

    def test_revert_audit_failure_rolls_back_demote_and_promote(self):
        op = self.reserve()["operation_id"]
        new_q = self.complete(op)["question_id"]
        self.inject_failure("review_logs", "INSERT")
        self.expect_error(
            "injected transaction failure", "review_revert_question", SID, new_q, uuid4()
        )
        self.assertEqual(self.value("SELECT id FROM version_questions WHERE is_current;"), new_q)
        self.assertEqual(self.value("SELECT count(*) FROM review_action_receipts;"), "0")

    def test_failure_audit_error_keeps_operation_recoverable_and_charge_intact(self):
        op = self.reserve()["operation_id"]
        self.permit(op)
        self.inject_failure("review_logs", "INSERT")
        self.expect_error(
            "injected transaction failure",
            "review_fail_regeneration",
            op,
            "GENERATION_FAILED",
            worker=True,
        )
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
        self.assertEqual(self.value("SELECT status FROM version_questions;"), "regenerating")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")

    def test_migration_replay_preserves_ledger_and_execute_permissions(self):
        op = self.reserve()["operation_id"]
        attempt = uuid4()
        self.permit(op, attempt)
        self.migrate()
        self.assertTrue(self.permit(op, attempt)["replayed"])
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")
        self.assertEqual(self.fail(op)["api_calls_used"], 1)

    def test_session_recovery_discovers_private_operation_after_worker_restart(self):
        self.sql("UPDATE version_questions SET status='approved';")
        op = self.reserve()["operation_id"]
        self.permit(op)  # Committed grant; the restarted worker may never see its response.
        self.assertEqual(self.value("SELECT regeneration_id IS NULL FROM version_questions;"), "t")
        denied = self.sql(
            self.auth("service_role") + "SELECT * FROM review_operations;", check=False
        )
        self.assertNotEqual(denied.returncode, 0)
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        recovered = self.call("review_recover_session", SID, worker=True)
        self.assertEqual(recovered["recovered_count"], 1)
        receipt = recovered["recoveries"][0]
        self.assertEqual(receipt["operation_id"], op)
        self.assertEqual(receipt["api_calls_used"], 1)
        self.assertTrue(receipt["recovered"])
        self.assertFalse(receipt["replayed"])
        self.assertEqual(recovered["session_status"], "reviewed")
        self.assertEqual(self.value("SELECT status FROM version_questions;"), "approved")
        self.assertEqual(self.value("SELECT user_id FROM review_logs;"), OWNER)
        self.assertEqual(self.call("review_recover_session", SID, worker=True)["recoveries"], [])
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")
        new_op = self.reserve()["operation_id"]
        self.assertNotEqual(new_op, op)
        self.expect_error(
            "REVIEW_STALE",
            "review_complete_regeneration",
            op,
            json.dumps(candidate(1)),
            worker=True,
        )
        self.assertEqual(self.value("SELECT status FROM version_questions;"), "regenerating")

    def test_session_recovery_uses_operation_lease_and_is_read_only_without_expiry(self):
        empty = self.call("review_recover_session", SID, worker=True)
        self.assertEqual(
            empty,
            {
                "session_id": SID,
                "session_status": "generated",
                "recovered_count": 0,
                "recoveries": [],
            },
        )
        self.reserve()
        self.sql("UPDATE version_questions SET updated_at=now()-interval '1 day';")
        self.assertEqual(self.call("review_recover_session", SID, worker=True), empty)
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "0")
        self.expect_error("REVIEW_NOT_FOUND", "review_recover_session", uuid4(), worker=True)
        for role in ("anon", "authenticated"):
            result = self.sql(
                self.auth(role) + f"SELECT review_recover_session('{SID}');", check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("permission denied", result.stderr)
        result = self.sql(
            self.auth("service_role")
            + f"SET request.jwt.claim.role='authenticated'; SELECT review_recover_session('{SID}');",
            check=False,
        )
        self.assertIn("REVIEW_WORKER_REQUIRED", result.stderr)

    def test_concurrent_session_recovery_settles_once(self):
        self.reserve()
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        script = self.auth("service_role") + f"SELECT review_recover_session('{SID}');"
        results = self.concurrent(script, script)
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(json.loads(r.stdout)["recovered_count"] for r in results), 1)
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "recovered")

    def test_session_discovery_races_direct_recovery_and_late_completion(self):
        op = self.reserve()["operation_id"]
        self.permit(op)
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        discovery, direct, late = self.concurrent(
            self.auth("service_role") + f"SELECT review_recover_session('{SID}');",
            self.auth("service_role") + f"SELECT review_recover_regeneration('{op}');",
            self.auth("service_role")
            + f"SELECT review_complete_regeneration('{op}',{literal(json.dumps(candidate(1)))});",
        )
        self.assertEqual(discovery.returncode, 0, discovery.stderr)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertNotEqual(late.returncode, 0)
        self.assertIn("REVIEW_STALE", late.stderr)
        self.assertEqual(self.value("SELECT count(*) FROM review_logs;"), "1")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")
        self.assertEqual(
            self.value("SELECT count(*) FROM version_questions WHERE is_current;"), "1"
        )

    def test_session_recovery_audit_failure_rolls_back_and_can_retry(self):
        self.reserve()
        self.permit(self.value("SELECT operation_id FROM review_operations;"))
        self.sql("UPDATE review_operations SET expires_at=now()-interval '1 second';")
        self.inject_failure("review_logs", "INSERT")
        self.expect_error(
            "injected transaction failure", "review_recover_session", SID, worker=True
        )
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
        self.assertEqual(self.value("SELECT status FROM version_questions;"), "regenerating")
        self.assertEqual(self.value("SELECT gemini_review_calls FROM exam_sessions;"), "1")
        self.sql("DROP TRIGGER injected_failure ON review_logs;")
        self.assertEqual(
            self.call("review_recover_session", SID, worker=True)["recovered_count"], 1
        )

    def test_session_recovery_does_not_scan_other_sessions_and_survives_replay(self):
        other = uuid4()
        self.reserve()
        self.sql(
            f"INSERT INTO exam_sessions(id,user_id,title,status) VALUES ('{other}','{OWNER}','Other','generated'); UPDATE review_operations SET expires_at=now()-interval '1 second';"
        )
        self.assertEqual(
            self.call("review_recover_session", other, worker=True)["recovered_count"], 0
        )
        self.assertEqual(self.value("SELECT status FROM review_operations;"), "active")
        self.migrate()
        self.assertEqual(
            self.call("review_recover_session", SID, worker=True)["recovered_count"], 1
        )
        self.assertEqual(
            self.value(
                "SELECT has_function_privilege('authenticated','review_recover_session(uuid)','EXECUTE');"
            ),
            "f",
        )

    def test_global_id_rebinding_races_across_sessions_return_domain_conflict(self):
        sid2, source2, version2, qid2 = (str(uuid4()) for _ in range(4))
        self.sql(f"""
        INSERT INTO exam_sessions(id,user_id,title,status) VALUES ('{sid2}','{OWNER}','Second fixture','generated');
        INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key)
          VALUES ('{source2}','{sid2}',9,'Source','["1","2","3","4"]','A');
        INSERT INTO question_blueprints(source_question_id,confirmed_at) VALUES ('{source2}',now());
        INSERT INTO generation_configs(session_id,n_versions) VALUES ('{sid2}',1);
        INSERT INTO exam_versions(id,session_id,version_code) VALUES ('{version2}','{sid2}','101');
        INSERT INTO version_questions(id,version_id,source_question_id,question_no,content,options,correct_key,
          canonical_question_no,canonical_options,canonical_correct_key)
          VALUES ('{qid2}','{version2}','{source2}',1,'Candidate','["1","2","3","4"]','A',9,'["1","2","3","4"]','A');
        """)
        publish_fixture(self, sid2, source2, OWNER)
        shared_op = uuid4()
        sessions = [(SID, QID), (sid2, qid2)]
        results = self.concurrent(
            *[
                self.auth() + f"SELECT review_reserve_regeneration('{sid}','{qid}','{shared_op}');"
                for sid, qid in sessions
            ]
        )
        self.assertEqual(sum(r.returncode == 0 for r in results), 1)
        self.assertIn(
            "REVIEW_IDEMPOTENCY_CONFLICT", next(r.stderr for r in results if r.returncode)
        )
        loser_sid, loser_qid = sessions[next(i for i, r in enumerate(results) if r.returncode)]
        other_op = self.call("review_reserve_regeneration", loser_sid, loser_qid, uuid4())[
            "operation_id"
        ]
        attempt = uuid4()
        results = self.concurrent(
            *[
                self.auth("service_role") + f"SELECT review_acquire_attempt('{op}','{attempt}');"
                for op in (shared_op, other_op)
            ]
        )
        self.assertEqual(sum(r.returncode == 0 for r in results), 1)
        self.assertIn(
            "REVIEW_IDEMPOTENCY_CONFLICT", next(r.stderr for r in results if r.returncode)
        )
        self.assertEqual(self.value("SELECT sum(gemini_review_calls) FROM exam_sessions;"), "1")
        self.fail(shared_op)
        self.fail(other_op)
        action = uuid4()
        results = self.concurrent(
            *[
                self.auth() + f"SELECT review_accept_question('{sid}','{qid}','{action}');"
                for sid, qid in sessions
            ]
        )
        self.assertEqual(sum(r.returncode == 0 for r in results), 1)
        self.assertIn(
            "REVIEW_IDEMPOTENCY_CONFLICT", next(r.stderr for r in results if r.returncode)
        )
        self.assertEqual(self.value("SELECT count(*) FROM review_action_receipts;"), "1")

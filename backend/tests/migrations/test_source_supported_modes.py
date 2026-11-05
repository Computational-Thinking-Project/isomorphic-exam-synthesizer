"""Canonical profile 1.0 on real SQL heads, never legacy Blueprint rows."""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import test_source_confirmation_revision as revision_fixtures
from test_review_rpcs import OWNER, SID, literal
from test_stage3_schema import ROOT


class SupportedModeTests(revision_fixtures.SourceRevisionTests):
    def setUp(self):
        super().setUp()
        self.sql(
            (ROOT / "backend/migrations/012_source_artifact_supported_modes.sql").read_text(
                encoding="utf-8"
            )
        )

    def state(self):
        return self.call("get_source_artifacts", SID, worker=False)

    def test_single_rpc_modes_pending_running_failed_ready(self):
        self.confirm()
        self.assertIsNone(self.state()["supported_modes"])
        job = str(uuid4())
        self.call("claim_source_production", SID, self.sources[0]["source_revision_id"], job)
        self.assertEqual(self.state()["production"][0]["status"], "running")
        self.assertIsNone(self.state()["supported_modes"])
        self.call(
            "fail_source_production",
            SID,
            self.sources[0]["source_revision_id"],
            job,
            "FIXTURE_FAILURE",
        )
        self.assertEqual(self.state()["production"][0]["status"], "failed")
        self.assertIsNone(self.state()["supported_modes"])
        self.publish()
        state = self.state()
        self.assertTrue(state["ready"])
        self.assertEqual(
            [m["id"] for m in state["supported_modes"]],
            ["NUMERICAL", "context_swap", "parameter_variation"],
        )
        self.assertTrue(
            all(
                m["question_count"] == 1 and m["is_available"] is True
                for m in state["supported_modes"]
            )
        )

    def test_none_only_is_valid_ready_empty_array(self):
        from app.services.blueprint.artifacts import prepare_blueprint_artifact

        document = deepcopy(self.blueprint)
        policy = document["requirement"]["variation_policy"]
        policy["allowed_transformations"] = [
            t for t in policy["allowed_transformations"] if t["dimension"] == "wording"
        ]
        publication = prepare_blueprint_artifact(self.sources[0], document)
        publication["producer_job_id"] = str(uuid4())
        self.confirm()
        self.publish(publication)
        state = self.state()
        self.assertTrue(state["ready"])
        self.assertEqual(state["supported_modes"], [])

    def test_history_is_ignored_after_new_source_head_and_duplicate_transforms_count_once(self):
        from app.services.blueprint.artifacts import prepare_blueprint_artifact

        self.confirm()
        self.publish()
        # Real invalidation, edit-and-revert and confirmation establish a new head.
        self.sql(
            "UPDATE source_questions SET raw_content=raw_content||'x'; UPDATE source_questions SET raw_content=left(raw_content,-1); UPDATE exam_sessions SET status='draft';"
        )
        self.revision, self.confirmation_id = self.token(), str(uuid4())
        from app.services.blueprint.artifacts import prepare_source_artifacts

        self.sources = prepare_source_artifacts(SID, [self.row])
        self.confirm()
        self.assertIsNone(self.state()["supported_modes"])
        doc = deepcopy(self.blueprint)
        transforms = doc["requirement"]["variation_policy"]["allowed_transformations"]
        transforms[:] = [t for t in transforms if t["dimension"] == "context"]
        duplicate = deepcopy(transforms[0])
        duplicate["id"] = "V_DUPLICATE"
        transforms.append(duplicate)
        publication = prepare_blueprint_artifact(self.sources[0], doc)
        publication["producer_job_id"] = str(uuid4())
        self.publish(publication)
        self.assertEqual([m["id"] for m in self.state()["supported_modes"]], ["context_swap"])
        self.assertEqual(self.state()["supported_modes"][0]["question_count"], 1)
        self.assertEqual(self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "2")

    def test_partial_batch_is_pending_then_partial_mode_is_disabled(self):
        from app.models.schemas import SourceQuestion
        from app.services.blueprint.adapters import source_to_item
        from app.services.blueprint.artifacts import (
            prepare_blueprint_artifact,
            prepare_source_artifacts,
        )

        row = dict(self.row, id=str(uuid4()), question_no=2)
        self.sql(
            f"INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key) VALUES ({literal(row['id'])},'{SID}',2,{literal(row['raw_content'])},{literal(json.dumps(row['options']))},'A');"
        )
        self.sources = prepare_source_artifacts(SID, [self.row, row])
        self.revision = self.token()
        self.confirm()
        first = prepare_blueprint_artifact(self.sources[0], self.blueprint)
        first["producer_job_id"] = str(uuid4())
        self.publish(first)
        self.assertFalse(self.state()["ready"])
        self.assertIsNone(self.state()["supported_modes"])
        old = source_to_item(SourceQuestion.model_validate(self.sources[0]["confirmed_input"]))[
            "source"
        ]["question_id"]
        new = source_to_item(SourceQuestion.model_validate(self.sources[1]["confirmed_input"]))[
            "source"
        ]["question_id"]
        doc = json.loads(json.dumps(self.blueprint).replace(old, new))
        policy = doc["requirement"]["variation_policy"]
        policy["allowed_transformations"] = [
            t for t in policy["allowed_transformations"] if t["dimension"] == "context"
        ]
        second = prepare_blueprint_artifact(self.sources[1], doc)
        second["producer_job_id"] = str(uuid4())
        self.publish(second)
        modes = {m["id"]: m for m in self.state()["supported_modes"]}
        self.assertEqual(modes["context_swap"]["question_count"], 2)
        self.assertTrue(modes["context_swap"]["is_available"])
        self.assertEqual(modes["NUMERICAL"]["question_count"], 1)
        self.assertFalse(modes["NUMERICAL"]["is_available"])
        self.assertFalse(modes["parameter_variation"]["is_available"])

    def test_modes_permissions_service_owner_foreign_anon(self):
        self.confirm()
        self.publish()
        self.assertEqual(
            self.call("get_source_artifacts", SID)["supported_modes"],
            self.state()["supported_modes"],
        )
        foreign = self.call(
            "get_source_artifacts", SID, worker=False, actor=str(uuid4()), check=False
        )
        self.assertIn("ARTIFACT_NOT_FOUND", foreign.stderr)
        from test_review_rpcs import ReviewRpcTests

        denied = self.sql(
            ReviewRpcTests.auth("anon", OWNER) + f"SELECT get_source_artifacts('{SID}');",
            check=False,
        )
        self.assertIn("permission denied", denied.stderr)

    def test_invalid_canonical_mapping_fails_closed(self):
        self.confirm()
        self.publish()
        # Corruption injection is distinct from valid producer fixtures.
        self.sql(
            "UPDATE canonical_blueprint_revisions SET canonical_blueprint=jsonb_set(canonical_blueprint,'{requirement,variation_policy,allowed_transformations}', '[{\"dimension\":\"invented\"}]');"
        )
        result = self.call("get_source_artifacts", SID, worker=False, check=False)
        self.assertIn("ARTIFACT_INVALID_CANONICAL_MODES", result.stderr)

    def test_publication_and_read_share_parent_lock_snapshot(self):
        import test_review_rpcs as rpc

        self.confirm()
        publication = self.publication
        self.call(
            "claim_source_production",
            SID,
            publication["source_revision_id"],
            publication["producer_job_id"],
        )
        held = self.hold(
            rpc.ReviewRpcTests.auth("service_role", OWNER)
            + f"SELECT publish_canonical_blueprint('{SID}',{literal(json.dumps(publication))})"
        )
        try:
            with ThreadPoolExecutor() as pool:
                future = pool.submit(self.state)
                import time

                time.sleep(0.15)
                self.assertFalse(future.done())
                out, err = held.communicate(timeout=8)
                self.assertEqual(held.returncode, 0, err)
                state = future.result()
            self.assertTrue(state["ready"])
            self.assertTrue(all(m["is_available"] for m in state["supported_modes"]))
        finally:
            if held.poll() is None:
                held.kill()


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        SupportedModeTests(name)
        for name in sorted(SupportedModeTests.__dict__)
        if name.startswith("test_")
    )

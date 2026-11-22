"""Historical reviewed rows -> actual shuffle/approval -> Q01 export.

SQL/RLS/ledger reads are real; this deliberately does not simulate the still
pending upstream Q01 producer migration or deployed Supabase transport.
"""

import asyncio
import json
import unittest
from uuid import uuid4

from test_export_snapshot_pg import (
    OWNER,
    ExportSnapshotPostgresFixture,
    SqlReadClient,
    auth,
    literal,
)

from app.models.schemas import ReviewDomainException
from app.services.exporter.snapshot_adapter import load_approved_export_snapshot
from app.services.finalize.repository import FinalizeRepository


class ExportQ01PostgresTests(ExportSnapshotPostgresFixture):
    def seed(self):
        # Insert the historical empty canonical value initially; never mutate
        # an existing candidate's immutable canonical snapshot for a test.
        for version in self.expected["versions"]:
            for question in version["questions"]:
                question["solution_md"] = ""
        # Also reused as a seed by the private-export fixture in TASK-08.
        ExportSnapshotPostgresFixture.seed(self)
        clone = "clone" in self._testMethodName
        if "on_on" in self._testMethodName:
            self.sql(
                "UPDATE generation_configs SET ordering_preferences="
                '\'{"shuffle_questions":true,"shuffle_options":true}\'::jsonb;'
            )
        self.kind = "ORIGINAL_CLONE" if clone else "CONFIRMED_SOURCE_FALLBACK"
        snap_id, token = str(uuid4()), str(uuid4())
        modes = "[]" if clone else '["NUMERICAL"]'
        dims = "[]" if clone else '["values"]'
        report = (
            {}
            if clone
            else {
                "fallback_source": True,
                "reason": "GENERATION_RETRIES_EXHAUSTED",
                "validation_status": "not_validated",
                "attempts": 4,
                "source_revision_id": str(uuid4()),
                "source_fingerprint": "a" * 64,
                "confirmed_source_hash": "b" * 64,
            }
        )
        self.sql(f"""
            UPDATE generation_configs SET active_variation_modes={literal(modes)}::jsonb,
                canonical_dimensions={literal(dims)}::jsonb WHERE session_id='{self.sid}';
            INSERT INTO generation_job_snapshots(id,session_id,job_token,confirmation_id,
                source_order,confirmed_source_hash,n_versions,public_modes,canonical_dimensions,
                mapping_version,snapshot_payload)
            VALUES ('{snap_id}','{self.sid}','{token}',gen_random_uuid(),'[]','{"b" * 64}',
                2,{literal(modes)}::jsonb,{literal(dims)}::jsonb,'1.0','{{}}');
            UPDATE version_questions SET has_warning={str(not clone).lower()},
                validation_report={literal(json.dumps(report))}::jsonb
            WHERE version_id IN (SELECT id FROM exam_versions WHERE session_id='{self.sid}');
            INSERT INTO generation_target_results(session_id,snapshot_id,job_token,version_index,
                source_question_id,question_no,is_success,attempts,seed,request_fingerprint,
                raw_result,version_question_id,result_kind,clone_fingerprint)
            SELECT '{self.sid}','{snap_id}','{token}',v.version_code::int-100,
                q.source_question_id,q.question_no,true,{0 if clone else 4},100,
                {"NULL" if clone else literal("d" * 64)},'{{}}',q.id,'{self.kind}',
                {literal("c" * 64) if clone else "NULL"}
            FROM version_questions q JOIN exam_versions v ON v.id=q.version_id
            WHERE v.session_id='{self.sid}';
        """)

    def snapshot(self, *, verifier=True):
        return asyncio.run(
            load_approved_export_snapshot(
                SqlReadClient(self),
                self.sid,
                OWNER,
                provenance_db=SqlReadClient(self, role="service_role") if verifier else None,
            )
        )

    def assert_empty_projection(self):
        self.approve()
        snapshot = self.snapshot()
        assert len(snapshot.versions) == 2
        assert all(q.solution_md == "" for v in snapshot.versions for q in v.questions)
        assert [q.question_no for q in snapshot.versions[0].questions] == [1, 2, 3]
        denied = self.sql(auth() + "SELECT * FROM generation_target_results", check=False)
        assert denied.returncode != 0  # authenticated content reader cannot read privileged ledger
        with self.assertRaises(ReviewDomainException):
            self.snapshot(verifier=False)

    def test_fallback_shuffle_approval_and_empty_export(self):
        self.assert_empty_projection()

    def test_clone_shuffle_approval_and_empty_export(self):
        self.assert_empty_projection()

    def preview_approval_export_parity(self):
        preview = asyncio.run(
            FinalizeRepository(
                SqlReadClient(self), provenance_db=SqlReadClient(self, role="service_role")
            ).fetch_preview_snapshot(self.sid)
        )
        self.approve()
        exported = self.snapshot()
        for actual, expected in zip(exported.versions, preview["versions"], strict=True):
            assert actual.code == expected["version_code"]
            for q, projected in zip(actual.questions, expected["questions"], strict=True):
                assert q.model_dump(mode="json") == {
                    key: projected[key] for key in type(q).model_fields
                }
                assert q.correct_key == preview["matrix"][q.question_no - 1]["answers"][actual.code]

    @unittest.skipUnless(
        hasattr(FinalizeRepository, "fetch_preview_snapshot"), "PR49 not integrated"
    )
    def test_fallback_off_off_preview_approval_export_parity(self):
        self.preview_approval_export_parity()

    @unittest.skipUnless(
        hasattr(FinalizeRepository, "fetch_preview_snapshot"), "PR49 not integrated"
    )
    def test_clone_on_on_preview_approval_export_parity(self):
        self.preview_approval_export_parity()

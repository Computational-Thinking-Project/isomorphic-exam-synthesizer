"""RPC020 on real PostgreSQL15. Opt in RUN_POSTGRES_MIGRATION_TESTS=1.

SQL replaces only HTTP transport; each RPC runs in a separate committed connection.
BlobStore is deliberately fake: these tests do NOT attest live Storage ACL/expiry.
"""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from app.services.exporter.bundle_models import BundleArtifact
from app.services.exporter.private_models import ExportFailure
from app.services.exporter.private_repository import SupabaseExportLedger, receipt
from app.services.exporter.private_service import PrivateExportService, user_snapshot_loader
from test_export_snapshot_pg import (
    BOOTSTRAP,
    OTHER,
    OWNER,
    ROOT,
    ExportSnapshotPostgresFixture,
    SqlReadClient,
    auth,
    literal,
)

from app.models.schemas import ReviewDomainException

MIGRATION = ROOT / "backend/migrations/020_private_export_ledger.sql"


def sql_literal(value):
    return (
        "NULL"
        if value is None
        else literal(json.dumps(value) if isinstance(value, dict) else value)
    )


class RpcClient:
    def __init__(self, case):
        self.case = case
        self.lose = set()

    def rpc(self, name, params):
        assert name == "private_export_ledger_command"

        def execute():
            result = self.case.command(params)
            if params["p_action"] in self.lose:
                self.lose.remove(params["p_action"])
                raise TimeoutError("Lost committed response")
            return SimpleNamespace(data=json.loads(result.stdout.strip().splitlines()[-1]))

        return SimpleNamespace(execute=execute)


class BlobStore:
    def __init__(self):
        self.objects = {}
        self.uploads = 0
        self.lose = False
        self.unavailable = False

    def upload(self, path, artifact):
        assert path not in self.objects
        self.objects[path] = artifact.data
        self.uploads += 1
        if self.lose:
            self.lose = False
            raise TimeoutError("Upload committed but response lost")

    def verify(self, artifact):
        if self.unavailable:
            raise TimeoutError("Storage offline")
        if artifact.object_path not in self.objects:
            raise ExportFailure("ERR_EXPORT_OBJECT_NOT_FOUND")
        data = self.objects[artifact.object_path]
        if len(data) != artifact.size_bytes or hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise ExportFailure("ERR_EXPORT_CHECKSUM_MISMATCH")


class PrivateExportPostgresTests(ExportSnapshotPostgresFixture):
    def setUp(self):
        # Upgrade path: existing approved content created under schema + 002..018.
        type(self).db = "private_export_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP + (ROOT / "backend/scripts/schema.sql").read_text(encoding="utf-8"))
        self.sql(
            "GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role; "
            "GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated,service_role;"
        )
        for path in sorted((ROOT / "backend/migrations").glob("*.sql")):
            if path != MIGRATION:
                self.sql(path.read_text(encoding="utf-8"))
        from test_export_snapshot_pg import FIXTURE

        self.expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.sid = self.expected["session_id"]
        self.seed()
        self.shuffle()
        self.approve()
        before = self.load().model_dump(mode="json")
        self.sql(MIGRATION.read_text(encoding="utf-8"))
        self.assertEqual(self.load().model_dump(mode="json"), before)
        self.client = RpcClient(self)
        self.ledger = SupabaseExportLedger(self.client)
        self.store = BlobStore()
        self.builds = 0

        def build(snapshot):
            self.builds += 1
            payload = b"compiled complete ZIP fixture " + str(self.builds).encode()
            return BundleArtifact(
                f"exam_bundle_{self.sid}.zip", payload, hashlib.sha256(payload).hexdigest()
            )

        self.service = PrivateExportService(
            user_snapshot_loader(SqlReadClient(self)), self.ledger, self.store, build=build
        )
        _, self.identity = self.service._snapshot(self.sid, OWNER)

    def command(self, params, *, check=True, role="service_role", actor=OWNER):
        names = (
            "p_session_id",
            "p_actor_id",
            "p_identity",
            "p_action",
            "p_token",
            "p_receipt",
            "p_reason",
        )
        query = (
            "SELECT private_export_ledger_command("
            + ",".join(sql_literal(params.get(n)) for n in names)
            + ");"
        )
        return self.sql(auth(actor, role) + query, check=check)

    def params(self, action, token=None, artifact=None, reason=None, identity=None):
        i = identity or self.identity
        return {
            "p_session_id": str(i.session_id),
            "p_actor_id": str(i.owner_id),
            "p_identity": {
                "revision": i.revision,
                "packaging_key": i.packaging_key,
                "packager_version": i.packager_version,
            },
            "p_action": action,
            "p_token": str(token) if token else None,
            "p_receipt": receipt(artifact) if artifact else None,
            "p_reason": reason,
        }

    def expire(self):
        self.sql(
            "UPDATE private_export_ledger SET lease_until=clock_timestamp()-interval '1 second';"
        )

    def run_export(self):
        return self.service.export(self.sid, OWNER)

    def test_concurrent_claims_have_one_identity_and_build_authority(self):
        barrier = Barrier(2)

        def claim():
            barrier.wait(5)
            return self.ledger.claim(self.identity)

        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(claim) for _ in range(2)]
            results = [f.result(10) for f in futures]
        self.assertEqual(sorted(r.state for r in results), ["claimed", "pending"])
        self.assertEqual(self.value("SELECT count(*) FROM private_export_ledger;"), "1")
        self.assertEqual(self.ledger.claim(self.identity).state, "pending")

    def test_complete_atomic_ready_replay_preserves_snapshot(self):
        before = self.load().revision
        first = self.run_export()
        self.assertEqual(first.state, "ready")
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "exported")
        self.assertEqual(self.load().revision, before)
        self.assertEqual(self.run_export(), first)
        self.assertEqual((self.builds, self.store.uploads), (1, 1))
        self.assertEqual(self.service.status(self.sid, OWNER), first)
        self.assertEqual(self.value("SELECT count(*) FROM private_export_ledger;"), "1")

    def test_upload_response_loss_recovers_old_path_without_recompilation(self):
        self.store.lose = True
        with self.assertRaisesRegex(ExportFailure, "STORAGE_OUTCOME_UNKNOWN"):
            self.run_export()
        old = json.loads(self.value("SELECT expected FROM private_export_ledger;"))
        old_token = self.value("SELECT token FROM private_export_ledger;")
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "approved")
        self.expire()
        ready = self.run_export()
        self.assertEqual(ready.artifact.object_path, old["object_path"])
        self.assertNotEqual(self.value("SELECT token FROM private_export_ledger;"), old_token)
        self.assertEqual((self.builds, self.store.uploads), (1, 1))

    def test_complete_response_loss_reads_back_committed_result(self):
        self.client.lose.add("complete")
        self.assertEqual(self.run_export().state, "ready")
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "exported")

    def test_claim_response_lost_does_not_build_until_explicit_takeover(self):
        self.client.lose.add("claim")
        with self.assertRaisesRegex(ExportFailure, "ERR_EXPORT_UNAVAILABLE"):
            self.run_export()
        self.assertEqual(self.run_export().state, "pending")
        self.assertEqual(self.builds, 0)
        self.expire()
        self.assertEqual(self.run_export().state, "ready")
        self.assertEqual(self.builds, 1)

    def test_restart_response_lost_does_not_blindly_rebuild(self):
        self.client.lose.add("checkpoint")
        with self.assertRaises(ExportFailure):
            self.run_export()
        self.expire()
        self.client.lose.add("restart")
        with self.assertRaisesRegex(ExportFailure, "OUTCOME_UNKNOWN"):
            self.run_export()
        self.assertEqual(self.run_export().state, "pending")
        self.assertEqual(self.builds, 1)
        self.expire()
        self.assertEqual(self.run_export().state, "ready")
        self.assertEqual(self.builds, 2)

    def test_committed_ready_object_loss_does_not_silently_rebuild(self):
        ready = self.run_export()
        self.store.objects.clear()
        self.assertEqual(self.run_export(), ready)
        with self.assertRaisesRegex(ExportFailure, "ERR_EXPORT_STORAGE_UNAVAILABLE"):
            self.service.download(self.sid, OWNER)
        self.assertEqual(self.builds, 1)

    def test_failed_build_replay_and_expired_complete_are_fenced(self):
        claim = self.ledger.claim(self.identity)
        self.ledger.fail(self.identity, claim.token, "ERR_EXPORT_BUILD_FAILED")
        self.ledger.fail(self.identity, claim.token, "ERR_EXPORT_BUILD_FAILED")
        self.assertEqual(self.ledger.read(self.identity).state, "failed")
        self.client.lose.add("checkpoint")
        with self.assertRaises(ExportFailure):
            self.run_export()
        token = self.value("SELECT token FROM private_export_ledger;")
        self.expire()
        p = self.params("complete", token)
        p["p_receipt"] = json.loads(self.value("SELECT expected FROM private_export_ledger;"))
        result = self.command(p, check=False)
        self.assertIn("ERR_EXPORT_STALE_ATTEMPT", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "approved")

    def test_checkpoint_response_loss_missing_object_fences_before_rebuild(self):
        self.client.lose.add("checkpoint")
        with self.assertRaisesRegex(ExportFailure, "OUTCOME_UNKNOWN"):
            self.run_export()
        old = json.loads(self.value("SELECT expected FROM private_export_ledger;"))
        self.assertFalse(self.store.objects)
        self.expire()
        ready = self.run_export()
        self.assertNotEqual(ready.artifact.object_path, old["object_path"])
        self.assertEqual((self.builds, self.store.uploads), (2, 1))

    def test_recovery_network_failure_keeps_receipt_and_does_not_rebuild(self):
        self.store.lose = True
        with self.assertRaises(ExportFailure):
            self.run_export()
        old = self.value("SELECT expected FROM private_export_ledger;")
        self.expire()
        self.store.unavailable = True
        with self.assertRaisesRegex(ExportFailure, "STORAGE_OUTCOME_UNKNOWN"):
            self.run_export()
        self.assertEqual(self.value("SELECT expected FROM private_export_ledger;"), old)
        self.assertEqual((self.builds, self.store.uploads), (1, 1))
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "approved")

    def test_corrupt_object_recovery_rebuilds_new_path_without_deleting_old(self):
        self.store.lose = True
        with self.assertRaises(ExportFailure):
            self.run_export()
        old = next(iter(self.store.objects))
        self.store.objects[old] = b"corrupt"
        self.expire()
        ready = self.run_export()
        self.assertNotEqual(ready.artifact.object_path, old)
        self.assertIn(old, self.store.objects)
        self.assertEqual((self.builds, self.store.uploads), (2, 2))

    def test_stale_mutations_cannot_override_recovery_or_ready(self):
        self.store.lose = True
        with self.assertRaises(ExportFailure):
            self.run_export()
        old_token = self.value("SELECT token FROM private_export_ledger;")
        old_receipt = json.loads(self.value("SELECT expected FROM private_export_ledger;"))
        self.expire()
        recovered = self.ledger.claim(self.identity)
        self.assertEqual(recovered.state, "recovering")
        for action in ("checkpoint", "complete", "fail", "restart"):
            with self.subTest(action=action):
                p = self.params(action, old_token, recovered.artifact, "ERR_EXPORT_BUILD_FAILED")
                result = self.command(p, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ERR_EXPORT_STALE_ATTEMPT", result.stderr)
        self.assertEqual(
            json.loads(self.value("SELECT expected FROM private_export_ledger;")), old_receipt
        )
        self.store.verify(recovered.artifact)
        self.ledger.complete(recovered.artifact, recovered.token)
        self.ledger.complete(recovered.artifact, recovered.token)  # exact replay
        result = self.command(
            self.params("fail", recovered.token, reason="ERR_EXPORT_BUILD_FAILED"), check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.value("SELECT state FROM private_export_ledger;"), "ready")

    def test_mismatched_identity_and_receipts_fail_closed(self):
        claim = self.ledger.claim(self.identity)
        from app.services.exporter.private_models import ReadyExport

        artifact = ReadyExport(
            self.identity,
            f"{self.sid}/{self.identity.packaging_key}/{claim.token}.zip",
            f"exam_bundle_{self.sid}.zip",
            "a" * 64,
            100,
        )
        for change in (
            {"object_path": "foreign/file.zip"},
            {"sha256": "invalid"},
            {"size_bytes": 0},
            {"size_bytes": 104857601},
            {"filename": "other.zip"},
        ):
            with self.subTest(change=change):
                bad = replace(artifact, **change)
                result = self.command(self.params("checkpoint", claim.token, bad), check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    self.value("SELECT expected IS NULL FROM private_export_ledger;"), "t"
                )
        self.ledger.record_built(artifact, claim.token)
        for change in (
            {"sha256": "b" * 64},
            {"size_bytes": 101},
            {"object_path": "foreign/file.zip"},
        ):
            self.assertNotEqual(
                self.command(
                    self.params("complete", claim.token, replace(artifact, **change)), check=False
                ).returncode,
                0,
            )
        wrong = replace(self.identity, revision="sha256:" + "b" * 64)
        self.assertNotEqual(
            self.command(self.params("claim", identity=wrong), check=False).returncode, 0
        )
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "approved")

    def test_completion_rolls_back_ledger_when_lifecycle_write_fails(self):
        self.sql("""CREATE FUNCTION test_reject_export() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.status='exported' THEN RAISE EXCEPTION 'test lifecycle failure'; END IF; RETURN NEW; END $$;
            CREATE TRIGGER test_export_failure BEFORE UPDATE ON exam_sessions FOR EACH ROW EXECUTE FUNCTION test_reject_export();""")
        with self.assertRaisesRegex(ExportFailure, "OUTCOME_UNKNOWN"):
            self.run_export()
        self.assertEqual(self.value("SELECT state FROM private_export_ledger;"), "preparing")
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "approved")
        self.assertEqual(len(self.store.objects), 1)
        self.sql("DROP TRIGGER test_export_failure ON exam_sessions;")
        self.expire()
        self.assertEqual(self.run_export().state, "ready")
        self.assertEqual(self.builds, 1)

    def test_rpc_acl_forged_role_owner_and_ledger_rls(self):
        for role in ("anon", "authenticated"):
            result = self.command(self.params("claim"), check=False, role=role)
            self.assertIn("permission denied", result.stderr)
        self.sql(
            "GRANT EXECUTE ON FUNCTION private_export_ledger_command(uuid,uuid,jsonb,text,uuid,jsonb,text) TO authenticated;"
        )
        p = self.params("claim")
        query = (
            "SELECT private_export_ledger_command("
            + ",".join(
                sql_literal(p.get(k))
                for k in (
                    "p_session_id",
                    "p_actor_id",
                    "p_identity",
                    "p_action",
                    "p_token",
                    "p_receipt",
                    "p_reason",
                )
            )
            + ");"
        )
        result = self.sql(
            auth() + "SET request.jwt.claim.role='service_role';" + query, check=False
        )
        self.assertIn("ERR_UNAUTHORIZED", result.stderr)
        self.assertNotEqual(
            self.command(
                self.params("claim", identity=replace(self.identity, owner_id=uuid4())), check=False
            ).returncode,
            0,
        )
        self.assertIn(
            "permission denied",
            self.sql(auth() + "SELECT * FROM private_export_ledger;", check=False).stderr,
        )
        with self.assertRaises(ReviewDomainException):
            user_snapshot_loader(SqlReadClient(self, OTHER))(self.sid, OTHER)

    def test_storage_policy_blocks_export_mutations_even_with_permissive_policy(self):
        self.sql("""ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
            GRANT USAGE ON SCHEMA storage TO authenticated,service_role;
            GRANT ALL ON storage.objects TO authenticated,service_role;
            CREATE POLICY extra_export_access ON storage.objects FOR ALL TO authenticated
                USING (bucket_id='exam-export-bundles') WITH CHECK (bucket_id='exam-export-bundles');""")
        export = (
            f"INSERT INTO storage.objects VALUES('exam-export-bundles','{self.sid}/fixture.zip');"
        )
        self.assertNotEqual(self.sql(auth() + export, check=False).returncode, 0)
        self.sql(auth(role="service_role") + export)
        self.sql(
            auth()
            + "UPDATE storage.objects SET name='bad' WHERE bucket_id='exam-export-bundles'; DELETE FROM storage.objects WHERE bucket_id='exam-export-bundles';"
        )
        self.assertEqual(
            self.value(
                "SELECT count(*) FROM storage.objects WHERE bucket_id='exam-export-bundles';"
            ),
            "1",
        )
        for bucket in ("exam-raw-files", "exam-sources"):
            self.sql(auth() + f"INSERT INTO storage.objects VALUES('{bucket}','{self.sid}/raw');")
        self.assertEqual(self.value("SELECT count(*) FROM storage.objects;"), "3")

    def test_fresh_chain_and_locked_content_after_export(self):
        # Fresh initialization uses the same production chain, before any data.
        fresh = "fresh_export_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", fresh)
        self.sql(
            BOOTSTRAP + (ROOT / "backend/scripts/schema.sql").read_text(encoding="utf-8"), db=fresh
        )
        for path in sorted((ROOT / "backend/migrations").glob("*.sql")):
            self.sql(path.read_text(encoding="utf-8"), db=fresh)
        self.assertEqual(
            self.sql("SELECT count(*) FROM private_export_ledger;", db=fresh).stdout.strip(), "0"
        )
        self.run_export()
        result = self.sql(
            auth() + "UPDATE version_questions SET content='unexpected mutation';", check=False
        )
        self.assertNotEqual(result.returncode, 0)  # Direct DML is already revoked by 009.
        self.assertIn("permission denied", result.stderr)
        qid = self.expected["versions"][0]["questions"][0]["id"]
        result = self.sql(
            auth() + f"SELECT review_accept_question('{self.sid}','{qid}','{uuid4()}');",
            check=False,
        )
        self.assertIn("REVIEW_LOCKED", result.stderr)

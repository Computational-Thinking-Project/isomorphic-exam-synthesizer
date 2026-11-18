"""Task-08 orchestration proof with fake durable ports, NOT DB/Storage ACL proof."""

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from threading import Event, Lock
from unittest.mock import Mock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from app.services.exporter.manifest_bundle import build_private_bundle, with_manifest
from app.services.exporter.private_models import ExportClaim, ExportFailure
from app.services.exporter.private_service import PrivateExportService
from app.services.exporter.private_storage import SupabasePrivateExportStore
from app.services.exporter.snapshot_builder import build_approved_snapshot
from snapshot_fixtures import OWNER_ID, SESSION_ID, golden_rows, to_rows

from app.models.schemas import ReviewDomainException
from app.services.exporter.exceptions import TypstCompilationError


class Ledger:
    """Test double only: asserts required calls, not a proposed production ledger."""

    def __init__(self):
        self.lock = Lock()
        self.current = None
        self.ready = None
        self.failures = []
        self.completions = 0
        self.lose_response = False
        self.reject_complete = False
        self.built = None
        self.reject_checkpoint = False

    def read(self, identity):
        if self.ready:
            return ExportClaim("ready", artifact=self.ready)
        if self.current:
            return ExportClaim("pending")
        if self.failures:
            return ExportClaim("failed", error_code=self.failures[-1])
        return ExportClaim("idle")

    def claim(self, identity):
        with self.lock:
            if self.ready:
                return self.read(identity)
            if self.current:
                return ExportClaim("pending")
            self.current = uuid4()
            return ExportClaim("claimed", self.current)

    def complete(self, artifact, token):
        assert token == self.current
        assert artifact == self.built
        assert self.ready is None
        self.completions += 1
        if self.reject_complete:
            raise RuntimeError("secret transport message")
        self.ready = artifact
        if self.lose_response:
            raise TimeoutError("secret transport message")
        return artifact

    def record_built(self, artifact, token):
        assert token == self.current
        if self.reject_checkpoint:
            raise TimeoutError("secret transport message")
        self.built = artifact

    def fail(self, identity, token, error_code):
        assert token == self.current and self.ready is None
        self.failures.append(error_code)
        self.current = None


class Store:
    def __init__(self):
        self.objects = {}
        self.uploads = 0
        self.signs = 0
        self.upload_failure = False
        self.corrupt = False

    def upload(self, path, artifact):
        self.uploads += 1
        assert path not in self.objects
        self.objects[path] = artifact.data
        if self.upload_failure:
            raise TimeoutError("secret transport message")

    def verify(self, artifact):
        data = self.objects[artifact.object_path]
        if self.corrupt or hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise ValueError("corrupt object")

    def sign(self, artifact):
        self.signs += 1
        return "https://storage.example/short-lived-bearer"


@pytest.fixture
def workflow(snapshot):
    ledger, store = Ledger(), Store()
    # Use a real deterministic source ZIP; PDF bytes stubbed only in this fixture.
    from app.services.exporter.bundle_builder import build_bundle, required_pdf_names
    from app.services.exporter.snapshot_revision import snapshot_revision

    revision = snapshot_revision(
        {"id": snapshot.session_id, "title": snapshot.title},
        [v.model_dump(mode="json") for v in snapshot.versions],
    )
    snapshot = snapshot.model_copy(update={"revision": revision})
    bundle = with_manifest(
        snapshot,
        build_bundle(
            snapshot, {name: b"%PDF-1.4\n%%EOF\n" for name in required_pdf_names(snapshot)}
        ),
    )
    loader = Mock(return_value=snapshot)
    builder = Mock(return_value=bundle)
    service = PrivateExportService(
        loader,
        ledger,
        store,
        build=builder,
        now=lambda: datetime(2026, 11, 12, tzinfo=timezone.utc),
    )
    return service, ledger, store, loader, builder


def args(workflow):
    return str(workflow[3].return_value.session_id), OWNER_ID


def test_export_upload_verify_commit_then_retry_reuses_exact_artifact(workflow):
    service, ledger, store, _, builder = workflow
    first = service.export(*args(workflow))
    assert first.state == "ready"
    assert store.objects[first.artifact.object_path]
    assert first.artifact.object_path.startswith(args(workflow)[0] + "/")
    assert first == service.export(*args(workflow))
    assert store.uploads == ledger.completions == builder.call_count == 1
    assert store.signs == 0  # Export/status never leak a signed URL.
    assert service.status(*args(workflow)) == first


def test_compile_failure_does_not_upload_or_publish(workflow):
    service, ledger, store, _, builder = workflow
    builder.side_effect = TypstCompilationError("secret compiler stderr")
    with pytest.raises(ExportFailure, match="ERR_EXPORT_BUILD_FAILED") as err:
        service.export(*args(workflow))
    assert err.value.http_status == 422
    assert not store.objects and not ledger.completions
    assert ledger.failures == ["ERR_EXPORT_BUILD_FAILED"]
    assert service.status(*args(workflow)).state == "failed"


def test_explicit_retry_after_build_failure_uses_new_claim(workflow):
    service, ledger, store, _, builder = workflow
    builder.side_effect = TypstCompilationError("failed")
    with pytest.raises(ExportFailure):
        service.export(*args(workflow))
    builder.side_effect = None
    assert service.export(*args(workflow)).state == "ready"
    assert store.uploads == ledger.completions == 1


@pytest.mark.parametrize("reason", ["lost_upload_response", "checksum_mismatch"])
def test_upload_failure_never_commits_and_keeps_uncertain_attempt_for_recovery(workflow, reason):
    service, ledger, store, _, builder = workflow
    store.upload_failure = reason == "lost_upload_response"
    store.corrupt = reason == "checksum_mismatch"
    with pytest.raises(ExportFailure, match="ERR_EXPORT_STORAGE_OUTCOME_UNKNOWN"):
        service.export(*args(workflow))
    assert ledger.completions == 0 and not ledger.failures
    assert len(store.objects) == 1  # Never delete a possibly committed upload.
    assert service.export(*args(workflow)).state == "pending"
    assert builder.call_count == store.uploads == 1


def test_complete_committed_but_response_lost_reads_back_ready(workflow):
    service, ledger, store, _, _ = workflow
    ledger.lose_response = True
    assert service.export(*args(workflow)).state == "ready"
    assert len(store.objects) == 1 and not ledger.failures


def test_complete_unknown_preserves_object_and_claim(workflow):
    service, ledger, store, _, _ = workflow
    ledger.reject_complete = True
    with pytest.raises(ExportFailure, match="ERR_EXPORT_OUTCOME_UNKNOWN"):
        service.export(*args(workflow))
    assert ledger.ready is None and ledger.current and not ledger.failures
    assert len(store.objects) == 1


def test_lost_built_checkpoint_response_does_not_start_upload(workflow):
    service, ledger, store, _, _ = workflow
    ledger.reject_checkpoint = True
    with pytest.raises(ExportFailure, match="ERR_EXPORT_OUTCOME_UNKNOWN"):
        service.export(*args(workflow))
    assert not store.objects and not ledger.completions and not ledger.failures


def test_parallel_second_request_waits_without_duplicate_build(workflow):
    service, ledger, store, _, builder = workflow
    started, release = Event(), Event()
    bundle = builder.return_value

    def build(snapshot):
        started.set()
        assert release.wait(5)
        return bundle

    builder.side_effect = build
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(service.export, *args(workflow))
        try:
            assert started.wait(5)
            assert service.export(*args(workflow)).state == "pending"
        finally:
            release.set()
        assert first.result(5).state == "ready"
    assert store.uploads == ledger.completions == builder.call_count == 1


@pytest.mark.parametrize("action", ["export", "status", "download"])
def test_owner_denied_before_ledger_or_storage(action, workflow):
    service, _, _, loader, builder = workflow
    service.ledger = Mock()
    service.store = Mock()
    loader.side_effect = ReviewDomainException(403, "ERR_UNAUTHORIZED", "Forbidden")
    with pytest.raises(ReviewDomainException) as err:
        getattr(service, action)(*args(workflow))
    assert err.value.status_code == 403
    assert not service.ledger.mock_calls and not service.store.mock_calls
    builder.assert_not_called()


def test_reissue_authorizes_again_and_returns_3600s_grant(workflow):
    service, _, store, loader, _ = workflow
    service.export(*args(workflow))
    one = service.download(*args(workflow))
    two = service.download(*args(workflow))
    assert one.expires_in == two.expires_in == 3600
    assert one.expires_at == "2026-11-12T01:00:00+00:00"
    assert store.signs == 2 and loader.call_count == 3


def test_no_download_before_ready(workflow):
    service, _, store, _, _ = workflow
    assert service.status(*args(workflow)).state == "idle"
    with pytest.raises(ExportFailure, match="ERR_EXPORT_NOT_READY"):
        service.download(*args(workflow))
    assert store.signs == 0


def test_sdk_adapter_immutable_upload_checksum_and_exact_ttl(workflow):
    service, _, store, _, builder = workflow
    artifact = service.export(*args(workflow)).artifact
    sdk = Mock()
    bucket = sdk.storage.from_.return_value
    bucket.download.return_value = store.objects[artifact.object_path]
    bucket.create_signed_url.return_value = {"signedURL": "https://example.test/token"}
    adapter = SupabasePrivateExportStore(sdk, "exam-export-bundles")
    adapter.upload(artifact.object_path, builder.return_value)
    assert bucket.upload.call_args.kwargs["file_options"]["upsert"] == "false"
    adapter.verify(artifact)
    assert adapter.sign(artifact) == "https://example.test/token"
    bucket.create_signed_url.assert_called_once_with(
        artifact.object_path, 3600, {"download": artifact.filename}
    )
    bucket.download.return_value = b"corrupt"
    with pytest.raises(ExportFailure, match="ERR_EXPORT_CHECKSUM_MISMATCH"):
        adapter.verify(artifact)


def test_manifest_each_file_checksum_and_determinism(workflow):
    _, _, _, loader, builder = workflow
    snapshot, bundle = loader.return_value, builder.return_value
    with ZipFile(BytesIO(bundle.data)) as archive:
        root = f"exam_bundle_{snapshot.session_id}/"
        manifest = json.loads(archive.read(root + "manifest.json"))
        assert manifest["revision"] == snapshot.revision
        assert len(manifest["files"]) + 1 == len(archive.namelist())
        for entry in manifest["files"]:
            data = archive.read(root + entry["path"])
            assert entry["size_bytes"] == len(data)
            assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert archive.testzip() is None
    assert hashlib.sha256(bundle.data).hexdigest() == bundle.sha256


@pytest.mark.skipif(not shutil.which("typst"), reason="Typst CLI required")
def test_real_07_snapshot_typst_manifest_bundle():
    snapshot = build_approved_snapshot(to_rows(golden_rows()))
    first = build_private_bundle(snapshot)
    with ZipFile(BytesIO(first.data)) as archive:
        root = f"exam_bundle_{SESSION_ID}/"
        manifest = json.loads(archive.read(root + "manifest.json"))
        pdfs = [e for e in manifest["files"] if e["path"].endswith(".pdf")]
        assert len(pdfs) == 5
        for entry in pdfs:
            assert archive.read(root + entry["path"]).startswith(b"%PDF-")
        for version in snapshot.versions:
            md = archive.read(root + f"markdown/exam_{version.code}.md").decode()
            for q in version.questions:
                assert q.content in md and q.solution_md in md
                assert f"Đáp án {q.correct_key}" in md
        for entry in manifest["files"]:
            assert hashlib.sha256(archive.read(root + entry["path"])).hexdigest() == entry["sha256"]


def test_invalid_metadata_cannot_sign_foreign_path(workflow):
    service, ledger, store, _, _ = workflow
    from dataclasses import replace

    artifact = service.export(*args(workflow)).artifact
    ledger.ready = replace(artifact, object_path=f"{uuid4()}/foreign.zip")
    with pytest.raises(ExportFailure, match="ERR_EXPORT_METADATA_INVALID"):
        service.download(*args(workflow))
    assert store.signs == 0

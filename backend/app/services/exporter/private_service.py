"""Synchronous export workflow. Run the WHOLE call in a worker thread from async HTTP.

No public routes/RPC are enabled while Q09/Q10 are unaccepted. Durable ports are
mandatory; the tests' in-memory ledger is never a production fallback.
"""

import hashlib
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import ValidationError
from supabase import Client

from app.models.schemas import ReviewDomainException

from .bundle_models import ApprovedExportSnapshot, BundleArtifact, BundleBuildError
from .exceptions import TypstCompilationError, TypstNotFoundError, TypstTimeoutError
from .manifest_bundle import build_private_bundle
from .private_models import (
    PACKAGER_VERSION,
    SIGNED_URL_TTL,
    DownloadGrant,
    ExportClaim,
    ExportFailure,
    ExportIdentity,
    ExportLedger,
    ExportResult,
    PrivateExportStore,
    ReadyExport,
    SnapshotLoader,
)
from .snapshot_builder import build_approved_snapshot
from .snapshot_reader import ExportSnapshotReader


def user_snapshot_loader(db: Client) -> SnapshotLoader:
    """Bind a verified user/RLS client, never a service-role client."""

    def load(session_id: str, owner_id: str) -> ApprovedExportSnapshot:
        return build_approved_snapshot(ExportSnapshotReader(db).load_rows(session_id, owner_id))

    return load


def object_prefix(identity: ExportIdentity) -> str:
    # Session-first path preserves schema.sql's existing owner RLS convention.
    return f"{identity.session_id}/{identity.packaging_key}/"


class PrivateExportService:
    def __init__(
        self,
        loader: SnapshotLoader,
        ledger: ExportLedger,
        store: PrivateExportStore,
        *,
        build: Callable[[ApprovedExportSnapshot], BundleArtifact] = build_private_bundle,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.loader, self.ledger, self.store = loader, ledger, store
        self.build, self.now = build, now

    def _snapshot(
        self, session_id: str, owner_id: str
    ) -> tuple[ApprovedExportSnapshot, ExportIdentity]:
        try:
            requested_id = UUID(session_id)
        except (ValueError, TypeError, AttributeError):
            raise ReviewDomainException(
                400, "ERR_INVALID_SESSION_ID", "Mã phiên không hợp lệ"
            ) from None
        try:
            snapshot = self.loader(session_id, owner_id)
            owner = UUID(owner_id)
        except ReviewDomainException:
            raise
        except Exception:
            raise ExportFailure("ERR_EXPORT_UNAVAILABLE") from None
        try:
            snapshot = ApprovedExportSnapshot.model_validate(snapshot.model_dump())
        except ValidationError:
            raise ExportFailure("ERR_EXPORT_SNAPSHOT_INVALID", 409) from None
        if snapshot.session_id != requested_id or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", snapshot.revision
        ):
            raise ExportFailure("ERR_EXPORT_SNAPSHOT_INVALID", 409)
        key = hashlib.sha256(f"{PACKAGER_VERSION}\n{snapshot.revision}".encode()).hexdigest()
        return snapshot, ExportIdentity(snapshot.session_id, owner, snapshot.revision, key)

    @staticmethod
    def _ready(identity: ExportIdentity, artifact: ReadyExport | None) -> ReadyExport:
        if (
            artifact is None
            or artifact.identity != identity
            or not re.fullmatch(
                re.escape(object_prefix(identity)) + r"[0-9a-f-]{36}\.zip", artifact.object_path
            )
            or artifact.filename != f"exam_bundle_{identity.session_id}.zip"
            or not re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)
            or not 0 < artifact.size_bytes <= 100 * 1024 * 1024
        ):
            raise ExportFailure("ERR_EXPORT_METADATA_INVALID")
        return artifact

    def _result(self, identity: ExportIdentity, claim: ExportClaim) -> ExportResult:
        if claim.state == "ready":
            return ExportResult("ready", self._ready(identity, claim.artifact))
        if claim.state in ("claimed", "pending"):
            return ExportResult("pending")
        if claim.state == "idle":
            return ExportResult("idle")
        if claim.state == "failed" and claim.error_code in {
            "ERR_EXPORT_BUILD_FAILED",
            "ERR_EXPORT_COMPILER_UNAVAILABLE",
        }:
            return ExportResult("failed", error_code=claim.error_code)
        raise ExportFailure("ERR_EXPORT_METADATA_INVALID")

    def status(self, session_id: str, owner_id: str) -> ExportResult:
        _, identity = self._snapshot(session_id, owner_id)
        try:
            return self._result(identity, self.ledger.read(identity))
        except ExportFailure:
            raise
        except Exception:
            raise ExportFailure("ERR_EXPORT_UNAVAILABLE") from None

    def _fail(self, identity: ExportIdentity, token: UUID, code: str) -> None:
        try:
            self.ledger.fail(identity, token, code)
        except Exception:
            # Persisted status is unknown: no false failure/success in response.
            raise ExportFailure("ERR_EXPORT_OUTCOME_UNKNOWN") from None

    def export(self, session_id: str, owner_id: str) -> ExportResult:
        snapshot, identity = self._snapshot(session_id, owner_id)
        try:
            claim = self.ledger.claim(identity)
        except Exception:
            raise ExportFailure("ERR_EXPORT_UNAVAILABLE") from None
        if claim.state in ("ready", "pending"):
            return self._result(identity, claim)
        if claim.state != "claimed" or claim.token is None:
            raise ExportFailure("ERR_EXPORT_METADATA_INVALID")
        token = claim.token
        try:
            bundle = self.build(snapshot)
        except (BundleBuildError, TypstCompilationError, ValidationError):
            self._fail(identity, token, "ERR_EXPORT_BUILD_FAILED")
            raise ExportFailure("ERR_EXPORT_BUILD_FAILED", 422) from None
        except (TypstNotFoundError, TypstTimeoutError):
            self._fail(identity, token, "ERR_EXPORT_COMPILER_UNAVAILABLE")
            raise ExportFailure("ERR_EXPORT_COMPILER_UNAVAILABLE") from None
        except Exception:
            self._fail(identity, token, "ERR_EXPORT_BUILD_FAILED")
            raise ExportFailure("ERR_EXPORT_BUILD_FAILED") from None
        artifact = ReadyExport(
            identity,
            f"{object_prefix(identity)}{token}.zip",
            bundle.filename,
            bundle.sha256,
            bundle.size_bytes,
        )
        self._ready(identity, artifact)
        try:
            # A process crash after upload must leave the expected hash/path in
            # durable storage, not only in this worker's memory.
            self.ledger.record_built(artifact, token)
        except Exception:
            raise ExportFailure("ERR_EXPORT_OUTCOME_UNKNOWN") from None
        try:
            self.store.upload(artifact.object_path, bundle)
            self.store.verify(artifact)
        except Exception:
            # Upload may have committed despite a lost response. Do not delete it
            # or release its lease: recovery must inspect this attempt's object.
            raise ExportFailure("ERR_EXPORT_STORAGE_OUTCOME_UNKNOWN") from None
        try:
            committed = self.ledger.complete(artifact, token)
            if self._ready(identity, committed) != artifact:
                raise ExportFailure("ERR_EXPORT_METADATA_INVALID")
            return ExportResult("ready", committed)
        except Exception:
            # Complete may have committed. Read back, never mark failed/delete.
            try:
                result = self._result(identity, self.ledger.read(identity))
                if result.state == "ready" and result.artifact == artifact:
                    return result
            except Exception:
                pass
            raise ExportFailure("ERR_EXPORT_OUTCOME_UNKNOWN") from None

    def download(self, session_id: str, owner_id: str) -> DownloadGrant:
        result = self.status(session_id, owner_id)  # authorizes on EVERY issuance
        if result.state != "ready" or result.artifact is None:
            raise ExportFailure("ERR_EXPORT_NOT_READY", 409)
        try:
            self.store.verify(result.artifact)
            # Timestamp before signing is conservative wrt server-side TTL.
            expires = self.now() + timedelta(seconds=SIGNED_URL_TTL)
            url = self.store.sign(result.artifact)
        except Exception:
            raise ExportFailure("ERR_EXPORT_STORAGE_UNAVAILABLE") from None
        return DownloadGrant(url, expires.isoformat(), result.artifact.filename)

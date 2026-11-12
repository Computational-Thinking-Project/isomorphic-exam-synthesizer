"""Task-08 integration ports; provisional Q09 choices, not deployed RPC contracts."""

from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID

from .bundle_models import ApprovedExportSnapshot, BundleArtifact

PACKAGER_VERSION = "w4-export-v1"
SIGNED_URL_TTL = 3600


class ExportFailure(Exception):
    """Only these fixed codes may cross the eventual HTTP boundary."""

    def __init__(self, code: str, http_status: int = 503):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class ExportIdentity:
    session_id: UUID
    owner_id: UUID
    revision: str
    packaging_key: str


@dataclass(frozen=True)
class ReadyExport:
    identity: ExportIdentity
    object_path: str
    filename: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ExportClaim:
    state: Literal["idle", "claimed", "pending", "ready", "failed"]
    token: UUID | None = None
    artifact: ReadyExport | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class ExportResult:
    state: Literal["idle", "pending", "ready", "failed"]
    artifact: ReadyExport | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class DownloadGrant:
    url: str = field(repr=False)
    expires_at: str
    filename: str
    expires_in: int = SIGNED_URL_TTL


class SnapshotLoader(Protocol):
    def __call__(self, session_id: str, owner_id: str) -> ApprovedExportSnapshot:
        """Authorize via user RLS, then return persisted, locked snapshot 07."""
        ...


class ExportLedger(Protocol):
    """Must be durable and transactional; no production in-memory substitute.

    Q09 proposal: claim under session lock; one current lease/token per identity;
    complete checks fencing token + approved snapshot, publishes metadata and
    approved->exported together. read never mutates. fail only matches its token,
    never changes session lifecycle or overwrites a ready artifact. A stale worker
    cannot publish or fail another worker. RPC/storage owners must accept this
    contract before a concrete adapter or migration is enabled.
    """

    def read(self, identity: ExportIdentity) -> ExportClaim: ...

    def claim(self, identity: ExportIdentity) -> ExportClaim: ...

    def record_built(self, artifact: ReadyExport, token: UUID) -> None:
        """Fence and persist expected path/hash/size BEFORE upload for recovery."""
        ...

    def complete(self, artifact: ReadyExport, token: UUID) -> ReadyExport: ...

    def fail(self, identity: ExportIdentity, token: UUID, error_code: str) -> None: ...


class PrivateExportStore(Protocol):
    def upload(self, path: str, artifact: BundleArtifact) -> None:
        """Create immutable private object. Never overwrite another attempt."""
        ...

    def verify(self, artifact: ReadyExport) -> None:
        """Read back existence, length and content SHA256; raise on mismatch."""
        ...

    def sign(self, artifact: ReadyExport) -> str:
        """Issue a 3600-second bearer URL; caller must have authorized owner."""
        ...

"""Strict adapter for service-only RPC020. User auth/RLS snapshot is required first."""

from typing import Any, Literal
from uuid import UUID

from supabase import Client

from .private_models import ExportClaim, ExportFailure, ExportIdentity, ReadyExport


def receipt(artifact: ReadyExport) -> dict[str, Any]:
    return {
        "object_path": artifact.object_path,
        "filename": artifact.filename,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }


class SupabaseExportLedger:
    def __init__(self, writer_db: Client):
        self.db = writer_db

    def _call(
        self,
        identity: ExportIdentity,
        action: str,
        token: UUID | None = None,
        artifact: ReadyExport | None = None,
        reason: str | None = None,
    ) -> ExportClaim:
        response = self.db.rpc(
            "private_export_ledger_command",
            {
                "p_session_id": str(identity.session_id),
                "p_actor_id": str(identity.owner_id),
                "p_identity": {
                    "revision": identity.revision,
                    "packaging_key": identity.packaging_key,
                    "packager_version": identity.packager_version,
                },
                "p_action": action,
                "p_token": str(token) if token else None,
                "p_receipt": receipt(artifact) if artifact else None,
                "p_reason": reason,
            },
        ).execute()
        data = getattr(response, "data", None)
        try:
            if not isinstance(data, dict):
                raise ValueError("Invalid receipt")
            state = data.get("state")
            if state not in {"idle", "claimed", "recovering", "pending", "ready", "failed"}:
                raise ValueError("Invalid state")
            token_value = UUID(data["token"]) if data.get("token") else None
            result = None
            if state in {"ready", "recovering"}:
                raw = data["receipt"]
                if (
                    not isinstance(raw, dict)
                    or set(raw) != {"object_path", "filename", "sha256", "size_bytes"}
                    or type(raw["size_bytes"]) is not int
                    or not all(
                        isinstance(raw[k], str) for k in ("object_path", "filename", "sha256")
                    )
                ):
                    raise ValueError("Invalid object receipt")
                result = ReadyExport(identity, **raw)
            if state in {"claimed", "recovering"} and token_value is None:
                raise ValueError("Missing token")
            if state == "failed" and data.get("error_code") not in {
                "ERR_EXPORT_BUILD_FAILED",
                "ERR_EXPORT_COMPILER_UNAVAILABLE",
            }:
                raise ValueError("Invalid error code")
            return ExportClaim(state, token_value, result, data.get("error_code"))
        except (ValueError, TypeError, KeyError):
            raise ExportFailure("ERR_EXPORT_METADATA_INVALID") from None

    def read(self, identity: ExportIdentity) -> ExportClaim:
        return self._call(identity, "read")

    def claim(self, identity: ExportIdentity) -> ExportClaim:
        return self._call(identity, "claim")

    def record_built(self, artifact: ReadyExport, token: UUID) -> None:
        result = self._call(artifact.identity, "checkpoint", token, artifact)
        if result.state not in {"pending", "ready"}:
            raise ExportFailure("ERR_EXPORT_METADATA_INVALID")

    def complete(self, artifact: ReadyExport, token: UUID) -> ReadyExport:
        result = self._call(artifact.identity, "complete", token, artifact)
        if result.state != "ready" or result.artifact != artifact:
            raise ExportFailure("ERR_EXPORT_METADATA_INVALID")
        return artifact

    def fail(self, identity: ExportIdentity, token: UUID, error_code: str) -> None:
        result = self._call(identity, "fail", token, reason=error_code)
        if result.state != "failed" or result.error_code != error_code:
            raise ExportFailure("ERR_EXPORT_METADATA_INVALID")

    def restart(
        self, artifact: ReadyExport, token: UUID, reason: Literal["missing", "checksum_mismatch"]
    ) -> ExportClaim:
        result = self._call(artifact.identity, "restart", token, artifact, reason)
        if result.state != "claimed" or result.token == token:
            raise ExportFailure("ERR_EXPORT_METADATA_INVALID")
        return result

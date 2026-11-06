"""Authenticated TASK-207a snapshot preflight and atomic configuration RPC adapter."""

from copy import deepcopy
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

import httpx
from postgrest.exceptions import APIError
from supabase import Client

from app.models.generation_config import GenerationConfigRequest, GenerationConfigResponse
from app.services.generation.config_service import (
    BlueprintConfigContext,
    CanonicalBlueprintConfigContext,
    GenerationConfigContext,
    GenerationConfigError,
    SourceQuestionConfigContext,
)
from app.services.generation.mode_mapper import resolve_modes_to_canonical_dimensions


class GenerationConfigStore(Protocol):
    def load_context(self, session_id: UUID) -> GenerationConfigContext | None: ...

    def save_config(
        self,
        session_id: UUID,
        config: GenerationConfigRequest,
        expected_snapshot: dict[str, object] | None,
    ) -> GenerationConfigResponse: ...


def _storage_failure() -> GenerationConfigError:
    return GenerationConfigError(
        500, "ERR_CONFIG_STORAGE_FAILURE", "Generation configuration could not be processed."
    )


def _rpc_error(exc: APIError, *, save: bool = False) -> GenerationConfigError:
    """Only genuine PostgREST SQLSTATEs and stable business prefixes are public."""
    code = str(getattr(exc, "code", "") or "").upper()
    message = str(getattr(exc, "message", "") or "")
    if code == "P0002":
        return GenerationConfigError(404, "ERR_SESSION_NOT_FOUND", "Session not found.")
    if code == "42501":
        return GenerationConfigError(403, "ERR_FORBIDDEN", "Access denied.")
    if code == "22023" and message.startswith("ERR_SOURCE_NOT_READY"):
        return GenerationConfigError(422, "ERR_SOURCE_NOT_READY", "The source is not ready.")
    if code == "22023" and message.startswith("ERR_CONFIG_CONFLICT"):
        return GenerationConfigError(400, "ERR_CONFIG_CONFLICT", "Generation configuration conflicts with the source.")
    if code == "55006" and message.startswith("ERR_CONFIG_CONFLICT"):
        return GenerationConfigError(409, "ERR_CONFIG_CONFLICT", "The session or source changed; reload before saving.")
    if save and code in {"502", "503", "504"}:
        return GenerationConfigError(
            504, "ERR_CONFIG_OUTCOME_UNCERTAIN",
            "Save outcome is uncertain; reload the session before trying again.",
        )
    return _storage_failure()


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Expected a database row array.")
    return cast(list[dict[str, object]], value)


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise ValueError("Expected a database UUID.")


def _confirmed_at(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value)
    else:
        raise ValueError("Expected a database timestamp.")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Expected a timezone-aware database timestamp.")
    return timestamp


def _canonical_context(
    session_id: UUID, status: str, approved: bool, snapshot: dict[str, object]
) -> GenerationConfigContext:
    if snapshot.get("session_id") != str(session_id) or snapshot.get("reason") is not None:
        raise ValueError("Canonical snapshot identity or readiness is malformed.")
    confirmation_id = _uuid(snapshot["confirmation_id"])
    manifest = snapshot["manifest"]
    confirmed = snapshot["confirmed_sources"]
    source_order = snapshot["source_order"]
    source_hash = snapshot["confirmed_source_hash"]
    if (
        not isinstance(manifest, dict)
        or _uuid(manifest["confirmation_id"]) != confirmation_id
        or not isinstance(confirmed, list)
        or not 1 <= len(confirmed) <= 20
        or not isinstance(source_order, list)
        or not isinstance(source_hash, str)
        or len(source_hash) != 64
    ):
        raise ValueError("Canonical snapshot manifest is malformed.")
    manifest_sources = manifest["sources"]
    if not isinstance(manifest_sources, list) or len(manifest_sources) != len(confirmed):
        raise ValueError("Canonical manifest source count does not match.")

    sources: list[SourceQuestionConfigContext] = []
    blueprints: list[CanonicalBlueprintConfigContext] = []
    ordered_ids: list[str] = []
    question_numbers: set[int] = set()
    seen_ids: set[UUID] = set()
    previous_question_no = 0
    for item, entry in zip(confirmed, manifest_sources):
        if not isinstance(item, dict) or not isinstance(entry, dict):
            raise ValueError("Canonical source is malformed.")
        source_id = _uuid(item["source_question_id"])
        question_no = item["question_no"]
        if (
            isinstance(question_no, bool)
            or not isinstance(question_no, int)
            or question_no < 1
            or question_no in question_numbers
            or question_no <= previous_question_no
            or source_id in seen_ids
        ):
            raise ValueError("Canonical source order is malformed.")
        seen_ids.add(source_id)
        question_numbers.add(question_no)
        previous_question_no = question_no
        for key in ("source_question_id", "question_no", "source_revision_id", "blueprint_revision_id"):
            if item[key] != entry[key]:
                raise ValueError("Canonical manifest differs from source revisions.")
        _uuid(item["source_revision_id"])
        _uuid(item["blueprint_revision_id"])
        if not isinstance(item["confirmed_input"], dict) or not isinstance(item["canonical_blueprint"], dict):
            raise ValueError("Canonical source content is missing.")
        if any(
            not isinstance(item[key], str) or len(item[key]) != 64
            for key in ("source_fingerprint", "blueprint_fingerprint")
        ):
            raise ValueError("Canonical fingerprints are malformed.")
        sources.append(SourceQuestionConfigContext(id=source_id, session_id=session_id))
        blueprints.append(
            CanonicalBlueprintConfigContext(
                source_question_id=source_id,
                canonical_blueprint=deepcopy(item["canonical_blueprint"]),
            )
        )
        ordered_ids.append(str(source_id))
    if source_order != ordered_ids:
        raise ValueError("Canonical source order differs from snapshot.")
    return GenerationConfigContext(
        session_id=session_id,
        status=status,
        source_questions=tuple(sources),
        blueprints=(),
        approved=approved,
        snapshot_ready=True,
        snapshot_reason=None,
        canonical_blueprints=tuple(blueprints),
        expected_snapshot=deepcopy(manifest),
    )


class GenerationConfigRepository:
    """Use the caller's authenticated client; the save RPC owns the transaction."""

    def __init__(self, db: Client) -> None:
        self._db = db

    def load_context(self, session_id: UUID) -> GenerationConfigContext | None:
        """Read canonical evidence first; legacy reads require NO_CONFIRMATION."""
        try:
            session_rows = _rows(
                self._db.table("exam_sessions")
                .select("id,status,approved_at")
                .eq("id", str(session_id))
                .limit(2)
                .execute()
                .data
            )
            if not session_rows:
                return None
            if len(session_rows) != 1 or _uuid(session_rows[0]["id"]) != session_id:
                raise ValueError("Unexpected session identity or row count.")
            status = session_rows[0]["status"]
            if not isinstance(status, str) or not status.strip():
                raise ValueError("Expected a database session status.")
            approved = session_rows[0]["approved_at"] is not None
            snapshot = self._db.rpc(
                "get_generation_source_snapshot", {"p_session_id": str(session_id)}
            ).execute().data
            if not isinstance(snapshot, dict) or snapshot.get("session_id") != str(session_id):
                raise ValueError("Generation snapshot is malformed.")
            if snapshot.get("ready") is True:
                return _canonical_context(session_id, status, approved, snapshot)
            if snapshot.get("ready") is not False or not isinstance(snapshot.get("reason"), str):
                raise ValueError("Generation snapshot readiness is malformed.")
            reason = snapshot["reason"]
            if reason != "NO_CONFIRMATION":
                return GenerationConfigContext(
                    session_id=session_id,
                    status=status,
                    source_questions=(),
                    blueprints=(),
                    approved=approved,
                    snapshot_reason=reason,
                )

            source_rows = _rows(
                self._db.table("source_questions")
                .select("id,session_id")
                .eq("session_id", str(session_id))
                .order("question_no")
                .limit(21)
                .execute()
                .data
            )
            sources: list[SourceQuestionConfigContext] = []
            for row in source_rows:
                source = SourceQuestionConfigContext(
                    id=_uuid(row["id"]), session_id=_uuid(row["session_id"])
                )
                if source.session_id != session_id:
                    raise ValueError("Source response is outside the requested session.")
                sources.append(source)

            blueprints: list[BlueprintConfigContext] = []
            if sources:
                source_ids = {source.id for source in sources}
                query_ids = list(dict.fromkeys(str(source.id) for source in sources))
                blueprint_rows = _rows(
                    self._db.table("question_blueprints")
                    .select("source_question_id,variation_modes,confirmed_at")
                    .in_("source_question_id", query_ids)
                    .order("source_question_id")
                    .limit(len(query_ids) + 1)
                    .execute()
                    .data
                )
                for row in blueprint_rows:
                    source_question_id = _uuid(row["source_question_id"])
                    if source_question_id not in source_ids:
                        raise ValueError("Blueprint response is outside the requested sources.")
                    blueprints.append(
                        BlueprintConfigContext(
                            source_question_id=source_question_id,
                            variation_modes=row["variation_modes"],
                            confirmed_at=_confirmed_at(row["confirmed_at"]),
                        )
                    )

            return GenerationConfigContext(
                session_id=session_id,
                status=status,
                source_questions=tuple(sources),
                blueprints=tuple(blueprints),
                approved=approved,
            )
        except GenerationConfigError:
            raise
        except APIError as exc:
            raise _rpc_error(exc) from exc
        except Exception as exc:
            raise _storage_failure() from exc

    def save_config(
        self,
        session_id: UUID,
        config: GenerationConfigRequest,
        expected_snapshot: dict[str, object] | None,
    ) -> GenerationConfigResponse:
        parameters = {
            "p_session_id": str(session_id),
            "p_n_versions": config.n_versions,
            "p_active_variation_modes": list(config.active_variation_modes),
            "p_ordering_preferences": config.ordering_preferences.model_dump(),
            "p_expected_snapshot": deepcopy(expected_snapshot),
        }
        try:
            data = self._db.rpc("save_generation_config", parameters).execute().data
            result = GenerationConfigResponse.model_validate(data)
            if (
                result.session_id != session_id
                or result.config.n_versions != config.n_versions
                or result.config.active_variation_modes != config.active_variation_modes
                or result.config.ordering_preferences != config.ordering_preferences
                or result.config.source_manifest != expected_snapshot
                or result.config.canonical_dimensions
                != sorted(set(resolve_modes_to_canonical_dimensions(config.active_variation_modes)))
            ):
                raise ValueError("Saved configuration receipt differs from the request.")
            return result
        except GenerationConfigError:
            raise
        except APIError as exc:
            raise _rpc_error(exc, save=True) from exc
        except (httpx.TransportError, TimeoutError, ConnectionError) as exc:
            raise GenerationConfigError(
                504,
                "ERR_CONFIG_OUTCOME_UNCERTAIN",
                "Save outcome is uncertain; reload the session before trying again.",
            ) from exc
        except Exception as exc:
            raise _storage_failure() from exc

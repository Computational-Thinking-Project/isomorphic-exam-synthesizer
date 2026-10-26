"""Read-only database adapter for TASK-207a configuration preflight.

The caller supplies an authenticated user client after auth/ownership checks.
This module never creates a client, retries with service-role privileges or
writes data. Separate preflight reads may observe concurrent changes and do not
form a database transaction; the future save RPC must revalidate under a session
lock.
"""

from datetime import datetime
from typing import cast
from uuid import UUID

from supabase import Client

from app.services.generation.config_service import (
    BlueprintConfigContext,
    GenerationConfigContext,
    GenerationConfigError,
    SourceQuestionConfigContext,
)


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


class GenerationConfigRepository:
    """Load policy inputs using only the supplied user's database visibility."""

    def __init__(self, db: Client) -> None:
        self._db = db

    def load_context(self, session_id: UUID) -> GenerationConfigContext | None:
        """Return None for a missing/RLS-hidden session, or a typed read snapshot.

        Read at most 21 sources: the extra row lets policy reject the 20-question
        overflow without an unbounded query. Keep duplicate sources/Blueprints
        visible to policy, rather than silently choosing one or fixing them.
        """
        try:
            session_rows = _rows(
                self._db.table("exam_sessions")
                .select("id,status")
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
            )
        except Exception as exc:
            raise GenerationConfigError(
                500,
                "ERR_CONFIG_STORAGE_FAILURE",
                "Generation configuration could not be processed.",
            ) from exc

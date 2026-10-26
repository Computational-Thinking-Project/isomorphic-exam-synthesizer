"""Pure configuration policy: no database, HTTP or AI side effects.

The future persistence RPC must repeat these checks under a session lock.
Passing this preflight alone does not authorize a later database write.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.models.generation_config import GenerationConfigRequest


@dataclass(frozen=True)
class SourceQuestionConfigContext:
    id: UUID
    session_id: UUID


@dataclass(frozen=True)
class BlueprintConfigContext:
    source_question_id: UUID
    # Database JSON is untrusted; validate its structure even for an empty request.
    variation_modes: object
    confirmed_at: datetime | None


@dataclass(frozen=True)
class GenerationConfigContext:
    session_id: UUID
    status: str
    source_questions: tuple[SourceQuestionConfigContext, ...]
    blueprints: tuple[BlueprintConfigContext, ...]


@dataclass(frozen=True)
class VariationModeConflict:
    source_question_id: UUID
    unsupported_modes: tuple[str, ...]


class GenerationConfigError(Exception):
    """Domain failure that the HTTP layer can map without parsing error text."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        conflicts: tuple[VariationModeConflict, ...] = (),
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.conflicts = conflicts

    def to_detail(self) -> dict[str, object]:
        detail: dict[str, object] = {"code": self.code, "message": self.message}
        if self.conflicts:
            detail["conflicts"] = [
                {
                    "source_question_id": str(conflict.source_question_id),
                    "unsupported_modes": list(conflict.unsupported_modes),
                }
                for conflict in self.conflicts
            ]
        return detail


def _source_not_ready() -> GenerationConfigError:
    return GenerationConfigError(
        422,
        "ERR_SOURCE_NOT_READY",
        "The session requires 1–20 source questions with confirmed Blueprints.",
    )


def _stored_modes(value: object) -> set[str]:
    if not isinstance(value, list) or any(
        not isinstance(mode, str) or not mode.strip() for mode in value
    ):
        raise GenerationConfigError(
            500,
            "ERR_CONFIG_STORAGE_FAILURE",
            "Generation configuration could not be processed.",
        )
    # Preserve stored IDs exactly; do not translate or silently repair database data.
    return set(value)


def validate_generation_config(
    config: GenerationConfigRequest, context: GenerationConfigContext
) -> GenerationConfigRequest:
    """Validate a normalized request against a snapshot without changing either."""
    if context.status not in {"blueprinted", "configured"}:
        raise GenerationConfigError(
            409,
            "ERR_SESSION_NOT_CONFIGURABLE",
            "The session state does not allow configuration changes.",
        )

    sources = context.source_questions
    if not 1 <= len(sources) <= 20:
        raise _source_not_ready()

    source_ids = {source.id for source in sources}
    if len(source_ids) != len(sources) or any(
        source.session_id != context.session_id for source in sources
    ):
        raise _source_not_ready()

    blueprints_by_source: dict[UUID, BlueprintConfigContext] = {}
    for blueprint in context.blueprints:
        if (
            blueprint.source_question_id not in source_ids
            or blueprint.source_question_id in blueprints_by_source
            or blueprint.confirmed_at is None
        ):
            raise _source_not_ready()
        blueprints_by_source[blueprint.source_question_id] = blueprint
    if blueprints_by_source.keys() != source_ids:
        raise _source_not_ready()

    allowed_by_source = {
        source.id: _stored_modes(blueprints_by_source[source.id].variation_modes)
        for source in sources
    }
    conflicts: list[VariationModeConflict] = []
    for source in sources:
        unsupported = tuple(
            mode
            for mode in config.active_variation_modes
            if mode not in allowed_by_source[source.id]
        )
        if unsupported:
            conflicts.append(VariationModeConflict(source.id, unsupported))
    if conflicts:
        raise GenerationConfigError(
            400,
            "ERR_CONFIG_CONFLICT",
            "Requested modes are not supported by every source Blueprint.",
            tuple(conflicts),
        )

    return config

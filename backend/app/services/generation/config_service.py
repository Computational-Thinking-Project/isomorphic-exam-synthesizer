"""Pure configuration policy: no database, HTTP or AI side effects.

The persistence RPC repeats these checks under a session lock.
Passing this preflight alone does not authorize a later database write.
"""

from dataclasses import dataclass
from uuid import UUID

from app.models.generation_config import GenerationConfigRequest


@dataclass(frozen=True)
class SourceQuestionConfigContext:
    id: UUID
    session_id: UUID


@dataclass(frozen=True)
class CanonicalBlueprintConfigContext:
    source_question_id: UUID
    canonical_blueprint: object


@dataclass(frozen=True)
class GenerationConfigContext:
    session_id: UUID
    status: str
    source_questions: tuple[SourceQuestionConfigContext, ...]
    approved: bool = False
    snapshot_ready: bool = False
    snapshot_reason: str | None = None
    canonical_blueprints: tuple[CanonicalBlueprintConfigContext, ...] = ()
    expected_snapshot: dict[str, object] | None = None


class GenerationConfigError(Exception):
    """Domain failure that the HTTP layer can map without parsing error text."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def to_detail(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message}


def _source_not_ready() -> GenerationConfigError:
    return GenerationConfigError(
        422,
        "ERR_SOURCE_NOT_READY",
        "The session requires 1–20 source questions with confirmed Blueprints.",
    )


_SUPPORTED_DIMENSIONS = {"values", "context", "wording", "names", "representation", "option_order"}
_TEXT_FIELDS = ("id", "description")
_LIST_FIELDS = ("target_refs", "preconditions", "limits")
_TRANSFORMATION_FIELDS = {"dimension", *_TEXT_FIELDS, *_LIST_FIELDS}


def _validate_canonical_policy(blueprint: object) -> None:
    requirement = blueprint.get("requirement") if isinstance(blueprint, dict) else None
    policy = requirement.get("variation_policy") if isinstance(requirement, dict) else None
    transformations = policy.get("allowed_transformations") if isinstance(policy, dict) else None
    if not isinstance(transformations, list) or not transformations:
        raise _source_not_ready()
    for item in transformations:
        if (
            not isinstance(item, dict)
            or item.keys() != _TRANSFORMATION_FIELDS
            or not isinstance(item["dimension"], str)
            or item["dimension"] not in _SUPPORTED_DIMENSIONS
        ):
            raise _source_not_ready()
        for key in _TEXT_FIELDS:
            value = item[key]
            if not isinstance(value, str) or not value.strip():
                raise _source_not_ready()
        for key in _LIST_FIELDS:
            values = item[key]
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise _source_not_ready()


def _storage_failure() -> GenerationConfigError:
    return GenerationConfigError(
        500, "ERR_CONFIG_STORAGE_FAILURE", "Generation configuration could not be processed."
    )


def validate_generation_config(
    config: GenerationConfigRequest, context: GenerationConfigContext
) -> GenerationConfigRequest:
    """Validate a normalized request against a snapshot without changing either."""
    if context.status not in {"blueprinted", "configured"} or context.approved:
        raise GenerationConfigError(
            409,
            "ERR_SESSION_NOT_CONFIGURABLE",
            "The session state does not allow configuration changes.",
        )

    if not context.snapshot_ready:
        raise _source_not_ready()
    if not isinstance(context.expected_snapshot, dict) or context.snapshot_reason is not None:
        raise _storage_failure()

    sources = context.source_questions
    if not 1 <= len(sources) <= 20:
        raise _source_not_ready()

    source_ids = {source.id for source in sources}
    if len(source_ids) != len(sources) or any(
        source.session_id != context.session_id for source in sources
    ):
        raise _source_not_ready()

    blueprint_ids = {blueprint.source_question_id for blueprint in context.canonical_blueprints}
    if blueprint_ids != source_ids or len(context.canonical_blueprints) != len(source_ids):
        raise _source_not_ready()
    for blueprint in context.canonical_blueprints:
        _validate_canonical_policy(blueprint.canonical_blueprint)

    return config

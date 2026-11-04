"""Prepare exact source/canonical artifacts at the confirmation write boundary.

These detached payloads are NOT persisted confirmation evidence. The database
must compare source content under the session lock, derive actor/time, commit the
revision and reject superseded publication. Reject must never call this producer
to manufacture a missing historical confirmation.
"""

from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from app.models.schemas import SourceQuestion
from app.services.blueprint.adapters import source_to_item, validate_math_blueprint
from app.services.blueprint.common import ToolError, load_json
from app.services.blueprint.config import Config
from app.services.blueprint.input_adapter import Contracts
from app.services.blueprint.service import source_fingerprint


def prepare_source_artifacts(session_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare a new per-question revision without altering persisted content."""
    try:
        session = UUID(session_id)
        if not 1 <= len(rows) <= 20:
            raise ValueError("Confirmation requires one to twenty sources")
        prepared = []
        seen: set[UUID] = set()
        for row in deepcopy(rows):
            source_id = UUID(row["id"])
            if UUID(row["session_id"]) != session or source_id in seen:
                raise ValueError("Source ownership/identity mismatch")
            seen.add(source_id)
            raw_options = row["options"]
            if isinstance(raw_options, dict) and set(raw_options) == set("ABCD"):
                options = [raw_options[key] for key in "ABCD"]
            elif isinstance(raw_options, list):
                options = raw_options
            else:
                raise ValueError("Invalid source options")
            if row["correct_key"] not in "ABCD" or len(row["correct_key"]) != 1:
                raise ValueError("Invalid source key")
            # Strict validation prevents numbers/flags from being coerced into
            # source text. NULL solution has the explicitly agreed empty mapping.
            source = SourceQuestion.model_validate(
                {
                    "id": str(source_id),
                    "question_text": row["raw_content"],
                    "options": options,
                    "correct_answer": row["correct_key"],
                    "solution": "" if row["solution_md"] is None else row["solution_md"],
                },
                strict=True,
            )
            if not source.question_text.strip() or len(source.question_text) > 12000:
                raise ValueError("Invalid source stem")
            item = source_to_item(source)  # validates answer association/unique four options
            prepared.append(
                {
                    "source_question_id": str(source_id),
                    "source_revision_id": str(uuid4()),
                    "confirmed_input": source.model_dump(
                        include={"id", "question_text", "options", "correct_answer", "solution"}
                    ),
                    "source_fingerprint": source_fingerprint([item]),
                }
            )
        return prepared
    except (ValueError, TypeError, KeyError, AttributeError, ToolError) as exc:
        raise ToolError("SOURCE_ARTIFACT_INVALID", "Nguồn xác nhận không hợp lệ.") from exc


def prepare_blueprint_artifact(
    source_artifact: dict[str, Any], blueprint: dict[str, Any]
) -> dict[str, Any]:
    """Validate canonical output against the exact committed source revision.

    The caller supplies its validated persistence receipt, not live rows. Hash
    verification detects corruption; it never fills or overwrites a missing hash.
    Publication still needs a transactional compare against the current revision.
    """
    try:
        source_record = deepcopy(source_artifact)
        source_id = UUID(source_record["source_question_id"])
        revision = UUID(source_record["source_revision_id"])
        source = SourceQuestion.model_validate(source_record["confirmed_input"], strict=True)
        if UUID(source.id) != source_id:
            raise ValueError("Source identity mismatch")
        item = source_to_item(source)
        stored_hash = source_record["source_fingerprint"]
        if not isinstance(stored_hash, str) or stored_hash != source_fingerprint([item]):
            raise ValueError("Persisted source fingerprint mismatch")
        canonical = deepcopy(blueprint)
        config = Config()
        schema = load_json(config.schema_path)
        validate_math_blueprint(canonical, item, Contracts(schema), schema)
        return {
            "source_question_id": str(source_id),
            "source_revision_id": str(revision),
            "source_fingerprint": stored_hash,
            "blueprint_revision_id": str(uuid4()),
            "schema_version": "0.4.0",
            "canonical_blueprint": canonical,
        }
    except (ValueError, TypeError, KeyError, AttributeError, ToolError) as exc:
        raise ToolError(
            "BLUEPRINT_ARTIFACT_INVALID", "Blueprint không khớp bản nguồn đã xác nhận."
        ) from exc

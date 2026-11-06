"""Validate TASK-304 evidence without manufacturing or coercing provider results."""

from copy import deepcopy
from functools import lru_cache
from typing import Any
from uuid import UUID

from app.models.schemas import ReviewDomainException, SourceQuestion
from app.services.blueprint.adapters import normalized_text, source_to_item, validate_math_blueprint
from app.services.blueprint.common import ToolError, load_json
from app.services.blueprint.config import Config
from app.services.blueprint.input_adapter import Contracts
from app.services.blueprint.service import source_fingerprint
from app.services.review.receipts import ReservationReceipt
from app.services.validator.base import CheckResult


@lru_cache(maxsize=1)
def _blueprint_contract():
    schema = load_json(Config().schema_path)
    return schema, Contracts(schema)


def frozen_inputs(receipt: ReservationReceipt) -> dict[str, Any]:
    """Validate the proposed artifact envelope, never synthesize confirmation.

    Current TASK-302 database_rows snapshots intentionally fail here until the
    owner supplies persisted artifacts. This support is not a rollout certificate.
    """
    try:
        data = deepcopy(receipt.snapshot)
        if data.get("format") != "confirmed_artifacts_v1":
            raise ValueError("Confirmed artifacts unavailable")
        source_revision = UUID(data["source_revision_id"])
        UUID(data["blueprint_revision_id"])
        if UUID(data["blueprint_source_revision_id"]) != source_revision:
            raise ValueError("Blueprint revision binding mismatch")
        source = data["source_snapshot"]
        if not isinstance(source, dict) or not all(
            k in source
            for k in (
                "id",
                "question_text",
                "options",
                "correct_answer",
                "solution",
                "content_hash",
            )
        ):
            raise ValueError("Confirmed source incomplete")
        UUID(source["id"])
        validated = SourceQuestion.model_validate(source, strict=True)
        item = source_to_item(validated)
        stored_hash = source["content_hash"]
        if (
            not isinstance(stored_hash, str)
            or not stored_hash
            or stored_hash != data["blueprint_source_fingerprint"]
        ):
            raise ValueError("Blueprint fingerprint binding mismatch")
        # Verification of persisted evidence is allowed; never fill a missing hash.
        if source_fingerprint([item]) != stored_hash:
            raise ValueError("Confirmed source fingerprint mismatch")
        schema, contracts = _blueprint_contract()
        validate_math_blueprint(data["blueprint"], item, contracts, schema)
        current = data["current_variant"]
        peers = data["peer_variants"]
        if (
            not isinstance(current, dict)
            or UUID(current["id"]) != receipt.question_id
            or not isinstance(peers, list)
        ):
            raise ValueError("Variant identity mismatch")
        version = UUID(current["version_id"])
        ids = {receipt.question_id}
        versions = {version}
        for candidate in [current, *peers]:
            if (
                not isinstance(candidate, dict)
                or candidate.get("source_question_id") != source["id"]
            ):
                raise ValueError("Variant source mismatch")
            stem = candidate.get("content", candidate.get("stem_latex"))
            options = candidate.get("options")
            if (
                not isinstance(stem, str)
                or not stem.strip()
                or not isinstance(options, list)
                or len(options) != 4
                or any(not isinstance(o, str) or not o.strip() for o in options)
            ):
                raise ValueError("Variant representation invalid")
            if candidate is not current:
                qid, vid = UUID(candidate["id"]), UUID(candidate["version_id"])
                if qid in ids or vid in versions:
                    raise ValueError("Invalid peer set")
                ids.add(qid)
                versions.add(vid)
        return {
            key: data[key]
            for key in ("source_snapshot", "blueprint", "current_variant", "peer_variants")
        }
    except (ValueError, KeyError, TypeError, AttributeError, ToolError) as exc:
        raise ReviewDomainException(
            422,
            "ERR_SOURCE_NOT_CONFIRMED",
            "Confirmed source/Blueprint artifacts unavailable or inconsistent",
        ) from exc


def validate_candidate(value: Any) -> dict[str, Any]:
    """Return a detached RPC payload, or reject it before any completion write."""

    def invalid(message: str) -> None:
        raise ReviewDomainException(422, "ERR_INVALID_PAYLOAD", message)

    if not isinstance(value, dict):
        invalid("Candidate must be an object")
    if set(value) - {
        "stem_latex",
        "content",
        "solution_md",
        "options",
        "correct_key",
        "api_calls_count",
        "validation_report",
    }:
        invalid("Candidate contains unknown fields")
    stem = value.get("stem_latex")
    if not isinstance(stem, str) or not 1 <= len(stem.strip()) <= 12000:
        invalid("Candidate requires a nonempty stem")
    if "content" in value and value["content"] != stem:
        invalid("Candidate content must equal stem_latex")
    solution = value.get("solution_md")
    if not isinstance(solution, str) or not solution.strip():
        invalid("Candidate requires solution_md")
    options = value.get("options")
    if not isinstance(options, list) or len(options) != 4:
        invalid("Candidate requires four options")
    if any(not isinstance(opt, str) or not 1 <= len(opt.strip()) <= 4000 for opt in options):
        invalid("Candidate options must be nonempty strings")
    if (
        len({normalized_text(opt) for opt in options}) != 4
        or len({opt.strip().lower() for opt in options}) != 4
    ):
        invalid("Candidate options must be distinct")
    if value.get("correct_key") not in ("A", "B", "C", "D"):
        invalid("Candidate requires a valid answer key")
    calls = value.get("api_calls_count")
    if type(calls) is not int or not 0 <= calls <= 4:
        invalid("Candidate api_calls_count must be an integer from zero to four")
    report = value.get("validation_report")
    if not isinstance(report, dict) or report.get("is_valid") is not True:
        invalid("Candidate requires valid validation evidence")
    if set(report) != {
        "is_valid",
        "math_verified",
        "requires_teacher_review",
        "checks",
        "warnings",
    }:
        invalid("Candidate report fields do not match TASK-304")
    if (
        type(report.get("math_verified")) is not bool
        or report.get("requires_teacher_review") is not True
    ):
        invalid("Candidate requires explicit verification and teacher review flags")
    if not isinstance(report.get("checks"), list) or any(
        not isinstance(check, dict) for check in report["checks"]
    ):
        invalid("Candidate checks must be an array of check records")
    if not isinstance(report.get("warnings"), list) or any(
        not isinstance(warning, str) for warning in report["warnings"]
    ):
        invalid("Candidate warnings must be an array of strings")
    try:
        for check in report["checks"]:
            CheckResult.model_validate(check, strict=True)
    except ValueError as exc:
        raise ReviewDomainException(422, "ERR_INVALID_PAYLOAD", "Invalid check evidence") from exc
    if report["math_verified"] and not any(
        check.get("check_name") == "answer_verified"
        and check.get("passed") is True
        and check.get("status") == "verified"
        and check.get("confidence") == "sympy_verified"
        for check in report["checks"]
    ):
        invalid("Mathematical verification requires matching validator evidence")
    return deepcopy(
        {
            "stem_latex": stem,
            "solution_md": solution,
            "options": options,
            "correct_key": value["correct_key"],
            "api_calls_count": calls,
            "validation_report": report,
        }
    )

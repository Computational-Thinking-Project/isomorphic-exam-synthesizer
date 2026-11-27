"""Published mode aliases and the version 1.1 per-question policy."""

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

PUBLIC_TO_CANONICAL_DIMENSIONS = {
    "NUMERICAL": "values",
    "parameter_variation": "values",
    "context_swap": "context",
}
PER_QUESTION_MAPPING_VERSION = "1.1"
# EXT-02: version 1.2 also freezes an explicit generation_mode in the job snapshot.
MODE_MAPPING_VERSION = "1.2"
GENERATION_MODES = ("ai_generation", "shuffle_only")


def question_policy(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Derive a new-job decision; malformed/empty policies never imply Clone."""
    from app.services.generation.config_service import (
        GenerationConfigError,
        validate_canonical_policy,
    )

    try:
        validate_canonical_policy(blueprint)
    except GenerationConfigError as exc:
        raise ValueError("Malformed canonical variation policy") from exc
    supported = {
        item["dimension"]
        for item in blueprint["requirement"]["variation_policy"]["allowed_transformations"]
    }
    dimensions = [dimension for dimension in ("values", "context") if dimension in supported]
    return {
        "canonical_dimensions": dimensions,
        "result_kind": "AI_RESULT" if dimensions else "ORIGINAL_CLONE",
    }


def mode_question_policy(generation_mode: str, blueprint: dict[str, Any]) -> dict[str, Any]:
    """Policy a job freezes for one question; shuffle_only never asks for AI."""
    # Malformed Blueprint evidence is rejected in both modes.
    policy = question_policy(blueprint)
    if generation_mode == "shuffle_only":
        return {"canonical_dimensions": [], "result_kind": "ORIGINAL_CLONE"}
    if generation_mode != "ai_generation":
        raise ValueError("Unknown generation mode")
    return policy


def frozen_generation_mode(config: dict[str, Any], context: dict[str, Any]) -> str:
    """Read a claimed job's mode from its snapshot, never from variation modes."""
    mapping_version = context.get("mapping_version")
    if mapping_version in {"1.0", PER_QUESTION_MAPPING_VERSION}:
        # Pre-EXT-02 snapshots are AI jobs; a migrated claim RPC reports that explicitly.
        if "generation_mode" in context or config.get("generation_mode", "ai_generation") != "ai_generation":
            raise ValueError("Legacy snapshot cannot carry another generation mode")
        return "ai_generation"
    mode = context.get("generation_mode")
    if (
        mapping_version != MODE_MAPPING_VERSION
        or mode not in GENERATION_MODES
        or config.get("generation_mode") != mode
    ):
        raise ValueError("Unknown or inconsistent frozen generation mode")
    return cast(str, mode)


class GenerationModeConflict(ValueError):
    """A frozen job snapshot does not follow the migration 028 mode/policy rules."""


_RESULT_KINDS = ("AI_RESULT", "ORIGINAL_CLONE")


def job_generation_mode(snapshot: Mapping[str, Any]) -> str:
    """Mode of a frozen job, for a ``generation_job_snapshots`` row read by service_role.

    Mirrors ``public._generation_job_mode`` in migration 028 and must change together
    with it (parity-tested in tests/migrations/test_generation_mode_pg.py).
    """
    version = snapshot.get("mapping_version")
    if version in ("1.0", PER_QUESTION_MAPPING_VERSION):
        return "ai_generation"
    payload = snapshot.get("snapshot_payload")
    mode = snapshot.get("generation_mode")
    if (
        version != MODE_MAPPING_VERSION
        or mode not in GENERATION_MODES
        or not isinstance(payload, Mapping)
        or payload.get("generation_mode") != mode
    ):
        raise GenerationModeConflict("Unknown or inconsistent generation mode")
    return cast(str, mode)


def slot_result_kind(snapshot: Mapping[str, Any], source_question_id: str | UUID) -> str:
    """Frozen result kind of one source question: ``AI_RESULT`` or ``ORIGINAL_CLONE``.

    Mirrors ``public._generation_is_clone`` in migration 028 and must change together
    with it: mapping 1.0 uses the session-wide rule, 1.1/1.2 the frozen per-slot policy,
    and a 1.2 shuffle_only job is always ``ORIGINAL_CLONE``. Fails closed. Unlike the SQL
    helper it does not re-derive the policy from the Blueprint; the database checks that
    on every claim and persist.
    """
    version = snapshot.get("mapping_version")
    if version == "1.0":
        clone = snapshot.get("public_modes") == [] and snapshot.get("canonical_dimensions") == []
        return "ORIGINAL_CLONE" if clone else "AI_RESULT"
    if version not in (PER_QUESTION_MAPPING_VERSION, MODE_MAPPING_VERSION):
        raise GenerationModeConflict("Unknown mapping version")
    mode = job_generation_mode(snapshot)
    payload = snapshot.get("snapshot_payload")
    policies = payload.get("question_policies") if isinstance(payload, Mapping) else None
    policy = policies.get(str(source_question_id)) if isinstance(policies, Mapping) else None
    kind = policy.get("result_kind") if isinstance(policy, Mapping) else None
    if kind not in _RESULT_KINDS or (mode == "shuffle_only" and kind != "ORIGINAL_CLONE"):
        raise GenerationModeConflict("Missing or inconsistent frozen slot policy")
    return cast(str, kind)


MODE_LABELS = {
    "NUMERICAL": "Thay đổi số liệu",
    "parameter_variation": "Thay đổi số liệu / tham số",
    "context_swap": "Đổi ngữ cảnh thực tế",
}


def normalize_variation_modes(modes: list[str] | None) -> list[str]:
    """Preserve exact public IDs; only the exact singleton NONE means clone."""
    if modes is None or modes == [] or modes == ["NONE"]:
        return []
    if "NONE" in modes:
        raise ValueError("NONE cannot be combined with other variation modes")
    if any(
        not isinstance(mode, str) or mode not in PUBLIC_TO_CANONICAL_DIMENSIONS for mode in modes
    ):
        raise ValueError("Variation mode is unsupported by public profile 1.0")
    return list(dict.fromkeys(modes))


def resolve_modes_to_canonical_dimensions(modes: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            PUBLIC_TO_CANONICAL_DIMENSIONS[mode] for mode in normalize_variation_modes(modes)
        )
    )


def compute_supported_modes_summary(
    blueprints: list[dict[str, Any]], total_sources: int
) -> list[dict[str, Any]]:
    """Reject malformed evidence instead of turning it into a clone-only session."""
    if total_sources == 0 or len(blueprints) != total_sources:
        raise ValueError("Canonical blueprints are incomplete")
    dimension_sets = []
    for blueprint in blueprints:
        requirement = blueprint.get("requirement")
        policy = requirement.get("variation_policy") if isinstance(requirement, dict) else None
        transforms = policy.get("allowed_transformations") if isinstance(policy, dict) else None
        if not isinstance(transforms, list) or any(
            not isinstance(item, dict)
            or item.get("dimension")
            not in {"values", "context", "wording", "names", "representation", "option_order"}
            for item in transforms
        ):
            raise ValueError("Malformed canonical variation policy")
        dimension_sets.append({item["dimension"] for item in transforms})
    counts = {
        mode: sum(dimension in dimensions for dimensions in dimension_sets)
        for mode, dimension in PUBLIC_TO_CANONICAL_DIMENSIONS.items()
    }
    return supported_modes_from_counts(counts, total_sources)


def supported_modes_from_counts(counts: dict[str, int], total_sources: int) -> list[dict[str, Any]]:
    """Project canonical dimensions or exact legacy IDs through the same profile."""
    result = []
    for mode, count in counts.items():
        if mode not in MODE_LABELS or not count:
            continue
        item: dict[str, Any] = {
            "id": mode,
            "label": MODE_LABELS[mode],
            "question_count": count,
            "is_available": count == total_sources,
        }
        if count != total_sources:
            item["unavailable_reason"] = (
                f"Chỉ hỗ trợ {count}/{total_sources} câu trong đề (yêu cầu toàn bộ câu hỏi hỗ trợ)."
            )
        result.append(item)
    return sorted(result, key=lambda item: (not item["is_available"], item["id"]))

"""The explicitly published Stage 2 mode profile (mapping version 1.0)."""

from typing import Any

PUBLIC_TO_CANONICAL_DIMENSIONS = {
    "NUMERICAL": "values",
    "parameter_variation": "values",
    "context_swap": "context",
}
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

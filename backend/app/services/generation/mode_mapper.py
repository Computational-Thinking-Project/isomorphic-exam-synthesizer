"""Mode resolution and canonical dimensions mapping for Stage 2 (TASK-207a/b).

Adheres to:
- I-B-POLICY / AI Contract #41 (docs/ai-w2-integration.md)
- FE2 Agreement (PR #30, PR #40)

Mappings:
- NUMERICAL, parameter_variation -> values
- context_swap -> context
- Canonical IDs (values, context, wording, names, representation, option_order) pass-through directly if supported
- NONE -> [] (Original Clone, zero Gemini calls)
- Unsupported modes: STRUCTURAL, variable_inversion, etc. -> raise ValueError
- NONE mixed with other modes -> raise ValueError
"""

from typing import Any, List, Optional, Set

PUBLIC_TO_CANONICAL_DIMENSIONS = {
    "NUMERICAL": "values",
    "parameter_variation": "values",
    "context_swap": "context",
    "values": "values",
    "context": "context",
    "wording": "wording",
    "names": "names",
    "representation": "representation",
    "option_order": "option_order",
}

UNSUPPORTED_MODES = {
    "STRUCTURAL",
    "structural",
    "variable_inversion",
    "scenario",
    "reverse",
    "visual",
}


def normalize_variation_modes(modes: Optional[List[str]]) -> List[str]:
    """Normalize input variation modes preserving case and order, handling NONE."""
    if not modes:
        return []

    # Check for NONE
    has_none = any(str(m).strip().upper() == "NONE" for m in modes)
    if has_none:
        if len(modes) > 1:
            raise ValueError("NONE cannot be combined with other variation modes")
        return []

    seen: Set[str] = set()
    normalized: List[str] = []
    for m in modes:
        clean = str(m).strip()
        if not clean:
            raise ValueError("Variation mode cannot be empty")
        if clean in UNSUPPORTED_MODES:
            raise ValueError(f"Variation mode '{clean}' is unsupported")
        if clean not in seen:
            seen.add(clean)
            normalized.append(clean)
    return normalized


def resolve_modes_to_canonical_dimensions(modes: List[str]) -> List[str]:
    """Map public mode IDs to canonical blueprint dimensions."""
    resolved: List[str] = []
    seen: Set[str] = set()
    for m in modes:
        dim = PUBLIC_TO_CANONICAL_DIMENSIONS.get(m)
        if not dim:
            raise ValueError(f"Unmapped variation mode: {m}")
        if dim not in seen:
            seen.add(dim)
            resolved.append(dim)
    return resolved


def compute_supported_modes_summary(
    blueprints: List[dict[str, Any]], total_sources: int
) -> List[dict[str, Any]]:
    """Compute supported modes projection for session detail from canonical blueprints.

    Each blueprint must have requirement.variation_policy.allowed_transformations[].dimension.
    """
    if not blueprints or total_sources == 0:
        return []

    dim_counts: dict[str, int] = {}
    for bp in blueprints:
        req = bp.get("requirement") or {}
        policy = req.get("variation_policy") or {}
        transforms = policy.get("allowed_transformations") or []
        dims_in_bp = {
            str(t.get("dimension")) for t in transforms if isinstance(t, dict) and t.get("dimension")
        }
        for d in dims_in_bp:
            dim_counts[d] = dim_counts.get(d, 0) + 1

    # Map dimensions to public representations for FE2
    dim_labels = {
        "values": "Thay đổi số liệu / tham số (values)",
        "context": "Đổi ngữ cảnh thực tế (context)",
        "wording": "Diễn đạt lại văn bản (wording)",
        "names": "Đổi tên riêng / đối tượng (names)",
        "representation": "Thay đổi cách biểu diễn (representation)",
        "option_order": "Xáo trộn thứ tự đáp án (option_order)",
    }

    supported_modes = []
    for d, count in dim_counts.items():
        if d in UNSUPPORTED_MODES:
            continue
        available = (count == total_sources)
        mode_item: dict[str, Any] = {
            "id": d,
            "label": dim_labels.get(d, d),
            "question_count": count,
            "is_available": available,
        }
        if not available:
            mode_item["unavailable_reason"] = (
                f"Chỉ hỗ trợ {count}/{total_sources} câu trong đề (yêu cầu toàn bộ câu hỏi hỗ trợ)."
            )
        supported_modes.append(mode_item)

    supported_modes.sort(key=lambda x: (not x["is_available"], x["id"]))
    return supported_modes

"""Unit and property tests for mode_mapper.py."""

import pytest

from app.services.generation.mode_mapper import (
    compute_supported_modes_summary,
    normalize_variation_modes,
    resolve_modes_to_canonical_dimensions,
)


def test_normalize_empty_and_none():
    assert normalize_variation_modes(None) == []
    assert normalize_variation_modes([]) == []
    assert normalize_variation_modes(["NONE"]) == []
    assert normalize_variation_modes(["none"]) == []
    assert normalize_variation_modes([" NONE "]) == []


def test_normalize_mixed_none_raises():
    with pytest.raises(ValueError, match="NONE cannot be combined"):
        normalize_variation_modes(["NONE", "values"])
    with pytest.raises(ValueError, match="NONE cannot be combined"):
        normalize_variation_modes(["values", "none"])


def test_normalize_unsupported_modes_raises():
    with pytest.raises(ValueError, match="is unsupported"):
        normalize_variation_modes(["STRUCTURAL"])
    with pytest.raises(ValueError, match="is unsupported"):
        normalize_variation_modes(["variable_inversion"])


def test_normalize_valid_modes():
    modes = [" NUMERICAL ", "context_swap", "NUMERICAL"]
    assert normalize_variation_modes(modes) == ["NUMERICAL", "context_swap"]


def test_resolve_modes_to_canonical():
    assert resolve_modes_to_canonical_dimensions(["NUMERICAL"]) == ["values"]
    assert resolve_modes_to_canonical_dimensions(["parameter_variation"]) == ["values"]
    assert resolve_modes_to_canonical_dimensions(["context_swap"]) == ["context"]
    assert resolve_modes_to_canonical_dimensions(["values", "context"]) == ["values", "context"]


def test_compute_supported_modes_summary():
    bp1 = {
        "requirement": {
            "variation_policy": {
                "allowed_transformations": [
                    {"dimension": "values"},
                    {"dimension": "context"},
                ]
            }
        }
    }
    bp2 = {
        "requirement": {
            "variation_policy": {
                "allowed_transformations": [
                    {"dimension": "values"},
                ]
            }
        }
    }
    summary = compute_supported_modes_summary([bp1, bp2], 2)
    assert len(summary) == 2
    # values is available (2/2)
    val_item = next(m for m in summary if m["id"] == "values")
    assert val_item["is_available"] is True
    assert val_item["question_count"] == 2

    # context is unavailable (1/2)
    ctx_item = next(m for m in summary if m["id"] == "context")
    assert ctx_item["is_available"] is False
    assert ctx_item["question_count"] == 1
    assert "1/2" in ctx_item["unavailable_reason"]

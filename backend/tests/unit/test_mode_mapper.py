"""Public mode profile and readiness regression tests."""

import pytest

from app.services.generation.mode_mapper import (
    compute_supported_modes_summary,
    normalize_variation_modes,
    resolve_modes_to_canonical_dimensions,
)


def test_clone_normalization_is_exact():
    for modes in (None, [], ["NONE"]):
        assert normalize_variation_modes(modes) == []


@pytest.mark.parametrize(
    "modes",
    [
        ["none"],
        [" NONE "],
        ["NONE", "context_swap"],
        ["STRUCTURAL"],
        ["variable_inversion"],
        ["values"],
        ["context"],
        ["wording"],
        [" NUMERICAL "],
        [None],
        ["unknown"],
    ],
)
def test_reject_unpublished_or_mixed_modes(modes):
    with pytest.raises(ValueError):
        normalize_variation_modes(modes)


def test_preserves_public_ids_and_deduplicates_dimensions():
    modes = ["NUMERICAL", "parameter_variation", "NUMERICAL", "context_swap"]
    assert normalize_variation_modes(modes) == ["NUMERICAL", "parameter_variation", "context_swap"]
    assert resolve_modes_to_canonical_dimensions(modes) == ["values", "context"]


def blueprint(*dimensions):
    return {
        "requirement": {
            "variation_policy": {
                "allowed_transformations": [{"dimension": dimension} for dimension in dimensions],
            }
        }
    }


def test_projection_exposes_only_public_aliases_and_batch_intersection():
    summary = compute_supported_modes_summary(
        [
            blueprint("values", "context", "wording"),
            blueprint("values"),
        ],
        2,
    )
    by_id = {mode["id"]: mode for mode in summary}
    assert set(by_id) == {"NUMERICAL", "parameter_variation", "context_swap"}
    assert by_id["NUMERICAL"]["is_available"]
    assert by_id["parameter_variation"]["question_count"] == 2
    assert not by_id["context_swap"]["is_available"]
    assert "1/2" in by_id["context_swap"]["unavailable_reason"]


def test_ready_without_public_dimensions_is_clone_only():
    assert compute_supported_modes_summary([blueprint("wording")], 1) == []


@pytest.mark.parametrize("blueprints,total", [([], 1), ([{}], 1), ([blueprint("values")], 2)])
def test_incomplete_or_malformed_evidence_cannot_be_clone(blueprints, total):
    with pytest.raises(ValueError):
        compute_supported_modes_summary(blueprints, total)

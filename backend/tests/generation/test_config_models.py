from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models.generation_config import (
    GenerationConfigRequest,
    GenerationConfigResponse,
    OrderingPreferences,
)


def request_payload(**overrides: object) -> dict[str, object]:
    return {"n_versions": 2, "active_variation_modes": ["NUMERICAL"], **overrides}


@pytest.mark.parametrize("n_versions", [1, 4])
def test_accept_version_boundaries(n_versions: int) -> None:
    config = GenerationConfigRequest.model_validate(request_payload(n_versions=n_versions))
    assert config.n_versions == n_versions


@pytest.mark.parametrize("n_versions", [0, -1, 5, True, False, "2", 2.0, 2.5, None])
def test_reject_invalid_or_coerced_version_count(n_versions: object) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(request_payload(n_versions=n_versions))


@pytest.mark.parametrize("field", ["n_versions", "active_variation_modes"])
def test_required_request_fields(field: str) -> None:
    payload = request_payload()
    del payload[field]
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(payload)


def test_modes_are_trimmed_deduplicated_and_case_sensitive_without_mutation() -> None:
    payload = request_payload(
        active_variation_modes=[" NUMERICAL ", "NONE", "NUMERICAL", "numerical", " CUSTOM "]
    )
    original = deepcopy(payload)
    config = GenerationConfigRequest.model_validate(payload)
    assert config.active_variation_modes == ["NUMERICAL", "NONE", "numerical", "CUSTOM"]
    assert payload == original


def test_empty_requested_modes_are_allowed() -> None:
    config = GenerationConfigRequest.model_validate(request_payload(active_variation_modes=[]))
    assert config.active_variation_modes == []


@pytest.mark.parametrize(
    "modes", [None, "NUMERICAL", {"NUMERICAL": True}, [1], [True], [None], [""], [" \t\n"]]
)
def test_reject_invalid_mode_structure_and_blank_items(modes: object) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(request_payload(active_variation_modes=modes))


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        ({}, {"shuffle_questions": True, "shuffle_options": True}),
        ({"shuffle_questions": False}, {"shuffle_questions": False, "shuffle_options": True}),
        ({"shuffle_options": False}, {"shuffle_questions": True, "shuffle_options": False}),
        (
            {"shuffle_questions": False, "shuffle_options": False},
            {"shuffle_questions": False, "shuffle_options": False},
        ),
    ],
)
def test_default_and_partial_ordering_preferences(
    provided: dict[str, bool], expected: dict[str, bool]
) -> None:
    config = GenerationConfigRequest.model_validate(request_payload(ordering_preferences=provided))
    assert config.ordering_preferences.model_dump() == expected


def test_omitted_ordering_defaults_are_independent() -> None:
    first = GenerationConfigRequest.model_validate(request_payload())
    second = GenerationConfigRequest.model_validate(request_payload())
    first.ordering_preferences.shuffle_options = False
    assert second.ordering_preferences.model_dump() == {
        "shuffle_questions": True,
        "shuffle_options": True,
    }


@pytest.mark.parametrize("field", ["shuffle_questions", "shuffle_options"])
@pytest.mark.parametrize("value", [None, 0, 1, 1.0, "true", "false", []])
def test_ordering_flags_are_strict_booleans(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        OrderingPreferences.model_validate({field: value})


@pytest.mark.parametrize("value", [None, [], "shuffle"])
def test_ordering_requires_an_object(value: object) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(request_payload(ordering_preferences=value))


@pytest.mark.parametrize("field", ["user_id", "session_id", "status", "extra"])
def test_unknown_request_fields_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(request_payload(**{field: "untrusted"}))


def test_unknown_nested_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(
            request_payload(ordering_preferences={"shuffle_answers": True})
        )


def test_response_serializes_uuid_and_normalized_config() -> None:
    response = GenerationConfigResponse.model_validate(
        {
            "session_id": "11111111-1111-4111-8111-111111111111",
            "status": "configured",
            "config": request_payload(active_variation_modes=[" NONE ", "NONE"]),
        }
    )
    assert isinstance(response.session_id, UUID)
    assert response.model_dump(mode="json") == {
        "session_id": "11111111-1111-4111-8111-111111111111",
        "status": "configured",
        "config": {
            "n_versions": 2,
            "active_variation_modes": ["NONE"],
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": True},
        },
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"session_id": "invalid"},
        {"status": "blueprinted"},
        {"config": None},
        {"extra": True},
    ],
)
def test_response_rejects_invalid_shape(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigResponse.model_validate(
            {
                "session_id": "11111111-1111-4111-8111-111111111111",
                "status": "configured",
                "config": request_payload(),
                **overrides,
            }
        )

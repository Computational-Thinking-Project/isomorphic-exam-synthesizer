from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models.generation_config import (
    GenerationConfigRequest,
    GenerationConfigResponse,
    OrderingPreferences,
)


def request_payload(**overrides: object) -> dict[str, object]:
    return {"n_versions": 2, **overrides}


@pytest.mark.parametrize("n_versions", [1, 4])
def test_accept_version_boundaries(n_versions: int) -> None:
    config = GenerationConfigRequest.model_validate(request_payload(n_versions=n_versions))
    assert config.n_versions == n_versions


@pytest.mark.parametrize("n_versions", [0, -1, 5, True, False, "2", 2.0, 2.5, None])
def test_reject_invalid_or_coerced_version_count(n_versions: object) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(request_payload(n_versions=n_versions))


def test_version_count_is_required() -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate({})


@pytest.mark.parametrize(
    "payload", [{"n_versions": 2}, {"n_versions": 2, "active_variation_modes": []}]
)
def test_accept_omitted_or_empty_requested_modes(payload: dict[str, object]) -> None:
    assert GenerationConfigRequest.model_validate(payload).active_variation_modes == []


@pytest.mark.parametrize(
    "modes", [None, (), "NUMERICAL", {"NUMERICAL": True}, [1], ["NUMERICAL"], ["NONE"], [""]]
)
def test_reject_client_selected_modes(modes: object) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(request_payload(active_variation_modes=modes))


@pytest.mark.parametrize("questions", [False, True])
@pytest.mark.parametrize("options", [False, True])
def test_accept_each_explicit_shuffle_combination(questions: bool, options: bool) -> None:
    prefs = {"shuffle_questions": questions, "shuffle_options": options}
    config = GenerationConfigRequest.model_validate(request_payload(ordering_preferences=prefs))
    assert config.ordering_preferences.model_dump() == prefs


@pytest.mark.parametrize("prefs", [{}, {"shuffle_questions": True}, {"shuffle_options": False}])
def test_explicit_ordering_requires_both_flags(prefs: dict[str, bool]) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigRequest.model_validate(request_payload(ordering_preferences=prefs))


def test_omitted_ordering_defaults_are_off_and_independent() -> None:
    first = GenerationConfigRequest.model_validate(request_payload())
    second = GenerationConfigRequest.model_validate(request_payload())
    first.ordering_preferences.shuffle_options = True
    first.active_variation_modes.append("test")
    assert second.active_variation_modes == []
    assert second.ordering_preferences.model_dump() == {
        "shuffle_questions": False,
        "shuffle_options": False,
    }


@pytest.mark.parametrize("field", ["shuffle_questions", "shuffle_options"])
@pytest.mark.parametrize("value", [None, 0, 1, 1.0, "true", "false", []])
def test_ordering_flags_are_strict_booleans(field: str, value: object) -> None:
    prefs = {"shuffle_questions": False, "shuffle_options": False, field: value}
    with pytest.raises(ValidationError):
        OrderingPreferences.model_validate(prefs)


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
            request_payload(
                ordering_preferences={
                    "shuffle_questions": False,
                    "shuffle_options": False,
                    "shuffle_answers": True,
                }
            )
        )


def test_response_preserves_server_derived_modes_and_ordering() -> None:
    response = GenerationConfigResponse.model_validate(
        {
            "success": True,
            "session_id": "11111111-1111-4111-8111-111111111111",
            "config_id": "22222222-2222-4222-8222-222222222222",
            "status": "configured",
            "config": {
                **request_payload(active_variation_modes=["NUMERICAL", "parameter_variation"]),
                "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
                "source_manifest": {"sources": []},
                "canonical_dimensions": ["values"],
                "mapping_version": "1.0",
            },
        }
    )
    assert isinstance(response.session_id, UUID)
    assert response.model_dump(mode="json") == {
        "success": True,
        "session_id": "11111111-1111-4111-8111-111111111111",
        "config_id": "22222222-2222-4222-8222-222222222222",
        "status": "configured",
        "config": {
            "n_versions": 2,
            "active_variation_modes": ["NUMERICAL", "parameter_variation"],
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": False},
            "source_manifest": {"sources": []},
            "canonical_dimensions": ["values"],
            "mapping_version": "1.0",
        },
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"success": False},
        {"session_id": "invalid"},
        {"config_id": "invalid"},
        {"status": "blueprinted"},
        {"config": None},
        {"extra": True},
    ],
)
def test_response_rejects_invalid_shape(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GenerationConfigResponse.model_validate(
            {
                "success": True,
                "session_id": "11111111-1111-4111-8111-111111111111",
                "config_id": "22222222-2222-4222-8222-222222222222",
                "status": "configured",
                "config": {
                    **request_payload(active_variation_modes=["NUMERICAL", "parameter_variation"]),
                    "ordering_preferences": {"shuffle_questions": False, "shuffle_options": False},
                    "source_manifest": {"sources": []},
                    "canonical_dimensions": ["values"],
                    "mapping_version": "1.0",
                },
                **overrides,
            }
        )

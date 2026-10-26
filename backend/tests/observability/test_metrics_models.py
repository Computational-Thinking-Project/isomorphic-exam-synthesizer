import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.models.runtime_metrics import (
    RuntimeMetricsResponse,
    RuntimeMetricsUnavailableDetail,
    RuntimeMetricsUnavailableResponse,
)

RESPONSE_FIELDS = (
    "status",
    "gemini_model",
    "uptime_seconds",
    "active_sse_connections",
    "gemini_call_count",
    "gemini_error_rate",
    "background_jobs_running",
    "process_memory_mb",
)
COUNT_FIELDS = ("active_sse_connections", "gemini_call_count", "background_jobs_running")
NUMBER_FIELDS = ("uptime_seconds", "gemini_error_rate", "process_memory_mb")


def snapshot(**overrides: object) -> dict[str, object]:
    return {
        "status": "operational",
        "gemini_model": "configured-model-id",
        "uptime_seconds": 125.5,
        "active_sse_connections": 2,
        "gemini_call_count": 12,
        "gemini_error_rate": 0.25,
        "background_jobs_running": 1,
        "process_memory_mb": 84.25,
        **overrides,
    }


def test_contract_example_round_trips_without_mutating_input() -> None:
    data = snapshot()
    original = deepcopy(data)
    response = RuntimeMetricsResponse.model_validate(data)
    assert response.model_dump(mode="json") == original
    assert json.loads(response.model_dump_json()) == original
    assert RuntimeMetricsResponse.model_validate_json(response.model_dump_json()) == response
    assert data == original


def test_explicit_zero_observations_are_valid() -> None:
    response = RuntimeMetricsResponse.model_validate(
        snapshot(**{field: 0 for field in (*COUNT_FIELDS, *NUMBER_FIELDS)})
    )
    assert response.gemini_call_count == 0
    assert response.gemini_error_rate == 0.0
    assert response.uptime_seconds == 0.0
    assert response.process_memory_mb == 0.0


@pytest.mark.parametrize("field", RESPONSE_FIELDS)
def test_missing_fields_never_default_to_zero_or_operational(field: str) -> None:
    data = snapshot()
    del data[field]
    with pytest.raises(ValidationError):
        RuntimeMetricsResponse.model_validate(data)


@pytest.mark.parametrize("field", COUNT_FIELDS)
@pytest.mark.parametrize("value", [-1, True, False, 1.0, 1.5, "1", None])
def test_counters_require_non_negative_strict_integers(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsResponse.model_validate(snapshot(**{field: value}))


@pytest.mark.parametrize("field", COUNT_FIELDS)
@pytest.mark.parametrize("value", [0, 1, 250])
def test_non_negative_counter_values_are_accepted(field: str, value: int) -> None:
    response = RuntimeMetricsResponse.model_validate(
        snapshot(**{field: value, "gemini_error_rate": 0.0})
    )
    assert getattr(response, field) == value
    assert type(getattr(response, field)) is int


@pytest.mark.parametrize("field", NUMBER_FIELDS)
@pytest.mark.parametrize(
    "value", [-0.1, float("nan"), float("inf"), float("-inf"), True, False, "0.5", None]
)
def test_measurements_require_non_negative_finite_numbers(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsResponse.model_validate(snapshot(**{field: value}))


@pytest.mark.parametrize("field", ["uptime_seconds", "process_memory_mb"])
@pytest.mark.parametrize("value", [0, 0.5, 1_000_000.0])
def test_elapsed_time_and_memory_are_not_artificially_capped(field: str, value: float) -> None:
    response = RuntimeMetricsResponse.model_validate(snapshot(**{field: value}))
    assert getattr(response, field) == value


@pytest.mark.parametrize("rate", [0, 0.25, 1])
def test_error_rate_is_a_fraction_including_both_boundaries(rate: float) -> None:
    response = RuntimeMetricsResponse.model_validate(snapshot(gemini_error_rate=rate))
    assert response.gemini_error_rate == rate


@pytest.mark.parametrize("rate", [1.0001, 25.0])
def test_error_rate_cannot_be_a_percentage_or_exceed_one(rate: float) -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsResponse.model_validate(snapshot(gemini_error_rate=rate))


def test_nonzero_error_rate_without_any_attempts_is_inconsistent() -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsResponse.model_validate(snapshot(gemini_call_count=0, gemini_error_rate=0.25))


@pytest.mark.parametrize("model_id", ["", "  ", "\n\t", None, 123, True])
def test_model_identifier_must_be_a_nonblank_string(model_id: object) -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsResponse.model_validate(snapshot(gemini_model=model_id))


@pytest.mark.parametrize("status", ["healthy", "configured", None, 1])
def test_success_status_is_operational(status: object) -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsResponse.model_validate(snapshot(status=status))


@pytest.mark.parametrize("field", ["access_token", "api_key", "session_id", "prompt"])
def test_unknown_response_fields_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsResponse.model_validate(snapshot(**{field: "fixture-only-value"}))


def test_validated_snapshot_cannot_be_mutated_into_invalid_data() -> None:
    response = RuntimeMetricsResponse.model_validate(snapshot())
    with pytest.raises(ValidationError):
        response.gemini_error_rate = float("nan")
    assert response.gemini_error_rate == 0.25


def test_unavailable_response_matches_the_safe_503_contract() -> None:
    response = RuntimeMetricsUnavailableResponse()
    expected = {
        "detail": {
            "code": "ERR_RUNTIME_METRICS_UNAVAILABLE",
            "message": "Runtime metrics are temporarily unavailable.",
        }
    }
    assert response.model_dump(mode="json") == expected
    assert json.loads(response.model_dump_json()) == expected
    assert RuntimeMetricsUnavailableResponse.model_validate(expected) == response


@pytest.mark.parametrize(
    "data",
    [
        {"code": "OTHER_ERROR"},
        {"message": "private provider error details"},
        {"code": None},
        {"message": None},
        {"raw_exception": "fixture-only-value"},
    ],
)
def test_unavailable_detail_rejects_unknown_codes_messages_and_fields(
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsUnavailableDetail.model_validate(data)


@pytest.mark.parametrize("detail", [None, "unavailable", [], {"extra": "unexpected"}])
def test_unavailable_envelope_rejects_invalid_detail(detail: object) -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsUnavailableResponse.model_validate({"detail": detail})


def test_unavailable_envelope_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RuntimeMetricsUnavailableResponse.model_validate({"status": "failed"})

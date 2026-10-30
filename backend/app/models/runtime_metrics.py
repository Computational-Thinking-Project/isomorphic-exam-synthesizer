"""Validated runtime snapshots; collection and HTTP access live outside these models."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NonNegativeCount = Annotated[int, Field(strict=True, ge=0)]
_NonNegativeMeasurement = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
_ErrorRate = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class RuntimeMetricsResponse(BaseModel):
    """All fields are required: a missing observation must never become a fake zero."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["operational"]
    gemini_model: Annotated[str, Field(strict=True, min_length=1)]
    uptime_seconds: _NonNegativeMeasurement
    active_sse_connections: _NonNegativeCount
    gemini_call_count: _NonNegativeCount
    gemini_error_rate: _ErrorRate
    background_jobs_running: _NonNegativeCount
    process_memory_mb: _NonNegativeMeasurement

    @field_validator("gemini_model")
    @classmethod
    def reject_blank_model_identifier(cls, model_id: str) -> str:
        if not model_id.strip():
            raise ValueError("The configured Gemini model identifier must not be blank.")
        return model_id

    @model_validator(mode="after")
    def require_attempts_for_nonzero_error_rate(self) -> Self:
        if self.gemini_call_count == 0 and self.gemini_error_rate != 0:
            raise ValueError("The error rate must be zero when no Gemini attempts have started.")
        return self


class RuntimeMetricsUnavailableDetail(BaseModel):
    """Fixed public error detail without internal collection/provider information."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Literal["ERR_RUNTIME_METRICS_UNAVAILABLE"] = "ERR_RUNTIME_METRICS_UNAVAILABLE"
    message: Literal["Runtime metrics are temporarily unavailable."] = (
        "Runtime metrics are temporarily unavailable."
    )


class RuntimeMetricsUnavailableResponse(BaseModel):
    """Body contract for the later route's HTTP 503 response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    detail: RuntimeMetricsUnavailableDetail = Field(default_factory=RuntimeMetricsUnavailableDetail)

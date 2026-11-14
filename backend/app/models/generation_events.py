"""W2 SSE wire contract; JSON is encoded before it enters an SSE frame."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

EventName = Literal["progress", "question_done", "warning", "error", "done"]
QuestionStatus = Literal["generating", "validating", "retrying", "done", "warning"]
SessionOutcome = Literal["generated", "partial_generated", "failed"]


class GenerationEventData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: AwareDatetime
    question_no: Annotated[int, Field(strict=True, ge=1)] | None = None
    version_index: Annotated[int, Field(strict=True, ge=1, le=4)] | None = None
    status: QuestionStatus
    percent_complete: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]
    retry_count: Annotated[int, Field(strict=True, ge=0)] = 0
    error_message: str | None = None
    error_code: str | None = None
    session_status: SessionOutcome | None = None
    completed_count: Annotated[int, Field(strict=True, ge=0, le=80)] | None = None
    total_count: Annotated[int, Field(strict=True, ge=1, le=80)] | None = None
    message: Annotated[str, Field(strict=True, min_length=1)] | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (self.completed_count is None) != (self.total_count is None):
            raise ValueError("Progress counts must be supplied together.")
        if self.completed_count is not None and self.total_count is not None:
            if self.completed_count > self.total_count:
                raise ValueError("Completed questions exceed the job total.")
        return self


class GenerationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[int, Field(strict=True, ge=1)]
    event: EventName
    data: GenerationEventData

    def to_sse(self) -> str:
        # EventSource exposes id/event natively. PR22 reads the inner payload
        # directly, so wrapping it in another {id,event,data} object hides fields.
        return f"id: {self.id}\nevent: {self.event}\ndata: {self.data.model_dump_json()}\n\n"

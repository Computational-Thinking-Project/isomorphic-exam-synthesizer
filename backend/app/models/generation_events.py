"""W2 SSE wire contract; JSON is encoded before it enters an SSE frame."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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


class GenerationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[int, Field(strict=True, ge=1)]
    event: EventName
    data: GenerationEventData

    def to_sse(self) -> str:
        # Keep the full W2 envelope in data; FE also gets native event/lastEventId.
        return f"id: {self.id}\nevent: {self.event}\ndata: {self.model_dump_json()}\n\n"

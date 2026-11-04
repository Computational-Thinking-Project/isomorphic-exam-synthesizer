"""Strict, durable lifecycle receipts; no authorization metadata is inferred."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

from app.models.schemas import ReviewDomainException

Count = Annotated[StrictInt, Field(ge=0)]
SessionState = Literal[
    "draft",
    "blueprinted",
    "configured",
    "generating",
    "partial_generated",
    "generated",
    "reviewed",
    "approved",
    "exported",
    "failed",
]


class ProgressCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_slots: Count
    current_slots: Count
    approved_slots: Count
    regenerating_slots: Count
    missing_slots: Count
    duplicate_slots: Count
    ready: StrictBool
    unapproved_question_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def consistent(self) -> "ProgressCounts":
        if self.approved_slots + self.regenerating_slots > self.current_slots:
            raise ValueError("Inconsistent candidate counts")
        if self.ready and not (
            self.expected_slots > 0
            and self.expected_slots == self.current_slots == self.approved_slots
            and self.regenerating_slots == self.missing_slots == self.duplicate_slots == 0
        ):
            raise ValueError("Inconsistent readiness")
        if self.unapproved_question_ids is not None:
            if len(set(self.unapproved_question_ids)) != len(self.unapproved_question_ids):
                raise ValueError("Duplicate unapproved IDs")
            if len(self.unapproved_question_ids) != self.current_slots - self.approved_slots:
                raise ValueError("Unapproved IDs do not match counts")
        return self


class ReservationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    session_status: SessionState
    replayed: StrictBool
    operation_id: UUID
    question_id: UUID
    expires_at: AwareDatetime
    max_attempts: Annotated[StrictInt, Field(ge=4, le=4)]
    snapshot: dict[str, Any]
    operation_status: Literal["active", "completed", "failed", "recovered"]
    settlement: dict[str, Any] | None = None

    @model_validator(mode="after")
    def consistent(self) -> "ReservationReceipt":
        if not self.replayed and self.operation_status != "active":
            raise ValueError("New reservation must be active")
        if self.operation_status != "active" and not self.settlement:
            raise ValueError("Settled replay requires its receipt")
        return self


class CompletionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    session_status: SessionState
    replayed: StrictBool
    operation_id: UUID
    previous_question_id: UUID
    question_id: UUID
    api_calls_used: Annotated[StrictInt, Field(ge=0, le=4)]
    invalidated_version_ids: list[UUID]
    progress: ProgressCounts


class ActionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    session_status: SessionState
    replayed: StrictBool
    previous_question_id: UUID
    question_id: UUID
    question_status: Literal["approved"]
    invalidated_version_ids: list[UUID]
    progress: ProgressCounts


class ProgressReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    session_status: SessionState
    replayed: StrictBool
    progress: ProgressCounts


def reservation_receipt(
    value: Any, session_id: str, question_id: str, operation_id: UUID
) -> ReservationReceipt:
    try:
        result = ReservationReceipt.model_validate(rpc_object(value))
        if (result.session_id, result.question_id, result.operation_id) != (
            UUID(session_id),
            UUID(question_id),
            operation_id,
        ):
            raise ValueError("Reservation identity mismatch")
        if result.operation_status == "completed":
            completion_receipt(result.settlement, session_id, question_id, operation_id)
        elif result.operation_status in ("failed", "recovered"):
            settled = settlement_receipt(result.settlement, session_id, question_id, operation_id)
            if settled.operation_status != result.operation_status:
                raise ValueError("Reservation settlement status mismatch")
        return result
    except (ValueError, TypeError) as exc:
        raise ReviewDomainException(
            503,
            "ERR_INVALID_RESERVATION",
            "Reservation could not be confirmed; retry with the same key",
        ) from exc


def completion_receipt(
    value: Any, session_id: str, question_id: str, operation_id: UUID
) -> CompletionReceipt:
    try:
        result = CompletionReceipt.model_validate(rpc_object(value))
        if (result.session_id, result.previous_question_id, result.operation_id) != (
            UUID(session_id),
            UUID(question_id),
            operation_id,
        ):
            raise ValueError("Completion identity mismatch")
        if result.question_id == result.previous_question_id:
            raise ValueError("Replacement must have a new identity")
        return result
    except (ValueError, TypeError) as exc:
        raise ReviewDomainException(
            503,
            "ERR_COMPLETION_UNCERTAIN",
            "Completion could not be confirmed; retry with the same key",
        ) from exc


class SettlementReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    session_status: SessionState
    operation_id: UUID
    question_id: UUID
    operation_status: Literal["failed", "recovered", "completed", "active"]
    replayed: StrictBool
    recovered: StrictBool
    api_calls_used: Annotated[StrictInt, Field(ge=0, le=4)]
    progress: ProgressCounts


class RecoveryReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    session_status: SessionState
    recovered_count: Annotated[StrictInt, Field(ge=0, le=1)]
    recoveries: list[SettlementReceipt]

    @model_validator(mode="after")
    def consistent(self) -> "RecoveryReceipt":
        if len(self.recoveries) != self.recovered_count:
            raise ValueError("Recovery count mismatch")
        for result in self.recoveries:
            if (
                result.session_id != self.session_id
                or result.operation_status != "recovered"
                or result.recovered is not True
                or result.replayed is not False
            ):
                raise ValueError("Recovery settlement mismatch")
        return self


def rpc_object(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict):
        raise ReviewDomainException(503, "ERR_INVALID_RPC_RESPONSE", "Invalid database response")
    return value


def settlement_receipt(
    value: Any, session_id: str, question_id: str, operation_id: UUID
) -> SettlementReceipt:
    try:
        result = SettlementReceipt.model_validate(rpc_object(value))
        if (result.session_id, result.question_id, result.operation_id) != (
            UUID(session_id),
            UUID(question_id),
            operation_id,
        ):
            raise ValueError("Receipt identity mismatch")
        if result.operation_status not in ("failed", "recovered"):
            raise ValueError("Operation has not been failure-settled")
        if result.recovered != (result.operation_status == "recovered"):
            raise ValueError("Recovery status mismatch")
        return result
    except (ValueError, TypeError) as exc:
        raise ReviewDomainException(
            503, "ERR_SETTLEMENT_UNCERTAIN", "Operation settlement could not be confirmed"
        ) from exc

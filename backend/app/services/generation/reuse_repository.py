"""EXT-02 Step 7 core: call reuse_session_source (migration 028c) with the caller's client.

The Bank HTTP route (``/api/exam-bank/{bank_item_id}/reuse`` in ``exam_bank_reuse.py``) is not
wired yet: it waits for EXT-04 to provide the bank item lookup and ``_bank_capacity_check``.
"""

from typing import Literal, Protocol
from uuid import UUID

from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.generation_config import GenerationMode


class ReuseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_session_id: UUID
    source_type: Literal["original", "version"]
    source_version_id: UUID | None = None
    generation_mode: GenerationMode
    idempotency_key: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _version_id_matches_type(self) -> "ReuseRequest":
        if (self.source_type == "version") != (self.source_version_id is not None):
            raise ValueError("source_version_id is required exactly for source_type 'version'")
        return self


class ReuseSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["original", "version"]
    source_session_id: UUID
    source_version_id: UUID | None
    new_source_order: list[int]


class ReuseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: Literal[True]
    replayed: bool
    session_id: UUID
    status: Literal["draft"]
    next_step: Literal["confirm_source", "analysis", "stage2_config"]
    generation_mode: GenerationMode
    question_count: int = Field(ge=1, le=20)
    source: ReuseSource


class ReuseError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class _RpcClient(Protocol):
    def rpc(self, fn: str, params: dict[str, object]) -> object: ...


_BUSINESS_ERRORS: tuple[tuple[str, int, str], ...] = (
    ("ERR_IDEMPOTENCY_CONFLICT", 409, "The idempotency key was used with a different request."),
    ("ERR_SOURCE_NOT_APPROVED", 409, "Only an approved round can be reused."),
    ("ERR_SOURCE_NOT_READY", 422, "The source must have 1-20 questions."),
    ("ERR_REUSE_INVALID", 422, "Invalid reuse request."),
)


def _error(exc: APIError) -> ReuseError:
    code = str(getattr(exc, "code", "") or "").upper()
    message = str(getattr(exc, "message", "") or "")
    if code == "P0002":
        return ReuseError(404, "ERR_NOT_FOUND", "Session or version not found.")
    if code == "42501":
        return ReuseError(403, "ERR_FORBIDDEN", "Access denied.")
    for prefix, status_code, text in _BUSINESS_ERRORS:
        if message.startswith(prefix):
            return ReuseError(status_code, prefix, text)
    return ReuseError(500, "ERR_REUSE_STORAGE_FAILURE", "Reuse could not be processed.")


def reuse_source(db: _RpcClient, request: ReuseRequest) -> ReuseResult:
    """Create (or replay) the draft session for a reuse request; the RPC owns the transaction."""
    params: dict[str, object] = {
        "p_source_session_id": str(request.source_session_id),
        "p_source_type": request.source_type,
        "p_source_version_id": str(request.source_version_id) if request.source_version_id else None,
        "p_generation_mode": request.generation_mode,
        "p_idempotency_key": request.idempotency_key,
    }
    try:
        data = db.rpc("reuse_session_source", params).execute().data  # type: ignore[attr-defined]
    except APIError as exc:
        raise _error(exc) from exc
    try:
        result = ReuseResult.model_validate(data)
    except ValueError as exc:
        raise ReuseError(500, "ERR_REUSE_STORAGE_FAILURE", "Reuse could not be processed.") from exc
    if (
        result.source.source_session_id != request.source_session_id
        or result.source.source_type != request.source_type
        or result.source.source_version_id != request.source_version_id
        or result.generation_mode != request.generation_mode
        or len(result.source.new_source_order) != result.question_count
    ):
        raise ReuseError(500, "ERR_REUSE_STORAGE_FAILURE", "Reuse receipt does not match the request.")
    return result

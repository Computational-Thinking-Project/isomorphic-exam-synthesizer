"""Python integration contracts, not invented SQL/RPC names or fake persistence."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, field_validator

from app.models.generation_events import SessionOutcome


class GenerationJobError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class GenerationQuotaExceeded(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QuestionTarget:
    source_question_id: UUID
    question_no: int
    version_index: int


@dataclass(frozen=True, slots=True)
class GenerationPlan:
    session_id: UUID
    job_id: UUID
    targets: tuple[QuestionTarget, ...]
    saved: frozenset[QuestionTarget]
    gemini_call_count: int
    # Immutable adapter-owned source/Blueprint/config snapshot. Never serialized.
    inputs: object

    def __post_init__(self) -> None:
        if type(self.targets) is not tuple or type(self.saved) is not frozenset:
            raise ValueError("Job targets and saved identities must be immutable collections.")
        if any(not isinstance(target, QuestionTarget) for target in self.targets):
            raise ValueError("Expected typed question targets.")
        if not isinstance(self.session_id, UUID) or not isinstance(self.job_id, UUID):
            raise ValueError("Job identities must be UUIDs.")
        if (
            not self.targets
            or len(self.targets) > 80
            or len(set(self.targets)) != len(self.targets)
        ):
            raise ValueError("Expected unique generation targets.")
        sources: dict[UUID, int] = {}
        versions: set[int] = set()
        for target in self.targets:
            if (
                not isinstance(target.source_question_id, UUID)
                or type(target.question_no) is not int
                or target.question_no < 1
            ):
                raise ValueError("Invalid source target.")
            if type(target.version_index) is not int or not 1 <= target.version_index <= 4:
                raise ValueError("Invalid version index.")
            if (
                target.source_question_id in sources
                and sources[target.source_question_id] != target.question_no
            ):
                raise ValueError("Source numbering changed across versions.")
            sources[target.source_question_id] = target.question_no
            versions.add(target.version_index)
        if not 1 <= len(sources) <= 20 or len(set(sources.values())) != len(sources):
            raise ValueError("Expected 1–20 uniquely numbered sources.")
        if versions != set(range(1, max(versions) + 1)) or len(self.targets) != len(sources) * len(
            versions
        ):
            raise ValueError("Expected every source in every version.")
        if not self.saved <= frozenset(self.targets):
            raise ValueError("Saved targets are outside this job.")
        if type(self.gemini_call_count) is not int or not 0 <= self.gemini_call_count <= 250:
            raise ValueError("Invalid durable Gemini quota count.")


class GeneratedDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: Annotated[str, Field(strict=True, min_length=1)]
    options: dict[str, str]
    correct_key: Literal["A", "B", "C", "D"]
    solution_md: Annotated[str, Field(strict=True, min_length=1)]
    has_warning: StrictBool = False
    retry_count: Annotated[int, Field(strict=True, ge=0)] = 0
    validation_report: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("content", "solution_md")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Draft text must not be blank.")
        return value

    @field_validator("options")
    @classmethod
    def complete_options(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != set("ABCD") or any(not option.strip() for option in value.values()):
            raise ValueError("Exactly four nonblank options are required.")
        return value


class GenerationJobStore(Protocol):
    """All calls must be asynchronous/nonblocking and enforce trusted ownership.

    claim atomically locks/revalidates config+confirmed inputs and transitions to
    generating, returning committed targets for incremental retry. Reject active
    jobs with 409. Use job_id as a fencing token on every later mutation.

    reserve_gemini_call atomically increments the EXISTING durable session count
    only below 250 (including Blueprint usage), otherwise raises quota exceeded.
    No retry reset. It returns the committed new count; never a read/modify/write.

    save_draft preserves existing current rows and atomically commits one new
    version_question plus updated_at. finish verifies durable completeness and
    commits the requested state only for this job. Errors must have stable codes.
    fail_stale must compare generating + updated_at < cutoff atomically and fence
    the former worker; set failed/ERR_GENERATION_INTERRUPTED. No SQL is defined here.
    """

    async def claim(self, session_id: UUID, *, retry: bool) -> GenerationPlan: ...
    async def reserve_gemini_call(self, plan: GenerationPlan) -> int: ...
    async def save_draft(
        self, plan: GenerationPlan, target: QuestionTarget, draft: GeneratedDraft
    ) -> None: ...
    async def finish(
        self, plan: GenerationPlan, outcome: SessionOutcome, *, error_code: str | None
    ) -> None: ...
    async def fail_stale(self, session_id: UUID, *, cutoff: datetime) -> bool: ...

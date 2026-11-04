"""TASK-304 handoff, independent of review persistence models."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.generation import AnswerKey
from app.services.blueprint.adapters import normalized_text
from app.services.validator.base import CheckResult


class TargetedValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    math_verified: bool = False
    requires_teacher_review: Literal[True] = True
    warnings: list[str] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)


class RegeneratedVariantResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stem_latex: str = Field(min_length=1, max_length=12000)
    options: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(min_length=4, max_length=4)
    correct_key: AnswerKey
    solution_md: str = Field(min_length=1)
    validation_report: TargetedValidationReport
    api_calls_count: int = Field(ge=0, le=4)

    @field_validator("options")
    @classmethod
    def unique_options(cls, value: list[str]) -> list[str]:
        if len({normalized_text(option) for option in value}) != 4:
            raise ValueError("Options must have distinct content")
        return value

    def to_review_payload(self) -> dict[str, Any]:
        """PR #28 persists content, while the AI contract names it stem_latex."""
        return {**self.model_dump(), "content": self.stem_latex}

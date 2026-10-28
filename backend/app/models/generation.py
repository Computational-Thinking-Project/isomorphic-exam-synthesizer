"""Contracts for the async Blueprint pipeline; legacy schemas remain compatible."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas import GeneratedVariant
from app.services.validator.base import CheckResult

AnswerKey = Literal["A", "B", "C", "D"]


class SolutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    explanation: str = Field(min_length=1, max_length=6000)
    latex: str | None = Field(default=None, max_length=4000)


class StepByStepSolution(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correct_key: AnswerKey
    final_answer: str = Field(
        min_length=1, max_length=4000,
        description="Copy the selected option text exactly; do not return only its A/B/C/D label.",
    )
    steps: list[SolutionStep] = Field(min_length=1, max_length=20)


class CandidatePayload(BaseModel):
    """Only model-owned content is requested from Gemini."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_text: str = Field(min_length=1, max_length=12000)
    options: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(
        min_length=4, max_length=4,
        description="Four nonempty option strings in A, B, C, D order, without label prefixes. Natural language and LaTeX are allowed.",
    )
    correct_key: AnswerKey = Field(description="A maps to options[0], B to options[1], C to options[2], D to options[3].")
    solution: StepByStepSolution


def render_solution(solution: StepByStepSolution) -> str:
    paragraphs = []
    for index, step in enumerate(solution.steps, 1):
        text = f"{index}. {step.explanation}"
        if step.latex:
            text += f"\n\n   $${step.latex}$$"
        paragraphs.append(text)
    paragraphs.append(f"Đáp án {solution.correct_key}: {solution.final_answer}")
    return "\n\n".join(paragraphs)


class ValidationReport(BaseModel):
    checks: list[CheckResult] = Field(default_factory=list)
    requires_teacher_review: bool = True

    @property
    def failures(self) -> list[CheckResult]:
        unknown = {"unknown", "unsupported", "inconclusive", "timeout"}
        return [check for check in self.checks if not check.passed and check.status not in unknown]

    @property
    def has_warning(self) -> bool:
        return any(not check.passed for check in self.checks)


class GeneratedQuestion(CandidatePayload):
    variant_id: str
    source_question_id: str
    blueprint_fingerprint: str
    seed: int
    solution_md: str
    has_warning: bool
    requires_teacher_review: bool = True

    def to_legacy(self) -> GeneratedVariant:
        return GeneratedVariant(
            variant_id=self.variant_id,
            source_question_id=self.source_question_id,
            question_text=self.question_text,
            options=self.options,
            correct_answer=self.options["ABCD".index(self.correct_key)],
            solution_steps=self.solution_md,
            seed=self.seed,
        )


class QuestionResult(BaseModel):
    version_index: int = Field(ge=1, le=4)
    source_question_id: str
    request_fingerprint: str
    candidate: GeneratedQuestion | None = None
    validation: ValidationReport | None = None
    error_code: str | None = None
    attempts: int = 0


class BatchResult(BaseModel):
    results: list[QuestionResult]
    status: Literal["generated", "partial_generated", "failed"]

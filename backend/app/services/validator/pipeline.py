"""Async adapters for existing checkers; unsupported math never becomes a pass."""

import asyncio
import time
from typing import Any

from app.models.generation import CandidatePayload, ValidationReport, render_solution
from app.services.blueprint.adapters import normalized_text

from .aggregator import validate_question
from .base import CheckResult
from .syntax_checker import check_latex_delimiters


def validate_solution(candidate: CandidatePayload) -> list[CheckResult]:
    solution = candidate.solution
    key_matches = solution.correct_key == candidate.correct_key
    answer_matches = normalized_text(solution.final_answer) == normalized_text(
        candidate.options["ABCD".index(candidate.correct_key)]
    )
    latex = check_latex_delimiters(render_solution(solution), "solution")
    latex.check_name = "solution_latex"
    return [
        CheckResult(
            check_name="solution_consistency",
            passed=key_matches and answer_matches,
            status="verified" if key_matches and answer_matches else "failed",
            detail="Solution key and final_answer must match the designated option content.",
        ),
        latex,
        CheckResult(
            check_name="solution_reasoning",
            passed=False,
            status="unknown",
            detail="Free-form reasoning steps require teacher review.",
        ),
    ]


class CandidateValidator:
    def __init__(self, timeout: float = 5):
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(3)

    async def validate(
        self,
        candidate: CandidatePayload,
        *,
        deadline: float,
        blueprint: dict[str, Any] | None = None,
    ) -> ValidationReport:
        async with asyncio.timeout_at(deadline):
            async with self._semaphore:
                remaining = min(self.timeout, deadline - time.monotonic())
                if remaining <= 0:
                    raise TimeoutError
                solution_checks = validate_solution(candidate)
                aggregate = await asyncio.to_thread(
                    validate_question,
                    candidate.question_text,
                    candidate.options,
                    candidate.correct_key,
                    blueprint=blueprint,
                    parameters=None,
                    timeout=remaining,
                    treat_fallback_as_warning=True,
                )
                checks = [
                    check.model_copy(update={"check_name": "answer_verified"})
                    if check.check_name == "sympy_evaluator"
                    else check
                    for check in aggregate.checks
                ]
                if not aggregate.passed and not any(
                    not check.passed
                    and check.status not in {"unknown", "unsupported", "inconclusive", "timeout"}
                    for check in checks
                ):
                    checks.append(
                        CheckResult(
                            check_name="validation_aggregate",
                            passed=False,
                            status="failed",
                            detail="The four-tier validator rejected this candidate.",
                        )
                    )
                if aggregate.confidence == "rule_only" and not aggregate.errors:
                    checks.append(
                        CheckResult(
                            check_name="validation_confidence",
                            passed=False,
                            status="unknown",
                            detail="Rule-only validation requires teacher review.",
                        )
                    )
                if blueprint is not None:
                    checks.append(
                        CheckResult(
                            check_name="parameter_coverage",
                            passed=False,
                            status="unknown",
                            detail="Candidate payload has no explicit parameter values for domain coverage.",
                        )
                    )
                checks.append(
                    CheckResult(
                        check_name="blueprint_equivalence",
                        passed=False,
                        status="unknown",
                        detail="Pedagogical equivalence requires teacher review.",
                    )
                )
                return ValidationReport(checks=[*checks, *solution_checks])

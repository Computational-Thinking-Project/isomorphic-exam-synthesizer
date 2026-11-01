"""Async adapters for existing checkers; unsupported math never becomes a pass."""

import asyncio
import time

from app.models.generation import CandidatePayload, ValidationReport, render_solution
from app.services.blueprint.adapters import normalized_text

from .base import CheckResult
from .logic_checker import check_logic
from .process_runner import run_with_timeout
from .sympy_evaluator import verify_question_math
from .syntax_checker import check_latex_delimiters, check_syntax


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


def _bounded_logic(candidate: CandidatePayload, timeout: float) -> CheckResult:
    result = run_with_timeout(
        check_logic, args=(candidate.options, candidate.correct_key), timeout=timeout
    )
    if result.success and isinstance(result.data, CheckResult):
        return result.data
    return CheckResult(
        check_name="logic_valid",
        passed=False,
        status="timeout" if result.timed_out else "unknown",
        detail="Option checker could not finish; no proof of validity is available.",
    )


class CandidateValidator:
    def __init__(self, timeout: float = 5):
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(3)

    async def validate(self, candidate: CandidatePayload, *, deadline: float) -> ValidationReport:
        async with asyncio.timeout_at(deadline):
            async with self._semaphore:
                remaining = min(self.timeout, deadline - time.monotonic())
                if remaining <= 0:
                    raise TimeoutError
                syntax = check_syntax(candidate.question_text, candidate.options)
                solution_checks = validate_solution(candidate)
                # Do not spend CAS work on structurally malformed content.
                if not syntax.passed:
                    return ValidationReport(checks=[syntax, *solution_checks])
                option_answer = candidate.options["ABCD".index(candidate.correct_key)]
                logic, math = await asyncio.gather(
                    asyncio.to_thread(_bounded_logic, candidate, remaining),
                    asyncio.to_thread(
                        verify_question_math, candidate.question_text, option_answer, remaining
                    ),
                )
                return ValidationReport(
                    checks=[
                        syntax,
                        logic,
                        math.to_check_result(),
                        *solution_checks,
                        CheckResult(
                            check_name="blueprint_equivalence",
                            passed=False,
                            status="unknown",
                            detail="General Blueprint constraints and pedagogical equivalence need teacher review.",
                        ),
                    ]
                )

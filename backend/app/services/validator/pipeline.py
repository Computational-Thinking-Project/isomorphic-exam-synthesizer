"""Async adapters for existing checkers; unsupported math never becomes a pass."""

import asyncio
import threading
from typing import Any

from app.models.generation import CandidatePayload, ValidationReport, render_solution
from app.services.blueprint.adapters import normalized_text

from .aggregator import validate_question
from .base import CheckResult
from .base import ValidationReport as AggregateReport
from .process_runner import ProcessResult, run_with_timeout
from .sympy_evaluator import validator_process_context
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


def _validate_four_tiers(
    question_text: str,
    options: list[str],
    correct_key: str,
    blueprint: dict[str, Any] | None,
    timeout: float,
) -> AggregateReport:
    """Run all four tiers inside one reclaimable process, including CAS."""
    with validator_process_context():
        return validate_question(
            question_text,
            options,
            correct_key,
            blueprint=blueprint,
            parameters=None,
            timeout=timeout,
            treat_fallback_as_warning=True,
        )


class CandidateValidator:
    # `timeout` was the CAS budget before F02. Allow bounded startup and the
    # other three tiers to finish without silently extending CAS's own limit.
    _OVERALL_OVERHEAD_SECONDS = 5.0

    def __init__(self, timeout: float = 5):
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(3)
        self._workers: set[asyncio.Task[ProcessResult]] = set()
        self._cancel_signals: dict[asyncio.Task[ProcessResult], threading.Event] = {}
        self._closing = False

    def _worker_done(self, worker: asyncio.Task[ProcessResult]) -> None:
        self._workers.discard(worker)
        self._cancel_signals.pop(worker, None)
        self._semaphore.release()
        # A second cancellation can detach the caller; retrieve its exception.
        if not worker.cancelled():
            worker.exception()

    async def aclose(self, timeout_seconds: float = 10) -> bool:
        """Stop outstanding calculations before app shutdown closes its runtime."""
        self._closing = True
        for signal in tuple(self._cancel_signals.values()):
            signal.set()
        if not self._workers:
            return True
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(asyncio.shield(worker) for worker in tuple(self._workers)),
                    return_exceptions=True,
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return False
        return True

    async def validate(
        self,
        candidate: CandidatePayload,
        *,
        deadline: float,
        blueprint: dict[str, Any] | None = None,
    ) -> ValidationReport:
        if self._closing:
            raise RuntimeError("Validator is shutting down.")
        async with asyncio.timeout_at(deadline):
            await self._semaphore.acquire()
            worker: asyncio.Task[ProcessResult] | None = None
            try:
                if self._closing:
                    raise RuntimeError("Validator is shutting down.")
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError
                cas_timeout = min(self.timeout, remaining)
                process_timeout = min(self.timeout + self._OVERALL_OVERHEAD_SECONDS, remaining)
                solution_checks = validate_solution(candidate)
                cancel_signal = threading.Event()
                worker = asyncio.create_task(
                    asyncio.to_thread(
                        run_with_timeout,
                        _validate_four_tiers,
                        args=(
                            candidate.question_text,
                            candidate.options,
                            candidate.correct_key,
                            blueprint,
                            cas_timeout,
                        ),
                        timeout=process_timeout,
                        start_method="spawn",
                        cancel_signal=cancel_signal,
                    )
                )
                self._workers.add(worker)
                self._cancel_signals[worker] = cancel_signal
                worker.add_done_callback(self._worker_done)
                try:
                    result = await asyncio.shield(worker)
                except BaseException:
                    cancel_signal.set()
                    # Keep the real slot occupied until process termination. A
                    # second cancellation may detach this await, but the done
                    # callback still owns and releases the slot exactly once.
                    try:
                        await asyncio.shield(worker)
                    except BaseException:
                        pass
                    raise
                if result.timed_out:
                    raise TimeoutError("Four-tier validation exceeded its deadline.")
                if not result.success or not isinstance(result.data, AggregateReport):
                    raise RuntimeError("Four-tier validation worker failed.")
                aggregate = result.data
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
            finally:
                if worker is None:
                    self._semaphore.release()

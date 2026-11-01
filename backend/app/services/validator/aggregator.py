"""
Validation Aggregator (VAL-05 / TASK-107d).

Coordinates multi-tier validation pipeline and produces a consolidated
ValidationReport:
1. Syntax Validation (VAL-01): Non-empty stem, exactly 4 options, balanced LaTeX delimiters.
2. Logic & Choice Integrity (VAL-02): Designated correct answer, no duplicate options.
3. Formal Mathematical CAS Verification (VAL-03): SymPy equation evaluation with 5s hard timeout.
4. Deterministic Rule-Based Fallback (VAL-04): Parameter bounds, math invariants, distractor sanity.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.validator.base import CheckResult, ValidationReport
from app.services.validator.logic_checker import (
    _resolve_option_letter,
    are_expressions_equivalent,
    check_designated_answer,
    check_duplicate_options,
    normalize_latex_string,
)
from app.services.validator.rule_checker import (
    check_distractor_reasonableness,
    check_mathematical_invariants,
    check_parameter_bounds,
    detect_out_of_scope_math,
    evaluate_rule_fallback,
)
from app.services.validator.sympy_evaluator import (
    DEFAULT_EVALUATION_TIMEOUT,
    EvaluationResult,
    EvaluationStatus,
    verify_question_math,
)
from app.services.validator.syntax_checker import (
    check_four_options,
    check_latex_delimiters,
    check_question_not_empty,
)

logger = logging.getLogger(__name__)


def validate_question(
    question_text: str,
    options: Sequence[str],
    correct_answer: str,
    blueprint: Optional[Dict[str, Any]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_EVALUATION_TIMEOUT,
    fail_fast: bool = False,
    treat_fallback_as_warning: bool = False,
) -> ValidationReport:
    """
    Coordinate the 4-tier validation pipeline for a multiple-choice question.

    Pipeline Stages:
    1. Syntax (VAL-01): question stem not empty, exactly 4 options, balanced LaTeX delimiters.
    2. Logic (VAL-02): designated answer present in options, options mathematically non-duplicate.
    3. Formal CAS (VAL-03): SymPy algebraic solution verification (bypassed if out-of-scope math).
    4. Rule Fallback & Invariants (VAL-04): parameter bounds, invariants (denominators, roots, logs,
       probabilities, geometry), and distractor reasonableness.

    Args:
        question_text: The question stem containing LaTeX expressions.
        options: Exactly 4 multiple-choice options.
        correct_answer: Designated correct answer (by option letter or text content).
        blueprint: Optional Blueprint dict specifying parameter domains and variation policies.
        parameters: Optional dict of parameter values used in question generation.
        timeout: Maximum duration in seconds for CAS evaluation (default: 5.0).
        fail_fast: If True, aborts immediately upon encountering errors in syntax or logic.
        treat_fallback_as_warning: If True and only rule-based fallback succeeds, reports status='warning'.

    Returns:
        ValidationReport containing overall status, confidence, checks, errors, and warnings.
    """
    start_time = time.perf_counter()

    checks: List[CheckResult] = []
    errors: List[str] = []
    warnings: List[str] = []

    # -------------------------------------------------------------------------
    # STAGE 1: Syntax Validation (VAL-01)
    # -------------------------------------------------------------------------
    res_stem = check_question_not_empty(question_text)
    checks.append(res_stem)
    if not res_stem.passed:
        errors.extend(res_stem.errors)

    res_four = check_four_options(options)
    checks.append(res_four)
    if not res_four.passed:
        errors.extend(res_four.errors)

    res_stem_delim = check_latex_delimiters(question_text or "", field_name="question_text")
    checks.append(res_stem_delim)
    if not res_stem_delim.passed:
        errors.extend(res_stem_delim.errors)

    if options:
        for idx, opt in enumerate(options):
            if opt and str(opt).strip():
                res_opt_delim = check_latex_delimiters(str(opt), field_name=f"option_{idx + 1}")
                if not res_opt_delim.passed:
                    checks.append(res_opt_delim)
                    errors.extend(res_opt_delim.errors)

    if fail_fast and errors:
        exec_ms = (time.perf_counter() - start_time) * 1000.0
        return ValidationReport(
            passed=False,
            status="failed",
            confidence="rule_only",
            checks=checks,
            errors=_dedup_list(errors),
            warnings=warnings,
            execution_time_ms=exec_ms,
        )

    # -------------------------------------------------------------------------
    # STAGE 2: Logic Validation (VAL-02)
    # -------------------------------------------------------------------------
    res_ans = check_designated_answer(correct_answer=correct_answer, options=options)
    checks.append(res_ans)
    if not res_ans.passed:
        errors.extend(res_ans.errors)

    res_dup = check_duplicate_options(options)
    checks.append(res_dup)
    if not res_dup.passed:
        errors.extend(res_dup.errors)

    if fail_fast and errors:
        exec_ms = (time.perf_counter() - start_time) * 1000.0
        return ValidationReport(
            passed=False,
            status="failed",
            confidence="rule_only",
            checks=checks,
            errors=_dedup_list(errors),
            warnings=warnings,
            execution_time_ms=exec_ms,
        )

    # -------------------------------------------------------------------------
    # STAGE 3: Formal Mathematical CAS Verification (VAL-03)
    # -------------------------------------------------------------------------
    is_oos, oos_category = detect_out_of_scope_math(question_text or "")
    sympy_res: Optional[EvaluationResult] = None
    uniqueness_inconclusive: bool = False

    # Resolve correct answer text content if designated by label letter (supports 'A', 'A.', 'Option A', '(A)', etc.)
    resolved_answer = correct_answer
    if correct_answer and options and len(options) == 4:
        letter_res = _resolve_option_letter(correct_answer, options)
        if letter_res is not None and letter_res[1] and str(letter_res[1]).strip():
            resolved_answer = str(letter_res[1]).strip()

    if is_oos:
        # Route directly to rule fallback to prevent process pool timeout/crash on non-CAS domains
        sympy_res = EvaluationResult(
            status=EvaluationStatus.UNSUPPORTED,
            passed=False,
            confidence="rule_only",
            detail=(
                f"Question domain '{oos_category}' is out-of-scope for single-equation CAS. "
                "Routed directly to Rule Fallback Checker."
            ),
        )
        warnings.append(
            f"Out-of-scope math domain '{oos_category}' detected; bypassed CAS evaluation."
        )
        checks.append(
            CheckResult(
                check_name="sympy_evaluator",
                passed=False,
                status="unsupported",
                confidence="rule_only",
                detail=sympy_res.detail,
            )
        )
    else:
        # Attempt SymPy formal algebraic verification within isolated process
        try:
            sympy_res = verify_question_math(
                question_text=question_text or "",
                correct_answer=resolved_answer or "",
                timeout=timeout,
            )
            raw_status_val = (
                sympy_res.status.value
                if hasattr(sympy_res.status, "value")
                else str(sympy_res.status)
            )
            sympy_check = CheckResult(
                check_name="sympy_evaluator",
                passed=sympy_res.passed,
                status=raw_status_val,
                confidence=sympy_res.confidence,
                detail=sympy_res.detail,
                errors=[]
                if sympy_res.passed
                else (
                    [sympy_res.detail]
                    if (
                        sympy_res.status in (EvaluationStatus.FAILED, EvaluationStatus.DOMAIN_ERROR)
                        and sympy_res.detail
                    )
                    else []
                ),
            )
            checks.append(sympy_check)
            if not sympy_res.passed and sympy_res.status in (
                EvaluationStatus.FAILED,
                EvaluationStatus.DOMAIN_ERROR,
            ):
                detail_err = (
                    sympy_res.detail
                    or f"SymPy CAS evaluation rejected candidate answer ({raw_status_val})."
                )
                errors.append(f"SymPy CAS verification failed: {detail_err}")

            if sympy_res.status == EvaluationStatus.TIMEOUT:
                warnings.append(
                    f"SymPy evaluation timed out after {timeout:.1f}s; routed to rule-based fallback."
                )
            elif sympy_res.status == EvaluationStatus.UNSUPPORTED:
                warnings.append(
                    "SymPy evaluator unsupported question structure; routed to rule-based fallback."
                )

            # Uniqueness verification: If the candidate answer is verified by CAS, ensure
            # that no other option in the multiple-choice set also satisfies the equation.
            if sympy_res.passed and sympy_res.status == EvaluationStatus.VERIFIED and options:
                designated_idx = -1
                if correct_answer and str(correct_answer).strip().upper() in ("A", "B", "C", "D"):
                    letter_idx = ord(str(correct_answer).strip().upper()) - ord("A")
                    if 0 <= letter_idx < len(options):
                        designated_idx = letter_idx
                if designated_idx == -1 and resolved_answer:
                    for i, opt in enumerate(options):
                        if opt is not None and (
                            normalize_latex_string(str(opt).strip())
                            == normalize_latex_string(resolved_answer.strip())
                            or are_expressions_equivalent(str(opt).strip(), resolved_answer.strip())
                        ):
                            designated_idx = i
                            break

                multiple_solutions_found: List[Tuple[str, str]] = []
                for i, opt in enumerate(options):
                    if i == designated_idx:
                        continue
                    if not opt or not str(opt).strip():
                        continue
                    try:
                        dist_res = verify_question_math(
                            question_text=question_text or "",
                            correct_answer=str(opt).strip(),
                            timeout=timeout,
                        )
                        if dist_res.passed and dist_res.status == EvaluationStatus.VERIFIED:
                            opt_label = chr(ord("A") + i) if i < 26 else str(i + 1)
                            multiple_solutions_found.append((opt_label, str(opt).strip()))
                            # Record definitive failure immediately so subsequent worker errors cannot erase it
                            des_label = (
                                f"Option {chr(ord('A') + designated_idx)}"
                                if 0 <= designated_idx < 26
                                else f"designated answer '{resolved_answer}'"
                            )
                            err_msg = (
                                f"Multiple options satisfy the equation: both {des_label} ('{resolved_answer}') "
                                f"and Option {opt_label} ('{str(opt).strip()}') are valid solutions."
                            )
                            errors.append(f"SymPy CAS verification failed: {err_msg}")
                            sympy_res.passed = False
                            sympy_res.status = EvaluationStatus.FAILED
                            sympy_res.detail = err_msg
                            sympy_check.passed = False
                            sympy_check.status = "failed"
                            sympy_check.detail = err_msg
                            sympy_check.errors.append(err_msg)
                        elif dist_res.status in (
                            EvaluationStatus.TIMEOUT,
                            EvaluationStatus.UNSUPPORTED,
                        ):
                            uniqueness_inconclusive = True
                            warnings.append(
                                f"Option {chr(ord('A') + i)} ('{str(opt).strip()}') uniqueness could not be definitively verified by CAS ({dist_res.status.value})."
                            )
                    except Exception as dist_exc:
                        logger.warning(
                            "Worker error during distractor evaluation for option %s: %s",
                            i,
                            dist_exc,
                        )
                        uniqueness_inconclusive = True
                        warnings.append(
                            f"Option {chr(ord('A') + i)} ('{str(opt).strip()}') uniqueness check encountered worker error: {dist_exc}"
                        )

        except Exception as exc:
            logger.warning("Unexpected error during SymPy evaluation: %s", exc)
            warnings.append(f"SymPy execution encountered an error: {exc}")
            # If sympy_res was already decisively failed (e.g. multiple correct answers found), never erase the failure!
            if sympy_res is None or sympy_res.status not in (
                EvaluationStatus.FAILED,
                EvaluationStatus.DOMAIN_ERROR,
            ):
                sympy_res = EvaluationResult(
                    status=EvaluationStatus.UNSUPPORTED,
                    passed=False,
                    confidence="rule_only",
                    detail=f"SymPy evaluation exception: {exc}",
                )
                checks.append(
                    CheckResult(
                        check_name="sympy_evaluator",
                        passed=False,
                        status="unsupported",
                        confidence="rule_only",
                        detail=str(exc),
                    )
                )

    # -------------------------------------------------------------------------
    # STAGE 4: Deterministic Rule-Based Fallback & Invariants (VAL-04)
    # -------------------------------------------------------------------------
    res_bounds = check_parameter_bounds(
        question_text=question_text,
        options=options,
        blueprint=blueprint,
        parameters=parameters,
    )
    checks.append(res_bounds)
    if not res_bounds.passed:
        errors.extend(res_bounds.errors)

    res_inv = check_mathematical_invariants(
        question_text=question_text,
        options=options,
        blueprint=blueprint,
    )
    checks.append(res_inv)
    if not res_inv.passed:
        errors.extend(res_inv.errors)

    res_dist = check_distractor_reasonableness(
        options=options,
        correct_answer=correct_answer,
    )
    checks.append(res_dist)
    if not res_dist.passed:
        errors.extend(res_dist.errors)

    res_fallback = evaluate_rule_fallback(
        question_text=question_text,
        options=options,
        correct_answer=correct_answer,
        blueprint=blueprint,
        parameters=parameters,
        sympy_result=sympy_res,
    )
    checks.append(res_fallback)
    if not res_fallback.passed:
        errors.extend(res_fallback.errors)

    # -------------------------------------------------------------------------
    # CONSOLIDATION: Determine Overall Status and Confidence
    # -------------------------------------------------------------------------
    dedup_errors = _dedup_list(errors)
    dedup_warnings = _dedup_list(warnings)

    overall_passed = (len(dedup_errors) == 0) and not (
        sympy_res is not None
        and sympy_res.status in (EvaluationStatus.FAILED, EvaluationStatus.DOMAIN_ERROR)
    )

    if (
        sympy_res is not None
        and sympy_res.passed
        and sympy_res.status == EvaluationStatus.VERIFIED
        and not uniqueness_inconclusive
    ):
        confidence = "sympy_verified"
    else:
        confidence = "rule_only"

    if not overall_passed:
        status = "failed"
    elif confidence == "sympy_verified":
        status = "passed"
    else:
        # Rule-only fallback passed
        if treat_fallback_as_warning and dedup_warnings:
            status = "warning"
        else:
            status = "passed"

    exec_ms = (time.perf_counter() - start_time) * 1000.0

    return ValidationReport(
        passed=overall_passed,
        status=status,
        confidence=confidence,
        checks=checks,
        errors=dedup_errors,
        warnings=dedup_warnings,
        execution_time_ms=exec_ms,
    )


def validate_variant(
    variant: Any,
    blueprint: Optional[Dict[str, Any]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_EVALUATION_TIMEOUT,
    fail_fast: bool = False,
    treat_fallback_as_warning: bool = False,
) -> ValidationReport:
    """
    Convenience wrapper to validate a GeneratedVariant, SourceQuestion,
    or duck-typed dictionary using the full 4-tier validation pipeline.
    """
    if isinstance(variant, dict):
        q_text = variant.get("question_text") or variant.get("stem_latex") or ""
        opts = variant.get("options") or []
        ans = variant.get("correct_answer") or variant.get("correct_option") or ""
        var_params = (
            parameters or variant.get("parameters") or variant.get("metadata", {}).get("parameters")
        )
    else:
        q_text = (
            getattr(variant, "question_text", None) or getattr(variant, "stem_latex", None) or ""
        )
        opts = getattr(variant, "options", None) or []
        ans = (
            getattr(variant, "correct_answer", None)
            or getattr(variant, "correct_option", None)
            or ""
        )
        var_params = parameters or getattr(variant, "parameters", None)

    return validate_question(
        question_text=q_text,
        options=opts,
        correct_answer=ans,
        blueprint=blueprint,
        parameters=var_params,
        timeout=timeout,
        fail_fast=fail_fast,
        treat_fallback_as_warning=treat_fallback_as_warning,
    )


def _dedup_list(items: Sequence[str]) -> List[str]:
    """Preserve order while removing duplicate string messages."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

"""
Answer Logic & Duplicate Checker (VAL-02).

Validates:
1. Designated correct answer is valid, unambiguous, and matches one of the 4 options.
2. The 4 options are mutually unique, with no textual or symbolic duplicates
   (e.g., verifying '1/2' vs '0.5' or equivalent expressions using SymPy).

Note:
Checking that an answer matches an option confirms option integrity.
It does NOT mathematically prove that this designated answer is the correct
solution to the problem stem (which is verified by VAL-03 SymPy Evaluator / VAL-04 Rule Checker).
"""

import logging
import re
from typing import Any, List, Optional, Sequence, Tuple

from app.services.validator.base import CheckResult

logger = logging.getLogger(__name__)


def normalize_latex_string(text: str) -> str:
    """
    Clean and normalize math/LaTeX strings for textual comparison:
    - Strip outer math delimiters ('$', '$$', '\\(', '\\)')
    - Normalize whitespace
    - Normalize common LaTeX macros like '\\dfrac' -> '\\frac'
    """
    if not text:
        return ""

    s = text.strip()
    # Strip outer single and double dollars
    if s.startswith("$$") and s.endswith("$$") and len(s) >= 4:
        s = s[2:-2].strip()
    elif s.startswith("$") and s.endswith("$") and len(s) >= 2:
        s = s[1:-1].strip()
    elif s.startswith(r"\(") and s.endswith(r"\)") and len(s) >= 4:
        s = s[2:-2].strip()
    elif s.startswith(r"\[") and s.endswith(r"\]") and len(s) >= 4:
        s = s[2:-2].strip()

    # Normalize common macros
    s = re.sub(r"\\dfrac(?={)", r"\\frac", s)
    s = re.sub(r"\\left|\\right", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _try_parse_to_sympy(expr_str: str) -> Optional[Any]:
    """
    Attempt to parse a LaTeX or math expression string into a SymPy expression.
    Returns None if parsing fails.
    """
    cleaned = normalize_latex_string(expr_str)
    if not cleaned:
        return None

    # First attempt: parse_latex if available
    try:
        from sympy.parsing.latex import parse_latex  # type: ignore[import-untyped]

        return parse_latex(cleaned)
    except Exception:
        pass

    # Second attempt: convert common LaTeX patterns to sympy syntax
    try:
        from sympy import sympify  # type: ignore[import-untyped]

        py_str = cleaned
        # \frac{a}{b} -> ((a)/(b))
        py_str = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", py_str)
        # \sqrt{a} -> sqrt(a)
        py_str = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", py_str)
        # \pm -> ignored or keep
        py_str = py_str.replace("^", "**")
        return sympify(py_str)
    except Exception:
        pass

    return None


def are_expressions_equivalent(expr_a: str, expr_b: str) -> bool:
    """
    Check if two option expressions are mathematically or textually equivalent.
    Returns True if proven equivalent, False otherwise.
    """
    norm_a = normalize_latex_string(expr_a)
    norm_b = normalize_latex_string(expr_b)

    # 1. Exact or normalized string identity
    if norm_a == norm_b:
        return True

    # 2. Direct numeric conversion (e.g. '0.5' vs '0.50' or '1/2' as float)
    try:
        float_a = float(norm_a)
        float_b = float(norm_b)
        if abs(float_a - float_b) < 1e-9:
            return True
    except (ValueError, TypeError):
        pass

    # 3. SymPy symbolic equivalence (e.g., 1/2 vs 0.5, 2x+2 vs 2(x+1))
    sym_a = _try_parse_to_sympy(expr_a)
    sym_b = _try_parse_to_sympy(expr_b)

    if sym_a is not None and sym_b is not None:
        try:
            from sympy import simplify  # type: ignore[import-untyped]

            diff = simplify(sym_a - sym_b)
            if diff == 0:
                return True

            # Check numeric evaluation
            diff_eval = complex(diff.evalf())
            if abs(diff_eval) < 1e-9:
                return True
        except Exception:
            pass

    return False


def _resolve_option_letter(letter: str, options: Sequence[str]) -> Optional[Tuple[int, str]]:
    """
    Resolve option letter ('A', 'B', 'C', 'D' or 'A.', 'Option A') to (index, option_text).
    """
    cleaned = letter.strip().rstrip(".").upper()
    match = re.search(r"\b([A-D])\b", cleaned)
    if match:
        idx = ord(match.group(1)) - ord("A")
        if 0 <= idx < len(options):
            return idx, options[idx]
    return None


def check_designated_answer(
    correct_answer: Optional[str],
    options: Optional[Sequence[str]],
) -> CheckResult:
    """
    Validate that the designated correct answer exists and matches one of the options.
    Accepts:
    - Direct option text match (exact or normalized math)
    - Letter identifier ('A', 'B', 'C', 'D')
    - Mathematical equivalence (e.g. '0.5' matching '$\\frac{1}{2}$')
    """
    if not correct_answer or not str(correct_answer).strip():
        return CheckResult(
            check_name="one_correct",
            passed=False,
            detail="Designated correct answer is empty.",
            errors=["Correct answer must not be empty."],
        )

    if not options or len(options) != 4:
        return CheckResult(
            check_name="one_correct",
            passed=False,
            detail=f"Cannot verify correct answer: expected 4 options, got {len(options) if options else 0}.",
            errors=["Valid 4 options required to verify correct answer."],
        )

    ans_str = str(correct_answer).strip()

    # 1. Check letter designation (e.g., 'A', 'B', 'C', 'D')
    letter_resolved = _resolve_option_letter(ans_str, options)
    if letter_resolved is not None:
        idx, opt_text = letter_resolved
        return CheckResult(
            check_name="one_correct",
            passed=True,
            detail=f"Correct answer letter '{ans_str}' designates Option {idx + 1} ('{opt_text}').",
        )

    # 2. Check direct / equivalent match against options
    matching_indices: List[int] = []
    for idx, opt in enumerate(options):
        if are_expressions_equivalent(ans_str, str(opt)):
            matching_indices.append(idx)

    if not matching_indices:
        return CheckResult(
            check_name="one_correct",
            passed=False,
            detail=f"Designated correct answer '{ans_str}' does not match any of the 4 options.",
            errors=[f"Correct answer '{ans_str}' was not found among the provided options."],
        )

    if len(matching_indices) > 1:
        matched_str = ", ".join(f"Option {i + 1}" for i in matching_indices)
        return CheckResult(
            check_name="one_correct",
            passed=False,
            detail=f"Ambiguous correct answer: matches multiple options ({matched_str}).",
            errors=[f"Correct answer matches multiple options: {matched_str}."],
        )

    matched_idx = matching_indices[0]
    return CheckResult(
        check_name="one_correct",
        passed=True,
        detail=f"Correct answer matches Option {matched_idx + 1} ('{options[matched_idx]}').",
    )


def check_duplicate_options(options: Optional[Sequence[str]]) -> CheckResult:
    """
    Validate that all 4 options are mutually unique and distinct.
    Detects both textual duplicates and mathematical symbolic equivalents
    (e.g., '1/2' vs '0.5' using SymPy simplify).
    """
    if not options or len(options) != 4:
        return CheckResult(
            check_name="no_duplicates",
            passed=False,
            detail=f"Expected exactly 4 options to check uniqueness, got {len(options) if options else 0}.",
            errors=["Options list must contain exactly 4 items."],
        )

    errors: List[str] = []
    duplicates_found: List[Tuple[int, int]] = []

    for i in range(len(options)):
        for j in range(i + 1, len(options)):
            opt_i = str(options[i])
            opt_j = str(options[j])

            if are_expressions_equivalent(opt_i, opt_j):
                duplicates_found.append((i, j))
                errors.append(
                    f"Option {i + 1} ('{opt_i}') and Option {j + 1} ('{opt_j}') have duplicate/equivalent values."
                )

    if duplicates_found:
        detail_msg = "; ".join(errors)
        return CheckResult(
            check_name="no_duplicates",
            passed=False,
            detail=f"Duplicate options detected: {detail_msg}",
            errors=errors,
        )

    return CheckResult(
        check_name="no_duplicates",
        passed=True,
        detail="All 4 options are distinct and mutually exclusive.",
    )


def check_logic(
    options: Optional[Sequence[str]],
    correct_answer: Optional[str],
) -> CheckResult:
    """
    Composite logic validator (VAL-02).
    Evaluates:
    - 4 options have no duplicates (textual or mathematical).
    - Exactly one designated correct answer matching an option.
    """
    errors: List[str] = []

    # Check duplicates first
    dup_res = check_duplicate_options(options)
    if not dup_res.passed:
        errors.extend(dup_res.errors)

    # Check designated answer
    ans_res = check_designated_answer(correct_answer, options)
    if not ans_res.passed:
        errors.extend(ans_res.errors)

    if errors:
        return CheckResult(
            check_name="logic_valid",
            passed=False,
            detail="; ".join(errors),
            errors=errors,
        )

    return CheckResult(
        check_name="logic_valid",
        passed=True,
        detail="All logic and option integrity checks passed.",
    )


def validate_logic_variant(variant: Any) -> CheckResult:
    """
    Convenience adapter to validate a GeneratedVariant, SourceQuestion,
    or duck-typed dictionary / object.
    """
    if isinstance(variant, dict):
        opts = variant.get("options")
        ans = variant.get("correct_answer") or variant.get("correct_option")
    else:
        opts = getattr(variant, "options", None)
        ans = getattr(variant, "correct_answer", None) or getattr(variant, "correct_option", None)

    return check_logic(options=opts, correct_answer=ans)

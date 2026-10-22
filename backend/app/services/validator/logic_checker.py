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

import ast
import builtins
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional, Sequence, Set, Tuple

from app.services.validator.base import CheckResult

logger = logging.getLogger(__name__)

# Safe AST nodes permitted for mathematical expression evaluation
SAFE_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Call,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Load,
)

# Approved mathematical functions permitted in AST call nodes
SAFE_MATH_CALLS = {
    "sqrt",
    "cbrt",
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "asin",
    "acos",
    "atan",
    "arcsin",
    "arccos",
    "arctan",
    "sinh",
    "cosh",
    "tanh",
    "log",
    "ln",
    "log10",
    "log2",
    "exp",
    "abs",
    "factorial",
    "pi",
    "E",
    "oo",
}

# Python builtins that must never be referenced or executed via sympify
DISALLOWED_IDENTIFIERS = set(dir(builtins)) - {"abs"}


def is_safe_math_ast(expr: str) -> bool:
    """
    Validate that a python math expression string contains only safe mathematical
    AST nodes, preventing Remote Code Execution (RCE) via sympify / eval.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except Exception:
        return False

    for node in ast.walk(tree):
        if not isinstance(node, SAFE_AST_NODES):
            return False
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, complex)):
                return False
        elif isinstance(node, ast.Name):
            if node.id.startswith("_") or node.id in DISALLOWED_IDENTIFIERS:
                return False
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                return False
            if node.func.id not in SAFE_MATH_CALLS:
                return False
            if node.keywords:
                return False

    return True


def is_natural_language_text(s: str) -> bool:
    """Check if string is natural language text rather than a pure math expression."""
    return bool(re.search(r"[a-zA-ZÀ-ỹ]{2,}\s+[a-zA-ZÀ-ỹ]{2,}", s))


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
    Enforces strict parsing and AST whitelisting to prevent partial parsing and RCE.
    Returns None if parsing fails or expression is invalid/unsafe.
    """
    cleaned = normalize_latex_string(expr_str)
    if not cleaned:
        return None

    # Reject dangling operators or unclosed expressions (e.g. "x +", "2 -", "3 *")
    if re.search(r"[+\-*/^=,\\]\s*$", cleaned):
        return None

    # First attempt: parse_latex with strict=True
    try:
        from sympy.parsing.latex import parse_latex  # type: ignore[import-untyped]

        # strict=True rejects expressions with trailing unparsed tokens (e.g. "x +")
        return parse_latex(cleaned, strict=True)
    except Exception:
        pass

    # Second attempt: convert common LaTeX patterns to sympy syntax
    try:
        from sympy import sympify  # type: ignore[import-untyped]

        py_str = cleaned
        # \frac{a}{b} -> ((a)/(b))
        py_str = re.sub(r"\\(?:d)?frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", py_str)
        # \sqrt{a} -> sqrt(a)
        py_str = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", py_str)
        py_str = py_str.replace("^", "**")

        # If any backslash remains, it is unparsed LaTeX, do not pass to Python parser
        if "\\" in py_str:
            return None

        # Reject trailing operators again after substitution
        if re.search(r"[+\-*/^=,\\]\s*$", py_str):
            return None

        # Verify AST safety before passing to sympify to prevent RCE
        if not is_safe_math_ast(py_str):
            return None

        return sympify(py_str)
    except Exception:
        pass

    return None


def _compare_equations(norm_a: str, norm_b: str) -> Optional[bool]:
    """
    Compare two equation strings for mathematical equivalence.
    Returns:
    - True if proven mathematically equivalent.
    - False if proven distinct.
    - None if inconclusive (e.g. unsupported structure, unparseable, or different variables).
    """
    lhs_a_str, rhs_a_str = norm_a.split("=", 1)
    lhs_b_str, rhs_b_str = norm_b.split("=", 1)

    lhs_a_clean = lhs_a_str.strip()
    rhs_a_clean = rhs_a_str.strip()
    lhs_b_clean = lhs_b_str.strip()
    rhs_b_clean = rhs_b_str.strip()

    # 1. Fast path: exact same LHS string
    if lhs_a_clean == lhs_b_clean:
        if re.fullmatch(r"^[a-zA-Z]$", lhs_a_clean):
            return are_expressions_equivalent(rhs_a_clean, rhs_b_clean)
        eq_rhs = are_expressions_equivalent(rhs_a_clean, rhs_b_clean)
        if eq_rhs is True:
            return True
        elif eq_rhs is False:
            return False

    # 2. Parse both equations to SymPy: e_a = lhs_a - rhs_a, e_b = lhs_b - rhs_b
    sym_lhs_a = _try_parse_to_sympy(lhs_a_clean)
    sym_rhs_a = _try_parse_to_sympy(rhs_a_clean)
    sym_lhs_b = _try_parse_to_sympy(lhs_b_clean)
    sym_rhs_b = _try_parse_to_sympy(rhs_b_clean)

    if (
        sym_lhs_a is not None
        and sym_rhs_a is not None
        and sym_lhs_b is not None
        and sym_rhs_b is not None
    ):
        try:
            from sympy import simplify, solve  # type: ignore[import-untyped]

            e_a = sym_lhs_a - sym_rhs_a
            e_b = sym_lhs_b - sym_rhs_b

            # Direct difference: e_a - e_b == 0
            diff = simplify(e_a - e_b)
            if diff == 0 or getattr(diff, "is_zero", False) is True:
                return True

            # If both have the exact same set of free symbols
            syms_a: Set[Any] = set(getattr(e_a, "free_symbols", set()))
            syms_b: Set[Any] = set(getattr(e_b, "free_symbols", set()))
            if syms_a and syms_a == syms_b:
                # Proportional equations: e_a / e_b is a non-zero constant (e.g. x - 1 vs 2x - 2)
                try:
                    ratio = simplify(e_a / e_b)
                    if getattr(ratio, "is_number", False) and ratio != 0:
                        return True
                except Exception:
                    pass

                # If single variable, compare root sets
                if len(syms_a) == 1:
                    try:
                        var = next(iter(syms_a))
                        roots_a = solve(e_a, var)
                        roots_b = solve(e_b, var)
                        if roots_a is not None and roots_b is not None:
                            if sorted(str(r) for r in roots_a) == sorted(str(r) for r in roots_b):
                                return True
                            else:
                                return False
                    except Exception:
                        pass
        except Exception:
            pass

    # If cannot prove equivalent or distinct, return None (inconclusive)
    # Crucial: DO NOT return False just because LHS strings differ
    return None


def aggregate_statuses(results: Sequence[CheckResult]) -> Tuple[bool, str, str]:
    """
    Aggregate multiple CheckResult statuses following strict priority:
    failed > inconclusive > verified.

    Returns (passed, status, confidence).
    """
    has_failed = any(
        r.status == "failed" or (not r.passed and r.status != "inconclusive") for r in results
    )
    has_inconclusive = any(r.status == "inconclusive" for r in results)

    if has_failed:
        failed_conf = (
            "sympy_verified"
            if any(r.status == "failed" and r.confidence == "sympy_verified" for r in results)
            else "rule_only"
        )
        return False, "failed", failed_conf

    if has_inconclusive:
        return False, "inconclusive", "rule_only"

    all_sympy = all(r.confidence == "sympy_verified" for r in results)
    return True, "verified", "sympy_verified" if all_sympy else "rule_only"


def are_expressions_equivalent(expr_a: str, expr_b: str) -> Optional[bool]:
    """
    Check if two option expressions are mathematically or textually equivalent.
    Returns:
    - True if proven equivalent.
    - False if proven distinct.
    - None if inconclusive (e.g., unparseable mathematical markup).
    """
    norm_a = normalize_latex_string(expr_a)
    norm_b = normalize_latex_string(expr_b)

    # 1. Exact or normalized string identity
    if norm_a == norm_b:
        return True

    # 2. Natural language text options (e.g. Vietnamese sentences)
    if is_natural_language_text(norm_a) or is_natural_language_text(norm_b):
        return norm_a == norm_b

    # 3. Handle equation-style options
    has_eq_a = norm_a.count("=") == 1
    has_eq_b = norm_b.count("=") == 1

    if has_eq_a and has_eq_b:
        return _compare_equations(norm_a, norm_b)
    elif has_eq_a ^ has_eq_b:
        eq_side, other_side = (norm_a, norm_b) if has_eq_a else (norm_b, norm_a)
        lhs, rhs = eq_side.split("=", 1)
        lhs_clean = lhs.strip()
        rhs_clean = rhs.strip()
        # Only unpack if LHS is a single standalone variable name (e.g. x = 2 matching 2)
        if re.fullmatch(r"^[a-zA-Z]$", lhs_clean):
            return are_expressions_equivalent(rhs_clean, other_side)
        else:
            # Complex equation like x+1=2 cannot match a scalar like 2
            return False

    # 4. Exact numeric conversion via Decimal (avoids float precision loss like 2^53 vs 2^53 + 1)
    try:
        dec_a = Decimal(norm_a)
        dec_b = Decimal(norm_b)
        if dec_a == dec_b:
            return True
        else:
            return False
    except (InvalidOperation, ValueError, TypeError):
        pass

    # 5. SymPy symbolic equivalence (e.g., 1/2 vs 0.5, 2x+2 vs 2(x+1))
    sym_a = _try_parse_to_sympy(expr_a)
    sym_b = _try_parse_to_sympy(expr_b)

    if sym_a is not None and sym_b is not None:
        try:
            from sympy import simplify  # type: ignore[import-untyped]

            diff = simplify(sym_a - sym_b)
            if diff == 0 or diff == 0.0 or getattr(diff, "is_zero", False) is True:
                return True
            return False
        except Exception:
            pass

    # 6. Plain text fallback: if neither expression contains math notation, they are distinct
    has_math_a = any(c in expr_a for c in ["\\", "$", "{", "}", "^", "_", "+", "-", "*", "/", "="])
    has_math_b = any(c in expr_b for c in ["\\", "$", "{", "}", "^", "_", "+", "-", "*", "/", "="])
    if not has_math_a and not has_math_b:
        return False

    # Inconclusive when mathematical expression could not be parsed
    return None


def _resolve_option_letter(letter: str, options: Sequence[str]) -> Optional[Tuple[int, str]]:
    """
    Resolve option letter ('A', 'B', 'C', 'D' or 'A.', 'Option A', 'Phương án A') to (index, option_text).
    Requires full-string match to avoid falsely matching math expressions like 'x + a' as Option A.
    """
    cleaned = letter.strip()
    if cleaned.startswith("$") and cleaned.endswith("$") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()

    match = re.fullmatch(
        r"^(?:(?:Option|Phương\s*án|Đáp\s*án|Câu)\s*)?\(?([A-Da-d])\)?\.?$",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        letter_char = match.group(1).upper()
        idx = ord(letter_char) - ord("A")
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
            status="failed",
            confidence="rule_only",
        )

    if not options or len(options) != 4:
        return CheckResult(
            check_name="one_correct",
            passed=False,
            detail=f"Cannot verify correct answer: expected 4 options, got {len(options) if options else 0}.",
            errors=["Valid 4 options required to verify correct answer."],
            status="failed",
            confidence="rule_only",
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
            status="verified",
            confidence="sympy_verified",
        )

    # 2. Check direct / equivalent match against options
    matching_indices: List[int] = []
    inconclusive_indices: List[int] = []
    for idx, opt in enumerate(options):
        eq = are_expressions_equivalent(ans_str, str(opt))
        if eq is True:
            matching_indices.append(idx)
        elif eq is None:
            inconclusive_indices.append(idx)

    if not matching_indices:
        if inconclusive_indices:
            inconclusive_opts = ", ".join(f"Option {i + 1}" for i in inconclusive_indices)
            return CheckResult(
                check_name="one_correct",
                passed=False,
                detail=f"Designated correct answer '{ans_str}' could not be conclusively compared against {inconclusive_opts}.",
                errors=[f"Correct answer '{ans_str}' could not be resolved against options."],
                status="inconclusive",
                confidence="rule_only",
            )
        return CheckResult(
            check_name="one_correct",
            passed=False,
            detail=f"Designated correct answer '{ans_str}' does not match any of the 4 options.",
            errors=[f"Correct answer '{ans_str}' was not found among the provided options."],
            status="failed",
            confidence="rule_only",
        )

    if len(matching_indices) > 1:
        matched_str = ", ".join(f"Option {i + 1}" for i in matching_indices)
        return CheckResult(
            check_name="one_correct",
            passed=False,
            detail=f"Ambiguous correct answer: matches multiple options ({matched_str}).",
            errors=[f"Correct answer matches multiple options: {matched_str}."],
            status="failed",
            confidence="rule_only",
        )

    matched_idx = matching_indices[0]
    return CheckResult(
        check_name="one_correct",
        passed=True,
        detail=f"Correct answer matches Option {matched_idx + 1} ('{options[matched_idx]}').",
        status="verified",
        confidence="sympy_verified",
    )


def check_duplicate_options(options: Optional[Sequence[str]]) -> CheckResult:
    """
    Validate that all 4 options are mutually unique and distinct.
    Detects both textual duplicates and mathematical symbolic equivalents
    (e.g., '1/2' vs '0.5' using SymPy simplify).
    Fails if any pair is duplicate OR inconclusive (unparseable math).
    """
    if not options or len(options) != 4:
        return CheckResult(
            check_name="no_duplicates",
            passed=False,
            detail=f"Expected exactly 4 options to check uniqueness, got {len(options) if options else 0}.",
            errors=["Options list must contain exactly 4 items."],
            status="failed",
            confidence="rule_only",
        )

    errors: List[str] = []
    duplicates_found: List[Tuple[int, int]] = []
    inconclusive_found: List[Tuple[int, int]] = []

    for i in range(len(options)):
        for j in range(i + 1, len(options)):
            opt_i = str(options[i])
            opt_j = str(options[j])

            eq = are_expressions_equivalent(opt_i, opt_j)
            if eq is True:
                duplicates_found.append((i, j))
                errors.append(
                    f"Option {i + 1} ('{opt_i}') and Option {j + 1} ('{opt_j}') have duplicate/equivalent values."
                )
            elif eq is None:
                inconclusive_found.append((i, j))
                errors.append(
                    f"Option {i + 1} ('{opt_i}') and Option {j + 1} ('{opt_j}') could not be verified for uniqueness (inconclusive expression)."
                )

    if duplicates_found:
        detail_msg = "; ".join(errors)
        return CheckResult(
            check_name="no_duplicates",
            passed=False,
            detail=f"Duplicate options detected: {detail_msg}",
            errors=errors,
            status="failed",
            confidence="sympy_verified",
        )

    if inconclusive_found:
        detail_msg = "; ".join(errors)
        return CheckResult(
            check_name="no_duplicates",
            passed=False,
            detail=f"Inconclusive option uniqueness: {detail_msg}",
            errors=errors,
            status="inconclusive",
            confidence="rule_only",
        )

    return CheckResult(
        check_name="no_duplicates",
        passed=True,
        detail="All 4 options are distinct and mutually exclusive.",
        status="verified",
        confidence="sympy_verified",
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
    Follows strict priority: failed > inconclusive > verified.
    """
    dup_res = check_duplicate_options(options)
    ans_res = check_designated_answer(correct_answer, options)

    all_results = [dup_res, ans_res]
    errors: List[str] = []
    for res in all_results:
        if not res.passed:
            errors.extend(res.errors)

    passed, status, confidence = aggregate_statuses(all_results)
    detail = "; ".join(errors) if errors else "All logic and option integrity checks passed."

    return CheckResult(
        check_name="logic_valid",
        passed=passed,
        detail=detail,
        errors=errors,
        status=status,
        confidence=confidence,
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

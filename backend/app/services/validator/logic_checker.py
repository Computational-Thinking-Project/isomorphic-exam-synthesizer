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
from typing import Any, List, Optional, Sequence, Tuple

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

    # 3. Handle equation-style options (e.g. 'x = 1' vs 'x = 2' or 'y = 0.5' vs 'y = 1/2')
    if "=" in norm_a and "=" in norm_b:
        lhs_a, rhs_a = norm_a.split("=", 1)
        lhs_b, rhs_b = norm_b.split("=", 1)
        if lhs_a.strip() == lhs_b.strip():
            return are_expressions_equivalent(rhs_a.strip(), rhs_b.strip())
        else:
            return False
    elif "=" in norm_a or "=" in norm_b:
        if "=" in norm_a:
            _, rhs_a = norm_a.split("=", 1)
            eq_rhs = are_expressions_equivalent(rhs_a.strip(), norm_b)
            if eq_rhs is True:
                return True
        elif "=" in norm_b:
            _, rhs_b = norm_b.split("=", 1)
            eq_rhs = are_expressions_equivalent(norm_a, rhs_b.strip())
            if eq_rhs is True:
                return True

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
    """
    errors: List[str] = []
    status: Optional[str] = None
    confidence: Optional[str] = None

    # Check duplicates first
    dup_res = check_duplicate_options(options)
    if not dup_res.passed:
        errors.extend(dup_res.errors)
        status = dup_res.status or "failed"
        confidence = dup_res.confidence or "rule_only"

    # Check designated answer
    ans_res = check_designated_answer(correct_answer, options)
    if not ans_res.passed:
        errors.extend(ans_res.errors)
        if status != "inconclusive":
            status = ans_res.status or "failed"
            confidence = ans_res.confidence or "rule_only"

    if errors:
        return CheckResult(
            check_name="logic_valid",
            passed=False,
            detail="; ".join(errors),
            errors=errors,
            status=status or "failed",
            confidence=confidence or "rule_only",
        )

    return CheckResult(
        check_name="logic_valid",
        passed=True,
        detail="All logic and option integrity checks passed.",
        status="verified",
        confidence="sympy_verified",
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

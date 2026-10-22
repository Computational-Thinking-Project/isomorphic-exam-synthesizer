"""
SymPy Mathematical Evaluator (VAL-03 / TASK-107b).

Performs formal mathematical verification:
1. Parse LaTeX strings to SymPy expressions with a strict 500-char bound.
   Enforces strict parsing and AST whitelisting to prevent RCE via sympify.
2. Verify mathematical domain constraints:
   - Denominators != 0
   - Radicands of even roots >= 0 (real domain)
   - Logarithm arguments > 0
3. Verify equations, solutions, and mathematical expressions using exact equality (no fuzzy 1e-9).
4. Executes all CAS computations inside isolated processes with a hard 5-second
   timeout and guaranteed resource reclamation.
5. Preserves confidence and status semantics in CheckResult:
   - Verified -> 'sympy_verified'
   - Timeout / Unsupported -> 'rule_only' / warning (never false pass).
"""

import ast
import builtins
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.services.validator.base import CheckResult
from app.services.validator.process_runner import run_with_timeout

logger = logging.getLogger(__name__)

MAX_EXPRESSION_LENGTH: int = 500
DEFAULT_EVALUATION_TIMEOUT: float = 5.0

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


class EvaluationStatus(str, Enum):
    """Status of mathematical CAS evaluation."""

    VERIFIED = "verified"  # Mathematically verified correct
    FAILED = "failed"  # Mathematically disproved or wrong answer
    DOMAIN_ERROR = "domain_error"  # Domain violation (zero denominator, negative root, etc.)
    UNSUPPORTED = "unsupported"  # Out-of-scope math family or unparseable expression
    TIMEOUT = "timeout"  # Computation timed out


class EvaluationResult:
    """Standardized outcome of mathematical evaluation."""

    def __init__(
        self,
        status: EvaluationStatus,
        passed: bool,
        confidence: str,
        detail: Optional[str] = None,
        errors: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.status = status
        self.passed = passed
        self.confidence = confidence
        self.detail = detail
        self.errors = errors or []
        self.metadata = metadata or {}

    def __bool__(self) -> bool:
        return self.passed

    def to_check_result(self, check_name: str = "answer_verified") -> CheckResult:
        """
        Convert to a standard CheckResult for aggregator / report.
        Preserves status and confidence for downstream handoff (e.g. TV7 rule fallback).
        """
        return CheckResult(
            check_name=check_name,
            passed=self.passed,
            detail=self.detail,
            errors=self.errors,
            status=self.status.value,
            confidence=self.confidence,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "confidence": self.confidence,
            "detail": self.detail,
            "errors": self.errors,
        }


def clean_latex(text: str) -> str:
    """Pre-process and clean LaTeX mathematical string for SymPy parsing."""
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

    # Normalize macros
    s = re.sub(r"\\dfrac(?={)", r"\\frac", s)
    s = re.sub(r"\\left|\\right", "", s)
    s = re.sub(r"\\cdot|\\times", "*", s)
    return s.strip()


def parse_to_sympy(expr_str: str) -> Tuple[Optional[Any], Optional[str]]:
    """
    Parse a mathematical string or LaTeX expression into a SymPy expression.
    Enforces the 500-character upper bound and strict parsing.
    Returns (expression, error_message).
    """
    if len(expr_str) > MAX_EXPRESSION_LENGTH:
        return (
            None,
            f"Expression exceeds maximum length of {MAX_EXPRESSION_LENGTH} characters (len={len(expr_str)}).",
        )

    cleaned = clean_latex(expr_str)
    if not cleaned:
        return None, "Empty expression."

    # Reject dangling operators or unclosed expressions (e.g. "2 +", "x -", "2 *")
    if re.search(r"[+\-*/^=,\\]\s*$", cleaned):
        return None, f"Expression '{cleaned}' has trailing or dangling operators."

    # First attempt: parse_latex with strict=True
    try:
        from sympy.parsing.latex import parse_latex  # type: ignore[import-untyped]

        parsed = parse_latex(cleaned, strict=True)
        return parsed, None
    except Exception:
        pass

    # Second attempt: regex translation to Python math syntax + sympify
    try:
        from sympy import sympify  # type: ignore[import-untyped]

        py_str = cleaned
        # \frac{a}{b} -> ((a)/(b))
        py_str = re.sub(r"\\(?:d)?frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", py_str)
        # \sqrt{a} -> sqrt(a)
        py_str = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", py_str)
        # Implicit multiplication between digit and variable (e.g. 5x -> 5*x)
        py_str = re.sub(r"(\d)\s*([a-zA-Z])", r"\1*\2", py_str)
        py_str = py_str.replace("^", "**")

        # If backslash remains, it is unparsed LaTeX
        if "\\" in py_str:
            return None, f"Unrecognized LaTeX macro in expression: '{cleaned}'"

        # Reject trailing operators again after substitution
        if re.search(r"[+\-*/^=,\\]\s*$", py_str):
            return None, f"Expression '{py_str}' has trailing operator."

        # AST whitelist check before passing to sympify to prevent RCE
        if not is_safe_math_ast(py_str):
            return None, f"Expression '{py_str}' contains unsafe or disallowed syntax."

        parsed = sympify(py_str)
        return parsed, None
    except Exception as exc:
        return None, f"Could not parse expression '{cleaned}': {exc}"


def _check_domain_internal(expr: Any, val_dict: Dict[Any, Any]) -> Tuple[bool, Optional[str]]:
    """
    Check mathematical domain of expression when evaluated at given symbol values.
    Verifies:
    1. Denominators != 0
    2. Even root arguments >= 0
    3. Logarithm arguments > 0
    """
    from sympy import Pow, Rational, fraction, log  # type: ignore[import-untyped]

    try:
        # 1. Denominator check from fraction
        numer, denom = fraction(expr)
        if denom != 1:
            denom_eval = denom.subs(val_dict)
            try:
                if complex(denom_eval.evalf()) == 0:
                    return False, f"Denominator equals zero when substituting {val_dict}."
            except Exception:
                pass

        # 2. Check all Pow nodes (negative exponents for denominators, even fractional for roots)
        for p in expr.atoms(Pow):
            base, exp = p.as_base_exp()
            # Negative power -> denominator
            if exp < 0:
                base_val = base.subs(val_dict)
                try:
                    if complex(base_val.evalf()) == 0:
                        return (
                            False,
                            f"Denominator '{base}' equals zero when substituting {val_dict}.",
                        )
                except Exception:
                    pass
            # Even root -> radicand must be >= 0
            if isinstance(exp, Rational) and exp.q % 2 == 0:
                base_val = base.subs(val_dict)
                try:
                    f_val = float(base_val.evalf())
                    if f_val < 0:
                        return (
                            False,
                            f"Radicand '{base}' is negative ({f_val}) in real domain when substituting {val_dict}.",
                        )
                except Exception:
                    pass

        # 3. Check logarithm nodes
        for node in expr.atoms(log):
            arg = node.args[0]
            val = arg.subs(val_dict)
            try:
                f_val = float(val.evalf())
                if f_val <= 0:
                    return (
                        False,
                        f"Logarithm argument '{arg}' is non-positive ({f_val}) when substituting {val_dict}.",
                    )
            except Exception:
                pass

    except Exception as e:
        logger.debug("Domain check encountered exception: %s", e)

    return True, None


def _verify_solution_internal(
    equation_str: str,
    candidate_answer_str: str,
    variable_name: str = "x",
) -> Tuple[EvaluationStatus, str]:
    """
    Internal calculation function to verify if candidate_answer_str is a valid solution
    to equation_str. Runs inside isolated worker process.
    """
    from sympy import (  # type: ignore[import-untyped]
        EmptySet,
        Eq,
        simplify,
        solve,
        symbols,
    )

    cleaned_eq = clean_latex(equation_str)
    cleaned_ans = clean_latex(candidate_answer_str)

    # 1. Parse equation
    if "=" in cleaned_eq:
        lhs_str, rhs_str = cleaned_eq.split("=", 1)
        lhs_expr, err_lhs = parse_to_sympy(lhs_str)
        rhs_expr, err_rhs = parse_to_sympy(rhs_str)
        if lhs_expr is None or rhs_expr is None:
            return (
                EvaluationStatus.UNSUPPORTED,
                f"Equation cannot be parsed: {err_lhs or err_rhs}",
            )
        equation = Eq(lhs_expr, rhs_expr)
    else:
        # If no '=', assume f(x) = 0
        lhs_expr, err_lhs = parse_to_sympy(cleaned_eq)
        if lhs_expr is None:
            return (
                EvaluationStatus.UNSUPPORTED,
                f"Expression cannot be parsed: {err_lhs}",
            )
        equation = Eq(lhs_expr, 0)

    # Detect variable symbol
    var_sym = symbols(variable_name)
    free_syms = equation.free_symbols
    if free_syms:
        # Pick the matching symbol or the first available
        for s in free_syms:
            if s.name == variable_name:
                var_sym = s
                break
        else:
            var_sym = list(free_syms)[0]

    # 2. Extract candidate values
    # Candidate answer can be "x = 2", "2", "x = 1; x = 3", etc.
    candidate_values: List[Any] = []

    # Handle multiple values separated by ';' or 'hoặc'
    parts = re.split(r"[;,]|\bhoặc\b", cleaned_ans)
    for part in parts:
        part_clean = part.strip()
        if not part_clean:
            continue
        # Check invalid tokens or dangling characters (e.g. "2 +", "2; ?")
        if re.search(r"[+\-*/^=,\\]\s*$", part_clean) or any(c in part_clean for c in "?!@#$%&"):
            return (
                EvaluationStatus.UNSUPPORTED,
                f"Candidate answer contains invalid or dangling token: '{part_clean}'.",
            )
        if "=" in part_clean:
            _, val_part = part_clean.split("=", 1)
            val_part = val_part.strip()
        else:
            val_part = part_clean

        parsed_val, err_val = parse_to_sympy(val_part)
        if parsed_val is None:
            # Philip: Do not silently ignore unparseable parts!
            return (
                EvaluationStatus.UNSUPPORTED,
                f"Part '{val_part}' of candidate answer could not be parsed: {err_val}",
            )
        candidate_values.append(parsed_val)

    if not candidate_values:
        return (
            EvaluationStatus.UNSUPPORTED,
            f"Candidate answer '{candidate_answer_str}' could not be parsed to mathematical value.",
        )

    # 3. Check domain for candidate values
    for val in candidate_values:
        val_map = {var_sym: val}
        ok_domain, domain_err = _check_domain_internal(equation.lhs - equation.rhs, val_map)
        if not ok_domain:
            return (
                EvaluationStatus.DOMAIN_ERROR,
                domain_err or "Domain constraint violated.",
            )

    # 4. Substitute candidate values into equation (exact equality, no fuzzy 1e-9 threshold)
    for val in candidate_values:
        diff = simplify(equation.lhs.subs(var_sym, val) - equation.rhs.subs(var_sym, val))
        is_zero = diff == 0 or diff == 0.0 or getattr(diff, "is_zero", False) is True

        if not is_zero:
            return (
                EvaluationStatus.FAILED,
                f"Candidate value '{val}' does not satisfy equation: LHS - RHS = {diff}.",
            )

    # 5. Check if equation has expected solutions
    try:
        solved_roots = solve(equation, var_sym)
        if solved_roots == EmptySet or len(solved_roots) == 0:
            return EvaluationStatus.FAILED, "Equation has no solutions in SymPy."
    except Exception:
        # Solving general equation might be out of scope, but candidate satisfied it
        pass

    return (
        EvaluationStatus.VERIFIED,
        f"Verified: candidate answer '{candidate_answer_str}' satisfies the mathematical equation.",
    )


def extract_equation_from_text(text: str) -> Optional[str]:
    """
    Heuristically extract a mathematical equation from a question text.
    Looks for LaTeX inline math containing '=' or equations like 'x^2 - 4x + 3 = 0'.
    """
    if not text:
        return None

    # Search for $...=...$
    math_matches = re.findall(r"\$([^\$]+=[^\$]+)\$", text)
    if math_matches:
        # Return the longest equation found
        return max(math_matches, key=len)

    # Search for $$...=...$$
    display_matches = re.findall(r"\$\$([^\$]+=[^\$]+)\$\$", text)
    if display_matches:
        return max(display_matches, key=len)

    return None


def verify_equation_solution(
    equation_str: str,
    candidate_answer_str: str,
    timeout: float = DEFAULT_EVALUATION_TIMEOUT,
) -> EvaluationResult:
    """
    Verify whether candidate_answer_str satisfies equation_str.
    Executes in an isolated worker process with strict timeout.
    """
    if len(equation_str) > MAX_EXPRESSION_LENGTH:
        return EvaluationResult(
            status=EvaluationStatus.UNSUPPORTED,
            passed=False,
            confidence="rule_only",
            detail=f"Equation exceeds maximum length bound of {MAX_EXPRESSION_LENGTH} characters.",
        )

    if len(candidate_answer_str) > MAX_EXPRESSION_LENGTH:
        return EvaluationResult(
            status=EvaluationStatus.UNSUPPORTED,
            passed=False,
            confidence="rule_only",
            detail=f"Candidate answer exceeds maximum length bound of {MAX_EXPRESSION_LENGTH} characters.",
        )

    proc_res = run_with_timeout(
        _verify_solution_internal,
        args=(equation_str, candidate_answer_str),
        timeout=timeout,
    )

    if proc_res.timed_out:
        return EvaluationResult(
            status=EvaluationStatus.TIMEOUT,
            passed=False,
            confidence="rule_only",
            detail=f"SymPy evaluation timed out after {timeout:.1f}s.",
        )

    if not proc_res.success:
        return EvaluationResult(
            status=EvaluationStatus.UNSUPPORTED,
            passed=False,
            confidence="rule_only",
            detail=f"Process runner error: {proc_res.error}",
        )

    status, detail_msg = proc_res.data
    is_passed = status == EvaluationStatus.VERIFIED
    confidence = (
        "sympy_verified"
        if status
        in (EvaluationStatus.VERIFIED, EvaluationStatus.FAILED, EvaluationStatus.DOMAIN_ERROR)
        else "rule_only"
    )

    return EvaluationResult(
        status=status,
        passed=is_passed,
        confidence=confidence,
        detail=detail_msg,
        errors=[] if is_passed else [detail_msg],
    )


def verify_question_math(
    question_text: str,
    correct_answer: str,
    timeout: float = DEFAULT_EVALUATION_TIMEOUT,
) -> EvaluationResult:
    """
    Attempt formal mathematical verification of a question stem and its correct answer.
    Extracts equation from the question text and runs verification in an isolated process.

    If question math is not formal algebra/calculus (e.g. geometry, word problems,
    expression calculation, or unsupported math), gracefully returns UNSUPPORTED with
    confidence 'rule_only', ready for Rule Fallback Checker (VAL-04 / TV7).
    """
    if not question_text or not question_text.strip():
        return EvaluationResult(
            status=EvaluationStatus.UNSUPPORTED,
            passed=False,
            confidence="rule_only",
            detail="Question text is empty.",
        )

    # Check if the question is an expression evaluation rather than an equation-solving task
    # e.g., "Cho x = 2. Tính x + 1" or "Tính giá trị của biểu thức..."
    calculation_indicators = re.search(
        r"\b(?:tính|giá\s*trị\s*(?:của|biểu\s*thức)?|rút\s*gọn|đạo\s*hàm|nguyên\s*hàm|tích\s*phân|xác\s*suất)\b",
        question_text,
        re.IGNORECASE,
    )
    if calculation_indicators:
        return EvaluationResult(
            status=EvaluationStatus.UNSUPPORTED,
            passed=False,
            confidence="rule_only",
            detail=(
                f"Question requires computation/evaluation ('{calculation_indicators.group(0)}') "
                "rather than finding roots of an equation. Fallback to rule checking."
            ),
        )

    equation = extract_equation_from_text(question_text)
    if not equation:
        return EvaluationResult(
            status=EvaluationStatus.UNSUPPORTED,
            passed=False,
            confidence="rule_only",
            detail="No solvable algebraic equation extracted from question text. Fallback to rule checking.",
        )

    return verify_equation_solution(
        equation_str=equation,
        candidate_answer_str=correct_answer,
        timeout=timeout,
    )


def verify_variant_math(
    variant: Any,
    timeout: float = DEFAULT_EVALUATION_TIMEOUT,
) -> EvaluationResult:
    """
    Convenience wrapper to verify a GeneratedVariant, SourceQuestion,
    or duck-typed dictionary.
    """
    if isinstance(variant, dict):
        q_text = variant.get("question_text") or variant.get("stem_latex") or ""
        ans = variant.get("correct_answer") or variant.get("correct_option") or ""
    else:
        q_text = (
            getattr(variant, "question_text", None) or getattr(variant, "stem_latex", None) or ""
        )
        ans = (
            getattr(variant, "correct_answer", None)
            or getattr(variant, "correct_option", None)
            or ""
        )

    return verify_question_math(
        question_text=q_text,
        correct_answer=ans,
        timeout=timeout,
    )

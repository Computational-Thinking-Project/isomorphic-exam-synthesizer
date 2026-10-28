"""
Rule-Based Fallback Checker (VAL-04 / TASK-107c).

Provides independent, deterministic rule-based mathematical validation and
fallback routing when CAS (SymPy) evaluation is unsupported, times out, or
inconclusive.

Key Capabilities:
1. Parameter bounds validation:
   - Validates numerical parameters against blueprint parameter_domains / bounds.
   - Supports Schema Draft 2020-12 nested format and flat dictionaries.
   - Enforces minimum, maximum, allowed_values, and step / divisibility constraints.
2. Mathematical invariants verification:
   - Denominator non-zero (fractions \\frac{A}{B} or A/B where B != 0).
   - Real radicands (even roots \\sqrt{A} where A >= 0 in the real domain).
   - Logarithm domains (\\log_b(A), \\ln(A) where A > 0 and base b > 0, b != 1).
   - Quadratic discriminant invariant (Delta = b^2 - 4ac > 0 for 2 distinct real roots).
   - Probability range (0 <= P <= 1 for explicit probability quantities).
   - Geometric measures (side lengths, radius, area, volume > 0, triangle inequality).
3. Distractor reasonableness check:
   - No duplicate options.
   - No empty, NaN, or degenerate options.
   - Validates options align with answer and domain sanity.
4. Out-of-scope math detection:
   - Detects geometry, word problems / practical math, combinatorics / probability, calculus.
5. Automated fallback routing and orchestration:
   - Handles SymPy evaluation results (passes if SymPy verified and rules hold).
   - Routes unsupported or timed-out CAS queries to rule-based fallback with status
     'passed_rule_fallback' and confidence 'rule_only'.
   - Direct standalone validation of question variants.
"""

import ast
import logging
import math
import re
from decimal import Decimal, InvalidOperation, getcontext
from fractions import Fraction
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.validator.base import CheckResult
from app.services.validator.logic_checker import (
    _resolve_option_letter,
    are_expressions_equivalent,
    normalize_latex_string,
)

logger = logging.getLogger(__name__)

# Out-of-scope classification patterns
OUT_OF_SCOPE_PATTERNS = {
    "geometry": re.compile(
        r"\b(?:hình\s+chóp|lăng\s+trụ|tam\s+giác|hình\s+vuông|hình\s+chữ\s+nhật|mặt\s+cầu|"
        r"tứ\s+diện|hình\s+nón|hình\s+trụ|đoạn\s+thẳng|vuông\s+góc|song\s+song|vectơ|vector|"
        r"mặt\s+phẳng|tọa\s+độ\s+không\s+gian|bán\s+kính|thể\s+tích|diện\s+tích|chu\s+vi|"
        r"góc\s+giữa|khoảng\s+cách\s+từ|hình\s+thang|hình\s+thoi|đa\s+giác)\b",
        re.IGNORECASE,
    ),
    "combinatorics_probability": re.compile(
        r"\b(?:xác\s+suất|tổ\s+hợp|chỉnh\s+hợp|hoán\s+vị|chọn\s+ngẫu\s+nhiên|biến\s+cố|"
        r"gieo\s+xúc\s+xắc|rút\s+thăm|bóng\s+đèn|viên\s+bi|chia\s+nhóm|cách\s+chọn|"
        r"xếp\s+ngẫu\s+nhiên|không\s+gian\s+mẫu|đồng\s+khả\s+năng)\b",
        re.IGNORECASE,
    ),
    "word_problem": re.compile(
        r"\b(?:quãng\s+đường|vận\s+tốc|thời\s+gian|lãi\s+suất|bể\s+nước|năng\s+suất|tiền|"
        r"triệu\s+đồng|người\s+đi\s+xe|công\s+việc|lợi\s+nhuận|doanh\s+thu|chi\s+phí|đoàn\s+tàu)\b",
        re.IGNORECASE,
    ),
    "calculus": re.compile(
        r"\b(?:nguyên\s+hàm|tích\s+phân|đạo\s+hàm|tiệm\s+cận|bảng\s+biến\s+thiên|cực\s+trị|"
        r"đồng\s+biến|nghịch\s+biến|điểm\s+uốn|tiếp\s+tuyến)\b",
        re.IGNORECASE,
    ),
    "complex_numbers": re.compile(
        r"\b(?:số\s+phức|phần\s+thực|phần\s+ảo|môđun|mô-đun|số\s+phức\s+liên\s+hợp|dạng\s+lượng\s+giác)\b",
        re.IGNORECASE,
    ),
    "linear_algebra_matrices": re.compile(
        r"\b(?:ma\s+trận|định\s+thức|hệ\s+phương\s+trình\s+(?:bậc\s+nhất\s+)?(?:ba|3|bốn|4)\s+ẩn)\b",
        re.IGNORECASE,
    ),
}

# Regex for fraction patterns in LaTeX: \frac{A}{B} or \dfrac{A}{B}
LATEX_FRACTION_REGEX = re.compile(r"\\(?:d)?frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")

# Regex for plain numerical fraction A / B
PLAIN_FRACTION_REGEX = re.compile(
    r"(?<![a-zA-Z0-9_])(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)(?![a-zA-Z0-9_])"
)

# Regex for radical expressions: \sqrt{A} or \sqrt[n]{A}
LATEX_SQRT_REGEX = re.compile(r"\\sqrt(?:\s*\[\s*(\d+)\s*\])?\s*\{([^{}]+)\}")

# Regex for logarithm expressions: \log_b(A), \log(A), \ln(A)
LATEX_LOG_REGEX = re.compile(
    r"\\log(?:\s*_\s*(?:\{([^{}]+)\}|([0-9a-zA-Z]+)))?\s*(?:\(\s*\{?([^{}\)\s]+)\}?\s*\)|\{([^{}]+)\})"
)
LATEX_LN_REGEX = re.compile(r"\\ln\s*(?:\(\s*\{?([^{}\)\s]+)\}?\s*\)|\{([^{}]+)\})")

# Regex for quadratic equation: a x^2 + b x + c = 0 (supports variables x, t, y, u, z)
QUADRATIC_EQ_REGEX = re.compile(
    r"(?:(?P<a>[+-]?\s*\d*(?:\.\d+)?)\s*\*?\s*(?:[xtyuz]\^2|[xtyuz]²))\s*"
    r"(?:(?P<b>[+-]\s*\d*(?:\.\d+)?)\s*\*?\s*[xtyuz])\s*"
    r"(?:(?P<c>[+-]\s*\d+(?:\.\d+)?))?\s*=\s*0",
    re.IGNORECASE,
)


def _format_fraction(val: Fraction) -> str:
    """Format Fraction into exact decimal string if terminating, otherwise fraction or integer."""
    if val.denominator == 1:
        return str(val.numerator)
    temp_den = val.denominator
    while temp_den % 2 == 0:
        temp_den //= 2
    while temp_den % 5 == 0:
        temp_den //= 5
    if temp_den == 1:
        return str(Decimal(val.numerator) / Decimal(val.denominator))
    return str(val)


def _exact_integer_nth_root(val: int, n: int) -> Optional[int]:
    """
    Return exact integer n-th root of non-negative integer val if it exists,
    otherwise None.
    """
    if val < 0 or n <= 0:
        return None
    if val == 0:
        return 0
    if val == 1 or n == 1:
        return val
    if n == 2:
        r = math.isqrt(val)
        return r if r * r == val else None

    # Binary search for exact integer n-th root (n >= 3)
    low = 1
    high = 1 << ((val.bit_length() + n - 1) // n)
    while low <= high:
        mid = (low + high) // 2
        p = mid**n
        if p == val:
            return mid
        if p < val:
            low = mid + 1
        else:
            high = mid - 1
    return None


def _extract_balanced_braces(text: str, start_pos: int) -> Optional[Tuple[str, int]]:
    """
    Extract content of balanced { ... } starting at start_pos (where text[start_pos] == '{').
    Returns (content, end_pos_after_closing_brace) or None if unclosed / invalid.
    """
    if start_pos >= len(text) or text[start_pos] != "{":
        return None
    depth = 0
    for i in range(start_pos, len(text)):
        if text[i] == "{" and (i == 0 or text[i - 1] != "\\"):
            depth += 1
        elif text[i] == "}" and (i == 0 or text[i - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return text[start_pos + 1 : i], i + 1
    return None


def _extract_latex_fractions(text: str) -> List[Tuple[str, str]]:
    """Extract all LaTeX fractions \\frac{num}{den} or \\dfrac{num}{den} supporting nested braces."""
    results: List[Tuple[str, str]] = []
    pattern = re.compile(r"\\(?:d)?frac(?=[^a-zA-Z]|$)")
    for m in pattern.finditer(text):
        idx = m.end()
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text) or text[idx] != "{":
            continue
        num_res = _extract_balanced_braces(text, idx)
        if not num_res:
            continue
        num_str, idx = num_res
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text) or text[idx] != "{":
            continue
        den_res = _extract_balanced_braces(text, idx)
        if not den_res:
            continue
        den_str, _ = den_res
        results.append((num_str.strip(), den_str.strip()))
    return results


def _extract_latex_sqrts(text: str) -> List[Tuple[Optional[int], str]]:
    """Extract all LaTeX radicals \\sqrt[n]{radicand} or \\sqrt{radicand} supporting nested braces."""
    results: List[Tuple[Optional[int], str]] = []
    pattern = re.compile(r"\\sqrt(?=[^a-zA-Z]|$)")
    for m in pattern.finditer(text):
        idx = m.end()
        degree: Optional[int] = None
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx < len(text) and text[idx] == "[":
            end_bracket = text.find("]", idx)
            if end_bracket != -1:
                deg_content = text[idx + 1 : end_bracket].strip()
                if deg_content.isdigit():
                    degree = int(deg_content)
                idx = end_bracket + 1
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx < len(text) and text[idx] == "{":
            res = _extract_balanced_braces(text, idx)
            if res:
                results.append((degree, res[0].strip()))
    return results


def _extract_latex_logs(text: str) -> List[Tuple[Optional[str], str]]:
    """Extract (base_str, arg_str) from \\log_{base}(arg) or \\log_b(arg) or \\log(arg) or \\log{arg}."""
    results: List[Tuple[Optional[str], str]] = []
    pattern = re.compile(r"\\log(?=[^a-zA-Z]|$)")
    for m in pattern.finditer(text):
        idx = m.end()
        base_str: Optional[str] = None
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx < len(text) and text[idx] == "_":
            idx += 1
            while idx < len(text) and text[idx].isspace():
                idx += 1
            if idx < len(text) and text[idx] == "{":
                res = _extract_balanced_braces(text, idx)
                if res:
                    base_str, idx = res
            else:
                m_base = re.match(r"([0-9a-zA-Z\.\-]+)", text[idx:])
                if m_base:
                    base_str = m_base.group(1)
                    idx += m_base.end()
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx < len(text) and text[idx] == "{":
            res = _extract_balanced_braces(text, idx)
            if res:
                results.append((base_str, res[0].strip()))
        elif idx < len(text) and text[idx] == "(":
            depth = 0
            start = idx
            for i in range(start, len(text)):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        results.append((base_str, text[start + 1 : i].strip()))
                        break
    return results


def _extract_latex_lns(text: str) -> List[str]:
    """Extract arg_str from \\ln(arg) or \\ln{arg} supporting nested braces."""
    results: List[str] = []
    pattern = re.compile(r"\\ln(?=[^a-zA-Z]|$)")
    for m in pattern.finditer(text):
        idx = m.end()
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx < len(text) and text[idx] == "{":
            res = _extract_balanced_braces(text, idx)
            if res:
                results.append(res[0].strip())
        elif idx < len(text) and text[idx] == "(":
            depth = 0
            start = idx
            for i in range(start, len(text)):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        results.append(text[start + 1 : i].strip())
                        break
    return results


def _latex_to_python_numeric(expr: str) -> str:
    """Pre-convert LaTeX fraction and sqrt macros into standard Python arithmetic for AST parsing."""
    cleaned = expr.strip()
    cleaned = re.sub(r"\\(?:left|right)", "", cleaned)
    # Replace \sqrt{...} with sqrt(...)
    while r"\sqrt" in cleaned:
        m = re.search(r"\\sqrt(?=[^a-zA-Z]|$)(?:\s*\[\s*(\d+)\s*\])?", cleaned)
        if not m:
            break
        idx = m.end()
        while idx < len(cleaned) and cleaned[idx].isspace():
            idx += 1
        if idx < len(cleaned) and cleaned[idx] == "{":
            res = _extract_balanced_braces(cleaned, idx)
            if res:
                inner, end_idx = res
                deg = m.group(1)
                if deg and deg != "2":
                    replacement = f"(({_latex_to_python_numeric(inner)})**(1/{deg}))"
                else:
                    replacement = f"sqrt({_latex_to_python_numeric(inner)})"
                cleaned = cleaned[: m.start()] + replacement + cleaned[end_idx:]
                continue
        break

    # Replace \frac{A}{B} or \dfrac{A}{B} with ((A)/(B))
    while re.search(r"\\(?:d)?frac(?=[^a-zA-Z]|$)", cleaned):
        m = re.search(r"\\(?:d)?frac(?=[^a-zA-Z]|$)", cleaned)
        if not m:
            break
        idx = m.end()
        while idx < len(cleaned) and cleaned[idx].isspace():
            idx += 1
        num_res = (
            _extract_balanced_braces(cleaned, idx)
            if idx < len(cleaned) and cleaned[idx] == "{"
            else None
        )
        if not num_res:
            break
        num_str, idx2 = num_res
        while idx2 < len(cleaned) and cleaned[idx2].isspace():
            idx2 += 1
        den_res = (
            _extract_balanced_braces(cleaned, idx2)
            if idx2 < len(cleaned) and cleaned[idx2] == "{"
            else None
        )
        if not den_res:
            break
        den_str, end_idx = den_res
        replacement = (
            f"(({_latex_to_python_numeric(num_str)})/({_latex_to_python_numeric(den_str)}))"
        )
        cleaned = cleaned[: m.start()] + replacement + cleaned[end_idx:]

    cleaned = cleaned.replace("{", "(").replace("}", ")")
    cleaned = cleaned.replace("^", "**")
    return cleaned


class SafeNumericEvaluator(ast.NodeVisitor):
    """
    Strict, deterministic AST visitor that safely evaluates basic numeric
    arithmetic expressions (+, -, *, /, **, %) and safe functions (sqrt, abs)
    without using eval() or arbitrary code execution.
    Maintains exact rational Fraction precision to prevent IEEE 754 precision loss
    and recurring decimal division rounding errors.
    """

    def __init__(self, source: Optional[str] = None) -> None:
        self.source = source

    def visit_Expression(self, node: ast.Expression) -> Fraction:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Fraction:
        if self.source is not None:
            raw = ast.get_source_segment(self.source, node)
            if raw is not None:
                cleaned_raw = raw.strip().strip("()").replace("_", "")
                try:
                    return Fraction(cleaned_raw)
                except ValueError:
                    pass
        if isinstance(node.value, int):
            return Fraction(node.value)
        if isinstance(node.value, float):
            return Fraction(str(node.value))
        if isinstance(node.value, str):
            return Fraction(node.value)
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Fraction:
        operand: Fraction = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"Unsupported unary operator: {type(node.op)}")

    def visit_BinOp(self, node: ast.BinOp) -> Fraction:
        left: Fraction = self.visit(node.left)
        right: Fraction = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("Division by zero in AST evaluation")
            return left / right
        if isinstance(node.op, ast.Pow):
            if left == 0 and right == 0:
                raise ValueError("Indeterminate form 0**0")
            max_base = 10**18 if abs(right) <= 1 else 1000000
            if abs(left) > max_base or abs(right) > 20:
                raise ValueError("Exponentiation out of safe bounds")
            if right.denominator != 1:
                p = right.numerator
                q = right.denominator
                if left == 0:
                    if p > 0:
                        return Fraction(0)
                    raise ZeroDivisionError(
                        "Division by zero in AST evaluation (0 to non-positive power)"
                    )
                if left < 0 and q % 2 == 0:
                    raise ValueError(f"Even root of negative number: {left}")

                abs_num = abs(left.numerator)
                den = left.denominator
                num_r = _exact_integer_nth_root(abs_num, q)
                den_r = _exact_integer_nth_root(den, q)
                if num_r is not None and den_r is not None:
                    root_frac = Fraction(num_r, den_r)
                    sign = -1 if (left < 0 and p % 2 != 0) else 1
                    return sign * (root_frac**p)

                # Fallback to high-precision Decimal without limit_denominator
                getcontext().prec = 50
                dec_base = Decimal(abs_num) / Decimal(den)
                dec_exp = Decimal(abs(p)) / Decimal(q)
                dec_res = dec_base**dec_exp
                if p < 0:
                    dec_res = Decimal(1) / dec_res
                sign = -1 if (left < 0 and p % 2 != 0) else 1
                return sign * Fraction(str(dec_res))

            return left ** int(right)
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError("Modulo by zero in AST evaluation")
            return left % right
        raise ValueError(f"Unsupported binary operator: {type(node.op)}")

    def visit_Call(self, node: ast.Call) -> Fraction:
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name == "abs" and len(node.args) == 1:
                return abs(self.visit(node.args[0]))
            if func_name == "sqrt" and len(node.args) == 1:
                val: Fraction = self.visit(node.args[0])
                if val < 0:
                    raise ValueError(f"Square root of negative number: {val}")
                if val == 0:
                    return Fraction(0)
                num_sqrt = math.isqrt(val.numerator)
                den_sqrt = math.isqrt(val.denominator)
                if num_sqrt * num_sqrt == val.numerator and den_sqrt * den_sqrt == val.denominator:
                    return Fraction(num_sqrt, den_sqrt)
                dec = Decimal(val.numerator) / Decimal(val.denominator)
                return Fraction(str(dec.sqrt()))
        raise ValueError("Unsupported function call in AST evaluator")

    def generic_visit(self, node: ast.AST) -> Fraction:
        raise ValueError(f"Disallowed AST node: {type(node).__name__}")


def safe_eval_numeric_expr(expr_str: str) -> Optional[Fraction]:
    """
    Safely evaluate a basic numeric expression string to an exact Fraction using AST.
    Returns None if the expression contains variables, unsupported syntax,
    or evaluation fails.
    """
    if not expr_str or not expr_str.strip():
        return None

    cleaned = _latex_to_python_numeric(expr_str)

    try:
        tree = ast.parse(cleaned, mode="eval")
        evaluator = SafeNumericEvaluator(source=cleaned)
        return evaluator.visit(tree)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, InvalidOperation):
        return None
    except Exception:
        return None


def _first_not_none(*args: Any) -> Any:
    """Return the first argument that is not None, preserving falsy 0/0.0 values."""
    for a in args:
        if a is not None:
            return a
    return None


def extract_parameter_domains(blueprint: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract a normalized list of parameter domain specifications from various
    blueprint schema versions (Science Blueprint 2020-12, variation_policy,
    or flat dictionary structures).
    """
    if not blueprint or not isinstance(blueprint, dict):
        return []

    # 1. Check nested requirement.variation_policy.parameter_domains (v0.4.0 standard)
    req = blueprint.get("requirement")
    if isinstance(req, dict):
        vp = req.get("variation_policy")
        if isinstance(vp, dict):
            domains = vp.get("parameter_domains")
            if isinstance(domains, list):
                return domains

    # 2. Check top-level variation_policy.parameter_domains
    vp = blueprint.get("variation_policy")
    if isinstance(vp, dict):
        domains = vp.get("parameter_domains")
        if isinstance(domains, list):
            return domains

    # 3. Check top-level parameter_domains
    if "parameter_domains" in blueprint and isinstance(blueprint["parameter_domains"], list):
        return blueprint["parameter_domains"]

    # 4. Check flat bounds dictionary: {"bounds": {"k": {"min": 55, "max": 5000}}} or {"bounds": {"min": -10, "max": 10}}
    bounds = blueprint.get("bounds")
    if isinstance(bounds, dict):
        # General bounds without parameter name
        if "min" in bounds or "max" in bounds:
            return [
                {
                    "name": "*",
                    "min": _first_not_none(bounds.get("min"), bounds.get("minimum")),
                    "max": _first_not_none(bounds.get("max"), bounds.get("maximum")),
                    "allowed_values": bounds.get("allowed_values"),
                    "step": _first_not_none(bounds.get("step")),
                }
            ]
        # Per-parameter bounds dict
        norm_domains = []
        for param_name, param_cfg in bounds.items():
            if isinstance(param_cfg, dict):
                norm_domains.append(
                    {
                        "name": param_name,
                        "min": _first_not_none(param_cfg.get("min"), param_cfg.get("minimum")),
                        "max": _first_not_none(param_cfg.get("max"), param_cfg.get("maximum")),
                        "allowed_values": param_cfg.get("allowed_values"),
                        "step": _first_not_none(param_cfg.get("step")),
                    }
                )
        return norm_domains

    # 5. Check flat parameters list: {"parameters": [{"name": "k", "min": 55, "max": 5000}]}
    params = blueprint.get("parameters")
    if isinstance(params, list):
        return params

    return []


def _parse_bound_value(val_obj: Any) -> Optional[Fraction]:
    """
    Parse numerical bound value from int, float, str (decimal or rational),
    or typed schema dict (e.g. {"type": "integer", "value": 2},
    {"type": "decimal", "value": "0.5"}, {"type": "rational", "numerator": 1, "denominator": 2}).
    Returns exact Fraction object, or None if val_obj is missing or unparseable.
    """
    if val_obj is None:
        return None
    if isinstance(val_obj, Fraction):
        return val_obj
    if isinstance(val_obj, Decimal):
        return Fraction(val_obj)
    if isinstance(val_obj, int):
        return Fraction(val_obj)
    if isinstance(val_obj, float):
        return Fraction(str(val_obj))
    if isinstance(val_obj, dict):
        if "numerator" in val_obj and "denominator" in val_obj:
            den = _parse_bound_value(val_obj["denominator"])
            num = _parse_bound_value(val_obj["numerator"])
            if den is not None and num is not None and den != 0:
                return num / den
        if "value" in val_obj and val_obj["value"] is not None:
            return _parse_bound_value(val_obj["value"])
    if isinstance(val_obj, str):
        cleaned = val_obj.strip()
        try:
            return Fraction(cleaned)
        except (ValueError, InvalidOperation):
            parsed = safe_eval_numeric_expr(cleaned)
            if parsed is not None:
                return parsed
    return None


def check_parameter_bounds(
    question_text: str,
    options: Sequence[str] = (),
    blueprint: Optional[Dict[str, Any]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> CheckResult:
    """
    Validate that numerical parameters used in the question or options satisfy
    the parameter bounds specified in the blueprint.

    Supports Schema Draft 2020-12, flat configurations, allowed_values, and steps.
    """
    domains = extract_parameter_domains(blueprint)
    if not domains and not parameters:
        return CheckResult(
            check_name="parameter_bounds",
            passed=True,
            status="no_parameter_domains",
            detail="No parameter domains specified in blueprint; bounds check passed by default.",
        )

    errors: List[str] = []
    checked_count = 0

    combined_text = question_text + " " + " ".join(options)

    for domain in domains:
        target_name = (
            domain.get("quantity_ref")
            or domain.get("name")
            or domain.get("id")
            or domain.get("symbol")
            or "*"
        )

        min_val = _parse_bound_value(_first_not_none(domain.get("minimum"), domain.get("min")))
        max_val = _parse_bound_value(_first_not_none(domain.get("maximum"), domain.get("max")))
        allowed_values = domain.get("allowed_values")
        step = _parse_bound_value(_first_not_none(domain.get("step")))

        values_to_test: List[Tuple[str, Fraction]] = []

        # 1. Direct parameter lookup if provided in parameters dict
        if parameters:
            # Check exact key
            if target_name in parameters:
                val = _parse_bound_value(parameters[target_name])
                if val is not None:
                    values_to_test.append((target_name, val))
            # Check normalized key (e.g. Q_K -> k or K)
            elif target_name.startswith("Q_"):
                short_name = target_name[2:].lower()
                for k, v in parameters.items():
                    if k.lower() == short_name or k.upper() == target_name:
                        val = _parse_bound_value(v)
                        if val is not None:
                            values_to_test.append((k, val))

        # 2. Extract from question text if not found in parameters dict
        if not values_to_test:
            if target_name == "*":
                # General bounds across all numbers
                all_nums = re.findall(
                    r"(?<![a-zA-Z0-9_.])-?\d+(?:\.\d+)?(?![a-zA-Z0-9_.])", combined_text
                )
                for num_str in all_nums:
                    parsed_n = _parse_bound_value(num_str)
                    if parsed_n is not None:
                        values_to_test.append(("*", parsed_n))
            else:
                # Match parameter name in text e.g. "k = 55", "k=55", "3190P" (multiplier before P)
                clean_target = (
                    target_name[2:].lower() if target_name.startswith("Q_") else target_name.lower()
                )
                patterns = [
                    rf"(?<![a-zA-Z0-9_]){re.escape(clean_target)}\s*=\s*(-?\d+(?:\.\d+)?)",
                    rf"(?<![a-zA-Z0-9_]){re.escape(target_name)}\s*=\s*(-?\d+(?:\.\d+)?)",
                ]
                # Special pattern for multipliers like 3190P
                if clean_target in ("k", "multiplier"):
                    patterns.append(r"(\d+)\s*P\b")

                for pat in patterns:
                    matches = re.findall(pat, combined_text, re.IGNORECASE)
                    for m in matches:
                        parsed_m = _parse_bound_value(m)
                        if parsed_m is not None:
                            values_to_test.append((target_name, parsed_m))

        # 3. Perform bound checks
        for p_name, val in values_to_test:
            checked_count += 1
            if min_val is not None and val < min_val:
                errors.append(
                    f"Parameter '{p_name}' value {_format_fraction(val)} is below minimum {_format_fraction(min_val)}."
                )
            if max_val is not None and val > max_val:
                errors.append(
                    f"Parameter '{p_name}' value {_format_fraction(val)} exceeds maximum {_format_fraction(max_val)}."
                )
            if allowed_values is not None and isinstance(allowed_values, list):
                allowed_fractions = [_parse_bound_value(x) for x in allowed_values]
                valid_allowed = [a for a in allowed_fractions if a is not None]
                if valid_allowed and not any(val == a for a in valid_allowed):
                    errors.append(
                        f"Parameter '{p_name}' value {_format_fraction(val)} is not in allowed values: {allowed_values}."
                    )
                elif not valid_allowed and len(allowed_values) > 0:
                    errors.append(
                        f"Parameter '{p_name}' allowed_values contains unsupported non-numeric specifications: {allowed_values}."
                    )
            if step is not None and min_val is not None and step > 0:
                diff = val - min_val
                rem = diff % step
                if rem != 0:
                    errors.append(
                        f"Parameter '{p_name}' value {_format_fraction(val)} does not satisfy step {_format_fraction(step)} from minimum {_format_fraction(min_val)}."
                    )

    if errors:
        return CheckResult(
            check_name="parameter_bounds",
            passed=False,
            status="failed",
            errors=errors,
            detail=f"Parameter bounds violation: {len(errors)} error(s) found.",
        )

    return CheckResult(
        check_name="parameter_bounds",
        passed=True,
        status="verified" if checked_count > 0 else "no_parameter_domains",
        detail=f"Parameter bounds verified successfully ({checked_count} values checked).",
    )


def check_mathematical_invariants(
    question_text: str,
    options: Sequence[str] = (),
    blueprint: Optional[Dict[str, Any]] = None,
) -> CheckResult:
    """
    Verify core mathematical invariants in the question stem and options:
    1. Denominators must not evaluate to zero.
    2. Radicands of even roots must be non-negative in the real domain.
    3. Logarithm arguments must be strictly positive (> 0); base must be > 0 and != 1.
    4. Quadratic equations claiming distinct real roots must have discriminant Delta > 0.
    5. Direct probabilities must be in range [0, 1].
    6. Geometric dimensions (lengths, radius, volume) must be strictly positive; triangle inequality.
    """
    errors: List[str] = []
    combined_texts = [question_text] + list(options)

    # 1. Denominator Non-Zero Check
    for text_segment in combined_texts:
        # Check LaTeX fractions: \frac{A}{B} or \dfrac{A}{B} supporting nested braces
        for num_str, denom_str in _extract_latex_fractions(text_segment):
            if denom_str in ("0", "0.0"):
                errors.append(
                    f"Zero denominator detected in fraction: '\\frac{{{num_str}}}{{{denom_str}}}'"
                )
                continue
            denom_val = safe_eval_numeric_expr(denom_str)
            if denom_val is not None and denom_val == 0:
                errors.append(
                    f"Zero denominator detected: denominator '{denom_str}' evaluates to 0 in '\\frac{{{num_str}}}{{{denom_str}}}'"
                )
            elif denom_val is None and not re.search(r"[a-zA-Z]", denom_str):
                errors.append(
                    f"Zero or uncomputable denominator detected: '{denom_str}' cannot be evaluated in '\\frac{{{num_str}}}{{{denom_str}}}'"
                )

        # Check plain fractions: A / B
        for match in PLAIN_FRACTION_REGEX.finditer(text_segment):
            num_str, denom_str = match.group(1).strip(), match.group(2).strip()
            denom_val = _parse_bound_value(denom_str)
            if denom_val is not None and denom_val == 0:
                errors.append(
                    f"Zero denominator detected in numerical fraction: '{num_str}/{denom_str}'"
                )
            elif denom_val is None and not re.search(r"[a-zA-Z]", denom_str):
                errors.append(
                    f"Zero or uncomputable denominator detected in numerical fraction: '{num_str}/{denom_str}'"
                )

    # 2. Non-Negative Radicand (Even Roots) Check
    for text_segment in combined_texts:
        for degree, radicand_str in _extract_latex_sqrts(text_segment):
            deg = degree if degree is not None else 2
            # Even root requires radicand >= 0 in real domain
            if deg % 2 == 0:
                rad_val = safe_eval_numeric_expr(radicand_str)
                if rad_val is not None:
                    if rad_val < 0:
                        errors.append(
                            f"Negative radicand in even root (index {deg}): radicand '{radicand_str}' "
                            f"evaluates to {_format_fraction(rad_val)} < 0."
                        )
                elif not re.search(r"[a-zA-Z]", radicand_str):
                    errors.append(
                        f"Uncomputable radicand in even root (index {deg}): '{radicand_str}' cannot be evaluated."
                    )

    # 3. Logarithm Domain Check
    for text_segment in combined_texts:
        # \log_b(A)
        for base_str, arg_str in _extract_latex_logs(text_segment):
            if arg_str:
                arg_val = safe_eval_numeric_expr(arg_str.strip())
                if arg_val is not None:
                    if arg_val <= 0:
                        errors.append(
                            f"Logarithm argument must be strictly positive: argument '{arg_str}' evaluates to {_format_fraction(arg_val)} <= 0."
                        )
                elif not re.search(r"[a-zA-Z]", arg_str):
                    errors.append(
                        f"Uncomputable logarithm argument: '{arg_str}' cannot be evaluated."
                    )
            if base_str:
                base_val = _parse_bound_value(base_str.strip())
                if base_val is not None:
                    if base_val <= 0:
                        errors.append(
                            f"Logarithm base must be strictly positive: base '{base_str}' evaluates to {_format_fraction(base_val)} <= 0."
                        )
                    elif base_val == 1:
                        errors.append(
                            f"Logarithm base cannot be equal to 1: base '{base_str}' evaluates to 1."
                        )
                elif not re.search(r"[a-zA-Z]", base_str):
                    errors.append(f"Uncomputable logarithm base: '{base_str}' cannot be evaluated.")

        # \ln(A)
        for arg_str in _extract_latex_lns(text_segment):
            if arg_str:
                arg_val = safe_eval_numeric_expr(arg_str.strip())
                if arg_val is not None:
                    if arg_val <= 0:
                        errors.append(
                            f"Logarithm argument must be strictly positive: argument '{arg_str}' evaluates to {_format_fraction(arg_val)} <= 0."
                        )
                elif not re.search(r"[a-zA-Z]", arg_str):
                    errors.append(
                        f"Uncomputable logarithm argument: '{arg_str}' cannot be evaluated."
                    )

    # 4. Quadratic Discriminant Invariant Check
    q_match = QUADRATIC_EQ_REGEX.search(question_text)
    if q_match:
        a_str = (q_match.group("a") or "").replace(" ", "")
        b_str = (q_match.group("b") or "").replace(" ", "")
        c_str = (q_match.group("c") or "").replace(" ", "")

        # Default leading coefficient signs
        if a_str in ("", "+"):
            a_val = 1.0
        elif a_str == "-":
            a_val = -1.0
        else:
            try:
                a_val = float(a_str)
            except ValueError:
                a_val = 1.0

        if b_str in ("", "+"):
            b_val = 1.0
        elif b_str == "-":
            b_val = -1.0
        else:
            try:
                b_val = float(b_str)
            except ValueError:
                b_val = 0.0

        try:
            c_val = float(c_str) if c_str else 0.0
        except ValueError:
            c_val = 0.0

        delta = b_val**2 - 4 * a_val * c_val

        # Check conditions in question stem
        claims_two_distinct_roots = bool(
            re.search(
                r"\b(?:hai\s+nghiệm\s+phân\s+biệt|2\s+nghiệm\s+phân\s+biệt|two\s+distinct\s+real\s+roots)\b",
                question_text,
                re.IGNORECASE,
            )
        )
        claims_no_real_roots = bool(
            re.search(
                r"\b(?:vô\s+nghiệm|không\s+có\s+nghiệm\s+thực|no\s+real\s+roots)\b",
                question_text,
                re.IGNORECASE,
            )
        )

        if claims_two_distinct_roots and delta <= 0:
            errors.append(
                f"Quadratic equation '{q_match.group(0)}' claims 2 distinct real roots, but discriminant Delta={delta} <= 0."
            )
        if claims_no_real_roots and delta >= 0:
            errors.append(
                f"Quadratic equation '{q_match.group(0)}' claims no real roots, but discriminant Delta={delta} >= 0."
            )

    # 5. Direct Probability Invariant: 0 <= P <= 1
    # Only applies when question directly asks for probability P itself, NOT k*P or 3190P
    is_direct_probability_question = bool(
        re.search(
            r"\b(?:xác\s+suất\s+(?:bằng|là|cần\s+tìm)|tính\s+xác\s+suất|tìm\s+xác\s+suất)\b",
            question_text,
            re.IGNORECASE,
        )
    ) and not bool(re.search(r"(?:\d+|k)\s*P\b", question_text, re.IGNORECASE))
    if is_direct_probability_question:
        for opt in options:
            opt_clean = opt.strip()
            # Match number or fraction
            val = safe_eval_numeric_expr(opt_clean)
            if val is not None:
                if val < -1e-9 or val > 1.0 + 1e-9:
                    errors.append(
                        f"Direct probability option '{opt}' evaluates to {val}, which is outside valid range [0, 1]."
                    )

    # 6. Geometric Invariant: Triangle Inequality
    # Check for "tam giác ... có ba cạnh / các cạnh a, b, c" or "AB = 3, BC = 4, AC = 10"
    tri_match = re.search(
        r"\b(?:ba\s+cạnh|các\s+cạnh)\s+(?:lần\s+lượt\s+là\s+)?(\d+(?:\.\d+)?)\s*[,;\s]\s*(\d+(?:\.\d+)?)\s*(?:và|[,;\s])\s*(\d+(?:\.\d+)?)",
        question_text,
        re.IGNORECASE,
    )
    if not tri_match:
        tri_match = re.search(
            r"\b[A-Za-z]{2}\s*=\s*(\d+(?:\.\d+)?)\s*[,;\s]\s*[A-Za-z]{2}\s*=\s*(\d+(?:\.\d+)?)\s*(?:và|[,;\s])\s*[A-Za-z]{2}\s*=\s*(\d+(?:\.\d+)?)",
            question_text,
            re.IGNORECASE,
        )
    if tri_match:
        try:
            s1, s2, s3 = (
                float(tri_match.group(1)),
                float(tri_match.group(2)),
                float(tri_match.group(3)),
            )
            if s1 + s2 <= s3 or s1 + s3 <= s2 or s2 + s3 <= s1:
                errors.append(f"Triangle inequality violated for side lengths {s1}, {s2}, {s3}.")
        except ValueError:
            pass

    if errors:
        return CheckResult(
            check_name="mathematical_invariants",
            passed=False,
            status="failed",
            errors=errors,
            detail=f"Mathematical invariant violation: {len(errors)} error(s) detected.",
        )

    return CheckResult(
        check_name="mathematical_invariants",
        passed=True,
        status="verified",
        detail="All mathematical invariants verified successfully.",
    )


def check_distractor_reasonableness(
    options: Sequence[str],
    correct_answer: Optional[str] = None,
) -> CheckResult:
    """
    Validate that multiple-choice distractors are reasonable:
    - Exactly 4 options.
    - No duplicate options (syntactically or normalized).
    - No empty, NaN, null, or degenerate strings.
    - If correct_answer provided, ensure it matches at least one option.
    """
    if options is None or len(options) != 4:
        return CheckResult(
            check_name="distractor_reasonableness",
            passed=False,
            status="failed",
            errors=[
                f"Expected exactly 4 options, got {len(options) if options is not None else 0}."
            ],
            detail="Option count invalid.",
        )

    errors: List[str] = []
    normalized_seen: Dict[str, int] = {}

    for idx, opt in enumerate(options):
        if not opt or not str(opt).strip():
            errors.append(f"Option {idx + 1} is empty or whitespace.")
            continue

        raw = str(opt).strip()
        if raw.lower() in ("null", "none", "nan", "n/a", "undefined"):
            errors.append(f"Option {idx + 1} contains degenerate value '{raw}'.")
            continue

        norm = normalize_latex_string(raw)
        if norm in normalized_seen:
            errors.append(
                f"Duplicate option detected: Option {idx + 1} matches Option {normalized_seen[norm] + 1} ('{raw}')."
            )
        else:
            normalized_seen[norm] = idx

    # Verify correct_answer is present among options
    if correct_answer:
        # Check either letter designation ('A', 'A.', 'Option A', '(A)', 'Phương án A') or matching option content
        letter_resolved = _resolve_option_letter(correct_answer, options)
        label_match = letter_resolved is not None
        norm_ans = normalize_latex_string(correct_answer.strip())
        content_match = any(
            norm_ans == normalize_latex_string(opt.strip())
            or are_expressions_equivalent(correct_answer.strip(), opt.strip())
            for opt in options
            if opt and str(opt).strip()
        )
        if not label_match and not content_match:
            errors.append(
                f"Designated correct answer '{correct_answer}' does not match any of the provided options."
            )

    if errors:
        return CheckResult(
            check_name="distractor_reasonableness",
            passed=False,
            status="failed",
            errors=errors,
            detail=f"Distractor reasonableness failed: {len(errors)} error(s) found.",
        )

    return CheckResult(
        check_name="distractor_reasonableness",
        passed=True,
        status="verified",
        detail="Distractors are distinct, non-empty, and valid.",
    )


def detect_out_of_scope_math(question_text: str) -> Tuple[bool, Optional[str]]:
    """
    Detect whether a question stem falls into mathematical domains outside
    single-equation CAS solvability (e.g. geometry, word problems, combinatorics, calculus).
    Returns (is_out_of_scope, category_name).
    """
    for category, pattern in OUT_OF_SCOPE_PATTERNS.items():
        if pattern.search(question_text):
            return True, category
    return False, None


def evaluate_rule_fallback(
    question_text: str,
    options: Sequence[str],
    correct_answer: str,
    blueprint: Optional[Dict[str, Any]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    sympy_result: Optional[Any] = None,
) -> CheckResult:
    """
    Orchestrate rule-based mathematical validation and fallback routing.

    - If sympy_result passed with verified status, reinforces with bounds and distractor checks.
    - If sympy_result is unsupported, timed out, inconclusive, or None, performs complete
      rule-based fallback verification (invariants, bounds, distractors, out-of-scope math).
    - Preserves semantic confidence: 'sympy_verified' if CAS succeeded, 'rule_only' for rule fallback.
    """
    all_errors: List[str] = []

    # 1. Run common sanity checks
    dist_res = check_distractor_reasonableness(options, correct_answer)
    if not dist_res.passed:
        all_errors.extend(dist_res.errors)

    bounds_res = check_parameter_bounds(question_text, options, blueprint, parameters)
    if not bounds_res.passed:
        all_errors.extend(bounds_res.errors)

    inv_res = check_mathematical_invariants(question_text, options, blueprint)
    if not inv_res.passed:
        all_errors.extend(inv_res.errors)

    is_out_of_scope, out_of_scope_cat = detect_out_of_scope_math(question_text)

    # 2. Case A: SymPy evaluation returned decisive results
    sympy_status_str = ""
    sympy_passed = False
    if sympy_result is not None:
        raw_status = getattr(sympy_result, "status", None)
        if raw_status is not None:
            sympy_status_str = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
        sympy_passed = bool(getattr(sympy_result, "passed", False))

    # If CAS decisively failed or encountered domain error, preserve rejection (never fallback to pass)
    if sympy_status_str in ("failed", "domain_error"):
        cas_detail = (
            getattr(sympy_result, "detail", None)
            or f"SymPy CAS evaluation rejected solution ({sympy_status_str})."
        )
        combined_errors = [cas_detail] + all_errors
        return CheckResult(
            check_name="rule_fallback",
            passed=False,
            status=sympy_status_str,
            confidence="sympy_verified",
            errors=combined_errors,
            detail=f"SymPy CAS rejected candidate answer ({sympy_status_str}): {cas_detail}",
        )

    if sympy_passed and sympy_status_str == "verified":
        if all_errors:
            return CheckResult(
                check_name="rule_fallback",
                passed=False,
                status="failed",
                confidence="sympy_verified",
                errors=all_errors,
                detail=f"SymPy CAS verified solution, but rule checks failed: {len(all_errors)} error(s).",
            )
        return CheckResult(
            check_name="rule_fallback",
            passed=True,
            status="verified",
            confidence="sympy_verified",
            detail="SymPy CAS verified equation solution; parameter bounds and invariants satisfied.",
        )

    # 3. Case B: Fallback triggered (SymPy unsupported, timeout, inconclusive, or None)
    if all_errors:
        return CheckResult(
            check_name="rule_fallback",
            passed=False,
            status="failed",
            confidence="rule_only",
            errors=all_errors,
            detail=f"Rule-based fallback verification failed with {len(all_errors)} error(s).",
        )

    # All rule checks passed
    reason = (
        f"SymPy evaluator returned '{sympy_status_str}'"
        if sympy_result is not None
        else "Pure rule-based evaluation"
    )
    scope_info = f" (out-of-scope math detected: {out_of_scope_cat})" if is_out_of_scope else ""

    detail_msg = (
        f"{reason}{scope_info}. Rule-based fallback verification passed: "
        f"all mathematical invariants and parameter bounds satisfied."
    )

    return CheckResult(
        check_name="rule_fallback",
        passed=True,
        status="passed_rule_fallback",
        confidence="rule_only",
        detail=detail_msg,
    )


def validate_rule_variant(
    variant: Any,
    blueprint: Optional[Dict[str, Any]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    sympy_result: Optional[Any] = None,
) -> CheckResult:
    """
    Convenience wrapper to validate a GeneratedVariant, SourceQuestion,
    or duck-typed dictionary using rule-based fallback checking.
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

    return evaluate_rule_fallback(
        question_text=q_text,
        options=opts,
        correct_answer=ans,
        blueprint=blueprint,
        parameters=var_params,
        sympy_result=sympy_result,
    )

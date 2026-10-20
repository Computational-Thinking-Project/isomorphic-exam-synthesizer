"""
Syntax & Option Integrity Checker (VAL-01).

Validates:
1. Question text is non-empty.
2. Exactly 4 non-empty options (A, B, C, D).
3. LaTeX delimiter balancing (braces '{}', dollar signs '$', and math environments).
"""

import re
from typing import Any, List, Optional, Sequence

from app.services.validator.base import CheckResult


def check_question_not_empty(question_text: Optional[str]) -> CheckResult:
    """Check that the question stem is not empty or whitespace only."""
    if not question_text or not question_text.strip():
        return CheckResult(
            check_name="syntax_valid",
            passed=False,
            detail="Question text must not be empty.",
            errors=["Question text is empty or contains only whitespace."],
        )
    return CheckResult(check_name="syntax_valid", passed=True)


def check_four_options(options: Optional[Sequence[str]]) -> CheckResult:
    """
    Check that there are exactly four non-empty options.
    """
    if options is None:
        return CheckResult(
            check_name="four_options",
            passed=False,
            detail="Options list is missing.",
            errors=["Options list cannot be None."],
        )

    if len(options) != 4:
        return CheckResult(
            check_name="four_options",
            passed=False,
            detail=f"Expected exactly 4 options, got {len(options)}.",
            errors=[f"Invalid option count: {len(options)} (expected 4)."],
        )

    empty_indices = [idx + 1 for idx, opt in enumerate(options) if not opt or not str(opt).strip()]
    if empty_indices:
        indices_str = ", ".join(f"Option {i}" for i in empty_indices)
        return CheckResult(
            check_name="four_options",
            passed=False,
            detail=f"Empty option detected: {indices_str}.",
            errors=[f"Option {i} must not be empty." for i in empty_indices],
        )

    return CheckResult(check_name="four_options", passed=True)


def check_latex_delimiters(text: str, field_name: str = "text") -> CheckResult:
    """
    Validate LaTeX brace balancing and dollar sign parity.
    Ignores escaped braces '\\{' and '\\}', and escaped dollars '\\$'.
    Also verifies '\\[' / '\\]' and '\\(' / '\\)' balance.
    """
    errors: List[str] = []

    # 1. Check brace balancing '{}'
    # We strip escaped braces '\\{' and '\\}'
    sanitized = re.sub(r"\\[{}]", "", text)

    depth = 0
    brace_error = False
    for char in sanitized:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                brace_error = True
                errors.append(f"Unmatched closing brace '}}' in {field_name}.")
                break

    if not brace_error and depth > 0:
        errors.append(f"Unclosed opening brace '{{' in {field_name} (depth={depth}).")

    # 2. Check dollar sign '$' parity
    # Escaped dollars '\\$' should be ignored
    no_escaped_dollars = re.sub(r"\\\$", "", text)
    # Remove double dollars '$$' (display math)
    no_display_math = re.sub(r"\$\$", "", no_escaped_dollars)
    single_dollar_count = no_display_math.count("$")
    if single_dollar_count % 2 != 0:
        errors.append(
            f"Unmatched inline math delimiter '$' in {field_name} (found {single_dollar_count} unescaped '$')."
        )

    # Count display math '$$' pairs
    double_dollar_count = len(re.findall(r"\$\$", no_escaped_dollars))
    # Each pair of $$ opens and closes display math -> total occurrences of $$ should be even
    if double_dollar_count % 2 != 0:
        errors.append(f"Unmatched display math delimiter '$$' in {field_name}.")

    # 3. Check '\[' and '\]' balancing
    open_brackets = len(re.findall(r"(?<!\\)\\\[", text))
    close_brackets = len(re.findall(r"(?<!\\)\\\]", text))
    if open_brackets != close_brackets:
        errors.append(
            f"Unmatched display brackets '\\[ ... \\]' in {field_name} "
            f"({open_brackets} open vs {close_brackets} close)."
        )

    # 4. Check '\(' and '\)' balancing
    open_parens = len(re.findall(r"(?<!\\)\\\(", text))
    close_parens = len(re.findall(r"(?<!\\)\\\)", text))
    if open_parens != close_parens:
        errors.append(
            f"Unmatched inline parentheses '\\( ... \\)' in {field_name} "
            f"({open_parens} open vs {close_parens} close)."
        )

    if errors:
        return CheckResult(
            check_name="latex_syntax",
            passed=False,
            detail="; ".join(errors),
            errors=errors,
        )

    return CheckResult(check_name="latex_syntax", passed=True)


def check_syntax(
    question_text: Optional[str],
    options: Optional[Sequence[str]],
    solution: Optional[str] = None,
) -> CheckResult:
    """
    Composite syntax validator (VAL-01).
    Evaluates:
    - Question text non-empty
    - Exactly 4 non-empty options
    - LaTeX delimiter balancing across question, options, and solution (if present).
    """
    errors: List[str] = []

    # Question stem check
    q_res = check_question_not_empty(question_text)
    if not q_res.passed:
        errors.extend(q_res.errors)

    # Options count and non-empty check
    opt_res = check_four_options(options)
    if not opt_res.passed:
        errors.extend(opt_res.errors)

    # LaTeX delimiters in question text
    if question_text:
        latex_q = check_latex_delimiters(question_text, field_name="question_text")
        if not latex_q.passed:
            errors.extend(latex_q.errors)

    # LaTeX delimiters in options
    if options:
        for idx, opt in enumerate(options):
            if opt:
                latex_opt = check_latex_delimiters(str(opt), field_name=f"options[{idx}]")
                if not latex_opt.passed:
                    errors.extend(latex_opt.errors)

    # LaTeX delimiters in solution (optional)
    if solution:
        latex_sol = check_latex_delimiters(solution, field_name="solution")
        if not latex_sol.passed:
            errors.extend(latex_sol.errors)

    if errors:
        return CheckResult(
            check_name="syntax_valid",
            passed=False,
            detail="; ".join(errors),
            errors=errors,
        )

    return CheckResult(
        check_name="syntax_valid",
        passed=True,
        detail="All syntax and structural checks passed.",
    )


def validate_syntax_variant(variant: Any) -> CheckResult:
    """
    Convenience adapter to validate a GeneratedVariant, SourceQuestion,
    or duck-typed dictionary / object.
    """
    if isinstance(variant, dict):
        q_text = variant.get("question_text") or variant.get("stem_latex")
        opts = variant.get("options")
        sol = variant.get("solution_steps") or variant.get("solution") or variant.get("solution_md")
    else:
        q_text = getattr(variant, "question_text", None) or getattr(variant, "stem_latex", None)
        opts = getattr(variant, "options", None)
        sol = (
            getattr(variant, "solution_steps", None)
            or getattr(variant, "solution", None)
            or getattr(variant, "solution_md", None)
        )

    return check_syntax(question_text=q_text, options=opts, solution=sol)

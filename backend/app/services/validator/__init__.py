"""
Validator package for Isomorphic Exam Synthesizer.

Exports:
- Base CheckResult
- Syntax and logic validation checkers (TASK-107a: VAL-01, VAL-02)
- Isolated process runner with hard timeout (process_runner)
- SymPy Mathematical Evaluator (VAL-03 / TASK-107b)
"""

from app.services.validator.base import CheckResult
from app.services.validator.logic_checker import (
    are_expressions_equivalent,
    check_designated_answer,
    check_duplicate_options,
    check_logic,
    normalize_latex_string,
    validate_logic_variant,
)
from app.services.validator.process_runner import ProcessResult, run_with_timeout
from app.services.validator.sympy_evaluator import (
    DEFAULT_EVALUATION_TIMEOUT,
    MAX_EXPRESSION_LENGTH,
    EvaluationResult,
    EvaluationStatus,
    clean_latex,
    extract_equation_from_text,
    parse_to_sympy,
    verify_equation_solution,
    verify_question_math,
    verify_variant_math,
)
from app.services.validator.syntax_checker import (
    check_four_options,
    check_latex_delimiters,
    check_question_not_empty,
    check_syntax,
    validate_syntax_variant,
)

__all__ = [
    "CheckResult",
    "check_question_not_empty",
    "check_four_options",
    "check_latex_delimiters",
    "check_syntax",
    "validate_syntax_variant",
    "check_designated_answer",
    "check_duplicate_options",
    "check_logic",
    "validate_logic_variant",
    "are_expressions_equivalent",
    "normalize_latex_string",
    "ProcessResult",
    "run_with_timeout",
    "EvaluationStatus",
    "EvaluationResult",
    "MAX_EXPRESSION_LENGTH",
    "DEFAULT_EVALUATION_TIMEOUT",
    "clean_latex",
    "parse_to_sympy",
    "extract_equation_from_text",
    "verify_equation_solution",
    "verify_question_math",
    "verify_variant_math",
]

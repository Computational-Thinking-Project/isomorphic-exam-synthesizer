"""
Validator package for Isomorphic Exam Synthesizer.

Exports:
- Base CheckResult
- Isolated process runner with hard timeout (process_runner)
- SymPy Mathematical Evaluator (VAL-03 / TASK-107b)
"""

from app.services.validator.base import CheckResult
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

__all__ = [
    "CheckResult",
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

"""
Validator package for Isomorphic Exam Synthesizer.

Exports syntax and logic validation checkers (TASK-107a: VAL-01, VAL-02).
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
]

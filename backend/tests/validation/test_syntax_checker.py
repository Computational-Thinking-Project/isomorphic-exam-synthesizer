"""
Unit tests for Syntax & Option Integrity Checker (VAL-01 / TASK-107a).
"""

from app.models.schemas import GeneratedVariant, SourceQuestion
from app.services.validator.syntax_checker import (
    check_four_options,
    check_latex_delimiters,
    check_question_not_empty,
    check_syntax,
    validate_syntax_variant,
)


class TestQuestionNotEmpty:
    def test_non_empty_question(self):
        result = check_question_not_empty("Giải phương trình $x^2 - 4 = 0$?")
        assert result.passed is True
        assert bool(result) is True
        assert result.check_name == "syntax_valid"

    def test_empty_string(self):
        result = check_question_not_empty("")
        assert result.passed is False
        assert bool(result) is False
        assert "empty" in result.detail.lower()

    def test_whitespace_string(self):
        result = check_question_not_empty("   \t \n  ")
        assert result.passed is False
        assert "empty" in result.detail.lower()

    def test_none_question(self):
        result = check_question_not_empty(None)
        assert result.passed is False


class TestFourOptions:
    def test_exactly_four_valid_options(self):
        options = ["$1$", "$2$", "$3$", "$4$"]
        result = check_four_options(options)
        assert result.passed is True
        assert result.check_name == "four_options"

    def test_too_few_options(self):
        options = ["$1$", "$2$", "$3$"]
        result = check_four_options(options)
        assert result.passed is False
        assert "expected exactly 4" in result.detail.lower()

    def test_too_many_options(self):
        options = ["$1$", "$2$", "$3$", "$4$", "$5$"]
        result = check_four_options(options)
        assert result.passed is False
        assert "expected exactly 4" in result.detail.lower()

    def test_none_options(self):
        result = check_four_options(None)
        assert result.passed is False

    def test_empty_option_inside_four(self):
        options = ["$1$", "", "$3$", "$4$"]
        result = check_four_options(options)
        assert result.passed is False
        assert "empty option" in result.detail.lower()
        assert "Option 2" in result.detail

    def test_whitespace_option_inside_four(self):
        options = ["$1$", "$2$", "   ", "$4$"]
        result = check_four_options(options)
        assert result.passed is False
        assert "Option 3" in result.detail


class TestLaTeXDelimiters:
    def test_balanced_braces(self):
        text = r"\frac{a + b}{c} + \sqrt{x^2 + 1}"
        result = check_latex_delimiters(text)
        assert result.passed is True

    def test_escaped_braces(self):
        text = r"Tập hợp \{1, 2, 3\} có 3 phần tử"
        result = check_latex_delimiters(text)
        assert result.passed is True

    def test_unclosed_opening_brace(self):
        text = r"\frac{a + b}{c"
        result = check_latex_delimiters(text)
        assert result.passed is False
        assert "unclosed opening brace" in result.detail.lower()

    def test_unmatched_closing_brace(self):
        text = r"x + 1} = 0"
        result = check_latex_delimiters(text)
        assert result.passed is False
        assert "unmatched closing brace" in result.detail.lower()

    def test_balanced_dollar_signs(self):
        text = "Cho phương trình $x^2 - 5x + 6 = 0$. Tìm nghiệm?"
        result = check_latex_delimiters(text)
        assert result.passed is True

    def test_escaped_dollar_signs(self):
        text = r"Giá tiền là \$100 và công thức $x = 1$."
        result = check_latex_delimiters(text)
        assert result.passed is True

    def test_unmatched_dollar_sign(self):
        text = "Phương trình $x^2 - 1 = 0 không đóng dấu dollar"
        result = check_latex_delimiters(text)
        assert result.passed is False
        assert "unmatched inline math delimiter" in result.detail.lower()

    def test_display_math_double_dollars(self):
        text = r"Công thức: $$\sum_{i=1}^n i = \frac{n(n+1)}{2}$$"
        result = check_latex_delimiters(text)
        assert result.passed is True

    def test_display_brackets(self):
        text = r"Biểu thức \[ E = mc^2 \]"
        result = check_latex_delimiters(text)
        assert result.passed is True

    def test_unmatched_display_brackets(self):
        text = r"Biểu thức \[ E = mc^2"
        result = check_latex_delimiters(text)
        assert result.passed is False
        assert "unmatched display brackets" in result.detail.lower()

    def test_regression_bracket_order_closing_before_opening(self):
        r"""Regression test: '\] x \[' must fail due to reversed delimiter order."""
        text = r"Biểu thức \] x \["
        result = check_latex_delimiters(text)
        assert result.passed is False
        assert "unmatched closing delimiter" in result.detail.lower()

    def test_regression_mismatched_delimiter_types(self):
        r"""Mismatched brackets like '\[ x \)' must fail."""
        text = r"Biểu thức \[ x \)"
        result = check_latex_delimiters(text)
        assert result.passed is False
        assert "mismatched delimiter" in result.detail.lower()

    def test_regression_nested_valid_delimiters(self):
        """Correctly nested and paired delimiters should pass."""
        text = r"Biểu thức \[ a + \( b \times c \) \]"
        result = check_latex_delimiters(text)
        assert result.passed is True


class TestCompositeSyntaxCheck:
    def test_valid_question_and_options(self):
        q = "Tính tích phân $I = \\int_0^1 x dx$?"
        opts = [r"$\frac{1}{2}$", r"$1$", r"$\frac{1}{3}$", r"$2$"]
        sol = r"Ta có $I = \left. \frac{x^2}{2} \right|_0^1 = \frac{1}{2}$."

        result = check_syntax(question_text=q, options=opts, solution=sol)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_multiple_syntax_errors_collected(self):
        # Empty question + 3 options + unbalanced brace in option 1
        q = ""
        opts = [r"$\frac{1}{2", "$1$", "$2$"]

        result = check_syntax(question_text=q, options=opts)
        assert result.passed is False
        assert len(result.errors) >= 3
        # Ensure errors detail mention question, option count, and brace
        detail = result.detail.lower()
        assert "empty" in detail
        assert "4" in detail

    def test_validate_syntax_variant_model(self):
        variant = GeneratedVariant(
            variant_id="var_01",
            source_question_id="q1",
            question_text="Cho $x^2 - 4x + 3 = 0$. Nghiệm là?",
            options=["$x=1$", "$x=3$", "$x=-1$", "$x=0$"],
            correct_answer="$x=1$",
            solution_steps="Giải $(x-1)(x-3) = 0$.",
            seed=123,
        )
        result = validate_syntax_variant(variant)
        assert result.passed is True

    def test_validate_syntax_source_question_model(self):
        source = SourceQuestion(
            id="src_01",
            question_text="Giải phương trình $2x - 4 = 0$?",
            options=["$x=2$", "$x=1$", "$x=-2$", "$x=4$"],
            correct_answer="$x=2$",
            solution="Ta có $2x = 4 \\implies x = 2$.",
        )
        result = validate_syntax_variant(source)
        assert result.passed is True

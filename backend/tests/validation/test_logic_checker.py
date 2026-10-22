"""
Unit tests for Answer Logic & Duplicate Checker (VAL-02 / TASK-107a).
"""

from app.models.schemas import GeneratedVariant, SourceQuestion
from app.services.validator.logic_checker import (
    are_expressions_equivalent,
    check_designated_answer,
    check_duplicate_options,
    check_logic,
    normalize_latex_string,
    validate_logic_variant,
)


class TestExpressionEquivalence:
    def test_normalize_latex_string(self):
        assert normalize_latex_string(r"$\dfrac{1}{2}$") == r"\frac{1}{2}"
        assert normalize_latex_string(r"$$\frac{a}{b}$$") == r"\frac{a}{b}"
        assert normalize_latex_string(r"\left( x + 1 \right)") == "( x + 1 )"

    def test_identical_strings(self):
        assert are_expressions_equivalent("x + 1", "x + 1") is True
        assert are_expressions_equivalent("$x + 1$", "x + 1") is True

    def test_numeric_float_equivalence(self):
        assert are_expressions_equivalent("0.5", "0.50") is True
        assert are_expressions_equivalent("0.5", r"\frac{1}{2}") is True
        assert are_expressions_equivalent(r"$\dfrac{1}{2}$", "0.5") is True

    def test_algebraic_equivalence(self):
        assert are_expressions_equivalent("x + y", "y + x") is True
        assert are_expressions_equivalent("2*(x + 1)", "2*x + 2") is True

    def test_different_expressions(self):
        assert are_expressions_equivalent("x + 1", "x + 2") is False
        assert are_expressions_equivalent("0.5", "0.25") is False
        assert are_expressions_equivalent("A", "B") is False


class TestDuplicateOptions:
    def test_all_unique_options(self):
        options = ["$1$", "$2$", "$3$", "$4$"]
        result = check_duplicate_options(options)
        assert result.passed is True
        assert result.check_name == "no_duplicates"
        assert len(result.errors) == 0

    def test_textual_duplicate(self):
        options = ["$x=1$", "$x=2$", "$x=1$", "$x=3$"]
        result = check_duplicate_options(options)
        assert result.passed is False
        assert "duplicate" in result.detail.lower()
        assert "Option 1" in result.detail and "Option 3" in result.detail

    def test_macro_duplicate_dfrac_vs_frac(self):
        options = [r"$\dfrac{1}{2}$", r"$\frac{1}{2}$", "$1$", "$2$"]
        result = check_duplicate_options(options)
        assert result.passed is False
        assert "duplicate" in result.detail.lower()

    def test_symbolic_numeric_duplicate_half(self):
        options = ["$0.5$", r"$\frac{1}{2}$", "$1$", "$2$"]
        result = check_duplicate_options(options)
        assert result.passed is False
        assert "duplicate" in result.detail.lower()
        assert "Option 1" in result.detail and "Option 2" in result.detail

    def test_algebraic_symbolic_duplicate(self):
        options = ["$x + 1$", "$1 + x$", "$x - 1$", "$x$"]
        result = check_duplicate_options(options)
        assert result.passed is False
        assert "Option 1" in result.detail and "Option 2" in result.detail

    def test_text_non_math_options_unique(self):
        options = [
            "Hàm số đồng biến trên R",
            "Hàm số nghịch biến trên R",
            "Hàm số đồng biến trên (0; +inf)",
            "Hàm số không đổi",
        ]
        result = check_duplicate_options(options)
        assert result.passed is True

    def test_text_non_math_options_duplicate(self):
        options = [
            "Hàm số đồng biến",
            "Hàm số nghịch biến",
            "Hàm số đồng biến",
            "Hàm số không đổi",
        ]
        result = check_duplicate_options(options)
        assert result.passed is False


class TestDesignatedAnswer:
    def test_exact_match(self):
        options = ["$1$", "$2$", "$3$", "$4$"]
        result = check_designated_answer("$2$", options)
        assert result.passed is True
        assert "Option 2" in result.detail

    def test_normalized_match_without_dollar(self):
        options = [r"$\dfrac{7}{18}$", r"$\dfrac{5}{18}$", r"$\dfrac{1}{3}$", r"$\dfrac{11}{36}$"]
        result = check_designated_answer(r"\frac{7}{18}", options)
        assert result.passed is True
        assert "Option 1" in result.detail

    def test_numeric_equivalence_match(self):
        options = [r"$\frac{1}{2}$", "$1$", "$2$", "$3$"]
        result = check_designated_answer("0.5", options)
        assert result.passed is True
        assert "Option 1" in result.detail

    def test_letter_designation(self):
        options = ["$x=1$", "$x=2$", "$x=3$", "$x=4$"]
        result_a = check_designated_answer("A", options)
        assert result_a.passed is True
        assert "Option 1" in result_a.detail

        result_c = check_designated_answer("C.", options)
        assert result_c.passed is True
        assert "Option 3" in result_c.detail

    def test_answer_not_in_options(self):
        options = ["$1$", "$2$", "$3$", "$4$"]
        result = check_designated_answer("$5$", options)
        assert result.passed is False
        assert "does not match any" in result.detail.lower()

    def test_empty_correct_answer(self):
        options = ["$1$", "$2$", "$3$", "$4$"]
        result = check_designated_answer("", options)
        assert result.passed is False
        assert "empty" in result.detail.lower()

    def test_none_correct_answer(self):
        options = ["$1$", "$2$", "$3$", "$4$"]
        result = check_designated_answer(None, options)
        assert result.passed is False


class TestCompositeLogicCheck:
    def test_valid_options_and_answer(self):
        options = [r"$\frac{7}{18}$", r"$\frac{5}{18}$", r"$\frac{1}{3}$", r"$\frac{11}{36}$"]
        ans = r"$\frac{7}{18}$"
        result = check_logic(options=options, correct_answer=ans)
        assert result.passed is True
        assert result.check_name == "logic_valid"

    def test_duplicate_options_and_missing_answer_combined(self):
        options = ["$1$", "$1$", "$2$", "$3$"]
        ans = "$5$"  # Not in options
        result = check_logic(options=options, correct_answer=ans)
        assert result.passed is False
        assert len(result.errors) >= 2

    def test_validate_logic_variant_model(self):
        variant = GeneratedVariant(
            variant_id="var_q1_v1",
            source_question_id="q1",
            question_text="Xác suất?",
            options=[
                r"$\dfrac{7}{18}$",
                r"$\dfrac{5}{18}$",
                r"$\dfrac{1}{3}$",
                r"$\dfrac{11}{36}$",
            ],
            correct_answer=r"$\dfrac{7}{18}$",
            solution_steps="Giải...",
            seed=42,
        )
        result = validate_logic_variant(variant)
        assert result.passed is True

    def test_validate_logic_source_question_model(self):
        source = SourceQuestion(
            id="src_01",
            question_text="Giải phương trình?",
            options=["$x=1$", "$x=2$", "$x=3$", "$x=4$"],
            correct_answer="$x=1$",
            solution="...",
        )
        result = validate_logic_variant(source)
        assert result.passed is True

    def test_validate_logic_dict_input(self):
        data = {
            "options": ["$a$", "$b$", "$c$", "$d$"],
            "correct_answer": "$a$",
        }
        result = validate_logic_variant(data)
        assert result.passed is True


class TestRegressionPhilipFeedback:
    def test_prevent_rce_via_sympify(self):
        malicious_expr = "__import__('os').system('echo pwned')"
        assert are_expressions_equivalent(malicious_expr, "0") is not True

        options = ["$1$", "$2$", "$3$", "$4$"]
        result = check_designated_answer(malicious_expr, options)
        assert result.passed is False

    def test_option_letter_fullmatch_not_substring(self):
        options = ["1", "2", "3", "4"]
        result = check_logic(options, "x + a")
        assert result.passed is False
        assert "not found" in result.detail.lower()

    def test_no_partial_expression_matching(self):
        assert are_expressions_equivalent("x +", "x") is not True

    def test_exact_equality_no_fuzzy_threshold(self):
        assert are_expressions_equivalent("0", r"\frac{1}{10000000000}") is False
        assert are_expressions_equivalent("0", "1e-10") is False

        options = ["0", r"\frac{1}{10000000000}", "2", "3"]
        result = check_duplicate_options(options)
        assert result.passed is True

    def test_large_integer_precision_decimal_no_float_rounding(self):
        """Review feedback: 9007199254740992 and 9007199254740993 (2^53 vs 2^53+1) must not be equal."""
        n1 = "9007199254740992"
        n2 = "9007199254740993"
        assert are_expressions_equivalent(n1, n2) is False

        options = [n1, "2", "3", "4"]
        res = check_designated_answer(n2, options)
        assert res.passed is False

    def test_inconclusive_options_fail_check_logic(self):
        """Review feedback: unparseable math like 'x +' must not pass as distinct options."""
        options = ["x +", "2", "3", "4"]
        dup_res = check_duplicate_options(options)
        assert dup_res.passed is False
        assert dup_res.status == "inconclusive"
        assert "inconclusive" in dup_res.detail.lower()

        logic_res = check_logic(options, "A")
        assert logic_res.passed is False
        assert logic_res.status == "inconclusive"

    def test_equation_option_not_matching_scalar_without_variable_assignment(self):
        """Review feedback: Answer '2' with options ['x+1=2', '3', '4', '5'] must not match."""
        options = ["x+1=2", "3", "4", "5"]
        ans_res = check_designated_answer("2", options)
        assert ans_res.passed is False
        assert ans_res.status == "failed"

        logic_res = check_logic(options, "2")
        assert logic_res.passed is False
        assert logic_res.status == "failed"

    def test_proportional_equations_equivalence(self):
        """Review feedback: 'x=1' and '2*x=2' are proven equivalent (True)."""
        assert are_expressions_equivalent("x = 1", "2*x = 2") is True
        assert are_expressions_equivalent("x = 1", "2*x = 4") is False
        # Equations with different variables are inconclusive (None), not falsely False
        assert are_expressions_equivalent("x = 1", "y = 1") is None

    def test_status_aggregation_priority_failed_over_inconclusive_over_verified(self):
        """
        Review feedback: Strict aggregation priority:
        1. Options ['1', '1', 'x +', '4'], answer '5' -> failed (proven duplicate).
        2. Options ['x +', '2', '3', '4'], answer 'A' -> inconclusive.
        3. Options ['1', '2', '3', '4'], answer 'A' -> verified.
        """
        # Case 1: Proven duplicate overrides inconclusive 'x +'
        res1 = check_logic(["1", "1", "x +", "4"], "5")
        assert res1.passed is False
        assert res1.status == "failed"

        # Case 2: Inconclusive without proven failure
        res2 = check_logic(["x +", "2", "3", "4"], "A")
        assert res2.passed is False
        assert res2.status == "inconclusive"

        # Case 3: All checks verified
        res3 = check_logic(["1", "2", "3", "4"], "A")
        assert res3.passed is True
        assert res3.status == "verified"

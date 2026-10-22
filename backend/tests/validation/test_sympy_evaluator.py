"""
Unit tests for SymPy Mathematical Evaluator (VAL-03 / TASK-107b).
"""

from app.models.schemas import GeneratedVariant, SourceQuestion
from app.services.validator.sympy_evaluator import (
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


class TestLatexCleaningAndParsing:
    def test_clean_latex_delimiters(self):
        assert clean_latex("$x^2 - 1 = 0$") == "x^2 - 1 = 0"
        assert clean_latex(r"$$\frac{1}{2}$$") == r"\frac{1}{2}"
        assert clean_latex(r"\left( x + 1 \right)") == "( x + 1 )"
        assert clean_latex(r"\dfrac{a}{b}") == r"\frac{a}{b}"

    def test_parse_to_sympy_fraction(self):
        expr, err = parse_to_sympy(r"\frac{1}{2}")
        assert err is None
        assert expr is not None
        assert float(expr) == 0.5

    def test_parse_to_sympy_polynomial(self):
        expr, err = parse_to_sympy("x^2 - 5*x + 6")
        assert err is None
        assert expr is not None

    def test_expression_length_bound(self):
        long_expr = "x + " * 300  # > 500 characters
        assert len(long_expr) > MAX_EXPRESSION_LENGTH
        expr, err = parse_to_sympy(long_expr)
        assert expr is None
        assert "exceeds maximum length" in err.lower()


class TestEquationVerification:
    def test_quadratic_equation_correct_root(self):
        # x^2 - 5x + 4 = 0 has roots x = 1, x = 4
        result: EvaluationResult = verify_equation_solution(
            equation_str="x^2 - 5x + 4 = 0",
            candidate_answer_str="1",
        )
        assert result.status == EvaluationStatus.VERIFIED
        assert result.passed is True
        assert result.confidence == "sympy_verified"
        assert "verified" in result.detail.lower()

    def test_quadratic_equation_second_root_with_variable(self):
        result: EvaluationResult = verify_equation_solution(
            equation_str="x^2 - 5x + 4 = 0",
            candidate_answer_str="x = 4",
        )
        assert result.status == EvaluationStatus.VERIFIED
        assert result.passed is True

    def test_quadratic_equation_both_roots_separated(self):
        result: EvaluationResult = verify_equation_solution(
            equation_str="x^2 - 4x + 3 = 0",
            candidate_answer_str="x=1; x=3",
        )
        assert result.status == EvaluationStatus.VERIFIED
        assert result.passed is True

    def test_quadratic_equation_incorrect_root(self):
        # Candidate 3 is NOT a root of x^2 - 5x + 4 = 0 (3^2 - 15 + 4 = -2 != 0)
        result: EvaluationResult = verify_equation_solution(
            equation_str="x^2 - 5x + 4 = 0",
            candidate_answer_str="3",
        )
        assert result.status == EvaluationStatus.FAILED
        assert result.passed is False
        assert result.confidence == "sympy_verified"
        assert len(result.errors) > 0

    def test_linear_equation(self):
        result: EvaluationResult = verify_equation_solution(
            equation_str="2x - 6 = 0",
            candidate_answer_str="3",
        )
        assert result.status == EvaluationStatus.VERIFIED
        assert result.passed is True


class TestDomainConstraints:
    def test_division_by_zero_fails(self):
        # Candidate x = 2 causes denominator x - 2 = 0
        result: EvaluationResult = verify_equation_solution(
            equation_str=r"\frac{1}{x - 2} = 0",
            candidate_answer_str="2",
        )
        assert result.status == EvaluationStatus.DOMAIN_ERROR
        assert result.passed is False
        assert result.confidence == "sympy_verified"
        assert "denominator equals zero" in result.detail.lower()

    def test_negative_square_root_radicand_fails(self):
        # Candidate x = 1 causes radicand x - 5 = -4 < 0
        result: EvaluationResult = verify_equation_solution(
            equation_str=r"\sqrt{x - 5} = 0",
            candidate_answer_str="1",
        )
        assert result.status == EvaluationStatus.DOMAIN_ERROR
        assert result.passed is False
        assert "negative" in result.detail.lower()


class TestQuestionExtractionAndFallback:
    def test_extract_equation_from_text(self):
        text = "Giải phương trình bậc hai $x^2 - 4x + 3 = 0$ để tìm nghiệm?"
        eq = extract_equation_from_text(text)
        assert eq == "x^2 - 4x + 3 = 0"

    def test_verify_question_math_algebraic(self):
        text = "Cho phương trình $x^2 - 5x + 6 = 0$. Nghiệm là gì?"
        result: EvaluationResult = verify_question_math(
            question_text=text,
            correct_answer="x = 2",
        )
        assert result.status == EvaluationStatus.VERIFIED
        assert result.passed is True
        assert result.confidence == "sympy_verified"

    def test_out_of_scope_math_returns_unsupported_not_pass(self):
        # Word problem / non-equation text: must NOT falsely pass
        text = "Một hình chóp tứ giác đều có cạnh đáy bằng a và chiều cao bằng 2a. Tính thể tích?"
        result: EvaluationResult = verify_question_math(
            question_text=text,
            correct_answer="V = \\frac{2a^3}{3}",
        )
        assert result.status == EvaluationStatus.UNSUPPORTED
        assert result.passed is False
        assert result.confidence == "rule_only"
        assert "fallback" in result.detail.lower()

    def test_variant_model_integration(self):
        variant = GeneratedVariant(
            variant_id="var_sympy_01",
            source_question_id="q1",
            question_text="Giải phương trình $x^2 - 4 = 0$?",
            options=["$x=2$", "$x=3$", "$x=4$", "$x=5$"],
            correct_answer="$x=2$",
            solution_steps="x^2 = 4 -> x = 2 hoặc x = -2",
        )
        result = verify_variant_math(variant)
        assert result.status == EvaluationStatus.VERIFIED
        assert result.passed is True
        # Check conversion to CheckResult
        check_res = result.to_check_result()
        assert check_res.passed is True
        assert check_res.check_name == "answer_verified"

    def test_source_question_model_integration(self):
        source = SourceQuestion(
            id="src_01",
            question_text="Cho phương trình $3x - 9 = 0$. Tìm nghiệm?",
            options=["$3$", "$1$", "$2$", "$0$"],
            correct_answer="$3$",
        )
        result = verify_variant_math(source)
        assert result.status == EvaluationStatus.VERIFIED
        assert result.passed is True


class TestTimeoutBehavior:
    def test_timeout_returns_rule_only_warning(self):
        # Pass a very short timeout (0.001s) to force a timeout
        result: EvaluationResult = verify_equation_solution(
            equation_str="x^2 - 5x + 4 = 0",
            candidate_answer_str="1",
            timeout=0.001,
        )
        assert result.status == EvaluationStatus.TIMEOUT
        assert result.passed is False
        assert result.confidence == "rule_only"
        assert "timed out" in result.detail.lower()


class TestRegressionPhilipFeedbackPR12:
    def test_prevent_rce_via_sympify(self):
        """Review feedback: code execution strings must not be executed by parse_to_sympy or verify."""
        malicious = "__import__('os').system('echo pwned')"
        expr, err = parse_to_sympy(malicious)
        assert expr is None
        assert err is not None

        res = verify_equation_solution("x = 2", malicious)
        assert res.status == EvaluationStatus.UNSUPPORTED
        assert res.passed is False

    def test_question_expression_evaluation_not_misidentified_as_equation(self):
        """Review feedback: 'Cho $x=2$. Tính $x+1$' must return UNSUPPORTED, not verify x=2."""
        text = "Cho $x=2$. Tính $x+1$?"
        res_3 = verify_question_math(text, "3")
        assert res_3.status == EvaluationStatus.UNSUPPORTED
        assert res_3.passed is False
        assert res_3.confidence == "rule_only"

        res_2 = verify_question_math(text, "2")
        assert res_2.status == EvaluationStatus.UNSUPPORTED
        assert res_2.passed is False

    def test_no_partial_answers_trailing_tokens(self):
        """Review feedback: candidate answers with dangling tokens like '2 +' or '2; ?' must fail."""
        res_plus = verify_equation_solution("x = 2", "2 +")
        assert res_plus.status == EvaluationStatus.UNSUPPORTED
        assert res_plus.passed is False

        res_qmark = verify_equation_solution("x = 2", "2; ?")
        assert res_qmark.status == EvaluationStatus.UNSUPPORTED
        assert res_qmark.passed is False

    def test_exact_equality_no_fuzzy_threshold(self):
        """Review feedback: equation x = 0 must reject 0.0000000001 (1e-10)."""
        res = verify_equation_solution("x = 0", "0.0000000001")
        assert res.status == EvaluationStatus.FAILED
        assert res.passed is False

    def test_check_result_preserves_status_and_confidence(self):
        """Review feedback: to_check_result() must keep status and confidence for downstream handoff."""
        res = verify_equation_solution("x = 2", "2")
        check_res = res.to_check_result()
        assert check_res.status == "verified"
        assert check_res.confidence == "sympy_verified"

        res_unsupported = verify_equation_solution("x = 2", "2 +")
        check_unsupported = res_unsupported.to_check_result()
        assert check_unsupported.status == "unsupported"
        assert check_unsupported.confidence == "rule_only"

    def test_expression_value_question_with_alternate_wording_returns_unsupported(self):
        """Review feedback: 'Với $x=2$, biểu thức $x+1$ bằng bao nhiêu?' must return UNSUPPORTED."""
        text = "Với $x=2$, biểu thức $x+1$ bằng bao nhiêu?"
        res_3 = verify_question_math(text, "3")
        assert res_3.status == EvaluationStatus.UNSUPPORTED
        assert res_3.passed is False
        assert res_3.confidence == "rule_only"

        res_2 = verify_question_math(text, "2")
        assert res_2.status == EvaluationStatus.UNSUPPORTED
        assert res_2.passed is False

    def test_equation_with_root_selection_or_extra_condition_returns_unsupported(self):
        """
        Review feedback: Questions with root selection conditions (positive/negative,
        inequalities, intervals, extrema) must return UNSUPPORTED regardless of answer.
        """
        # 1. Simple equation without conditions: verified or failed
        eq_simple = "Giải $x^2-1=0$"
        res_corr = verify_question_math(eq_simple, "1")
        assert res_corr.status == EvaluationStatus.VERIFIED
        assert res_corr.passed is True
        assert res_corr.confidence == "sympy_verified"

        res_wrong = verify_question_math(eq_simple, "2")
        assert res_wrong.status == EvaluationStatus.FAILED
        assert res_wrong.passed is False
        assert res_wrong.confidence == "sympy_verified"

        # 2. Condition: "nghiệm dương" - both answers '1' and '-1' must return UNSUPPORTED
        q_pos = "Tìm nghiệm dương của phương trình $x^2-1=0$."
        res_pos_1 = verify_question_math(q_pos, "1")
        assert res_pos_1.status == EvaluationStatus.UNSUPPORTED
        assert res_pos_1.passed is False
        assert res_pos_1.confidence == "rule_only"

        res_pos_neg1 = verify_question_math(q_pos, "-1")
        assert res_pos_neg1.status == EvaluationStatus.UNSUPPORTED
        assert res_pos_neg1.passed is False
        assert res_pos_neg1.confidence == "rule_only"

        # 3. Condition: "với điều kiện x > 0"
        q_cond1 = "Giải phương trình $x^2-1=0$ với điều kiện $x>0$."
        res_cond1 = verify_question_math(q_cond1, "-1")
        assert res_cond1.status == EvaluationStatus.UNSUPPORTED
        assert res_cond1.passed is False
        assert res_cond1.confidence == "rule_only"

        # 4. Condition: "với x > 0"
        q_cond2 = "Giải phương trình $x^2-1=0$ với $x>0$"
        res_cond2 = verify_question_math(q_cond2, "-1")
        assert res_cond2.status == EvaluationStatus.UNSUPPORTED
        assert res_cond2.passed is False
        assert res_cond2.confidence == "rule_only"

        # 5. Condition: "thuộc khoảng (0; 2)"
        q_interval = "Tìm nghiệm thuộc khoảng (0; 2) của phương trình $x^2-1=0$"
        res_interval = verify_question_math(q_interval, "1")
        assert res_interval.status == EvaluationStatus.UNSUPPORTED
        assert res_interval.passed is False
        assert res_interval.confidence == "rule_only"

        # 6. Condition: "lớn nhất" / "nhỏ nhất"
        q_max = "Tìm nghiệm lớn nhất của phương trình $x^2-1=0$"
        res_max = verify_question_math(q_max, "1")
        assert res_max.status == EvaluationStatus.UNSUPPORTED
        assert res_max.passed is False
        assert res_max.confidence == "rule_only"

        # 7. Preserves status and confidence in to_check_result and to_dict
        check_res = res_pos_1.to_check_result("custom_check")
        assert check_res.status == "unsupported"
        assert check_res.confidence == "rule_only"
        assert check_res.passed is False

        dict_res = res_pos_1.to_dict()
        assert dict_res["status"] == "unsupported"
        assert dict_res["confidence"] == "rule_only"
        assert dict_res["passed"] is False

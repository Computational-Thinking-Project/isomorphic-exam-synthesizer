"""
Unit tests for Rule-Based Fallback Checker (VAL-04 / TASK-107c).
"""

import json
from pathlib import Path

from app.models.schemas import GeneratedVariant, SourceQuestion
from app.services.validator.base import CheckResult
from app.services.validator.rule_checker import (
    check_distractor_reasonableness,
    check_mathematical_invariants,
    check_parameter_bounds,
    detect_out_of_scope_math,
    evaluate_rule_fallback,
    extract_parameter_domains,
    safe_eval_numeric_expr,
    validate_rule_variant,
)
from app.services.validator.sympy_evaluator import EvaluationResult, EvaluationStatus


class TestSafeNumericEvaluator:
    def test_basic_arithmetic(self):
        assert safe_eval_numeric_expr("1 + 2") == 3.0
        assert safe_eval_numeric_expr("10 - 4.5") == 5.5
        assert safe_eval_numeric_expr("3 * 4") == 12.0
        assert safe_eval_numeric_expr("15 / 3") == 5.0
        assert safe_eval_numeric_expr("2^3") == 8.0
        assert safe_eval_numeric_expr("10 % 3") == 1.0

    def test_unary_operators(self):
        assert safe_eval_numeric_expr("-5") == -5.0
        assert safe_eval_numeric_expr("+12.5") == 12.5
        assert safe_eval_numeric_expr("-(-7)") == 7.0

    def test_safe_functions(self):
        assert safe_eval_numeric_expr("abs(-15)") == 15.0
        assert safe_eval_numeric_expr("sqrt(25)") == 5.0
        assert safe_eval_numeric_expr("sqrt(0)") == 0.0

    def test_invalid_and_negative_roots(self):
        assert safe_eval_numeric_expr("sqrt(-4)") is None

    def test_division_by_zero_returns_none(self):
        assert safe_eval_numeric_expr("10 / 0") is None
        assert safe_eval_numeric_expr("5 / (2 - 2)") is None

    def test_latex_braces_and_syntax_cleaning(self):
        assert safe_eval_numeric_expr(r"\left( 3 + 4 \right)") == 7.0
        assert safe_eval_numeric_expr("{5} * {2}") == 10.0

    def test_disallowed_syntax_and_code_injection_safety(self):
        # Code injection attempts must safely return None
        assert safe_eval_numeric_expr("__import__('os').system('calc')") is None
        assert safe_eval_numeric_expr("eval('2+2')") is None
        assert safe_eval_numeric_expr("open('secret.txt')") is None
        assert safe_eval_numeric_expr("lambda x: x + 1") is None
        assert (
            safe_eval_numeric_expr("x + 5") is None
        )  # Variable is unsupported in pure numeric eval
        assert safe_eval_numeric_expr("") is None
        assert safe_eval_numeric_expr("   ") is None


class TestExtractParameterDomains:
    def test_nested_draft_2020_12_blueprint(self):
        bp = {
            "requirement": {
                "variation_policy": {
                    "parameter_domains": [
                        {
                            "quantity_ref": "Q_K",
                            "minimum": {"type": "integer", "value": 55},
                            "maximum": {"type": "integer", "value": 5000},
                        }
                    ]
                }
            }
        }
        domains = extract_parameter_domains(bp)
        assert len(domains) == 1
        assert domains[0]["quantity_ref"] == "Q_K"

    def test_variation_policy_top_level(self):
        bp = {"variation_policy": {"parameter_domains": [{"name": "m", "min": 1, "max": 10}]}}
        domains = extract_parameter_domains(bp)
        assert len(domains) == 1
        assert domains[0]["name"] == "m"

    def test_flat_parameter_domains(self):
        bp = {"parameter_domains": [{"name": "a", "min": -5, "max": 5}]}
        domains = extract_parameter_domains(bp)
        assert len(domains) == 1
        assert domains[0]["name"] == "a"

    def test_flat_general_bounds(self):
        bp = {"bounds": {"min": 0, "max": 100}}
        domains = extract_parameter_domains(bp)
        assert len(domains) == 1
        assert domains[0]["name"] == "*"
        assert domains[0]["min"] == 0
        assert domains[0]["max"] == 100

    def test_flat_per_parameter_bounds(self):
        bp = {
            "bounds": {
                "k": {"min": 55, "max": 5000, "step": 55},
                "m": {"minimum": 1, "maximum": 10},
            }
        }
        domains = extract_parameter_domains(bp)
        assert len(domains) == 2
        names = {d["name"] for d in domains}
        assert names == {"k", "m"}

    def test_empty_or_malformed_blueprint(self):
        assert extract_parameter_domains(None) == []
        assert extract_parameter_domains({}) == []
        assert extract_parameter_domains({"other": 123}) == []


class TestCheckParameterBounds:
    def test_no_blueprint_or_domains_skips_gracefully(self):
        res = check_parameter_bounds(question_text="Tìm nghiệm của phương trình x = 5")
        assert res.passed is True
        assert res.status == "no_parameter_domains"

    def test_parameter_within_bounds(self):
        bp = {"bounds": {"k": {"min": 55, "max": 5000, "step": 55}}}
        # In text: "k = 110"
        res = check_parameter_bounds(
            question_text="Cho tham số k = 110. Tính xác suất...",
            blueprint=bp,
        )
        assert res.passed is True
        assert res.status == "verified"
        assert len(res.errors) == 0

    def test_parameter_below_minimum_fails(self):
        bp = {"bounds": {"k": {"min": 55, "max": 5000}}}
        res = check_parameter_bounds(
            question_text="Cho tham số k = 10. Tính xác suất...",
            blueprint=bp,
        )
        assert res.passed is False
        assert res.status == "failed"
        assert any("below minimum 55" in err for err in res.errors)

    def test_parameter_above_maximum_fails(self):
        bp = {"bounds": {"k": {"min": 55, "max": 5000}}}
        res = check_parameter_bounds(
            question_text="Cho tham số k = 6000. Tính xác suất...",
            blueprint=bp,
        )
        assert res.passed is False
        assert res.status == "failed"
        assert any("exceeds maximum 5000" in err for err in res.errors)

    def test_parameter_step_violation_fails(self):
        bp = {"bounds": {"k": {"min": 55, "max": 5000, "step": 55}}}
        # 120 is not 55 + n*55
        res = check_parameter_bounds(
            question_text="Cho tham số k = 120. Tính xác suất...",
            blueprint=bp,
        )
        assert res.passed is False
        assert any("does not satisfy step 55" in err for err in res.errors)

    def test_parameter_allowed_values_constraint(self):
        bp = {"bounds": {"m": {"allowed_values": [1, 2, 4, 8]}}}
        res_pass = check_parameter_bounds(
            question_text="Với m = 4, phương trình có nghiệm...",
            blueprint=bp,
        )
        assert res_pass.passed is True

        res_fail = check_parameter_bounds(
            question_text="Với m = 5, phương trình có nghiệm...",
            blueprint=bp,
        )
        assert res_fail.passed is False
        assert any("not in allowed values" in err for err in res_fail.errors)

    def test_parameters_passed_explicitly_in_dict(self):
        bp = {
            "requirement": {
                "variation_policy": {
                    "parameter_domains": [
                        {
                            "quantity_ref": "Q_K",
                            "minimum": 55,
                            "maximum": 5000,
                        }
                    ]
                }
            }
        }
        # Pass via parameters dict with key "Q_K"
        res = check_parameter_bounds(
            question_text="Tính giá trị biểu thức...",
            blueprint=bp,
            parameters={"Q_K": 3190},
        )
        assert res.passed is True
        assert res.status == "verified"

        # Pass out of bound value via parameters dict with short name "k"
        res_fail = check_parameter_bounds(
            question_text="Tính giá trị biểu thức...",
            blueprint=bp,
            parameters={"k": 20},
        )
        assert res_fail.passed is False
        assert any("below minimum 55" in err for err in res_fail.errors)

    def test_general_bounds_check_all_numbers(self):
        bp = {"bounds": {"min": -10, "max": 10}}
        # 15 is outside [-10, 10]
        res = check_parameter_bounds(
            question_text="Tìm x biết x + 15 = 0",
            blueprint=bp,
        )
        assert res.passed is False
        assert any("exceeds maximum 10" in err for err in res.errors)


class TestCheckMathematicalInvariants:
    def test_zero_denominator_in_latex_fraction_fails(self):
        res = check_mathematical_invariants(
            question_text=r"Giá trị của biểu thức \frac{5}{0} bằng bao nhiêu?",
            options=[r"\frac{1}{2}", r"\frac{3}{4}", "1", "2"],
        )
        assert res.passed is False
        assert any("Zero denominator detected" in err for err in res.errors)

    def test_zero_denominator_in_calculated_expression_fails(self):
        res = check_mathematical_invariants(
            question_text=r"Tính giá trị của \frac{10}{3 - 3}",
            options=["1", "2", "3", "4"],
        )
        assert res.passed is False
        assert any("Zero denominator detected" in err for err in res.errors)

    def test_zero_denominator_in_options_fails(self):
        res = check_mathematical_invariants(
            question_text="Tính giới hạn...",
            options=[r"\frac{1}{2}", r"\frac{5}{0}", "1", "2"],
        )
        assert res.passed is False
        assert any("Zero denominator detected" in err for err in res.errors)

    def test_zero_denominator_plain_fraction_fails(self):
        res = check_mathematical_invariants(
            question_text="Giá trị 10 / 0 là:",
            options=["1", "2", "3", "4"],
        )
        assert res.passed is False
        assert any("Zero denominator detected in numerical fraction" in err for err in res.errors)

    def test_valid_fractions_pass(self):
        res = check_mathematical_invariants(
            question_text=r"Tính \frac{1}{2} + \frac{3}{4}",
            options=[r"\frac{5}{4}", r"\frac{1}{4}", "1", "2"],
        )
        assert res.passed is True
        assert res.status == "verified"

    def test_negative_radicand_in_even_root_fails(self):
        res = check_mathematical_invariants(
            question_text=r"Tính giá trị biểu thức \sqrt{-9}",
            options=["3", "-3", "9", "0"],
        )
        assert res.passed is False
        assert any("Negative radicand in even root" in err for err in res.errors)

    def test_negative_radicand_in_calculated_expression_fails(self):
        res = check_mathematical_invariants(
            question_text=r"Cho biểu thức \sqrt{2 - 6}",
            options=["1", "2", "3", "4"],
        )
        assert res.passed is False
        assert any("Negative radicand in even root" in err for err in res.errors)

    def test_positive_radicand_passes(self):
        res = check_mathematical_invariants(
            question_text=r"Tính giá trị biểu thức \sqrt{9} + \sqrt{16}",
            options=["7", "5", "1", "0"],
        )
        assert res.passed is True

    def test_odd_root_negative_radicand_allowed_in_real_domain(self):
        # Cube root of -8 is -2, which is completely valid in real domain
        res = check_mathematical_invariants(
            question_text=r"Tính giá trị biểu thức \sqrt[3]{-8}",
            options=["-2", "2", "4", "0"],
        )
        assert res.passed is True

    def test_logarithm_non_positive_argument_fails(self):
        res1 = check_mathematical_invariants(
            question_text=r"Tính \ln(0)",
            options=["1", "2", "3", "4"],
        )
        assert res1.passed is False
        assert any("Logarithm argument must be strictly positive" in err for err in res1.errors)

        res2 = check_mathematical_invariants(
            question_text=r"Tính \log(-5)",
            options=["1", "2", "3", "4"],
        )
        assert res2.passed is False
        assert any("Logarithm argument must be strictly positive" in err for err in res2.errors)

    def test_logarithm_invalid_base_fails(self):
        # Base 1 is invalid
        res1 = check_mathematical_invariants(
            question_text=r"Tính \log_{1}(5)",
            options=["1", "2", "3", "4"],
        )
        assert res1.passed is False
        assert any("Logarithm base cannot be equal to 1" in err for err in res1.errors)

        # Base 0 or negative is invalid
        res2 = check_mathematical_invariants(
            question_text=r"Tính \log_{0}(5)",
            options=["1", "2", "3", "4"],
        )
        assert res2.passed is False
        assert any("Logarithm base must be strictly positive" in err for err in res2.errors)

    def test_quadratic_discriminant_invariant_two_distinct_roots(self):
        # x^2 - 4x + 3 = 0 -> Delta = 16 - 12 = 4 > 0 (two distinct roots) -> Passes
        res_pass = check_mathematical_invariants(
            question_text="Phương trình x^2 - 4x + 3 = 0 có hai nghiệm phân biệt x_1, x_2.",
            options=["1", "2", "3", "4"],
        )
        assert res_pass.passed is True

        # x^2 - 2x + 1 = 0 -> Delta = 4 - 4 = 0 (double root, NOT 2 distinct roots) -> Fails
        res_fail = check_mathematical_invariants(
            question_text="Phương trình x^2 - 2x + 1 = 0 có hai nghiệm phân biệt x_1, x_2.",
            options=["1", "2", "3", "4"],
        )
        assert res_fail.passed is False
        assert any("Delta=0.0 <= 0" in err for err in res_fail.errors)

    def test_quadratic_discriminant_invariant_no_real_roots(self):
        # x^2 + 2x + 5 = 0 -> Delta = 4 - 20 = -16 < 0 (no real roots) -> Passes
        res_pass = check_mathematical_invariants(
            question_text="Phương trình x^2 + 2x + 5 = 0 vô nghiệm.",
            options=["1", "2", "3", "4"],
        )
        assert res_pass.passed is True

        # x^2 - 5x + 6 = 0 -> Delta = 25 - 24 = 1 >= 0 -> Claims no real roots, so Fails
        res_fail = check_mathematical_invariants(
            question_text="Phương trình x^2 - 5x + 6 = 0 vô nghiệm.",
            options=["1", "2", "3", "4"],
        )
        assert res_fail.passed is False
        assert any("Delta=1.0 >= 0" in err for err in res_fail.errors)

    def test_direct_probability_range_invariant(self):
        # Valid probability options in [0, 1]
        res_pass = check_mathematical_invariants(
            question_text="Tìm xác suất để biến cố A xảy ra:",
            options=[r"\frac{1}{4}", r"\frac{1}{2}", r"\frac{3}{4}", "1"],
        )
        assert res_pass.passed is True

        # Invalid probability option: 1.5 or -0.2
        res_fail = check_mathematical_invariants(
            question_text="Tìm xác suất để biến cố A xảy ra:",
            options=[r"\frac{1}{4}", "1.5", "0.2", "0.5"],
        )
        assert res_fail.passed is False
        assert any("outside valid range [0, 1]" in err for err in res_fail.errors)

    def test_indirect_probability_scaled_by_k_allows_large_integer(self):
        # In mathematics_partition_probability: "Giá trị của 3190P bằng bao nhiêu?"
        # Options are large integers like 1856, 1334, 928, 2552.
        # This must NOT fail probability [0, 1] bounds!
        res = check_mathematical_invariants(
            question_text="Gọi P là xác suất... Giá trị của 3190P bằng bao nhiêu?",
            options=["1856", "1334", "928", "2552"],
        )
        assert res.passed is True

    def test_triangle_inequality_violation_fails(self):
        # 3, 4, 8: 3 + 4 = 7 < 8 -> violates triangle inequality
        res_fail = check_mathematical_invariants(
            question_text="Cho tam giác ABC có các cạnh lần lượt là 3, 4, 8.",
            options=["A", "B", "C", "D"],
        )
        assert res_fail.passed is False
        assert any("Triangle inequality violated" in err for err in res_fail.errors)

        # 3, 4, 5: valid triangle
        res_pass = check_mathematical_invariants(
            question_text="Cho tam giác ABC có các cạnh lần lượt là 3, 4, 5.",
            options=["A", "B", "C", "D"],
        )
        assert res_pass.passed is True


class TestCheckDistractorReasonableness:
    def test_valid_options_and_correct_answer_by_label(self):
        res = check_distractor_reasonableness(
            options=["1", "2", "3", "4"],
            correct_answer="A",
        )
        assert res.passed is True
        assert res.status == "verified"

    def test_valid_options_and_correct_answer_by_content(self):
        res = check_distractor_reasonableness(
            options=["$x = 1$", "$x = 2$", "$x = 3$", "$x = 4$"],
            correct_answer="x = 2",
        )
        assert res.passed is True
        assert res.status == "verified"

    def test_invalid_option_count_fails(self):
        res = check_distractor_reasonableness(
            options=["1", "2", "3"],
            correct_answer="1",
        )
        assert res.passed is False
        assert "Expected exactly 4 options" in res.errors[0]

    def test_empty_or_whitespace_option_fails(self):
        res = check_distractor_reasonableness(
            options=["1", "", "3", "4"],
            correct_answer="1",
        )
        assert res.passed is False
        assert any("Option 2 is empty" in err for err in res.errors)

    def test_degenerate_option_fails(self):
        for degen in ("null", "None", "NaN", "N/A", "undefined"):
            res = check_distractor_reasonableness(
                options=["1", degen, "3", "4"],
                correct_answer="1",
            )
            assert res.passed is False
            assert any(f"degenerate value '{degen}'" in err for err in res.errors)

    def test_duplicate_options_syntactic_and_normalized_fails(self):
        # Exactly matching strings
        res1 = check_distractor_reasonableness(
            options=["1", "2", "2", "4"],
            correct_answer="1",
        )
        assert res1.passed is False
        assert any("Duplicate option detected" in err for err in res1.errors)

        # Normalized LaTeX match ($x = 1$ vs x = 1)
        res2 = check_distractor_reasonableness(
            options=["$x = 1$", "x = 1", "3", "4"],
            correct_answer="3",
        )
        assert res2.passed is False
        assert any("Duplicate option detected" in err for err in res2.errors)

    def test_unmatched_correct_answer_fails(self):
        res = check_distractor_reasonableness(
            options=["1", "2", "3", "4"],
            correct_answer="99",  # Not among options and not a label A-D
        )
        assert res.passed is False
        assert any("does not match any of the provided options" in err for err in res.errors)


class TestDetectOutOfScopeMath:
    def test_geometry_detection(self):
        is_oos, cat = detect_out_of_scope_math(
            "Cho hình chóp S.ABCD có đáy là hình vuông cạnh a. Tính thể tích khối chóp."
        )
        assert is_oos is True
        assert cat == "geometry"

        is_oos2, cat2 = detect_out_of_scope_math(
            "Trong không gian, cho mặt cầu (S) có bán kính R = 5."
        )
        assert is_oos2 is True
        assert cat2 == "geometry"

    def test_combinatorics_probability_detection(self):
        is_oos, cat = detect_out_of_scope_math(
            "Một hộp có 12 quả bóng gồm 4 bóng đỏ và 8 bóng xanh. Chọn ngẫu nhiên 3 bóng. Tính xác suất..."
        )
        assert is_oos is True
        assert cat == "combinatorics_probability"

    def test_word_problem_detection(self):
        is_oos, cat = detect_out_of_scope_math(
            "Một người đi xe máy từ A đến B với vận tốc 40 km/h trên quãng đường 120 km..."
        )
        assert is_oos is True
        assert cat == "word_problem"

    def test_calculus_detection(self):
        is_oos, cat = detect_out_of_scope_math("Tìm nguyên hàm của hàm số f(x) = 2x + 1.")
        assert is_oos is True
        assert cat == "calculus"

    def test_single_equation_not_out_of_scope(self):
        is_oos, cat = detect_out_of_scope_math("Tìm nghiệm của phương trình x^2 - 5x + 6 = 0.")
        assert is_oos is False
        assert cat is None


class TestEvaluateRuleFallbackAndIntegration:
    def test_standalone_fallback_evaluation_passes(self):
        res: CheckResult = evaluate_rule_fallback(
            question_text="Một hộp có 4 bóng đỏ và 8 bóng xanh. Tính xác suất chọn 2 bóng đỏ.",
            options=[r"\frac{1}{11}", r"\frac{2}{11}", r"\frac{3}{11}", r"\frac{4}{11}"],
            correct_answer="A",
            blueprint={"bounds": {"min": 1, "max": 20}},
        )
        assert res.passed is True
        assert res.status == "passed_rule_fallback"
        assert res.confidence == "rule_only"
        assert "out-of-scope math detected" in res.detail

    def test_standalone_fallback_evaluation_fails_on_invariant_violation(self):
        res: CheckResult = evaluate_rule_fallback(
            question_text="Cho hình chóp có đáy là tam giác với biểu thức chia cho không: \\frac{1}{0}",
            options=["1", "2", "3", "4"],
            correct_answer="1",
        )
        assert res.passed is False
        assert res.status == "failed"
        assert res.confidence == "rule_only"
        assert len(res.errors) > 0

    def test_integration_with_sympy_verified_success(self):
        sympy_res = EvaluationResult(
            status=EvaluationStatus.VERIFIED,
            passed=True,
            confidence="sympy_verified",
            detail="CAS verified solution x = 1",
        )
        res: CheckResult = evaluate_rule_fallback(
            question_text="Tìm nghiệm phương trình x - 1 = 0",
            options=["1", "2", "3", "4"],
            correct_answer="1",
            sympy_result=sympy_res,
        )
        assert res.passed is True
        assert res.status == "verified"
        assert res.confidence == "sympy_verified"
        assert "SymPy CAS verified" in res.detail

    def test_integration_with_sympy_verified_but_distractor_duplicate_fails(self):
        sympy_res = EvaluationResult(
            status=EvaluationStatus.VERIFIED,
            passed=True,
            confidence="sympy_verified",
            detail="CAS verified solution x = 1",
        )
        # Duplicate option "2"
        res: CheckResult = evaluate_rule_fallback(
            question_text="Tìm nghiệm phương trình x - 1 = 0",
            options=["1", "2", "2", "4"],
            correct_answer="1",
            sympy_result=sympy_res,
        )
        assert res.passed is False
        assert res.status == "failed"
        assert res.confidence == "sympy_verified"
        assert any("Duplicate option detected" in err for err in res.errors)

    def test_integration_with_sympy_unsupported_falls_back_to_rule_only(self):
        sympy_res = EvaluationResult(
            status=EvaluationStatus.UNSUPPORTED,
            passed=False,
            confidence="rule_only",
            detail="Question structure not single equation. Fallback to rule checking.",
        )
        res: CheckResult = evaluate_rule_fallback(
            question_text="Cho hình chóp S.ABC có đáy là tam giác vuông. Tính thể tích.",
            options=["10", "20", "30", "40"],
            correct_answer="A",
            sympy_result=sympy_res,
        )
        assert res.passed is True
        assert res.status == "passed_rule_fallback"
        assert res.confidence == "rule_only"
        assert "unsupported" in res.detail
        assert "geometry" in res.detail

    def test_integration_with_sympy_timeout_falls_back_to_rule_only(self):
        sympy_res = EvaluationResult(
            status=EvaluationStatus.TIMEOUT,
            passed=False,
            confidence="rule_only",
            detail="CAS evaluation timed out after 5.0 seconds.",
        )
        res: CheckResult = evaluate_rule_fallback(
            question_text="Tính xác suất gieo xúc xắc...",
            options=["1/6", "2/6", "3/6", "4/6"],
            correct_answer="A",
            sympy_result=sympy_res,
        )
        assert res.passed is True
        assert res.status == "passed_rule_fallback"
        assert res.confidence == "rule_only"
        assert "timeout" in res.detail


class TestValidateRuleVariant:
    def test_validate_generated_variant_model(self):
        variant = GeneratedVariant(
            variant_id="VAR-TEST-001",
            source_question_id="SRC-001",
            question_text="Một hình chóp tứ giác đều có cạnh đáy bằng 4. Tính diện tích đáy.",
            options=["16", "8", "12", "20"],
            correct_answer="16",
            solution_steps=r"\text{Diện tích đáy là } 4^2 = 16.",
        )
        res = validate_rule_variant(variant)
        assert res.passed is True
        assert res.status == "passed_rule_fallback"
        assert res.confidence == "rule_only"

    def test_validate_source_question_model(self):
        source = SourceQuestion(
            id="SRC-TEST-001",
            question_text="Cho hình vuông ABCD có cạnh bằng 5.",
            options=["25", "20", "15", "10"],
            correct_answer="A",
        )
        res = validate_rule_variant(source)
        assert res.passed is True
        assert res.status == "passed_rule_fallback"

    def test_validate_duck_typed_dict(self):
        var_dict = {
            "question_text": "Tính xác suất để chọn ngẫu nhiên được một số chẵn từ tập {1, 2, 3, 4, 5, 6}.",
            "options": [r"\frac{1}{2}", r"\frac{1}{3}", r"\frac{1}{6}", r"\frac{2}{3}"],
            "correct_answer": r"\frac{1}{2}",
        }
        res = validate_rule_variant(var_dict)
        assert res.passed is True
        assert res.status == "passed_rule_fallback"

    def test_with_real_blueprint_partition_probability(self):
        # Try finding fixture from repository filesystem
        candidates = [
            Path(__file__).parents[3]
            / "docs"
            / "blueprints"
            / "examples"
            / "mathematics_partition_probability.json",
            Path.cwd()
            / "docs"
            / "blueprints"
            / "examples"
            / "mathematics_partition_probability.json",
            Path.cwd().parent
            / "docs"
            / "blueprints"
            / "examples"
            / "mathematics_partition_probability.json",
        ]
        fixture_path = next((p for p in candidates if p.exists()), None)

        if fixture_path is not None:
            with open(fixture_path, "r", encoding="utf-8") as f:
                blueprint_data = json.load(f)
            src_item = blueprint_data["requirement"]["source"]
            stem = src_item["content"][0]["text"]
            options = [opt["content"][0]["text"] for opt in src_item["options"]]
            ans = "1856"
        else:
            # Standalone fallback blueprint for isolated container environments
            blueprint_data = {
                "requirement": {
                    "variation_policy": {
                        "parameter_domains": [
                            {
                                "quantity_ref": "Q_K",
                                "minimum": {"type": "integer", "value": 55},
                            }
                        ]
                    }
                }
            }
            stem = (
                "Một khung hình trang trí có dạng một đa giác đều 12 cạnh được gắn cố định trên một trần nhà. "
                "Gọi P là xác suất để mỗi hình vuông đều có ít nhất một bóng đèn màu đỏ. "
                "Giá trị của 3190P bằng bao nhiêu?"
            )
            options = ["1856", "1334", "928", "2552"]
            ans = "1856"

        res = evaluate_rule_fallback(
            question_text=stem,
            options=options,
            correct_answer=ans,
            blueprint=blueprint_data,
            parameters={"Q_K": 3190},
        )
        assert res.passed is True
        assert res.status == "passed_rule_fallback"
        assert res.confidence == "rule_only"
        assert "out-of-scope math detected" in res.detail


class TestRuleCheckerReviewRegressionFixes:
    def test_zero_bounds_not_dropped(self):
        # min=0, max=10
        bp_min0 = {"bounds": {"min": 0, "max": 10}}
        res_fail1 = check_parameter_bounds("Giá trị tham số k = -1", blueprint=bp_min0)
        assert res_fail1.passed is False
        assert any("below minimum 0.0" in err for err in res_fail1.errors)

        res_pass1 = check_parameter_bounds("Giá trị tham số k = 0", blueprint=bp_min0)
        assert res_pass1.passed is True

        # min=-10, max=0
        bp_max0 = {"bounds": {"min": -10, "max": 0}}
        res_fail2 = check_parameter_bounds("Giá trị tham số k = 1", blueprint=bp_max0)
        assert res_fail2.passed is False
        assert any("exceeds maximum 0.0" in err for err in res_fail2.errors)

        # nested parameter_domains with minimum 0
        bp_nested0 = {"parameter_domains": [{"name": "p", "minimum": 0, "maximum": 5}]}
        res_nested_fail = check_parameter_bounds("Cho p = -2", blueprint=bp_nested0)
        assert res_nested_fail.passed is False

    def test_typed_allowed_values_in_physics_blueprint(self):
        candidates = [
            Path(__file__).parents[3]
            / "docs"
            / "blueprints"
            / "examples"
            / "physics_newton_acceleration.json",
            Path.cwd() / "docs" / "blueprints" / "examples" / "physics_newton_acceleration.json",
            Path.cwd().parent
            / "docs"
            / "blueprints"
            / "examples"
            / "physics_newton_acceleration.json",
        ]
        fixture_path = next((p for p in candidates if p.exists()), None)
        if fixture_path is not None:
            with open(fixture_path, "r", encoding="utf-8") as f:
                bp = json.load(f)
        else:
            bp = {
                "variation_policy": {
                    "parameter_domains": [
                        {
                            "quantity_ref": "Q_M",
                            "allowed_values": [
                                {"type": "integer", "value": 2},
                                {"type": "integer", "value": 3},
                                {"type": "integer", "value": 4},
                            ],
                        }
                    ]
                }
            }

        # Q_M = 100 must fail
        res_fail = check_parameter_bounds(
            question_text="Một vật có khối lượng m = 100 kg chịu lực kéo...",
            blueprint=bp,
            parameters={"Q_M": 100},
        )
        assert res_fail.passed is False
        assert any("not in allowed values" in err for err in res_fail.errors)

        # Q_M = 2 must pass
        res_pass = check_parameter_bounds(
            question_text="Một vật có khối lượng m = 2 kg chịu lực kéo...",
            blueprint=bp,
            parameters={"Q_M": 2},
        )
        assert res_pass.passed is True

    def test_decimal_and_rational_allowed_values(self):
        bp = {
            "bounds": {
                "ratio": {
                    "allowed_values": [
                        "0.5",
                        {"type": "rational", "numerator": 1, "denominator": 4},
                    ]
                }
            }
        }
        res_pass1 = check_parameter_bounds("Cho ratio = 0.5", blueprint=bp)
        assert res_pass1.passed is True

        res_pass2 = check_parameter_bounds("Cho ratio = 0.25", blueprint=bp)
        assert res_pass2.passed is True

        res_fail = check_parameter_bounds("Cho ratio = 0.75", blueprint=bp)
        assert res_fail.passed is False

    def test_exact_mathematical_domain_boundaries(self):
        # 1e-13 is strictly positive and non-zero: must NOT trigger zero denominator
        res_denom = check_mathematical_invariants(r"Tính \frac{1}{0.0000000000001}")
        assert res_denom.passed is True

        # -1e-13 is strictly negative: MUST trigger negative radicand in real domain
        res_sqrt = check_mathematical_invariants(r"Tính \sqrt{-0.0000000000001}")
        assert res_sqrt.passed is False
        assert any("Negative radicand" in err for err in res_sqrt.errors)

        # ln(1e-13) has argument > 0: MUST be valid
        res_ln = check_mathematical_invariants(r"Tính \ln(0.0000000000001)")
        assert res_ln.passed is True

        # log base 1.0000000000001 is != 1: MUST be valid
        res_log_base = check_mathematical_invariants(r"Tính \log_{1.0000000000001}(5)")
        assert res_log_base.passed is True

    def test_mathematically_equivalent_answers_not_rejected(self):
        # 0.5 is mathematically equivalent to 1/2
        res = check_distractor_reasonableness(
            options=["1/2", "1", "2", "3"],
            correct_answer="0.5",
        )
        assert res.passed is True
        assert res.status == "verified"

    def test_cas_decisive_failure_not_passed_to_fallback(self):
        # FAILED from CAS
        failed_cas = EvaluationResult(
            status=EvaluationStatus.FAILED,
            passed=False,
            confidence="sympy_verified",
            detail="Candidate value 2 is not a root of x - 1 = 0",
        )
        res_fail = evaluate_rule_fallback(
            question_text="Giải phương trình $x - 1 = 0$",
            options=["1", "2", "3", "4"],
            correct_answer="2",
            sympy_result=failed_cas,
        )
        assert res_fail.passed is False
        assert res_fail.status == "failed"
        assert any("Candidate value 2 is not a root" in err for err in res_fail.errors)

        # DOMAIN_ERROR from CAS
        domain_err_cas = EvaluationResult(
            status=EvaluationStatus.DOMAIN_ERROR,
            passed=False,
            confidence="sympy_verified",
            detail="Solution x = 1 causes denominator x - 1 to evaluate to zero",
        )
        res_domain = evaluate_rule_fallback(
            question_text=r"Giải phương trình $\frac{1}{x-1} = 0$",
            options=["1", "2", "3", "4"],
            correct_answer="1",
            sympy_result=domain_err_cas,
        )
        assert res_domain.passed is False
        assert res_domain.status == "domain_error"
        assert any("causes denominator" in err for err in res_domain.errors)

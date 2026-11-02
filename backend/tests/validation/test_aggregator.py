"""
Unit tests for Validation Aggregator (VAL-05 / TASK-107d).
"""

import json
from pathlib import Path
from unittest.mock import patch

from app.models.schemas import GeneratedVariant, SourceQuestion
from app.services.validator.aggregator import validate_question, validate_variant
from app.services.validator.base import ValidationReport
from app.services.validator.sympy_evaluator import EvaluationResult, EvaluationStatus


class TestValidateQuestionSuccessSymPy:
    def test_algebraic_equation_verified_by_sympy(self):
        # x^2 - 5x + 6 = 0 has roots x = 2 and x = 3
        report: ValidationReport = validate_question(
            question_text="Tìm nghiệm của phương trình $x^2 - 5x + 6 = 0$",
            options=["2", "4", "5", "7"],
            correct_answer="2",
        )
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "sympy_verified"
        assert len(report.errors) == 0
        assert report.execution_time_ms > 0

        # Verify to_dict output adheres to API contract
        report_dict = report.to_dict()
        assert report_dict["passed"] is True
        assert report_dict["status"] == "passed"
        assert report_dict["confidence"] == "sympy_verified"
        assert isinstance(report_dict["checks"], list)
        assert len(report_dict["checks"]) >= 5
        assert isinstance(report_dict["execution_time_ms"], float)

    def test_correct_answer_by_label_letter(self):
        # Option A is root x = 3
        report: ValidationReport = validate_question(
            question_text="Phương trình $x^2 - 4x + 3 = 0$ có nghiệm là",
            options=["3", "5", "7", "9"],
            correct_answer="A",
        )
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "sympy_verified"


class TestValidateQuestionSyntaxErrors:
    def test_empty_question_stem_fails(self):
        report: ValidationReport = validate_question(
            question_text="",
            options=["1", "2", "3", "4"],
            correct_answer="1",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any(
            "Question text must not be empty" in err or "empty or contains only whitespace" in err
            for err in report.errors
        )

    def test_invalid_option_count_fails(self):
        report: ValidationReport = validate_question(
            question_text="Phương trình x - 1 = 0",
            options=["1", "2", "3"],
            correct_answer="1",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any(
            "Expected exactly 4 options" in err or "Invalid option count" in err
            for err in report.errors
        )

    def test_empty_option_content_fails(self):
        report: ValidationReport = validate_question(
            question_text="Phương trình x - 1 = 0",
            options=["1", "  ", "3", "4"],
            correct_answer="1",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any(
            "Empty option detected" in err or "must not be empty" in err for err in report.errors
        )

    def test_unbalanced_latex_delimiters_fails(self):
        report: ValidationReport = validate_question(
            question_text=r"Phương trình \frac{1}{2 có nghiệm là:",
            options=["1", "2", "3", "4"],
            correct_answer="1",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("brace" in err.lower() or "unclosed" in err.lower() for err in report.errors)

    def test_fail_fast_aborts_early_on_syntax_error(self):
        report: ValidationReport = validate_question(
            question_text="",
            options=["1", "2", "3", "4"],
            correct_answer="1",
            fail_fast=True,
        )
        assert report.passed is False
        assert report.status == "failed"
        # In fail_fast mode, later stages (SymPy, Rule Fallback) are not executed
        check_names = [c.check_name for c in report.checks]
        assert "syntax_valid" in check_names
        assert "sympy_evaluator" not in check_names
        assert "rule_fallback" not in check_names


class TestValidateQuestionLogicErrors:
    def test_unmatched_designated_answer_fails(self):
        report: ValidationReport = validate_question(
            question_text="Phương trình x - 1 = 0",
            options=["1", "2", "3", "4"],
            correct_answer="999",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("Designated answer" in err or "does not match" in err for err in report.errors)

    def test_duplicate_options_syntactic_fails(self):
        report: ValidationReport = validate_question(
            question_text="Phương trình x - 1 = 0",
            options=["1", "2", "2", "4"],
            correct_answer="1",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any(
            "Duplicate options found" in err or "Duplicate option detected" in err
            for err in report.errors
        )

    def test_duplicate_options_latex_equivalent_fails(self):
        report: ValidationReport = validate_question(
            question_text="Phương trình x - 1 = 0",
            options=["$x = 1$", "x = 1", "3", "4"],
            correct_answer="3",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("Duplicate" in err for err in report.errors)

    def test_fail_fast_aborts_on_logic_error(self):
        report: ValidationReport = validate_question(
            question_text="Phương trình x - 1 = 0",
            options=["1", "2", "2", "4"],
            correct_answer="1",
            fail_fast=True,
        )
        assert report.passed is False
        assert report.status == "failed"
        check_names = [c.check_name for c in report.checks]
        assert "no_duplicates" in check_names
        assert "sympy_evaluator" not in check_names
        assert "rule_fallback" not in check_names


class TestValidateQuestionOutOfScopeAndFallback:
    def test_geometry_bypasses_cas_and_passes_rule_fallback(self):
        report: ValidationReport = validate_question(
            question_text="Cho hình chóp S.ABCD có đáy là hình vuông cạnh 4. Tính diện tích đáy.",
            options=["16", "8", "12", "20"],
            correct_answer="16",
        )
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "rule_only"
        assert any("geometry" in w for w in report.warnings)

    def test_treat_fallback_as_warning_flag(self):
        report: ValidationReport = validate_question(
            question_text="Cho hình chóp S.ABCD có đáy là hình vuông cạnh 4. Tính diện tích đáy.",
            options=["16", "8", "12", "20"],
            correct_answer="16",
            treat_fallback_as_warning=True,
        )
        assert report.passed is True
        assert report.status == "warning"
        assert report.confidence == "rule_only"

    def test_combinatorics_probability_bypasses_cas(self):
        report: ValidationReport = validate_question(
            question_text="Một hộp có 12 bóng đèn gồm 4 bóng đỏ và 8 bóng xanh. Chọn ngẫu nhiên 3 bóng.",
            options=[r"\frac{1}{55}", r"\frac{2}{55}", r"\frac{3}{55}", r"\frac{4}{55}"],
            correct_answer="A",
        )
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "rule_only"
        assert any("combinatorics_probability" in w for w in report.warnings)


class TestValidateQuestionSymPyOutcomes:
    def test_sympy_incorrect_answer_fails(self):
        # x - 1 = 0 has root x = 1, but candidate answer is designated as 5
        report: ValidationReport = validate_question(
            question_text="Tìm nghiệm của phương trình $x - 1 = 0$",
            options=["1", "2", "5", "7"],
            correct_answer="5",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("is not a root" in err or "failed" in err.lower() for err in report.errors)

    def test_sympy_timeout_triggers_fallback_and_warning(self):
        mock_timeout_res = EvaluationResult(
            status=EvaluationStatus.TIMEOUT,
            passed=False,
            confidence="rule_only",
            detail="CAS evaluation timed out after 5.0 seconds.",
        )
        with patch(
            "app.services.validator.aggregator.verify_question_math", return_value=mock_timeout_res
        ):
            report: ValidationReport = validate_question(
                question_text="Tìm nghiệm của phương trình x^2 - 7x + 12 = 0",
                options=["3", "5", "6", "8"],
                correct_answer="3",
            )
            assert report.passed is True
            assert report.status == "passed"
            assert report.confidence == "rule_only"
            assert any("timed out" in w for w in report.warnings)


class TestValidateQuestionRuleInvariantsAndBounds:
    def test_zero_denominator_fails_overall_report(self):
        report: ValidationReport = validate_question(
            question_text=r"Giá trị của biểu thức \frac{10}{0} là:",
            options=["1", "2", "3", "4"],
            correct_answer="1",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("Zero denominator detected" in err for err in report.errors)

    def test_negative_radicand_fails_overall_report(self):
        report: ValidationReport = validate_question(
            question_text=r"Tính giá trị biểu thức \sqrt{-16}",
            options=["4", "-4", "16", "0"],
            correct_answer="4",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("Negative radicand in even root" in err for err in report.errors)

    def test_parameter_bounds_violation_fails_overall_report(self):
        bp = {"bounds": {"k": {"min": 55, "max": 5000}}}
        report: ValidationReport = validate_question(
            question_text="Cho tham số k = 10. Tính kết quả biểu thức x - 5 = 0",
            options=["5", "6", "7", "8"],
            correct_answer="5",
            blueprint=bp,
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("below minimum 55" in err for err in report.errors)


class TestValidateVariantConvenienceWrapper:
    def test_validate_generated_variant(self):
        variant = GeneratedVariant(
            variant_id="VAR-AGG-001",
            source_question_id="SRC-001",
            question_text="Cho hình chóp tam giác đều S.ABC có đáy là tam giác cạnh 3.",
            options=["9", "12", "15", "18"],
            correct_answer="9",
            solution_steps=r"\text{Diện tích đáy là } 9.",
        )
        report: ValidationReport = validate_variant(variant)
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "rule_only"

    def test_validate_source_question(self):
        source = SourceQuestion(
            id="SRC-AGG-001",
            question_text="Giải phương trình $x - 4 = 0$",
            options=["4", "5", "6", "7"],
            correct_answer="A",
        )
        report: ValidationReport = validate_variant(source)
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "sympy_verified"

    def test_validate_duck_typed_dict(self):
        var_dict = {
            "question_text": "Giải phương trình $x + 3 = 0$",
            "options": ["-3", "0", "3", "6"],
            "correct_answer": "-3",
        }
        report: ValidationReport = validate_variant(var_dict)
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "sympy_verified"

    def test_with_real_blueprint_partition_probability(self):
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

        report: ValidationReport = validate_question(
            question_text=stem,
            options=options,
            correct_answer=ans,
            blueprint=blueprint_data,
            parameters={"Q_K": 3190},
        )
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "rule_only"
        assert any("geometry" in w or "out-of-scope" in w for w in report.warnings)


class TestAggregatorReviewRegressionFixes:
    def test_domain_error_from_cas_fails(self):
        # Solution x = 1 causes denominator x - 1 = 0
        report = validate_question(
            question_text=r"Phương trình $\frac{1}{x-1} = 0$ có nghiệm là",
            options=["1", "2", "3", "4"],
            correct_answer="A",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any(
            "zero" in err.lower() or "domain" in err.lower() or "denominator" in err.lower()
            for err in report.errors
        )

    def test_multiple_options_satisfying_equation_fails(self):
        # x^2 - 1 = 0 has roots x = 1 and x = -1; both A and B are roots
        report = validate_question(
            question_text="Phương trình $x^2 - 1 = 0$ có nghiệm là",
            options=["1", "-1", "2", "3"],
            correct_answer="A",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("Multiple options satisfy the equation" in err for err in report.errors)

    def test_unique_option_satisfying_equation_passes(self):
        # x^2 - 1 = 0 with only x = 1 in options
        report = validate_question(
            question_text="Phương trình $x^2 - 1 = 0$ có nghiệm là",
            options=["1", "2", "3", "4"],
            correct_answer="A",
        )
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "sympy_verified"
        assert len(report.errors) == 0

    def test_zero_bounds_not_dropped_in_aggregator(self):
        # k = -1 is below minimum 0
        report = validate_question(
            question_text="Cho giá trị tham số k = -1",
            options=["1", "2", "3", "4"],
            correct_answer="1",
            blueprint={"bounds": {"min": 0, "max": 10}},
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("below minimum 0" in err for err in report.errors)

    def test_mathematically_equivalent_answer_passes(self):
        # Option A is 1/2, correct answer is 0.5
        report = validate_question(
            question_text="Phương trình $2x - 1 = 0$ có nghiệm là",
            options=["1/2", "1", "2", "3"],
            correct_answer="0.5",
        )
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "sympy_verified"
        assert len(report.errors) == 0

    def test_worker_oserror_does_not_erase_multiple_correct_solutions_failure(self):
        # A=1 and B=-1 both satisfy x^2 - 1 = 0.
        # If testing distractor C=2 triggers an OSError (worker process error),
        # the multiple solutions failure MUST NOT be overwritten or erased into passed!
        call_count = 0

        def mock_verify(question_text: str, correct_answer: str, timeout: float):
            nonlocal call_count
            call_count += 1
            if correct_answer == "1":
                return EvaluationResult(
                    status=EvaluationStatus.VERIFIED,
                    passed=True,
                    confidence="sympy_verified",
                    detail="Verified candidate answer '1'",
                )
            if correct_answer == "-1":
                return EvaluationResult(
                    status=EvaluationStatus.VERIFIED,
                    passed=True,
                    confidence="sympy_verified",
                    detail="Verified candidate answer '-1'",
                )
            if correct_answer == "2":
                raise OSError("Cannot allocate worker process in pool")
            return EvaluationResult(
                status=EvaluationStatus.FAILED,
                passed=False,
                confidence="sympy_verified",
                detail="Not a root",
            )

        with patch(
            "app.services.validator.aggregator.verify_question_math", side_effect=mock_verify
        ):
            report = validate_question(
                question_text="Phương trình $x^2 - 1 = 0$ có nghiệm là",
                options=["1", "-1", "2", "3"],
                correct_answer="A",
            )

        assert report.passed is False
        assert report.status == "failed"
        assert any("Multiple options satisfy the equation" in err for err in report.errors)
        assert any("worker error" in w.lower() or "oserror" in w.lower() for w in report.warnings)

    def test_flexible_label_designations_in_aggregator(self):
        # Various valid letter formats must resolve correctly across all validation tiers
        for ans in ["A.", "Option A", "(A)", "Phương án A", "Đáp án A"]:
            report = validate_question(
                question_text="Phương trình $x + 1 = 2$ có nghiệm là",
                options=["1", "2", "3", "4"],
                correct_answer=ans,
            )
            assert report.passed is True
            assert report.status == "passed"
            assert report.confidence == "sympy_verified"
            assert len(report.errors) == 0

    def test_out_of_scope_complex_numbers_in_aggregator(self):
        # Complex numbers domain is out-of-scope for single-equation CAS and routes directly to rule fallback
        report = validate_question(
            question_text="Cho số phức z = 3 + 4i. Tìm phần thực của z.",
            options=["3", "4", "-3", "-4"],
            correct_answer="A",
        )
        assert report.passed is True
        assert report.status == "passed"
        assert report.confidence == "rule_only"
        assert any("complex_numbers" in w for w in report.warnings)

    def test_nested_latex_invariants_in_aggregator(self):
        # Denominator containing nested power 2^{3} - 8 == 0 must fail overall report
        report = validate_question(
            question_text=r"Tính giá trị của biểu thức $P = \frac{1}{2^{3} - 8}$",
            options=["1", "2", "3", "4"],
            correct_answer="1",
        )
        assert report.passed is False
        assert report.status == "failed"
        assert any("Zero denominator detected" in err for err in report.errors)

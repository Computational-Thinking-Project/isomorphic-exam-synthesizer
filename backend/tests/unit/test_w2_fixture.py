"""AI handoff fixtures preserve rendered evidence, not just JSON shape."""

import json
from pathlib import Path

import pytest

from app.models.generation import QuestionResult, render_solution

FIXTURES = Path(__file__).parents[1] / "fixtures"


def assert_result_evidence(raw):
    result = QuestionResult.model_validate(raw)
    if result.candidate is not None:
        candidate = result.candidate
        assert candidate.solution_md == render_solution(candidate.solution)
        assert candidate.correct_key == candidate.solution.correct_key
        assert (
            candidate.options["ABCD".index(candidate.correct_key)]
            == candidate.solution.final_answer
        )
    return result


@pytest.mark.parametrize("case", ["success", "warning_timeout", "hard_failure", "provider_failure"])
def test_ai_handoff_fixture_preserves_solution_and_key(case):
    fixture = json.loads((FIXTURES / "w2_ai_contract.json").read_text(encoding="utf-8"))
    assert_result_evidence(fixture["cases"][case]["result"])


def test_sql_receipt_is_labeled_and_preserves_full_result_evidence():
    receipt = json.loads((FIXTURES / "w2_rpc_receipt.json").read_text(encoding="utf-8"))
    assert receipt["synthetic_request_fingerprint"] is True
    assert receipt["omitted_fields"]
    for entry in receipt["resume"]["completed"] + receipt["resume"]["failures"]:
        result = assert_result_evidence(entry["raw_result"])
        assert result.source_question_id == entry["source_question_id"]
        assert result.version_index == entry["version_index"]
        assert result.request_fingerprint == entry["request_fingerprint"]
        if result.candidate is not None:
            assert result.candidate.seed == entry["seed"]

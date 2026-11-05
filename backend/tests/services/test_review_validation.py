from copy import deepcopy

import pytest

from app.models.schemas import ReviewDomainException
from app.services.review.validation import validate_candidate


def candidate():
    return {
        "stem_latex": "Solve x + 1 = 2",
        "content": "Solve x + 1 = 2",
        "options": ["1", "2", "3", "4"],
        "correct_key": "A",
        "solution_md": "Subtract one: x = 1.",
        "api_calls_count": 1,
        "validation_report": {
            "is_valid": True,
            "math_verified": False,
            "requires_teacher_review": True,
            "checks": [],
            "warnings": ["teacher review"],
        },
    }


@pytest.mark.parametrize(
    "field", ["validation_report", "solution_md", "correct_key", "api_calls_count"]
)
def test_missing_evidence_is_not_manufactured(field):
    value = candidate()
    value.pop(field)
    with pytest.raises(ReviewDomainException) as error:
        validate_candidate(value)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("is_valid", "true"),
        ("is_valid", False),
        ("math_verified", "false"),
        ("requires_teacher_review", 1),
        ("checks", None),
        ("warnings", [1]),
    ],
)
def test_report_requires_actual_typed_evidence(field, value):
    data = candidate()
    data["validation_report"][field] = value
    with pytest.raises(ReviewDomainException):
        validate_candidate(data)


@pytest.mark.parametrize("count", [True, "1", -1, 5, 1.0])
def test_calls_are_not_coerced_or_clamped(count):
    data = candidate()
    data["api_calls_count"] = count
    with pytest.raises(ReviewDomainException):
        validate_candidate(data)


def test_valid_evidence_preserved_without_mutating_input():
    data = candidate()
    before = deepcopy(data)
    result = validate_candidate(data)
    assert result["validation_report"] == before["validation_report"]
    assert result["validation_report"]["math_verified"] is False
    result["options"][0] = "changed"
    result["validation_report"]["warnings"].clear()
    assert data == before


def test_conflicting_content_is_rejected():
    data = candidate()
    data["content"] = "different question"
    with pytest.raises(ReviewDomainException):
        validate_candidate(data)


@pytest.mark.parametrize("check", [{}, {"check_name": "answer_verified", "passed": "true"}])
def test_malformed_nested_check_evidence_is_rejected(check):
    data = candidate()
    data["validation_report"]["checks"] = [check]
    with pytest.raises(ReviewDomainException):
        validate_candidate(data)


def test_math_verified_requires_the_matching_cas_check():
    data = candidate()
    data["validation_report"]["math_verified"] = True
    with pytest.raises(ReviewDomainException):
        validate_candidate(data)
    data["validation_report"]["checks"] = [
        {
            "check_name": "answer_verified",
            "passed": True,
            "status": "verified",
            "confidence": "sympy_verified",
        }
    ]
    assert validate_candidate(data)["validation_report"] == data["validation_report"]

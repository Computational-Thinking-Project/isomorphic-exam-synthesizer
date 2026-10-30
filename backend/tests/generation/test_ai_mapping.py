from copy import deepcopy
from uuid import UUID

import pytest

from app.models.generation import (
    GeneratedQuestion,
    QuestionResult,
    StepByStepSolution,
    ValidationReport,
    render_solution,
)
from app.services.generation.ai_mapping import map_source_questions, prepare_question_result
from app.services.generation.job_contracts import GenerationPlan, QuestionTarget
from app.services.validator.base import CheckResult

SESSION = UUID(int=1)
SOURCE = UUID(int=11)


def source_row(**changes):
    return {
        "id": str(SOURCE),
        "session_id": str(SESSION),
        "question_no": 1,
        "raw_content": "  Tính $2 + 2$.\nGiữ nguyên công thức.  ",
        "options": {"D": "6", "B": "4", "A": "3", "C": "5"},
        "correct_key": "B",
        "solution_md": None,
        "has_security_warning": False,
        **changes,
    }


def plan():
    return GenerationPlan(
        SESSION, UUID(int=2), (QuestionTarget(SOURCE, 1, 1),), frozenset(), 0, None
    )


def result():
    solution = StepByStepSolution(
        correct_key="B", final_answer="4", steps=[{"explanation": "Cộng hai số.", "latex": "2+2=4"}]
    )
    return QuestionResult(
        version_index=1,
        source_question_id=str(SOURCE),
        request_fingerprint="request-fingerprint",
        candidate=GeneratedQuestion(
            question_text="Tính $2+2$.",
            options=["3", "4", "5", "6"],
            correct_key="B",
            solution=solution,
            variant_id="var_saved",
            source_question_id=str(SOURCE),
            blueprint_fingerprint="blueprint-fingerprint",
            seed=1100,
            solution_md=render_solution(solution),
            has_warning=True,
        ),
        validation=ValidationReport(
            checks=[CheckResult(check_name="answer_math", passed=False, status="unsupported")]
        ),
        attempts=3,
    )


def test_sources_preserve_content_and_map_options_in_abcd_order():
    row = source_row()
    original = deepcopy(row)
    mapped = map_source_questions([row], SESSION)
    assert mapped[0].id == row["id"]
    assert mapped[0].question_text == row["raw_content"]
    assert mapped[0].options == ["3", "4", "5", "6"]
    assert mapped[0].correct_answer == "B" and mapped[0].solution == ""
    mapped[0].options[0] = "changed outside the database row"
    assert row == original


def test_sources_are_ordered_by_question_number_and_preserve_solution_warning():
    rows = [
        source_row(
            id=str(UUID(int=12)), question_no=9, solution_md="Lời giải", has_security_warning=True
        ),
        source_row(question_no=3),
    ]
    mapped = map_source_questions(rows, SESSION)
    assert [source.id for source in mapped] == [str(SOURCE), str(UUID(int=12))]
    assert mapped[1].solution == "Lời giải" and mapped[1].has_security_warning


@pytest.mark.parametrize(
    "changes",
    [
        {"session_id": str(UUID(int=99))},
        {"id": "not-a-uuid"},
        {"question_no": True},
        {"question_no": 0},
        {"question_no": "1"},
        {"raw_content": " "},
        {"raw_content": False},
        {"options": {"A": "1"}},
        {"options": {"A": "1", "B": "", "C": "3", "D": "4"}},
        {"options": {"A": "1", "B": 2, "C": "3", "D": "4"}},
        {"options": {"A": "1", "B": "1", "C": "3", "D": "4"}},
        {"correct_key": "E"},
        {"correct_key": "b"},
        {"solution_md": 9},
        {"has_security_warning": "false"},
    ],
)
def test_invalid_source_rows_fail_without_repair_or_guessing(changes):
    with pytest.raises(ValueError):
        map_source_questions([source_row(**changes)], SESSION)


@pytest.mark.parametrize("problem", ["empty", "overflow", "duplicate_id", "duplicate_number"])
def test_source_batch_boundaries_and_duplicates(problem):
    rows = [source_row()]
    if problem == "empty":
        rows = []
    elif problem == "overflow":
        rows = [source_row(id=str(UUID(int=100 + i)), question_no=i + 1) for i in range(21)]
    elif problem == "duplicate_id":
        rows.append(source_row(question_no=2))
    else:
        rows.append(source_row(id=str(UUID(int=12))))
    with pytest.raises(ValueError):
        map_source_questions(rows, SESSION)


def test_result_mapping_keeps_key_report_and_complete_resume_record():
    ai_result = result()
    original = ai_result.model_dump(mode="json")
    prepared = prepare_question_result(ai_result, plan())
    assert prepared.target == plan().targets[0]
    assert prepared.draft is not None
    assert prepared.draft.options == dict(zip("ABCD", ["3", "4", "5", "6"]))
    assert prepared.draft.correct_key == "B" and prepared.draft.retry_count == 2
    assert prepared.draft.has_warning
    assert prepared.draft.validation_report["requires_teacher_review"] is True
    assert prepared.raw_result.model_dump(mode="json") == original
    assert QuestionResult.model_validate(prepared.raw_result.model_dump(mode="json")) == ai_result
    prepared.raw_result.candidate.options[0] = "mutated by storage consumer"
    assert ai_result.model_dump(mode="json") == original


def test_error_result_has_no_invented_draft():
    failed = result().model_copy(update={"candidate": None, "error_code": "VALIDATION_FAILED"})
    prepared = prepare_question_result(failed, plan())
    assert prepared.draft is None
    assert prepared.raw_result.error_code == "VALIDATION_FAILED"


@pytest.mark.parametrize(
    "problem",
    [
        "foreign_source",
        "foreign_version",
        "candidate_source",
        "hard_failure",
        "missing_report",
        "key",
        "final_answer",
        "solution_md",
        "negative_attempts",
        "error_with_candidate",
    ],
)
def test_inconsistent_results_cannot_become_saveable_drafts(problem):
    value = result()
    if problem == "foreign_source":
        value.source_question_id = str(UUID(int=99))
    elif problem == "foreign_version":
        value.version_index = 2
    elif problem == "candidate_source":
        value.candidate.source_question_id = str(UUID(int=99))
    elif problem == "hard_failure":
        value.validation.checks = [CheckResult(check_name="logic", passed=False, status="failed")]
    elif problem == "missing_report":
        value.validation = None
    elif problem == "key":
        value.candidate.solution.correct_key = "A"
    elif problem == "final_answer":
        value.candidate.solution.final_answer = "999"
    elif problem == "solution_md":
        value.candidate.solution_md = "A different solution"
    elif problem == "negative_attempts":
        value.attempts = -1
    else:
        value.error_code = "VALIDATION_FAILED"
    with pytest.raises(ValueError):
        prepare_question_result(value, plan())

"""In-Memory Pre-validator and Zero Database Mutation Guard (TASK-202, ADR-002, TASK-203b)."""

from typing import List

from fastapi import HTTPException, status

from app.models.schemas import ParsedQuestionItem, ParserErrorItem

MIN_QUESTIONS: int = 1
MAX_QUESTIONS: int = 20


def validate_exam_integrity(
    questions: List[ParsedQuestionItem],
    parser_errors: List[ParserErrorItem],
) -> List[ParserErrorItem]:
    """Validate parsed questions in-memory and return a consolidated list of errors."""
    all_errors: List[ParserErrorItem] = list(parser_errors)

    # 1. Question count boundary check [1, 20]
    total_q = len(questions)
    if total_q < MIN_QUESTIONS:
        all_errors.append(
            ParserErrorItem(
                question_no=0,
                error_type="INVALID_FORMAT",
                message="No valid exam questions detected. Exam must contain at least 1 question.",
            )
        )
    elif total_q > MAX_QUESTIONS:
        all_errors.append(
            ParserErrorItem(
                question_no=0,
                error_type="INVALID_FORMAT",
                message=f"Detected {total_q} questions. Exam cannot exceed maximum limit of {MAX_QUESTIONS} questions.",
            )
        )

    # 2. Check each question's integrity
    for q in questions:
        # Check missing answer
        if (
            q.has_missing_answer
            or not q.correct_key
            or q.correct_key.upper() not in {"A", "B", "C", "D"}
        ):
            if not any(
                e.question_no == q.question_no and e.error_type == "MISSING_ANSWER"
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=q.question_no,
                        error_type="MISSING_ANSWER",
                        message=f"Question {q.question_no} does not have a valid correct answer key.",
                    )
                )

        # Check OMML
        if q.has_unparsed_omml:
            if not any(
                e.question_no == q.question_no and e.error_type == "UNPARSED_OMML"
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=q.question_no,
                        error_type="UNPARSED_OMML",
                        message=f"Question {q.question_no} contains unparsed OMML / Equation formulas.",
                    )
                )

        # Check options
        if len(q.options) != 4 or not all(k in q.options for k in ["A", "B", "C", "D"]):
            if not any(
                e.question_no == q.question_no and e.error_type == "INVALID_FORMAT"
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=q.question_no,
                        error_type="INVALID_FORMAT",
                        message=f"Question {q.question_no} is missing one or more options (A, B, C, D required).",
                    )
                )

    # Sort errors by question_no ascending
    all_errors.sort(key=lambda x: x.question_no)
    return all_errors


def assert_zero_mutation_or_raise(
    questions: List[ParsedQuestionItem],
    parser_errors: List[ParserErrorItem],
) -> None:
    """Enforce ADR-002: If any errors exist, raise HTTP 422 immediately with structured errors list.

    Guarantees the database is untouched on failure.
    """
    consolidated_errors = validate_exam_integrity(questions, parser_errors)
    if consolidated_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Exam content incomplete or unprocessable",
                "errors": [err.model_dump() for err in consolidated_errors],
            },
        )

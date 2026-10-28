"""In-Memory Pre-validator and Zero Database Mutation Guard (TASK-202, ADR-002, TASK-203b)."""

from typing import List, Optional

from fastapi import HTTPException, status

from app.models.schemas import ParsedQuestionItem, ParserErrorItem
from app.services.parser.utils import RawAnswerKeyInfo

MIN_QUESTIONS: int = 1
MAX_QUESTIONS: int = 20


def validate_exam_integrity(
    questions: List[ParsedQuestionItem],
    parser_errors: List[ParserErrorItem],
    answer_key_info: Optional[RawAnswerKeyInfo] = None,
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

    # 2. Check question numbers uniqueness and validity
    seen_q_nums = set()
    for q in questions:
        if q.question_no <= 0:
            if not any(
                e.question_no == q.question_no and e.error_type == "INVALID_QUESTION_NO"
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=q.question_no,
                        error_type="INVALID_QUESTION_NO",
                        message=f"Question number {q.question_no} is invalid. Question numbers must be positive integers.",
                    )
                )
        if q.question_no in seen_q_nums:
            if not any(
                e.question_no == q.question_no and e.error_type == "DUPLICATE_QUESTION_NO"
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=q.question_no,
                        error_type="DUPLICATE_QUESTION_NO",
                        message=f"Duplicate question number {q.question_no} detected in exam.",
                    )
                )
        seen_q_nums.add(q.question_no)

    # 3. Check each question's individual integrity
    for q in questions:
        # Check empty question stem
        if q.is_empty_stem or not q.raw_content.strip():
            if not any(
                e.question_no == q.question_no and e.error_type == "EMPTY_STEM"
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=q.question_no,
                        error_type="EMPTY_STEM",
                        message=f"Question {q.question_no} has an empty question stem (no prompt text).",
                    )
                )

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

        # Check unparsed images / drawings
        if q.has_unparsed_image:
            if not any(
                e.question_no == q.question_no and e.error_type == "UNPARSED_IMAGE"
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=q.question_no,
                        error_type="UNPARSED_IMAGE",
                        message=f"Question {q.question_no} contains unparsed embedded images or drawings.",
                    )
                )

        # Check options: all 4 keys A, B, C, D must exist and each option's text must not be empty after strip()
        has_invalid_options = (
            len(q.options) != 4
            or not all(k in q.options for k in ["A", "B", "C", "D"])
            or any(not (q.options.get(k) or "").strip() for k in ["A", "B", "C", "D"])
        )
        if has_invalid_options:
            if not any(
                e.question_no == q.question_no and e.error_type in ("INVALID_FORMAT", "AMBIGUOUS_FORMAT")
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=q.question_no,
                        error_type="INVALID_FORMAT",
                        message=f"Question {q.question_no} is missing one or more options or contains empty option content (A, B, C, D required).",
                    )
                )

    # 4. Check answer key integrity if RawAnswerKeyInfo is provided
    if answer_key_info is not None:
        for conf_q, conf_keys in answer_key_info.conflicts.items():
            if not any(
                e.question_no == conf_q and e.error_type == "CONFLICTING_ANSWER_KEY"
                for e in all_errors
            ):
                all_errors.append(
                    ParserErrorItem(
                        question_no=conf_q,
                        error_type="CONFLICTING_ANSWER_KEY",
                        message=f"Question {conf_q} has conflicting answer keys in answer section: {conf_keys}",
                    )
                )

        for pair_q, _ in answer_key_info.raw_pairs:
            if pair_q <= 0:
                if not any(
                    e.question_no == pair_q and e.error_type == "INVALID_QUESTION_NO"
                    for e in all_errors
                ):
                    all_errors.append(
                        ParserErrorItem(
                            question_no=pair_q,
                            error_type="INVALID_QUESTION_NO",
                            message=f"Answer key contains invalid question number {pair_q} (question numbers must be positive integers).",
                        )
                    )
            elif pair_q not in seen_q_nums:
                if not any(
                    e.question_no == pair_q and e.error_type == "SURPLUS_ANSWER_KEY"
                    for e in all_errors
                ):
                    all_errors.append(
                        ParserErrorItem(
                            question_no=pair_q,
                            error_type="SURPLUS_ANSWER_KEY",
                            message=f"Answer key contains answer for question {pair_q} which does not exist in the exam questions.",
                        )
                    )

    # Sort errors by question_no ascending
    all_errors.sort(key=lambda x: x.question_no)
    return all_errors


def assert_zero_mutation_or_raise(
    questions: List[ParsedQuestionItem],
    parser_errors: List[ParserErrorItem],
    answer_key_info: Optional[RawAnswerKeyInfo] = None,
) -> None:
    """Enforce ADR-002: If any errors exist, raise HTTP 422 immediately with structured errors list.

    Guarantees the database is untouched on failure.
    """
    consolidated_errors = validate_exam_integrity(
        questions, parser_errors, answer_key_info=answer_key_info
    )
    if consolidated_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Exam content incomplete or unprocessable",
                "errors": [err.model_dump() for err in consolidated_errors],
            },
        )

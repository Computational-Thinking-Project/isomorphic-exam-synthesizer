"""Review Lifecycle API Endpoints (TASK-301).

Exposes:
- POST /api/sessions/{session_id}/questions/{version_question_id}/accept
- POST /api/sessions/{session_id}/questions/{version_question_id}/reject
- POST /api/sessions/{session_id}/questions/{version_question_id}/revert
- GET  /api/sessions/{session_id}/review/progress
"""

import logging

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.models.schemas import (
    CurrentUser,
    RegeneratedQuestionResponse,
    ReviewActionResponse,
    ReviewProgressResponse,
)
from app.services.review.service import ReviewService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/{session_id}/questions/{version_question_id}/accept",
    response_model=ReviewActionResponse,
    summary="Approve a question variant (TASK-301)",
    description="Chấp nhận câu hỏi biến thể hiện hành. Thao tác có tính chất idempotent.",
)
async def accept_question_endpoint(
    session_id: str,
    version_question_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ReviewActionResponse:
    """Accept and approve a version question."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    assert_ownership("version_questions", version_question_id, current_user.id, db=db)

    service = ReviewService(db)
    return await service.accept_question(session_id, version_question_id, current_user.id)


@router.post(
    "/{session_id}/questions/{version_question_id}/reject",
    response_model=RegeneratedQuestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject question and regenerate a new variant (TASK-301)",
    description=(
        "Từ chối câu hỏi biến thể và kích hoạt AI sinh lại câu mới ngoài DB transaction. "
        "Thao tác nhị phân nghiêm ngặt (không nhận text từ chối thủ công)."
    ),
)
async def reject_question_endpoint(
    session_id: str,
    version_question_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> RegeneratedQuestionResponse:
    """Reject question variant and trigger targeted regeneration."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    assert_ownership("version_questions", version_question_id, current_user.id, db=db)

    service = ReviewService(db)
    return await service.reject_question(session_id, version_question_id, current_user.id)


@router.post(
    "/{session_id}/questions/{version_question_id}/revert",
    response_model=ReviewActionResponse,
    summary="Atomically revert variant to source question (TASK-301)",
    description="Hoàn nguyên câu hỏi về nguyên bản câu gốc. Thao tác có tính chất idempotent.",
)
async def revert_question_endpoint(
    session_id: str,
    version_question_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ReviewActionResponse:
    """Revert question variant back to original source content."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    assert_ownership("version_questions", version_question_id, current_user.id, db=db)

    service = ReviewService(db)
    return await service.revert_question(session_id, version_question_id, current_user.id)


@router.get(
    "/{session_id}/review/progress",
    response_model=ReviewProgressResponse,
    summary="Get review progress metrics (TASK-301)",
    description="Truy vấn tiến độ duyệt câu hỏi của phiên làm việc (Read-only, tuân thủ Invariant đa version).",
)
async def get_review_progress_endpoint(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ReviewProgressResponse:
    """Query current review progress metrics for the session."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    service = ReviewService(db)
    return await service.get_progress(session_id)

"""Review Lifecycle API Endpoints (TASK-301).

Exposes:
- POST /api/sessions/{session_id}/questions/{version_question_id}/accept
- POST /api/sessions/{session_id}/questions/{version_question_id}/reject
- POST /api/sessions/{session_id}/questions/{version_question_id}/revert
- GET  /api/sessions/{session_id}/review/progress
"""

import logging
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Header, Request, Response, status
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_service_db, get_user_db
from app.models.schemas import (
    CurrentUser,
    RegeneratedQuestionResponse,
    ReviewActionResponse,
    ReviewProgressResponse,
    ReviewSnapshotResponse,
)
from app.services.review.service import ReviewService, action_key, resource_ids

logger = logging.getLogger(__name__)

router = APIRouter()


def get_ai_generator(request: Request) -> Optional[Callable[..., Any]]:
    """Dependency provider for AI variant regeneration adapter (TASK-304).

    Returns None if not configured in production, raising HTTP 503 rather than fabricating mock data.
    Tests can override this dependency with an explicit mock fixture.
    """
    ai_services = getattr(request.app.state, "ai_services", None)
    configured_keys = getattr(getattr(ai_services, "settings", None), "get_gemini_api_keys", None)
    if ai_services is None or not callable(configured_keys) or not configured_keys():
        return None
    try:
        from app.services.generation.targeted_service import TargetedRegenerator

        return TargetedRegenerator(
            service=ai_services.generation,
            max_api_calls=4,
            timeout_seconds=40.0,
        )
    except Exception as exc:
        logger.warning("Could not initialize TargetedRegenerator: %s", exc)
        return None


@router.post(
    "/{session_id}/questions/{version_question_id}/accept",
    response_model=ReviewActionResponse,
    summary="Approve a question variant (TASK-301)",
    description="Chấp nhận câu hỏi biến thể hiện hành. Thao tác có tính chất idempotent.",
)
async def accept_question_endpoint(
    session_id: str,
    version_question_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ReviewActionResponse:
    """Accept and approve a version question."""
    resource_ids(session_id, version_question_id)
    if idempotency_key is not None:
        action_key(idempotency_key)
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    assert_ownership("version_questions", version_question_id, current_user.id, db=db)

    service = ReviewService(db)
    return await service.accept_question(
        session_id, version_question_id, current_user.id, idempotency_key=idempotency_key
    )


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
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
    service_db: Client = Depends(get_service_db),
    ai_generator: Optional[Callable[..., Any]] = Depends(get_ai_generator),
) -> RegeneratedQuestionResponse:
    """Reject question variant and trigger targeted regeneration."""
    resource_ids(session_id, version_question_id)
    if idempotency_key is not None:
        action_key(idempotency_key)
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    assert_ownership("version_questions", version_question_id, current_user.id, db=db)

    service = ReviewService(db=db, service_db=service_db, ai_generator=ai_generator)
    return await service.reject_question(
        session_id, version_question_id, current_user.id, idempotency_key=idempotency_key
    )


@router.post(
    "/{session_id}/questions/{version_question_id}/revert",
    response_model=ReviewActionResponse,
    summary="Atomically revert variant to source question (TASK-301)",
    description="Hoàn nguyên câu hỏi về nguyên bản câu gốc. Thao tác có tính chất idempotent.",
)
async def revert_question_endpoint(
    session_id: str,
    version_question_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ReviewActionResponse:
    """Revert question variant back to original source content."""
    resource_ids(session_id, version_question_id)
    if idempotency_key is not None:
        action_key(idempotency_key)
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    assert_ownership("version_questions", version_question_id, current_user.id, db=db)

    service = ReviewService(db)
    return await service.revert_question(
        session_id, version_question_id, current_user.id, idempotency_key=idempotency_key
    )


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
    resource_ids(session_id)
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    service = ReviewService(db=db)
    return await service.get_progress(session_id, current_user.id)


@router.get(
    "/{session_id}/review/snapshot",
    response_model=ReviewSnapshotResponse,
    summary="Get current candidate review snapshot (W4-MVP-03)",
    description=(
        "Đọc ma trận ứng viên biến thể hiện hành (current candidate snapshot) trước khi shuffle. "
        "Bảo đảm tính nguyên tử, xác thực chủ sở hữu, trả về đủ N x M slot và provenance chi tiết."
    ),
)
async def get_review_snapshot_endpoint(
    session_id: str,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ReviewSnapshotResponse:
    """Query current review candidate snapshot for the session."""
    resource_ids(session_id)
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    # Set cache control header
    response.headers["Cache-Control"] = "no-store"

    service = ReviewService(db=db)
    return await service.get_current_snapshot(session_id, current_user.id)

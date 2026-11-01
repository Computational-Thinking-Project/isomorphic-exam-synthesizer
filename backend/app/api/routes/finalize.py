"""Finalize & Content Lock API Endpoints (TASK-305).

Exposes:
- POST /api/sessions/{session_id}/finalize/approve: Final approval and content lock
- GET  /api/sessions/{session_id}/finalize/matrix: Answers matrix cross-check
"""

import logging

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.models.schemas import (
    AnswersMatrixResponse,
    CurrentUser,
    FinalizeApproveResponse,
)
from app.services.finalize.service import FinalizeService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/{session_id}/finalize/approve",
    response_model=FinalizeApproveResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve exam session and lock content (TASK-305)",
    description=(
        "Phê duyệt cuối cùng phiên làm việc khi thỏa mãn 4 điều kiện chốt đề "
        "(100% câu approved, 0 câu regenerating, 100% version finalized, session status reviewed/generated). "
        "Khóa vĩnh viễn nội dung phiên đề (HTTP 423 với các thao tác chỉnh sửa tiếp theo)."
    ),
)
async def finalize_approve_endpoint(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> FinalizeApproveResponse:
    """Approve an exam session and lock contents."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    service = FinalizeService(db)
    return await service.approve_session(session_id, current_user.id)


@router.get(
    "/{session_id}/finalize/matrix",
    response_model=AnswersMatrixResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cross-version answers matrix (TASK-305)",
    description=(
        "Truy xuất bảng ma trận đối soát đáp án của tất cả các đề sau hoán vị. "
        "Ưu tiên lấy từ bảng answer_keys, tự động fallback sang version_questions."
    ),
)
async def finalize_matrix_endpoint(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> AnswersMatrixResponse:
    """Retrieve the answers matrix across all exam versions."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    service = FinalizeService(db)
    return await service.get_answers_matrix(session_id, current_user.id)

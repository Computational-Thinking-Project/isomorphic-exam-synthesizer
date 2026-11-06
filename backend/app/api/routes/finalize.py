"""Finalize & Content Lock API Endpoints (TASK-305).

Exposes:
- POST /api/sessions/{session_id}/finalize/approve: Final approval and content lock
- POST /api/sessions/{session_id}/finalize/shuffle: Persist a reviewed exam shuffle
- GET  /api/sessions/{session_id}/finalize/matrix: Answers matrix cross-check
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_service_db, get_user_db
from app.models.schemas import (
    AnswersMatrixResponse,
    CurrentUser,
    FinalizeApproveResponse,
    PreviewSnapshotResponse,
    ReviewDomainException,
)
from app.services.finalize.repository import FinalizeRepository
from app.services.finalize.service import FinalizeService
from app.services.shuffler.schemas import FinalizeShuffleResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def validate_session_uuid(session_id: str) -> str:
    """Pre-validate session_id format to prevent PostgREST 22P02 unhandled HTTP 500 at assert_ownership (F18)."""
    try:
        val = UUID(session_id)
        if str(val) != session_id.lower():
            raise ValueError("UUID representation mismatch")
    except (ValueError, AttributeError):
        raise ReviewDomainException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="ERR_INVALID_SESSION_ID",
            detail=f"Mã phiên làm việc '{session_id}' không đúng định dạng UUID",
        )
    return session_id


@router.post(
    "/{session_id}/finalize/shuffle",
    response_model=FinalizeShuffleResponse,
    status_code=status.HTTP_200_OK,
    summary="Shuffle and finalize reviewed exam versions",
    description="Hoán vị xác định từ dữ liệu canonical của phiên reviewed; ghi nguyên tử trước khi trả kết quả.",
)
async def finalize_shuffle_endpoint(
    session_id: str = Depends(validate_session_uuid),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
    writer_db: Client = Depends(get_service_db),
) -> FinalizeShuffleResponse:
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    return await FinalizeService(db, writer_repo=FinalizeRepository(writer_db)).shuffle_session(
        session_id, current_user.id
    )


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
    session_id: str = Depends(validate_session_uuid),
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
        "Đọc answer_keys đầy đủ và hợp lệ; trả lỗi 409 nếu dữ liệu không nhất quán."
    ),
)
async def finalize_matrix_endpoint(
    session_id: str = Depends(validate_session_uuid),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> AnswersMatrixResponse:
    """Retrieve the answers matrix across all exam versions."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    service = FinalizeService(db)
    return await service.get_answers_matrix(session_id, current_user.id)


@router.get(
    "/{session_id}/finalize/preview",
    response_model=PreviewSnapshotResponse,
    status_code=status.HTTP_200_OK,
    summary="Get post-shuffle pre-approval preview projection (W4-MVP-05)",
    description=(
        "Truy xuất ảnh chiếu xem trước toàn bộ các phiên bản đề thi sau hoán vị trước khi phê duyệt. "
        "Bao gồm thứ tự câu hiển thị (1..M), thứ tự phương án A-D sau xáo trộn, đáp án đúng hiển thị, "
        "lời giải chi tiết đã đồng bộ nhãn đáp án, và ma trận đối soát đáp án chéo giữa các mã đề."
    ),
)
async def finalize_preview_endpoint(
    session_id: str = Depends(validate_session_uuid),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> PreviewSnapshotResponse:
    """Retrieve the post-shuffle display preview projection across all versions."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    service = FinalizeService(db)
    return await service.get_preview_snapshot(session_id, current_user.id)

"""Service Layer for Finalize and Content Lock (TASK-305).

Coordinates:
- Verification of session existence and status
- Idempotency guarantees for already-approved sessions
- Strict enforcement of the 4 approval pre-conditions
- Invocation of atomic update in repository
- Assembly and normalization of cross-version answer matrices
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from supabase import Client

from app.models.schemas import (
    AnswersMatrixResponse,
    FinalizeApproveResponse,
    MatrixItem,
    ReviewDomainException,
)
from app.services.finalize.repository import FinalizeRepository

logger = logging.getLogger(__name__)


class FinalizeService:
    """Business logic coordinator for the finalize lifecycle."""

    def __init__(self, db: Client, repo: Optional[FinalizeRepository] = None) -> None:
        self.db = db
        self.repo = repo or FinalizeRepository(db)

    async def approve_session(
        self, session_id: str, user_id: str
    ) -> FinalizeApproveResponse:
        """Approve an exam session and permanently lock its contents.

        Enforces:
        1. Session existence (404 ERR_SESSION_NOT_FOUND)
        2. Idempotency: if already 'approved', return 200 with stored approved_at
        3. Allowed state: must be 'reviewed' or 'generated' (409 ERR_INVALID_SESSION_STATE)
        4. Pre-conditions:
           - Total versions > 0 and 100% versions is_finalized=true (400 ERR_VERSIONS_NOT_FINALIZED)
           - 0 questions regenerating (409 ERR_QUESTION_REGENERATING)
           - 100% current questions approved (400 ERR_NOT_ALL_QUESTIONS_APPROVED)
        5. Atomic state update to 'approved'
        """
        # Step 1: Check session existence
        session_meta = await self.repo.get_session_meta(session_id)
        if not session_meta:
            raise ReviewDomainException(
                404, "ERR_SESSION_NOT_FOUND", f"Phiên làm việc '{session_id}' không tồn tại"
            )

        current_status = str(session_meta.get("status", "")).lower()

        # Step 2: Idempotent return if already approved
        if current_status == "approved":
            approved_at = str(session_meta.get("approved_at") or "")
            logger.info(
                "FinalizeService: Session %s is already approved (approved_at=%s), returning idempotent response",
                session_id,
                approved_at,
            )
            return FinalizeApproveResponse(
                session_id=session_id,
                status="approved",
                approved_at=approved_at,
                message="Phiên đề đã được phê duyệt trước đó",
            )

        # Step 3: Verify session status is allowed for approval
        if current_status not in ("reviewed", "generated"):
            raise ReviewDomainException(
                409,
                "ERR_INVALID_SESSION_STATE",
                f"Phiên đề ở trạng thái '{current_status}' không thể phê duyệt. Cần ở trạng thái 'reviewed' hoặc 'generated'.",
            )

        # Step 4: Verify pre-conditions
        stats = await self.repo.check_preconditions(session_id)

        # 4a. Check versions finalized
        total_versions = stats.get("total_versions", 0)
        unfinalized_versions = stats.get("unfinalized_versions_count", 0)
        if total_versions == 0:
            raise ReviewDomainException(
                400,
                "ERR_VERSIONS_NOT_FINALIZED",
                "Phiên đề chưa được khởi tạo các phiên bản hoán vị (chưa qua TASK-303)",
            )
        if unfinalized_versions > 0:
            raise ReviewDomainException(
                400,
                "ERR_VERSIONS_NOT_FINALIZED",
                f"Còn {unfinalized_versions}/{total_versions} phiên bản đề thi chưa hoàn tất hoán vị (is_finalized=False)",
            )

        # 4b. Check regenerating questions
        regenerating_count = stats.get("regenerating_count", 0)
        if regenerating_count > 0:
            raise ReviewDomainException(
                409,
                "ERR_QUESTION_REGENERATING",
                f"Còn {regenerating_count} câu hỏi đang trong tiến trình sinh lại bởi AI",
            )

        # 4c. Check all questions approved
        unapproved_count = stats.get("unapproved_count", 0)
        total_questions = stats.get("total_questions", 0)
        if total_questions == 0:
            raise ReviewDomainException(
                400,
                "ERR_NOT_ALL_QUESTIONS_APPROVED",
                "Phiên đề chưa có câu hỏi nào để phê duyệt",
            )
        if unapproved_count > 0:
            raise ReviewDomainException(
                400,
                "ERR_NOT_ALL_QUESTIONS_APPROVED",
                f"Còn {unapproved_count}/{total_questions} câu hỏi hiện hành chưa được thẩm định phê duyệt (status != 'approved')",
            )

        # Step 5: Atomic update
        updated_row = await self.repo.update_session_approved(
            session_id, allowed_statuses=["reviewed", "generated"]
        )

        # If update returned None, check if race occurred and it got approved concurrently
        if not updated_row:
            latest_meta = await self.repo.get_session_meta(session_id)
            if latest_meta and str(latest_meta.get("status", "")).lower() == "approved":
                return FinalizeApproveResponse(
                    session_id=session_id,
                    status="approved",
                    approved_at=str(latest_meta.get("approved_at") or ""),
                    message="Phiên đề đã được phê duyệt",
                )
            raise ReviewDomainException(
                409,
                "ERR_INVALID_SESSION_STATE",
                "Trạng thái phiên đề đã thay đổi trong quá trình xử lý, vui lòng thử lại",
            )

        approved_at_res = str(updated_row.get("approved_at") or "")
        logger.info(
            "FinalizeService: Successfully approved session %s at %s",
            session_id,
            approved_at_res,
        )

        return FinalizeApproveResponse(
            session_id=session_id,
            status="approved",
            approved_at=approved_at_res,
            message="Phê duyệt phiên thi thành công và đã khóa nội dung",
        )

    async def get_answers_matrix(
        self, session_id: str, user_id: str
    ) -> AnswersMatrixResponse:
        """Fetch and structure cross-version answer key matrix.

        Returns a sorted matrix of answers per question_no across all version_codes.
        """
        # Step 1: Check session existence
        session_meta = await self.repo.get_session_meta(session_id)
        if not session_meta:
            raise ReviewDomainException(
                404, "ERR_SESSION_NOT_FOUND", f"Phiên làm việc '{session_id}' không tồn tại"
            )

        # Step 2: Fetch raw rows
        version_codes, rows = await self.repo.fetch_matrix_raw(session_id)
        if not version_codes:
            return AnswersMatrixResponse(
                session_id=session_id,
                total_questions=0,
                version_codes=[],
                matrix=[],
            )

        # Step 3: Group answers by question_no
        grouped: Dict[int, Dict[str, str]] = defaultdict(dict)
        for r in rows:
            q_no = r["question_no"]
            v_code = r["version_code"]
            ans = r["answer"]
            grouped[q_no][v_code] = ans

        # Step 4: Build sorted matrix items
        sorted_q_numbers = sorted(grouped.keys())
        matrix_items: List[MatrixItem] = []

        for q_no in sorted_q_numbers:
            matrix_items.append(
                MatrixItem(
                    question_no=q_no,
                    answers=grouped[q_no],
                )
            )

        return AnswersMatrixResponse(
            session_id=session_id,
            total_questions=len(matrix_items),
            version_codes=version_codes,
            matrix=matrix_items,
        )

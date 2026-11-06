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
from uuid import UUID

from supabase import Client

from app.models.schemas import (
    AnswersMatrixResponse,
    FinalizeApproveResponse,
    MatrixItem,
    ReviewDomainException,
)
from app.services.finalize.repository import FinalizeRepository, _valid_timestamp
from app.services.finalize.shuffle_input import prepare_shuffle
from app.services.review.repository import ReviewRepository
from app.services.review.service import session_lock_registry
from app.services.shuffler.schemas import FinalizeShuffleResponse

logger = logging.getLogger(__name__)


class FinalizeService:
    """Business logic coordinator for the finalize lifecycle."""

    def __init__(
        self,
        db: Client,
        repo: Optional[FinalizeRepository] = None,
        *,
        writer_repo: Optional[FinalizeRepository] = None,
    ) -> None:
        self.db = db
        self.repo = repo or FinalizeRepository(db)
        self.writer_repo = writer_repo

    async def shuffle_session(self, session_id: str, user_id: str) -> FinalizeShuffleResponse:
        """Compute from canonical inputs and return only a validated RPC receipt."""
        try:
            session_id = str(UUID(session_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ReviewDomainException(
                400, "ERR_INVALID_SESSION_ID", "Mã phiên không hợp lệ"
            ) from exc
        meta = await self.repo.get_session_meta(session_id)
        if not meta or str(meta.get("user_id")) != user_id:
            raise ReviewDomainException(404, "ERR_SESSION_NOT_FOUND", "Không tìm thấy phiên đề")
        if meta.get("status") in ("approved", "exported") or meta.get("approved_at") is not None:
            raise ReviewDomainException(423, "ERR_SESSION_LOCKED", "Phiên đề đã được khóa")
        if meta.get("status") != "reviewed":
            raise ReviewDomainException(409, "ERR_INVALID_SESSION_STATE", "Phiên đề chưa sẵn sàng")
        progress = await ReviewRepository(self.db).progress(session_id)
        if progress.get("ready") is not True:
            raise ReviewDomainException(409, "ERR_SHUFFLE_NOT_READY", "Phiên đề chưa sẵn sàng")
        snapshot = await self.repo.fetch_shuffle_snapshot(session_id)
        results = prepare_shuffle(
            session_id,
            snapshot["config"],
            snapshot["versions"],
            snapshot["sources"],
            snapshot["questions"],
        )
        if self.writer_repo is None:
            raise ReviewDomainException(
                503, "ERR_SHUFFLE_UNAVAILABLE", "Trusted shuffle writer is not configured"
            )
        # Never accept shuffle output/actor from the HTTP request. The backend
        # computes it from owner-scoped reads and the verified CurrentUser.
        payload = {
            "actor_id": user_id,
            "snapshot": snapshot,
            "versions": [r.model_dump(mode="json") for r in results],
        }
        receipt = await self.writer_repo.persist_shuffle_rpc(
            session_id, payload, snapshot["versions"], len(snapshot["sources"])
        )
        return FinalizeShuffleResponse.model_validate(receipt)

    async def approve_session(self, session_id: str, user_id: str) -> FinalizeApproveResponse:
        """Approve an exam session and permanently lock its contents.

        Enforces:
        1. Session existence (404 ERR_SESSION_NOT_FOUND)
        2. Idempotency: if already 'approved', return 200 with stored approved_at
        3. Allowed state: must be 'reviewed' (409 ERR_INVALID_SESSION_STATE)
        4. Pre-conditions:
           - Total versions > 0 and 100% versions is_finalized=true (400 ERR_VERSIONS_NOT_FINALIZED)
           - 0 questions regenerating (409 ERR_QUESTION_REGENERATING)
           - 100% current questions approved and no missing pairs across all versions (400 ERR_NOT_ALL_QUESTIONS_APPROVED)
        5. Atomic state update to 'approved' serialized via session_lock_registry and optimistic lock
        """
        # Edge case guard (F05): Validate UUID format to prevent unhandled ValueError 500
        try:
            session_uuid = UUID(session_id)
        except (ValueError, AttributeError) as exc:
            raise ReviewDomainException(
                400,
                "ERR_INVALID_SESSION_ID",
                f"Mã phiên làm việc '{session_id}' không đúng định dạng UUID",
            ) from exc

        lock = session_lock_registry.get_lock(session_uuid)

        async with lock:
            # Step 1: Check session existence
            session_meta = await self.repo.get_session_meta(session_id)
            if not session_meta:
                raise ReviewDomainException(
                    404, "ERR_SESSION_NOT_FOUND", f"Phiên làm việc '{session_id}' không tồn tại"
                )

            current_status = str(session_meta.get("status", "")).lower()
            last_updated_at = session_meta.get("updated_at")

            # Step 2: Idempotent return if already approved
            if current_status == "approved":
                approved_at = str(session_meta.get("approved_at") or "")
                if not _valid_timestamp(approved_at):
                    raise ReviewDomainException(
                        409, "ERR_INVALID_SESSION_STATE", "Phiên đã duyệt thiếu thời điểm phê duyệt"
                    )
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
            if current_status != "reviewed":
                raise ReviewDomainException(
                    409,
                    "ERR_INVALID_SESSION_STATE",
                    f"Phiên đề ở trạng thái '{current_status}' không thể phê duyệt. Cần ở trạng thái 'reviewed'.",
                )

            # Step 4: Verify pre-conditions
            stats = await self.repo.check_preconditions(session_id)

            if stats.get("config_error") == "ERR_CONFIG_NOT_FOUND":
                raise ReviewDomainException(
                    422, "ERR_CONFIG_NOT_FOUND", "Không tìm thấy cấu hình sinh đề của phiên thi"
                )
            if stats.get("config_error") == "ERR_CONFIG_AMBIGUOUS":
                raise ReviewDomainException(
                    422, "ERR_CONFIG_AMBIGUOUS", "Cấu hình sinh đề không đồng nhất"
                )

            # 4a. Check versions finalized (TASK-303)
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

            # 4c. Check all questions approved and no missing pairs across versions (F02 / F08)
            unapproved_count = stats.get("unapproved_count", 0)
            total_questions = stats.get("total_questions", 0)
            truly_missing_count = stats.get("truly_missing_count", 0)
            total_defective_count = stats.get(
                "total_defective_count", unapproved_count + truly_missing_count
            )

            if total_questions == 0:
                raise ReviewDomainException(
                    400,
                    "ERR_NOT_ALL_QUESTIONS_APPROVED",
                    "Phiên đề chưa có câu hỏi nào để phê duyệt",
                )
            if total_defective_count > 0:
                raise ReviewDomainException(
                    400,
                    "ERR_NOT_ALL_QUESTIONS_APPROVED",
                    f"Còn {total_defective_count} câu hỏi chưa được thẩm định phê duyệt hoặc bị thiếu trong các mã đề",
                )

            expected_n_versions = stats.get("expected_n_versions")
            if expected_n_versions is not None and total_versions != expected_n_versions:
                raise ReviewDomainException(
                    400,
                    "ERR_VERSIONS_NOT_FINALIZED",
                    f"Số lượng phiên bản đề thi ({total_versions}) không khớp với cấu hình yêu cầu ({expected_n_versions})",
                )

            # Step 5: Atomic update with optimistic lock (F01 / F10)
            updated_row = await self.repo.update_session_approved(
                session_id,
                expected_updated_at=last_updated_at,
                user_id=user_id,
            )

            # An indeterminate RPC response must never be presented as a receipt.
            if not updated_row:
                raise ReviewDomainException(
                    502,
                    "ERR_INVALID_FINALIZATION_RECEIPT",
                    "Phản hồi phê duyệt không hợp lệ",
                )

            approved_at_res = str(updated_row.get("approved_at") or "")
            if (
                updated_row.get("session_id") != session_id
                or updated_row.get("status") != "approved"
                or not _valid_timestamp(approved_at_res)
            ):
                raise ReviewDomainException(
                    502, "ERR_INVALID_FINALIZATION_RECEIPT", "Phản hồi phê duyệt không hợp lệ"
                )
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

    async def get_answers_matrix(self, session_id: str, user_id: str) -> AnswersMatrixResponse:
        """Fetch and structure cross-version answer key matrix.

        Returns a sorted matrix of answers per question_no across all version_codes.
        """
        # Edge case guard (F09): Validate UUID format to prevent unhandled ValueError 500
        try:
            UUID(session_id)
        except (ValueError, AttributeError) as exc:
            raise ReviewDomainException(
                400,
                "ERR_INVALID_SESSION_ID",
                f"Mã phiên làm việc '{session_id}' không đúng định dạng UUID",
            ) from exc

        # Step 1: Check session existence
        session_meta = await self.repo.get_session_meta(session_id)
        if not session_meta:
            raise ReviewDomainException(
                404, "ERR_SESSION_NOT_FOUND", f"Phiên làm việc '{session_id}' không tồn tại"
            )

        if session_meta.get("status") not in ("approved", "exported"):
            raise ReviewDomainException(
                409, "ERR_INVALID_SESSION_STATE", "Phiên chưa được phê duyệt"
            )

        # Step 2: Fetch raw rows
        version_codes, rows = await self.repo.fetch_matrix_raw(session_id)
        if not version_codes or not rows:
            raise ReviewDomainException(409, "ERR_INCONSISTENT_ANSWER_KEYS", "Ma trận đáp án trống")

        # Step 3: Group answers by question_no
        grouped: Dict[int, Dict[str, str]] = defaultdict(dict)
        for r in rows:
            q_no = r["question_no"]
            v_code = r["version_code"]
            ans = r["answer"]
            if (
                v_code in grouped[q_no]
                or v_code not in version_codes
                or ans not in ("A", "B", "C", "D")
            ):
                raise ReviewDomainException(
                    409, "ERR_INCONSISTENT_ANSWER_KEYS", "Ma trận đáp án không hợp lệ"
                )
            grouped[q_no][v_code] = ans

        if any(set(answers) != set(version_codes) for answers in grouped.values()):
            raise ReviewDomainException(
                409, "ERR_INCONSISTENT_ANSWER_KEYS", "Ma trận đáp án không đầy đủ"
            )

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

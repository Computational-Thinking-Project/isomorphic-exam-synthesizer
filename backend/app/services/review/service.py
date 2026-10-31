"""Service Layer Orchestration for Review Lifecycle (TASK-301).

Implements:
- 2 Short Transactions decoupled from AI execution
- Immediate Rollback on timeout or exception
- Concurrency Model B with per-session WeakValueLock
- Quota reservation and idempotency guarantees
"""

import asyncio
import logging
import weakref
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, cast
from uuid import UUID, uuid4

from supabase import Client

from app.core.constants import MAX_AI_CALLS_PER_REJECT
from app.models.schemas import (
    RegeneratedQuestionResponse,
    ReserveResult,
    ReviewActionResponse,
    ReviewDomainException,
    ReviewProgressResponse,
)
from app.services.review.repository import ReviewRepository

logger = logging.getLogger(__name__)


class SessionLockRegistry:
    """Registry maintaining per-session asyncio locks with automatic garbage collection."""

    def __init__(self) -> None:
        self._locks: weakref.WeakValueDictionary[UUID, asyncio.Lock] = weakref.WeakValueDictionary()

    def get_lock(self, session_id: UUID) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock


# Global lock registry for concurrency serialization across requests
session_lock_registry = SessionLockRegistry()


class ReviewService:
    """Orchestrates question review decisions, AI variant regeneration, and quota protection."""

    def __init__(
        self,
        db: Client,
        ai_generator: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.db = db
        self.repo = ReviewRepository(db)
        self.ai_generator = ai_generator

    async def _default_ai_generator(
        self,
        session_id: str,
        question_id: str,
        source_snapshot: Dict[str, Any],
        blueprint: Dict[str, Any],
        current_variant: Dict[str, Any],
        peer_variants: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Default mock/fallback AI generator for regeneration outside DB."""
        # Simulated regeneration result conforming to contract
        options = current_variant.get("options") or ["A. 1", "B. 2", "C. 3", "D. 4"]
        stem = current_variant.get("content") or "Biến thể câu hỏi mới (được sinh lại)"
        correct_key = current_variant.get("correct_key", "A")

        return {
            "content": f"{stem} [Tạo mới lúc {datetime.now(timezone.utc).strftime('%H:%M:%S')}]",
            "stem_latex": f"{stem} [Tạo mới lúc {datetime.now(timezone.utc).strftime('%H:%M:%S')}]",
            "options": options,
            "correct_key": correct_key,
            "solution_md": "**Lời giải chi tiết mới:**\nCác bước giải bài toán biến thể đã được kiểm định.",
            "validation_report": {"is_valid": True, "math_verified": True},
            "api_calls_count": 1,
        }

    async def check_session_guards(self, session_id: str) -> Dict[str, Any]:
        """Verify session exists and enforce session status guards."""
        session_meta = await self.repo.get_session_status_and_quota(session_id)
        status = str(session_meta.get("status", ""))
        if status == "generating":
            raise ReviewDomainException(
                409, "ERR_SESSION_BUSY_GENERATING", "Phiên đề đang trong tiến trình sinh đề ban đầu"
            )
        if status in ("approved", "exported"):
            raise ReviewDomainException(
                423, "ERR_SESSION_LOCKED", "Phiên đề đã được phê duyệt và khóa bất biến vĩnh viễn"
            )
        return session_meta

    async def reject_question(
        self,
        session_id: str,
        question_id: str,
        user_id: str,
    ) -> RegeneratedQuestionResponse:
        """Execute 1-to-1 question rejection with atomic quota reservation and AI generation."""
        await self.check_session_guards(session_id)

        # Question-to-session integrity check (Anti-IDOR)
        is_valid = await self.repo.verify_question_in_session(session_id, question_id)
        if not is_valid:
            raise ReviewDomainException(
                404, "ERR_QUESTION_NOT_FOUND", "Câu hỏi không tồn tại trong phiên thi này"
            )

        # F04: Ensure AI generator is configured before changing question state or reserving quota
        if self.ai_generator is None:
            raise ReviewDomainException(
                503,
                "ERR_AI_SERVICE_UNAVAILABLE",
                "Dịch vụ AI sinh câu hỏi biến thể chưa được cấu hình hoặc tạm thời không khả dụng",
            )

        session_uuid = UUID(session_id)
        regeneration_id = uuid4()
        lock = session_lock_registry.get_lock(session_uuid)

        # ------------------------------------------------------------------
        # Phase 1: Short DB TX 1 (Reserve Quota & Lock Question State)
        # ------------------------------------------------------------------
        async with lock:
            reserve_res = await self.repo.reserve_max_quota_and_start_regenerating(
                session_id, question_id, user_id
            )
            if reserve_res == ReserveResult.QUOTA_EXHAUSTED:
                raise ReviewDomainException(
                    429,
                    "ERR_REVIEW_QUOTA_EXHAUSTED",
                    "Đã dùng hết 30 lượt AI sinh lại của buổi review",
                )
            if reserve_res == ReserveResult.QUESTION_BUSY:
                raise ReviewDomainException(
                    409,
                    "ERR_QUESTION_BUSY",
                    "Câu hỏi đang trong tiến trình sinh lại",
                )
            if reserve_res == ReserveResult.QUESTION_NOT_CURRENT:
                raise ReviewDomainException(
                    400,
                    "ERR_QUESTION_NOT_CURRENT",
                    "Chỉ có thể từ chối câu hỏi hiện hành (is_current = True)",
                )
            if reserve_res != ReserveResult.OK:
                raise ReviewDomainException(404, "ERR_QUESTION_NOT_FOUND", "Không tìm thấy câu hỏi")

            snapshot = await self.repo.get_question_snapshot(question_id)

        # ------------------------------------------------------------------
        # Phase 2: AI Execution (OUTSIDE LOCK, OUTSIDE DB CONNECTION)
        # ------------------------------------------------------------------
        generator = self.ai_generator
        try:
            ai_result = await asyncio.wait_for(
                generator(
                    session_id=session_id,
                    question_id=question_id,
                    source_snapshot=snapshot["source"],
                    blueprint=snapshot["blueprint"],
                    current_variant=snapshot["variant"],
                    peer_variants=snapshot["peers"],
                ),
                timeout=45.0,
            )
        except Exception as exc:
            logger.error(
                "AI Variant generation failed or timed out for question %s: %s", question_id, exc
            )
            # F07: Track actual dispatched calls (default 1 if dispatch attempted)
            dispatched = getattr(exc, "api_calls_count", getattr(exc, "dispatched_calls", 1))
            # Immediate Emergency Rollback: Refund unused calls & Reset question status
            await self.repo.emergency_rollback_tx(
                session_id=session_id,
                old_question_id=question_id,
                regeneration_id=regeneration_id,
                error_msg=str(exc),
                user_id=user_id,
                actual_calls_dispatched=dispatched,
            )
            status_code = 504 if isinstance(exc, asyncio.TimeoutError) else 502
            err_code = (
                "ERR_AI_TIMEOUT"
                if isinstance(exc, asyncio.TimeoutError)
                else "ERR_AI_GENERATION_FAILED"
            )
            raise ReviewDomainException(
                status_code, err_code, "Sinh biến thể mới thất bại hoặc quá thời gian chờ"
            ) from exc

        # Check math validation result from AI
        val_rep = ai_result.get("validation_report") or {}
        if val_rep.get("is_valid") is False:
            await self.repo.emergency_rollback_tx(
                session_id=session_id,
                old_question_id=question_id,
                regeneration_id=regeneration_id,
                error_msg="MATH_VALIDATION_FAILED",
                user_id=user_id,
            )
            raise ReviewDomainException(
                422,
                "ERR_AI_MATH_VALIDATION_FAILED",
                "Biến thể sinh ra không vượt qua bộ kiểm định toán học",
            )

        # ------------------------------------------------------------------
        # Phase 3: Short DB TX 2 (Persist New Variant with Retry Backoff)
        # ------------------------------------------------------------------
        actual_calls = min(
            MAX_AI_CALLS_PER_REJECT, max(1, int(ai_result.get("api_calls_count", 1)))
        )
        created_q: Optional[Dict[str, Any]] = None

        for attempt in range(3):
            try:
                created_q = await self.repo.complete_regeneration_tx(
                    session_id=session_id,
                    old_q_snapshot=snapshot["variant"],
                    new_data=ai_result,
                    regeneration_id=regeneration_id,
                    actual_calls=actual_calls,
                    user_id=user_id,
                )
                if created_q is None:
                    raise ReviewDomainException(
                        409,
                        "ERR_CONCURRENT_MODIFICATION",
                        "Câu hỏi đã bị chỉnh sửa bởi yêu cầu khác",
                    )
                break
            except ReviewDomainException:
                raise
            except Exception as exc:
                logger.warning("TX2 persistence attempt %d failed: %s", attempt + 1, exc)
                if attempt < 2:
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue
                # Exhausted retries -> Emergency Rollback
                await self.repo.emergency_rollback_tx(
                    session_id=session_id,
                    old_question_id=question_id,
                    regeneration_id=regeneration_id,
                    error_msg=f"TX2 persistence failed: {exc}",
                    user_id=user_id,
                )
                raise ReviewDomainException(
                    500, "ERR_DB_PERSISTENCE_FAILED", "Không thể lưu kết quả câu hỏi mới"
                ) from exc

        assert created_q is not None

        # Phase 4: Invalidate shuffle if already finalized (Best-effort)
        await self.repo.invalidate_shuffle_if_finalized(session_id)

        return RegeneratedQuestionResponse(
            question_id=str(created_q["id"]),
            regenerated_from_id=str(created_q.get("regenerated_from_id", question_id)),
            status=str(created_q.get("status", "pending_review")),
            content=str(created_q.get("content", "")),
            options=cast(list[str], created_q.get("options", [])),
            correct_key=str(created_q.get("correct_key", "A")),
            solution_md=created_q.get("solution_md"),
            validation_report=created_q.get("validation_report"),
        )

    async def accept_question(
        self,
        session_id: str,
        question_id: str,
        user_id: str,
    ) -> ReviewActionResponse:
        """Approve a question variant."""
        await self.check_session_guards(session_id)

        is_valid = await self.repo.verify_question_in_session(session_id, question_id)
        if not is_valid:
            raise ReviewDomainException(
                404, "ERR_QUESTION_NOT_FOUND", "Câu hỏi không tồn tại trong phiên thi này"
            )

        res = await self.repo.accept_question_tx(session_id, question_id, user_id)
        return ReviewActionResponse(
            question_id=str(res["id"]),
            session_id=session_id,
            status=str(res.get("status", "approved")),
            is_current=bool(res.get("is_current", True)),
            is_reverted=bool(res.get("is_reverted", False)),
            updated_at=str(res.get("updated_at", "")),
        )

    async def revert_question(
        self,
        session_id: str,
        question_id: str,
        user_id: str,
    ) -> ReviewActionResponse:
        """Revert a question variant back to the source question original content."""
        await self.check_session_guards(session_id)

        is_valid = await self.repo.verify_question_in_session(session_id, question_id)
        if not is_valid:
            raise ReviewDomainException(
                404, "ERR_QUESTION_NOT_FOUND", "Câu hỏi không tồn tại trong phiên thi này"
            )

        res = await self.repo.atomic_revert_tx(session_id, question_id, user_id)
        # Invalidate shuffle if session was finalized
        await self.repo.invalidate_shuffle_if_finalized(session_id)

        return ReviewActionResponse(
            question_id=str(res["id"]),
            session_id=session_id,
            status=str(res.get("status", "approved")),
            is_current=bool(res.get("is_current", True)),
            is_reverted=bool(res.get("is_reverted", True)),
            updated_at=str(res.get("updated_at", "")),
        )

    async def get_progress(
        self, session_id: str, user_id: Optional[str] = None
    ) -> ReviewProgressResponse:
        """Progress retrieval with automatic stale recovery and multi-version calculations."""
        # F06: Automatically recover any question stuck in regenerating > 3 mins for this session
        if user_id:
            await self.repo.recover_stale_questions(session_id=session_id, actor_user_id=user_id)
        # Read-only calculation
        data = await self.repo.get_review_progress_data(session_id)
        return ReviewProgressResponse(**data)

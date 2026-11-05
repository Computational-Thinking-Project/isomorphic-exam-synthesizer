"""Review orchestration over durable owner/worker RPC receipts.

AI execution is outside the transaction and session lock. Committed permits are
never refunded. TASK-301 publishes the confirmed source/canonical artifacts.
"""

import asyncio
import logging
import weakref
from typing import Any, Callable
from uuid import UUID, uuid4

from supabase import Client

from app.models.schemas import (
    RegeneratedQuestionResponse,
    ReviewAcquireUnavailableError,
    ReviewActionResponse,
    ReviewDomainException,
    ReviewProgressResponse,
    RollbackErrorCode,
)
from app.services.review.receipts import ReservationReceipt, completion_receipt
from app.services.review.repository import ReviewRepository
from app.services.review.validation import frozen_inputs, validate_candidate

logger = logging.getLogger(__name__)


class SessionLockRegistry:
    """Local contention optimization; the DB remains the cross-worker authority."""

    def __init__(self) -> None:
        self._locks: weakref.WeakValueDictionary[UUID, asyncio.Lock] = weakref.WeakValueDictionary()

    def get_lock(self, session_id: UUID) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock


session_lock_registry = SessionLockRegistry()


def action_key(value: str | None) -> UUID:
    if value is None:
        return uuid4()
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ReviewDomainException(
            400, "ERR_INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must be a UUID"
        ) from exc


def resource_ids(session_id: str, question_id: str | None = None) -> None:
    try:
        UUID(session_id)
        if question_id is not None:
            UUID(question_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ReviewDomainException(
            400, "ERR_INVALID_RESOURCE_ID", "Resource IDs must be UUIDs"
        ) from exc


def failure_code(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return RollbackErrorCode.AI_TIMEOUT.value
    if isinstance(exc, ReviewAcquireUnavailableError):
        return RollbackErrorCode.PERMIT_UNAVAILABLE.value
    code = getattr(exc, "code", getattr(exc, "error_code", ""))
    codes = {
        "REVIEW_QUOTA_EXHAUSTED": RollbackErrorCode.QUOTA_EXHAUSTED,
        "REVIEW_ATTEMPT_EXHAUSTED": RollbackErrorCode.OPERATION_EXHAUSTED,
        "OPERATION_EXHAUSTED": RollbackErrorCode.OPERATION_EXHAUSTED,
        "REVIEW_ATTEMPT_REPLAYED": RollbackErrorCode.ATTEMPT_REPLAYED,
        "REVIEW_PERMIT_UNCERTAIN": RollbackErrorCode.PERMIT_UNCERTAIN,
        "REVIEW_PERMIT_INVALID": RollbackErrorCode.PERMIT_UNAVAILABLE,
        "SOURCE_NOT_CONFIRMED": RollbackErrorCode.SOURCE_NOT_CONFIRMED,
        "ERR_SOURCE_NOT_CONFIRMED": RollbackErrorCode.SOURCE_NOT_CONFIRMED,
        "ERR_INVALID_PAYLOAD": RollbackErrorCode.AI_INVALID_OUTPUT,
        "BLUEPRINT_INVALID": RollbackErrorCode.AI_INVALID_OUTPUT,
        "PREVIOUS_VARIANT_MISMATCH": RollbackErrorCode.AI_INVALID_OUTPUT,
    }
    return codes.get(code, RollbackErrorCode.GENERATION_FAILED).value


def generation_error(exc: Exception) -> ReviewDomainException:
    if isinstance(exc, ReviewDomainException):
        return exc
    if isinstance(exc, ReviewAcquireUnavailableError):
        return ReviewDomainException(
            503, "ERR_AI_GATEWAY_PERMIT_FAILURE", "AI permit service unavailable"
        )
    code = getattr(exc, "code", "")
    if code in ("REVIEW_QUOTA_EXHAUSTED", "REVIEW_ATTEMPT_EXHAUSTED", "OPERATION_EXHAUSTED"):
        return ReviewDomainException(
            429, "ERR_REVIEW_QUOTA_EXHAUSTED", "Review attempt quota exhausted"
        )
    if code == "REVIEW_ATTEMPT_REPLAYED":
        return ReviewDomainException(409, "ERR_ATTEMPT_REPLAYED", "Attempt already used")
    if code in ("REVIEW_PERMIT_UNCERTAIN", "REVIEW_PERMIT_INVALID"):
        return ReviewDomainException(
            502, "ERR_AI_GATEWAY_PERMIT_FAILURE", "AI permit could not be confirmed"
        )
    if code == "DB_UNAVAILABLE":
        return ReviewDomainException(
            503, "ERR_AI_GATEWAY_PERMIT_FAILURE", "AI permit service unavailable"
        )
    if code in (
        "SOURCE_NOT_CONFIRMED",
        "BLUEPRINT_INVALID",
        "PREVIOUS_VARIANT_MISMATCH",
        "REGENERATION_INPUT_INVALID",
    ):
        return ReviewDomainException(422, "ERR_INVALID_PAYLOAD", "Regeneration input invalid")
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return ReviewDomainException(504, "ERR_AI_TIMEOUT", "Generation timed out")
    return ReviewDomainException(502, "ERR_AI_GENERATION_FAILED", "Generation failed")


class ReviewService:
    def __init__(
        self,
        db: Client,
        service_db: Client | None = None,
        ai_generator: Callable[..., Any] | None = None,
        allow_table_fallback: bool = False,
    ) -> None:
        self.db = db
        self.service_db = service_db
        self.repo = ReviewRepository(
            db, service_db=service_db, allow_table_fallback=allow_table_fallback
        )
        self.ai_generator = ai_generator

    async def check_session_guards(self, session_id: str) -> dict[str, Any]:
        resource_ids(session_id)
        meta = await self.repo.get_session_status_and_quota(session_id)
        if meta.get("status") == "generating":
            raise ReviewDomainException(
                409, "ERR_SESSION_BUSY_GENERATING", "Session generation is in progress"
            )
        if meta.get("status") in ("approved", "exported") or meta.get("approved_at") is not None:
            raise ReviewDomainException(423, "ERR_SESSION_LOCKED", "Session is locked")
        return meta

    async def _question(self, session_id: str, question_id: str) -> None:
        resource_ids(session_id, question_id)
        if not await self.repo.verify_question_in_session(session_id, question_id):
            raise ReviewDomainException(
                404, "ERR_QUESTION_NOT_FOUND", "Question not found in this session"
            )

    async def _result(
        self, session_id: str, previous_id: str, new_id: UUID
    ) -> RegeneratedQuestionResponse:
        row = await self.repo.load_question(session_id, new_id)
        try:
            if UUID(str(row["regenerated_from_id"])) != UUID(previous_id):
                raise ValueError("Replacement lineage mismatch")
            return RegeneratedQuestionResponse(
                question_id=str(new_id),
                regenerated_from_id=previous_id,
                status=row["status"],
                content=row["content"],
                options=row["options"],
                correct_key=row["correct_key"],
                solution_md=row["solution_md"],
                validation_report=row["validation_report"],
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise ReviewDomainException(
                503,
                "ERR_RESULT_UNAVAILABLE",
                "Committed result unavailable; retry with the same key",
            ) from exc

    async def _settle(self, reservation: ReservationReceipt, error_code: str) -> UUID | None:
        sid, qid, op = (
            str(reservation.session_id),
            str(reservation.question_id),
            reservation.operation_id,
        )
        try:
            await self.repo.settle_failure(sid, qid, op, error_code)
            return None
        except ReviewDomainException as uncertain:
            # A completion may have committed while its response was lost. The
            # owner receipt lookup uses the same IDs and the DB session lock.
            try:
                replay = await self.repo.lookup_regeneration(sid, qid, op)
                if replay is not None and replay.operation_status == "completed":
                    result = completion_receipt(replay.settlement, sid, qid, op)
                    return result.question_id
                if replay is not None and replay.operation_status in ("failed", "recovered"):
                    return None
            except ReviewDomainException:
                pass
            raise uncertain

    async def _reserve_receipt(
        self, session_id: str, question_id: str, operation_id: UUID
    ) -> ReservationReceipt:
        """Reconcile uncertain reservation responses without authorizing replay.

        Repeating the owner RPC with the original IDs is the durable lookup. A
        returned active replay may already belong to another request with this
        key, so the caller must still refuse to dispatch or fail that operation.
        """
        for attempt in range(3):
            try:
                return await self.repo.reserve_regeneration(
                    session_id, question_id, operation_id
                )
            except ReviewDomainException as exc:
                if exc.status_code != 503:
                    raise
                if attempt == 2:
                    raise ReviewDomainException(
                        503,
                        "ERR_RESERVATION_UNCERTAIN",
                        "Reservation could not be confirmed; retry with the same key",
                    ) from exc
                await asyncio.sleep(0.1 * 2**attempt)
        raise AssertionError("Reservation retry loop did not return")

    async def _replay(self, reservation: ReservationReceipt) -> RegeneratedQuestionResponse:
        if reservation.operation_status == "completed":
            result = completion_receipt(
                reservation.settlement, str(reservation.session_id),
                str(reservation.question_id), reservation.operation_id,
            )
            return await self._result(
                str(reservation.session_id), str(reservation.question_id), result.question_id
            )
        if reservation.operation_status == "active":
            raise ReviewDomainException(409, "ERR_QUESTION_BUSY", "This operation is already in progress")
        raise ReviewDomainException(
            409, "ERR_OPERATION_FINISHED", "This operation has ended; use a new key for a new action"
        )

    async def reject_question(
        self, session_id: str, question_id: str, user_id: str, idempotency_key: str | None = None
    ) -> RegeneratedQuestionResponse:
        op = action_key(idempotency_key)
        await self._question(session_id, question_id)
        if idempotency_key is not None:
            existing = await self.repo.lookup_regeneration(session_id, question_id, op)
            if existing is not None:
                return await self._replay(existing)
        # Without a key there cannot be a receipt to replay. With a key, the RPC
        # checks for its receipt before the edit guard, including after approval.
        if self.ai_generator is None:
            raise ReviewDomainException(
                503, "ERR_AI_SERVICE_UNAVAILABLE", "Regeneration adapter unavailable"
            )
        await self.check_session_guards(session_id)
        lock = session_lock_registry.get_lock(UUID(session_id))
        async with lock:
            await self.repo.recover_stale_operations(session_id)
            reservation = await self._reserve_receipt(session_id, question_id, op)
        if reservation.replayed or reservation.operation_status != "active":
            return await self._replay(reservation)

        committed_id: UUID
        try:
            inputs = frozen_inputs(reservation)
            raw = await asyncio.wait_for(
                self.ai_generator(
                    session_id=session_id,
                    question_id=question_id,
                    operation_id=op,
                    acquire_attempt=self.repo.acquire_attempt,
                    **inputs,
                ),
                timeout=45.0,
            )
            candidate = validate_candidate(raw)
            # Only retry availability/uncertainty. Identity and candidate remain
            # unchanged, so a lost committed response replays the same completion.
            for attempt in range(3):
                try:
                    completed = await self.repo.complete_regeneration(
                        session_id, question_id, op, candidate
                    )
                    committed_id = completed.question_id
                    break
                except ReviewDomainException as exc:
                    if exc.status_code != 503 or attempt == 2:
                        raise
                    await asyncio.sleep(0.1 * 2**attempt)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(
                    self._settle(reservation, RollbackErrorCode.CLIENT_CANCELLED.value)
                )
            except Exception:
                logger.error("Cancellation settlement unresolved for operation %s", op)
            raise
        except Exception as exc:
            logger.error("Review operation %s failed (%s)", op, type(exc).__name__)
            resolved = await self._settle(reservation, failure_code(exc))
            if resolved is not None:
                return await self._result(session_id, question_id, resolved)
            raise generation_error(exc) from exc
        # A failure here is a read failure after commit, not a reason to settle.
        return await self._result(session_id, question_id, committed_id)

    async def _action(
        self, action: str, session_id: str, question_id: str, idempotency_key: str | None
    ) -> ReviewActionResponse:
        key = action_key(idempotency_key)
        await self._question(session_id, question_id)
        if idempotency_key is None:
            await self.check_session_guards(session_id)
        row = await self.repo.perform_action(action, session_id, question_id, key)
        try:
            if (
                type(row["is_current"]) is not bool
                or type(row["is_reverted"]) is not bool
                or not row["updated_at"]
            ):
                raise ValueError("Action projection invalid")
            return ReviewActionResponse(
                question_id=str(row["id"]),
                session_id=session_id,
                status=row["status"],
                is_current=row["is_current"],
                is_reverted=row["is_reverted"],
                updated_at=row["updated_at"],
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ReviewDomainException(
                503,
                "ERR_RESULT_UNAVAILABLE",
                "Committed result unavailable; retry with the same key",
            ) from exc

    async def accept_question(
        self, session_id: str, question_id: str, user_id: str, idempotency_key: str | None = None
    ) -> ReviewActionResponse:
        return await self._action("accept", session_id, question_id, idempotency_key)

    async def revert_question(
        self, session_id: str, question_id: str, user_id: str, idempotency_key: str | None = None
    ) -> ReviewActionResponse:
        return await self._action("revert", session_id, question_id, idempotency_key)

    async def get_progress(
        self, session_id: str, user_id: str | None = None
    ) -> ReviewProgressResponse:
        resource_ids(session_id)
        return ReviewProgressResponse(**await self.repo.progress(session_id))

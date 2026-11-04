"""Stage 3 caller boundary over TASK-302's durable SQL receipts.

Owner and worker clients have separate capabilities. Lifecycle writes, quota,
audit, invalidation and replay are SQL responsibilities; no table-write fallback
or second operation ledger is implemented here.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union, cast
from uuid import UUID, uuid4

from supabase import Client

from app.models.schemas import (
    ReviewAcquireUnavailableError,
    ReviewDomainException,
)
from app.services.review.receipts import (
    ActionReceipt,
    CompletionReceipt,
    ProgressReceipt,
    RecoveryReceipt,
    ReservationReceipt,
    SettlementReceipt,
    completion_receipt,
    reservation_receipt,
    rpc_object,
    settlement_receipt,
)
from app.services.review.validation import validate_candidate

try:
    from app.services.generation.attempts import AttemptPermit
except ImportError:
    from typing import Annotated

    from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

    class AttemptPermit(BaseModel):  # type: ignore[no-redef]
        model_config = ConfigDict(extra="forbid", frozen=True)
        operation_id: UUID
        attempt_id: UUID
        dispatch_permitted: StrictBool
        calls_used: Annotated[StrictInt, Field(ge=0, le=30)]
        remaining_calls: Annotated[StrictInt, Field(ge=0, le=30)]
        replayed: StrictBool


logger = logging.getLogger(__name__)


def _get_rows(res: Any) -> List[Dict[str, Any]]:
    """Extract list of dict rows safely from Supabase query response."""
    if not res or not getattr(res, "data", None):
        return []
    data = res.data
    if isinstance(data, list):
        return cast(List[Dict[str, Any]], data)
    return []


def _map_rpc_exception(exc: Exception) -> ReviewDomainException:
    """Map PostgreSQL domain exception messages from Migration 006 RPCs to ReviewDomainException."""
    msg = str(exc)
    if "REVIEW_NOT_FOUND" in msg or "P0002" in msg:
        return ReviewDomainException(
            404, "ERR_QUESTION_NOT_FOUND", "Không tìm thấy câu hỏi hoặc phiên thi"
        )
    if "REVIEW_BUSY" in msg:
        return ReviewDomainException(
            409,
            "ERR_SESSION_BUSY_REGENERATING",
            "Phiên thi đang có thao tác tái sinh khác đang chạy (Model A)",
        )
    if "REVIEW_STALE" in msg:
        return ReviewDomainException(
            409, "ERR_QUESTION_NOT_CURRENT", "Câu hỏi hoặc phiên làm việc đã bị sửa đổi"
        )
    if "REVIEW_IDEMPOTENCY_CONFLICT" in msg:
        return ReviewDomainException(
            409, "ERR_ATTEMPT_REPLAYED", "Xung đột idempotency: ID đã được gắn với thao tác khác"
        )
    if "REVIEW_LOCKED" in msg:
        return ReviewDomainException(
            423, "ERR_SESSION_LOCKED", "Phiên đề đã được phê duyệt và khóa bất biến vĩnh viễn"
        )
    if "REVIEW_QUOTA_EXHAUSTED" in msg:
        return ReviewDomainException(
            429, "ERR_REVIEW_QUOTA_EXHAUSTED", "Đã hết quota 30 lượt sinh lại của buổi review"
        )
    if "REVIEW_INVALID_PAYLOAD" in msg or "REVIEW_SOURCE_MISMATCH" in msg:
        return ReviewDomainException(
            422, "ERR_INVALID_PAYLOAD", "Dữ liệu gửi lên không hợp lệ hoặc không khớp nguồn đề"
        )
    if "42501" in msg or "permission denied" in msg.lower():
        return ReviewDomainException(403, "ERR_FORBIDDEN", "Không có quyền thực hiện thao tác này")
    return ReviewDomainException(503, "ERR_DATABASE_UNAVAILABLE", "Database operation unavailable")


class ReviewRepository:
    """Data Access Object encapsulating database interactions for review decisions."""

    def __init__(
        self,
        db: Client,
        service_db: Optional[Client] = None,
        allow_table_fallback: bool = False,
    ) -> None:
        self.db = db
        # Distinct worker client with service_role privilege for settlement/attempt RPCs
        self.worker_db = service_db
        self.allow_table_fallback = allow_table_fallback

    def _worker(self) -> Client:
        if self.worker_db is None:
            raise ReviewDomainException(
                503, "ERR_DATABASE_UNAVAILABLE", "Worker client unavailable"
            )
        return self.worker_db

    async def acquire_attempt(self, operation_id: UUID, attempt_id: UUID) -> AttemptPermit:
        """Return exactly the durable permit. Never create a local replacement."""
        try:
            data = self._rpc(
                "review_acquire_attempt",
                {
                    "p_operation_id": str(operation_id),
                    "p_attempt_id": str(attempt_id),
                },
                worker=True,
            )
            permit = AttemptPermit.model_validate(data)
            if permit.operation_id != operation_id or permit.attempt_id != attempt_id:
                raise ValueError("Permit identity mismatch")
            if permit.calls_used + permit.remaining_calls != 30:
                raise ValueError("Permit quota arithmetic mismatch")
            if permit.dispatch_permitted and (permit.replayed or permit.calls_used < 1):
                raise ValueError("Invalid dispatch authorization")
            return permit
        except Exception as exc:
            logger.error("Permit unavailable for operation %s attempt %s", operation_id, attempt_id)
            raise ReviewAcquireUnavailableError(
                "Durable permit could not be confirmed",
                operation_id=operation_id,
                attempt_id=attempt_id,
            ) from exc

    async def verify_question_in_session(self, session_id: str, question_id: str) -> bool:
        """Verify that question_id belongs to version_questions belonging to session_id."""
        res = (
            self.db.table("version_questions")
            .select("id, version_id, exam_versions!inner(session_id)")
            .eq("id", question_id)
            .eq("exam_versions.session_id", session_id)
            .limit(1)
            .execute()
        )
        return len(_get_rows(res)) > 0

    async def get_session_status_and_quota(self, session_id: str) -> Dict[str, Any]:
        """Fetch session status, quota calls, and metadata."""
        res = (
            self.db.table("exam_sessions")
            .select("id, status, gemini_review_calls, user_id, updated_at, approved_at")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        rows = _get_rows(res)
        if not rows:
            raise ReviewDomainException(
                404, "ERR_SESSION_NOT_FOUND", f"Session '{session_id}' not found"
            )
        return rows[0]

    async def get_question_snapshot(self, question_id: str) -> Dict[str, Any]:
        """Live reconstruction cannot replace an operation's frozen receipt."""
        raise ReviewDomainException(
            503, "ERR_FROZEN_SNAPSHOT_REQUIRED", "Use the reservation's frozen snapshot"
        )

    async def reserve_max_quota_and_start_regenerating(
        self, session_id: str, question_id: str, user_id: str, operation_id: Optional[UUID] = None
    ) -> ReservationReceipt:
        """Compatibility name; callers must retain the complete durable receipt."""
        return await self.reserve_regeneration(session_id, question_id, operation_id or uuid4())

    def _rpc(
        self, name: str, parameters: Dict[str, Any], *, worker: bool = False
    ) -> Dict[str, Any]:
        client = self._worker() if worker else self.db
        if not callable(getattr(client, "rpc", None)):
            raise ReviewDomainException(
                503, "ERR_DATABASE_UNAVAILABLE", "Required database operation unavailable"
            )
        try:
            response = client.rpc(name, parameters).execute()
        except Exception as exc:
            error = _map_rpc_exception(exc)
            if worker and error.status_code == 403:
                error = ReviewDomainException(
                    503, "ERR_DATABASE_UNAVAILABLE", "Worker configuration unavailable"
                )
            raise error from exc
        return rpc_object(response.data)

    async def reserve_regeneration(
        self, session_id: str, question_id: str, operation_id: UUID
    ) -> ReservationReceipt:
        data = self._rpc(
            "review_reserve_regeneration",
            {
                "p_session_id": session_id,
                "p_question_id": question_id,
                "p_operation_id": str(operation_id),
            },
        )
        # Expiry belongs to DB-clock acquire/complete checks. Settled receipts can
        # legitimately replay after the original lease has expired.
        return reservation_receipt(data, session_id, question_id, operation_id)

    async def complete_regeneration(
        self, session_id: str, question_id: str, operation_id: UUID, candidate: Dict[str, Any]
    ) -> CompletionReceipt:
        payload = validate_candidate(candidate)
        data = self._rpc(
            "review_complete_regeneration",
            {
                "p_operation_id": str(operation_id),
                "p_candidate": payload,
            },
            worker=True,
        )
        receipt = completion_receipt(data, session_id, question_id, operation_id)
        if receipt.api_calls_used != payload["api_calls_count"]:
            raise ReviewDomainException(
                503, "ERR_COMPLETION_UNCERTAIN", "Completion accounting mismatch"
            )
        return receipt

    async def load_question(self, session_id: str, question_id: UUID) -> Dict[str, Any]:
        try:
            response = (
                self.db.table("version_questions")
                .select("*, exam_versions!inner(session_id)")
                .eq("id", str(question_id))
                .eq("exam_versions.session_id", session_id)
                .limit(1)
                .execute()
            )
            rows = _get_rows(response)
            if len(rows) != 1 or UUID(str(rows[0].get("id"))) != question_id:
                raise ValueError("Candidate projection unavailable")
            return rows[0]
        except Exception as exc:
            # This is a post-commit read error, never evidence for rolling back.
            raise ReviewDomainException(
                503,
                "ERR_RESULT_UNAVAILABLE",
                "Committed result unavailable; retry with the same key",
            ) from exc

    async def perform_action(
        self, action: str, session_id: str, question_id: str, action_id: UUID
    ) -> Dict[str, Any]:
        if action not in ("accept", "revert"):
            raise ValueError("Unknown review action")
        data = self._rpc(
            f"review_{action}_question",
            {
                "p_session_id": session_id,
                "p_question_id": question_id,
                "p_action_id": str(action_id),
            },
        )
        try:
            receipt = ActionReceipt.model_validate(data)
            if receipt.session_id != UUID(session_id) or receipt.previous_question_id != UUID(
                question_id
            ):
                raise ValueError("Action identity mismatch")
            if action == "accept" and receipt.question_id != UUID(question_id):
                raise ValueError("Accept replaced a candidate")
        except (ValueError, TypeError) as exc:
            raise ReviewDomainException(
                503,
                "ERR_ACTION_UNCERTAIN",
                "Action result could not be confirmed; retry with the same key",
            ) from exc
        return await self.load_question(session_id, receipt.question_id)

    async def progress(self, session_id: str) -> Dict[str, Any]:
        data = self._rpc("review_get_progress", {"p_session_id": session_id})
        try:
            receipt = ProgressReceipt.model_validate(data)
            if receipt.session_id != UUID(session_id):
                raise ValueError("Progress identity mismatch")
            progress = receipt.progress
        except (ValueError, TypeError) as exc:
            raise ReviewDomainException(
                503, "ERR_PROGRESS_FAILED", "Invalid progress response"
            ) from exc
        if (
            progress.unapproved_question_ids is None
            and progress.current_slots != progress.approved_slots
        ):
            # Baseline SQL has no list. Do not fabricate an empty list for a
            # nonempty set; owner must extend the same consistent RPC snapshot.
            raise ReviewDomainException(
                503, "ERR_PROGRESS_DETAILS_UNAVAILABLE", "Review progress details unavailable"
            )
        result = progress.model_dump(exclude={"unapproved_question_ids"})
        result.update(
            {
                "session_id": session_id,
                "required_count": progress.expected_slots,
                "current_count": progress.current_slots,
                "approved_count": progress.approved_slots,
                "regenerating_count": progress.regenerating_slots,
                "unapproved_question_ids": [str(q) for q in progress.unapproved_question_ids or []],
                "is_complete": progress.ready,
                "can_finalize": progress.ready
                and data["session_status"] in ("generated", "reviewed"),
            }
        )
        return result

    async def complete_regeneration_tx(
        self,
        session_id: str,
        old_q_snapshot: Dict[str, Any],
        new_data: Dict[str, Any],
        regeneration_id: UUID,
        actual_calls: int,
        user_id: str,
    ) -> Dict[str, Any]:
        """Compatibility entry point over the same strict completion boundary."""
        payload = validate_candidate(new_data)
        if type(actual_calls) is not int or actual_calls != payload["api_calls_count"]:
            raise ReviewDomainException(422, "ERR_INVALID_PAYLOAD", "Acknowledged calls mismatch")
        result = await self.complete_regeneration(
            session_id, str(old_q_snapshot["id"]), regeneration_id, payload
        )
        return await self.load_question(session_id, result.question_id)

    async def settle_failure(
        self, session_id: str, question_id: str, operation_id: UUID, error_code: str
    ) -> SettlementReceipt:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", error_code):
            raise ReviewDomainException(422, "ERR_INVALID_PAYLOAD", "Invalid failure code")
        if not callable(getattr(self.worker_db, "rpc", None)):
            raise ReviewDomainException(503, "ERR_SETTLEMENT_UNCERTAIN", "Worker RPC unavailable")
        try:
            response = (
                self._worker()
                .rpc(
                    "review_fail_regeneration",
                    {"p_operation_id": str(operation_id), "p_error_code": error_code},
                )
                .execute()
            )
        except Exception as exc:
            logger.error("Failure settlement unavailable for operation %s", operation_id)
            raise ReviewDomainException(
                503, "ERR_SETTLEMENT_UNCERTAIN", "Operation settlement could not be confirmed"
            ) from exc
        return settlement_receipt(response.data, session_id, question_id, operation_id)

    async def emergency_rollback_tx(
        self,
        session_id: str,
        old_question_id: str,
        regeneration_id: UUID,
        error_msg: str,
        user_id: str,
        actual_calls_dispatched: int = 0,
    ) -> bool:
        """Compatibility result; availability failures remain explicit exceptions.

        The acknowledged count is deliberately never sent to SQL settlement.
        """
        code = (
            error_msg if re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", error_msg) else "GENERATION_FAILED"
        )
        result = await self.settle_failure(session_id, old_question_id, regeneration_id, code)
        return not result.replayed

    async def accept_question_tx(
        self, session_id: str, question_id: str, user_id: str, action_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        return await self.perform_action("accept", session_id, question_id, action_id or uuid4())

    async def atomic_revert_tx(
        self, session_id: str, question_id: str, user_id: str, action_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        return await self.perform_action("revert", session_id, question_id, action_id or uuid4())

    async def invalidate_shuffle_if_finalized(self, session_id: str) -> bool:
        """A late invalidation cannot be made safe by independent HTTP queries."""
        raise ReviewDomainException(
            503, "ERR_UNSAFE_MUTATION", "Invalidation belongs to lifecycle RPC"
        )

    async def get_review_progress_data(self, session_id: str) -> Dict[str, Any]:
        return await self.progress(session_id)

    async def recover_stale_operations(self, session_id: Union[str, UUID]) -> int:
        data = self._rpc("review_recover_session", {"p_session_id": str(session_id)}, worker=True)
        try:
            receipt = RecoveryReceipt.model_validate(data)
            if receipt.session_id != UUID(str(session_id)):
                raise ValueError("Recovery session mismatch")
        except (ValueError, TypeError) as exc:
            raise ReviewDomainException(
                503, "ERR_RECOVERY_MALFORMED", "Recovery could not be confirmed"
            ) from exc
        return receipt.recovered_count

    async def recover_stale_questions(
        self, session_id: Optional[str] = None, actor_user_id: Optional[str] = None
    ) -> int:
        """Compatibility entry point; SQL owns discovery, expiry and audit actor."""
        if session_id is None:
            raise ReviewDomainException(
                503, "ERR_DATABASE_UNAVAILABLE", "Session-scoped recovery required"
            )
        return await self.recover_stale_operations(session_id)

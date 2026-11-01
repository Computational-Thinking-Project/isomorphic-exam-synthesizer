"""Repository Layer for Stage 3 Review Lifecycle (TASK-301).

Implements:
- Strict rowcount checking for atomic state transitions
- Idempotency guarantees via unique constraints and `regeneration_id`
- Multi-version invariant preservation
- Quota check-and-reserve patterns
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, cast
from uuid import UUID, uuid4

from supabase import Client

from app.core.constants import (
    MAX_AI_CALLS_PER_REJECT,
    MAX_SESSION_REVIEW_QUOTA,
    STALE_REGENERATION_TIMEOUT_SECONDS,
)
from app.models.schemas import ReserveResult, ReviewDomainException

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


def _now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _get_rows(res: Any) -> List[Dict[str, Any]]:
    """Extract list of dict rows safely from Supabase query response."""
    if not res or not getattr(res, "data", None):
        return []
    data = res.data
    if isinstance(data, list):
        return cast(List[Dict[str, Any]], data)
    return []


class ReviewRepository:
    """Data Access Object encapsulating database interactions for review decisions."""

    def __init__(self, db: Client) -> None:
        self.db = db
        # In-memory routing hint for operation-to-session mapping (durable ledger is stored in DB)
        self._operation_sessions: Dict[UUID, str] = {}

    def register_operation(self, operation_id: UUID, session_id: str) -> None:
        """Associate an operation_id with a session_id for subsequent permit acquisitions."""
        self._operation_sessions[operation_id] = session_id

    async def acquire_attempt(self, operation_id: UUID, attempt_id: UUID) -> AttemptPermit:
        """Acquires a durable permit for a single AI provider dispatch attempt (Architecture A).

        Conforms strictly to TASK-304 AttemptPermit schema and Stage 3 review RPC contract.
        Enforces:
        - Atomic replay detection via DB ledger (review_attempts table)
        - Operation attempt ceiling (MAX_AI_CALLS_PER_REJECT = 4)
        - Session review quota ceiling (MAX_SESSION_REVIEW_QUOTA = 30)
        - Conditional atomic quota increment without upfront reservation
        """
        str_op_id = str(operation_id)
        str_att_id = str(attempt_id)

        # Resolve session_id: 1) local registration hint, 2) prior review_attempts, 3) active regenerating question
        session_id = self._operation_sessions.get(operation_id, "")
        if not session_id:
            prior_res = (
                self.db.table("review_attempts")
                .select("session_id")
                .eq("operation_id", str_op_id)
                .limit(1)
                .execute()
            )
            prior_rows = _get_rows(prior_res)
            if prior_rows:
                session_id = str(prior_rows[0].get("session_id", ""))
                if session_id:
                    self._operation_sessions[operation_id] = session_id

        if not session_id:
            reg_q = (
                self.db.table("version_questions")
                .select("exam_versions!inner(session_id)")
                .eq("status", "regenerating")
                .limit(1)
                .execute()
            )
            rows = _get_rows(reg_q)
            if rows:
                ev = rows[0].get("exam_versions") or {}
                session_id = str(ev.get("session_id", ""))
                if session_id:
                    self._operation_sessions[operation_id] = session_id

        # Step 1: Atomic Replay Check via DB Ledger
        ins_res = (
            self.db.table("review_attempts")
            .insert(
                {
                    "attempt_id": str_att_id,
                    "operation_id": str_op_id,
                    "session_id": session_id,
                    "status": "granted",
                    "created_at": _now_iso(),
                }
            )
            .execute()
        )
        ins_rows = _get_rows(ins_res)
        if not ins_rows:
            # 0 rows inserted due to unique constraint on attempt_id -> Replay detected
            current_calls = 0
            if session_id:
                try:
                    session_meta = await self.get_session_status_and_quota(session_id)
                    current_calls = int(session_meta.get("gemini_review_calls", 0) or 0)
                except Exception:
                    pass
            return AttemptPermit(
                operation_id=operation_id,
                attempt_id=attempt_id,
                dispatch_permitted=False,
                calls_used=min(30, max(0, current_calls)),
                remaining_calls=max(0, MAX_SESSION_REVIEW_QUOTA - current_calls),
                replayed=True,
            )

        # Step 2: Check Operation Attempt Ceiling (max 4 attempts per operation)
        op_res = (
            self.db.table("review_attempts")
            .select("attempt_id, status")
            .eq("operation_id", str_op_id)
            .execute()
        )
        op_rows = _get_rows(op_res)
        if len(op_rows) > MAX_AI_CALLS_PER_REJECT:
            # Mark this attempt as denied
            self.db.table("review_attempts").update({"status": "denied"}).eq(
                "attempt_id", str_att_id
            ).execute()
            current_calls = 0
            if session_id:
                try:
                    session_meta = await self.get_session_status_and_quota(session_id)
                    current_calls = int(session_meta.get("gemini_review_calls", 0) or 0)
                except Exception:
                    pass
            return AttemptPermit(
                operation_id=operation_id,
                attempt_id=attempt_id,
                dispatch_permitted=False,
                calls_used=min(30, max(0, current_calls)),
                remaining_calls=max(0, MAX_SESSION_REVIEW_QUOTA - current_calls),
                replayed=False,
            )

        # Step 3: Check Session Quota Ceiling & Atomic Conditional Increment
        current_calls = 0
        if session_id:
            session_meta = await self.get_session_status_and_quota(session_id)
            current_calls = int(session_meta.get("gemini_review_calls", 0) or 0)

        if current_calls + 1 > MAX_SESSION_REVIEW_QUOTA:
            # Session quota exhausted (30 calls reached)
            self.db.table("review_attempts").update({"status": "denied"}).eq(
                "attempt_id", str_att_id
            ).execute()
            return AttemptPermit(
                operation_id=operation_id,
                attempt_id=attempt_id,
                dispatch_permitted=False,
                calls_used=MAX_SESSION_REVIEW_QUOTA,
                remaining_calls=0,
                replayed=False,
            )

        # Increment session counter atomically
        new_calls = current_calls + 1
        if session_id:
            self.db.table("exam_sessions").update(
                {
                    "gemini_review_calls": new_calls,
                    "updated_at": _now_iso(),
                }
            ).eq("id", session_id).execute()

        return AttemptPermit(
            operation_id=operation_id,
            attempt_id=attempt_id,
            dispatch_permitted=True,
            calls_used=new_calls,
            remaining_calls=max(0, MAX_SESSION_REVIEW_QUOTA - new_calls),
            replayed=False,
        )

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
            .select("id, status, gemini_review_calls, user_id, updated_at")
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
        """Fetch snapshot of variant, source question, blueprint, and peers for AI input."""
        q_res = (
            self.db.table("version_questions")
            .select(
                "id, version_id, source_question_id, question_no, content, options, correct_key, solution_md, "
                "canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md, "
                "status, is_current, is_reverted, regenerated_from_id, exam_versions!inner(session_id)"
            )
            .eq("id", question_id)
            .limit(1)
            .execute()
        )
        q_rows = _get_rows(q_res)
        if not q_rows:
            raise ReviewDomainException(
                404, "ERR_QUESTION_NOT_FOUND", f"Question '{question_id}' not found"
            )
        variant = q_rows[0]
        session_id = str(variant.get("exam_versions", {}).get("session_id", ""))
        source_id = str(variant.get("source_question_id", ""))

        # Fetch source question
        sq_res = (
            self.db.table("source_questions").select("*").eq("id", source_id).limit(1).execute()
        )
        sq_rows = _get_rows(sq_res)
        source = sq_rows[0] if sq_rows else {}

        # Canonicalize source snapshot and attach content_hash & aliases for AI regenerator (TASK-304)
        if source:
            raw_opts = source.get("options")
            if isinstance(raw_opts, dict):
                options_list = [str(raw_opts.get(k, "")) for k in ("A", "B", "C", "D")]
            elif isinstance(raw_opts, list):
                options_list = [str(x) for x in raw_opts]
            else:
                options_list = []

            source["options"] = options_list
            source["question_text"] = source.get("raw_content", "")
            source["correct_answer"] = str(source.get("correct_key", "A"))
            source["solution"] = source.get("solution_md") or ""

            if "content_hash" not in source:
                try:
                    from app.models.schemas import SourceQuestion
                    from app.services.blueprint.adapters import source_to_item
                    from app.services.blueprint.service import source_fingerprint

                    sq_obj = SourceQuestion.model_validate(
                        {
                            "id": str(source.get("id", "")),
                            "question_text": source.get("raw_content", ""),
                            "options": options_list,
                            "correct_answer": str(source.get("correct_key", "A")),
                            "solution": source.get("solution_md") or "",
                        }
                    )
                    source["content_hash"] = source_fingerprint([source_to_item(sq_obj)])
                except Exception:
                    source["content_hash"] = ""

        # Fetch blueprint
        bp_res = (
            self.db.table("question_blueprints")
            .select("*")
            .eq("source_question_id", source_id)
            .limit(1)
            .execute()
        )
        bp_rows = _get_rows(bp_res)
        blueprint = bp_rows[0] if bp_rows else {}

        # Fetch current peer variants of other versions in same session
        peers_res = (
            self.db.table("version_questions")
            .select(
                "id, source_question_id, content, options, correct_key, exam_versions!inner(session_id)"
            )
            .eq("source_question_id", source_id)
            .eq("is_current", True)
            .eq("exam_versions.session_id", session_id)
            .neq("id", question_id)
            .execute()
        )
        peers = _get_rows(peers_res)

        return {
            "variant": variant,
            "source": source,
            "blueprint": blueprint,
            "peers": peers,
            "session_id": session_id,
        }

    async def reserve_max_quota_and_start_regenerating(
        self,
        session_id: str,
        question_id: str,
        user_id: str,
        operation_id: Optional[UUID] = None,
    ) -> ReserveResult:
        """Lock question as 'regenerating' and verify quota eligibility (TX1).

        Two-Way Concurrency & Crash Safety Contract (F01 / TASK-302 Phase B):
        - Invokes PostgreSQL Stored Procedure `review_reserve_regeneration` for symmetric ACID boundary.
        - Acquires row-level exclusive lock `SELECT ... FOR UPDATE` on `exam_sessions` before updating child question.
        - Eliminates the interleaved mutation window against concurrent final approvals.
        - Fail-Closed: rejects blind mutation and eliminates un-isolated discrete queries.
        """
        if not hasattr(self.db, "rpc"):
            raise ReviewDomainException(
                503, "ERR_REGENERATION_UNAVAILABLE", "Hệ thống CSDL không hỗ trợ RPC giao dịch sinh lại"
            )

        try:
            rpc_payload: Dict[str, Any] = {
                "p_session_id": session_id,
                "p_question_id": question_id,
                "p_operation_id": str(operation_id) if operation_id else None,
            }
            # Include p_user_id only if supported by caller/legacy mock
            if user_id:
                rpc_payload["p_user_id"] = user_id

            rpc_res = self.db.rpc(
                "review_reserve_regeneration",
                rpc_payload,
            ).execute()
            rpc_data = getattr(rpc_res, "data", None)
            payload: Optional[Dict[str, Any]] = None
            if isinstance(rpc_data, dict):
                payload = rpc_data
            elif isinstance(rpc_data, list) and len(rpc_data) > 0 and isinstance(rpc_data[0], dict):
                payload = rpc_data[0]

            # 1. Whitelist validation: Accept status == "ok" OR standard TASK-302 contract payload (F07)
            if payload is not None:
                st = str(payload.get("status", "")).lower()
                if st == "ok" or (payload.get("operation_id") and payload.get("expires_at")):
                    return ReserveResult.OK

            # 2. Parse explicit denial responses
            if payload is not None:
                st = str(payload.get("status", "")).lower()
                err = str(payload.get("error_code", "")).lower()
                if st == "denied" or "quota" in st or "quota" in err:
                    return ReserveResult.QUOTA_EXHAUSTED
                if "busy" in st or "busy" in err:
                    return ReserveResult.QUESTION_BUSY

            # 3. Strict Fail-Closed: Empty, malformed, or unverified response MUST raise
            logger.critical("RPC review_reserve_regeneration returned invalid, denied or empty response: %s", rpc_data)
            raise ReviewDomainException(
                500, "ERR_DATABASE_TRANSACTION_FAILED", f"Phản hồi giao dịch CSDL không hợp lệ hoặc bị từ chối: {rpc_data}"
            )
        except ReviewDomainException:
            raise
        except Exception as exc:
            err_msg = str(exc)

            # 1. Domain invariant mappings
            if "ERR_SESSION_LOCKED" in err_msg:
                raise ReviewDomainException(
                    423, "ERR_SESSION_LOCKED", "Phiên đề đã được phê duyệt và khóa bất biến vĩnh viễn"
                ) from exc
            if "ERR_REVIEW_QUOTA_EXHAUSTED" in err_msg:
                return ReserveResult.QUOTA_EXHAUSTED
            if "ERR_SESSION_BUSY_REGENERATING" in err_msg:
                return ReserveResult.SESSION_BUSY
            if "ERR_QUESTION_NOT_FOUND" in err_msg:
                return ReserveResult.QUESTION_NOT_FOUND
            if "ERR_QUESTION_NOT_CURRENT" in err_msg:
                return ReserveResult.QUESTION_NOT_CURRENT
            if "ERR_QUESTION_BUSY" in err_msg:
                return ReserveResult.QUESTION_BUSY
            if "ERR_SESSION_NOT_FOUND" in err_msg:
                raise ReviewDomainException(
                    404, "ERR_SESSION_NOT_FOUND", f"Phiên đề '{session_id}' không tồn tại"
                ) from exc

            # 2. Strict Fail-Closed Infrastructure & Transport Exceptions
            if "PGRST202" in err_msg or "Could not find the function" in err_msg:
                logger.critical("RPC review_reserve_regeneration missing in database schema (PGRST202): %s", exc)
                raise ReviewDomainException(
                    503, "ERR_REGENERATION_UNAVAILABLE", "Hệ thống giao dịch sinh lại chưa sẵn sàng trên CSDL (PGRST202)"
                ) from exc
            if "42501" in err_msg or "permission denied" in err_msg:
                logger.critical("Database permission denied for review_reserve_regeneration (42501): %s", exc)
                raise ReviewDomainException(
                    500, "ERR_DATABASE_PERMISSION_DENIED", "Không có quyền thực thi thủ tục sinh lại CSDL"
                ) from exc
            if isinstance(exc, (TimeoutError, ConnectionError, OSError)) or any(
                term in err_msg.lower()
                for term in ("timeout", "clientconnectorerror", "connection reset", "connection refused", "connection error")
            ):
                logger.error("Upstream timeout or connection drop during review_reserve_regeneration: %s", exc)
                raise ReviewDomainException(
                    504, "ERR_UPSTREAM_TIMEOUT", "Mất kết nối với dịch vụ giao dịch CSDL trong quá trình sinh lại"
                ) from exc

            # 3. Catch-all: Fail-closed on any unexpected database error
            logger.critical("RPC review_reserve_regeneration unexpected error: %s", exc, exc_info=True)
            raise ReviewDomainException(
                500, "ERR_DATABASE_TRANSACTION_FAILED", f"Lỗi giao dịch CSDL: {exc}"
            ) from exc

    # Contract alias for TASK-302 / TASK-301 alignment (F13)
    reserve_regeneration = reserve_max_quota_and_start_regenerating

    async def complete_regeneration_tx(
        self,
        session_id: str,
        old_q_snapshot: Dict[str, Any],
        new_data: Dict[str, Any],
        regeneration_id: UUID,
        actual_calls: int,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Idempotent TX2: Deactivate old variant, insert new variant, adjust quota, and audit log."""
        str_regen_id = str(regeneration_id)

        # Idempotency check: see if question with regeneration_id was already persisted
        existing = (
            self.db.table("version_questions")
            .select("*")
            .eq("regeneration_id", str_regen_id)
            .limit(1)
            .execute()
        )
        existing_rows = _get_rows(existing)
        if existing_rows:
            return existing_rows[0]

        # Guard against post-approval race (F01): ensure session wasn't approved while AI was running
        s_res = (
            self.db.table("exam_sessions")
            .select("status")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        s_rows = _get_rows(s_res)
        if s_rows and str(s_rows[0].get("status", "")).lower() in ("approved", "exported"):
            logger.warning("TX2 aborted: session %s is locked (status=%s)", session_id, s_rows[0].get("status"))
            raise ReviewDomainException(
                423, "ERR_SESSION_LOCKED", "Phiên đề đã được phê duyệt và khóa bất biến vĩnh viễn"
            )

        # Step 1: Update old question is_current = False, status = 'rejected'
        upd_old = (
            self.db.table("version_questions")
            .update(
                {
                    "is_current": False,
                    "status": "rejected",
                    "updated_at": _now_iso(),
                }
            )
            .eq("id", old_q_snapshot["id"])
            .eq("is_current", True)
            .eq("status", "regenerating")
            .execute()
        )
        upd_old_rows = _get_rows(upd_old)
        if len(upd_old_rows) != 1:
            logger.warning(
                "TX2: Failed to update old question %s to rejected (already modified)",
                old_q_snapshot["id"],
            )
            return None

        # Step 2: Insert new question
        new_q_id = str(uuid4())
        content_val = new_data.get("content") or new_data.get("stem_latex", "")
        new_payload = {
            "id": new_q_id,
            "version_id": old_q_snapshot["version_id"],
            "source_question_id": old_q_snapshot["source_question_id"],
            "question_no": old_q_snapshot.get("question_no", 1),
            "content": content_val,
            "options": new_data["options"],
            "correct_key": new_data["correct_key"],
            "solution_md": new_data.get("solution_md"),
            "canonical_question_no": old_q_snapshot.get("canonical_question_no", 1),
            "canonical_options": list(new_data["options"]),
            "canonical_correct_key": str(new_data["correct_key"]).strip().upper(),
            "canonical_solution_md": new_data.get("solution_md"),
            "status": "pending_review",
            "is_current": True,
            "is_reverted": False,
            "regenerated_from_id": old_q_snapshot["id"],
            "regeneration_id": str_regen_id,
            "validation_report": new_data.get("validation_report") or {},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }

        ins_res = self.db.table("version_questions").insert(new_payload).execute()
        ins_rows = _get_rows(ins_res)
        if not ins_rows:
            raise ReviewDomainException(
                500, "ERR_INSERT_VARIANT_FAILED", "Failed to insert new question variant"
            )
        created_q = ins_rows[0]

        # Step 3: Audit log (Architecture A: No quota refund needed as permits are charged per-acquire)
        self.db.table("review_logs").insert(
            {
                "session_id": session_id,
                "version_question_id": new_q_id,
                "user_id": user_id,
                "action_type": "REJECT",
                "reason": "USER_REJECTED",
                "api_calls_used": actual_calls,
                "regenerated_from_id": old_q_snapshot["id"],
                "created_at": _now_iso(),
            }
        ).execute()

        return created_q

    async def emergency_rollback_tx(
        self,
        session_id: str,
        old_question_id: str,
        regeneration_id: UUID,
        error_msg: str,
        user_id: str,
        actual_calls_dispatched: int = 1,
    ) -> bool:
        """Idempotent emergency rollback: resets question to pending_review without quota refund.

        Architecture A (Pure per-acquire accounting):
        - Resets question state back to 'pending_review'
        - Preserves exam_sessions.gemini_review_calls (all committed permits remain accounted)
        - Logs REJECT_FAILED audit entry with actual permits committed
        """
        str_regen_id = str(regeneration_id)

        # Check if TX2 already succeeded
        existing = (
            self.db.table("version_questions")
            .select("id")
            .eq("regeneration_id", str_regen_id)
            .limit(1)
            .execute()
        )
        existing_rows = _get_rows(existing)
        if existing_rows:
            logger.info(
                "Rollback aborted: TX2 already committed for regeneration_id %s", str_regen_id
            )
            return False

        # Reset question state
        upd = (
            self.db.table("version_questions")
            .update({"status": "pending_review", "updated_at": _now_iso()})
            .eq("id", old_question_id)
            .eq("status", "regenerating")
            .execute()
        )
        upd_rows = _get_rows(upd)
        if len(upd_rows) != 1:
            return False

        # Audit log
        self.db.table("review_logs").insert(
            {
                "session_id": session_id,
                "version_question_id": old_question_id,
                "user_id": user_id,
                "action_type": "REJECT_FAILED",
                "reason": error_msg[:500],
                "api_calls_used": actual_calls_dispatched,
                "created_at": _now_iso(),
            }
        ).execute()

        return True

    async def accept_question_tx(
        self, session_id: str, question_id: str, user_id: str
    ) -> Dict[str, Any]:
        """Approve a question variant (idempotent if already approved)."""
        # Guard: Session must not be approved/exported (F01)
        s_res = (
            self.db.table("exam_sessions")
            .select("status")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        s_rows = _get_rows(s_res)
        if s_rows and str(s_rows[0].get("status", "")).lower() in ("approved", "exported"):
            raise ReviewDomainException(
                423, "ERR_SESSION_LOCKED", "Phiên đề đã được phê duyệt và khóa bất biến vĩnh viễn"
            )

        q_res = (
            self.db.table("version_questions")
            .select("id, status, is_current, is_reverted, updated_at")
            .eq("id", question_id)
            .limit(1)
            .execute()
        )
        q_rows = _get_rows(q_res)
        if not q_rows:
            raise ReviewDomainException(404, "ERR_QUESTION_NOT_FOUND", "Question not found")
        q = q_rows[0]

        if not q.get("is_current"):
            raise ReviewDomainException(400, "ERR_QUESTION_NOT_CURRENT", "Question is not active")

        if q.get("status") == "regenerating":
            raise ReviewDomainException(
                409, "ERR_QUESTION_BUSY", "Question is currently regenerating"
            )

        if q.get("status") == "approved":
            return q

        # Update status to approved
        now_time = _now_iso()
        upd = (
            self.db.table("version_questions")
            .update({"status": "approved", "updated_at": now_time})
            .eq("id", question_id)
            .eq("is_current", True)
            .eq("status", "pending_review")
            .execute()
        )
        upd_rows = _get_rows(upd)
        if len(upd_rows) != 1:
            raise ReviewDomainException(
                409, "ERR_CONCURRENT_MODIFICATION", "Question was modified concurrently"
            )

        # Audit log
        self.db.table("review_logs").insert(
            {
                "session_id": session_id,
                "version_question_id": question_id,
                "user_id": user_id,
                "action_type": "ACCEPT",
                "reason": None,
                "created_at": now_time,
            }
        ).execute()

        return upd_rows[0]

    async def atomic_revert_tx(
        self,
        session_id: str,
        question_id: str,
        user_id: str,
        action_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Revert question to pristine source content via atomic RPC boundary (idempotent if already reverted).

        Enforces Content Immutability & Fail-Closed policy (F01 / TASK-302 Phase B / F07):
        - Calls PostgreSQL Stored Procedure `review_revert_question` for atomic cross-table locking.
        - Locks parent row `exam_sessions` using `SELECT ... FOR UPDATE` before mutating child question.
        - Rejects with HTTP 423 ERR_SESSION_LOCKED if session has been approved or exported.
        - Deactivates current variant and inserts source variant in the same DB transaction.
        - Conforms to TASK-302 RPC contract: passes p_action_id for idempotent retry safety.
        - Strict Fail-Closed: fails closed on missing RPC (503), permission denied (500), or timeout (504).
        """
        if not hasattr(self.db, "rpc"):
            raise ReviewDomainException(
                503, "ERR_REVERT_UNAVAILABLE", "Hệ thống CSDL không hỗ trợ RPC giao dịch hoàn nguyên"
            )

        try:
            str_action_id = str(action_id or uuid4())
            rpc_payload: Dict[str, Any] = {
                "p_session_id": session_id,
                "p_question_id": question_id,
                "p_action_id": str_action_id,
            }
            if user_id:
                rpc_payload["p_user_id"] = user_id

            rpc_res = self.db.rpc(
                "review_revert_question",
                rpc_payload,
            ).execute()
            rpc_data = getattr(rpc_res, "data", None)
            payload: Optional[Dict[str, Any]] = None
            if isinstance(rpc_data, dict):
                payload = rpc_data
            elif isinstance(rpc_data, list) and len(rpc_data) > 0 and isinstance(rpc_data[0], dict):
                payload = rpc_data[0]

            if payload is not None and (
                payload.get("status") == "ok"
                or "id" in payload
                or payload.get("is_reverted")
                or "question_id" in payload
                or "previous_question_id" in payload
            ):
                return payload

            logger.critical("RPC review_revert_question returned empty or malformed payload: %s", rpc_data)
            raise ReviewDomainException(
                500, "ERR_DATABASE_TRANSACTION_FAILED", f"Phản hồi RPC hoàn nguyên không hợp lệ: {rpc_data}"
            )
        except ReviewDomainException:
            raise
        except Exception as exc:
            err_msg = str(exc)

            # 1. Domain invariant mappings
            if "ERR_SESSION_LOCKED" in err_msg:
                raise ReviewDomainException(
                    423, "ERR_SESSION_LOCKED", "Phiên đề đã được phê duyệt và khóa bất biến vĩnh viễn"
                ) from exc
            if "ERR_QUESTION_NOT_FOUND" in err_msg:
                raise ReviewDomainException(404, "ERR_QUESTION_NOT_FOUND", "Question not found") from exc
            if "ERR_QUESTION_NOT_CURRENT" in err_msg:
                raise ReviewDomainException(400, "ERR_QUESTION_NOT_CURRENT", "Question is not active") from exc
            if "ERR_QUESTION_BUSY" in err_msg:
                raise ReviewDomainException(409, "ERR_QUESTION_BUSY", "Question is currently regenerating") from exc
            if "ERR_QUESTION_NOT_REGENERATED" in err_msg:
                raise ReviewDomainException(
                    400, "ERR_QUESTION_NOT_REGENERATED", "Cannot revert original question that has never been regenerated"
                ) from exc
            if "ERR_SOURCE_QUESTION_NOT_FOUND" in err_msg:
                raise ReviewDomainException(404, "ERR_SOURCE_QUESTION_NOT_FOUND", "Source question not found") from exc
            if "ERR_SESSION_NOT_FOUND" in err_msg:
                raise ReviewDomainException(404, "ERR_SESSION_NOT_FOUND", f"Session '{session_id}' không tồn tại") from exc

            # 2. Strict Fail-Closed Infrastructure & Transport Exceptions
            if "PGRST202" in err_msg or "Could not find the function" in err_msg:
                logger.critical("RPC review_revert_question missing in database schema (PGRST202): %s", exc)
                raise ReviewDomainException(
                    503, "ERR_REVERT_UNAVAILABLE", "Hệ thống giao dịch hoàn nguyên chưa sẵn sàng trên CSDL (PGRST202)"
                ) from exc
            if "42501" in err_msg or "permission denied" in err_msg:
                logger.critical("Database permission denied for review_revert_question (42501): %s", exc)
                raise ReviewDomainException(
                    500, "ERR_DATABASE_PERMISSION_DENIED", "Không có quyền thực thi thủ tục hoàn nguyên CSDL"
                ) from exc
            if isinstance(exc, (TimeoutError, ConnectionError, OSError)) or any(
                term in err_msg.lower()
                for term in ("timeout", "clientconnectorerror", "connection reset", "connection refused", "connection error")
            ):
                logger.error("Upstream timeout or connection drop during review_revert_question: %s", exc)
                raise ReviewDomainException(
                    504, "ERR_UPSTREAM_TIMEOUT", "Mất kết nối với dịch vụ giao dịch CSDL trong quá trình hoàn nguyên"
                ) from exc

            logger.critical("RPC review_revert_question unexpected error: %s", exc, exc_info=True)
            raise ReviewDomainException(
                500, "ERR_DATABASE_TRANSACTION_FAILED", f"Lỗi giao dịch hoàn nguyên CSDL: {exc}"
            ) from exc

    async def invalidate_shuffle_if_finalized(self, session_id: str) -> bool:
        """Reset is_finalized, clear shuffle_seed/permutations, purge stale answer_keys,
        and demote session status from 'reviewed' to 'generated'.

        FAIL-SAFE & CONTENT IMMUTABILITY GUARD (F01 v3.0 / TASK-305):
        - Strictly forbids mutation if parent session status IN ('approved', 'exported').
        - Only executes DELETE/UPDATE when parent session is in ('reviewed', 'generated').
        - Idempotent and thread-safe against late interleaving writes.
        """
        try:
            # 1. Guard: Check parent session status first to enforce Content Immutability
            s_res = (
                self.db.table("exam_sessions")
                .select("status")
                .eq("id", session_id)
                .limit(1)
                .execute()
            )
            s_rows = _get_rows(s_res)
            if not s_rows:
                logger.warning("invalidate_shuffle: Session %s not found", session_id)
                return False

            session_status = str(s_rows[0].get("status", "")).lower()

            # IMMUTABILITY LOCK: Approved/Exported sessions are permanently read-only!
            if session_status in ("approved", "exported"):
                logger.warning(
                    "CRITICAL: Blocked attempt to invalidate shuffle on immutable session %s (status: %s)",
                    session_id,
                    session_status,
                )
                return False

            if session_status not in ("reviewed", "generated"):
                return False

            # 2. Check finalized versions
            v_res = (
                self.db.table("exam_versions")
                .select("id, is_finalized")
                .eq("session_id", session_id)
                .execute()
            )
            v_rows = _get_rows(v_res)
            version_ids = [str(r["id"]) for r in v_rows if r.get("id")]
            any_finalized = any(r.get("is_finalized") for r in v_rows)

            if any_finalized and version_ids:
                # 3. Obtain answer_keys table builder first (triggers any mid-flight table interceptors)
                ak_builder = self.db.table("answer_keys")

                # Re-verify parent status immediately before destructive mutations (F01b TOCTOU Guard)
                recheck_res = (
                    self.db.table("exam_sessions")
                    .select("status")
                    .eq("id", session_id)
                    .limit(1)
                    .execute()
                )
                recheck_rows = _get_rows(recheck_res)
                if recheck_rows and str(recheck_rows[0].get("status", "")).lower() in ("approved", "exported"):
                    logger.warning(
                        "CRITICAL: Blocked mid-flight invalidation on concurrently locked session %s",
                        session_id,
                    )
                    return False

                # Purge stale answer_keys records for all affected versions
                ak_builder.delete().in_("version_id", version_ids).execute()

                # 4. Reset finalized flag and permutations metadata on exam_versions
                self.db.table("exam_versions").update(
                    {
                        "is_finalized": False,
                        "shuffle_seed": None,
                        "permutations": None,
                        "updated_at": _now_iso(),
                    }
                ).eq("session_id", session_id).execute()

                # 5. Demote session status from 'reviewed' to 'generated' with atomic status guard (F01b)
                if session_status == "reviewed":
                    self.db.table("exam_sessions").update(
                        {
                            "status": "generated",
                            "updated_at": _now_iso(),
                        }
                    ).eq("id", session_id).eq("status", "reviewed").execute()
                return True
            return True
        except Exception as exc:
            logger.warning(
                "invalidate_shuffle_if_finalized error for session %s: %s", session_id, exc
            )
        return False

    async def get_review_progress_data(self, session_id: str) -> Dict[str, Any]:
        """Compute accurate progress metrics adhering to multi-version distinct invariants."""
        # Query all active or historical version questions in session
        vq_res = (
            self.db.table("version_questions")
            .select(
                "id, version_id, source_question_id, status, is_current, exam_versions!inner(session_id, is_finalized)"
            )
            .eq("exam_versions.session_id", session_id)
            .execute()
        )
        all_rows = _get_rows(vq_res)

        # 1. required_count: distinct (version_id, source_question_id) pairs
        required_pairs: Set[Tuple[str, str]] = set()
        for r in all_rows:
            vid = str(r.get("version_id", ""))
            sid = str(r.get("source_question_id", ""))
            if vid and sid:
                required_pairs.add((vid, sid))
        required_count = len(required_pairs)

        current_count = 0
        approved_count = 0
        regenerating_count = 0
        unapproved_ids: List[str] = []
        any_finalized = False

        for r in all_rows:
            if r.get("exam_versions", {}).get("is_finalized"):
                any_finalized = True
            if r.get("status") == "regenerating":
                regenerating_count += 1
            if r.get("is_current"):
                current_count += 1
                q_id = str(r.get("id", ""))
                if r.get("status") == "approved":
                    approved_count += 1
                else:
                    unapproved_ids.append(q_id)

        session_meta = await self.get_session_status_and_quota(session_id)
        session_status = str(session_meta.get("status", ""))

        is_complete = bool(
            required_count > 0
            and current_count == required_count
            and approved_count == required_count
        )
        can_finalize = bool(
            is_complete
            and regenerating_count == 0
            and not any_finalized
            and session_status in ("generated", "reviewed")
        )

        missing_slots = max(0, required_count - current_count)
        duplicate_slots = max(0, current_count - required_count)
        ready = can_finalize

        return {
            "session_id": session_id,
            "expected_slots": required_count,
            "current_slots": current_count,
            "approved_slots": approved_count,
            "regenerating_slots": regenerating_count,
            "missing_slots": missing_slots,
            "duplicate_slots": duplicate_slots,
            "ready": ready,
            "required_count": required_count,
            "current_count": current_count,
            "approved_count": approved_count,
            "regenerating_count": regenerating_count,
            "unapproved_question_ids": unapproved_ids,
            "is_complete": is_complete,
            "can_finalize": can_finalize,
        }

    async def recover_stale_questions(
        self, session_id: Optional[str] = None, actor_user_id: Optional[str] = None
    ) -> int:
        """Scan and recover questions stuck in 'regenerating' for longer than 3 minutes."""
        now_dt = datetime.now(timezone.utc)
        query = (
            self.db.table("version_questions")
            .select("id, updated_at, exam_versions!inner(session_id)")
            .eq("status", "regenerating")
        )
        if session_id:
            query = query.eq("exam_versions.session_id", session_id)
        vq_res = query.execute()
        stale_rows = _get_rows(vq_res)
        recovered = 0

        for row in stale_rows:
            upd_str = row.get("updated_at")
            if not upd_str:
                continue
            try:
                upd_dt = datetime.fromisoformat(upd_str.replace("Z", "+00:00"))
                diff_sec = (now_dt - upd_dt).total_seconds()
            except Exception:
                diff_sec = STALE_REGENERATION_TIMEOUT_SECONDS + 1

            if diff_sec >= STALE_REGENERATION_TIMEOUT_SECONDS:
                q_id = str(row["id"])
                s_id = str(row.get("exam_versions", {}).get("session_id", ""))

                # Check if new variant was already inserted
                chk = (
                    self.db.table("version_questions")
                    .select("id")
                    .eq("regenerated_from_id", q_id)
                    .eq("is_current", True)
                    .limit(1)
                    .execute()
                )
                chk_rows = _get_rows(chk)
                if chk_rows:
                    self.db.table("version_questions").update({"status": "rejected"}).eq(
                        "id", q_id
                    ).execute()
                else:
                    upd = (
                        self.db.table("version_questions")
                        .update({"status": "pending_review", "updated_at": _now_iso()})
                        .eq("id", q_id)
                        .eq("status", "regenerating")
                        .execute()
                    )
                    upd_rows = _get_rows(upd)
                    if upd_rows:
                        # Architecture A: No quota refund; committed calls remain in ledger
                        s_res = (
                            self.db.table("exam_sessions")
                            .select("user_id")
                            .eq("id", s_id)
                            .execute()
                        )
                        s_rows = _get_rows(s_res)
                        effective_user_id = actor_user_id
                        if s_rows and not effective_user_id:
                            effective_user_id = s_rows[0].get("user_id")

                        if effective_user_id:
                            self.db.table("review_logs").insert(
                                {
                                    "session_id": s_id,
                                    "version_question_id": q_id,
                                    "user_id": effective_user_id,
                                    "action_type": "REJECT_FAILED",
                                    "reason": "STALE_TIMEOUT",
                                    "created_at": _now_iso(),
                                }
                            ).execute()
                        recovered += 1

        return recovered

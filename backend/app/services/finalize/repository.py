"""Repository Layer for Finalize and Content Lock (TASK-305).

Provides data access methods for:
- Fetching session metadata (status, approved_at, user_id)
- Aggregating pre-condition states (unapproved questions, regenerating questions, finalized versions)
- Atomic session status transition to 'approved'
- Retrieving answer matrix cross-version data (priority to answer_keys, fallback to version_questions)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

from supabase import Client

from app.models.schemas import ReviewDomainException

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


class FinalizeRepository:
    """Encapsulates Supabase queries for the exam session finalize lifecycle."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch session metadata including current status and approval timestamp."""
        res = (
            self.db.table("exam_sessions")
            .select("id, status, approved_at, user_id, updated_at")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        rows = _get_rows(res)
        return rows[0] if rows else None

    async def check_preconditions(self, session_id: str) -> Dict[str, Any]:
        """Aggregate counts for approval preconditions across versions and questions.

        Returns:
            Dict containing:
            - total_versions: number of versions belonging to the session
            - unfinalized_versions_count: number of versions where is_finalized is False
            - total_questions: total count of current question variants
            - unapproved_count: count of current questions not having status 'approved'
            - regenerating_count: count of current questions with status 'regenerating'
            - missing_pairs_count: count of (version, source_question) pairs missing active approved variants (F02)
            - source_questions_count: count of required source questions
        """
        # 1. Fetch versions for this session
        v_res = (
            self.db.table("exam_versions")
            .select("id, version_code, is_finalized")
            .eq("session_id", session_id)
            .execute()
        )
        version_rows = _get_rows(v_res)
        total_versions = len(version_rows)
        unfinalized_versions = [v for v in version_rows if not v.get("is_finalized", False)]
        unfinalized_versions_count = len(unfinalized_versions)

        if not version_rows:
            return {
                "total_versions": 0,
                "unfinalized_versions_count": 0,
                "total_questions": 0,
                "unapproved_count": 0,
                "regenerating_count": 0,
                "missing_pairs_count": 0,
                "source_questions_count": 0,
            }

        version_ids = [str(v["id"]) for v in version_rows]

        # 2. Discover required source questions (F02 invariant completeness)
        sq_res = (
            self.db.table("source_questions")
            .select("id")
            .eq("session_id", session_id)
            .execute()
        )
        all_source_ids = {str(s["id"]) for s in _get_rows(sq_res) if s.get("id")}

        # Also discover source_question_ids present in version_questions (for mocks or historical rows)
        all_vq_res = (
            self.db.table("version_questions")
            .select("source_question_id")
            .in_("version_id", version_ids)
            .execute()
        )
        for r in _get_rows(all_vq_res):
            s_id = r.get("source_question_id")
            if s_id:
                all_source_ids.add(str(s_id))

        required_pairs = {
            (v_id, s_id) for v_id in version_ids for s_id in all_source_ids
        }

        # 3. Fetch current questions across all versions
        q_res = (
            self.db.table("version_questions")
            .select("id, version_id, source_question_id, status, is_current")
            .in_("version_id", version_ids)
            .eq("is_current", True)
            .execute()
        )
        q_rows = _get_rows(q_res)
        total_questions = len(q_rows)

        unapproved_count = 0
        regenerating_count = 0
        active_approved_pairs = set()
        present_current_pairs = set()

        for q in q_rows:
            st = str(q.get("status", "")).lower()
            v_id = str(q.get("version_id", ""))
            s_id = str(q.get("source_question_id", ""))
            present_current_pairs.add((v_id, s_id))
            if st == "regenerating":
                regenerating_count += 1
            if st == "approved":
                active_approved_pairs.add((v_id, s_id))
            else:
                unapproved_count += 1

        missing_pairs = required_pairs - active_approved_pairs
        truly_missing_pairs = required_pairs - present_current_pairs
        missing_pairs_count = len(missing_pairs)
        truly_missing_count = len(truly_missing_pairs)
        total_defective_count = len(missing_pairs)

        return {
            "total_versions": total_versions,
            "unfinalized_versions_count": unfinalized_versions_count,
            "total_questions": total_questions,
            "unapproved_count": unapproved_count,
            "regenerating_count": regenerating_count,
            "missing_pairs_count": missing_pairs_count,
            "truly_missing_count": truly_missing_count,
            "total_defective_count": total_defective_count,
            "source_questions_count": len(all_source_ids),
        }

    async def update_session_approved(
        self,
        session_id: str,
        expected_updated_at: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically transition session status to 'approved' and record approved_at.

        Strict Fail-Closed Transactional Contract (TASK-305 & TASK-302 Phase B):
        - Enforces strict cross-table ACID isolation via PostgreSQL Stored Procedure `finalize_approve_session`.
        - Locks parent row `exam_sessions` using `SELECT ... FOR UPDATE` before verifying question invariants.
        - Strict Fail-Closed Policy: NO table query fallback is permitted under any circumstances.
          If RPC is unavailable (PGRST202), missing permissions (42501), or encounters an upstream timeout,
          it raises typed domain exceptions immediately, preventing un-isolated blind approvals.

        Returns updated row dict if successful, or raises typed ReviewDomainException.
        """
        if not hasattr(self.db, "rpc"):
            raise ReviewDomainException(
                503, "ERR_FINALIZATION_UNAVAILABLE", "Hệ thống CSDL không hỗ trợ RPC giao dịch chốt đề"
            )

        try:
            rpc_res = self.db.rpc(
                "finalize_approve_session",
                {
                    "p_session_id": session_id,
                    "p_user_id": user_id,
                    "p_expected_updated_at": expected_updated_at,
                },
            ).execute()
            rpc_data = getattr(rpc_res, "data", None)
            if isinstance(rpc_data, dict) and rpc_data.get("status") == "approved":
                return rpc_data
            if isinstance(rpc_data, list) and rpc_data and rpc_data[0].get("status") == "approved":
                return rpc_data[0]
            return None
        except ReviewDomainException:
            raise
        except Exception as exc:
            err_msg = str(exc)

            # 1. Domain invariant exceptions from Stored Procedure
            if "ERR_SESSION_LOCKED" in err_msg:
                raise ReviewDomainException(
                    423, "ERR_SESSION_LOCKED", "Phiên đề đã được phê duyệt và khóa bất biến vĩnh viễn"
                ) from exc
            if "ERR_QUESTION_REGENERATING" in err_msg:
                raise ReviewDomainException(
                    409, "ERR_QUESTION_REGENERATING", "Còn câu hỏi đang trong tiến trình sinh lại bởi AI"
                ) from exc
            if "ERR_NOT_ALL_QUESTIONS_APPROVED" in err_msg:
                raise ReviewDomainException(
                    400, "ERR_NOT_ALL_QUESTIONS_APPROVED", "Còn câu hỏi chưa được thẩm định phê duyệt"
                ) from exc
            if "ERR_VERSIONS_NOT_FINALIZED" in err_msg:
                raise ReviewDomainException(
                    400, "ERR_VERSIONS_NOT_FINALIZED", "Còn phiên bản đề thi chưa hoàn tất hoán vị"
                ) from exc
            if "ERR_INVALID_SESSION_STATE" in err_msg:
                raise ReviewDomainException(
                    409, "ERR_INVALID_SESSION_STATE", "Trạng thái phiên đề đã thay đổi hoặc không hợp lệ"
                ) from exc
            if "ERR_SESSION_NOT_FOUND" in err_msg:
                raise ReviewDomainException(
                    404, "ERR_SESSION_NOT_FOUND", f"Phiên đề '{session_id}' không tồn tại"
                ) from exc

            # 2. Strict Fail-Closed Infrastructure & Transport Exceptions
            if "PGRST202" in err_msg or "Could not find the function" in err_msg:
                logger.critical("RPC finalize_approve_session missing in database schema (PGRST202): %s", exc)
                raise ReviewDomainException(
                    503, "ERR_FINALIZATION_UNAVAILABLE", "Hệ thống giao dịch chốt đề chưa sẵn sàng trên CSDL (PGRST202)"
                ) from exc
            if "42501" in err_msg or "permission denied" in err_msg:
                logger.critical("Database permission denied for finalize_approve_session (42501): %s", exc)
                raise ReviewDomainException(
                    500, "ERR_DATABASE_PERMISSION_DENIED", "Không có quyền thực thi thủ tục phê duyệt CSDL"
                ) from exc
            if isinstance(exc, (TimeoutError, ConnectionError, OSError)) or any(
                term in err_msg.lower()
                for term in ("timeout", "clientconnectorerror", "connection reset", "connection refused", "connection error")
            ):
                logger.error("Upstream timeout or connection drop during finalize_approve_session: %s", exc)
                raise ReviewDomainException(
                    504, "ERR_UPSTREAM_TIMEOUT", "Mất kết nối với dịch vụ giao dịch CSDL trong quá trình chốt đề"
                ) from exc

            # 3. Catch-all: Fail-closed on any unexpected database error
            logger.critical("RPC finalize_approve_session unexpected error: %s", exc, exc_info=True)
            raise ReviewDomainException(
                500, "ERR_DATABASE_TRANSACTION_FAILED", f"Lỗi giao dịch phê duyệt CSDL: {exc}"
            ) from exc

    async def fetch_matrix_raw(
        self, session_id: str
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Retrieve answer keys for all versions belonging to a session.

        Prioritizes the 'answer_keys' table (reading 'correct_option').
        If 'answer_keys' has no records for the versions, falls back to
        'version_questions' (reading 'correct_key' where is_current = true).

        Returns:
            Tuple of:
            - sorted version_codes: List[str] (e.g. ['101', '102', '103', '104'])
            - rows: List[Dict[str, Any]] containing at least 'version_code', 'question_no', 'answer'
        """
        # 1. Fetch versions ordered by version_code
        v_builder = (
            self.db.table("exam_versions")
            .select("id, version_code")
            .eq("session_id", session_id)
        )
        if hasattr(v_builder, "order"):
            v_builder = v_builder.order("version_code")
        v_res = v_builder.execute()
        version_rows = _get_rows(v_res)
        if not version_rows:
            return [], []

        # Natural sort version codes (F06: e.g. '1', '2', '10' instead of '1', '10', '2')
        def _natural_key(row: Dict[str, Any]) -> tuple[int, Any]:
            code = str(row.get("version_code", ""))
            return (0, int(code)) if code.isdigit() else (1, code)

        version_rows.sort(key=_natural_key)
        version_codes = [str(v["version_code"]) for v in version_rows]
        version_id_to_code = {str(v["id"]): str(v["version_code"]) for v in version_rows}
        version_ids = list(version_id_to_code.keys())

        # 2. Determine expected question count
        sq_res = (
            self.db.table("source_questions")
            .select("id")
            .eq("session_id", session_id)
            .execute()
        )
        sq_rows = _get_rows(sq_res)
        expected_q_count = len(sq_rows)

        if expected_q_count == 0:
            vq_count_res = (
                self.db.table("version_questions")
                .select("question_no")
                .in_("version_id", version_ids)
                .eq("is_current", True)
                .execute()
            )
            q_numbers = {
                int(r.get("question_no", 0))
                for r in _get_rows(vq_count_res)
                if r.get("question_no") is not None
            }
            if q_numbers:
                expected_q_count = max(q_numbers)

        # 3. Attempt reading from answer_keys (with display_no / display_correct_key alias compatibility for TASK-303/302, F15)
        ak_builder = (
            self.db.table("answer_keys")
            .select("*")
            .in_("version_id", version_ids)
        )
        if hasattr(ak_builder, "order"):
            ak_builder = ak_builder.order("question_no")
        ak_res = ak_builder.execute()
        ak_rows = _get_rows(ak_res)

        normalized_rows: List[Dict[str, Any]] = []

        if ak_rows:
            # Check completeness across all versions and questions (F03 / F15)
            ak_versions = {str(r.get("version_id", "")) for r in ak_rows}
            ak_q_numbers = {
                int(r["question_no"] if r.get("question_no") is not None else r.get("display_no", 0))
                for r in ak_rows
                if r.get("question_no") is not None or r.get("display_no") is not None
            }
            if expected_q_count == 0 and ak_q_numbers:
                expected_q_count = max(ak_q_numbers)

            expected_pairs = {
                (v_id, q_no)
                for v_id in version_ids
                for q_no in range(1, expected_q_count + 1)
            }
            actual_pairs = {
                (
                    str(r.get("version_id", "")),
                    int(r["question_no"] if r.get("question_no") is not None else r.get("display_no", 0)),
                )
                for r in ak_rows
            }
            missing_pairs = expected_pairs - actual_pairs

            if missing_pairs or ak_versions != set(version_ids):
                logger.error(
                    "FinalizeRepository: answer_keys incomplete for session %s (missing %d cells, present: %s / expected: %s)",
                    session_id,
                    len(missing_pairs),
                    ak_versions,
                    set(version_ids),
                )
                from app.models.schemas import ReviewDomainException

                raise ReviewDomainException(
                    409,
                    "ERR_INCONSISTENT_ANSWER_KEYS",
                    f"Dữ liệu bảng answer_keys bị thiếu {len(missing_pairs)} đáp án hoặc không đồng bộ giữa các mã đề thi",
                )

            logger.info(
                "FinalizeRepository: fetched %d records from answer_keys for session %s",
                len(ak_rows),
                session_id,
            )
            for r in ak_rows:
                v_code = version_id_to_code.get(str(r.get("version_id", "")))
                if v_code:
                    q_no = r["question_no"] if r.get("question_no") is not None else r.get("display_no", 0)
                    ans = str(r.get("correct_option") or r.get("display_correct_key") or "").strip().upper()
                    normalized_rows.append(
                        {
                            "version_code": v_code,
                            "question_no": int(q_no),
                            "answer": ans,
                        }
                    )
            return version_codes, normalized_rows

        # 4. Fallback to version_questions (where is_current = True)
        logger.warning(
            "FinalizeRepository: answer_keys empty for session %s, falling back to version_questions",
            session_id,
        )
        vq_builder = (
            self.db.table("version_questions")
            .select("version_id, question_no, correct_key")
            .in_("version_id", version_ids)
            .eq("is_current", True)
        )
        if hasattr(vq_builder, "order"):
            vq_builder = vq_builder.order("question_no")
        vq_res = vq_builder.execute()
        vq_rows = _get_rows(vq_res)

        if vq_rows:
            vq_versions = {str(r.get("version_id", "")) for r in vq_rows}
            vq_q_numbers = {
                int(r.get("question_no", 0))
                for r in vq_rows
                if r.get("question_no") is not None
            }
            if expected_q_count == 0 and vq_q_numbers:
                expected_q_count = max(vq_q_numbers)

            expected_vq_pairs = {
                (v_id, q_no)
                for v_id in version_ids
                for q_no in range(1, expected_q_count + 1)
            }
            actual_vq_pairs = {
                (str(r.get("version_id", "")), int(r.get("question_no", 0)))
                for r in vq_rows
            }
            missing_vq_pairs = expected_vq_pairs - actual_vq_pairs

            if missing_vq_pairs or vq_versions != set(version_ids):
                from app.models.schemas import ReviewDomainException

                raise ReviewDomainException(
                    409,
                    "ERR_INCONSISTENT_ANSWER_KEYS",
                    f"Dữ liệu câu hỏi phiên bản bị thiếu {len(missing_vq_pairs)} đáp án hoặc không đồng bộ giữa các mã đề thi",
                )

        for r in vq_rows:
            v_code = version_id_to_code.get(str(r.get("version_id", "")))
            if v_code:
                normalized_rows.append(
                    {
                        "version_code": v_code,
                        "question_no": int(r.get("question_no", 0)),
                        "answer": str(r.get("correct_key", "")).strip().upper(),
                    }
                )

        return version_codes, normalized_rows


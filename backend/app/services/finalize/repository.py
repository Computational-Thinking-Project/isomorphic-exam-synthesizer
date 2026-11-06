"""Repository Layer for Finalize and Content Lock (TASK-305).

Provides data access methods for:
- Fetching session metadata (status, approved_at, user_id)
- Aggregating pre-condition states (unapproved questions, regenerating questions, finalized versions)
- Atomic session status transition to 'approved'
- Retrieving validated cross-version display answer keys
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


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


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

    async def fetch_shuffle_snapshot(self, session_id: str) -> Dict[str, Any]:
        """Read inputs for computation; the writer must revalidate them under lock."""
        configs = _get_rows(
            self.db.table("generation_configs")
            .select("id,session_id,n_versions,ordering_preferences")
            .eq("session_id", session_id)
            .execute()
        )
        if len(configs) != 1:
            raise ReviewDomainException(
                409, "ERR_SHUFFLE_INPUT_INCOMPLETE", "Cấu hình hoán vị không hợp lệ"
            )
        versions = _get_rows(
            self.db.table("exam_versions")
            .select("id,session_id,version_code")
            .eq("session_id", session_id)
            .execute()
        )
        sources = _get_rows(
            self.db.table("source_questions")
            .select("id,session_id,question_no")
            .eq("session_id", session_id)
            .execute()
        )
        ids = [v["id"] for v in versions if v.get("id")]
        questions = (
            _get_rows(
                self.db.table("version_questions")
                .select(
                    "id,version_id,source_question_id,content,canonical_question_no,canonical_options,"
                    "canonical_correct_key,canonical_solution_md,status,is_current"
                )
                .in_("version_id", ids)
                .eq("is_current", True)
                .execute()
            )
            if ids
            else []
        )
        return {
            "config": configs[0],
            "versions": versions,
            "sources": sources,
            "questions": questions,
        }

    async def persist_shuffle_rpc(
        self,
        session_id: str,
        payload: Dict[str, Any],
        expected_versions: List[Dict[str, Any]],
        question_count: int,
    ) -> Dict[str, Any]:
        """Accept only a complete receipt from the transactional shuffle writer."""
        try:
            response = self.db.rpc(
                "finalize_persist_shuffle",
                {
                    "p_session_id": session_id,
                    "p_payload": payload,
                },
            ).execute()
        except Exception as exc:
            message = str(exc)
            if "ERR_SESSION_LOCKED" in message:
                raise ReviewDomainException(
                    423, "ERR_SESSION_LOCKED", "Phiên đề đã được khóa"
                ) from exc
            if "ERR_SHUFFLE_STALE_INPUT" in message:
                raise ReviewDomainException(
                    409, "ERR_SHUFFLE_STALE_INPUT", "Dữ liệu đã thay đổi; vui lòng thử lại"
                ) from exc
            if "ERR_SHUFFLE_NOT_READY" in message:
                raise ReviewDomainException(
                    409, "ERR_SHUFFLE_NOT_READY", "Phiên đề chưa sẵn sàng"
                ) from exc
            if "ERR_SHUFFLE_INPUT_INCOMPLETE" in message:
                raise ReviewDomainException(
                    409, "ERR_SHUFFLE_INPUT_INCOMPLETE", "Dữ liệu hoán vị không hợp lệ"
                ) from exc
            if "ERR_UNAUTHORIZED" in message or "42501" in message:
                raise ReviewDomainException(
                    403, "ERR_UNAUTHORIZED", "Không có quyền hoán vị"
                ) from exc
            if "PGRST202" in message or "Could not find the function" in message:
                raise ReviewDomainException(
                    503, "ERR_SHUFFLE_UNAVAILABLE", "Giao dịch hoán vị chưa sẵn sàng"
                ) from exc
            if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
                raise ReviewDomainException(
                    504, "ERR_UPSTREAM_TIMEOUT", "Mất kết nối khi hoán vị"
                ) from exc
            raise ReviewDomainException(
                500, "ERR_SHUFFLE_TRANSACTION_FAILED", "Giao dịch hoán vị thất bại"
            ) from exc
        receipt = getattr(response, "data", None)
        if isinstance(receipt, list) and len(receipt) == 1:
            receipt = receipt[0]

        def invalid_receipt() -> ReviewDomainException:
            return ReviewDomainException(
                502, "ERR_INVALID_SHUFFLE_RECEIPT", "Phản hồi hoán vị không hợp lệ"
            )

        if not isinstance(receipt, dict):
            raise invalid_receipt()
        versions = receipt.get("versions")
        if not isinstance(versions, list) or not versions:
            raise invalid_receipt()
        actual = set()
        for version in versions:
            if (
                not isinstance(version, dict)
                or not isinstance(version.get("version_id"), str)
                or not isinstance(version.get("version_code"), str)
                or type(version.get("total_questions")) is not int
            ):
                raise invalid_receipt()
            actual.add((version["version_id"], version["version_code"], version["total_questions"]))
        expected = {(v["id"], v["version_code"], question_count) for v in expected_versions}
        if not (
            receipt.get("session_id") == session_id
            and receipt.get("status") == "reviewed"
            and receipt.get("is_finalized") is True
            and type(question_count) is int
            and question_count > 0
            and len(expected) == len(expected_versions) > 0
            and len(actual) == len(versions)
            and actual == expected
        ):
            raise ReviewDomainException(
                502, "ERR_INVALID_SHUFFLE_RECEIPT", "Phản hồi hoán vị không hợp lệ"
            )
        return receipt

    async def check_preconditions(self, session_id: str) -> Dict[str, Any]:
        """Aggregate counts for approval preconditions across versions and questions.

        Returns:
            Dict containing:
            - total_versions: number of versions belonging to the session
            - expected_n_versions: configured n_versions from generation_configs (F19)
            - unfinalized_versions_count: number of versions where is_finalized is False
            - total_questions: total count of current question variants
            - unapproved_count: count of current questions not having status 'approved'
            - regenerating_count: count of current questions with status 'regenerating'
            - missing_pairs_count: count of (version, source_question) pairs missing active approved variants (F02)
            - source_questions_count: count of required source questions
        """
        # 0. Fetch configured expected number of versions from generation_configs (F19 Fail-Closed)
        cfg_res = (
            self.db.table("generation_configs")
            .select("n_versions")
            .eq("session_id", session_id)
            .execute()
        )
        cfg_rows = _get_rows(cfg_res)
        config_error: Optional[str] = None
        if not cfg_rows:
            config_error = "ERR_CONFIG_NOT_FOUND"
            expected_n_versions = None
        elif len(cfg_rows) != 1:
            config_error = "ERR_CONFIG_AMBIGUOUS"
            expected_n_versions = None
        else:
            n_versions_list = [
                int(c["n_versions"]) for c in cfg_rows if c.get("n_versions") is not None
            ]
            if not n_versions_list:
                config_error = "ERR_CONFIG_NOT_FOUND"
                expected_n_versions = None
            elif len(set(n_versions_list)) > 1:
                config_error = "ERR_CONFIG_AMBIGUOUS"
                expected_n_versions = None
            else:
                expected_n_versions = n_versions_list[0]

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
                "expected_n_versions": expected_n_versions,
                "config_error": config_error,
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
            self.db.table("source_questions").select("id").eq("session_id", session_id).execute()
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

        required_pairs = {(v_id, s_id) for v_id in version_ids for s_id in all_source_ids}

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
            "expected_n_versions": expected_n_versions,
            "config_error": config_error,
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
                503,
                "ERR_FINALIZATION_UNAVAILABLE",
                "Hệ thống CSDL không hỗ trợ RPC giao dịch chốt đề",
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
            if isinstance(rpc_data, list) and len(rpc_data) == 1:
                rpc_data = rpc_data[0]
            if (
                isinstance(rpc_data, dict)
                and rpc_data.get("status") == "approved"
                and rpc_data.get("session_id") == session_id
                and _valid_timestamp(rpc_data.get("approved_at"))
            ):
                return rpc_data
            raise ReviewDomainException(
                502, "ERR_INVALID_FINALIZATION_RECEIPT", "Phản hồi phê duyệt không hợp lệ"
            )
        except ReviewDomainException:
            raise
        except Exception as exc:
            err_msg = str(exc)

            # 1. Domain invariant exceptions from Stored Procedure
            if "ERR_SESSION_LOCKED" in err_msg:
                raise ReviewDomainException(
                    423,
                    "ERR_SESSION_LOCKED",
                    "Phiên đề đã được phê duyệt và khóa bất biến vĩnh viễn",
                ) from exc
            if "ERR_QUESTION_REGENERATING" in err_msg:
                raise ReviewDomainException(
                    409,
                    "ERR_QUESTION_REGENERATING",
                    "Còn câu hỏi đang trong tiến trình sinh lại bởi AI",
                ) from exc
            if "ERR_CONFIG_NOT_FOUND" in err_msg:
                raise ReviewDomainException(
                    422, "ERR_CONFIG_NOT_FOUND", "Không tìm thấy cấu hình sinh đề của phiên thi"
                ) from exc
            if "ERR_CONFIG_AMBIGUOUS" in err_msg:
                raise ReviewDomainException(
                    422, "ERR_CONFIG_AMBIGUOUS", "Cấu hình sinh đề không đồng nhất"
                ) from exc
            if "ERR_INCONSISTENT_ANSWER_KEYS" in err_msg:
                raise ReviewDomainException(
                    409,
                    "ERR_INCONSISTENT_ANSWER_KEYS",
                    "Ma trận đáp án không đầy đủ hoặc không hợp lệ",
                ) from exc
            if "ERR_NOT_ALL_QUESTIONS_APPROVED" in err_msg or "REVIEW_SOURCE_MISMATCH" in err_msg:
                raise ReviewDomainException(
                    400,
                    "ERR_NOT_ALL_QUESTIONS_APPROVED",
                    "Còn câu hỏi chưa được thẩm định phê duyệt",
                ) from exc
            if "ERR_VERSIONS_NOT_FINALIZED" in err_msg:
                raise ReviewDomainException(
                    400, "ERR_VERSIONS_NOT_FINALIZED", "Còn phiên bản đề thi chưa hoàn tất hoán vị"
                ) from exc
            if "ERR_INVALID_SESSION_STATE" in err_msg:
                raise ReviewDomainException(
                    409,
                    "ERR_INVALID_SESSION_STATE",
                    "Trạng thái phiên đề đã thay đổi hoặc không hợp lệ",
                ) from exc
            if "ERR_SESSION_NOT_FOUND" in err_msg:
                raise ReviewDomainException(
                    404, "ERR_SESSION_NOT_FOUND", f"Phiên đề '{session_id}' không tồn tại"
                ) from exc
            if "ERR_UNAUTHORIZED" in err_msg:
                raise ReviewDomainException(
                    403, "ERR_UNAUTHORIZED", "Người dùng không có quyền phê duyệt phiên thi này"
                ) from exc

            # 2. Strict Fail-Closed Infrastructure & Transport Exceptions
            if "PGRST202" in err_msg or "Could not find the function" in err_msg:
                logger.critical(
                    "RPC finalize_approve_session missing in database schema (PGRST202): %s", exc
                )
                raise ReviewDomainException(
                    503,
                    "ERR_FINALIZATION_UNAVAILABLE",
                    "Hệ thống giao dịch chốt đề chưa sẵn sàng trên CSDL (PGRST202)",
                ) from exc
            if "42501" in err_msg or "permission denied" in err_msg:
                logger.critical(
                    "Database permission denied for finalize_approve_session (42501): %s", exc
                )
                raise ReviewDomainException(
                    500,
                    "ERR_DATABASE_PERMISSION_DENIED",
                    "Không có quyền thực thi thủ tục phê duyệt CSDL",
                ) from exc
            if isinstance(exc, (TimeoutError, ConnectionError, OSError)) or any(
                term in err_msg.lower()
                for term in (
                    "timeout",
                    "clientconnectorerror",
                    "connection reset",
                    "connection refused",
                    "connection error",
                )
            ):
                logger.error(
                    "Upstream timeout or connection drop during finalize_approve_session: %s", exc
                )
                raise ReviewDomainException(
                    504,
                    "ERR_UPSTREAM_TIMEOUT",
                    "Mất kết nối với dịch vụ giao dịch CSDL trong quá trình chốt đề",
                ) from exc

            # 3. Catch-all: Fail-closed on any unexpected database error
            logger.critical("RPC finalize_approve_session unexpected error: %s", exc, exc_info=True)
            raise ReviewDomainException(
                500, "ERR_DATABASE_TRANSACTION_FAILED", "Lỗi giao dịch phê duyệt CSDL"
            ) from exc

    # Contract alias for TASK-305 / TASK-302 alignment (F13)
    finalize_approve_rpc = update_session_approved

    async def fetch_matrix_raw(self, session_id: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Read only complete, validated display keys produced by shuffle."""

        def inconsistent() -> ReviewDomainException:
            return ReviewDomainException(
                409, "ERR_INCONSISTENT_ANSWER_KEYS", "Ma tr?n ??p ?n kh?ng ??y ?? ho?c kh?ng h?p l?"
            )

        configs = _get_rows(
            self.db.table("generation_configs")
            .select("n_versions")
            .eq("session_id", session_id)
            .execute()
        )
        versions = _get_rows(
            self.db.table("exam_versions")
            .select("id, version_code, is_finalized")
            .eq("session_id", session_id)
            .execute()
        )
        sources = _get_rows(
            self.db.table("source_questions").select("id").eq("session_id", session_id).execute()
        )
        if len(configs) != 1 or not sources or not versions:
            raise inconsistent()
        n = configs[0].get("n_versions")
        if not isinstance(n, int) or isinstance(n, bool) or n != len(versions):
            raise inconsistent()
        if any(
            not v.get("id") or not v.get("version_code") or v.get("is_finalized") is not True
            for v in versions
        ):
            raise inconsistent()
        ids = [str(v["id"]) for v in versions]
        codes = [str(v["version_code"]) for v in versions]
        if len(set(ids)) != n or len(set(codes)) != n:
            raise inconsistent()
        id_to_code = dict(zip(ids, codes))
        keys = _get_rows(self.db.table("answer_keys").select("*").in_("version_id", ids).execute())
        expected = {(vid, q) for vid in ids for q in range(1, len(sources) + 1)}
        seen: set[tuple[str, int]] = set()
        rows: List[Dict[str, Any]] = []
        for key in keys:
            vid, number, display_no = (
                str(key.get("version_id", "")),
                key.get("question_no"),
                key.get("display_no"),
            )
            answer, display_answer = key.get("correct_option"), key.get("display_correct_key")
            if (
                not isinstance(number, int)
                or isinstance(number, bool)
                or (display_no is not None and display_no != number)
                or answer not in ("A", "B", "C", "D")
                or (display_answer is not None and display_answer != answer)
            ):
                raise inconsistent()
            pair = (vid, number)
            if pair not in expected or pair in seen:
                raise inconsistent()
            seen.add(pair)
            rows.append({"version_code": id_to_code[vid], "question_no": number, "answer": answer})
        if seen != expected:
            raise inconsistent()
        codes.sort(key=lambda code: (0, int(code), code) if code.isdigit() else (1, code, code))
        return codes, rows

    async def fetch_preview_snapshot(self, session_id: str) -> Dict[str, Any]:
        """Fetch and assemble post-shuffle pre-approval preview projection (W4-MVP-05).

        Validates:
        1. Session existence and allowed state ('reviewed', 'approved', 'exported').
        2. Exactly 1 generation config with 1..4 versions.
        3. All exam versions are finalized (is_finalized=True) and match n_versions.
        4. Complete set of approved, current questions for each version with contiguous question_no (1..M).
        5. Valid, synchronized options (4 distinct items) and correct_key ('A'..'D').
        6. Consistent answer_keys for all versions matching display question_no and correct_key.
        7. Cross-version answers matrix sorted by display question_no.
        """

        def inconsistent(detail: str = "Dữ liệu đề sau hoán vị không nhất quán") -> ReviewDomainException:
            return ReviewDomainException(409, "ERR_INCONSISTENT_ANSWER_KEYS", detail)

        # Step 1: Session meta
        session_meta = await self.get_session_meta(session_id)
        if not session_meta:
            raise ReviewDomainException(
                404, "ERR_SESSION_NOT_FOUND", f"Phiên làm việc '{session_id}' không tồn tại"
            )
        status = str(session_meta.get("status", "")).lower()
        if status not in ("reviewed", "approved", "exported"):
            raise ReviewDomainException(
                409,
                "ERR_INVALID_SESSION_STATE",
                f"Phiên đề ở trạng thái '{status}' chưa sẵn sàng để xem trước",
            )

        # Step 2: Generation config
        configs = _get_rows(
            self.db.table("generation_configs")
            .select("n_versions")
            .eq("session_id", session_id)
            .execute()
        )
        if len(configs) != 1:
            raise inconsistent("Cấu hình sinh đề không hợp lệ")
        n = configs[0].get("n_versions")
        if not isinstance(n, int) or isinstance(n, bool) or not (1 <= n <= 4):
            raise inconsistent("Số lượng phiên bản đề trong cấu hình không hợp lệ")

        # Step 3: Exam versions
        versions = _get_rows(
            self.db.table("exam_versions")
            .select("id, version_code, is_finalized, shuffle_seed, permutations")
            .eq("session_id", session_id)
            .execute()
        )
        if len(versions) != n:
            raise inconsistent("Số lượng bản ghi exam_versions không khớp với cấu hình")

        if any(v.get("is_finalized") is not True for v in versions):
            raise ReviewDomainException(
                409,
                "ERR_SHUFFLE_REQUIRED",
                "Phiên đề chưa hoàn tất hoán vị đề thi. Vui lòng thực hiện hoán vị trước khi xem trước.",
            )

        ids = [str(v["id"]) for v in versions]
        codes = [str(v["version_code"]) for v in versions]
        if len(set(ids)) != n or len(set(codes)) != n:
            raise inconsistent("Mã hoặc định danh phiên bản đề bị trùng lặp")

        # Step 4: Source questions count
        sources = _get_rows(
            self.db.table("source_questions")
            .select("id, question_no")
            .eq("session_id", session_id)
            .execute()
        )
        if not sources:
            raise inconsistent("Không tìm thấy câu hỏi nguồn của phiên đề")
        m = len(sources)

        # Step 5: Version questions
        raw_questions = _get_rows(
            self.db.table("version_questions")
            .select(
                "id, version_id, source_question_id, question_no, content, options, "
                "correct_key, solution_md, canonical_question_no, status, is_current"
            )
            .in_("version_id", ids)
            .eq("is_current", True)
            .execute()
        )

        questions_by_version: Dict[str, List[Dict[str, Any]]] = {vid: [] for vid in ids}
        for q in raw_questions:
            vid = str(q.get("version_id", ""))
            if vid in questions_by_version:
                questions_by_version[vid].append(q)

        # Step 6: Answer keys
        raw_keys = _get_rows(
            self.db.table("answer_keys")
            .select("version_id, question_no, correct_option, display_no, display_correct_key")
            .in_("version_id", ids)
            .execute()
        )
        keys_by_version: Dict[str, Dict[int, str]] = {vid: {} for vid in ids}
        for k in raw_keys:
            vid = str(k.get("version_id", ""))
            q_no = k.get("question_no")
            opt = k.get("correct_option")
            if vid in keys_by_version and isinstance(q_no, int) and opt in ("A", "B", "C", "D"):
                keys_by_version[vid][q_no] = opt

        # Step 7: Build and validate preview versions
        preview_versions: List[Dict[str, Any]] = []
        for v in versions:
            vid = str(v["id"])
            v_code = str(v["version_code"])
            v_seed = v.get("shuffle_seed")
            v_questions = questions_by_version[vid]

            if len(v_questions) != m:
                raise inconsistent(f"Phiên bản {v_code} thiếu câu hỏi (có {len(v_questions)}/{m} câu)")

            if any(not isinstance(q.get("question_no"), int) for q in v_questions):
                raise inconsistent(f"Thứ tự câu hỏi hiển thị của phiên bản {v_code} không hợp lệ")
            q_numbers = [int(q["question_no"]) for q in v_questions]
            if sorted(q_numbers) != list(range(1, m + 1)):
                raise inconsistent(f"Thứ tự câu hỏi hiển thị của phiên bản {v_code} không liên tục từ 1 đến {m}")

            sorted_v_questions = sorted(v_questions, key=lambda x: int(x["question_no"]))
            formatted_questions: List[Dict[str, Any]] = []

            for q in sorted_v_questions:
                q_no = int(q["question_no"])
                options = q.get("options")
                correct_key = q.get("correct_key")
                solution_md = q.get("solution_md") or ""

                if not isinstance(options, list) or len(options) != 4 or not all(isinstance(o, str) and o.strip() for o in options):
                    raise inconsistent(f"Phương án của câu {q_no} trong phiên bản {v_code} không hợp lệ")

                if correct_key not in ("A", "B", "C", "D"):
                    raise inconsistent(f"Đáp án đúng của câu {q_no} trong phiên bản {v_code} không hợp lệ")

                key_in_table = keys_by_version[vid].get(q_no)
                if key_in_table != correct_key:
                    raise inconsistent(f"Đáp án bảng tra không khớp đáp án câu hỏi {q_no} trong phiên bản {v_code}")

                canonical_no = q.get("canonical_question_no")
                if not isinstance(canonical_no, int) or canonical_no < 1:
                    canonical_no = q_no

                formatted_questions.append({
                    "id": str(q["id"]),
                    "source_question_id": str(q["source_question_id"]),
                    "question_no": q_no,
                    "canonical_question_no": canonical_no,
                    "content": str(q.get("content", "")),
                    "options": options,
                    "correct_key": correct_key,
                    "solution_md": str(solution_md),
                    "status": str(q.get("status", "approved")),
                })

            ans_map = {str(q_no): opt for q_no, opt in sorted(keys_by_version[vid].items())}

            preview_versions.append({
                "id": vid,
                "version_code": v_code,
                "is_finalized": True,
                "shuffle_seed": str(v_seed) if v_seed is not None else None,
                "total_questions": m,
                "questions": formatted_questions,
                "answer_keys": ans_map,
            })

        preview_versions.sort(
            key=lambda x: (0, int(x["version_code"]), x["version_code"])
            if x["version_code"].isdigit()
            else (1, x["version_code"], x["version_code"])
        )

        # Step 8: Build matrix
        matrix: List[Dict[str, Any]] = []
        for q_no in range(1, m + 1):
            row_answers: Dict[str, str] = {}
            for pv in preview_versions:
                ans = pv["answer_keys"].get(str(q_no))
                if not ans:
                    raise inconsistent(f"Thiếu đáp án câu {q_no} cho phiên bản {pv['version_code']}")
                row_answers[pv["version_code"]] = ans
            matrix.append({"question_no": q_no, "answers": row_answers})

        return {
            "session_id": session_id,
            "status": status,
            "is_finalized": True,
            "n_versions": n,
            "total_questions": m,
            "versions": preview_versions,
            "matrix": matrix,
        }

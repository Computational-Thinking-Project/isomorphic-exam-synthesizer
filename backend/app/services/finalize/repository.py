"""Repository Layer for Finalize and Content Lock (TASK-305).

Provides data access methods for:
- Fetching session metadata (status, approved_at, user_id)
- Aggregating pre-condition states (unapproved questions, regenerating questions, finalized versions)
- Atomic session status transition to 'approved'
- Retrieving validated cross-version display answer keys
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

from supabase import Client

from app.models.schemas import ReviewDomainException
from app.services.blueprint.adapters import normalized_text
from app.services.shuffler.service import generate_deterministic_seed, sync_solution_text

logger = logging.getLogger(__name__)

VERSION_CODE_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")


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
            .select("id, title, status, approved_at, user_id, updated_at")
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

        Enforces:
        1. Session existence and allowed state ('reviewed', 'approved', 'exported').
        2. Exactly 1 generation config with 1..4 versions.
        3. All exam versions are finalized (is_finalized=True) and match n_versions.
        4. Validated shuffle provenance and permutation metadata (permutations JSON).
        5. Source questions count M in range 1..20.
        6. Complete set of approved, current questions for each version with contiguous question_no (1..M).
        7. Strict parity with exporter DisplayQuestion invariants:
           - Non-empty, non-whitespace content (1..16000 chars)
           - Non-empty, non-whitespace solution_md (1..16000 chars)
           - Exactly 4 options distinct after normalized_text
           - Question status == 'approved'
           - Display correct_key in ('A', 'B', 'C', 'D')
        8. Complete answer_keys integrity validation:
           - No duplicate or unexpected keys
           - display_no == question_no, display_correct_key == correct_option
           - Bidirectional consistency between answer_keys, version_questions, and permutations.
        9. Deterministic cross-version answers matrix sorted by display question_no.
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
        codes: List[str] = []
        for v in versions:
            raw_code = v.get("version_code")
            if (
                not isinstance(raw_code, str)
                or raw_code != raw_code.strip()
                or not VERSION_CODE_REGEX.match(raw_code)
            ):
                raise inconsistent(
                    f"Mã phiên bản (version_code) '{raw_code}' không hợp lệ hoặc sai định dạng quy định"
                )
            codes.append(raw_code)
        if len(set(ids)) != n or len({c.casefold() for c in codes}) != n:
            raise inconsistent("Mã hoặc định danh phiên bản đề bị trùng lặp")

        # Step 4: Source questions count & 1:1 mappings
        sources = _get_rows(
            self.db.table("source_questions")
            .select("id, question_no")
            .eq("session_id", session_id)
            .execute()
        )
        if not sources or not (1 <= len(sources) <= 20):
            raise inconsistent(
                f"Số lượng câu hỏi nguồn ({len(sources) if sources else 0}) không nằm trong giới hạn cho phép (1..20)"
            )
        m = len(sources)
        source_by_no: Dict[int, str] = {}
        source_by_id: Dict[str, int] = {}
        for s in sources:
            s_id = str(s.get("id", ""))
            s_no = s.get("question_no")
            if not isinstance(s_no, int) or isinstance(s_no, bool) or s_no < 1:
                raise inconsistent("Thứ tự câu hỏi nguồn (question_no) không hợp lệ")
            if s_no in source_by_no or s_id in source_by_id:
                raise inconsistent("Phát hiện trùng lặp mã hoặc thứ tự câu hỏi nguồn")
            source_by_no[s_no] = s_id
            source_by_id[s_id] = s_no

        canonical_numbers = set(source_by_no.keys())
        if len(canonical_numbers) != m:
            raise inconsistent("Danh sách mã số câu hỏi nguồn không hợp lệ")

        # Step 5: Version questions
        raw_questions = _get_rows(
            self.db.table("version_questions")
            .select(
                "id, version_id, source_question_id, question_no, content, options, "
                "correct_key, solution_md, canonical_question_no, canonical_options, "
                "canonical_correct_key, canonical_solution_md, status, is_current"
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

        # Step 6: Complete Answer keys Integrity Check
        raw_keys = _get_rows(
            self.db.table("answer_keys")
            .select("version_id, question_no, correct_option, display_no, display_correct_key, canonical_question_no")
            .in_("version_id", ids)
            .execute()
        )

        expected_pairs = {(vid, q) for vid in ids for q in range(1, m + 1)}
        seen_pairs: set[tuple[str, int]] = set()
        keys_by_version: Dict[str, Dict[int, Dict[str, Any]]] = {vid: {} for vid in ids}

        for k in raw_keys:
            vid = str(k.get("version_id", ""))
            q_no = k.get("question_no")
            display_no = k.get("display_no")
            opt = k.get("correct_option")
            display_opt = k.get("display_correct_key")
            canonical_q_no = k.get("canonical_question_no")

            if (
                vid not in keys_by_version
                or not isinstance(q_no, int)
                or isinstance(q_no, bool)
                or (display_no is not None and display_no != q_no)
                or opt not in ("A", "B", "C", "D")
                or (display_opt is not None and display_opt != opt)
                or not isinstance(canonical_q_no, int)
                or isinstance(canonical_q_no, bool)
                or canonical_q_no not in canonical_numbers
            ):
                raise inconsistent("Dữ liệu bảng tra đáp án không hợp lệ hoặc không nhất quán")

            pair = (vid, q_no)
            if pair not in expected_pairs or pair in seen_pairs:
                raise inconsistent("Phát hiện trùng lặp hoặc thừa bản ghi trong bảng tra đáp án")
            seen_pairs.add(pair)
            keys_by_version[vid][q_no] = {
                "correct_option": opt,
                "canonical_question_no": canonical_q_no,
            }

        if seen_pairs != expected_pairs:
            raise inconsistent("Bảng tra đáp án không đầy đủ cho tất cả phiên bản và câu hỏi")

        # Step 7: Build and validate preview versions
        preview_versions: List[Dict[str, Any]] = []
        for v in versions:
            vid = str(v["id"])
            v_code = str(v["version_code"])
            v_seed = v.get("shuffle_seed")
            permutations = v.get("permutations")

            # Validate shuffle seed against deterministic contract
            expected_seed, _ = generate_deterministic_seed(str(session_id), v_code)
            if not isinstance(v_seed, str) or v_seed.strip().lower() != expected_seed.lower():
                raise inconsistent(f"Mã hạt giống hoán vị (shuffle_seed) của phiên bản {v_code} không hợp lệ hoặc không khớp hợp đồng tất định")

            # Validate shuffle provenance
            if not isinstance(permutations, dict):
                raise inconsistent(f"Dữ liệu hoán vị (permutations) của phiên bản {v_code} không hợp lệ")

            for req_key in ("question_order", "display_to_canonical", "canonical_to_display", "option_permutations"):
                if req_key not in permutations:
                    raise inconsistent(f"Dữ liệu hoán vị của phiên bản {v_code} thiếu trường '{req_key}'")

            q_order = permutations.get("question_order")
            c_to_d = permutations.get("canonical_to_display")
            d_to_c = permutations.get("display_to_canonical")
            opt_perms = permutations.get("option_permutations")

            if (
                not isinstance(q_order, list)
                or len(q_order) != m
                or any(not isinstance(x, int) or isinstance(x, bool) for x in q_order)
                or len(set(q_order)) != m
                or set(q_order) != canonical_numbers
            ):
                raise inconsistent(f"Thứ tự câu hỏi (question_order) của phiên bản {v_code} không hợp lệ")

            if (
                not isinstance(c_to_d, dict)
                or not isinstance(d_to_c, dict)
                or not isinstance(opt_perms, dict)
                or len(c_to_d) != m
                or len(d_to_c) != m
            ):
                raise inconsistent(f"Bảng ánh xạ hoán vị của phiên bản {v_code} không hợp lệ")

            if len(opt_perms) != m:
                raise inconsistent(f"Bảng hoán vị phương án (option_permutations) của phiên bản {v_code} không hợp lệ")

            # Validate bijection between display_to_canonical and canonical_to_display
            for d_str, c_val in d_to_c.items():
                if not str(d_str).isdigit() or not isinstance(c_val, int) or isinstance(c_val, bool):
                    raise inconsistent(f"Ánh xạ display_to_canonical của phiên bản {v_code} không hợp lệ")
                d_int = int(d_str)
                if d_int not in range(1, m + 1) or c_val not in canonical_numbers:
                    raise inconsistent(f"Giá trị ánh xạ display_to_canonical của phiên bản {v_code} vượt giới hạn")
                if c_to_d.get(str(c_val)) != d_int and c_to_d.get(c_val) != d_int:
                    raise inconsistent(f"Ánh xạ hai chiều hoán vị không đối xứng cho phiên bản {v_code}")

            for c_str, d_val in c_to_d.items():
                if not str(c_str).isdigit() or not isinstance(d_val, int) or isinstance(d_val, bool):
                    raise inconsistent(f"Ánh xạ canonical_to_display của phiên bản {v_code} không hợp lệ")
                c_int = int(c_str)
                if c_int not in canonical_numbers or d_val not in range(1, m + 1):
                    raise inconsistent(f"Giá trị ánh xạ canonical_to_display của phiên bản {v_code} vượt giới hạn")
                if d_to_c.get(str(d_val)) != c_int and d_to_c.get(d_val) != c_int:
                    raise inconsistent(f"Ánh xạ hai chiều hoán vị không đối xứng cho phiên bản {v_code}")

            # Cross-check question_order against display_to_canonical and canonical_to_display
            for d_idx, c_num in enumerate(q_order, start=1):
                d_str = str(d_idx)
                c_str = str(c_num)
                expected_c = d_to_c.get(d_str, d_to_c.get(d_idx))
                if expected_c != c_num:
                    raise inconsistent(
                        f"Thứ tự question_order tại vị trí {d_idx} (câu gốc {c_num}) không khớp display_to_canonical ({expected_c}) cho phiên bản {v_code}"
                    )
                expected_d = c_to_d.get(c_str, c_to_d.get(c_num))
                if expected_d != d_idx:
                    raise inconsistent(
                        f"Thứ tự question_order tại vị trí {d_idx} (câu gốc {c_num}) không khớp canonical_to_display ({expected_d}) cho phiên bản {v_code}"
                    )

            v_questions = questions_by_version[vid]
            if len(v_questions) != m:
                raise inconsistent(f"Phiên bản {v_code} thiếu câu hỏi (có {len(v_questions)}/{m} câu)")

            # Verify 1:1 source question coverage
            v_source_ids = {str(q.get("source_question_id", "")) for q in v_questions}
            if v_source_ids != set(source_by_id.keys()):
                raise inconsistent(f"Phiên bản {v_code} không bao phủ đủ 1:1 các câu hỏi nguồn")

            if any(not isinstance(q.get("question_no"), int) for q in v_questions):
                raise inconsistent(f"Thứ tự câu hỏi hiển thị của phiên bản {v_code} không hợp lệ")
            q_numbers = [int(q["question_no"]) for q in v_questions]
            if sorted(q_numbers) != list(range(1, m + 1)):
                raise inconsistent(f"Thứ tự câu hỏi hiển thị của phiên bản {v_code} không liên tục từ 1 đến {m}")

            sorted_v_questions = sorted(v_questions, key=lambda x: int(x["question_no"]))
            formatted_questions: List[Dict[str, Any]] = []

            labels = "ABCD"
            for q in sorted_v_questions:
                q_no = int(q["question_no"])
                content = q.get("content")
                solution_md = q.get("solution_md")
                options = q.get("options")
                correct_key = q.get("correct_key")
                q_status = q.get("status")
                canonical_no = q.get("canonical_question_no")
                canonical_options = q.get("canonical_options")
                canonical_correct_key = q.get("canonical_correct_key")
                canonical_solution_md = q.get("canonical_solution_md")
                src_id = str(q.get("source_question_id", ""))

                # Exporter DisplayQuestion Invariant: Content non-empty
                if not isinstance(content, str) or not (1 <= len(content.strip()) <= 16000):
                    raise inconsistent(f"Đề bài câu {q_no} trong phiên bản {v_code} bị rỗng hoặc không hợp lệ")

                # Exporter DisplayQuestion Invariant: Solution non-empty
                if not isinstance(solution_md, str) or not (1 <= len(solution_md.strip()) <= 16000):
                    raise inconsistent(f"Lời giải câu {q_no} trong phiên bản {v_code} bị rỗng hoặc thiếu")

                # Exporter DisplayQuestion Invariant: Options 4 distinct after normalization, each 1..16000 chars
                if (
                    not isinstance(options, list)
                    or len(options) != 4
                    or not all(isinstance(o, str) and (1 <= len(o.strip()) <= 16000) for o in options)
                ):
                    raise inconsistent(f"Phương án của câu {q_no} trong phiên bản {v_code} không hợp lệ hoặc vượt quá giới hạn 16,000 ký tự")
                if len({normalized_text(o) for o in options}) != 4:
                    raise inconsistent(f"Phương án của câu {q_no} trong phiên bản {v_code} chứa các lựa chọn trùng lặp sau chuẩn hóa")

                if correct_key not in ("A", "B", "C", "D"):
                    raise inconsistent(f"Đáp án đúng của câu {q_no} trong phiên bản {v_code} không hợp lệ")

                # Exporter DisplayQuestion Invariant: status must be approved
                if q_status != "approved":
                    raise inconsistent(f"Câu hỏi {q_no} trong phiên bản {v_code} chưa được thẩm định phê duyệt (status='{q_status}')")

                # Canonical question mapping & Source Lineage
                if (
                    not isinstance(canonical_no, int)
                    or isinstance(canonical_no, bool)
                    or canonical_no not in canonical_numbers
                ):
                    raise inconsistent(f"Thứ tự câu hỏi gốc (canonical_question_no) của câu {q_no} trong phiên bản {v_code} không hợp lệ")

                if src_id not in source_by_id or source_by_id[src_id] != canonical_no:
                    raise inconsistent(f"Nguồn gốc câu hỏi (source_question_id) của câu {q_no} trong phiên bản {v_code} không khớp câu gốc {canonical_no}")

                c_str = str(canonical_no)
                q_str = str(q_no)
                if (c_to_d.get(c_str) != q_no and c_to_d.get(canonical_no) != q_no) or (d_to_c.get(q_str) != canonical_no and d_to_c.get(q_no) != canonical_no):
                    raise inconsistent(f"Ánh xạ hoán vị không khớp giữa version_questions và permutations cho câu {q_no} trong phiên bản {v_code}")

                # Option Permutation & Canonical Consistency
                if not isinstance(canonical_options, list) or len(canonical_options) != 4 or not all(isinstance(o, str) and o.strip() for o in canonical_options):
                    raise inconsistent(f"Phương án gốc (canonical_options) của câu {q_no} trong phiên bản {v_code} không hợp lệ")
                if canonical_correct_key not in ("A", "B", "C", "D"):
                    raise inconsistent(f"Đáp án gốc (canonical_correct_key) của câu {q_no} trong phiên bản {v_code} không hợp lệ")

                perm_map = opt_perms.get(q_str) or opt_perms.get(q_no)
                if not isinstance(perm_map, dict) or set(perm_map.keys()) != set("ABCD") or set(perm_map.values()) != set("ABCD"):
                    raise inconsistent(f"Bảng hoán vị phương án (option_permutations) của câu {q_no} trong phiên bản {v_code} không hợp lệ")

                if correct_key != perm_map.get(canonical_correct_key):
                    raise inconsistent(f"Đáp án đúng sau hoán vị không khớp bảng hoán vị cho câu {q_no} trong phiên bản {v_code}")

                for i, label in enumerate(labels):
                    mapped_label = perm_map[label]
                    j = labels.index(mapped_label)
                    if options[j] != canonical_options[i]:
                        raise inconsistent(f"Nội dung phương án hiển thị '{mapped_label}' không khớp phương án gốc '{label}' cho câu {q_no} trong phiên bản {v_code}")

                # Solution synchronization check
                if canonical_solution_md:
                    expected_solution = sync_solution_text(
                        canonical_solution_md,
                        canonical_key=canonical_correct_key,
                        display_key=correct_key,
                    )
                    if solution_md.strip() != expected_solution.strip():
                        raise inconsistent(f"Lời giải câu {q_no} trong phiên bản {v_code} không khớp lời giải sau đồng bộ hoán vị")

                # Answer key consistency
                key_entry = keys_by_version[vid].get(q_no)
                if not key_entry or key_entry["correct_option"] != correct_key:
                    raise inconsistent(f"Đáp án bảng tra không khớp đáp án câu hỏi {q_no} trong phiên bản {v_code}")
                if key_entry["canonical_question_no"] != canonical_no:
                    raise inconsistent(f"Thứ tự câu hỏi gốc trong bảng tra không khớp câu hỏi {q_no} trong phiên bản {v_code}")

                formatted_questions.append({
                    "id": str(q["id"]),
                    "source_question_id": src_id,
                    "question_no": q_no,
                    "canonical_question_no": canonical_no,
                    "content": content.strip(),
                    "options": options,
                    "correct_key": correct_key,
                    "solution_md": solution_md.strip(),
                    "status": "approved",
                })

            ans_map = {str(q_no): keys_by_version[vid][q_no]["correct_option"] for q_no in range(1, m + 1)}

            preview_versions.append({
                "id": vid,
                "version_code": v_code,
                "is_finalized": True,
                "shuffle_seed": str(v_seed),
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

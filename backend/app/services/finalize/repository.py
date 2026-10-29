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
            }

        version_ids = [str(v["id"]) for v in version_rows]

        # 2. Fetch current questions across all versions
        q_res = (
            self.db.table("version_questions")
            .select("id, version_id, status, is_current")
            .in_("version_id", version_ids)
            .eq("is_current", True)
            .execute()
        )
        q_rows = _get_rows(q_res)
        total_questions = len(q_rows)

        unapproved_count = 0
        regenerating_count = 0

        for q in q_rows:
            st = str(q.get("status", "")).lower()
            if st == "regenerating":
                regenerating_count += 1
            if st != "approved":
                unapproved_count += 1

        return {
            "total_versions": total_versions,
            "unfinalized_versions_count": unfinalized_versions_count,
            "total_questions": total_questions,
            "unapproved_count": unapproved_count,
            "regenerating_count": regenerating_count,
        }

    async def update_session_approved(
        self, session_id: str, allowed_statuses: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Atomically transition session status to 'approved' and record approved_at.

        Returns updated row dict if successful, or None if condition not met (e.g. status changed).
        """
        if allowed_statuses is None:
            allowed_statuses = ["reviewed", "generated"]

        now_str = _now_iso()
        res = (
            self.db.table("exam_sessions")
            .update(
                {
                    "status": "approved",
                    "approved_at": now_str,
                    "updated_at": now_str,
                }
            )
            .eq("id", session_id)
            .in_("status", allowed_statuses)
            .execute()
        )
        rows = _get_rows(res)
        return rows[0] if rows else None

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
        v_res = (
            self.db.table("exam_versions")
            .select("id, version_code")
            .eq("session_id", session_id)
            .order("version_code")
            .execute()
        )
        version_rows = _get_rows(v_res)
        if not version_rows:
            return [], []

        # Sort version codes naturally
        version_rows.sort(key=lambda x: str(x.get("version_code", "")))
        version_codes = [str(v["version_code"]) for v in version_rows]
        version_id_to_code = {str(v["id"]): str(v["version_code"]) for v in version_rows}
        version_ids = list(version_id_to_code.keys())

        # 2. Attempt reading from answer_keys
        ak_res = (
            self.db.table("answer_keys")
            .select("version_id, question_no, correct_option")
            .in_("version_id", version_ids)
            .order("question_no")
            .execute()
        )
        ak_rows = _get_rows(ak_res)

        normalized_rows: List[Dict[str, Any]] = []

        if ak_rows:
            logger.info(
                "FinalizeRepository: fetched %d records from answer_keys for session %s",
                len(ak_rows),
                session_id,
            )
            for r in ak_rows:
                v_code = version_id_to_code.get(str(r.get("version_id", "")))
                if v_code:
                    normalized_rows.append(
                        {
                            "version_code": v_code,
                            "question_no": int(r.get("question_no", 0)),
                            "answer": str(r.get("correct_option", "")),
                        }
                    )
            return version_codes, normalized_rows

        # 3. Fallback to version_questions (where is_current = True)
        logger.warning(
            "FinalizeRepository: answer_keys empty for session %s, falling back to version_questions",
            session_id,
        )
        vq_res = (
            self.db.table("version_questions")
            .select("version_id, question_no, correct_key")
            .in_("version_id", version_ids)
            .eq("is_current", True)
            .order("question_no")
            .execute()
        )
        vq_rows = _get_rows(vq_res)

        for r in vq_rows:
            v_code = version_id_to_code.get(str(r.get("version_id", "")))
            if v_code:
                normalized_rows.append(
                    {
                        "version_code": v_code,
                        "question_no": int(r.get("question_no", 0)),
                        "answer": str(r.get("correct_key", "")),
                    }
                )

        return version_codes, normalized_rows

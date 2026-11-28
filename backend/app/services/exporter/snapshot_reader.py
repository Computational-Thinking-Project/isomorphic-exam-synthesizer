"""DB reader for the approved export snapshot (W4-MVP-07).

Read order matters. Each PostgREST call is its own transaction, so there is no
snapshot isolation across calls. The reads are only consistent IF approved and
exported sessions are locked against writes. Migration 009 and the generation
state/fencing guards enforce that boundary; test_export_snapshot_pg.py exercises
the installed migration chain with independent connections. Order: read the session first, continue
only if it is locked, read content, then re-read the session and require it to be
unchanged.

PR #58 decision: keep table reads with an authenticated user/RLS client from
get_user_db. A foreign session may be invisible (404). A service client must not
be substituted just to distinguish 403 from 404. Transport/SDK failures propagate
to the caller and are never converted into an invalid-data conflict (409).
"""

from typing import Any, Dict, List
from uuid import UUID

from supabase import Client

from app.models.schemas import ReviewDomainException
from app.services.exporter.snapshot_common import LOCKED_STATUSES, valid_timestamp
from app.services.exporter.snapshot_provenance import is_empty
from app.services.exporter.snapshot_rows import BankRoundRows, RawSnapshotRows

SESSION_COLUMNS = "id, user_id, title, status, approved_at, updated_at"
BANK_ROUND_COLUMNS = "session_id, bank_item_id, owner_id, is_legacy"
BANK_SNAPSHOT_COLUMNS = "session_id, snapshot_revision, snapshot_payload"
LOCK_FIELDS = ("user_id", "status", "approved_at", "updated_at")


def _rows(response: Any) -> List[Dict[str, Any]]:
    data = getattr(response, "data", None)
    if not data or not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _changed() -> ReviewDomainException:
    return ReviewDomainException(
        409, "ERR_EXPORT_SNAPSHOT_INVALID", "Phiên đề thay đổi trong lúc đọc snapshot"
    )


class ExportSnapshotReader:
    def __init__(self, db: Client, *, provenance_db: Client | None = None) -> None:
        self.db = db
        self.provenance_db = provenance_db

    def _session(self, session_id: str) -> Dict[str, Any] | None:
        rows = _rows(
            self.db.table("exam_sessions").select(SESSION_COLUMNS).eq("id", session_id).execute()
        )
        return rows[0] if len(rows) == 1 else None

    def _locked_session(self, session_id: str, user_id: str) -> tuple[str, Dict[str, Any]]:
        """Canonical id and first read of an owned, approved session, or raise."""
        try:
            canonical_id = str(UUID(session_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ReviewDomainException(
                400, "ERR_INVALID_SESSION_ID", "Mã phiên không đúng định dạng UUID"
            ) from exc
        if canonical_id != session_id.lower():
            raise ReviewDomainException(
                400, "ERR_INVALID_SESSION_ID", "Mã phiên không đúng định dạng UUID"
            )
        first = self._session(canonical_id)
        if first is None:
            raise ReviewDomainException(404, "ERR_SESSION_NOT_FOUND", "Phiên đề không tồn tại")
        if str(first.get("user_id")) != str(user_id):
            raise ReviewDomainException(
                403, "ERR_UNAUTHORIZED", "Người dùng không có quyền với phiên đề này"
            )
        if first.get("status") not in LOCKED_STATUSES or not valid_timestamp(
            first.get("approved_at")
        ):
            raise ReviewDomainException(
                409, "ERR_INVALID_SESSION_STATE", "Phiên đề chưa được phê duyệt để xuất"
            )
        return canonical_id, first

    def _require_unchanged(self, canonical_id: str, first: Dict[str, Any]) -> None:
        second = self._session(canonical_id)
        if second is None or any(second.get(f) != first.get(f) for f in LOCK_FIELDS):
            raise _changed()

    def load_bank_round(self, session_id: str, user_id: str) -> BankRoundRows:
        """EXT-03 G3: Bank link and, for a non-legacy round, the Approve snapshot.

        Both tables are read with the caller's RLS client (I-EXT-02 Decided 28/11).
        Requires the EXT-04 tables; callers enable this path only after Q05.
        """
        canonical_id, first = self._locked_session(session_id, user_id)
        links = _rows(
            self.db.table("exam_bank_rounds")
            .select(BANK_ROUND_COLUMNS)
            .eq("session_id", canonical_id)
            .execute()
        )
        snapshots: List[Dict[str, Any]] = []
        if any(link.get("is_legacy") is not True for link in links):
            snapshots = _rows(
                self.db.table("approved_exam_snapshots")
                .select(BANK_SNAPSHOT_COLUMNS)
                .eq("session_id", canonical_id)
                .execute()
            )
        self._require_unchanged(canonical_id, first)
        return BankRoundRows(session=first, links=tuple(links), snapshots=tuple(snapshots))

    def load_rows(self, session_id: str, user_id: str) -> RawSnapshotRows:
        """Return validated-by-the-builder raw rows for an owned, locked session."""
        canonical_id, first = self._locked_session(session_id, user_id)

        configs = _rows(
            self.db.table("generation_configs")
            .select("n_versions, active_variation_modes, canonical_dimensions")
            .eq("session_id", canonical_id)
            .execute()
        )
        sources = _rows(
            self.db.table("source_questions").select("id").eq("session_id", canonical_id).execute()
        )
        versions = _rows(
            self.db.table("exam_versions")
            .select("id, version_code, is_finalized, shuffle_seed, permutations")
            .eq("session_id", canonical_id)
            .execute()
        )
        version_ids = [str(v["id"]) for v in versions if v.get("id")]
        questions: List[Dict[str, Any]] = []
        keys: List[Dict[str, Any]] = []
        if version_ids:
            questions = _rows(
                self.db.table("version_questions")
                .select(
                    "id, version_id, source_question_id, question_no, canonical_question_no, "
                    "content, options, correct_key, solution_md, status, is_current, "
                    "canonical_solution_md, has_warning, regenerated_from_id, validation_report"
                )
                .in_("version_id", version_ids)
                .eq("is_current", True)
                .execute()
            )
            keys = _rows(
                self.db.table("answer_keys")
                .select(
                    "version_id, question_no, display_no, correct_option, "
                    "display_correct_key, canonical_question_no"
                )
                .in_("version_id", version_ids)
                .execute()
            )

        # All content and ownership reads above use the caller's RLS client.
        # The optional privileged client is limited to provenance for those
        # already-authorized question IDs; without it empty solutions fail closed.
        results: List[Dict[str, Any]] = []
        snapshots: List[Dict[str, Any]] = []
        empty_ids = [
            str(q["id"]) for q in questions if q.get("id") and is_empty(q.get("solution_md"))
        ]
        if empty_ids and self.provenance_db is not None:
            results = _rows(
                self.provenance_db.table("generation_target_results")
                .select(
                    "version_question_id, snapshot_id, session_id, source_question_id, "
                    "is_success, result_kind, clone_fingerprint"
                )
                .eq("session_id", canonical_id)
                .in_("version_question_id", empty_ids)
                .execute()
            )
            snapshot_ids = sorted(
                {
                    str(r["snapshot_id"])
                    for r in results
                    if r.get("result_kind") == "ORIGINAL_CLONE" and r.get("snapshot_id")
                }
            )
            if snapshot_ids:
                snapshots = _rows(
                    self.provenance_db.table("generation_job_snapshots")
                    .select("id, session_id, public_modes, canonical_dimensions")
                    .eq("session_id", canonical_id)
                    .in_("id", snapshot_ids)
                    .execute()
                )
        self._require_unchanged(canonical_id, first)

        n_versions = configs[0].get("n_versions") if len(configs) == 1 else None
        return RawSnapshotRows(
            session=first,
            n_versions=n_versions,
            source_question_ids=tuple(s.get("id") for s in sources),
            versions=tuple(versions),
            questions=tuple(questions),
            answer_keys=tuple(keys),
            generation_config=configs[0] if len(configs) == 1 else {},
            provenance_results=tuple(results),
            provenance_snapshots=tuple(snapshots),
        )

"""Q01 empty-solution exception, verified from internal persisted rows.

Matches Preview's Q01 policy; warnings alone never establish fallback origin.
No question content is read with a privileged client or accepted from HTTP input.
"""

import re
from typing import Any, Mapping

from app.services.exporter.snapshot_rows import RawSnapshotRows


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def verified_empty_solution(rows: RawSnapshotRows, question: Mapping[str, Any]) -> bool:
    if not is_empty(question.get("solution_md")) or not is_empty(
        question.get("canonical_solution_md")
    ):
        return False
    if question.get("regenerated_from_id") is not None:
        return False
    qid = str(question.get("id", ""))
    entries = [r for r in rows.provenance_results if str(r.get("version_question_id")) == qid]
    if len(entries) != 1:
        return False
    entry = entries[0]
    session_id = str(rows.session.get("id", ""))
    if (
        entry.get("is_success") is not True
        or str(entry.get("session_id", "")) != session_id
        or str(entry.get("source_question_id", "")) != str(question.get("source_question_id"))
    ):
        return False
    report = question.get("validation_report")
    if entry.get("result_kind") == "CONFIRMED_SOURCE_FALLBACK":
        return (
            question.get("has_warning") is True
            and isinstance(report, dict)
            and report.get("fallback_source") is True
            and report.get("reason") == "GENERATION_RETRIES_EXHAUSTED"
            and report.get("validation_status") == "not_validated"
            and type(report.get("attempts")) is int
            and report["attempts"] >= 1
            and all(
                isinstance(report.get(k), str) and bool(report[k].strip())
                for k in ("source_revision_id", "source_fingerprint", "confirmed_source_hash")
            )
        )
    if entry.get("result_kind") != "ORIGINAL_CLONE":
        return False
    snapshots = [
        s for s in rows.provenance_snapshots if str(s.get("id")) == str(entry.get("snapshot_id"))
    ]
    fingerprint = entry.get("clone_fingerprint")
    return (
        rows.generation_config.get("active_variation_modes") == []
        and rows.generation_config.get("canonical_dimensions") == []
        and question.get("has_warning") is False
        and (report is None or report == {})
        and isinstance(fingerprint, str)
        and re.fullmatch(r"[a-f0-9]{64}", fingerprint) is not None
        and len(snapshots) == 1
        and str(snapshots[0].get("session_id", "")) == session_id
        and snapshots[0].get("public_modes") == []
        and snapshots[0].get("canonical_dimensions") == []
    )

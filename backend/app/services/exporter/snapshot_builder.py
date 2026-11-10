"""Pure builder: validated ``ApprovedExportSnapshot`` from persisted rows (W4-MVP-07).

No database access. Every check fails closed with a ``ReviewDomainException``;
messages name the version code and slot but never include question content,
solutions, keys or raw database values.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence, cast
from uuid import UUID

from pydantic import ValidationError

from app.models.schemas import ReviewDomainException
from app.services.exporter.bundle_models import (
    ApprovedExportSnapshot,
    DisplayQuestion,
    DisplayVersion,
)
from app.services.exporter.snapshot_revision import snapshot_revision
from app.services.exporter.snapshot_rows import RawSnapshotRows

logger = logging.getLogger(__name__)

LOCKED_STATUSES = ("approved", "exported")
RevisionSource = Callable[[Mapping[str, Any], Sequence[Mapping[str, Any]]], str]


def _invalid(detail: str) -> ReviewDomainException:
    return ReviewDomainException(409, "ERR_EXPORT_SNAPSHOT_INVALID", detail)


def _keys_invalid(detail: str) -> ReviewDomainException:
    return ReviewDomainException(409, "ERR_INCONSISTENT_ANSWER_KEYS", detail)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _uuid(value: Any, what: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise _invalid(f"{what} không phải UUID hợp lệ") from exc


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def _code_order(code: str) -> tuple[int, int, str]:
    return (0, int(code), code) if code.isdigit() else (1, 0, code)


def _fields(exc: ValidationError) -> str:
    """Names of failing fields only: never the offending values."""
    names = sorted({".".join(str(part) for part in err["loc"]) or "?" for err in exc.errors()})
    return ", ".join(names)


def _check_session(session: Mapping[str, Any]) -> tuple[str, str]:
    session_id = _uuid(session.get("id"), "Mã phiên")
    if session.get("status") not in LOCKED_STATUSES:
        raise ReviewDomainException(
            409, "ERR_INVALID_SESSION_STATE", "Phiên đề chưa được phê duyệt để xuất"
        )
    if not _valid_timestamp(session.get("approved_at")):
        raise _invalid("Phiên đề đã khóa nhưng thiếu thời điểm phê duyệt hợp lệ")
    title = session.get("title")
    if not _text(title):
        raise _invalid("Phiên đề thiếu tiêu đề")
    return session_id, str(title).strip()


def _check_versions(rows: RawSnapshotRows) -> list[tuple[str, str]]:
    n = rows.n_versions
    if not _is_int(n) or not 1 <= n <= 4:
        raise _invalid("Số mã đề trong cấu hình không hợp lệ")
    if len(rows.versions) != n:
        raise _invalid("Số mã đề đã lưu không khớp cấu hình")
    seen_ids: set[str] = set()
    seen_codes: set[str] = set()
    result: list[tuple[str, str]] = []
    for version in rows.versions:
        version_id = _uuid(version.get("id"), "Mã đề")
        code = version.get("version_code")
        if not _text(code):
            raise _invalid("Mã đề thiếu version_code")
        code = str(code)
        if version_id in seen_ids or code.casefold() in seen_codes:
            raise _invalid("Mã đề bị trùng")
        seen_ids.add(version_id)
        seen_codes.add(code.casefold())
        if version.get("is_finalized") is not True:
            raise _invalid(f"Mã đề {code} chưa hoán vị xong hoặc biên nhận hoán vị đã cũ")
        if not _text(version.get("shuffle_seed")) or version.get("permutations") is None:
            raise _invalid(f"Mã đề {code} thiếu seed hoặc hoán vị đã lưu")
        result.append((version_id, code))
    return sorted(result, key=lambda item: _code_order(item[1]))


def _check_sources(rows: RawSnapshotRows) -> set[str]:
    if not rows.source_question_ids:
        raise _invalid("Phiên đề không có câu hỏi nguồn")
    sources = {_uuid(value, "Mã câu nguồn") for value in rows.source_question_ids}
    if len(sources) != len(rows.source_question_ids):
        raise _invalid("Câu hỏi nguồn bị trùng")
    return sources


def _group_questions(
    rows: RawSnapshotRows, version_ids: set[str]
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {vid: [] for vid in version_ids}
    for question in rows.questions:
        vid = _uuid(question.get("version_id"), "Mã đề của câu")
        if vid not in grouped:
            raise _invalid("Có câu hỏi thuộc mã đề ngoài phiên đề")
        grouped[vid].append(question)
    return grouped


def _index_keys(rows: RawSnapshotRows, version_ids: set[str]) -> dict[tuple[str, int], Mapping]:
    indexed: dict[tuple[str, int], Mapping[str, Any]] = {}
    for key in rows.answer_keys:
        vid = _uuid(key.get("version_id"), "Mã đề của đáp án")
        number = key.get("question_no")
        if vid not in version_ids or not _is_int(number):
            raise _keys_invalid("Bảng đáp án có dòng ngoài phạm vi hoặc sai kiểu")
        slot = (vid, cast(int, number))
        if slot in indexed:
            raise _keys_invalid("Bảng đáp án có dòng trùng")
        indexed[slot] = key
    return indexed


def _display_question(
    question: Mapping[str, Any], key: Mapping[str, Any], code: str, number: int
) -> DisplayQuestion:
    correct = question.get("correct_key")
    if (
        key.get("correct_option") != correct
        or key.get("display_correct_key") != correct
        or key.get("display_no") != number
    ):
        raise _keys_invalid(f"Đáp án bảng tra không khớp câu {number} của mã đề {code}")
    options = question.get("options")
    if not isinstance(options, list) or len(options) != 4:
        raise _invalid(f"Phương án câu {number} của mã đề {code} không hợp lệ")
    try:
        return DisplayQuestion.model_validate(
            {
                "id": question.get("id"),
                "question_no": number,
                "content": question.get("content"),
                "options": tuple(options),
                "correct_key": correct,
                "solution_md": question.get("solution_md"),
                "status": question.get("status"),
            }
        )
    except ValidationError as exc:
        raise _invalid(f"Câu {number} của mã đề {code} không hợp lệ ({_fields(exc)})") from exc


def _build_version(
    code: str,
    questions: list[Mapping[str, Any]],
    sources: set[str],
    keys: dict[tuple[str, int], Mapping[str, Any]],
    version_id: str,
) -> DisplayVersion:
    m = len(sources)
    if len(questions) != m:
        raise _invalid(f"Mã đề {code} có {len(questions)}/{m} câu hiện hành")
    if any(q.get("is_current") is not True for q in questions):
        raise _invalid(f"Mã đề {code} có câu không phải bản hiện hành")
    if {_uuid(q.get("source_question_id"), "Mã câu nguồn") for q in questions} != sources:
        raise _invalid(f"Mã đề {code} không phủ đúng một câu cho mỗi câu nguồn")
    numbers = [q.get("question_no") for q in questions]
    if not all(_is_int(n) for n in numbers) or sorted(cast(list[int], numbers)) != list(
        range(1, m + 1)
    ):
        raise _invalid(f"Thứ tự hiển thị của mã đề {code} không liền mạch từ 1 đến {m}")
    canonical = [q.get("canonical_question_no") for q in questions]
    if not all(_is_int(n) for n in canonical) or sorted(cast(list[int], canonical)) != list(
        range(1, m + 1)
    ):
        raise _invalid(f"Thứ tự gốc của mã đề {code} không hợp lệ")
    for number in range(1, m + 1):
        if (version_id, number) not in keys:
            raise _keys_invalid(f"Thiếu đáp án câu {number} của mã đề {code}")
    if sum(1 for (vid, _n) in keys if vid == version_id) != m:
        raise _keys_invalid(f"Bảng đáp án của mã đề {code} có dòng thừa")
    ordered = sorted(questions, key=lambda q: int(q["question_no"]))
    display = []
    for q in ordered:
        number = int(q["question_no"])
        key = keys[(version_id, number)]
        if key.get("canonical_question_no") != q.get("canonical_question_no"):
            raise _keys_invalid(f"Số thứ tự gốc lệch ở câu {number} của mã đề {code}")
        display.append(_display_question(q, key, code, number))
    try:
        return DisplayVersion(code=code, questions=tuple(display))
    except ValidationError as exc:
        raise _invalid(f"Mã đề {code} không hợp lệ ({_fields(exc)})") from exc


def snapshot_identity(snapshot: ApprovedExportSnapshot) -> dict[str, Any]:
    """Sanitized identity for logs: no question content, solutions or keys."""
    return {
        "session_id": str(snapshot.session_id),
        "revision": snapshot.revision,
        "status": snapshot.status,
        "versions": [version.code for version in snapshot.versions],
        "questions_per_version": len(snapshot.versions[0].questions),
    }


def build_approved_snapshot(
    rows: RawSnapshotRows, *, revision_of: RevisionSource = snapshot_revision
) -> ApprovedExportSnapshot:
    """Validate ``rows`` and return the export snapshot, or raise fail-closed."""
    session_id, title = _check_session(rows.session)
    ordered_versions = _check_versions(rows)
    sources = _check_sources(rows)
    version_ids = {vid for vid, _code in ordered_versions}
    grouped = _group_questions(rows, version_ids)
    keys = _index_keys(rows, version_ids)
    versions = tuple(
        _build_version(code, grouped[vid], sources, keys, vid) for vid, code in ordered_versions
    )
    revision = revision_of(
        {**rows.session, "id": session_id},
        [version.model_dump(mode="json") for version in versions],
    )
    try:
        snapshot = ApprovedExportSnapshot(
            session_id=UUID(session_id),
            revision=revision,
            title=title,
            status=rows.session["status"],
            versions=versions,
        )
    except ValidationError as exc:
        raise _invalid(f"Snapshot không hợp lệ ({_fields(exc)})") from exc
    logger.info("approved export snapshot built: %s", snapshot_identity(snapshot))
    return snapshot

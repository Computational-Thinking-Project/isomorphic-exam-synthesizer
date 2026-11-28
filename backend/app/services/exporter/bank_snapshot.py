"""EXT-03 G3: pick the export source of one approved round (I-EXT-02, Decided 28/11).

Round kinds, from ``public.exam_bank_rounds`` read with the caller's RLS client:

- no link row: a pre-backfill MVP session; the existing projection path is kept.
- ``is_legacy = true``: an MVP round linked by the backfill; same projection path,
  so revision, keys and artifacts stay byte-identical.
- ``is_legacy = false``: an EXT round; the only accepted source is the immutable
  ``approved_exam_snapshots`` row written by Approve. A missing or malformed
  snapshot fails closed with ``409 ERR_EXPORT_SNAPSHOT_INVALID``.

Everything here is pure: no database, no Typst. Messages name the version code or
slot but never question content, keys or raw payload values.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence
from uuid import UUID

from pydantic import ValidationError

from app.models.schemas import ReviewDomainException
from app.services.exporter.bundle_models import (
    ApprovedExportSnapshot,
    DisplayQuestion,
    DisplayVersion,
)
from app.services.exporter.print_layout import ExamMetadata
from app.services.exporter.snapshot_common import LOCKED_STATUSES, valid_timestamp
from app.services.exporter.snapshot_provenance import is_empty

PUBLIC_CODE = re.compile(r"^[0-9]{3}$")
PUBLIC_CODE_MIN, PUBLIC_CODE_MAX = 101, 999
REVISION = re.compile(r"^\S{1,128}$")
PAYLOAD_KEYS = frozenset({"session_id", "bank_item_id", "title", "metadata", "versions"})
VERSION_KEYS = frozenset({"version_id", "public_version_code", "questions"})
QUESTION_KEYS = frozenset(
    {
        "version_question_id",
        "source_question_id",
        "canonical_question_no",
        "content",
        "options",
        "correct_key",
        "solution_md",
    }
)


class RoundKind(str, Enum):
    UNLINKED = "unlinked"
    LEGACY = "legacy"
    EXT = "ext"


def _invalid(detail: str) -> ReviewDomainException:
    return ReviewDomainException(409, "ERR_EXPORT_SNAPSHOT_INVALID", detail)


def _uuid(value: Any, what: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise _invalid(f"{what} không phải UUID hợp lệ") from None


def classify_round(session_id: str, owner_id: str, links: Sequence[Mapping[str, Any]]) -> RoundKind:
    """Classify from the caller-visible link rows of exactly this session."""
    own = [row for row in links if str(row.get("session_id")) == session_id]
    if not own:
        return RoundKind.UNLINKED
    if len(own) != 1:
        raise _invalid("Phiên đề có nhiều liên kết Bank")
    link = own[0]
    if str(link.get("owner_id")) != str(owner_id):
        raise ReviewDomainException(
            403, "ERR_UNAUTHORIZED", "Người dùng không có quyền với phiên đề này"
        )
    _uuid(link.get("bank_item_id"), "Mã bộ đề")
    if link.get("is_legacy") is True:
        return RoundKind.LEGACY
    if link.get("is_legacy") is False:
        return RoundKind.EXT
    raise _invalid("Liên kết Bank thiếu cờ legacy hợp lệ")


@dataclass(frozen=True)
class BankExportSnapshot:
    """A validated EXT snapshot plus the Bank fields only G4/G5 need."""

    snapshot: ApprovedExportSnapshot
    bank_item_id: str
    metadata: ExamMetadata
    # public_version_code -> version_id, for the manifest and artifact identity.
    version_ids: Mapping[str, str] = field(default_factory=dict)
    # display question id -> source_question_id, for the R09 verifier (G2).
    source_question_ids: Mapping[str, str] = field(default_factory=dict)


def _keys(value: Any, allowed: frozenset[str], what: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(f"{what} không phải object")
    if set(value) != allowed:
        raise _invalid(f"{what} sai tập field")
    return value


def _question(
    raw: Any, position: int, code: str, verified_empty: frozenset[str]
) -> tuple[DisplayQuestion, str]:
    where = f"Mã đề {code}, câu {position}"
    q = _keys(raw, QUESTION_KEYS, where)
    qid = _uuid(q["version_question_id"], f"{where}: version_question_id")
    source_id = _uuid(q["source_question_id"], f"{where}: source_question_id")
    canonical = q["canonical_question_no"]
    if type(canonical) is not int or not 1 <= canonical <= 20:
        raise _invalid(f"{where}: canonical_question_no không hợp lệ")
    options = q["options"]
    if not isinstance(options, list) or len(options) != 4:
        raise _invalid(f"{where}: cần đúng 4 phương án")
    solution = q["solution_md"]
    if solution is not None and not isinstance(solution, str):
        raise _invalid(f"{where}: lời giải không hợp lệ")
    if is_empty(solution):
        # Empty solutions need R09 evidence from the internal verifier (G2);
        # a flag inside the payload is never trusted.
        if qid not in verified_empty:
            raise _invalid(f"{where}: thiếu lời giải chưa có bằng chứng R09")
        solution = ""
    try:
        question = DisplayQuestion.model_validate(
            {
                "id": qid,
                "question_no": position,
                "content": q["content"],
                "options": tuple(options),
                "correct_key": q["correct_key"],
                "solution_md": solution,
                "status": "approved",
            },
            context={"verified_empty_solution_ids": {UUID(qid)} if not solution else set()},
        )
    except ValidationError as exc:
        names = sorted({str(err["loc"][0]) if err["loc"] else "?" for err in exc.errors()})
        raise _invalid(f"{where}: dữ liệu không hợp lệ ({', '.join(names)})") from None
    return question, source_id


def build_bank_snapshot(
    session: Mapping[str, Any],
    snapshot_rows: Sequence[Mapping[str, Any]],
    *,
    verified_empty_ids: frozenset[str] = frozenset(),
) -> BankExportSnapshot:
    """Validate one EXT round's Approve snapshot into the export boundary model.

    ``session`` is the locked ``exam_sessions`` row already authorized by the reader.
    ``verified_empty_ids`` comes only from the server-side R09 verifier.
    """
    session_id = _uuid(session.get("id"), "Mã phiên")
    if session.get("status") not in LOCKED_STATUSES:
        raise ReviewDomainException(
            409, "ERR_INVALID_SESSION_STATE", "Phiên đề chưa được phê duyệt để xuất"
        )
    if not valid_timestamp(session.get("approved_at")):
        raise _invalid("Phiên đề đã khóa nhưng thiếu thời điểm phê duyệt hợp lệ")
    own = [row for row in snapshot_rows if str(row.get("session_id")) == session_id]
    if len(own) != 1:
        raise _invalid("Lượt EXT đã duyệt thiếu snapshot Approve")
    row = own[0]
    revision = row.get("snapshot_revision")
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise _invalid("snapshot_revision không hợp lệ")

    payload = _keys(row.get("snapshot_payload"), PAYLOAD_KEYS, "snapshot_payload")
    if _uuid(payload["session_id"], "snapshot_payload.session_id") != session_id:
        raise _invalid("Snapshot thuộc phiên khác")
    bank_item_id = _uuid(payload["bank_item_id"], "snapshot_payload.bank_item_id")
    title = payload["title"]
    if not isinstance(title, str) or not title.strip():
        raise _invalid("Snapshot thiếu tiêu đề đã khóa")
    try:
        metadata = ExamMetadata.model_validate(
            _keys(payload["metadata"], frozenset(ExamMetadata.model_fields), "metadata")
        )
    except ValidationError as exc:
        names = sorted({str(err["loc"][0]) if err["loc"] else "?" for err in exc.errors()})
        raise _invalid(f"metadata không hợp lệ ({', '.join(names)})") from None

    raw_versions = payload["versions"]
    if not isinstance(raw_versions, list) or not 1 <= len(raw_versions) <= 4:
        raise _invalid("Snapshot cần 1–4 mã đề")
    versions: list[DisplayVersion] = []
    version_ids: dict[str, str] = {}
    sources: dict[str, str] = {}
    for index, raw in enumerate(raw_versions, start=1):
        v = _keys(raw, VERSION_KEYS, f"Mã đề thứ {index}")
        code = v["public_version_code"]
        if (
            not isinstance(code, str)
            or not PUBLIC_CODE.fullmatch(code)
            or not PUBLIC_CODE_MIN <= int(code) <= PUBLIC_CODE_MAX
        ):
            raise _invalid(f"Mã đề thứ {index}: public_version_code ngoài miền 101–999")
        version_id = _uuid(v["version_id"], f"Mã đề {code}: version_id")
        if code in version_ids or version_id in version_ids.values():
            raise _invalid(f"Mã đề {code} bị trùng")
        raw_questions = v["questions"]
        if not isinstance(raw_questions, list) or not 1 <= len(raw_questions) <= 20:
            raise _invalid(f"Mã đề {code}: cần 1–20 câu")
        built = [
            _question(q, pos, code, verified_empty_ids)
            for pos, q in enumerate(raw_questions, start=1)
        ]
        if len({c["canonical_question_no"] for c in raw_questions}) != len(raw_questions):
            raise _invalid(f"Mã đề {code}: canonical_question_no bị trùng")
        for question, source_id in built:
            if str(question.id) in sources:
                raise _invalid(f"Mã đề {code}: version_question_id bị trùng")
            sources[str(question.id)] = source_id
        versions.append(DisplayVersion(code=code, questions=tuple(q for q, _ in built)))
        version_ids[code] = version_id

    versions.sort(key=lambda version: int(version.code))
    try:
        snapshot = ApprovedExportSnapshot(
            session_id=UUID(session_id),
            revision=revision,
            title=title.strip(),
            status=session["status"],
            versions=tuple(versions),
        )
    except ValidationError as exc:
        names = sorted({str(err["loc"][0]) if err["loc"] else "?" for err in exc.errors()})
        raise _invalid(f"Snapshot không nhất quán ({', '.join(names)})") from None
    return BankExportSnapshot(
        snapshot=snapshot,
        bank_item_id=bank_item_id,
        metadata=metadata,
        version_ids=dict(sorted(version_ids.items(), key=lambda kv: int(kv[0]))),
        source_question_ids=sources,
    )

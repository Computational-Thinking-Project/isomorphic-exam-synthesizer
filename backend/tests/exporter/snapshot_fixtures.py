"""Typed fixtures for the approved export snapshot adapter (W4-MVP-07).

Synthetic data only. ``golden_rows`` is a 3 questions x 2 versions session: version
101 keeps source order, version 102 permutes questions and options, so slot, key and
canonical mappings are all exercised. This is the adapter's own fixture; it is not
the preview fixture of task 05.
"""

from copy import deepcopy
from typing import Any, Callable

from app.services.exporter.snapshot_rows import RawSnapshotRows

SESSION_ID = "11111111-1111-4111-8111-111111111111"
OWNER_ID = "22222222-2222-4222-8222-222222222222"
APPROVED_AT = "2026-11-10T03:00:00+00:00"
VERSION_IDS = {
    "101": "33333333-3333-4333-8333-333333330101",
    "102": "33333333-3333-4333-8333-333333330102",
}
SOURCE_IDS = [f"44444444-4444-4444-8444-44444444000{n}" for n in (1, 2, 3)]

# (source index, options in display order, correct display key) per version slot 1..3.
_LAYOUT = {
    "101": [
        (0, ["1", "2", "3", "4"], "A"),
        (1, ["5", "6", "7", "8"], "B"),
        (2, ["9", "10", "11", "12"], "C"),
    ],
    "102": [
        (2, ["12", "9", "11", "10"], "B"),
        (0, ["4", "3", "2", "1"], "D"),
        (1, ["7", "5", "8", "6"], "A"),
    ],
}
_CANONICAL_KEY = {0: "A", 1: "B", 2: "C"}


def _qid(code: str, slot: int) -> str:
    return f"55555555-5555-4555-8555-5555{VERSION_IDS[code][-4:]}00{slot:02d}"


def golden_rows() -> dict[str, Any]:
    """Plain dict of the raw rows (mutable, deep-copied by ``mutated``)."""
    questions: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    for code, layout in _LAYOUT.items():
        for slot, (source, options, key) in enumerate(layout, start=1):
            questions.append(
                {
                    "id": _qid(code, slot),
                    "version_id": VERSION_IDS[code],
                    "source_question_id": SOURCE_IDS[source],
                    "question_no": slot,
                    "canonical_question_no": source + 1,
                    "content": f"Câu nguồn {source + 1}: tính giá trị biểu thức.",
                    "options": list(options),
                    "correct_key": key,
                    "solution_md": f"Lời giải câu nguồn {source + 1}. Đáp án {key}.",
                    "status": "approved",
                    "is_current": True,
                }
            )
            keys.append(
                {
                    "version_id": VERSION_IDS[code],
                    "question_no": slot,
                    "display_no": slot,
                    "correct_option": key,
                    "display_correct_key": key,
                    "canonical_question_no": source + 1,
                }
            )
    return {
        "session": {
            "id": SESSION_ID,
            "user_id": OWNER_ID,
            "title": "Đề kiểm tra Golden",
            "status": "approved",
            "approved_at": APPROVED_AT,
            "updated_at": APPROVED_AT,
        },
        "n_versions": 2,
        "source_question_ids": list(SOURCE_IDS),
        "versions": [
            {
                "id": VERSION_IDS[code],
                "version_code": code,
                "is_finalized": True,
                "shuffle_seed": f"seed-{code}",
                "permutations": {"questions": [s for s, _o, _k in layout]},
            }
            for code, layout in _LAYOUT.items()
        ],
        "questions": questions,
        "answer_keys": keys,
    }


def to_rows(data: dict[str, Any]) -> RawSnapshotRows:
    return RawSnapshotRows(
        session=data["session"],
        n_versions=data["n_versions"],
        source_question_ids=tuple(data["source_question_ids"]),
        versions=tuple(data["versions"]),
        questions=tuple(data["questions"]),
        answer_keys=tuple(data["answer_keys"]),
    )


def mutated(change: Callable[[dict[str, Any]], None]) -> RawSnapshotRows:
    data = deepcopy(golden_rows())
    change(data)
    return to_rows(data)


def question(data: dict[str, Any], code: str, slot: int) -> dict[str, Any]:
    return next(
        q
        for q in data["questions"]
        if q["version_id"] == VERSION_IDS[code] and q["question_no"] == slot
    )


def key_row(data: dict[str, Any], code: str, slot: int) -> dict[str, Any]:
    return next(
        k
        for k in data["answer_keys"]
        if k["version_id"] == VERSION_IDS[code] and k["question_no"] == slot
    )

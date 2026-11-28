"""EXT-03 G3: Bank link dispatch and EXT Approve snapshot reader (I-EXT-02, 28/11).

Fixture shape follows Quỳnh's Decided contract on #112 and the EXT-04 schema
rehearsal at 80134f2 (``exam_bank_rounds``). ``approved_exam_snapshots`` is not
in the rehearsal yet, so its rows are built from the Decided payload fields.
Integration against a snapshot written by a real Approve is A14/A15, still pending.
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from snapshot_fixtures import OWNER_ID, SESSION_ID, golden_rows, to_rows

from app.models.schemas import ReviewDomainException
from app.services.exporter.bank_snapshot import (
    RoundKind,
    build_bank_snapshot,
    classify_round,
)
from app.services.exporter.bundle_models import revalidate_snapshot
from app.services.exporter.export_pipeline import build_compiled_bundle
from app.services.exporter.print_layout import parse_export_config
from app.services.exporter.snapshot_adapter import load_export_source
from app.services.exporter.snapshot_builder import build_approved_snapshot

BANK_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OTHER_USER = "77777777-7777-4777-8777-777777777777"
APPROVED_AT = "2026-11-28T05:00:00+00:00"


def _uuid(n: int, prefix: str = "c") -> str:
    return f"{prefix * 8}-{prefix * 4}-4{prefix * 3}-8{prefix * 3}-{n:012d}"


def session_row(**over):
    row = {
        "id": SESSION_ID,
        "user_id": OWNER_ID,
        "title": "Kiểm tra giữa kỳ",
        "status": "approved",
        "approved_at": APPROVED_AT,
        "updated_at": APPROVED_AT,
    }
    row.update(over)
    return row


def q(vi: int, qi: int, *, solution="Lời giải.", key="A"):
    return {
        "version_question_id": _uuid(vi * 100 + qi),
        "source_question_id": _uuid(qi, "d"),
        "canonical_question_no": qi,
        "content": f"Câu {qi} của mã {vi}",
        "options": [f"P{vi}-{qi}-{x}" for x in "ABCD"],
        "correct_key": key,
        "solution_md": solution,
    }


def payload(codes=("102", "101"), n=3, **over):
    data = {
        "session_id": SESSION_ID,
        "bank_item_id": BANK_ID,
        "title": "Đề kiểm tra Toán 10",
        "metadata": {
            "school": "THPT A",
            "subject": "Toán",
            "exam_type": "Giữa kỳ",
            "grade": 10,
            "semester": 1,
            "academic_year": "2026-2027",
            "exam_date": "2026-12-01",
            "duration_minutes": 45,
        },
        "versions": [
            {
                "version_id": _uuid(vi, "e"),
                "public_version_code": code,
                "questions": [q(vi, qi) for qi in range(1, n + 1)],
            }
            for vi, code in enumerate(codes, start=1)
        ],
    }
    data.update(over)
    return data


def snap_row(data=None, **over):
    row = {
        "session_id": SESSION_ID,
        "snapshot_revision": "sha256:" + "a" * 64,
        "snapshot_payload": payload() if data is None else data,
    }
    row.update(over)
    return row


def link(is_legacy=False, **over):
    row = {
        "session_id": SESSION_ID,
        "bank_item_id": BANK_ID,
        "owner_id": OWNER_ID,
        "is_legacy": is_legacy,
    }
    row.update(over)
    return row


def code_of(exc: pytest.ExceptionInfo) -> tuple[int, str]:
    return exc.value.status_code, exc.value.error_code


# --- classify_round -------------------------------------------------------------


def test_classify_unlinked_legacy_and_ext():
    assert classify_round(SESSION_ID, OWNER_ID, []) is RoundKind.UNLINKED
    assert classify_round(SESSION_ID, OWNER_ID, [link(True)]) is RoundKind.LEGACY
    assert classify_round(SESSION_ID, OWNER_ID, [link(False)]) is RoundKind.EXT


def test_classify_ignores_rows_of_other_sessions():
    other = link(True, session_id=_uuid(1, "f"))
    assert classify_round(SESSION_ID, OWNER_ID, [other]) is RoundKind.UNLINKED


@pytest.mark.parametrize("flag", [None, "true", 1, 0])
def test_classify_rejects_non_boolean_legacy_flag(flag):
    with pytest.raises(ReviewDomainException) as exc:
        classify_round(SESSION_ID, OWNER_ID, [link(flag)])
    assert code_of(exc) == (409, "ERR_EXPORT_SNAPSHOT_INVALID")


def test_classify_rejects_foreign_owner_and_duplicates():
    with pytest.raises(ReviewDomainException) as exc:
        classify_round(SESSION_ID, OWNER_ID, [link(owner_id=OTHER_USER)])
    assert code_of(exc) == (403, "ERR_UNAUTHORIZED")
    with pytest.raises(ReviewDomainException) as exc:
        classify_round(SESSION_ID, OWNER_ID, [link(), link()])
    assert code_of(exc) == (409, "ERR_EXPORT_SNAPSHOT_INVALID")


# --- build_bank_snapshot ----------------------------------------------------------


def test_ext_snapshot_uses_public_codes_sorted_and_locked_revision():
    bank = build_bank_snapshot(session_row(), [snap_row()])
    snap = bank.snapshot
    assert [v.code for v in snap.versions] == ["101", "102"]
    assert snap.revision == "sha256:" + "a" * 64
    assert snap.title == "Đề kiểm tra Toán 10"  # title locked at Approve, not live session title
    assert bank.bank_item_id == BANK_ID
    assert list(bank.version_ids) == ["101", "102"]
    assert bank.version_ids["102"] == _uuid(1, "e")
    assert [qq.question_no for qq in snap.versions[0].questions] == [1, 2, 3]
    assert bank.metadata.grade == 10 and str(bank.metadata.exam_date) == "2026-12-01"
    assert bank.source_question_ids[_uuid(101)] == _uuid(1, "d")
    revalidate_snapshot(snap)


def test_ext_snapshot_keeps_null_metadata():
    data = payload()
    data["metadata"] = {k: None for k in data["metadata"]}
    bank = build_bank_snapshot(session_row(), [snap_row(data)])
    assert bank.metadata.model_dump() == {k: None for k in data["metadata"]}


def test_missing_snapshot_fails_closed():
    with pytest.raises(ReviewDomainException) as exc:
        build_bank_snapshot(session_row(), [])
    assert code_of(exc) == (409, "ERR_EXPORT_SNAPSHOT_INVALID")
    with pytest.raises(ReviewDomainException):
        build_bank_snapshot(session_row(), [snap_row(session_id=_uuid(1, "f"))])


def _mutate(fn):
    data = payload()
    fn(data)
    return data


INVALID = {
    "payload other session": lambda d: d.update(session_id=_uuid(9, "f")),
    "extra payload key": lambda d: d.update(public_modes=[]),
    "missing metadata key": lambda d: d["metadata"].pop("grade"),
    "bad academic year": lambda d: d["metadata"].update(academic_year="2026-2028"),
    "blank title": lambda d: d.update(title="  "),
    "code below range": lambda d: d["versions"][0].update(public_version_code="100"),
    "code leading zero": lambda d: d["versions"][0].update(public_version_code="099"),
    "code not 3 digits": lambda d: d["versions"][0].update(public_version_code="1010"),
    "duplicate code": lambda d: d["versions"][1].update(public_version_code="102"),
    "duplicate version id": lambda d: d["versions"][1].update(
        version_id=d["versions"][0]["version_id"]
    ),
    "five versions": lambda d: d.update(versions=d["versions"] * 3),
    "question count differs": lambda d: d["versions"][0]["questions"].pop(),
    "three options": lambda d: d["versions"][0]["questions"][0]["options"].pop(),
    "bad key": lambda d: d["versions"][0]["questions"][0].update(correct_key="E"),
    "duplicate canonical": lambda d: d["versions"][0]["questions"][1].update(
        canonical_question_no=1
    ),
    "extra question flag": lambda d: d["versions"][0]["questions"][0].update(
        solution_is_placeholder=False
    ),
    "duplicate options": lambda d: d["versions"][0]["questions"][0].update(
        options=["x", "x", "y", "z"]
    ),
}


@pytest.mark.parametrize("name", sorted(INVALID))
def test_malformed_payload_fails_closed(name):
    with pytest.raises(ReviewDomainException) as exc:
        build_bank_snapshot(session_row(), [snap_row(_mutate(INVALID[name]))])
    assert code_of(exc) == (409, "ERR_EXPORT_SNAPSHOT_INVALID")
    assert "Câu 1 của mã" not in exc.value.detail  # no content leaks into errors


@pytest.mark.parametrize("revision", [None, "", "has space", "x" * 129])
def test_bad_revision_fails_closed(revision):
    with pytest.raises(ReviewDomainException):
        build_bank_snapshot(session_row(), [snap_row(snapshot_revision=revision)])


def test_unlocked_session_rejected():
    with pytest.raises(ReviewDomainException) as exc:
        build_bank_snapshot(session_row(status="reviewed"), [snap_row()])
    assert code_of(exc) == (409, "ERR_INVALID_SESSION_STATE")


@pytest.mark.parametrize("solution", [None, "", "   "])
def test_empty_solution_needs_r09_evidence(solution):
    data = payload()
    data["versions"][0]["questions"][1]["solution_md"] = solution
    with pytest.raises(ReviewDomainException) as exc:
        build_bank_snapshot(session_row(), [snap_row(data)])
    assert code_of(exc) == (409, "ERR_EXPORT_SNAPSHOT_INVALID")
    qid = data["versions"][0]["questions"][1]["version_question_id"]
    bank = build_bank_snapshot(session_row(), [snap_row(data)], verified_empty_ids=frozenset({qid}))
    question = next(x for v in bank.snapshot.versions for x in v.questions if str(x.id) == qid)
    assert question.solution_md == ""
    revalidate_snapshot(bank.snapshot)  # verified-empty capability survives


def test_placeholder_text_is_not_empty_here():
    # Placeholder detection belongs to the R09 verifier (G2); the builder keeps text.
    data = payload()
    data["versions"][0]["questions"][0]["solution_md"] = "Không có lời giải cho câu hỏi này."
    build_bank_snapshot(session_row(), [snap_row(data)])


def test_ext_snapshot_feeds_configured_markdown_bundle():
    bank = build_bank_snapshot(session_row(), [snap_row()])
    config = parse_export_config({"formats": ["md"]})
    artifact = build_compiled_bundle(bank.snapshot, config=config, metadata=bank.metadata)
    assert artifact.filename == f"exam_bundle_{SESSION_ID}.zip"


# --- reader + dispatcher ------------------------------------------------------------


class Query:
    def __init__(self, client, name):
        self.client, self.name, self.filters = client, name, []

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self.filters.append((field, [value]))
        return self

    def in_(self, field, values):
        self.filters.append((field, list(values)))
        return self

    def execute(self):
        self.client.calls.append(self.name)
        rows = self.client.table_rows(self.name)
        for field, allowed in self.filters:
            rows = [r for r in rows if r.get(field) in allowed]
        return SimpleNamespace(data=deepcopy(rows))


class Client:
    def __init__(self, tables, session_changes=()):
        self.tables, self.calls = tables, []
        self.session_changes = list(session_changes)
        self.session_reads = 0

    def table(self, name):
        return Query(self, name)

    def table_rows(self, name):
        if name == "exam_sessions":
            row = dict(self.tables["exam_sessions"][0])
            if self.session_reads < len(self.session_changes):
                row.update(self.session_changes[self.session_reads])
            self.session_reads += 1
            return [row]
        return self.tables.get(name, [])


def mvp_tables(links):
    d = golden_rows()
    tables = {
        "exam_sessions": [dict(d["session"])],
        "generation_configs": [{"session_id": SESSION_ID, "n_versions": d["n_versions"]}],
        "source_questions": [{"id": s, "session_id": SESSION_ID} for s in d["source_question_ids"]],
        "exam_versions": [{"session_id": SESSION_ID, **v} for v in d["versions"]],
        "version_questions": d["questions"],
        "answer_keys": d["answer_keys"],
        "exam_bank_rounds": links,
    }
    return to_rows(d), tables


@pytest.mark.parametrize("links", [[], [link(True)]])
def test_mvp_rounds_keep_projection_and_revision(links):
    rows, tables = mvp_tables(links)
    client = Client(tables)
    source = load_export_source(client, SESSION_ID, OWNER_ID)
    assert source.kind is (RoundKind.LEGACY if links else RoundKind.UNLINKED)
    assert source.bank is None
    assert source.snapshot == build_approved_snapshot(rows)
    assert "approved_exam_snapshots" not in client.calls


def test_ext_round_reads_only_snapshot_with_caller_client():
    client = Client(
        {
            "exam_sessions": [session_row()],
            "exam_bank_rounds": [link(False)],
            "approved_exam_snapshots": [snap_row()],
        }
    )
    source = load_export_source(client, SESSION_ID, OWNER_ID)
    assert source.kind is RoundKind.EXT
    assert [v.code for v in source.snapshot.versions] == ["101", "102"]
    assert "version_questions" not in client.calls and "answer_keys" not in client.calls


def test_ext_round_without_snapshot_is_409():
    client = Client({"exam_sessions": [session_row()], "exam_bank_rounds": [link(False)]})
    with pytest.raises(ReviewDomainException) as exc:
        load_export_source(client, SESSION_ID, OWNER_ID)
    assert code_of(exc) == (409, "ERR_EXPORT_SNAPSHOT_INVALID")


def test_session_change_during_bank_read_is_409():
    client = Client(
        {
            "exam_sessions": [session_row()],
            "exam_bank_rounds": [link(False)],
            "approved_exam_snapshots": [snap_row()],
        },
        session_changes=[{}, {"updated_at": "2026-11-28T06:00:00+00:00"}],
    )
    with pytest.raises(ReviewDomainException) as exc:
        load_export_source(client, SESSION_ID, OWNER_ID)
    assert code_of(exc) == (409, "ERR_EXPORT_SNAPSHOT_INVALID")


def test_foreign_session_is_403_before_bank_read():
    client = Client({"exam_sessions": [session_row(user_id=OTHER_USER)]})
    with pytest.raises(ReviewDomainException) as exc:
        load_export_source(client, SESSION_ID, OWNER_ID)
    assert code_of(exc) == (403, "ERR_UNAUTHORIZED")
    assert client.calls == ["exam_sessions"]

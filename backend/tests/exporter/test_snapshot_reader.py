"""Reader/adapter tests with an in-memory table stub (W4-MVP-07).

The stub is read-only and is NOT a lock or transaction simulator; DB lock behaviour is
covered by the opt-in PostgreSQL suite, not here.
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from snapshot_fixtures import OWNER_ID, SESSION_ID, golden_rows, question

from app.models.schemas import ReviewDomainException
from app.services.exporter.snapshot_adapter import load_approved_export_snapshot
from app.services.exporter.snapshot_reader import ExportSnapshotReader

TABLES = {
    "exam_sessions": "session",
    "generation_configs": "config",
    "source_questions": "sources",
    "exam_versions": "versions",
    "version_questions": "questions",
    "answer_keys": "answer_keys",
}


class Query:
    def __init__(self, client, name):
        self.client, self.name = client, name
        self.filters = []

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self.filters.append(("in", field, list(values)))
        return self

    def execute(self):
        self.client.calls.append(self.name)
        rows = self.client.rows(self.name)
        for kind, field, value in self.filters:
            rows = [
                r
                for r in rows
                if (r.get(field) == value if kind == "eq" else r.get(field) in value)
            ]
        return SimpleNamespace(data=deepcopy(rows))


class Client:
    def __init__(self, data, session_overrides=None):
        self.data = data
        self.calls = []
        self.session_reads = 0
        self.session_overrides = session_overrides or []

    def rows(self, name):
        d = self.data
        if name == "exam_sessions":
            session = dict(d["session"])
            if self.session_reads < len(self.session_overrides):
                session.update(self.session_overrides[self.session_reads])
            self.session_reads += 1
            return [session]
        if name == "generation_configs":
            return [{"session_id": SESSION_ID, "n_versions": d["n_versions"]}]
        if name == "source_questions":
            return [{"id": s, "session_id": SESSION_ID} for s in d["source_question_ids"]]
        if name == "exam_versions":
            return [{**v, "session_id": SESSION_ID} for v in d["versions"]]
        if name == "version_questions":
            return d["questions"]
        if name == "answer_keys":
            return d["answer_keys"]
        raise AssertionError(name)

    def table(self, name):
        return Query(self, name)


async def _load(client, session_id=SESSION_ID, user_id=OWNER_ID):
    return await load_approved_export_snapshot(client, session_id, user_id)


async def _error(client, **kw):
    with pytest.raises(ReviewDomainException) as caught:
        await _load(client, **kw)
    return caught.value


@pytest.mark.asyncio
async def test_loads_golden_snapshot_for_the_owner():
    client = Client(golden_rows())
    snapshot = await _load(client)
    assert [v.code for v in snapshot.versions] == ["101", "102"]
    assert client.session_reads == 2  # read before and after the content tables
    assert client.calls[0] == "exam_sessions" and client.calls[-1] == "exam_sessions"


@pytest.mark.asyncio
async def test_exported_session_is_readable_with_the_same_content():
    data = golden_rows()
    exported = deepcopy(data)
    exported["session"]["status"] = "exported"
    a, b = await _load(Client(data)), await _load(Client(exported))
    assert a.revision == b.revision and b.status == "exported"


@pytest.mark.asyncio
async def test_only_current_rows_are_requested_and_used():
    data = golden_rows()
    stale = deepcopy(question(data, "101", 1))
    stale.update(id="b" * 8 + "-bbbb-4bbb-8bbb-bbbbbbbbbbbb", is_current=False, content="OLD")
    data["questions"].append(stale)
    snapshot = await _load(Client(data))
    assert all("OLD" not in q.content for v in snapshot.versions for q in v.questions)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    ["", "not-a-uuid", SESSION_ID.replace("-", ""), "{" + SESSION_ID + "}"],  # non-canonical forms
)
async def test_invalid_session_id_is_400_without_touching_the_database(bad):
    client = Client(golden_rows())
    error = await _error(client, session_id=bad)
    assert (error.status_code, error.error_code) == (400, "ERR_INVALID_SESSION_ID")
    assert client.calls == []


@pytest.mark.asyncio
async def test_unknown_session_is_404():
    client = Client(golden_rows())
    error = await _error(client, session_id="99999999-9999-4999-8999-999999999999")
    assert (error.status_code, error.error_code) == (404, "ERR_SESSION_NOT_FOUND")


@pytest.mark.asyncio
async def test_other_user_is_403_and_no_content_tables_are_read():
    client = Client(golden_rows())
    error = await _error(client, user_id="33333333-3333-4333-8333-000000000000")
    assert (error.status_code, error.error_code) == (403, "ERR_UNAUTHORIZED")
    assert client.calls == ["exam_sessions"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "generated", "reviewed", "generating"])
async def test_unlocked_session_is_409_and_content_is_not_read(status):
    data = golden_rows()
    data["session"]["status"] = status
    client = Client(data)
    error = await _error(client)
    assert (error.status_code, error.error_code) == (409, "ERR_INVALID_SESSION_STATE")
    assert client.calls == ["exam_sessions"]


@pytest.mark.asyncio
async def test_locked_status_without_approved_at_is_409_state():
    data = golden_rows()
    data["session"]["approved_at"] = None
    error = await _error(Client(data))
    assert (error.status_code, error.error_code) == (409, "ERR_INVALID_SESSION_STATE")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"status": "reviewed"},
        {"approved_at": "2026-11-10T04:00:00+00:00"},
        {"updated_at": "2026-11-10T05:00:00Z"},
    ],
)
async def test_session_changing_during_the_read_is_rejected(change):
    # first read is the normal locked row, the re-read shows a change
    client = Client(golden_rows(), session_overrides=[{}, change])
    error = await _error(client)
    assert (error.status_code, error.error_code) == (409, "ERR_EXPORT_SNAPSHOT_INVALID")


@pytest.mark.asyncio
async def test_missing_config_is_rejected_fail_closed():
    data = golden_rows()
    data["n_versions"] = None
    error = await _error(Client(data))
    assert error.error_code == "ERR_EXPORT_SNAPSHOT_INVALID"


def test_reader_returns_the_boundary_type_without_validating_content():
    data = golden_rows()
    question(data, "101", 1).update(solution_md="")  # the builder, not the reader, rejects it
    rows = ExportSnapshotReader(Client(data)).load_rows(SESSION_ID, OWNER_ID)
    assert len(rows.questions) == 6 and len(rows.answer_keys) == 6 and len(rows.versions) == 2

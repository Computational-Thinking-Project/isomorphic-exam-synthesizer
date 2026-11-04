"""Focused regressions for display-key matrices and strict approval receipts."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.schemas import ReviewDomainException
from app.services.finalize.repository import FinalizeRepository


class Tables:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.in_.return_value = query
        query.execute.return_value = SimpleNamespace(data=self.tables[name])
        return query


def data():
    return {
        "generation_configs": [{"n_versions": 2}],
        "exam_versions": [
            {"id": "one", "version_code": "101", "is_finalized": True},
            {"id": "two", "version_code": "102", "is_finalized": True},
        ],
        "source_questions": [{"id": str(i)} for i in range(3)],
        "answer_keys": [
            {"version_id": v, "question_no": n, "display_no": n,
             "correct_option": a, "display_correct_key": a}
            for v, answers in (("one", "CBA"), ("two", "DAC"))
            for n, a in enumerate(answers, 1)
        ],
    }


@pytest.mark.asyncio
async def test_matrix_uses_display_keys_for_both_versions():
    codes, rows = await FinalizeRepository(Tables(data())).fetch_matrix_raw("session")
    assert codes == ["101", "102"]
    assert {(r["version_code"], r["question_no"]): r["answer"] for r in rows} == {
        ("101", 1): "C", ("101", 2): "B", ("101", 3): "A",
        ("102", 1): "D", ("102", 2): "A", ("102", 3): "C",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["empty", "missing", "duplicate", "extra", "invalid", "alias", "source"])
async def test_matrix_rejects_incomplete_or_invalid_display_keys(case):
    tables = data()
    keys = tables["answer_keys"]
    if case == "empty":
        keys.clear()
    elif case == "missing":
        keys.pop()
    elif case == "duplicate":
        keys.append(dict(keys[0]))
    elif case == "extra":
        keys[0]["question_no"] = keys[0]["display_no"] = 4
    elif case == "invalid":
        keys[0]["correct_option"] = "E"
    elif case == "alias":
        keys[0]["display_correct_key"] = "A"
    elif case == "source":
        tables["source_questions"].clear()
    with pytest.raises(ReviewDomainException) as exc:
        await FinalizeRepository(Tables(tables)).fetch_matrix_raw("session")
    assert exc.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt", [{}, {"status": "approved"},
    {"status": "approved", "session_id": "other", "approved_at": "2026-01-01"}])
async def test_approval_rejects_malformed_receipts(receipt):
    db = MagicMock()
    db.rpc.return_value.execute.return_value.data = receipt
    with pytest.raises(ReviewDomainException) as exc:
        await FinalizeRepository(db).update_session_approved("session")
    assert exc.value.error_code == "ERR_INVALID_FINALIZATION_RECEIPT"

"""Shuffle input validation without database writes."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.schemas import ReviewDomainException
from app.services.finalize import shuffle_input
from app.services.finalize.repository import FinalizeRepository
from app.services.finalize.service import FinalizeService
from app.services.finalize.shuffle_input import prepare_shuffle
from tests.services.finalize_test_client import MockSupabaseClient


@pytest.fixture
def snapshot():
    session = str(uuid4())
    versions = [{"id": str(uuid4()), "version_code": code} for code in ("101", "102")]
    sources = [{"id": str(uuid4()), "question_no": i} for i in range(1, 4)]
    questions = [
        {
            "id": str(uuid4()),
            "version_id": v["id"],
            "source_question_id": s["id"],
            "canonical_question_no": s["question_no"],
            "content": "stem",
            "canonical_options": ["a", "b", "c", "d"],
            "canonical_correct_key": "A",
            "canonical_solution_md": "Đáp án A",
            "is_current": True,
            "status": "approved",
        }
        for v in versions
        for s in sources
    ]
    return [session, {"n_versions": 2, "ordering_preferences": {}}, versions, sources, questions]


def test_per_version_shuffle_is_deterministic_and_uses_real_ids(snapshot):
    first = prepare_shuffle(*snapshot)
    reordered = deepcopy(snapshot)
    reordered[2].reverse()
    reordered[3].reverse()
    reordered[4].reverse()
    second = prepare_shuffle(*reordered)
    assert [r.model_dump() for r in first] == [r.model_dump() for r in second]
    assert {r.version_id for r in first} == {v["id"] for v in snapshot[2]}
    assert len({r.shuffle_seed for r in first}) == 2
    for result in first:
        expected_ids = {q["id"] for q in snapshot[4] if q["version_id"] == result.version_id}
        assert {q.id for q in result.questions} == expected_ids
        assert result.total_questions == 3


def test_canonical_option_whitespace_is_preserved(snapshot):
    snapshot[4][0]["canonical_options"] = [" a ", " b", "c ", "d"]
    result = prepare_shuffle(*snapshot)
    question = next(q for r in result for q in r.questions if q.id == snapshot[4][0]["id"])
    assert question.canonical_options == [" a ", " b", "c ", "d"]
    assert sorted(question.options) == sorted(question.canonical_options)


@pytest.mark.parametrize("field", ["key", "options", "permutations", "solution"])
def test_rejects_corrupted_shuffler_result(snapshot, monkeypatch, field):
    real_shuffle = shuffle_input.shuffle_exam_version

    def corrupt(*args, **kwargs):
        result = real_shuffle(*args, **kwargs)
        question = result.questions[0]
        if field == "key":
            question.display_correct_key = "Z"
        elif field == "options":
            question.options[0] = "modified"
        elif field == "permutations":
            result.permutations["question_order"] = []
        else:
            question.solution_md = "modified"
        return result

    monkeypatch.setattr(shuffle_input, "shuffle_exam_version", corrupt)
    with pytest.raises(ReviewDomainException):
        prepare_shuffle(*snapshot)


@pytest.mark.asyncio
async def test_snapshot_reads_current_candidates_for_session(snapshot):
    session, config, versions, sources, questions = deepcopy(snapshot)
    config.update(id=str(uuid4()), session_id=session)
    for row in versions + sources:
        row["session_id"] = session
    old = deepcopy(questions[0])
    old["is_current"] = False
    client = MockSupabaseClient(
        {
            "generation_configs": [config],
            "exam_versions": versions,
            "source_questions": sources,
            "version_questions": questions + [old],
        }
    )
    result = await FinalizeRepository(client).fetch_shuffle_snapshot(session)
    assert result["config"] == config
    assert len(result["questions"]) == 6
    assert all(q["is_current"] for q in result["questions"])
    assert (
        len(
            prepare_shuffle(
                session,
                result["config"],
                result["versions"],
                result["sources"],
                result["questions"],
            )
        )
        == 2
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["valid", "empty", "wrong_session", "false_finalized", "duplicate", "missing_rpc"]
)
async def test_shuffle_rpc_receipt_fails_closed(snapshot, case):
    session, _, versions, sources, _ = snapshot
    receipt = {
        "session_id": session,
        "status": "reviewed",
        "is_finalized": True,
        "versions": [
            {
                "version_id": v["id"],
                "version_code": v["version_code"],
                "total_questions": len(sources),
            }
            for v in versions
        ],
    }
    if case == "empty":
        receipt = None
    elif case == "wrong_session":
        receipt["session_id"] = str(uuid4())
    elif case == "false_finalized":
        receipt["is_finalized"] = False
    elif case == "duplicate":
        receipt["versions"].append(receipt["versions"][0])

    class Client:
        def table(self, name):
            raise AssertionError("table fallback is forbidden")

        def rpc(self, name, params):
            assert name == "finalize_persist_shuffle"
            assert params["p_session_id"] == session
            if case == "missing_rpc":
                raise RuntimeError("PGRST202")
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=receipt))

    repo = FinalizeRepository(Client())
    if case == "valid":
        assert await repo.persist_shuffle_rpc(session, {}, versions, len(sources)) == receipt
    else:
        with pytest.raises(ReviewDomainException) as exc_info:
            await repo.persist_shuffle_rpc(session, {}, versions, len(sources))
        assert exc_info.value.error_code == (
            "ERR_SHUFFLE_UNAVAILABLE" if case == "missing_rpc" else "ERR_INVALID_SHUFFLE_RECEIPT"
        )


@pytest.mark.asyncio
async def test_shuffle_returns_only_after_writer_receipt(snapshot):
    session, config, versions, sources, questions = snapshot
    repo = MagicMock()
    repo.get_session_meta = AsyncMock(
        return_value={"id": session, "user_id": "owner", "status": "reviewed", "approved_at": None}
    )
    repo.fetch_shuffle_snapshot = AsyncMock(
        return_value={
            "config": config,
            "versions": versions,
            "sources": sources,
            "questions": questions,
        }
    )
    repo.persist_shuffle_rpc = AsyncMock(
        return_value={
            "session_id": session,
            "status": "reviewed",
            "is_finalized": True,
            "versions": [
                {
                    "version_id": v["id"],
                    "version_code": v["version_code"],
                    "total_questions": len(sources),
                }
                for v in versions
            ],
        }
    )
    with patch("app.services.finalize.service.ReviewRepository") as review:
        review.return_value.progress = AsyncMock(return_value={"ready": True})
        result = await FinalizeService(MagicMock(), repo).shuffle_session(session, "owner")
    assert result.is_finalized is True
    repo.persist_shuffle_rpc.assert_awaited_once()
    assert len(repo.persist_shuffle_rpc.await_args.args[1]["versions"]) == 2


@pytest.mark.asyncio
async def test_shuffle_writer_failure_never_returns_success(snapshot):
    session, config, versions, sources, questions = snapshot
    repo = MagicMock()
    repo.get_session_meta = AsyncMock(
        return_value={"user_id": "owner", "status": "reviewed", "approved_at": None}
    )
    repo.fetch_shuffle_snapshot = AsyncMock(
        return_value={
            "config": config,
            "versions": versions,
            "sources": sources,
            "questions": questions,
        }
    )
    repo.persist_shuffle_rpc = AsyncMock(
        side_effect=ReviewDomainException(503, "ERR_SHUFFLE_UNAVAILABLE", "unavailable")
    )
    with patch("app.services.finalize.service.ReviewRepository") as review:
        review.return_value.progress = AsyncMock(return_value={"ready": True})
        with pytest.raises(ReviewDomainException) as exc_info:
            await FinalizeService(MagicMock(), repo).shuffle_session(session, "owner")
    assert exc_info.value.error_code == "ERR_SHUFFLE_UNAVAILABLE"


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "foreign", "invalid_key", "bad_options", "bad_preferences"]
)
def test_rejects_incomplete_or_invalid_snapshot(snapshot, mutation):
    questions = snapshot[4]
    if mutation == "missing":
        questions.pop()
    elif mutation == "duplicate":
        questions.append(deepcopy(questions[0]))
    elif mutation == "foreign":
        questions[0]["source_question_id"] = str(uuid4())
    elif mutation == "invalid_key":
        questions[0]["canonical_correct_key"] = "E"
    elif mutation == "bad_options":
        questions[0]["canonical_options"] = {"A": "a", "B": "b", "C": "c", "D": "d"}
    else:
        snapshot[1]["ordering_preferences"] = {"shuffle_questions": "yes"}
    with pytest.raises(ReviewDomainException) as exc_info:
        prepare_shuffle(*snapshot)
    assert exc_info.value.error_code == "ERR_SHUFFLE_INPUT_INCOMPLETE"

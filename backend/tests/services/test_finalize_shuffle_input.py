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
    "case",
    [
        "valid",
        "empty",
        "wrong_session",
        "false_finalized",
        "duplicate",
        "missing_rpc",
        "scalar",
        "list_empty",
        "list_two",
        "versions_object",
        "version_scalar",
        "unhashable_id",
        "bool_count",
        "string_count",
        "zero_versions",
        "missing_field",
    ],
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
    elif case == "scalar":
        receipt = 1
    elif case == "list_empty":
        receipt = []
    elif case == "list_two":
        receipt = [receipt, receipt]
    elif case == "versions_object":
        receipt["versions"] = {}
    elif case == "version_scalar":
        receipt["versions"] = [1]
    elif case == "unhashable_id":
        receipt["versions"][0]["version_id"] = []
    elif case in ("bool_count", "string_count"):
        receipt["versions"][0]["total_questions"] = True if case == "bool_count" else "3"
    elif case == "zero_versions":
        receipt["versions"] = []
    elif case == "missing_field":
        del receipt["versions"][0]["version_code"]

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
    "mutation",
    [
        "missing",
        "duplicate",
        "foreign",
        "invalid_key",
        "bad_options",
        "bad_preferences",
        "unknown_pref",
        "noncurrent",
        "unapproved",
        "number",
        "key_bool",
        "short_options",
        "long_options",
        "nonstring_options",
        "missing_version",
        "duplicate_version",
        "missing_source",
        "duplicate_source",
        "duplicate_number",
        "blank_code",
        "count_bool",
    ],
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
    elif mutation == "bad_preferences":
        snapshot[1]["ordering_preferences"] = {"shuffle_questions": "yes"}
    elif mutation == "unknown_pref":
        snapshot[1]["ordering_preferences"] = {"unexpected": True}
    elif mutation == "noncurrent":
        questions[0]["is_current"] = False
    elif mutation == "unapproved":
        questions[0]["status"] = "pending_review"
    elif mutation == "number":
        questions[0]["canonical_question_no"] = 99
    elif mutation == "key_bool":
        questions[0]["canonical_correct_key"] = True
    elif mutation.endswith("options"):
        questions[0]["canonical_options"] = {
            "short_options": ["a"],
            "long_options": ["a"] * 5,
            "nonstring_options": [1, 2, 3, 4],
        }[mutation]
    elif mutation == "missing_version":
        snapshot[2].pop()
    elif mutation == "duplicate_version":
        snapshot[2][1] = deepcopy(snapshot[2][0])
    elif mutation == "missing_source":
        snapshot[3].pop()
    elif mutation == "duplicate_source":
        snapshot[3].append(deepcopy(snapshot[3][0]))
    elif mutation == "duplicate_number":
        snapshot[3][1]["question_no"] = snapshot[3][0]["question_no"]
    elif mutation == "blank_code":
        snapshot[2][0]["version_code"] = ""
    elif mutation == "count_bool":
        snapshot[1]["n_versions"] = True
    with pytest.raises(ReviewDomainException) as exc_info:
        prepare_shuffle(*snapshot)
    assert exc_info.value.error_code == "ERR_SHUFFLE_INPUT_INCOMPLETE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,stamp,ready,expected",
    [
        ("generated", None, True, 409),
        ("approved", None, True, 423),
        ("exported", None, True, 423),
        ("reviewed", "2026-11-05T00:00:00Z", True, 423),
        ("reviewed", None, False, 409),
    ],
)
async def test_shuffle_service_state_and_readiness_fail_before_writer(
    status, stamp, ready, expected
):
    repo = MagicMock()
    repo.get_session_meta = AsyncMock(
        return_value={"user_id": "owner", "status": status, "approved_at": stamp}
    )
    repo.persist_shuffle_rpc = AsyncMock()
    with patch("app.services.finalize.service.ReviewRepository") as review:
        review.return_value.progress = AsyncMock(return_value={"ready": ready})
        with pytest.raises(ReviewDomainException) as exc:
            await FinalizeService(MagicMock(), repo).shuffle_session(str(uuid4()), "owner")
    assert exc.value.status_code == expected
    repo.persist_shuffle_rpc.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,code",
    [
        (TimeoutError("timeout"), "ERR_UPSTREAM_TIMEOUT"),
        (ConnectionError("lost"), "ERR_UPSTREAM_TIMEOUT"),
        (RuntimeError("42501 permission denied"), "ERR_UNAUTHORIZED"),
        (RuntimeError("ERR_SHUFFLE_STALE_INPUT"), "ERR_SHUFFLE_STALE_INPUT"),
        (RuntimeError("ERR_SESSION_LOCKED"), "ERR_SESSION_LOCKED"),
        (RuntimeError("boom"), "ERR_SHUFFLE_TRANSACTION_FAILED"),
    ],
)
async def test_shuffle_transport_errors_have_no_table_fallback(snapshot, error, code):
    class Client:
        def rpc(self, *args):
            return SimpleNamespace(execute=lambda: (_ for _ in ()).throw(error))

        def table(self, name):
            raise AssertionError("table write fallback forbidden")

    with pytest.raises(ReviewDomainException) as exc:
        await FinalizeRepository(Client()).persist_shuffle_rpc(snapshot[0], {}, snapshot[2], 3)
    assert exc.value.error_code == code

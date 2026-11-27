"""Package 01 (EXT-01 F01-1): Reject API & Reasons Canonicalization tests (A02-01, A02-02, A02-03, A02-29)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from app.api.dependencies import get_current_user, get_service_db, get_user_db
from app.api.routes.review import get_ai_generator
from app.main import app
from app.models.schemas import (
    CurrentUser,
    RegeneratedQuestionResponse,
    RejectQuestionRequest,
    ReviewDomainException,
    ReviewReasonCode,
    ReviewSnapshotResponse,
    canonicalize_review_reasons,
)
from app.services.review.receipts import CompletionReceipt, ProgressCounts, ReservationReceipt
from app.services.review.service import ReviewService

SESSION_ID = "10000000-0000-0000-0000-000000000001"
QUESTION_ID = "40000000-0000-0000-0000-000000000001"
NEW_QUESTION_ID = "40000000-0000-0000-0000-000000000002"
USER_ID = "00000000-0000-0000-0000-000000000099"
IDEMPOTENCY_KEY = "50000000-0000-0000-0000-000000000001"
VERSION_ID = "30000000-0000-0000-0000-000000000001"

REJECT_URL = f"/api/sessions/{SESSION_ID}/questions/{QUESTION_ID}/reject"

EXPECTED_SORTED_CODES = [
    "DIFFICULTY_MISMATCH",
    "EQUIVALENT_OPTIONS",
    "INCORRECT_ANSWER",
    "INCORRECT_SOLUTION",
    "INVALID_QUESTION",
    "ISOMORPHISM_MISMATCH",
    "MULTIPLE_CORRECT_ANSWERS",
    "NO_CORRECT_ANSWER",
]


def _make_regenerated_response(
    *,
    question_id: str = NEW_QUESTION_ID,
    regenerated_from_id: str = QUESTION_ID,
) -> RegeneratedQuestionResponse:
    return RegeneratedQuestionResponse(
        question_id=question_id,
        regenerated_from_id=regenerated_from_id,
        status="pending_review",
        content="5x - 15 = 0",
        options=["x = 3", "x = -3", "x = 5", "x = -5"],
        correct_key="A",
        solution_md="5x = 15 nên x = 3. Chọn A.",
        validation_report=None,
    )


def _make_active_reservation(
    operation_id: UUID, reasons: list[ReviewReasonCode] | None = None
) -> ReservationReceipt:
    return ReservationReceipt(
        session_id=UUID(SESSION_ID),
        session_status="generated",
        replayed=False,
        operation_id=operation_id,
        question_id=UUID(QUESTION_ID),
        expires_at=datetime(2026, 11, 26, 15, 0, 0, tzinfo=timezone.utc),
        max_attempts=4,
        reasons=reasons or [],
        snapshot={"format": "confirmed_artifacts_v1"},
        operation_status="active",
        settlement=None,
    )


def _make_completion_receipt(operation_id: UUID) -> CompletionReceipt:
    return CompletionReceipt(
        session_id=UUID(SESSION_ID),
        session_status="generated",
        replayed=False,
        operation_id=operation_id,
        previous_question_id=UUID(QUESTION_ID),
        question_id=UUID(NEW_QUESTION_ID),
        api_calls_used=1,
        invalidated_version_ids=[UUID(VERSION_ID)],
        progress=ProgressCounts(
            expected_slots=1,
            current_slots=1,
            approved_slots=0,
            regenerating_slots=0,
            missing_slots=0,
            duplicate_slots=0,
            ready=False,
        ),
    )


def _make_candidate_payload() -> dict[str, Any]:
    return {
        "stem_latex": "5x - 15 = 0",
        "solution_md": "5x = 15 nên x = 3. Chọn A.",
        "options": ["x = 3", "x = -3", "x = 5", "x = -5"],
        "correct_key": "A",
        "api_calls_count": 1,
        "validation_report": {
            "is_valid": True,
            "math_verified": True,
            "requires_teacher_review": True,
            "checks": [
                {
                    "check_name": "answer_verified",
                    "passed": True,
                    "status": "verified",
                    "confidence": "sympy_verified",
                }
            ],
            "warnings": [],
        },
    }


@pytest.fixture
def review_api_overrides():
    mock_db = MagicMock()
    mock_service_db = MagicMock()
    mock_ai_generator = AsyncMock()
    owner = CurrentUser(id=USER_ID, email="teacher@example.com", access_token="test-token")

    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_user_db] = lambda: mock_db
    app.dependency_overrides[get_service_db] = lambda: mock_service_db
    app.dependency_overrides[get_ai_generator] = lambda: mock_ai_generator
    try:
        yield {
            "db": mock_db,
            "service_db": mock_service_db,
            "ai_generator": mock_ai_generator,
            "owner": owner,
        }
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Unit tests: ReviewReasonCode, canonicalize_review_reasons, RejectQuestionRequest
# ---------------------------------------------------------------------------


def test_review_reason_code_exact_eight_uppercase_members_and_sorted_order() -> None:
    members = [member.value for member in ReviewReasonCode]
    assert len(members) == 8
    assert sorted(members) == EXPECTED_SORTED_CODES
    assert ReviewReasonCode.INCORRECT_ANSWER == "INCORRECT_ANSWER"
    assert isinstance(ReviewReasonCode.INCORRECT_ANSWER, str)


def test_canonicalize_review_reasons_none_and_empty() -> None:
    assert canonicalize_review_reasons(None) == []
    assert canonicalize_review_reasons([]) == []
    assert canonicalize_review_reasons(()) == []


def test_canonicalize_review_reasons_deduplicates_and_sorts() -> None:
    result = canonicalize_review_reasons(
        [
            "INCORRECT_SOLUTION",
            ReviewReasonCode.INCORRECT_ANSWER,
            "INCORRECT_SOLUTION",
            "DIFFICULTY_MISMATCH",
            ReviewReasonCode.INCORRECT_ANSWER,
        ]
    )
    assert result == [
        ReviewReasonCode.DIFFICULTY_MISMATCH,
        ReviewReasonCode.INCORRECT_ANSWER,
        ReviewReasonCode.INCORRECT_SOLUTION,
    ]


@pytest.mark.parametrize(
    "bad_input",
    [
        "INCORRECT_ANSWER",
        b"INCORRECT_ANSWER",
        {"INCORRECT_ANSWER": True},
        [123],
        [True],
        [None],
        [{}],
    ],
)
def test_canonicalize_review_reasons_rejects_non_iterable_or_non_string_items(bad_input: Any) -> None:
    with pytest.raises(TypeError):
        canonicalize_review_reasons(bad_input)


@pytest.mark.parametrize(
    "bad_code",
    [
        ["incorrect_answer"],
        ["Incorrect_Answer"],
        ["FREE_TEXT_REASON"],
        [""],
        ["INCORRECT_ANSWER "],
    ],
)
def test_canonicalize_review_reasons_rejects_case_mismatch_and_unknown_codes(
    bad_code: list[str],
) -> None:
    with pytest.raises(ValueError):
        canonicalize_review_reasons(bad_code)


def test_reject_question_request_defaults_and_canonicalization() -> None:
    assert RejectQuestionRequest().reasons == []
    assert RejectQuestionRequest.model_validate({}).reasons == []
    assert RejectQuestionRequest.model_validate({"reasons": []}).reasons == []

    req = RejectQuestionRequest.model_validate(
        {"reasons": ["MULTIPLE_CORRECT_ANSWERS", "DIFFICULTY_MISMATCH", "MULTIPLE_CORRECT_ANSWERS"]}
    )
    assert req.reasons == [
        ReviewReasonCode.DIFFICULTY_MISMATCH,
        ReviewReasonCode.MULTIPLE_CORRECT_ANSWERS,
    ]


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"reasons": None},
        {"reasons": "INCORRECT_ANSWER"},
        {"reasons": ["incorrect_answer"]},
        {"reasons": ["Incorrect_Answer"]},
        {"reasons": ["UNKNOWN_REASON"]},
        {"reasons": [""]},
        {"reasons": [123]},
        {"reasons": [True]},
        {"reasons": [None]},
        {"reasons": [{}]},
        {"reasons": ["INCORRECT_ANSWER"], "comment": "free text"},
        {"extra_field": "unexpected"},
        [],
        ["INCORRECT_ANSWER"],
        "INCORRECT_ANSWER",
        123,
    ],
)
def test_reject_question_request_strict_validation_errors(invalid_payload: Any) -> None:
    with pytest.raises(ValidationError):
        RejectQuestionRequest.model_validate(invalid_payload)


# ---------------------------------------------------------------------------
# API tests: POST /api/sessions/{session_id}/questions/{version_question_id}/reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "content"),
    [
        ({}, None),
        ({"Content-Type": "application/json"}, b""),
        ({"Content-Type": "application/json"}, b"null"),
        ({"Content-Type": "application/json"}, b"{}"),
        ({"Content-Type": "application/json"}, b'{"reasons": []}'),
    ],
)
async def test_reject_api_optional_and_empty_bodies_canonicalize_to_empty_list(
    review_api_overrides: dict[str, Any],
    headers: dict[str, str],
    content: bytes | None,
) -> None:
    """A02-01: Omitted body, JSON null (MVP caller), {}, and {"reasons": []} map to []."""
    expected_response = _make_regenerated_response()

    with (
        patch("app.api.routes.review.assert_ownership") as mock_ownership,
        patch(
            "app.api.routes.review.ReviewService.reject_question",
            new=AsyncMock(return_value=expected_response),
        ) as mock_reject,
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                REJECT_URL,
                headers={**headers, "Idempotency-Key": IDEMPOTENCY_KEY},
                content=content,
            )

    assert resp.status_code == 200
    assert resp.json()["question_id"] == NEW_QUESTION_ID
    assert mock_ownership.call_count == 2
    mock_reject.assert_awaited_once_with(
        SESSION_ID,
        QUESTION_ID,
        USER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        reasons=[],
    )


@pytest.mark.asyncio
async def test_reject_api_allows_omitted_idempotency_key_and_mvp_null_body(
    review_api_overrides: dict[str, Any],
) -> None:
    """A02-01: MVP callers omitting Idempotency-Key and sending JSON null remain compatible."""
    expected_response = _make_regenerated_response()

    with (
        patch("app.api.routes.review.assert_ownership"),
        patch(
            "app.api.routes.review.ReviewService.reject_question",
            new=AsyncMock(return_value=expected_response),
        ) as mock_reject,
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                REJECT_URL,
                headers={"Content-Type": "application/json"},
                content=b"null",
            )

    assert resp.status_code == 200
    mock_reject.assert_awaited_once_with(
        SESSION_ID,
        QUESTION_ID,
        USER_ID,
        idempotency_key=None,
        reasons=[],
    )


@pytest.mark.asyncio
async def test_reject_api_canonicalizes_unsorted_duplicate_reasons_order_insensitively(
    review_api_overrides: dict[str, Any],
) -> None:
    """A02-02: Multiple reasons in different orders with duplicates canonicalize identically."""
    expected_response = _make_regenerated_response()

    with (
        patch("app.api.routes.review.assert_ownership"),
        patch(
            "app.api.routes.review.ReviewService.reject_question",
            new=AsyncMock(return_value=expected_response),
        ) as mock_reject,
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp_a = await client.post(
                REJECT_URL,
                json={
                    "reasons": [
                        "INCORRECT_SOLUTION",
                        "INCORRECT_ANSWER",
                        "INCORRECT_SOLUTION",
                        "DIFFICULTY_MISMATCH",
                    ]
                },
            )
            resp_b = await client.post(
                REJECT_URL,
                json={
                    "reasons": [
                        "DIFFICULTY_MISMATCH",
                        "INCORRECT_ANSWER",
                        "INCORRECT_SOLUTION",
                    ]
                },
            )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert mock_reject.await_count == 2

    expected_canonical = [
        ReviewReasonCode.DIFFICULTY_MISMATCH,
        ReviewReasonCode.INCORRECT_ANSWER,
        ReviewReasonCode.INCORRECT_SOLUTION,
    ]
    assert mock_reject.await_args_list[0].kwargs["reasons"] == expected_canonical
    assert mock_reject.await_args_list[1].kwargs["reasons"] == expected_canonical


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "content"),
    [
        ({"Content-Type": "application/json"}, b'{"reasons": null}'),
        ({"Content-Type": "application/json"}, b"[]"),
        ({"Content-Type": "application/json"}, b'["INCORRECT_ANSWER"]'),
        ({"Content-Type": "application/json"}, b'"INCORRECT_ANSWER"'),
        ({"Content-Type": "application/json"}, b"123"),
        ({"Content-Type": "application/json"}, b"true"),
        ({"Content-Type": "application/json"}, b"{not-json"),
        ({"Content-Type": "application/json"}, b"   "),
        ({"Content-Type": "application/json"}, b'{"reasons": ["FREE_TEXT"]}'),
        ({"Content-Type": "application/json"}, b'{"reasons": [""]}'),
        ({"Content-Type": "application/json"}, b'{"reasons": ["incorrect_answer"]}'),
        ({"Content-Type": "application/json"}, b'{"reasons": ["Incorrect_Answer"]}'),
        ({"Content-Type": "application/json"}, b'{"reasons": "INCORRECT_ANSWER"}'),
        ({"Content-Type": "application/json"}, b'{"reasons": [123]}'),
        ({"Content-Type": "application/json"}, b'{"reasons": [true]}'),
        ({"Content-Type": "application/json"}, b'{"reasons": [null]}'),
        ({"Content-Type": "application/json"}, b'{"reasons": [{}]}'),
        (
            {"Content-Type": "application/json"},
            b'{"reasons": ["INCORRECT_ANSWER"], "comment": "bad"}',
        ),
        ({"Content-Type": "application/json"}, b'{"unknown": true}'),
    ],
)
async def test_reject_api_invalid_payloads_return_422_before_any_side_effects(
    review_api_overrides: dict[str, Any],
    headers: dict[str, str],
    content: bytes,
) -> None:
    """A02-03 & A02-29: Invalid payloads return 422 before ownership, service, DB, or AI."""
    mock_db = review_api_overrides["db"]
    mock_service_db = review_api_overrides["service_db"]
    mock_ai_generator = review_api_overrides["ai_generator"]

    with (
        patch("app.api.routes.review.assert_ownership") as mock_ownership,
        patch("app.api.routes.review.ReviewService.reject_question", new=AsyncMock()) as mock_reject,
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                REJECT_URL,
                headers={**headers, "Idempotency-Key": IDEMPOTENCY_KEY},
                content=content,
            )

    assert resp.status_code == 422
    assert mock_ownership.call_count == 0
    assert mock_reject.call_count == 0
    assert mock_db.rpc.call_count == 0
    assert mock_db.table.call_count == 0
    assert mock_service_db.rpc.call_count == 0
    assert mock_service_db.table.call_count == 0
    assert mock_ai_generator.call_count == 0


# ---------------------------------------------------------------------------
# Service compatibility & pre-side-effect validation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call_kwargs",
    [
        {},
        {"reasons": None},
        {"reasons": ["INCORRECT_SOLUTION", "DIFFICULTY_MISMATCH", "INCORRECT_SOLUTION"]},
    ],
)
async def test_review_service_reject_question_accepts_legacy_and_canonical_reasons(
    call_kwargs: dict[str, Any],
) -> None:
    """ReviewService.reject_question preserves 4-arg callers and accepts optional reasons."""
    op_uuid = UUID(IDEMPOTENCY_KEY)
    candidate_payload = _make_candidate_payload()
    mock_ai = AsyncMock(return_value=candidate_payload)
    service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=mock_ai)

    service.repo = MagicMock()
    service.repo.verify_question_in_session = AsyncMock(return_value=True)
    service.repo.lookup_regeneration = AsyncMock(return_value=None)
    service.repo.get_session_status_and_quota = AsyncMock(
        return_value={"status": "generated", "approved_at": None}
    )
    service.repo.recover_stale_operations = AsyncMock(return_value=None)
    expected_reasons = canonicalize_review_reasons(call_kwargs.get("reasons"))
    service.repo.reserve_regeneration = AsyncMock(
        return_value=_make_active_reservation(op_uuid, reasons=expected_reasons)
    )
    service.repo.complete_regeneration = AsyncMock(return_value=_make_completion_receipt(op_uuid))
    completed = _make_active_reservation(op_uuid, reasons=expected_reasons).model_copy(update={
        "replayed": True, "operation_status": "completed",
        "settlement": _make_completion_receipt(op_uuid).model_dump(),
        "completion_candidate": candidate_payload,
    })
    service.repo.lookup_regeneration.side_effect = [None, completed]
    service.repo.acquire_attempt = AsyncMock()

    with patch(
        "app.services.review.service.frozen_inputs",
        return_value={
            "source_snapshot": {},
            "blueprint": {},
            "current_variant": {},
            "peer_variants": [],
        },
    ):
        result = await service.reject_question(
            SESSION_ID,
            QUESTION_ID,
            USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            **call_kwargs,
        )

    assert result.question_id == NEW_QUESTION_ID
    assert result.regenerated_from_id == QUESTION_ID
    service.repo.reserve_regeneration.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_reasons",
    [
        "INCORRECT_ANSWER",
        ["incorrect_answer"],
        ["UNKNOWN_CODE"],
        [123],
        {"INCORRECT_ANSWER": 1},
    ],
)
async def test_review_service_reject_question_invalid_reasons_fail_422_before_db_or_ai(
    bad_reasons: Any,
) -> None:
    """Programmatic invalid reasons fail with 422 ERR_INVALID_PAYLOAD before any DB/AI call."""
    mock_ai = AsyncMock()
    service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=mock_ai)
    service.repo = MagicMock()
    service.repo.verify_question_in_session = AsyncMock()
    service.repo.lookup_regeneration = AsyncMock()
    service.repo.get_session_status_and_quota = AsyncMock()
    service.repo.recover_stale_operations = AsyncMock()
    service.repo.reserve_regeneration = AsyncMock()

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.reject_question(
            SESSION_ID,
            QUESTION_ID,
            USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            reasons=bad_reasons,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.error_code == "ERR_INVALID_PAYLOAD"
    assert service.repo.verify_question_in_session.call_count == 0
    assert service.repo.lookup_regeneration.call_count == 0
    assert service.repo.get_session_status_and_quota.call_count == 0
    assert service.repo.recover_stale_operations.call_count == 0
    assert service.repo.reserve_regeneration.call_count == 0
    assert mock_ai.call_count == 0

@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["not_owner", "locked", "post_shuffle", "lost_snapshot", "active", "recovered"])
async def test_recovery_guard_order_and_result(review_api_overrides, scenario):
    from fastapi import HTTPException

    transitions = json.loads(
        (Path(__file__).parents[1] / "fixtures/ext01_review_transitions.json").read_text(encoding="utf-8")
    )["snapshots"]
    active = ReviewSnapshotResponse.model_validate(transitions["regenerating"])
    initial = ReviewSnapshotResponse.model_validate(transitions["initial"])
    failure = {
        "locked": ReviewDomainException(423, "ERR_SESSION_LOCKED", "locked"),
        "post_shuffle": ReviewDomainException(409, "ERR_SHUFFLE_REQUIRED", "shuffled"),
        "lost_snapshot": ReviewDomainException(503, "ERR_RESULT_UNAVAILABLE", "unavailable"),
    }.get(scenario)
    reads = [failure] if scenario in ("locked", "post_shuffle") else [
        active, failure or (active if scenario == "active" else initial)
    ]
    with (
        patch("app.api.routes.review.assert_ownership",
              side_effect=HTTPException(404) if scenario == "not_owner" else None) as owner,
        patch.object(ReviewService, "get_current_snapshot", new=AsyncMock(side_effect=reads)) as snapshot,
        patch("app.services.review.repository.ReviewRepository.recover_stale_operations",
              new=AsyncMock(return_value=int(scenario == "recovered"))) as worker,
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/sessions/{SESSION_ID}/review/recover")
    owner.assert_called_once_with("exam_sessions", SESSION_ID, USER_ID, db=review_api_overrides["db"])
    if scenario == "not_owner":
        assert response.status_code == 404
        snapshot.assert_not_awaited()
    if scenario in ("not_owner", "locked", "post_shuffle"):
        worker.assert_not_awaited()
    else:
        worker.assert_awaited_once_with(SESSION_ID)
    if failure:
        assert response.status_code == failure.status_code
    elif scenario != "not_owner":
        assert response.status_code == 200
        assert response.json()["has_active_operation"] is (scenario == "active")
        assert response.json()["recovered_count"] == int(scenario == "recovered")


def test_ext01_transition_fixture_schema_and_lineage():
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/ext01_review_transitions.json").read_text(encoding="utf-8")
    )
    snapshots = {k: ReviewSnapshotResponse.model_validate(v) for k, v in fixture["snapshots"].items()}
    assert (fixture["contract"], fixture["schema"], fixture["revision"]) == ("I-EXT-01", "ReviewSnapshotResponse", 1)
    for before, after in [("initial", "accepted"), ("regenerated", "regenerated_accepted"), ("reverted", "reverted_accepted")]:
        a, b = snapshots[before], snapshots[after]
        assert not a.progress.ready and b.progress.ready
        assert a.versions[0].slots[0].candidate.candidate_id == b.versions[0].slots[0].candidate.candidate_id
    assert snapshots["initial"].versions[0].slots[0].candidate.correct_key == "B"
    assert snapshots["regenerated"].versions[0].slots[0].candidate.correct_key == "A"


def test_compatibility_fixture_matches_frozen_policy_projection():
    from app.services.generation.mode_mapper import question_policy

    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/ext01_policy_compatibility.json").read_text(encoding="utf-8")
    )
    assert fixture["legacy_snapshot"]["mapping_version"] == "1.0"
    job = fixture["mixed_snapshot"]
    assert job["mapping_version"] == "1.1"
    frozen = job["snapshot_payload"]
    for slot, source in zip(fixture["slots"], frozen["confirmed_sources"], strict=True):
        assert slot["source_question_id"] == source["source_question_id"]
        policy = frozen["question_policies"][slot["source_question_id"]]
        assert slot["result_kind"] == policy["result_kind"]
        assert question_policy(source["canonical_blueprint"]) == policy

"""Spec-derived unit and service tests for EXT-01 Package 02 (Durable Reasons & DB Receipt).

Covers: A02-04, A02-05, A02-06, A02-07, A02-08 (Python layer), A02-19.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.models.schemas import ReviewDomainException, ReviewReasonCode
from app.services.review.receipts import ReservationReceipt, reservation_receipt
from app.services.review.repository import ReviewRepository, _map_rpc_exception
from app.services.review.service import ReviewService


def _valid_completion_settlement(
    session_id: UUID, question_id: UUID, operation_id: UUID, new_question_id: UUID
) -> dict[str, Any]:
    return {
        "session_id": str(session_id),
        "session_status": "generated",
        "replayed": False,
        "operation_id": str(operation_id),
        "previous_question_id": str(question_id),
        "question_id": str(new_question_id),
        "api_calls_used": 1,
        "invalidated_version_ids": [],
        "progress": {
            "expected_slots": 1,
            "current_slots": 1,
            "approved_slots": 0,
            "regenerating_slots": 0,
            "missing_slots": 0,
            "duplicate_slots": 0,
            "ready": False,
            "unapproved_question_ids": [str(new_question_id)],
        },
    }


def _valid_failure_settlement(
    session_id: UUID,
    question_id: UUID,
    operation_id: UUID,
    operation_status: str = "failed",
) -> dict[str, Any]:
    return {
        "session_id": str(session_id),
        "session_status": "generated",
        "operation_id": str(operation_id),
        "question_id": str(question_id),
        "operation_status": operation_status,
        "replayed": False,
        "recovered": operation_status == "recovered",
        "api_calls_used": 1,
        "progress": {
            "expected_slots": 1,
            "current_slots": 1,
            "approved_slots": 0,
            "regenerating_slots": 0,
            "missing_slots": 0,
            "duplicate_slots": 0,
            "ready": False,
            "unapproved_question_ids": [str(question_id)],
        },
    }


def _receipt_payload(
    *,
    session_id: UUID | None = None,
    question_id: UUID | None = None,
    operation_id: UUID | None = None,
    replayed: bool = False,
    operation_status: str = "active",
    settlement: dict[str, Any] | None = None,
    reasons: Any = ...,
) -> dict[str, Any]:
    sid = session_id or uuid4()
    qid = question_id or uuid4()
    op = operation_id or uuid4()
    payload: dict[str, Any] = {
        "session_id": str(sid),
        "session_status": "generated",
        "replayed": replayed,
        "operation_id": str(op),
        "question_id": str(qid),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat(),
        "max_attempts": 4,
        "snapshot": {"format": "confirmed_artifacts_v1"},
        "operation_status": operation_status,
        "settlement": settlement,
    }
    if reasons is not ...:
        payload["reasons"] = reasons
    return payload


def _valid_candidate() -> dict[str, Any]:
    return {
        "stem_latex": "Tinh gia tri cua $2 + 3$.",
        "solution_md": "Ta co $2 + 3 = 5$.",
        "options": ["3", "4", "5", "6"],
        "correct_key": "C",
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
                    "details": "ok",
                }
            ],
            "warnings": [],
        },
    }


class TestReservationReceiptReasons:
    def test_legacy_receipt_missing_reasons_defaults_to_empty(self) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        payload = _receipt_payload(session_id=sid, question_id=qid, operation_id=op)
        assert "reasons" not in payload

        receipt = ReservationReceipt.model_validate(payload)
        assert receipt.reasons == []

        parsed = reservation_receipt(payload, str(sid), str(qid), op, reasons=[])
        assert parsed.reasons == []

    def test_present_reasons_canonicalized_sorted_and_deduplicated(self) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        payload = _receipt_payload(
            session_id=sid,
            question_id=qid,
            operation_id=op,
            reasons=["INVALID_QUESTION", "DIFFICULTY_MISMATCH", "INVALID_QUESTION"],
        )
        receipt = reservation_receipt(
            payload,
            str(sid),
            str(qid),
            op,
            reasons=[ReviewReasonCode.DIFFICULTY_MISMATCH, ReviewReasonCode.INVALID_QUESTION],
        )
        assert receipt.reasons == [
            ReviewReasonCode.DIFFICULTY_MISMATCH,
            ReviewReasonCode.INVALID_QUESTION,
        ]

    @pytest.mark.parametrize(
        "bad_reasons",
        [
            None,
            "INCORRECT_ANSWER",
            b"INCORRECT_ANSWER",
            {"code": "INCORRECT_ANSWER"},
            123,
            True,
            ["incorrect_answer"],
            ["UNKNOWN_REASON"],
            [123],
            [True],
            [None],
            [b"INCORRECT_ANSWER"],
            [{}],
        ],
    )
    def test_malformed_present_reasons_fail_closed(self, bad_reasons: Any) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        payload = _receipt_payload(
            session_id=sid, question_id=qid, operation_id=op, reasons=bad_reasons
        )
        with pytest.raises(ValidationError):
            ReservationReceipt.model_validate(payload)

        with pytest.raises(ReviewDomainException) as exc_info:
            reservation_receipt(payload, str(sid), str(qid), op)
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "ERR_INVALID_RESERVATION"

    def test_reservation_receipt_rejects_reasons_mismatch(self) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        payload = _receipt_payload(
            session_id=sid,
            question_id=qid,
            operation_id=op,
            reasons=["INCORRECT_ANSWER"],
        )
        with pytest.raises(ReviewDomainException) as exc_info:
            reservation_receipt(
                payload,
                str(sid),
                str(qid),
                op,
                reasons=[ReviewReasonCode.INVALID_QUESTION],
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "ERR_INVALID_RESERVATION"

    def test_legacy_receipt_mismatch_against_non_empty_expected_reasons_fails_closed(self) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        payload = _receipt_payload(session_id=sid, question_id=qid, operation_id=op)
        with pytest.raises(ReviewDomainException) as exc_info:
            reservation_receipt(
                payload,
                str(sid),
                str(qid),
                op,
                reasons=[ReviewReasonCode.INCORRECT_ANSWER],
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "ERR_INVALID_RESERVATION"


class TestReviewRepositoryReasons:
    def test_rpc_exception_mappings_preserved(self) -> None:
        conflict = _map_rpc_exception(Exception("REVIEW_IDEMPOTENCY_CONFLICT"))
        assert conflict.status_code == 409
        assert conflict.error_code == "ERR_ATTEMPT_REPLAYED"

        invariant = _map_rpc_exception(
            Exception("REVIEW_INVARIANT_VIOLATION: malformed reservation reasons")
        )
        assert invariant.status_code == 503
        assert invariant.error_code == "ERR_REVIEW_INVARIANT_VIOLATION"

        invalid = _map_rpc_exception(Exception("REVIEW_INVALID_PAYLOAD"))
        assert invalid.status_code == 422
        assert invalid.error_code == "ERR_INVALID_PAYLOAD"

        not_found = _map_rpc_exception(Exception("REVIEW_NOT_FOUND"))
        assert not_found.status_code == 404
        assert not_found.error_code == "ERR_QUESTION_NOT_FOUND"

        locked = _map_rpc_exception(Exception("REVIEW_LOCKED"))
        assert locked.status_code == 423
        assert locked.error_code == "ERR_SESSION_LOCKED"

        stale = _map_rpc_exception(Exception("REVIEW_STALE"))
        assert stale.status_code == 409
        assert stale.error_code == "ERR_QUESTION_NOT_CURRENT"

    @pytest.mark.asyncio
    async def test_lookup_and_reserve_send_4_arg_canonical_p_reasons(self) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        rpc_calls: list[tuple[str, dict[str, Any]]] = []

        def fake_rpc(name: str, params: dict[str, Any]) -> Any:
            rpc_calls.append((name, params))
            if name == "review_lookup_regeneration":
                data: Any = {"found": False}
            else:
                data = _receipt_payload(
                    session_id=sid,
                    question_id=qid,
                    operation_id=op,
                    reasons=["DIFFICULTY_MISMATCH", "INVALID_QUESTION"],
                )
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))

        db = SimpleNamespace(rpc=fake_rpc)
        repo = ReviewRepository(db=db)  # type: ignore[arg-type]

        found = await repo.lookup_regeneration(
            str(sid),
            str(qid),
            op,
            reasons=[ReviewReasonCode.INVALID_QUESTION, "DIFFICULTY_MISMATCH", "INVALID_QUESTION"],
        )
        assert found is None

        reserved = await repo.reserve_regeneration(
            str(sid),
            str(qid),
            op,
            reasons=["INVALID_QUESTION", "DIFFICULTY_MISMATCH"],
        )
        assert reserved.reasons == [
            ReviewReasonCode.DIFFICULTY_MISMATCH,
            ReviewReasonCode.INVALID_QUESTION,
        ]
        assert rpc_calls == [
            (
                "review_lookup_regeneration",
                {
                    "p_session_id": str(sid),
                    "p_question_id": str(qid),
                    "p_operation_id": str(op),
                    "p_reasons": ["DIFFICULTY_MISMATCH", "INVALID_QUESTION"],
                },
            ),
            (
                "review_reserve_regeneration",
                {
                    "p_session_id": str(sid),
                    "p_question_id": str(qid),
                    "p_operation_id": str(op),
                    "p_reasons": ["DIFFICULTY_MISMATCH", "INVALID_QUESTION"],
                },
            ),
        ]

    @pytest.mark.asyncio
    async def test_compat_reserve_forwards_reasons(self) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        captured: list[dict[str, Any]] = []

        def fake_rpc(name: str, params: dict[str, Any]) -> Any:
            captured.append(params)
            data = _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                reasons=["INCORRECT_SOLUTION"],
            )
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))

        repo = ReviewRepository(db=SimpleNamespace(rpc=fake_rpc))  # type: ignore[arg-type]
        receipt = await repo.reserve_max_quota_and_start_regenerating(
            str(sid),
            str(qid),
            str(uuid4()),
            operation_id=op,
            reasons=["INCORRECT_SOLUTION"],
        )
        assert receipt.reasons == [ReviewReasonCode.INCORRECT_SOLUTION]
        assert captured[0]["p_reasons"] == ["INCORRECT_SOLUTION"]

    @pytest.mark.asyncio
    async def test_invalid_reasons_rejected_422_before_rpc(self) -> None:
        rpc_mock = MagicMock()
        repo = ReviewRepository(db=SimpleNamespace(rpc=rpc_mock))  # type: ignore[arg-type]

        with pytest.raises(ReviewDomainException) as exc1:
            await repo.lookup_regeneration(str(uuid4()), str(uuid4()), uuid4(), reasons=["BAD_CODE"])
        assert exc1.value.status_code == 422
        assert exc1.value.error_code == "ERR_INVALID_PAYLOAD"

        with pytest.raises(ReviewDomainException) as exc2:
            await repo.reserve_regeneration(
                str(uuid4()), str(uuid4()), uuid4(), reasons="INCORRECT_ANSWER"  # type: ignore[arg-type]
            )
        assert exc2.value.status_code == 422
        assert exc2.value.error_code == "ERR_INVALID_PAYLOAD"
        rpc_mock.assert_not_called()


class TestReviewServiceDurableReasons:
    @pytest.mark.asyncio
    async def test_invalid_reasons_rejected_before_lookup_reserve_or_ai(self) -> None:
        ai_gen = AsyncMock()
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=ai_gen)
        service.repo.lookup_regeneration = AsyncMock()  # type: ignore[method-assign]
        service.repo.reserve_regeneration = AsyncMock()  # type: ignore[method-assign]
        service.repo.verify_question_in_session = AsyncMock(return_value=True)  # type: ignore[method-assign]

        with pytest.raises(ReviewDomainException) as exc_info:
            await service.reject_question(
                str(uuid4()),
                str(uuid4()),
                str(uuid4()),
                idempotency_key=str(uuid4()),
                reasons=["NOT_A_REASON"],
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.error_code == "ERR_INVALID_PAYLOAD"
        service.repo.lookup_regeneration.assert_not_called()
        service.repo.reserve_regeneration.assert_not_called()
        ai_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_pre_reserve_lookup_and_replay_bind_canonical_reasons(self) -> None:
        sid, qid, op, new_qid = uuid4(), uuid4(), uuid4(), uuid4()
        ai_gen = AsyncMock()
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=ai_gen)
        service.repo.verify_question_in_session = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service.repo.reserve_regeneration = AsyncMock()  # type: ignore[method-assign]

        completed = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=True,
                operation_status="completed",
                settlement=_valid_completion_settlement(sid, qid, op, new_qid),
                reasons=["DIFFICULTY_MISMATCH", "INVALID_QUESTION"],
            )
        )
        service.repo.lookup_regeneration = AsyncMock(return_value=completed)  # type: ignore[method-assign]
        service.repo.load_question = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "id": str(new_qid),
                "regenerated_from_id": str(qid),
                "status": "pending_review",
                "content": "Q",
                "options": ["A", "B", "C", "D"],
                "correct_key": "A",
                "solution_md": "Sol",
                "validation_report": {
                    "is_valid": True,
                    "math_verified": True,
                    "requires_teacher_review": True,
                    "checks": [],
                    "warnings": [],
                },
            }
        )

        result = await service.reject_question(
            str(sid),
            str(qid),
            str(uuid4()),
            idempotency_key=str(op),
            reasons=["INVALID_QUESTION", "DIFFICULTY_MISMATCH", "INVALID_QUESTION"],
        )
        assert result.question_id == str(new_qid)
        service.repo.lookup_regeneration.assert_awaited_once_with(
            str(sid),
            str(qid),
            op,
            reasons=[ReviewReasonCode.DIFFICULTY_MISMATCH, ReviewReasonCode.INVALID_QUESTION],
        )
        service.repo.reserve_regeneration.assert_not_called()
        ai_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_replay_raises_409_when_receipt_reasons_differ_from_expected(self) -> None:
        sid, qid, op, new_qid = uuid4(), uuid4(), uuid4(), uuid4()
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=AsyncMock())
        completed = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=True,
                operation_status="completed",
                settlement=_valid_completion_settlement(sid, qid, op, new_qid),
                reasons=["INCORRECT_ANSWER"],
            )
        )
        with pytest.raises(ReviewDomainException) as exc_info:
            await service._replay(
                completed,
                expected_reasons=[ReviewReasonCode.INVALID_QUESTION],
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.error_code == "ERR_ATTEMPT_REPLAYED"

    @pytest.mark.asyncio
    async def test_reserve_retries_503_with_same_non_empty_reasons(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.services.review.service.asyncio.sleep", AsyncMock())
        sid, qid, op = uuid4(), uuid4(), uuid4()
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=AsyncMock())
        receipt = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=True,
                operation_status="active",
                reasons=["EQUIVALENT_OPTIONS", "INCORRECT_ANSWER"],
            )
        )
        service.repo.reserve_regeneration = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                ReviewDomainException(503, "ERR_DATABASE_UNAVAILABLE", "lost response"),
                receipt,
            ]
        )
        actual = await service._reserve_receipt(
            str(sid),
            str(qid),
            op,
            reasons=["INCORRECT_ANSWER", "EQUIVALENT_OPTIONS"],
        )
        assert actual is receipt
        assert service.repo.reserve_regeneration.await_count == 2
        for call in service.repo.reserve_regeneration.await_args_list:
            assert call.kwargs["reasons"] == [
                ReviewReasonCode.EQUIVALENT_OPTIONS,
                ReviewReasonCode.INCORRECT_ANSWER,
            ]

    @pytest.mark.asyncio
    async def test_settle_passes_reservation_reasons_on_503_reconciliation(self) -> None:
        sid, qid, op, new_qid = uuid4(), uuid4(), uuid4(), uuid4()
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=AsyncMock())
        active = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=False,
                operation_status="active",
                reasons=["INCORRECT_SOLUTION"],
            )
        )
        completed = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=True,
                operation_status="completed",
                settlement=_valid_completion_settlement(sid, qid, op, new_qid),
                reasons=["INCORRECT_SOLUTION"],
            )
        )
        service.repo.settle_failure = AsyncMock(  # type: ignore[method-assign]
            side_effect=ReviewDomainException(503, "ERR_SETTLEMENT_UNCERTAIN", "uncertain")
        )
        service.repo.lookup_regeneration = AsyncMock(return_value=completed)  # type: ignore[method-assign]

        resolved_id = await service._settle(active, "AI_TIMEOUT")
        assert resolved_id == new_qid
        service.repo.lookup_regeneration.assert_awaited_once_with(
            str(sid),
            str(qid),
            op,
            reasons=[ReviewReasonCode.INCORRECT_SOLUTION],
        )

        failed_replay = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=True,
                operation_status="failed",
                settlement=_valid_failure_settlement(sid, qid, op, "failed"),
                reasons=["INCORRECT_SOLUTION"],
            )
        )
        service.repo.lookup_regeneration = AsyncMock(return_value=failed_replay)  # type: ignore[method-assign]
        assert await service._settle(active, "AI_TIMEOUT") is None

    @pytest.mark.asyncio
    async def test_active_reservation_reasons_mismatch_fails_503_before_ai(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        ai_gen = AsyncMock()
        frozen_mock = MagicMock()
        monkeypatch.setattr("app.services.review.service.frozen_inputs", frozen_mock)

        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=ai_gen)
        service.repo.verify_question_in_session = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service.repo.lookup_regeneration = AsyncMock(return_value=None)  # type: ignore[method-assign]
        service.repo.get_session_status_and_quota = AsyncMock(  # type: ignore[method-assign]
            return_value={"status": "generated", "approved_at": None}
        )
        service.repo.recover_stale_operations = AsyncMock(return_value=0)  # type: ignore[method-assign]
        mismatched = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=False,
                operation_status="active",
                reasons=["INVALID_QUESTION"],
            )
        )
        service.repo.reserve_regeneration = AsyncMock(return_value=mismatched)  # type: ignore[method-assign]

        with pytest.raises(ReviewDomainException) as exc_info:
            await service.reject_question(
                str(sid),
                str(qid),
                str(uuid4()),
                idempotency_key=str(op),
                reasons=["INCORRECT_ANSWER"],
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "ERR_INVALID_RESERVATION"
        frozen_mock.assert_not_called()
        ai_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_keeps_ai_generator_kwargs_unchanged_in_m2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid, qid, op, new_qid = uuid4(), uuid4(), uuid4(), uuid4()
        captured_kwargs: dict[str, Any] = {}

        async def fake_ai(**kwargs: Any) -> dict[str, Any]:
            captured_kwargs.update(kwargs)
            return _valid_candidate()

        monkeypatch.setattr(
            "app.services.review.service.frozen_inputs",
            lambda receipt: {
                "source_snapshot": {"id": str(uuid4())},
                "blueprint": {"schema_version": "0.4.0"},
                "current_variant": {"id": str(qid)},
                "peer_variants": [],
            },
        )
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=fake_ai)
        service.repo.verify_question_in_session = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service.repo.lookup_regeneration = AsyncMock(return_value=None)  # type: ignore[method-assign]
        service.repo.get_session_status_and_quota = AsyncMock(  # type: ignore[method-assign]
            return_value={"status": "generated", "approved_at": None}
        )
        service.repo.recover_stale_operations = AsyncMock(return_value=0)  # type: ignore[method-assign]
        active = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=False,
                operation_status="active",
                reasons=["INCORRECT_ANSWER"],
            )
        )
        service.repo.reserve_regeneration = AsyncMock(return_value=active)  # type: ignore[method-assign]
        service.repo.complete_regeneration = AsyncMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(question_id=new_qid)
        )
        service.repo.load_question = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "id": str(new_qid),
                "regenerated_from_id": str(qid),
                "status": "pending_review",
                "content": "Tinh gia tri cua $2 + 3$.",
                "options": ["3", "4", "5", "6"],
                "correct_key": "C",
                "solution_md": "Ta co $2 + 3 = 5$.",
                "validation_report": _valid_candidate()["validation_report"],
            }
        )

        res = await service.reject_question(
            str(sid),
            str(qid),
            str(uuid4()),
            idempotency_key=str(op),
            reasons=["INCORRECT_ANSWER"],
        )
        assert res.question_id == str(new_qid)
        assert "reasons" not in captured_kwargs

    @pytest.mark.asyncio
    async def test_reserve_does_not_retry_409_conflict(self) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=AsyncMock())
        service.repo.reserve_regeneration = AsyncMock(  # type: ignore[method-assign]
            side_effect=ReviewDomainException(409, "ERR_ATTEMPT_REPLAYED", "conflict")
        )
        with pytest.raises(ReviewDomainException) as exc_info:
            await service._reserve_receipt(
                str(sid),
                str(qid),
                op,
                reasons=["INCORRECT_ANSWER"],
            )
        assert exc_info.value.status_code == 409
        assert service.repo.reserve_regeneration.await_count == 1

    @pytest.mark.asyncio
    async def test_pre_reserve_lookup_conflict_stops_before_reserve_and_ai(self) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()
        ai_gen = AsyncMock()
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=ai_gen)
        service.repo.verify_question_in_session = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service.repo.lookup_regeneration = AsyncMock(  # type: ignore[method-assign]
            side_effect=ReviewDomainException(409, "ERR_ATTEMPT_REPLAYED", "conflict")
        )
        service.repo.reserve_regeneration = AsyncMock()  # type: ignore[method-assign]

        with pytest.raises(ReviewDomainException) as exc_info:
            await service.reject_question(
                str(sid),
                str(qid),
                str(uuid4()),
                idempotency_key=str(op),
                reasons=["INCORRECT_ANSWER"],
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.error_code == "ERR_ATTEMPT_REPLAYED"
        service.repo.reserve_regeneration.assert_not_called()
        ai_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_question_settles_with_reservation_reasons_on_cancelled_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid, qid, op = uuid4(), uuid4(), uuid4()

        async def cancelled_ai(**_: Any) -> dict[str, Any]:
            raise asyncio.CancelledError()

        monkeypatch.setattr(
            "app.services.review.service.frozen_inputs",
            lambda receipt: {
                "source_snapshot": {"id": str(uuid4())},
                "blueprint": {"schema_version": "0.4.0"},
                "current_variant": {"id": str(qid)},
                "peer_variants": [],
            },
        )
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=cancelled_ai)
        service.repo.verify_question_in_session = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service.repo.lookup_regeneration = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                None,
                ReservationReceipt.model_validate(
                    _receipt_payload(
                        session_id=sid,
                        question_id=qid,
                        operation_id=op,
                        replayed=True,
                        operation_status="failed",
                        settlement=_valid_failure_settlement(sid, qid, op, "failed"),
                        reasons=["INVALID_QUESTION"],
                    )
                ),
            ]
        )
        service.repo.get_session_status_and_quota = AsyncMock(  # type: ignore[method-assign]
            return_value={"status": "generated", "approved_at": None}
        )
        service.repo.recover_stale_operations = AsyncMock(return_value=0)  # type: ignore[method-assign]
        service.repo.reserve_regeneration = AsyncMock(  # type: ignore[method-assign]
            return_value=ReservationReceipt.model_validate(
                _receipt_payload(
                    session_id=sid,
                    question_id=qid,
                    operation_id=op,
                    replayed=False,
                    operation_status="active",
                    reasons=["INVALID_QUESTION"],
                )
            )
        )
        service.repo.settle_failure = AsyncMock(  # type: ignore[method-assign]
            side_effect=ReviewDomainException(503, "ERR_SETTLEMENT_UNCERTAIN", "uncertain")
        )

        with pytest.raises(asyncio.CancelledError):
            await service.reject_question(
                str(sid),
                str(qid),
                str(uuid4()),
                idempotency_key=str(op),
                reasons=["INVALID_QUESTION"],
            )

        assert service.repo.lookup_regeneration.await_count == 2
        fallback_call = service.repo.lookup_regeneration.await_args_list[1]
        assert fallback_call.kwargs["reasons"] == [ReviewReasonCode.INVALID_QUESTION]

    @pytest.mark.asyncio
    async def test_reject_question_recovers_completed_result_via_settle_reasons_on_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid, qid, op, new_qid = uuid4(), uuid4(), uuid4(), uuid4()

        async def failing_ai(**_: Any) -> dict[str, Any]:
            raise RuntimeError("transient gateway error after server commit")

        monkeypatch.setattr(
            "app.services.review.service.frozen_inputs",
            lambda receipt: {
                "source_snapshot": {"id": str(uuid4())},
                "blueprint": {"schema_version": "0.4.0"},
                "current_variant": {"id": str(qid)},
                "peer_variants": [],
            },
        )
        service = ReviewService(db=MagicMock(), service_db=MagicMock(), ai_generator=failing_ai)
        service.repo.verify_question_in_session = AsyncMock(return_value=True)  # type: ignore[method-assign]
        completed = ReservationReceipt.model_validate(
            _receipt_payload(
                session_id=sid,
                question_id=qid,
                operation_id=op,
                replayed=True,
                operation_status="completed",
                settlement=_valid_completion_settlement(sid, qid, op, new_qid),
                reasons=["DIFFICULTY_MISMATCH", "INCORRECT_ANSWER"],
            )
        )
        service.repo.lookup_regeneration = AsyncMock(  # type: ignore[method-assign]
            side_effect=[None, completed]
        )
        service.repo.get_session_status_and_quota = AsyncMock(  # type: ignore[method-assign]
            return_value={"status": "generated", "approved_at": None}
        )
        service.repo.recover_stale_operations = AsyncMock(return_value=0)  # type: ignore[method-assign]
        service.repo.reserve_regeneration = AsyncMock(  # type: ignore[method-assign]
            return_value=ReservationReceipt.model_validate(
                _receipt_payload(
                    session_id=sid,
                    question_id=qid,
                    operation_id=op,
                    replayed=False,
                    operation_status="active",
                    reasons=["DIFFICULTY_MISMATCH", "INCORRECT_ANSWER"],
                )
            )
        )
        service.repo.settle_failure = AsyncMock(  # type: ignore[method-assign]
            side_effect=ReviewDomainException(503, "ERR_SETTLEMENT_UNCERTAIN", "uncertain")
        )
        service.repo.load_question = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "id": str(new_qid),
                "regenerated_from_id": str(qid),
                "status": "pending_review",
                "content": "Q",
                "options": ["A", "B", "C", "D"],
                "correct_key": "A",
                "solution_md": "Sol",
                "validation_report": _valid_candidate()["validation_report"],
            }
        )

        res = await service.reject_question(
            str(sid),
            str(qid),
            str(uuid4()),
            idempotency_key=str(op),
            reasons=["INCORRECT_ANSWER", "DIFFICULTY_MISMATCH"],
        )
        assert res.question_id == str(new_qid)
        fallback_call = service.repo.lookup_regeneration.await_args_list[1]
        assert fallback_call.kwargs["reasons"] == [
            ReviewReasonCode.DIFFICULTY_MISMATCH,
            ReviewReasonCode.INCORRECT_ANSWER,
        ]

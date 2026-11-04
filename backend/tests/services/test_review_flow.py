"""Caller/RPC contract tests with explicit in-memory receipts.

These drive immediate coroutines and stub scheduling, not concurrency or SQL.
No sockets, credentials, Gemini or real database are used.
"""

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.models.schemas import ReviewDomainException, SourceQuestion
from app.services.ai.gateway import GatewayError
from app.services.blueprint.adapters import source_to_item
from app.services.blueprint.service import source_fingerprint
from app.services.generation.targeted_service import TargetedRegenerator
from app.services.review import service as service_module
from app.services.review.service import ReviewService
from app.services.review.validation import frozen_inputs


def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    else:
        raise AssertionError("Unexpected scheduling in immediate contract test")
    finally:
        coroutine.close()


def counts(approved=0):
    return dict(
        expected_slots=1,
        current_slots=1,
        approved_slots=approved,
        regenerating_slots=0,
        missing_slots=0,
        duplicate_slots=0,
        ready=approved == 1,
    )


def output():
    return dict(
        stem_latex="Solve x+1=2",
        content="Solve x+1=2",
        options=["1", "2", "3", "4"],
        correct_key="A",
        solution_md="Subtract one: x=1.",
        api_calls_count=1,
        validation_report=dict(
            is_valid=True,
            math_verified=False,
            requires_teacher_review=True,
            checks=[],
            warnings=["Explicit offline fixture"],
        ),
    )


class State:
    def __init__(self):
        self.sid, self.qid, self.vid = str(uuid4()), str(uuid4()), str(uuid4())
        self.calls, self.operations, self.actions, self.attempts = [], {}, {}, {}
        self.complete_calls = self.provider_calls = self.charges = 0
        self.fail_transport = self.lost_completion = self.bad_result = False
        self.status = "generated"
        self.approved_at = None
        self.progress_data = None
        self.snapshot = self.artifacts()
        self.rows = {
            self.qid: dict(
                id=self.qid,
                version_id=self.vid,
                status="pending_review",
                is_current=True,
                is_reverted=False,
                updated_at="2026-11-04T00:00:00Z",
                exam_versions={"session_id": self.sid},
            )
        }
        self.owner = Client(self, "owner")
        self.worker = Client(self, "worker")

    def artifacts(self):
        fixture = json.loads(
            (Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8")
        )
        source = fixture["source"]
        source["content_hash"] = source_fingerprint(
            [source_to_item(SourceQuestion.model_validate(source))]
        )
        revision = str(uuid4())
        return dict(
            format="confirmed_artifacts_v1",
            source_revision_id=revision,
            blueprint_revision_id=str(uuid4()),
            blueprint_source_revision_id=revision,
            blueprint_source_fingerprint=source["content_hash"],
            source_snapshot=source,
            blueprint=fixture["blueprint"],
            current_variant=dict(
                id=self.qid,
                version_id=self.vid,
                source_question_id=source["id"],
                content="Previous candidate",
                options=["1", "2", "3", "4"],
            ),
            peer_variants=[],
        )

    def rpc(self, role, name, params):
        self.calls.append((role, name, deepcopy(params)))
        worker_names = {
            "review_complete_regeneration",
            "review_fail_regeneration",
            "review_acquire_attempt",
            "review_recover_session",
        }
        if (name in worker_names) != (role == "worker"):
            raise RuntimeError("42501 permission denied")
        if name == "review_reserve_regeneration":
            op = params["p_operation_id"]
            if op in self.operations:
                return deepcopy(self.operations[op]) | {"replayed": True}
            if self.status in ("approved", "exported") or self.approved_at is not None:
                raise RuntimeError("REVIEW_LOCKED")
            if any(record["operation_status"] == "active" for record in self.operations.values()):
                raise RuntimeError("REVIEW_BUSY")
            value = dict(
                session_id=self.sid,
                question_id=self.qid,
                operation_id=op,
                session_status="generated",
                replayed=False,
                max_attempts=4,
                expires_at=(datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat(),
                operation_status="active",
                snapshot=deepcopy(self.snapshot),
            )
            self.operations[op] = value
            return deepcopy(value)
        if name == "review_acquire_attempt":
            attempt = params["p_attempt_id"]
            replayed = attempt in self.attempts
            if not replayed:
                self.charges += 1
                self.attempts[attempt] = (params["p_operation_id"], self.charges)
            used = self.attempts[attempt][1]
            return dict(
                operation_id=params["p_operation_id"],
                attempt_id=attempt,
                dispatch_permitted=not replayed,
                replayed=replayed,
                calls_used=used,
                remaining_calls=30 - used,
            )
        if name == "review_complete_regeneration":
            self.complete_calls += 1
            op = params["p_operation_id"]
            record = self.operations[op]
            if record["operation_status"] == "completed":
                return deepcopy(record["settlement"]) | {"replayed": True}
            if record["operation_status"] != "active":
                raise RuntimeError("REVIEW_STALE")
            payload = params["p_candidate"]
            used = sum(operation == op for operation, _ in self.attempts.values())
            assert payload["api_calls_count"] == used
            qid = str(uuid4())
            self.rows[qid] = dict(
                id=qid,
                regenerated_from_id=self.qid,
                status="pending_review",
                content=payload["stem_latex"],
                **{
                    k: deepcopy(payload[k])
                    for k in ("options", "correct_key", "solution_md", "validation_report")
                },
                exam_versions={"session_id": self.sid},
            )
            result = dict(
                session_id=self.sid,
                session_status="generated",
                replayed=False,
                operation_id=op,
                previous_question_id=self.qid,
                question_id=qid,
                api_calls_used=used,
                invalidated_version_ids=[self.vid],
                progress=counts(),
            )
            record.update(operation_status="completed", settlement=deepcopy(result))
            if self.lost_completion:
                self.lost_completion = False
                raise ConnectionError("response lost after commit")
            return result
        if name == "review_fail_regeneration":
            if self.fail_transport:
                raise ConnectionError("SQL transport private detail")
            op = params["p_operation_id"]
            record = self.operations[op]
            if record["operation_status"] == "completed":
                raise RuntimeError("REVIEW_STALE")
            if record["operation_status"] == "recovered":
                raise RuntimeError("REVIEW_STALE")
            replay = record["operation_status"] == "failed"
            result = dict(
                session_id=self.sid,
                session_status="generated",
                operation_id=op,
                question_id=self.qid,
                operation_status="failed",
                recovered=False,
                replayed=replay,
                api_calls_used=sum(operation == op for operation, _ in self.attempts.values()),
                progress=counts(),
            )
            record.update(operation_status="failed", settlement=deepcopy(result))
            return result
        if name in ("review_accept_question", "review_revert_question"):
            key = params["p_action_id"]
            if key in self.actions:
                old_name, old_params, old_result = self.actions[key]
                if old_name != name or old_params != params:
                    raise RuntimeError("REVIEW_IDEMPOTENCY_CONFLICT")
                return deepcopy(old_result) | {"replayed": True}
            if self.status in ("approved", "exported") or self.approved_at is not None:
                raise RuntimeError("REVIEW_LOCKED")
            self.rows[self.qid].update(
                status="approved", is_reverted=name == "review_revert_question"
            )
            result = dict(
                session_id=self.sid,
                session_status="reviewed",
                replayed=False,
                previous_question_id=self.qid,
                question_id=self.qid,
                question_status="approved",
                invalidated_version_ids=[],
                progress=counts(1),
            )
            self.actions[key] = (name, deepcopy(params), deepcopy(result))
            return result
        if name == "review_recover_session":
            recovered = []
            for op, record in self.operations.items():
                if record["operation_status"] == "active" and datetime.fromisoformat(
                    record["expires_at"]
                ) < datetime.now(timezone.utc):
                    result = dict(
                        session_id=self.sid,
                        session_status="generated",
                        operation_id=op,
                        question_id=self.qid,
                        operation_status="recovered",
                        replayed=False,
                        recovered=True,
                        api_calls_used=sum(
                            operation == op for operation, _ in self.attempts.values()
                        ),
                        progress=counts(),
                    )
                    record.update(operation_status="recovered", settlement=result)
                    recovered.append(result)
            return dict(
                session_id=self.sid,
                session_status="generated",
                recovered_count=len(recovered),
                recoveries=recovered,
            )
        if name == "review_get_progress":
            return deepcopy(self.progress_data)
        raise AssertionError(name)

    async def provider(self, **kwargs):
        assert not service_module.session_lock_registry.get_lock(UUID(self.sid)).locked()
        self.provider_calls += 1
        await kwargs["acquire_attempt"](kwargs["operation_id"], uuid4())
        return output()

    def service(self, provider=None):
        return ReviewService(self.owner, self.worker, ai_generator=provider or self.provider)


class Query:
    def __init__(self, state, table):
        self.state, self.table, self.filters = state, table, {}

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_):
        return self

    def execute(self):
        if self.table == "exam_sessions":
            return SimpleNamespace(
                data=[
                    dict(
                        id=self.state.sid,
                        status=self.state.status,
                        approved_at=self.state.approved_at,
                        user_id="owner",
                        gemini_review_calls=self.state.charges,
                    )
                ]
                if self.filters.get("id") == self.state.sid
                else []
            )
        row = self.state.rows.get(self.filters.get("id"))
        if self.state.bad_result and row and row.get("regenerated_from_id"):
            raise ConnectionError("read failed after commit")
        return SimpleNamespace(
            data=[deepcopy(row)]
            if row and self.filters.get("exam_versions.session_id") == self.state.sid
            else []
        )


class Client:
    def __init__(self, state, role):
        self.state, self.role = state, role

    def rpc(self, name, params):
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(data=self.state.rpc(self.role, name, params))
        )

    def table(self, table):
        assert table in ("version_questions", "exam_sessions"), (
            "No source/Blueprint/ledger table fallback allowed"
        )
        return Query(self.state, table)


@pytest.fixture
def state(monkeypatch):
    async def wait_for(coroutine, **_):
        return await coroutine

    async def sleep(_):
        pass

    async def shield(coroutine):
        return await coroutine

    monkeypatch.setattr(service_module.asyncio, "wait_for", wait_for)
    monkeypatch.setattr(service_module.asyncio, "sleep", sleep)
    monkeypatch.setattr(service_module.asyncio, "shield", shield)
    return State()


def test_success_uses_frozen_receipt_and_worker_permit(state):
    result = immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert result.question_id != state.qid and result.validation_report["math_verified"] is False
    assert state.charges == state.provider_calls == state.complete_calls == 1
    assert not any(name == "review_fail_regeneration" for _, name, _ in state.calls)


def test_real_targeted_callable_uses_frozen_source_and_durable_permit(state):
    seen = []

    async def generate(source, blueprint, *, confirmed_source_hash, context, excluded_identities):
        seen.append((source.model_dump(), deepcopy(blueprint), confirmed_source_hash))
        assert excluded_identities
        await context.reserve_request()
        payload = output()
        return SimpleNamespace(
            candidate=SimpleNamespace(
                question_text=payload["stem_latex"],
                options=payload["options"],
                correct_key=payload["correct_key"],
                solution_md=payload["solution_md"],
            ),
            validation=SimpleNamespace(failures=[], checks=[]),
        )

    adapter = TargetedRegenerator(SimpleNamespace(regenerate_from_snapshots=generate))
    result = immediate(state.service(adapter).reject_question(state.sid, state.qid, "owner"))
    assert result.question_id in state.rows
    assert len(seen) == 1 and state.charges == state.complete_calls == 1
    assert seen[0][0]["id"] == state.snapshot["source_snapshot"]["id"]
    assert seen[0][1] == state.snapshot["blueprint"]
    assert seen[0][2] == state.snapshot["source_snapshot"]["content_hash"]
    assert result.validation_report["math_verified"] is False
    assert result.validation_report["requires_teacher_review"] is True


def test_real_targeted_callable_denied_permit_settles_without_completion(state):
    original = state.rpc

    def deny(role, name, params):
        if name == "review_acquire_attempt":
            state.calls.append((role, name, deepcopy(params)))
            return dict(
                operation_id=params["p_operation_id"],
                attempt_id=params["p_attempt_id"],
                dispatch_permitted=False,
                replayed=False,
                calls_used=30,
                remaining_calls=0,
            )
        return original(role, name, params)

    async def generate(source, blueprint, *, confirmed_source_hash, context, excluded_identities):
        try:
            await context.reserve_request()
        except GatewayError as exc:
            # GenerationService reports a failed QuestionResult at its gateway
            # boundary; the adapter translates that public result, not a raw
            # gateway exception escaping an artificial generation stub.
            return SimpleNamespace(candidate=None, validation=None, error_code=exc.code)
        raise AssertionError("Denied permit must stop generation")

    state.rpc = deny
    adapter = TargetedRegenerator(SimpleNamespace(regenerate_from_snapshots=generate))
    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service(adapter).reject_question(state.sid, state.qid, "owner", key))
    assert error.value.status_code == 429
    assert state.charges == state.complete_calls == 0
    assert state.operations[key]["operation_status"] == "failed"


def test_lost_completion_response_retries_same_candidate_without_ai(state):
    state.lost_completion = True
    result = immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert result.question_id in state.rows
    assert state.complete_calls == 2 and state.charges == state.provider_calls == 1
    payloads = [p for _, n, p in state.calls if n == "review_complete_regeneration"]
    assert payloads[0] == payloads[1]


def test_reservation_transport_failure_before_commit_retries_original_ids(state):
    original = state.rpc
    reservations = []

    def fail_once(role, name, params):
        if name == "review_reserve_regeneration":
            reservations.append(deepcopy(params))
            if len(reservations) == 1:
                raise ConnectionError("connection lost before commit")
        return original(role, name, params)

    state.rpc = fail_once
    result = immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert result.question_id in state.rows
    assert len(reservations) == 2 and reservations[0] == reservations[1]
    assert state.provider_calls == state.charges == 1


@pytest.mark.parametrize("damage", ["transport", "identity", "empty", "multiple"])
def test_uncertain_committed_reservation_reconciles_without_dispatch_or_failure(state, damage):
    original = state.rpc
    reservations = []

    def damaged_once(role, name, params):
        result = original(role, name, params)
        if name == "review_reserve_regeneration":
            reservations.append(deepcopy(params))
            if len(reservations) == 1:
                if damage == "transport":
                    raise ConnectionError("response lost after reservation commit")
                if damage == "identity":
                    return result | {"operation_id": str(uuid4())}
                if damage == "empty":
                    return {}
                return [result, result]
        return result

    state.rpc = damaged_once
    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    assert error.value.error_code == "ERR_QUESTION_BUSY"
    assert len(reservations) == 2 and reservations[0] == reservations[1]
    assert state.operations[key]["operation_status"] == "active"
    assert state.provider_calls == state.complete_calls == state.charges == 0
    assert not any(name == "review_fail_regeneration" for _, name, _ in state.calls)


def test_all_reservation_responses_lost_preserve_unknown_outcome_and_original_key(state):
    original = state.rpc

    def lose_all(role, name, params):
        result = original(role, name, params)
        if name == "review_reserve_regeneration":
            raise ConnectionError("secret transport detail")
        return result

    state.rpc = lose_all
    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    assert error.value.error_code == "ERR_RESERVATION_UNCERTAIN"
    assert "secret" not in str(error.value)
    requests = [p for _, n, p in state.calls if n == "review_reserve_regeneration"]
    assert len(requests) == 3 and all(p == requests[0] for p in requests)
    assert state.operations[key]["operation_status"] == "active"
    assert state.provider_calls == state.charges == 0
    assert not any(n == "review_fail_regeneration" for _, n, _ in state.calls)


def test_deterministic_reservation_error_is_not_retried(state):
    state.status = "approved"
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert error.value.status_code == 423
    assert sum(n == "review_reserve_regeneration" for _, n, _ in state.calls) == 1
    assert state.provider_calls == 0 and not state.operations


def test_all_completion_responses_lost_reconcile_receipt_without_failure_write(state):
    original = state.rpc

    def lose_response(role, name, params):
        result = original(role, name, params)
        if name == "review_complete_regeneration":
            raise ConnectionError("completion response lost")
        return result

    state.rpc = lose_response
    result = immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert result.question_id in state.rows
    assert state.complete_calls == 3 and state.provider_calls == state.charges == 1
    assert next(iter(state.operations.values()))["operation_status"] == "completed"


def test_late_completion_cannot_replace_new_operation(state):
    newer = str(uuid4())

    async def late_provider(**kwargs):
        result = await state.provider(**kwargs)
        old = str(kwargs["operation_id"])
        state.operations[old]["expires_at"] = "2000-01-01T00:00:00+00:00"
        immediate(state.service().repo.recover_stale_operations(state.sid))
        immediate(state.service().repo.reserve_regeneration(state.sid, state.qid, UUID(newer)))
        return result

    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service(late_provider).reject_question(state.sid, state.qid, "owner", key))
    assert error.value.status_code == 409
    assert state.operations[key]["operation_status"] == "recovered"
    assert state.operations[newer]["operation_status"] == "active"
    assert len(state.rows) == 1 and state.charges == 1


def test_completed_reservation_replays_after_expiry_and_approval(state):
    key = str(uuid4())
    first = immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    state.status = "approved"
    state.operations[key]["expires_at"] = "2000-01-01T00:00:00Z"
    replay = immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    assert replay.question_id == first.question_id and state.provider_calls == 1


def test_active_replay_does_not_start_another_generator(state):
    key = uuid4()
    immediate(state.service().repo.reserve_regeneration(state.sid, state.qid, key))
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", str(key)))
    assert error.value.status_code == 409 and state.provider_calls == 0


def test_legacy_snapshot_fails_before_permit_and_is_settled(state):
    state.snapshot["format"] = "database_rows"
    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    assert error.value.status_code == 422
    assert (
        state.charges == state.provider_calls == 0
        and state.operations[key]["operation_status"] == "failed"
    )


def test_invalid_output_is_settled_without_fabricated_report(state):
    async def provider(**kwargs):
        result = await state.provider(**kwargs)
        result.pop("validation_report")
        return result

    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service(provider).reject_question(state.sid, state.qid, "owner", key))
    assert error.value.status_code == 422 and state.complete_calls == 0
    assert state.charges == 1 and state.operations[key]["operation_status"] == "failed"
    assert [p["p_error_code"] for _, n, p in state.calls if n == "review_fail_regeneration"] == [
        "AI_INVALID_OUTPUT"
    ]


def test_uncertain_failure_does_not_claim_rollback(state):
    state.snapshot["format"] = "database_rows"
    state.fail_transport = True
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert error.value.error_code == "ERR_SETTLEMENT_UNCERTAIN"
    assert next(iter(state.operations.values()))["operation_status"] == "active"


def test_read_failure_after_commit_does_not_failure_settle(state):
    state.bad_result = True
    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    assert error.value.error_code == "ERR_RESULT_UNAVAILABLE"
    assert state.operations[key]["operation_status"] == "completed"
    assert not any(n == "review_fail_regeneration" for _, n, _ in state.calls)


def test_cancellation_is_preserved_after_settlement(state):
    async def cancelled(**_):
        raise asyncio.CancelledError()

    key = str(uuid4())
    with pytest.raises(asyncio.CancelledError):
        immediate(state.service(cancelled).reject_question(state.sid, state.qid, "owner", key))
    assert state.operations[key]["operation_status"] == "failed"


@pytest.mark.parametrize("action", ["accept_question", "revert_question"])
def test_action_replay_uses_same_key_even_after_session_is_locked(state, action):
    key = str(uuid4())
    first = immediate(getattr(state.service(), action)(state.sid, state.qid, "owner", key))
    state.status = "approved"
    replay = immediate(getattr(state.service(), action)(state.sid, state.qid, "owner", key))
    assert first == replay and len(state.actions) == 1
    with pytest.raises(ReviewDomainException) as error:
        immediate(getattr(state.service(), action)(state.sid, state.qid, "owner", str(uuid4())))
    assert error.value.status_code == 423


def test_action_key_cannot_be_rebound_to_another_action(state):
    key = str(uuid4())
    immediate(state.service().accept_question(state.sid, state.qid, "owner", key))
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().revert_question(state.sid, state.qid, "owner", key))
    assert error.value.status_code == 409 and len(state.actions) == 1


@pytest.mark.parametrize("action", ["accept_question", "revert_question", "reject_question"])
def test_invalid_key_never_reaches_rpc(state, action):
    with pytest.raises(ReviewDomainException) as error:
        immediate(getattr(state.service(), action)(state.sid, state.qid, "owner", "invalid"))
    assert error.value.status_code == 400 and state.calls == []


def test_snapshot_validation_does_not_mutate_stored_receipt(state):
    key = uuid4()
    reservation = immediate(state.service().repo.reserve_regeneration(state.sid, state.qid, key))
    before = deepcopy(reservation.snapshot)
    inputs = frozen_inputs(reservation)
    inputs["source_snapshot"]["options"][0] = "changed"
    assert reservation.snapshot == before


@pytest.mark.parametrize(
    "field", ["source_revision_id", "blueprint_source_fingerprint", "blueprint"]
)
def test_missing_artifact_fails_before_generation_and_settles(state, field):
    state.snapshot.pop(field)
    key = str(uuid4())
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", key))
    assert error.value.status_code == 422 and state.provider_calls == 0
    assert state.operations[key]["operation_status"] == "failed"


def test_busy_same_question_recovers_expired_operation_without_ledger_scan(state):
    old = uuid4()
    immediate(state.service().repo.reserve_regeneration(state.sid, state.qid, old))
    state.operations[str(old)]["expires_at"] = "2000-01-01T00:00:00+00:00"
    state.charges = 1
    state.attempts[str(uuid4())] = (str(old), 1)
    result = immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert result.question_id in state.rows
    assert state.operations[str(old)]["operation_status"] == "recovered"
    assert state.charges == 2 and state.provider_calls == 1
    assert sum(n == "review_recover_session" for _, n, _ in state.calls) == 1


def test_unexpired_busy_operation_is_not_force_recovered(state):
    old = uuid4()
    immediate(state.service().repo.reserve_regeneration(state.sid, state.qid, old))
    with pytest.raises(ReviewDomainException) as error:
        immediate(state.service().reject_question(state.sid, state.qid, "owner", str(uuid4())))
    assert error.value.status_code == 409
    assert state.operations[str(old)]["operation_status"] == "active" and state.provider_calls == 0


@pytest.mark.parametrize("action", ["accept", "revert"])
def test_action_handlers_forward_header_to_actual_rpc(state, monkeypatch, action):
    from app.api.routes import review

    monkeypatch.setattr(review, "assert_ownership", lambda *args, **kwargs: None)
    key = str(uuid4())
    handler = getattr(review, f"{action}_question_endpoint")
    result = immediate(
        handler(
            session_id=state.sid,
            version_question_id=state.qid,
            idempotency_key=key,
            current_user=SimpleNamespace(id="owner"),
            db=state.owner,
        )
    )
    assert result.question_id == state.qid
    assert state.calls[-1][2]["p_action_id"] == key


@pytest.mark.parametrize("action", ["accept", "revert", "reject"])
def test_action_handlers_reject_bad_key_before_ownership_or_rpc(state, monkeypatch, action):
    from app.api.routes import review

    monkeypatch.setattr(
        review,
        "assert_ownership",
        lambda *args, **kwargs: pytest.fail("invalid key reached ownership query"),
    )
    kwargs = dict(
        session_id=state.sid,
        version_question_id=state.qid,
        idempotency_key="",
        current_user=SimpleNamespace(id="owner"),
        db=state.owner,
    )
    if action == "reject":
        kwargs.update(service_db=state.worker, ai_generator=state.provider)
    with pytest.raises(ReviewDomainException) as error:
        immediate(getattr(review, f"{action}_question_endpoint")(**kwargs))
    assert error.value.status_code == 400 and state.calls == []


def test_openapi_documents_optional_key_for_all_mutations():
    from fastapi import FastAPI

    from app.api.routes import review

    app = FastAPI()
    app.include_router(review.router, prefix="/api/sessions")
    paths = app.openapi()["paths"]
    for action in ("accept", "reject", "revert"):
        parameters = paths[
            f"/api/sessions/{{session_id}}/questions/{{version_question_id}}/{action}"
        ]["post"]["parameters"]
        header = next(p for p in parameters if p["name"] == "Idempotency-Key")
        assert header["in"] == "header" and header["required"] is False

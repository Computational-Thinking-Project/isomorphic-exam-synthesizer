"""Offline RPC contract checks; live PostgREST/RLS remains a separate gate."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.generation import (
    CandidatePayload,
    GeneratedQuestion,
    QuestionResult,
    ValidationReport,
    render_solution,
)
from app.services.generation.ai_mapping import PreparedAIResult
from app.services.generation.events import GenerationEventBroker
from app.services.generation.job_contracts import GeneratedDraft
from app.services.generation.job_repository import CloneJobInputs, GenerationJobRepository
from app.services.generation.jobs import GenerationJobRunner
from app.services.observability.runtime_registry import RuntimeRegistry


class FakeRPCClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        value = self.responses[name]
        if isinstance(value, list):
            value = value.pop(0)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=value))


def claim_fixture(*, clone=True, completed=()):
    session, job, snapshot, source, source_revision, blueprint_revision = (
        uuid4() for _ in range(6)
    )
    frozen = {
        "source_question_id": str(source),
        "question_no": 1,
        "source_revision_id": str(source_revision),
        "blueprint_revision_id": str(blueprint_revision),
        "source_fingerprint": "a" * 64,
        "blueprint_fingerprint": "b" * 64,
        "confirmed_input": {
            "id": str(source),
            "question_text": "Find x.",
            "options": ["1", "2", "3", "4"],
            "correct_answer": "A",
            "solution": "x=1",
        },
        "canonical_blueprint": {},
    }
    context = {
        "confirmed_sources": [frozen],
        "canonical_dimensions": [] if clone else ["values"],
        "confirmed_source_hash": "c" * 64,
        "base_seed": 100,
    }
    committed = [
        {
            "version_index": row["version_index"],
            "source_question_id": str(source),
            "question_no": 1,
            "result_kind": row["result_kind"],
        }
        for row in completed
    ]
    claim = {
        "session_id": str(session),
        "job_id": str(job),
        "snapshot_id": str(snapshot),
        "context": context,
        "gemini_call_count": 7,
        "config": {"n_versions": 2, "active_variation_modes": [] if clone else ["VARY_VALUES"]},
        "committed_targets": committed,
    }
    loaded = {
        "session_id": str(session),
        "snapshot_id": str(snapshot),
        "context": context,
        "completed": list(completed),
        "failures": [],
    }
    return session, job, snapshot, source, claim, loaded


@pytest.mark.asyncio
async def test_clone_claim_resume_persists_only_missing_frozen_slot(monkeypatch):
    session, job, snapshot, source, claim, loaded = claim_fixture()
    first = claim["context"]["confirmed_sources"][0]
    record = {
        "result_kind": "ORIGINAL_CLONE",
        "snapshot_id": str(snapshot),
        "version_index": 1,
        "source_question_id": str(source),
        "question_no": 1,
        "source_revision_id": first["source_revision_id"],
        "source_fingerprint": first["source_fingerprint"],
        "blueprint_revision_id": first["blueprint_revision_id"],
        "confirmed_source_hash": "c" * 64,
        "seed": 1100,
        "content": "Find x.",
        "options": ["1", "2", "3", "4"],
        "correct_key": "A",
        "solution_md": "x=1",
    }
    loaded["completed"] = [
        {
            "snapshot_id": str(snapshot),
            "version_index": 1,
            "source_question_id": str(source),
            "question_no": 1,
            "result_kind": "ORIGINAL_CLONE",
            "raw_result": record,
        }
    ]
    claim["committed_targets"] = [
        {
            "version_index": 1,
            "source_question_id": str(source),
            "question_no": 1,
            "result_kind": "ORIGINAL_CLONE",
        }
    ]
    owner = FakeRPCClient({"claim_generation_job": claim})
    worker = FakeRPCClient(
        {
            "load_generation_completed_results": loaded,
            "fail_stale_generation_job": {
                "session_id": str(session),
                "stale_job_recovered": False,
            },
            "persist_generation_clone": {
                "success": True,
                "session_id": str(session),
                "snapshot_id": str(snapshot),
                "result_kind": "ORIGINAL_CLONE",
                "version_index": 2,
                "source_question_id": str(source),
            },
            "finish_generation_job": {
                "session_id": str(session),
                "snapshot_id": str(snapshot),
                "status": "generated",
            },
        }
    )
    monkeypatch.setattr(
        "app.services.generation.job_repository.get_service_role_client", lambda: worker
    )
    repo = GenerationJobRepository(owner)
    events = GenerationEventBroker()
    registry = RuntimeRegistry()
    registry.start()
    runner = GenerationJobRunner(None, events, registry)
    plan = await runner.claim(repo, session)
    assert isinstance(plan.inputs, CloneJobInputs)
    assert plan.saved == {plan.targets[0]}
    outcome = await runner.run(plan, repo)
    assert outcome.status == "generated" and outcome.completed == 2
    assert [name for name, _ in worker.calls].count("persist_generation_clone") == 1
    assert not any(name == "reserve_generation_quota" for name, _ in worker.calls)
    assert worker.calls[-2][1]["p_clone_record"] == {**record, "version_index": 2, "seed": 2100}
    assert owner.calls[0][1] == {"p_session_id": str(session), "p_is_retry": False}


@pytest.mark.asyncio
async def test_quota_and_stale_use_fenced_rpc(monkeypatch):
    session, job, snapshot, _, claim, loaded = claim_fixture()
    owner = FakeRPCClient({"claim_generation_job": claim})
    worker = FakeRPCClient(
        {
            "load_generation_completed_results": loaded,
            "reserve_generation_quota": {
                "session_id": str(session),
                "job_id": str(job),
                "reserved_calls": 1,
                "new_total_calls": 8,
            },
            "fail_stale_generation_job": {
                "session_id": str(session),
                "stale_job_recovered": True,
            },
        }
    )
    monkeypatch.setattr(
        "app.services.generation.job_repository.get_service_role_client", lambda: worker
    )
    repo = GenerationJobRepository(owner)
    plan = await repo.claim(session, retry=True)
    assert await repo.reserve_gemini_call(plan) == 8
    assert await repo.fail_stale(session, cutoff=datetime.now(timezone.utc)) is True
    assert worker.calls[1][1] == {
        "p_session_id": str(session),
        "p_calls_requested": 1,
        "p_job_token": str(job),
    }


@pytest.mark.asyncio
async def test_claim_rejects_disagreement_between_claim_and_durable_results(monkeypatch):
    session, _, _, _, claim, loaded = claim_fixture()
    claim["committed_targets"] = [
        {
            "version_index": 1,
            "source_question_id": str(uuid4()),
            "question_no": 1,
            "result_kind": "ORIGINAL_CLONE",
        }
    ]
    owner = FakeRPCClient({"claim_generation_job": claim})
    worker = FakeRPCClient({"load_generation_completed_results": loaded})
    monkeypatch.setattr(
        "app.services.generation.job_repository.get_service_role_client", lambda: worker
    )
    repo = GenerationJobRepository(owner)
    with pytest.raises(Exception, match="Generation snapshot could not be verified"):
        await repo.claim(session, retry=False)


@pytest.mark.asyncio
async def test_ai_result_rpc_receives_full_raw_result_and_projection(monkeypatch):
    session, job, snapshot, source, claim, loaded = claim_fixture(clone=False)
    owner = FakeRPCClient({"claim_generation_job": claim})
    worker = FakeRPCClient(
        {
            "load_generation_completed_results": loaded,
            "persist_generation_result": {
                "success": True,
                "session_id": str(session),
                "snapshot_id": str(snapshot),
                "version_index": 1,
                "source_question_id": str(source),
            },
        }
    )
    monkeypatch.setattr(
        "app.services.generation.job_repository.get_service_role_client", lambda: worker
    )
    repo = GenerationJobRepository(owner)
    plan = await repo.claim(session, retry=False)
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text())
    payload = CandidatePayload.model_validate(fixture["candidates"][0])
    candidate = GeneratedQuestion(
        **payload.model_dump(),
        variant_id="variant-1",
        source_question_id=str(source),
        blueprint_fingerprint="b" * 64,
        seed=1100,
        solution_md=render_solution(payload.solution),
        has_warning=False,
    )
    raw = QuestionResult(
        version_index=1,
        source_question_id=str(source),
        request_fingerprint="d" * 64,
        candidate=candidate,
        validation=ValidationReport(checks=[]),
        attempts=2,
    )
    draft = GeneratedDraft(
        content=candidate.question_text,
        options=dict(zip("ABCD", candidate.options, strict=True)),
        correct_key=candidate.correct_key,
        solution_md=candidate.solution_md,
        retry_count=1,
    )
    await repo.save_result(plan, PreparedAIResult(plan.targets[0], draft, raw))
    name, args = worker.calls[-1]
    assert name == "persist_generation_result"
    assert args["p_job_token"] == str(job) and args["p_seed"] == 1100
    assert args["p_raw_result"] == raw.model_dump(mode="json")
    assert args["p_options"] == candidate.options
    assert args["p_request_fingerprint"] == "d" * 64


@pytest.mark.asyncio
@pytest.mark.parametrize("n_versions", [1, 2, 3, 4])
@pytest.mark.parametrize("is_success", [True, False])
async def test_ai_result_seed_uses_frozen_source_ordinal_after_resume(
    monkeypatch, n_versions, is_success
):
    session, job, snapshot, first_source, claim, loaded = claim_fixture(clone=False)
    first = claim["context"]["confirmed_sources"][0]
    second_source = uuid4()
    second = deepcopy(first)
    second["source_question_id"] = str(second_source)
    second["question_no"] = 2
    second["source_revision_id"] = str(uuid4())
    second["blueprint_revision_id"] = str(uuid4())
    second["confirmed_input"]["id"] = str(second_source)
    claim["context"]["confirmed_sources"].append(second)
    claim["config"]["n_versions"] = n_versions

    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8")
    )
    payload = CandidatePayload.model_validate(fixture["candidates"][0])

    def make_candidate(source_id, seed):
        return GeneratedQuestion(
            **payload.model_dump(),
            variant_id="variant-1",
            source_question_id=str(source_id),
            blueprint_fingerprint="b" * 64,
            seed=seed,
            solution_md=render_solution(payload.solution),
            has_warning=False,
        )

    committed = QuestionResult(
        version_index=1,
        source_question_id=str(first_source),
        request_fingerprint="d" * 64,
        candidate=make_candidate(first_source, 1100),
        validation=ValidationReport(checks=[]),
        attempts=1,
    )
    loaded["completed"] = [
        {
            "snapshot_id": str(snapshot),
            "version_index": 1,
            "source_question_id": str(first_source),
            "question_no": 1,
            "result_kind": "AI_RESULT",
            "request_fingerprint": committed.request_fingerprint,
            "raw_result": committed.model_dump(mode="json"),
        }
    ]
    claim["committed_targets"] = [
        {
            "version_index": 1,
            "source_question_id": str(first_source),
            "question_no": 1,
            "result_kind": "AI_RESULT",
        }
    ]
    owner = FakeRPCClient({"claim_generation_job": claim})
    worker = FakeRPCClient({"load_generation_completed_results": loaded})
    monkeypatch.setattr(
        "app.services.generation.job_repository.get_service_role_client", lambda: worker
    )
    repo = GenerationJobRepository(owner)
    plan = await repo.claim(session, retry=True)
    assert plan.saved == {plan.targets[0]}
    assert plan.inputs.completed == (committed,)

    for version in range(1, n_versions + 1):
        expected_seed = 100 + version * 1000 + 1
        target = next(
            target
            for target in plan.targets
            if target.source_question_id == second_source and target.version_index == version
        )
        candidate = make_candidate(second_source, expected_seed) if is_success else None
        raw = QuestionResult(
            version_index=version,
            source_question_id=str(second_source),
            request_fingerprint="e" * 64,
            candidate=candidate,
            validation=ValidationReport(checks=[]) if is_success else None,
            attempts=1,
            error_code=None if is_success else "API_TIMEOUT",
        )
        draft = (
            GeneratedDraft(
                content=candidate.question_text,
                options=dict(zip("ABCD", candidate.options, strict=True)),
                correct_key=candidate.correct_key,
                solution_md=candidate.solution_md,
                retry_count=0,
            )
            if candidate is not None
            else None
        )
        worker.responses["persist_generation_result"] = {
            "success": True,
            "session_id": str(session),
            "snapshot_id": str(snapshot),
            "version_index": version,
            "source_question_id": str(second_source),
        }
        await repo.save_result(plan, PreparedAIResult(target, draft, raw))
        name, params = worker.calls[-1]
        assert name == "persist_generation_result"
        assert params["p_seed"] == expected_seed
        assert params["p_version_index"] == version
        assert params["p_source_question_id"] == str(second_source)
        assert params["p_is_success"] is is_success
        assert params["p_raw_result"] == raw.model_dump(mode="json")

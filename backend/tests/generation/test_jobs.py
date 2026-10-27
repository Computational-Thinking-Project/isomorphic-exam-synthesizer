import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.services.generation.events import GenerationEventBroker
from app.services.generation.job_contracts import (
    GeneratedDraft,
    GenerationJobError,
    GenerationPlan,
    GenerationQuotaExceeded,
    QuestionTarget,
)
from app.services.generation.jobs import GenerationJobRunner, ProviderCalls
from app.services.observability.runtime_registry import RuntimeRegistry


def make_plan(*, quota: int = 0) -> GenerationPlan:
    targets = tuple(QuestionTarget(uuid4(), index, 1) for index in (1, 2))
    return GenerationPlan(uuid4(), uuid4(), targets, frozenset(), quota, inputs=None)


def draft(*, warning: bool = False) -> GeneratedDraft:
    return GeneratedDraft(
        content="Question",
        options={key: str(i) for i, key in enumerate("ABCD")},
        correct_key="B",
        solution_md="Detailed solution",
        has_warning=warning,
        retry_count=3 if warning else 0,
    )


class FakeStore:
    """Fixture only: does not prove any SQL transaction, fencing or RLS."""

    def __init__(self, plan: GenerationPlan) -> None:
        self.plan = plan
        self.count = plan.gemini_call_count
        self.claimed = False
        self.retry = False
        self.saved: list[QuestionTarget] = []
        self.finished: list[tuple[str, str | None]] = []
        self.cutoff: datetime | None = None
        self.save_error = False
        self.finish_error = False

    async def claim(self, session_id: UUID, *, retry: bool) -> GenerationPlan:
        if self.claimed:
            raise GenerationJobError(409, "ERR_ALREADY_GENERATING", "Already generating.")
        assert session_id == self.plan.session_id
        self.claimed = True
        self.retry = retry
        return self.plan

    async def reserve_gemini_call(self, plan: GenerationPlan) -> int:
        if self.count >= 250:
            raise GenerationQuotaExceeded()
        self.count += 1
        return self.count

    async def save_draft(
        self, plan: GenerationPlan, target: QuestionTarget, draft: GeneratedDraft
    ) -> None:
        if self.save_error:
            raise ConnectionError("private database endpoint")
        assert target not in self.saved and target not in plan.saved
        self.saved.append(target)

    async def finish(self, plan: GenerationPlan, outcome, *, error_code: str | None) -> None:
        if self.finish_error:
            raise ConnectionError("private database endpoint")
        self.finished.append((outcome, error_code))

    async def fail_stale(self, session_id: UUID, *, cutoff: datetime) -> bool:
        self.cutoff = cutoff
        return False


class FakePipeline:
    def __init__(self) -> None:
        self.seen: list[QuestionTarget] = []
        self.warning = False
        self.no_candidate = False
        self.block: asyncio.Event | None = None
        self.local_error = False

    async def generate(
        self, plan: GenerationPlan, target: QuestionTarget, calls: ProviderCalls
    ) -> GeneratedDraft | None:
        self.seen.append(target)
        if self.local_error:
            raise ValueError("private prompt")

        async def outbound() -> str:
            if self.block is not None:
                await self.block.wait()
            return "provider response"

        await calls.send(outbound)
        return None if self.no_candidate else draft(warning=self.warning)


def harness(plan: GenerationPlan, *, timeout: float = 600):
    registry = RuntimeRegistry()
    registry.start()
    pipeline = FakePipeline()
    events = GenerationEventBroker()
    runner = GenerationJobRunner(pipeline, events, registry, timeout_seconds=timeout)
    return FakeStore(plan), pipeline, events, registry, runner


def test_success_commits_each_question_and_releases_runtime_handles() -> None:
    async def scenario() -> None:
        plan = make_plan()
        store, pipeline, events, registry, runner = harness(plan)
        claimed = await runner.claim(store, plan.session_id)
        result = await runner.run(claimed, store)
        assert result.status == "generated" and result.completed == 2 and result.state_persisted
        assert store.saved == list(plan.targets)
        assert store.finished == [("generated", None)]
        assert registry.snapshot().background_jobs_running == 0
        assert registry.snapshot().gemini_call_count == 2
        assert registry.snapshot().gemini_error_rate == 0
        assert store.cutoff is not None
        age = (datetime.now(timezone.utc) - store.cutoff).total_seconds()
        assert 720 <= age < 725
        with pytest.raises(GenerationJobError):
            await runner.run(claimed, store)

    asyncio.run(scenario())


def test_retry_preserves_saved_targets_and_existing_quota() -> None:
    async def scenario() -> None:
        original = make_plan(quota=20)
        plan = replace(original, saved=frozenset(original.targets[:1]))
        store, pipeline, events, registry, runner = harness(plan)
        await runner.claim(store, plan.session_id, retry=True)
        result = await runner.run(plan, store)
        assert result.status == "generated" and store.retry
        assert pipeline.seen == list(plan.targets[1:])
        assert store.saved == list(plan.targets[1:]) and store.count == 21
        assert registry.snapshot().gemini_call_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("quota", "expected", "completed"), [(249, "partial_generated", 1), (250, "failed", 0)]
)
def test_quota_never_sends_the_251st_request(quota: int, expected: str, completed: int) -> None:
    async def scenario() -> None:
        plan = make_plan(quota=quota)
        store, pipeline, events, registry, runner = harness(plan)
        await runner.claim(store, plan.session_id)
        result = await runner.run(plan, store)
        assert result.status == expected and result.completed == completed
        assert result.error_code == "ERR_GEMINI_QUOTA_EXHAUSTED"
        assert store.count == 250
        assert registry.snapshot().gemini_call_count == completed

    asyncio.run(scenario())


def test_validation_warning_does_not_prevent_full_generated_result() -> None:
    async def scenario() -> None:
        plan = make_plan()
        store, pipeline, events, registry, runner = harness(plan)
        pipeline.warning = True
        await runner.claim(store, plan.session_id)
        result = await runner.run(plan, store)
        assert result.status == "generated" and len(store.saved) == 2
        stream = events.stream(plan.session_id, registry=registry)
        frames = [frame async for frame in stream]
        assert sum("event: warning\n" in frame for frame in frames) == 2
        assert sum("event: question_done\n" in frame for frame in frames) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("already_saved", [False, True])
def test_timeout_retains_durable_progress(already_saved: bool) -> None:
    async def scenario() -> None:
        original = make_plan()
        plan = replace(
            original, saved=frozenset(original.targets[:1]) if already_saved else frozenset()
        )
        store, pipeline, events, registry, runner = harness(plan, timeout=0.01)
        pipeline.block = asyncio.Event()
        await runner.claim(store, plan.session_id)
        result = await runner.run(plan, store)
        assert result.status == ("partial_generated" if already_saved else "failed")
        assert result.error_code == "ERR_GENERATION_TIMEOUT"
        assert registry.snapshot().background_jobs_running == 0
        assert store.count == 1
        # Cancellation/timeout leaves the provider outcome unknown, not success.
        assert registry.snapshot().gemini_error_rate == 0

    asyncio.run(scenario())


def test_db_failure_does_not_emit_question_done_or_leak_exception() -> None:
    async def scenario() -> None:
        plan = make_plan()
        store, pipeline, events, registry, runner = harness(plan)
        store.save_error = True
        store.finish_error = True
        await runner.claim(store, plan.session_id)
        result = await runner.run(plan, store)
        assert not result.state_persisted and result.error_code == "ERR_GENERATION_STORAGE_FAILURE"
        frames = [frame async for frame in events.stream(plan.session_id, registry=registry)]
        assert not any("event: question_done\n" in frame for frame in frames)
        assert "private" not in "".join(frames)
        assert "event: error\n" in frames[-1]

    asyncio.run(scenario())


def test_local_failure_does_not_increment_provider_quota_or_runtime_count() -> None:
    async def scenario() -> None:
        plan = make_plan()
        store, pipeline, events, registry, runner = harness(plan)
        pipeline.local_error = True
        await runner.claim(store, plan.session_id)
        result = await runner.run(plan, store)
        assert result.status == "failed" and store.count == 0
        assert registry.snapshot().gemini_call_count == 0

    asyncio.run(scenario())


def test_fatal_error_after_partial_commit_marks_failed_without_erasing_progress() -> None:
    async def scenario() -> None:
        plan = make_plan()
        store, pipeline, events, registry, runner = harness(plan)

        class BrokenPipeline(FakePipeline):
            async def generate(
                self, plan: GenerationPlan, target: QuestionTarget, calls: ProviderCalls
            ) -> GeneratedDraft | None:
                if target == plan.targets[1]:
                    raise ConnectionError("private database details")
                return await super().generate(plan, target, calls)

        runner = GenerationJobRunner(BrokenPipeline(), events, registry)
        await runner.claim(store, plan.session_id)
        result = await runner.run(plan, store)
        assert result.status == "failed" and result.completed == 1
        assert store.saved == list(plan.targets[:1])
        assert store.finished[-1][0] == "failed"

    asyncio.run(scenario())


def test_retry_of_complete_job_sends_no_requests_even_at_quota_limit() -> None:
    async def scenario() -> None:
        original = make_plan(quota=250)
        plan = replace(original, saved=frozenset(original.targets))
        store, pipeline, events, registry, runner = harness(plan)
        await runner.claim(store, plan.session_id, retry=True)
        result = await runner.run(plan, store)
        assert result.status == "generated" and result.completed == 2
        assert pipeline.seen == [] and store.count == 250
        assert registry.snapshot().gemini_call_count == 0

    asyncio.run(scenario())


def test_no_saveable_candidates_never_create_fake_rows() -> None:
    async def scenario() -> None:
        plan = make_plan()
        store, pipeline, events, registry, runner = harness(plan)
        pipeline.no_candidate = True
        await runner.claim(store, plan.session_id)
        result = await runner.run(plan, store)
        assert result.status == "failed" and result.error_code == "ERR_GENERATION_INCOMPLETE"
        assert store.saved == [] and len(pipeline.seen) == 2

    asyncio.run(scenario())


def test_duplicate_claim_and_duplicate_run_are_rejected() -> None:
    async def scenario() -> None:
        plan = make_plan()
        store, pipeline, events, registry, runner = harness(plan)
        pipeline.block = asyncio.Event()
        await runner.claim(store, plan.session_id)
        with pytest.raises(GenerationJobError) as error:
            await runner.claim(store, plan.session_id)
        assert error.value.status_code == 409
        running = asyncio.create_task(runner.run(plan, store))
        await asyncio.sleep(0)
        with pytest.raises(GenerationJobError):
            await runner.run(plan, store)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert registry.snapshot().background_jobs_running == 0
        assert store.finished[-1][1] == "ERR_GENERATION_INTERRUPTED"

    asyncio.run(scenario())


def test_provider_failures_retries_and_concurrency_share_three_slots() -> None:
    async def scenario() -> None:
        registry = RuntimeRegistry()
        registry.start()
        slots = asyncio.Semaphore(3)
        active = 0
        peak = 0
        started = asyncio.Event()
        release = asyncio.Event()

        async def outbound() -> str:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 3:
                started.set()
            try:
                await release.wait()
                return "response"
            finally:
                active -= 1

        plan = make_plan()
        store = FakeStore(plan)
        context = ProviderCalls(
            store, plan, registry, slots, asyncio.get_running_loop().time() + 10
        )
        pending = [asyncio.create_task(context.send(outbound)) for _ in range(9)]
        await asyncio.wait_for(started.wait(), 1)
        assert store.count == 3 and peak == 3
        release.set()
        await asyncio.gather(*pending)
        assert peak == 3 and store.count == 9

        async def failure() -> str:
            raise ConnectionError("private URL")

        with pytest.raises(ConnectionError):
            await context.send(failure)
        assert registry.snapshot().gemini_call_count == 10
        assert registry.snapshot().gemini_error_rate == 0.1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "problem", ["duplicates", "gap", "saved_foreign", "quota_bool", "missing_cross_product"]
)
def test_invalid_job_plans_are_rejected(problem: str) -> None:
    plan = make_plan()
    with pytest.raises(ValueError):
        if problem == "duplicates":
            replace(plan, targets=(plan.targets[0], plan.targets[0]))
        elif problem == "gap":
            replace(plan, targets=tuple(replace(t, version_index=2) for t in plan.targets))
        elif problem == "saved_foreign":
            replace(plan, saved=frozenset(make_plan().targets))
        elif problem == "quota_bool":
            replace(plan, gemini_call_count=True)
        else:
            replace(plan, targets=(*plan.targets, replace(plan.targets[0], version_index=2)))


@pytest.mark.parametrize(
    "field,value",
    [("content", " "), ("solution_md", ""), ("options", {"A": "1"}), ("has_warning", "false")],
)
def test_incomplete_drafts_are_not_saveable(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        GeneratedDraft.model_validate({**draft().model_dump(), field: value})

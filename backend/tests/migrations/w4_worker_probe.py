"""Consume real local SQL receipts using pinned PR30's actual worker modules.

Executed by the SQL regression suite with PYTHONPATH pointing to an isolated
PR30 checkout. Transport is an in-memory receipt replay and generation is fake;
no Supabase client, provider call or remote write is allowed.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID


async def main() -> None:
    from app.services.generation.ai_batch_adapter import AIBatchAdapter
    from app.services.generation.job_repository import GenerationJobRepository

    from app.models.generation import (
        BatchResult,
        CandidatePayload,
        GeneratedQuestion,
        QuestionResult,
        ValidationReport,
        render_solution,
    )
    from app.services.generation.service import fingerprint

    data = json.load(sys.stdin)

    class ReceiptClient:
        def rpc(self, name, params):
            assert params["p_session_id"] == data["claim"]["session_id"]
            assert name in ("claim_generation_job", "load_generation_completed_results")
            value = data["claim"] if name == "claim_generation_job" else data["loaded"]
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=value))

    client = ReceiptClient()
    with patch("app.services.generation.job_repository.get_service_role_client", return_value=client):
        repo = GenerationJobRepository(client)
    plan = await repo.claim(UUID(data["claim"]["session_id"]), retry=False)
    assert plan.inputs.variation_modes == ("values",)
    assert len(plan.targets) == 4 and len(set(plan.targets)) == 4

    async def generate(sources, blueprints, **kwargs):
        assert kwargs["variation_modes"] == ["values"]
        assert kwargs["n_versions"] == 2 and len(sources) == 2
        results = []
        fixture = json.loads((Path.cwd() / "backend/tests/fixtures/ai_pipeline.json").read_text())
        payload = CandidatePayload.model_validate(fixture["candidates"][0])
        for target in plan.targets:
            index = next(i for i, source in enumerate(sources) if source.id == str(target.source_question_id))
            candidate = GeneratedQuestion(**payload.model_dump(),
                source_question_id=str(target.source_question_id), variant_id=f"fixture_{index}_{target.version_index}",
                blueprint_fingerprint=fingerprint(blueprints[str(target.source_question_id)]),
                seed=kwargs["base_seed"] + target.version_index * 1000 + index,
                solution_md=render_solution(payload.solution), has_warning=True)
            result = QuestionResult(version_index=target.version_index,
                source_question_id=str(target.source_question_id), request_fingerprint="fixture",
                attempts=1, candidate=candidate, validation=ValidationReport(checks=[]))
            await kwargs["on_result"](result)
            results.append(result)
        return BatchResult(results=results, status="generated")

    service = SimpleNamespace(generate_exam_drafts=AsyncMock(side_effect=generate))
    callback = AsyncMock()
    result = await AIBatchAdapter(service).run(plan, plan.inputs, SimpleNamespace(),
        deadline=time.monotonic() + 10, on_result=callback)
    service.generate_exam_drafts.assert_awaited_once()
    assert callback.await_count == 4 and len(result.results) == 4
    assert result.status == "generated"
    assert all(call.args[0].draft is not None for call in callback.await_args_list)
    assert len({call.args[0].target for call in callback.await_args_list}) == 4
    print("PASS: real SQL snapshot -> PR30 repository -> adapter; values once, four unique slots")


if __name__ == "__main__":
    asyncio.run(main())

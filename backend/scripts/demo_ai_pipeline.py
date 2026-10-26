"""Offline replay of confirmed source -> Blueprint -> N drafts -> one regeneration.

Run from backend: python scripts/demo_ai_pipeline.py
No credentials, network, DB or provider quota are used. This proves orchestration,
not Gemini output quality or general mathematical equivalence.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.schemas import SourceQuestion  # noqa: E402
from app.services.ai.gateway import RequestBudget, RequestContext  # noqa: E402
from app.services.blueprint.adapters import prepare_sources  # noqa: E402
from app.services.blueprint.common import canonical  # noqa: E402
from app.services.blueprint.schema_adapter import generation_payload  # noqa: E402
from app.services.blueprint.service import BlueprintService, source_fingerprint  # noqa: E402
from app.services.generation.service import GenerationService  # noqa: E402


class ReplayGateway:
    model = "offline-reviewed-fixture"

    def __init__(self, fixture):
        self.fixture = fixture
        self.index = 0

    async def generate_content(self, *, contents, config, context):
        await context.reserve_request()
        if config.response_json_schema.get("title") not in {"CandidatePayload", "StepByStepSolution"}:
            payload = generation_payload(self.fixture["blueprint"])
        else:
            payload = self.fixture["candidates"][self.index]
            self.index += 1
        return SimpleNamespace(text=canonical(payload), candidates=[SimpleNamespace(finish_reason="STOP")],
                               model_version=self.model, usage_metadata=None)


async def main():
    backend = Path(__file__).resolve().parents[1]
    fixture = json.loads((backend / "tests/fixtures/ai_pipeline.json").read_text(encoding="utf-8"))
    source = SourceQuestion.model_validate(fixture["source"])
    confirmed = source_fingerprint(prepare_sources([source]))  # Simulate BE's stored confirmation.
    budget = RequestBudget(10)
    context = RequestContext(time.monotonic() + 60, budget.reserve)
    gateway = ReplayGateway(fixture)
    blueprints, _ = await BlueprintService(gateway).extract_sources(
        [source], confirmed_source_hash=confirmed, context=context)
    service = GenerationService(gateway)
    drafts = await service.generate_exam_drafts([source], {source.id: blueprints[0]["blueprint"]},
        confirmed_source_hash=confirmed, n_versions=2, context=context)
    if drafts.status != "generated":
        raise RuntimeError(drafts.model_dump_json())
    previous = drafts.results[0].candidate
    regenerated = await service.regenerate_question(source, blueprints[0]["blueprint"], previous,
        confirmed_source_hash=confirmed, context=context,
        current_candidates=[result.candidate for result in drafts.results[1:]])
    if regenerated.candidate is None:
        raise RuntimeError(regenerated.model_dump_json())
    output = {
        "mode": "offline replay; teacher review required; no live API used",
        "reserved_replay_requests": budget.used,
        "blueprints": blueprints, "drafts": drafts.model_dump(),
        "regenerated": regenerated.model_dump(),
    }
    destination = backend.parent / "outputs/blueprint/ai-pipeline-demo.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": drafts.status, "requests": budget.used, "output": str(destination)}, ensure_ascii=True))


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import copy
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import Settings
from app.services.ai import gateway as gateway_module
from app.services.ai.gateway import GeminiGateway, RequestBudget, RequestContext
from app.services.blueprint.common import ToolError, canonical, load_json
from app.services.blueprint.schema_adapter import generation_payload
from app.services.blueprint.service import BlueprintService, source_fingerprint


def test_backend_resources_are_self_contained_without_repo_docs_or_scripts(tmp_path):
    backend = Path(__file__).resolve().parents[2]
    shutil.copytree(backend / "app", tmp_path / "app", ignore=shutil.ignore_patterns("__pycache__"))
    process = subprocess.run(
        [sys.executable, "-c", (
            "from types import SimpleNamespace; "
            "from app.services.blueprint.service import BlueprintService; "
            "service = BlueprintService(SimpleNamespace(model='offline')); "
            "assert service.config.schema_path.is_file(); "
            "assert service.prompts.system"
        )],
        cwd=tmp_path, capture_output=True, text=True, timeout=20,
    )
    assert process.returncode == 0, process.stderr


@pytest.fixture
def setup_service():
    example = load_json(Path(__file__).resolve().parents[1] / "fixtures/blueprint_math.json")
    response = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason="STOP")],
        text=canonical(generation_payload(example)),
        model_version="test-model",
        usage_metadata=None,
    )
    gateway = SimpleNamespace(model="test-model", generate_content=AsyncMock(return_value=response))
    item = {
        "source": copy.deepcopy(example["requirement"]["source"]),
        "context": {"subject": "mathematics", "language": "vi"},
    }
    return BlueprintService(gateway), gateway, item


@pytest.mark.asyncio
async def test_source_requires_confirmation_and_matching_fingerprint(setup_service):
    service, gateway, item = setup_service
    ctx = RequestContext(time.monotonic() + 10, RequestBudget(5).reserve)
    for fingerprint, code in [(None, "SOURCE_NOT_CONFIRMED"), ("different", "SOURCE_CHANGED")]:
        with pytest.raises(ToolError) as caught:
            await service.extract_confirmed([item], confirmed_source_hash=fingerprint, context=ctx)
        assert caught.value.code == code
    gateway.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_source_is_preserved_and_resources_work_from_other_cwd(
    setup_service, tmp_path, monkeypatch
):
    service, gateway, item = setup_service
    monkeypatch.chdir(tmp_path)
    ctx = RequestContext(time.monotonic() + 10, RequestBudget(5).reserve)
    results, metadata = await service.extract_confirmed(
        [item], confirmed_source_hash=source_fingerprint([item]), context=ctx
    )
    assert results[0]["error"] is None
    assert results[0]["blueprint"]["requirement"]["source"] == item["source"]
    assert results[0]["blueprint"]["constraint"]["source_check"]["methods"] == []
    assert metadata[0]["requests"] == 1
    assert gateway.generate_content.await_args.kwargs["context"] is ctx


@pytest.mark.asyncio
async def test_invalid_item_does_not_block_valid_sibling(setup_service):
    service, gateway, item = setup_service
    items = [item, {"source": {"question_id": "bad"}}]
    ctx = RequestContext(time.monotonic() + 10, RequestBudget(5).reserve)
    results, _ = await service.extract_confirmed(
        items, confirmed_source_hash=source_fingerprint(items), context=ctx
    )
    assert results[0]["error"] is None
    assert results[1]["error"]["code"] == "ITEM_INPUT_INVALID"
    assert gateway.generate_content.await_count == 1


@pytest.mark.asyncio
async def test_source_snapshot_cannot_change_during_request(setup_service):
    service, gateway, item = setup_service
    original = copy.deepcopy(item)
    response = gateway.generate_content.return_value
    started, release = asyncio.Event(), asyncio.Event()

    async def wait(**kwargs):
        started.set()
        await release.wait()
        return response

    gateway.generate_content.side_effect = wait
    ctx = RequestContext(time.monotonic() + 10, RequestBudget(5).reserve)
    task = asyncio.create_task(
        service.extract_confirmed(
            [item], confirmed_source_hash=source_fingerprint([item]), context=ctx
        )
    )
    await started.wait()
    item["source"]["content"][0]["text"] = "changed"
    release.set()
    results, _ = await task
    assert results[0]["blueprint"]["requirement"]["source"] == original["source"]


@pytest.mark.asyncio
async def test_extraction_repair_uses_shared_gateway_and_same_request_budget(setup_service, monkeypatch):
    _, fake_gateway, item = setup_service
    valid = fake_gateway.generate_content.return_value
    malformed = copy.copy(valid)
    malformed.text = "broken JSON"
    sdk = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=AsyncMock(side_effect=[malformed, valid])),
            aclose=AsyncMock(),
        ),
        close=Mock(),
    )
    monkeypatch.setattr(gateway_module.genai, "Client", lambda **kwargs: sdk)
    config = Settings(
        _env_file=None, GEMINI_API_KEY="test-only", GEMINI_API_KEY_1="",
        GEMINI_API_KEY_2="", GEMINI_API_KEY_3="",
    )
    budget = RequestBudget(2)
    ctx = RequestContext(time.monotonic() + 10, budget.reserve)
    async with GeminiGateway(config) as gateway:
        service = BlueprintService(gateway)
        results, metadata = await service.extract_confirmed(
            [item], confirmed_source_hash=source_fingerprint([item]), context=ctx
        )
    assert results[0]["error"] is None
    assert budget.used == metadata[0]["requests"] == 2
    assert sdk.aio.models.generate_content.await_count == 2
    assert "VALIDATION_ERRORS" in sdk.aio.models.generate_content.await_args.kwargs["contents"]

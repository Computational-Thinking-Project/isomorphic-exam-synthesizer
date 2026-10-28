"""Backend entry point for confirmed sources; no HTTP, SQL or implicit API calls."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from google.genai import types

from app.models.schemas import SourceQuestion
from app.services.ai.gateway import GatewayError, GeminiGateway, RequestContext

from .adapters import prepare_sources, validate_math_blueprint
from .ai_client import ProviderError, reply_from_response
from .common import ToolError, canonical, load_json
from .config import Config
from .extractor import Extractor
from .input_adapter import Contracts, input_items
from .prompt_builder import PROMPT_VERSION, Prompts
from .schema_adapter import build_api_schema


def source_fingerprint(items: list[dict[str, Any]]) -> str:
    """Hash source plus extraction context; persist this at source confirmation."""
    return hashlib.sha256(canonical(items).encode("utf-8")).hexdigest()


class _GatewayClient:
    def __init__(self, gateway: GeminiGateway, context: RequestContext, max_tokens: int):
        self.gateway = gateway
        self.context = context
        self.max_tokens = max_tokens

    async def generate(self, *, item, prompt, system, api_schema):
        try:
            response = await self.gateway.generate_content(
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=api_schema,
                    max_output_tokens=self.max_tokens,
                ),
                context=self.context,
            )
        except GatewayError as exc:
            raise ProviderError(exc.code, exc.code, retryable=exc.retryable) from None
        return reply_from_response(response)


class BlueprintService:
    """Reuse one app-scoped gateway across jobs. The caller owns its lifecycle."""

    def __init__(self, gateway: GeminiGateway):
        self.gateway = gateway
        self.config = Config(model=gateway.model)
        self.schema = load_json(self.config.schema_path)
        self.contracts = Contracts(self.schema)
        self.api_schema, self.schema_manifest = build_api_schema(self.schema)
        self.prompts = Prompts(self.config.prompt_directory)

    def input_fingerprint(self, item: dict[str, Any]) -> str:
        return hashlib.sha256(canonical({
            "item": item, "model": self.gateway.model,
            "schema": self.schema, "prompts": self.prompts.hash,
        }).encode("utf-8")).hexdigest()

    async def extract_sources(
        self, sources: list[SourceQuestion], *, confirmed_source_hash: str | None,
        context: RequestContext, ready: dict[str, dict[str, Any]] | None = None,
        on_result: Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]] | None = None,
    ):
        """App profile with incremental retry; ready values are prior result records."""
        sources = [source.model_copy(deep=True) for source in sources]
        items = prepare_sources(sources)
        if not confirmed_source_hash or source_fingerprint(items) != confirmed_source_hash:
            raise ToolError("SOURCE_NOT_CONFIRMED", "Nguồn chưa được xác nhận hoặc đã thay đổi.")
        ready = deepcopy(ready or {})
        if not set(ready) <= {source.id for source in sources}:
            raise ToolError("BLUEPRINT_CACHE_MISMATCH", "Blueprint lưu không thuộc đề nguồn này.")
        results, metadata, missing = {}, {}, []
        for index, source in enumerate(sources):
            cached = ready.get(source.id)
            if cached:
                if cached.get("input_fingerprint") != self.input_fingerprint(items[index]) or cached.get("error") or not cached.get("blueprint"):
                    raise ToolError("BLUEPRINT_CACHE_MISMATCH", "Blueprint lưu khác input/model/schema/prompt.")
                validate_math_blueprint(cached["blueprint"], items[index], self.contracts, self.schema)
                cached["index"] = index
                results[index] = cached
                metadata[index] = {"index": index, "source_question_id": source.id, "requests": 0, "cached": True}
            else:
                missing.append(index)
        if missing:
            semaphore = asyncio.Semaphore(self.config.concurrency)

            async def one(index):
                source_id = sources[index].id
                try:
                    async with asyncio.timeout_at(context.deadline):
                        async with semaphore:
                            item = items[index]
                            extracted, stats = await self.extract_confirmed(
                                [item], confirmed_source_hash=source_fingerprint([item]), context=context
                            )
                            result, stat = extracted[0], stats[0]
                except TimeoutError:
                    result = {"blueprint": None, "error": ToolError("JOB_DEADLINE", "Hết thời gian trích xuất.").as_dict()}
                    stat = {"requests": None, "limitations": ["Use the shared reservation counter for quota accounting."]}
                if result["blueprint"] is not None:
                    try:
                        validate_math_blueprint(result["blueprint"], items[index], self.contracts, self.schema)
                    except ToolError as exc:
                        result["blueprint"], result["error"] = None, exc.as_dict()
                result.update(index=index, source_question_id=source_id,
                              input_fingerprint=self.input_fingerprint(items[index]))
                stat.update(index=index, source_question_id=source_id, cached=False,
                            model=self.gateway.model, schema_version="0.4.0",
                            prompt_version=PROMPT_VERSION, prompt_hash=self.prompts.hash)
                if on_result:
                    await on_result(deepcopy(result), deepcopy(stat))
                results[index], metadata[index] = result, stat
            async with asyncio.TaskGroup() as group:
                for index in missing:
                    group.create_task(one(index))
        return [results[index] for index in range(len(items))], [metadata[index] for index in range(len(items))]

    async def extract_confirmed(
        self,
        items: list[dict[str, Any]],
        *,
        confirmed_source_hash: str | None,
        context: RequestContext,
    ):
        # Snapshot before the first await so callers cannot mutate a running job.
        snapshot = deepcopy(items)
        if not confirmed_source_hash:
            raise ToolError(
                "SOURCE_NOT_CONFIRMED", "Cần xác nhận đề nguồn trước khi sinh Blueprint."
            )
        if source_fingerprint(snapshot) != confirmed_source_hash:
            raise ToolError("SOURCE_CHANGED", "Đề nguồn không khớp bản đã xác nhận.")
        input_items({"questions": snapshot}, "batch")
        extractor = Extractor(
            self.config,
            self.schema,
            self.api_schema,
            self.contracts,
            self.prompts,
            _GatewayClient(self.gateway, context, self.config.max_output_tokens),
        )
        async with asyncio.timeout_at(context.deadline):
            return await extractor.run(snapshot)

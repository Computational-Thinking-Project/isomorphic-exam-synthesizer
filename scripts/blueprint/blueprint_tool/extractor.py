"""Per-question request budget, bounded repair, ordered concurrent batch."""

import asyncio
import hashlib
import time
import uuid
from copy import deepcopy

from .ai_client import ProviderError
from .common import MAX_RESPONSE_BYTES, ToolError, canonical, strict_json
from .input_adapter import question_id
from .validators import schema_issues, validate_blueprint, validate_input


def assemble(payload, source, blueprint_id):
    result = deepcopy(payload)
    req, con = result["requirement"], result["constraint"]
    req.update(
        blueprint_id=blueprint_id,
        schema_version="0.4.0",
        source=deepcopy(source),
        language_policy={
            "field_names": "en",
            "descriptive_values": "source_language",
            "machine_codes": "stable",
        },
    )
    req["presentation"].update(
        allowed_content_types=["text", "formula", "table"], requires_image=False
    )
    con["validation_policy"] = {
        "outcomes": ["pass", "fail", "unknown"],
        "required_unknown_action": "block_automatic_acceptance",
        "advisory_can_override_required": False,
    }
    con["source_check"].update(methods=[], evidence=[])
    return result


class Extractor:
    def __init__(self, config, canonical_schema, api_schema, contracts, prompts, client):
        self.config, self.schema, self.api_schema = config, canonical_schema, api_schema
        self.contracts, self.prompts, self.client = contracts, prompts, client

    async def _extract(self, item, metadata):
        validate_input(item, self.contracts.single, self.contracts.registry)
        source = deepcopy(item["source"])
        metadata["source_sha256"] = hashlib.sha256(canonical(source).encode()).hexdigest()
        prompt = original_prompt = self.prompts.extraction(item)
        previous, issues = None, []
        blueprint_id = "bp_" + uuid.uuid4().hex
        for attempt in range(self.config.max_requests_per_item):
            metadata["requests"] += 1
            try:
                async with asyncio.timeout(self.config.request_timeout_seconds):
                    reply = await self.client.generate(
                        item=item,
                        prompt=prompt,
                        system=self.prompts.system,
                        api_schema=self.api_schema,
                    )
                metadata["responses"].append(
                    {"model_version": reply.model_version, "tokens": reply.tokens}
                )
                if len(reply.text.encode("utf-8")) > MAX_RESPONSE_BYTES:
                    raise ToolError("AI_OUTPUT_TOO_LARGE", "Output AI vượt giới hạn kích thước.")
                previous = reply.text
                payload = strict_json(reply.text)
                issues = schema_issues(payload, self.api_schema)
                if not issues:
                    blueprint = assemble(payload, source, blueprint_id)
                    issues = validate_blueprint(
                        blueprint, self.schema, source, item.get("context", {})
                    )
                    if not issues:
                        return blueprint
                metadata["validation_failures"].append(issues)
                previous = payload
            except TimeoutError:
                issues = [{"rule": "request_timeout"}]
            except ProviderError as exc:
                if not exc.retryable or attempt + 1 == self.config.max_requests_per_item:
                    raise
                issues = [{"rule": exc.code}]
                if exc.code == "AI_TRUNCATED":
                    prompt = self.prompts.repair(original_prompt, None, issues)
                await asyncio.sleep(min(2**attempt, 4))
                continue
            except ToolError as exc:
                issues = [{"rule": exc.code}]
                metadata["validation_failures"].append(issues)
            if attempt + 1 < self.config.max_requests_per_item:
                if previous is not None:
                    prompt = self.prompts.repair(original_prompt, previous, issues)
                else:
                    await asyncio.sleep(min(2**attempt, 4))
        raise ToolError(
            "BLUEPRINT_INVALID", "Chưa tạo được blueprint hợp lệ trong ngân sách request.", issues
        )

    async def run(self, items):
        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def one(index, item):
            async with semaphore:
                start = time.monotonic()
                metadata = {
                    "index": index,
                    "question_id": question_id(item),
                    "requests": 0,
                    "responses": [],
                    "validation_failures": [],
                    "limitations": [
                        "Chưa xác minh độc lập tính đúng chuyên môn và tính tương đương sư phạm.",
                        "Ngôn ngữ và phụ thuộc hình chỉ có kiểm tra heuristic; cần rà soát nội dung.",
                    ],
                }
                result = {
                    "index": index,
                    "question_id": question_id(item),
                    "blueprint": None,
                    "error": None,
                }
                try:
                    async with asyncio.timeout(self.config.item_timeout_seconds):
                        result["blueprint"] = await self._extract(item, metadata)
                except TimeoutError:
                    result["error"] = ToolError(
                        "ITEM_TIMEOUT", "Hết thời gian xử lý một câu."
                    ).as_dict()
                except ToolError as exc:
                    result["error"] = exc.as_dict()
                except Exception:
                    result["error"] = ToolError(
                        "ITEM_INTERNAL",
                        "Lỗi nội bộ khi xử lý câu; không trả blueprint chưa kiểm tra.",
                    ).as_dict()
                metadata["elapsed_seconds"] = round(time.monotonic() - start, 3)
                return result, metadata

        pairs = await asyncio.gather(*(one(index, item) for index, item in enumerate(items)))
        return [p[0] for p in pairs], [p[1] for p in pairs]

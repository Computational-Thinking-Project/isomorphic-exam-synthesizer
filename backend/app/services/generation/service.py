"""Async generation from a fixed Blueprint, with bounded retries and shared quota."""

import asyncio
import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any, Literal

from google.genai import types

from app.models.generation import (
    BatchResult,
    CandidatePayload,
    GeneratedQuestion,
    QuestionResult,
    StepByStepSolution,
    render_solution,
)
from app.models.schemas import SourceQuestion
from app.services.ai.gateway import GatewayError, GeminiGateway, RequestContext
from app.services.ai.structured_output import parse_model_output
from app.services.blueprint.adapters import (
    normalized_text,
    prepare_sources,
    source_to_item,
    validate_math_blueprint,
)
from app.services.blueprint.ai_client import ProviderError, reply_from_response
from app.services.blueprint.common import ToolError, canonical, load_json
from app.services.blueprint.config import Config
from app.services.blueprint.input_adapter import Contracts
from app.services.blueprint.service import source_fingerprint
from app.services.validator.pipeline import CandidateValidator

from .prompts import PROMPT_VERSION, SYSTEM, build_prompt

ResultCallback = Callable[[QuestionResult], Awaitable[None]]
AcceptCandidate = Callable[[CandidatePayload], Awaitable[bool]]


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def candidate_identity(candidate: CandidatePayload) -> str:
    # Option shuffling or a different solution alone does not create a new question.
    return fingerprint([
        normalized_text(candidate.question_text),
        sorted(normalized_text(option) for option in candidate.options),
    ])


class GenerationService:
    MAX_ATTEMPTS = 4  # Initial call + at most three further calls, including repair.

    def __init__(self, gateway: GeminiGateway, validator: CandidateValidator | None = None):
        self.gateway = gateway
        self.validator = validator or CandidateValidator()
        self.schema = load_json(Config().schema_path)
        self.contracts = Contracts(self.schema)

    def _prepare(
        self, source: SourceQuestion, blueprint: dict[str, Any], variation_modes: list[str]
    ) -> dict[str, Any]:
        item = source_to_item(source)
        validate_math_blueprint(blueprint, item, self.contracts, self.schema)
        supported = {
            transform["dimension"]
            for transform in blueprint["requirement"]["variation_policy"]["allowed_transformations"]
        }
        if not set(variation_modes) <= supported:
            raise ToolError("ERR_CONFIG_CONFLICT", "Chế độ biến thể không được Blueprint hỗ trợ.")
        return item

    def _request_fingerprint(
        self, item: dict[str, Any], blueprint: dict[str, Any], seed: int, variation_modes: list[str]
    ) -> str:
        return fingerprint({
            "source": item, "blueprint": blueprint, "seed": seed,
            "variation_modes": sorted(set(variation_modes)),
            "model": self.gateway.model, "prompt_version": PROMPT_VERSION,
        })

    async def generate_question(
        self, source: SourceQuestion, blueprint: dict[str, Any], *,
        confirmed_source_hash: str, context: RequestContext, seed: int = 100,
        version_index: int = 1, variation_modes: list[str] | None = None,
    ) -> QuestionResult:
        source = source.model_copy(deep=True)
        blueprint = deepcopy(blueprint)
        modes = list(variation_modes or [])
        item = self._prepare(source, blueprint, modes)
        if not confirmed_source_hash or source_fingerprint([item]) != confirmed_source_hash:
            raise ToolError("SOURCE_NOT_CONFIRMED", "Nguồn chưa được xác nhận hoặc đã thay đổi.")
        return await self._generate(source, item, blueprint, context, seed, version_index, modes)

    async def _generate(
        self, source: SourceQuestion, item: dict[str, Any], blueprint: dict[str, Any],
        context: RequestContext, seed: int, version_index: int, variation_modes: list[str],
        previous: GeneratedQuestion | None = None, accept: AcceptCandidate | None = None,
        excluded_identities: set[str] | None = None,
    ) -> QuestionResult:
        result = QuestionResult(
            version_index=version_index, source_question_id=source.id,
            request_fingerprint=self._request_fingerprint(item, blueprint, seed, variation_modes),
        )
        original_identity = fingerprint([
            normalized_text(source.question_text),
            sorted(normalized_text(option) for option in source.options),
        ])
        excluded = {original_identity, *(excluded_identities or set())}
        if previous:
            excluded.add(candidate_identity(previous))
        feedback: list[dict[str, str]] = []
        previous_payload: Any = previous.model_dump() if previous else None
        repair_candidate: CandidatePayload | None = None
        solution_repairs = schema_failures = 0
        last_code = "GENERATION_INVALID"
        try:
            async with asyncio.timeout_at(context.deadline):
                for attempt in range(1, self.MAX_ATTEMPTS + 1):
                    result.attempts = attempt
                    prompt = build_prompt(
                        blueprint=blueprint, seed=seed, variation_modes=variation_modes,
                        feedback=feedback, previous=previous_payload,
                        repair_solution=repair_candidate is not None,
                    )
                    try:
                        response = await self.gateway.generate_content(
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                system_instruction=SYSTEM, response_mime_type="application/json",
                                # JSON Schema transport preserves Pydantic's extra=forbid.
                                # response_schema maps additionalProperties to a provider
                                # field unsupported by the Gemini endpoint in use.
                                response_json_schema=(
                                    StepByStepSolution if repair_candidate else CandidatePayload
                                ).model_json_schema(),
                                max_output_tokens=16384,
                            ),
                            context=context,
                        )
                        reply = reply_from_response(response)
                        if repair_candidate:
                            solution = parse_model_output(reply.text, StepByStepSolution)
                            candidate = repair_candidate.model_copy(update={"solution": solution})
                        else:
                            candidate = parse_model_output(reply.text, CandidatePayload)
                    except (GatewayError, ProviderError) as exc:
                        last_code = exc.code
                        if not exc.retryable or attempt == self.MAX_ATTEMPTS:
                            break
                        repair_candidate = None
                        await asyncio.sleep(min(2 ** (attempt - 1), 4))
                        continue
                    except ToolError as exc:
                        last_code = exc.code
                        schema_failures += 1
                        feedback = [{"check": "output_schema", "code": exc.code}]
                        repair_candidate = None
                        if schema_failures > 2:
                            break
                        continue

                    result.validation = await self.validator.validate(candidate, deadline=context.deadline)
                    failures = result.validation.failures
                    duplicate = candidate_identity(candidate) in excluded
                    if not failures and not duplicate and accept is not None:
                        duplicate = not await accept(candidate)
                    if not failures and not duplicate:
                        result.candidate = GeneratedQuestion(
                            **candidate.model_dump(), variant_id="var_" + uuid.uuid4().hex,
                            source_question_id=source.id, blueprint_fingerprint=fingerprint(blueprint),
                            seed=seed, solution_md=render_solution(candidate.solution),
                            has_warning=result.validation.has_warning,
                        )
                        return result
                    previous_payload = candidate.model_dump()
                    feedback = [
                        {"check": check.check_name, "code": check.status or "failed",
                         "message": (check.detail or "")[:1000]}
                        for check in failures
                    ]
                    if duplicate:
                        feedback.append({"check": "duplicate_candidate", "code": "unchanged_question"})
                    last_code = "DUPLICATE_CANDIDATE" if duplicate else "VALIDATION_FAILED"
                    solution_only = (
                        not duplicate and failures
                        and all(check.check_name in {"solution_consistency", "solution_latex"} for check in failures)
                    )
                    repair_candidate = candidate if solution_only and solution_repairs == 0 else None
                    if repair_candidate:
                        solution_repairs += 1
        except TimeoutError:
            last_code = "JOB_DEADLINE"
        except asyncio.CancelledError:
            raise
        except Exception:
            last_code = "GENERATION_INTERNAL"
        result.error_code = last_code
        return result

    async def regenerate_question(
        self, source: SourceQuestion, blueprint: dict[str, Any], previous: GeneratedQuestion, *,
        confirmed_source_hash: str, context: RequestContext, version_index: int = 1,
        variation_modes: list[str] | None = None,
        current_candidates: list[GeneratedQuestion] | None = None,
    ) -> QuestionResult:
        source = source.model_copy(deep=True)
        blueprint = deepcopy(blueprint)
        previous = previous.model_copy(deep=True)
        modes = list(variation_modes or [])
        item = self._prepare(source, blueprint, modes)
        if not confirmed_source_hash or source_fingerprint([item]) != confirmed_source_hash:
            raise ToolError("SOURCE_NOT_CONFIRMED", "Nguồn chưa được xác nhận hoặc đã thay đổi.")
        if previous.source_question_id != source.id or previous.blueprint_fingerprint != fingerprint(blueprint):
            raise ToolError("PREVIOUS_VARIANT_MISMATCH", "Câu cũ không thuộc nguồn và Blueprint này.")
        # BE supplies the current same-source candidates from the other versions.
        # Snapshot checks cannot replace a transaction-time uniqueness check in BE.
        peers = [candidate.model_copy(deep=True) for candidate in current_candidates or []]
        if any(
            candidate.source_question_id != source.id
            or candidate.blueprint_fingerprint != fingerprint(blueprint)
            for candidate in peers
        ):
            raise ToolError("PREVIOUS_VARIANT_MISMATCH", "Câu ở mã đề khác không thuộc nguồn và Blueprint này.")
        seed = (previous.seed + 1 + secrets.randbelow(2 ** 30)) % (2 ** 31)
        return await self._generate(
            source, item, blueprint, context, seed, version_index, modes, previous=previous,
            excluded_identities={candidate_identity(candidate) for candidate in peers},
        )

    async def generate_exam_drafts(
        self, sources: list[SourceQuestion], blueprints: dict[str, dict[str, Any]], *,
        confirmed_source_hash: str, n_versions: int, context: RequestContext,
        base_seed: int = 100, variation_modes: list[str] | None = None,
        completed: list[QuestionResult] | None = None, on_result: ResultCallback | None = None,
    ) -> BatchResult:
        sources = [source.model_copy(deep=True) for source in sources]
        blueprints = deepcopy(blueprints)
        modes = list(variation_modes or [])
        items = prepare_sources(sources)
        if not 1 <= n_versions <= 4:
            raise ToolError("VERSION_COUNT_INVALID", "Số mã đề phải từ 1 đến 4.")
        if not confirmed_source_hash or source_fingerprint(items) != confirmed_source_hash:
            raise ToolError("SOURCE_NOT_CONFIRMED", "Nguồn chưa được xác nhận hoặc đã thay đổi.")
        if set(blueprints) != {source.id for source in sources}:
            raise ToolError("BLUEPRINTS_NOT_READY", "Cần đủ Blueprint cho toàn bộ đề nguồn.")
        for source in sources:
            self._prepare(source, blueprints[source.id], modes)
        slots = [
            (version, index, source, base_seed + version * 1000 + index)
            for version in range(1, n_versions + 1)
            for index, source in enumerate(sources)
        ]
        cached = {(r.version_index, r.source_question_id): r.model_copy(deep=True) for r in completed or []}
        if len(cached) != len(completed or []) or not set(cached) <= {(v, s.id) for v, _, s, _ in slots}:
            raise ToolError("RESUME_MISMATCH", "Kết quả lưu không khớp các vị trí cần sinh.")
        seen: dict[str, set[str]] = {source.id: set() for source in sources}
        for version, index, source, seed in slots:
            saved = cached.get((version, source.id))
            if saved:
                expected = self._request_fingerprint(items[index], blueprints[source.id], seed, modes)
                if (
                    saved.request_fingerprint != expected or saved.candidate is None or saved.error_code
                    or saved.candidate.source_question_id != source.id
                    or saved.candidate.blueprint_fingerprint != fingerprint(blueprints[source.id])
                    or saved.validation is None or saved.validation.failures
                ):
                    raise ToolError("RESUME_MISMATCH", "Không tái dùng kết quả cũ khác nguồn/config hoặc bị lỗi.")
                identity = candidate_identity(saved.candidate)
                if identity in seen[source.id]:
                    raise ToolError("RESUME_MISMATCH", "Kết quả lưu trùng câu giữa các mã đề.")
                seen[source.id].add(identity)
        lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(3)
        results: list[QuestionResult | None] = [None] * len(slots)

        async def one(position: int, version: int, index: int, source: SourceQuestion, seed: int):
            saved = cached.get((version, source.id))
            if saved:
                results[position] = saved
                return

            async def accept(candidate: CandidatePayload) -> bool:
                async with lock:
                    identity = candidate_identity(candidate)
                    if identity in seen[source.id]:
                        return False
                    seen[source.id].add(identity)
                    return True

            async with semaphore:
                result = await self._generate(
                    source, items[index], blueprints[source.id], context,
                    seed, version, modes, accept=accept,
                )
                if on_result:
                    # Await persistence before declaring this slot complete. Failure cancels siblings.
                    await on_result(result.model_copy(deep=True))
                results[position] = result

        async with asyncio.TaskGroup() as group:
            for position, slot in enumerate(slots):
                group.create_task(one(position, *slot))
        ordered = [result for result in results if result is not None]
        count = sum(result.candidate is not None for result in ordered)
        status: Literal["generated", "partial_generated", "failed"] = (
            "generated" if count == len(slots) else "partial_generated" if count else "failed"
        )
        return BatchResult(results=ordered, status=status)

"""TASK-207b adapter for committed 005/015/016 and PR #52's 017 RPCs."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.core.database import get_service_role_client
from app.models.generation import QuestionResult
from app.models.schemas import SourceQuestion
from app.services.generation.ai_batch_adapter import AIBatchInputs
from app.services.generation.ai_mapping import PreparedAIResult
from app.services.generation.job_contracts import (
    GenerationJobError,
    GenerationPlan,
    GenerationQuotaExceeded,
    QuestionTarget,
)
from app.services.generation.mode_mapper import PUBLIC_TO_CANONICAL_DIMENSIONS


@dataclass(frozen=True, slots=True)
class CloneJobInputs:
    snapshot_id: UUID
    context: dict[str, Any]


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Malformed generation RPC object.")
    return cast(dict[str, Any], value)


def _array(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Malformed generation RPC array.")
    return cast(list[Any], value)


def _uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("Malformed generation UUID.")
    return UUID(value)


def _check_frozen_config(config: dict[str, Any], context: dict[str, Any]) -> tuple[str, ...]:
    modes = _array(config["active_variation_modes"])
    dimensions = _array(context["canonical_dimensions"])
    preferences = _object(config["ordering_preferences"])
    frozen_preferences = _object(context["ordering_preferences"])
    if (
        type(context["n_versions"]) is not int
        or config["n_versions"] != context["n_versions"]
        or modes != context["public_modes"]
        or preferences != frozen_preferences
        or any(
            type(prefs.get(key)) is not bool
            for prefs in (preferences, frozen_preferences)
            for key in ("shuffle_questions", "shuffle_options")
        )
        or context["mapping_version"] != "1.0"
    ):
        raise ValueError("Claim configuration differs from its frozen context.")
    if (
        any(not isinstance(mode, str) or mode not in PUBLIC_TO_CANONICAL_DIMENSIONS for mode in modes)
        or any(not isinstance(dimension, str) for dimension in dimensions)
        or len(modes) != len(set(modes))
        or len(dimensions) != len(set(dimensions))
        or set(dimensions) != {PUBLIC_TO_CANONICAL_DIMENSIONS[mode] for mode in modes}
    ):
        raise ValueError("Frozen public modes and AI dimensions disagree.")
    # W2 can store one alias for values and order dimensions differently from 019.
    # Keep the original order for resumed generation.
    return tuple(dimensions)


def _check_frozen_sources(context: dict[str, Any], session_id: UUID) -> list[dict[str, Any]]:
    sources = _array(context["confirmed_sources"])
    manifest = _object(context["manifest"])
    confirmation_id = _uuid(context["confirmation_id"])
    entries = _array(manifest["sources"])
    source_hash = context["confirmed_source_hash"]
    if (
        _uuid(context["session_id"]) != session_id
        or context["ready"] is not True
        or context["reason"] is not None
        or _uuid(manifest["confirmation_id"]) != confirmation_id
        or not 1 <= len(sources) <= 20
        or len(entries) != len(sources)
        or type(context["base_seed"]) is not int
        or not isinstance(source_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_hash) is None
    ):
        raise ValueError("Malformed frozen source manifest.")
    rows: list[dict[str, Any]] = []
    source_ids: set[UUID] = set()
    previous_question_no = 0
    for source, entry in zip(sources, entries, strict=True):
        row = _object(source)
        manifest_row = _object(entry)
        source_id = _uuid(row["source_question_id"])
        question_no = row["question_no"]
        if (
            source_id in source_ids
            or type(question_no) is not int
            or question_no <= previous_question_no
            or type(manifest_row["question_no"]) is not int
            or manifest_row["question_no"] != question_no
            or any(
                _uuid(row[key]) != _uuid(manifest_row[key])
                for key in ("source_question_id", "source_revision_id", "blueprint_revision_id")
            )
            or any(
                not isinstance(row[key], str) or re.fullmatch(r"[0-9a-f]{64}", row[key]) is None
                for key in ("source_fingerprint", "blueprint_fingerprint")
            )
        ):
            raise ValueError("Frozen source does not match its manifest.")
        rows.append(row)
        source_ids.add(source_id)
        previous_question_no = question_no
    if context["source_order"] != [row["source_question_id"] for row in rows]:
        raise ValueError("Frozen source order differs from its manifest.")
    return rows


def _target_from_receipt(row: dict[str, Any]) -> QuestionTarget:
    version, question_no = row["version_index"], row["question_no"]
    if type(version) is not int or type(question_no) is not int:
        raise ValueError("Malformed generation slot.")
    return QuestionTarget(_uuid(row["source_question_id"]), question_no, version)


def _rpc_error(exc: APIError) -> GenerationJobError:
    code = str(getattr(exc, "code", "") or "").upper()
    message = str(getattr(exc, "message", "") or "")
    if code == "P0002":
        return GenerationJobError(404, "ERR_SESSION_NOT_FOUND", "Session not found.")
    if code == "42501":
        return GenerationJobError(403, "ERR_FORBIDDEN", "Access denied.")
    if code == "55006":
        return GenerationJobError(
            409, "ERR_CONFIG_CONFLICT", "Generation state changed; reload the session."
        )
    if code == "22023" and message.startswith("ERR_SOURCE_NOT_READY"):
        return GenerationJobError(422, "ERR_SOURCE_NOT_READY", "The source is not ready.")
    if code == "22023" and message.startswith("ERR_CONFIG_CONFLICT"):
        return GenerationJobError(
            409, "ERR_CONFIG_CONFLICT", "Generation input conflicts with its snapshot."
        )
    return GenerationJobError(
        503, "ERR_GENERATION_STORAGE_FAILURE", "Generation storage is temporarily unavailable."
    )


class GenerationJobRepository:
    """Claim with the owner's JWT; perform fenced worker mutations as service_role.

    The synchronous Supabase client is isolated in a threadpool. Every write is
    a single RPC. A lost write response is never retried by this adapter.
    """

    def __init__(self, owner_db: Client) -> None:
        self._owner_db = owner_db
        self._worker_db = get_service_role_client()

    async def _rpc(self, name: str, params: dict[str, object], *, worker: bool = True) -> object:
        db = self._worker_db if worker else self._owner_db
        try:
            return await run_in_threadpool(lambda: db.rpc(name, params).execute().data)
        except APIError as exc:
            raise _rpc_error(exc) from exc
        except Exception as exc:
            raise GenerationJobError(
                503,
                "ERR_GENERATION_STORAGE_FAILURE",
                "Generation storage is temporarily unavailable.",
            ) from exc

    async def claim(self, session_id: UUID, *, retry: bool) -> GenerationPlan:
        try:
            receipt = _object(
                await self._rpc(
                    "claim_generation_job",
                    {"p_session_id": str(session_id), "p_is_retry": retry},
                    worker=False,
                )
            )
            if (
                _uuid(receipt["session_id"]) != session_id
                or receipt["status"] != "generating"
            ):
                raise ValueError("Claim session or status changed.")
            job_id = _uuid(receipt["job_id"])
            snapshot_id = _uuid(receipt["snapshot_id"])
            context = _object(receipt["context"])
            config = _object(receipt["config"])
            n_versions = config["n_versions"]
            count = receipt["gemini_call_count"]
            if type(n_versions) is not int or not 1 <= n_versions <= 4:
                raise ValueError("Invalid frozen version count.")
            if type(count) is not int or not 0 <= count <= 250:
                raise ValueError("Invalid durable quota count.")
            dimensions = _check_frozen_config(config, context)
            sources = _check_frozen_sources(context, session_id)
            targets: list[QuestionTarget] = []
            source_models: list[SourceQuestion] = []
            blueprints: dict[str, dict[str, Any]] = {}
            for row in sources:
                source_id = _uuid(row["source_question_id"])
                question_no = row["question_no"]
                confirmed = _object(row["confirmed_input"])
                source_model = SourceQuestion.model_validate(confirmed)
                if source_model.id != str(source_id):
                    raise ValueError("Frozen source ID differs from confirmed input.")
                source_models.append(source_model)
                blueprints[str(source_id)] = _object(row["canonical_blueprint"])
                for version in range(1, n_versions + 1):
                    targets.append(QuestionTarget(source_id, question_no, version))
            loaded = _object(
                await self._rpc("load_generation_completed_results", {"p_session_id": str(session_id)})
            )
            if (
                _uuid(loaded["session_id"]) != session_id
                or _uuid(loaded["snapshot_id"]) != snapshot_id
                or loaded["context"] != context
            ):
                raise ValueError("Loaded results belong to another frozen snapshot.")
            target_set = set(targets)
            source_positions = {
                _uuid(row["source_question_id"]): index for index, row in enumerate(sources)
            }
            clone_mode = not dimensions
            result_kind = "ORIGINAL_CLONE" if clone_mode else "AI_RESULT"
            claimed: set[QuestionTarget] = set()
            for value in _array(receipt["committed_targets"]):
                row = _object(value)
                target = _target_from_receipt(row)
                if target not in target_set or target in claimed or row["result_kind"] != result_kind:
                    raise ValueError("Claimed result is outside the frozen job.")
                claimed.add(target)
            saved: set[QuestionTarget] = set()
            ai_completed: list[QuestionResult] = []
            for row_value in _array(loaded["completed"]):
                row = _object(row_value)
                target = _target_from_receipt(row)
                if target not in claimed or target in saved or _uuid(row["snapshot_id"]) != snapshot_id:
                    raise ValueError("Committed target is outside frozen snapshot.")
                if row["result_kind"] != result_kind:
                    raise ValueError("Committed result kind differs from frozen modes.")
                saved.add(target)
                if not clone_mode:
                    result = QuestionResult.model_validate(row["raw_result"])
                    candidate = result.candidate
                    position = source_positions[target.source_question_id]
                    if (
                        candidate is None
                        or result.error_code is not None
                        or result.request_fingerprint != row["request_fingerprint"]
                        or result.version_index != target.version_index
                        or _uuid(result.source_question_id) != target.source_question_id
                        or _uuid(candidate.source_question_id) != target.source_question_id
                        or candidate.seed != context["base_seed"] + target.version_index * 1000 + position
                        or candidate.blueprint_fingerprint != sources[position]["blueprint_fingerprint"]
                    ):
                        raise ValueError("Committed AI result differs from its frozen slot.")
                    ai_completed.append(result)
            if claimed != saved:
                raise ValueError("Claim and completed results disagree.")
            if clone_mode:
                inputs: object = CloneJobInputs(snapshot_id, deepcopy(context))
            else:
                inputs = AIBatchInputs(
                    sources=tuple(source_models),
                    blueprints=blueprints,
                    confirmed_source_hash=context["confirmed_source_hash"],
                    base_seed=context["base_seed"],
                    variation_modes=dimensions,
                    completed=tuple(ai_completed),
                    snapshot_id=snapshot_id,
                )
            return GenerationPlan(
                session_id, job_id, tuple(targets), frozenset(saved), count, inputs
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GenerationJobError(
                503, "ERR_GENERATION_STORAGE_FAILURE", "Generation snapshot could not be verified."
            ) from exc

    async def reserve_gemini_call(self, plan: GenerationPlan) -> int:
        try:
            receipt = _object(
                await self._rpc(
                    "reserve_generation_quota",
                    {
                        "p_session_id": str(plan.session_id),
                        "p_calls_requested": 1,
                        "p_job_token": str(plan.job_id),
                    },
                )
            )
            if (
                _uuid(receipt["session_id"]) != plan.session_id
                or _uuid(receipt["job_id"]) != plan.job_id
                or receipt["reserved_calls"] != 1
            ):
                raise ValueError("Quota receipt identity changed.")
            count = receipt["new_total_calls"]
            if type(count) is not int or not 1 <= count <= 250:
                raise ValueError("Invalid quota receipt.")
            return count
        except GenerationJobError as exc:
            if isinstance(exc.__cause__, APIError) and str(exc.__cause__.code) == "54000":
                raise GenerationQuotaExceeded("Gemini session quota exhausted.") from exc
            raise
        except (KeyError, ValueError, TypeError) as exc:
            raise GenerationJobError(
                503, "ERR_GENERATION_STORAGE_FAILURE", "Invalid quota receipt."
            ) from exc

    async def save_result(self, plan: GenerationPlan, result: object) -> None:
        if not isinstance(result, PreparedAIResult):
            raise TypeError("Expected a prepared full AI result.")
        raw = result.raw_result
        draft = result.draft
        if result.target in plan.saved or result.target not in plan.targets:
            raise ValueError("AI attempted to write a saved or foreign target.")
        inputs = plan.inputs
        if not isinstance(inputs, AIBatchInputs):
            raise TypeError("AI result requires a frozen AI batch snapshot.")
        source_index = next(
            (
                index
                for index, source in enumerate(inputs.sources)
                if source.id == str(result.target.source_question_id)
            ),
            None,
        )
        if source_index is None:
            raise ValueError("AI target is outside job snapshot.")
        seed = inputs.base_seed + result.target.version_index * 1000 + source_index
        params: dict[str, object] = {
            "p_session_id": str(plan.session_id),
            "p_job_token": str(plan.job_id),
            "p_version_index": result.target.version_index,
            "p_source_question_id": str(result.target.source_question_id),
            "p_question_no": result.target.question_no,
            "p_is_success": draft is not None,
            "p_error_code": raw.error_code,
            "p_attempts": raw.attempts,
            "p_seed": seed,
            "p_request_fingerprint": raw.request_fingerprint,
            "p_raw_result": raw.model_dump(mode="json"),
            "p_content": draft.content if draft else None,
            "p_options": [draft.options[key] for key in "ABCD"] if draft else None,
            "p_correct_key": draft.correct_key if draft else None,
            "p_solution_md": draft.solution_md if draft else None,
            "p_has_warning": draft.has_warning if draft else False,
        }
        receipt = _object(await self._rpc("persist_generation_result", params))
        if (
            receipt.get("success") is not True
            or _uuid(receipt.get("session_id")) != plan.session_id
            or _uuid(receipt.get("snapshot_id")) != _snapshot_id(plan)
            or receipt.get("version_index") != result.target.version_index
            or _uuid(receipt.get("source_question_id")) != result.target.source_question_id
        ):
            raise GenerationJobError(
                503, "ERR_GENERATION_STORAGE_FAILURE", "Invalid result receipt."
            )

    async def save_clone(self, plan: GenerationPlan, target: QuestionTarget) -> None:
        inputs = plan.inputs
        if not isinstance(inputs, CloneJobInputs):
            raise ValueError("Clone requires a frozen clone snapshot.")
        if target in plan.saved or target not in plan.targets:
            raise ValueError("Clone attempted to write a saved or foreign target.")
        sources = _array(inputs.context["confirmed_sources"])
        index, source = next(
            (
                (i, _object(row))
                for i, row in enumerate(sources)
                if row["source_question_id"] == str(target.source_question_id)
            ),
            (None, None),
        )
        if index is None or source is None or source["question_no"] != target.question_no:
            raise ValueError("Clone target is outside frozen source order.")
        confirmed = _object(source["confirmed_input"])
        record = {
            "result_kind": "ORIGINAL_CLONE",
            "snapshot_id": str(inputs.snapshot_id),
            "version_index": target.version_index,
            "source_question_id": str(target.source_question_id),
            "question_no": target.question_no,
            "source_revision_id": source["source_revision_id"],
            "source_fingerprint": source["source_fingerprint"],
            "blueprint_revision_id": source["blueprint_revision_id"],
            "confirmed_source_hash": inputs.context["confirmed_source_hash"],
            "seed": inputs.context["base_seed"] + target.version_index * 1000 + index,
            "content": confirmed["question_text"],
            "options": confirmed["options"],
            "correct_key": confirmed["correct_answer"],
            "solution_md": confirmed.get("solution"),
        }
        receipt = _object(
            await self._rpc(
                "persist_generation_clone",
                {
                    "p_session_id": str(plan.session_id),
                    "p_job_token": str(plan.job_id),
                    "p_clone_record": record,
                },
            )
        )
        if (
            receipt.get("success") is not True
            or receipt.get("result_kind") != "ORIGINAL_CLONE"
            or _uuid(receipt.get("session_id")) != plan.session_id
            or _uuid(receipt.get("snapshot_id")) != inputs.snapshot_id
            or receipt.get("version_index") != target.version_index
            or _uuid(receipt.get("source_question_id")) != target.source_question_id
        ):
            raise GenerationJobError(
                503, "ERR_GENERATION_STORAGE_FAILURE", "Invalid clone receipt."
            )

    async def finish(self, plan: GenerationPlan, outcome: str, *, error_code: str | None) -> None:
        with_error = outcome in {"failed", "partial_generated"}
        if with_error and (
            error_code is None or re.fullmatch(r"[A-Z0-9_]{3,64}", error_code) is None
        ):
            raise ValueError("A failed or partial job requires a valid durable error code.")
        rpc_name = "finish_generation_job_with_error" if with_error else "finish_generation_job"
        params: dict[str, object] = {
            "p_session_id": str(plan.session_id),
            "p_outcome": outcome,
            "p_job_token": str(plan.job_id),
        }
        if with_error:
            params["p_error_code"] = error_code
        receipt = _object(await self._rpc(rpc_name, params))
        if (
            _uuid(receipt.get("session_id")) != plan.session_id
            or receipt.get("status") != outcome
            or _uuid(receipt.get("snapshot_id")) != _snapshot_id(plan)
            or (with_error and receipt.get("generation_error_code") != error_code)
        ):
            raise GenerationJobError(
                503, "ERR_GENERATION_STORAGE_FAILURE", "Invalid finish receipt."
            )

    async def fail_stale(self, session_id: UUID, *, cutoff: datetime) -> bool:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("Stale cutoff must have a timezone.")
        seconds = max(1, int((datetime.now(timezone.utc) - cutoff).total_seconds()))
        receipt = _object(
            await self._rpc(
                "fail_stale_generation_job",
                {
                    "p_session_id": str(session_id),
                    "p_cutoff_seconds": seconds,
                },
            )
        )
        if (
            _uuid(receipt.get("session_id")) != session_id
            or type(receipt.get("stale_job_recovered")) is not bool
        ):
            raise GenerationJobError(
                503, "ERR_GENERATION_STORAGE_FAILURE", "Invalid recovery receipt."
            )
        return cast(bool, receipt["stale_job_recovered"])

    async def save_draft(self, plan: GenerationPlan, target: QuestionTarget, draft: object) -> None:
        raise NotImplementedError("Product jobs persist full QuestionResult through save_result.")


def _snapshot_id(plan: GenerationPlan) -> UUID:
    inputs = plan.inputs
    if isinstance(inputs, CloneJobInputs):
        return inputs.snapshot_id
    if isinstance(inputs, AIBatchInputs):
        if inputs.snapshot_id is None:
            raise ValueError("AI snapshot identity is missing.")
        return inputs.snapshot_id
    raise ValueError("Unknown generation inputs.")

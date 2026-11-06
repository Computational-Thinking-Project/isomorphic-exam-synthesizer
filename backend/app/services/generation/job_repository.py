"""TASK-207b adapter for the committed 005/015/016 generation RPCs."""

from __future__ import annotations

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
        receipt = _object(
            await self._rpc(
                "claim_generation_job",
                {"p_session_id": str(session_id), "p_is_retry": retry},
                worker=False,
            )
        )
        loaded = _object(
            await self._rpc("load_generation_completed_results", {"p_session_id": str(session_id)})
        )
        try:
            if (
                _uuid(receipt["session_id"]) != session_id
                or _uuid(loaded["session_id"]) != session_id
            ):
                raise ValueError("Claim session changed.")
            job_id = _uuid(receipt["job_id"])
            snapshot_id = _uuid(receipt["snapshot_id"])
            if _uuid(loaded["snapshot_id"]) != snapshot_id:
                raise ValueError("Loaded results belong to another snapshot.")
            context = _object(receipt["context"])
            if loaded["context"] != context:
                raise ValueError("Frozen generation context changed during claim.")
            config = _object(receipt["config"])
            sources = _array(context["confirmed_sources"])
            n_versions = config["n_versions"]
            count = receipt["gemini_call_count"]
            if type(n_versions) is not int or not 1 <= n_versions <= 4:
                raise ValueError("Invalid frozen version count.")
            if type(count) is not int or not 0 <= count <= 250:
                raise ValueError("Invalid durable quota count.")
            targets: list[QuestionTarget] = []
            source_models: list[SourceQuestion] = []
            blueprints: dict[str, dict[str, Any]] = {}
            for row_value in sources:
                row = _object(row_value)
                source_id = _uuid(row["source_question_id"])
                question_no = row["question_no"]
                if type(question_no) is not int or question_no < 1:
                    raise ValueError("Invalid frozen source order.")
                confirmed = _object(row["confirmed_input"])
                source_model = SourceQuestion.model_validate(confirmed)
                if source_model.id != str(source_id):
                    raise ValueError("Frozen source ID differs from confirmed input.")
                source_models.append(source_model)
                blueprints[str(source_id)] = _object(row["canonical_blueprint"])
                for version in range(1, n_versions + 1):
                    targets.append(QuestionTarget(source_id, question_no, version))
            if len(sources) != len({row.id for row in source_models}):
                raise ValueError("Duplicate frozen source.")
            completed_rows = _array(loaded["completed"])
            committed_rows = _array(receipt["committed_targets"])
            saved: set[QuestionTarget] = set()
            ai_completed: list[QuestionResult] = []
            public_modes = _array(config["active_variation_modes"])
            dimensions = _array(context["canonical_dimensions"])
            if (not public_modes) != (not dimensions):
                raise ValueError("Frozen public modes and AI dimensions disagree.")
            clone_mode = not public_modes
            for row_value in completed_rows:
                row = _object(row_value)
                target = next(
                    (
                        target
                        for target in targets
                        if target.version_index == row["version_index"]
                        and str(target.source_question_id) == row["source_question_id"]
                        and target.question_no == row["question_no"]
                    ),
                    None,
                )
                if target is None or target in saved or _uuid(row["snapshot_id"]) != snapshot_id:
                    raise ValueError("Committed target is outside frozen snapshot.")
                if row["result_kind"] != ("ORIGINAL_CLONE" if clone_mode else "AI_RESULT"):
                    raise ValueError("Committed result kind differs from frozen modes.")
                saved.add(target)
                if not clone_mode:
                    result = QuestionResult.model_validate(row["raw_result"])
                    if result.request_fingerprint != row["request_fingerprint"]:
                        raise ValueError("Committed AI fingerprint changed.")
                    ai_completed.append(result)
            claim_saved = {
                (row["version_index"], row["source_question_id"], row["question_no"])
                for row in map(_object, committed_rows)
            }
            loaded_saved = {
                (t.version_index, str(t.source_question_id), t.question_no) for t in saved
            }
            if claim_saved != loaded_saved:
                raise ValueError("Claim and completed results disagree.")
            if clone_mode:
                inputs: object = CloneJobInputs(snapshot_id, deepcopy(context))
            else:
                inputs = AIBatchInputs(
                    sources=tuple(source_models),
                    blueprints=blueprints,
                    confirmed_source_hash=context["confirmed_source_hash"],
                    base_seed=context["base_seed"],
                    variation_modes=tuple(dimensions),
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
        source_index = next(
            (
                index
                for index, target in enumerate(plan.targets)
                if target.version_index == 1
                and target.source_question_id == result.target.source_question_id
            ),
            None,
        )
        if source_index is None:
            raise ValueError("AI target is outside job snapshot.")
        seed = (
            cast(AIBatchInputs, plan.inputs).base_seed
            + result.target.version_index * 1000
            + source_index
        )
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
        receipt = _object(
            await self._rpc(
                "finish_generation_job",
                {
                    "p_session_id": str(plan.session_id),
                    "p_outcome": outcome,
                    "p_job_token": str(plan.job_id),
                },
            )
        )
        if (
            _uuid(receipt.get("session_id")) != plan.session_id
            or receipt.get("status") != outcome
            or _uuid(receipt.get("snapshot_id")) != _snapshot_id(plan)
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

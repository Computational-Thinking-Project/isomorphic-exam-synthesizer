"""Confirmed source -> canonical Blueprint publication using worker-only RPCs.

Public routes derive the actor from verified authentication. The worker is a
separate server capability: owner JWTs cannot submit arbitrary hashes/documents.
No transaction spans extraction, and a publication retains its revision on retry.
"""

import asyncio
from copy import deepcopy
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)
from supabase import Client

from app.models.schemas import ReviewDomainException, SourceQuestion
from app.services.ai.gateway import RequestContext
from app.services.blueprint.adapters import source_to_item
from app.services.blueprint.artifacts import prepare_blueprint_artifact, prepare_source_artifacts
from app.services.blueprint.common import ToolError
from app.services.blueprint.service import BlueprintService
from app.services.review.receipts import rpc_object


class SourceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_question_id: UUID
    source_revision_id: UUID
    confirmed_input: dict[str, Any]
    source_fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class SourceConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_id: UUID
    session_id: UUID
    actor_id: UUID
    confirmed_at: AwareDatetime
    status: Literal["blueprinted"]
    total_questions: Annotated[StrictInt, Field(ge=1, le=20)]
    total_blueprints: Annotated[StrictInt, Field(ge=0, le=20)]
    # Older confirmation receipts counted legacy rows. They must not imply ready;
    # only get_source_artifacts' current canonical heads establish readiness.
    canonical_status: Literal["pending"] = "pending"
    replayed: StrictBool
    sources: list[SourceArtifact]

    @model_validator(mode="after")
    def consistent(self) -> "SourceConfirmation":
        if len(self.sources) != self.total_questions or self.total_blueprints > self.total_questions:
            raise ValueError("Confirmation counts do not match its sources")
        if len({s.source_question_id for s in self.sources}) != self.total_questions:
            raise ValueError("Duplicate source artifact")
        return self


class BlueprintPublication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    source_question_id: UUID
    source_revision_id: UUID
    blueprint_revision_id: UUID
    replayed: StrictBool


class SourceArtifactState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: SourceConfirmation
    pending_source_question_ids: list[UUID]
    ready: StrictBool


def artifact_error(exc: Exception) -> ReviewDomainException:
    message = str(exc)
    for database_code, status, public_code in (
        ("ARTIFACT_OWNER_MISMATCH", 403, "ERR_FORBIDDEN"),
        ("ARTIFACT_IDEMPOTENCY_CONFLICT", 409, "ERR_IDEMPOTENCY_CONFLICT"),
        ("ARTIFACT_SOURCE_MISMATCH", 409, "ERR_SOURCE_CHANGED"),
        ("ARTIFACT_STALE", 409, "ERR_SOURCE_CHANGED"),
        ("ARTIFACT_LOCKED", 423, "ERR_SESSION_LOCKED"),
        ("ARTIFACT_INVALID_PAYLOAD", 422, "ERR_SOURCE_ARTIFACT_INVALID"),
        ("P0002", 404, "ERR_SESSION_NOT_FOUND"),
    ):
        if database_code in message:
            return ReviewDomainException(status, public_code, "Source artifact operation refused")
    return ReviewDomainException(
        503, "ERR_ARTIFACT_OUTCOME_UNCERTAIN", "Artifact result unavailable; retry the same action"
    )


class SourceArtifactRepository:
    def __init__(self, worker: Client):
        self.worker = worker

    async def _call(self, name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if self.worker is None or not callable(getattr(self.worker, "rpc", None)):
            raise ReviewDomainException(503, "ERR_ARTIFACT_UNAVAILABLE", "Artifact worker unavailable")
        try:
            result = self.worker.rpc(name, deepcopy(parameters)).execute()
        except Exception as exc:
            raise artifact_error(exc) from exc
        return rpc_object(result.data)

    async def confirm(
        self, session_id: str, actor_id: str, confirmation_id: UUID,
        expected_updated_at: str, prepared: list[dict[str, Any]],
    ) -> SourceConfirmation:
        expected = {p["source_question_id"]: p for p in prepared}
        data = await self._call("confirm_source_artifacts", {
            "p_session_id": session_id,
            "p_actor_id": actor_id,
            "p_confirmation_id": str(confirmation_id),
            "p_expected_updated_at": expected_updated_at,
            "p_sources": prepared,
        })
        try:
            receipt = SourceConfirmation.model_validate(data)
            if (receipt.session_id, receipt.actor_id, receipt.confirmation_id) != (
                UUID(session_id), UUID(actor_id), confirmation_id,
            ) or receipt.total_questions != len(prepared) or (not receipt.replayed and receipt.total_blueprints != 0):
                raise ValueError("Confirmation identity/count mismatch")
            if len(receipt.sources) != len(expected) or len({s.source_question_id for s in receipt.sources}) != len(expected):
                raise ValueError("Confirmation source set mismatch")
            for source in receipt.sources:
                requested = expected[str(source.source_question_id)]
                if source.confirmed_input != requested["confirmed_input"] or source.source_fingerprint != requested["source_fingerprint"]:
                    raise ValueError("Confirmation content mismatch")
                if not receipt.replayed and str(source.source_revision_id) != requested["source_revision_id"]:
                    raise ValueError("New confirmation revision mismatch")
            return receipt
        except (ValueError, KeyError, TypeError) as exc:
            raise ReviewDomainException(
                503, "ERR_ARTIFACT_OUTCOME_UNCERTAIN", "Source confirmation could not be confirmed"
            ) from exc

    async def publish(self, session_id: UUID, publication: dict[str, Any]) -> BlueprintPublication:
        # One validated canonical output is retried with its original UUID/body;
        # never invoke the provider again just because publication lost a response.
        for attempt in range(3):
            try:
                data = await self._call("publish_canonical_blueprint", {
                    "p_session_id": str(session_id), "p_publication": publication,
                })
                receipt = BlueprintPublication.model_validate(data)
                if receipt.session_id != session_id or any(
                    str(getattr(receipt, key)) != publication[key]
                    for key in ("source_question_id", "source_revision_id", "blueprint_revision_id")
                ):
                    raise ValueError("Publication identity mismatch")
                return receipt
            except (ValueError, KeyError, TypeError) as exc:
                error = ReviewDomainException(
                    503, "ERR_ARTIFACT_OUTCOME_UNCERTAIN", "Publication could not be confirmed"
                )
                if attempt == 2:
                    raise error from exc
            except ReviewDomainException as exc:
                if exc.status_code != 503 or attempt == 2:
                    raise
            await asyncio.sleep(0.1 * 2**attempt)
        raise AssertionError("Publication retry loop did not return")

    async def load(self, session_id: str) -> SourceArtifactState:
        data = await self._call("get_source_artifacts", {"p_session_id": session_id})
        try:
            state = SourceArtifactState.model_validate(data)
            pending = set(state.pending_source_question_ids)
            if state.confirmation.session_id != UUID(session_id) or len(pending) != len(state.pending_source_question_ids):
                raise ValueError("Artifact state identity mismatch")
            if not pending <= {s.source_question_id for s in state.confirmation.sources} or state.ready != (not pending):
                raise ValueError("Artifact readiness mismatch")
            return state
        except (ValueError, TypeError) as exc:
            raise ReviewDomainException(
                503, "ERR_ARTIFACT_OUTCOME_UNCERTAIN", "Artifact state could not be confirmed"
            ) from exc


class ConfirmedArtifactProducer:
    def __init__(self, repository: SourceArtifactRepository, blueprints: BlueprintService | None):
        self.repository = repository
        self.blueprints = blueprints

    async def confirm(
        self, session_id: str, actor_id: str, confirmation_id: UUID,
        expected_updated_at: str, source_rows: list[dict[str, Any]],
    ) -> SourceConfirmation:
        prepared = prepare_source_artifacts(session_id, source_rows)
        return await self.repository.confirm(
            session_id, actor_id, confirmation_id, expected_updated_at, prepared
        )

    async def produce(
        self, confirmation: SourceConfirmation, context: RequestContext,
        source_ids: set[UUID] | None = None,
    ) -> list[BlueprintPublication]:
        if self.blueprints is None:
            raise ReviewDomainException(503, "ERR_AI_SERVICE_UNAVAILABLE", "Blueprint producer unavailable")
        # Snapshot before the first await; the writer still compares the persisted
        # revision under lock after AI, including edits followed by text reversion.
        receipt = confirmation.model_copy(deep=True)
        if source_ids is not None and not source_ids <= {s.source_question_id for s in receipt.sources}:
            raise ReviewDomainException(409, "ERR_SOURCE_CHANGED", "Unknown source revision")
        published = []
        for artifact in receipt.sources:
            if source_ids is not None and artifact.source_question_id not in source_ids:
                continue
            source = SourceQuestion.model_validate(artifact.confirmed_input, strict=True)
            results, _ = await self.blueprints.extract_confirmed(
                [source_to_item(source)], confirmed_source_hash=artifact.source_fingerprint,
                context=context,
            )
            if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict) or results[0].get("error") or not isinstance(results[0].get("blueprint"), dict):
                raise ToolError("BLUEPRINT_PRODUCTION_FAILED", "Chưa tạo được canonical Blueprint hợp lệ.")
            publication = prepare_blueprint_artifact(
                artifact.model_dump(mode="json"), results[0]["blueprint"]
            )
            published.append(await self.repository.publish(receipt.session_id, publication))
        return published

    async def resume(self, session_id: str, context: RequestContext) -> list[BlueprintPublication]:
        state = await self.repository.load(session_id)
        if state.ready:
            return []
        return await self.produce(state.confirmation, context, set(state.pending_source_question_ids))

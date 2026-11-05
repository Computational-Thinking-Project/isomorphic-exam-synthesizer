"""Confirmed source -> canonical Blueprint publication using worker-only RPCs.

Public routes derive the actor from verified authentication. The worker is a
separate server capability: owner JWTs cannot submit arbitrary hashes/documents.
No transaction spans extraction, and a publication retains its revision on retry.
"""

import asyncio
import time
from copy import deepcopy
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

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


class SourceProductionState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_question_id: UUID
    source_revision_id: UUID
    status: Literal["pending", "running", "ready", "failed"]
    expires_at: AwareDatetime | None
    error_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")] | None


class SourceArtifactState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: SourceConfirmation
    pending_source_question_ids: list[UUID]
    ready: StrictBool
    production: list[SourceProductionState] = Field(default_factory=list)
    supported_modes: list[str] | None = None


class SourceProductionClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    source_question_id: UUID
    source_revision_id: UUID
    producer_job_id: UUID
    status: Literal["claimed", "busy", "ready"]
    expires_at: AwareDatetime | None


def artifact_error(exc: Exception, *, confirmation: bool = False) -> ReviewDomainException:
    message = str(exc)
    for database_code, status, public_code in (
        ("ARTIFACT_OWNER_MISMATCH", 403, "ERR_FORBIDDEN"),
        ("ARTIFACT_IDEMPOTENCY_CONFLICT", 409, "ERR_IDEMPOTENCY_CONFLICT"),
        ("ARTIFACT_SOURCE_MISMATCH", 409, "ERR_SOURCE_CHANGED"),
        (
            "ARTIFACT_STALE",
            409,
            "ERR_SOURCE_REVISION_CONFLICT" if confirmation else "ERR_SOURCE_CHANGED",
        ),
        ("ARTIFACT_LOCKED", 423, "ERR_SESSION_LOCKED"),
        ("ARTIFACT_INVALID_PAYLOAD", 422, "ERR_SOURCE_ARTIFACT_INVALID"),
        ("P0002", 404, "ERR_SESSION_NOT_FOUND"),
    ):
        if database_code in message:
            return ReviewDomainException(status, public_code, "Source artifact operation refused")
    if confirmation:
        from app.services.parser.ingestion_service import (
            is_database_rollback_evidence,
            is_network_timeout,
            is_network_transport,
        )

        if is_network_timeout(exc) or is_network_transport(exc):
            return ReviewDomainException(504, "ERR_ARTIFACT_OUTCOME_UNCERTAIN", "Confirmation outcome uncertain; retry the same key")
        if is_database_rollback_evidence(exc):
            return ReviewDomainException(500, "ERR_SOURCE_CONFIRMATION_FAILED", "Source confirmation transaction rolled back")
        return ReviewDomainException(500, "ERR_ARTIFACT_OUTCOME_UNCERTAIN", "Confirmation outcome uncertain; retry the same key")
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
            raise artifact_error(exc, confirmation=name == "confirm_source_artifacts") from exc
        return rpc_object(result.data)

    async def confirm(
        self, session_id: str, actor_id: str, confirmation_id: UUID,
        expected_source_revision: str, prepared: list[dict[str, Any]],
    ) -> SourceConfirmation:
        expected = {p["source_question_id"]: p for p in prepared}
        data = await self._call("confirm_source_artifacts", {
            "p_session_id": session_id,
            "p_actor_id": actor_id,
            "p_confirmation_id": str(confirmation_id),
            "p_expected_source_revision": expected_source_revision,
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
            if state.production:
                revisions = {s.source_question_id: s.source_revision_id for s in state.confirmation.sources}
                if len(state.production) != len(revisions) or {s.source_question_id for s in state.production} != set(revisions):
                    raise ValueError("Producer state source set mismatch")
                for item in state.production:
                    if item.source_revision_id != revisions[item.source_question_id] or (item.status == "ready") != (item.source_question_id not in pending):
                        raise ValueError("Producer state revision/readiness mismatch")
                    if item.status == "running" and item.expires_at is None:
                        raise ValueError("Running producer lacks lease")
                    if item.status == "failed" and item.error_code is None:
                        raise ValueError("Failed producer lacks error code")
            return state
        except (ValueError, TypeError) as exc:
            raise ReviewDomainException(
                503, "ERR_ARTIFACT_OUTCOME_UNCERTAIN", "Artifact state could not be confirmed"
            ) from exc

    async def claim(self, session_id: UUID, source: SourceArtifact, job_id: UUID) -> SourceProductionClaim:
        for attempt in range(3):
            try:
                data = await self._call("claim_source_production", {
                    "p_session_id": str(session_id), "p_source_revision_id": str(source.source_revision_id),
                    "p_job_id": str(job_id),
                })
                claim = SourceProductionClaim.model_validate(data)
                if (claim.session_id, claim.source_question_id, claim.source_revision_id, claim.producer_job_id) != (
                    session_id, source.source_question_id, source.source_revision_id, job_id,
                ) or (claim.status in ("claimed", "busy") and claim.expires_at is None):
                    raise ValueError("Producer claim identity/lease mismatch")
                return claim
            except (ValueError, TypeError) as exc:
                if attempt == 2:
                    raise ReviewDomainException(503, "ERR_ARTIFACT_OUTCOME_UNCERTAIN", "Producer claim unavailable") from exc
            except ReviewDomainException as exc:
                if exc.status_code != 503 or attempt == 2:
                    raise
            await asyncio.sleep(0.1 * 2**attempt)
        raise AssertionError("Claim retry did not return")

    async def fail(self, session_id: UUID, revision: UUID, job_id: UUID, code: str) -> None:
        await self._call("fail_source_production", {
            "p_session_id": str(session_id), "p_source_revision_id": str(revision),
            "p_job_id": str(job_id), "p_error_code": code,
        })


class ConfirmedArtifactProducer:
    def __init__(self, repository: SourceArtifactRepository, blueprints: BlueprintService | None):
        self.repository = repository
        self.blueprints = blueprints

    async def confirm(
        self, session_id: str, actor_id: str, confirmation_id: UUID,
        expected_source_revision: str, source_rows: list[dict[str, Any]],
    ) -> SourceConfirmation:
        prepared = prepare_source_artifacts(session_id, source_rows)
        return await self.repository.confirm(
            session_id, actor_id, confirmation_id, expected_source_revision, prepared
        )

    async def produce(
        self, confirmation: SourceConfirmation, context: RequestContext,
        source_ids: set[UUID] | None = None,
    ) -> list[BlueprintPublication]:
        blueprints = self.blueprints
        if blueprints is None:
            raise ReviewDomainException(503, "ERR_AI_SERVICE_UNAVAILABLE", "Blueprint producer unavailable")
        # Snapshot before the first await; the writer still compares the persisted
        # revision under lock after AI, including edits followed by text reversion.
        receipt = confirmation.model_copy(deep=True)
        if source_ids is not None and not source_ids <= {s.source_question_id for s in receipt.sources}:
            raise ReviewDomainException(409, "ERR_SOURCE_CHANGED", "Unknown source revision")
        semaphore = asyncio.Semaphore(3)

        async def one(artifact: SourceArtifact) -> BlueprintPublication | None:
            if source_ids is not None and artifact.source_question_id not in source_ids:
                return None
            async with semaphore:
                job_id = uuid4()
                claim = await self.repository.claim(receipt.session_id, artifact, job_id)
                if claim.status != "claimed":
                    return None
                try:
                    source = SourceQuestion.model_validate(artifact.confirmed_input, strict=True)
                    item_context = RequestContext(min(context.deadline, time.monotonic()+360), context.reserve_request)
                    async with asyncio.timeout_at(item_context.deadline):
                        results, _ = await blueprints.extract_confirmed(
                            [source_to_item(source)], confirmed_source_hash=artifact.source_fingerprint,
                            context=item_context,
                        )
                    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict) or results[0].get("error") or not isinstance(results[0].get("blueprint"), dict):
                        raise ToolError("BLUEPRINT_PRODUCTION_FAILED", "Chưa tạo được canonical Blueprint hợp lệ.")
                    publication = prepare_blueprint_artifact(artifact.model_dump(mode="json"), results[0]["blueprint"])
                    publication.update(producer_job_id=str(job_id), blueprint_revision_id=str(job_id))
                    return await self.repository.publish(receipt.session_id, publication)
                except BaseException as exc:
                    code = "PRODUCER_CANCELLED" if isinstance(exc, asyncio.CancelledError) else "BLUEPRINT_PRODUCTION_FAILED"
                    try:
                        await asyncio.shield(self.repository.fail(receipt.session_id, artifact.source_revision_id, job_id, code))
                    except Exception:
                        pass  # Durable lease expires; do not overwrite a newer job.
                    raise

        results = await asyncio.gather(*(one(s) for s in receipt.sources), return_exceptions=True)
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            raise errors[0]
        return [r for r in results if isinstance(r, BlueprintPublication)]

    async def resume(self, session_id: str, context: RequestContext) -> list[BlueprintPublication]:
        state = await self.repository.load(session_id)
        if state.ready:
            return []
        return await self.produce(state.confirmation, context, set(state.pending_source_question_ids))

"""Source confirmation/background canonical production and read-only status."""

import logging
import time
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_service_db, get_user_db
from app.models.schemas import ConfirmSourceResponse, CurrentUser, ReviewDomainException
from app.services.ai.gateway import RequestBudget, RequestContext
from app.services.blueprint.common import ToolError
from app.services.blueprint.producer import (
    ConfirmedArtifactProducer,
    SourceArtifactRepository,
    SourceArtifactState,
    SourceProductionState,
)
from app.services.blueprint.service import BlueprintService
from app.services.review.service import action_key, resource_ids

logger = logging.getLogger(__name__)
router = APIRouter()


class SourceArtifactStatus(BaseModel):
    session_id: UUID
    ready: bool
    canonical_status: Literal["pending", "running", "ready", "failed"]
    total_questions: int
    completed_count: int
    pending_source_question_ids: list[UUID]
    production: list[SourceProductionState]
    # Q02: canonical supported generation modes derived from ready canonical Blueprint heads.
    # Empty list is valid when ready=True and no mode is supported (e.g. NONE-only blueprint).
    # None when canonical production has not completed yet (pending/running/failed).
    supported_modes: list[str] | None = None


def blueprint_service(request: Request) -> BlueprintService | None:
    runtime = getattr(request.app.state, "ai_services", None)
    keys = getattr(getattr(runtime, "settings", None), "get_gemini_api_keys", None)
    if runtime is None or not callable(keys) or not keys():
        return None
    try:
        return runtime.blueprints
    except Exception as exc:
        logger.warning("Blueprint producer unavailable (%s)", type(exc).__name__)
        return None


def status_payload(state: SourceArtifactState) -> SourceArtifactStatus:
    statuses = {item.status for item in state.production}
    status: Literal["pending", "running", "ready", "failed"] = (
        "ready"
        if state.ready
        else "running"
        if "running" in statuses
        else "failed"
        if "failed" in statuses
        else "pending"
    )
    # Q02: supported_modes is populated by endpoint callers that have DB access
    # (get_source_artifact_status, confirm_source_flow response).  We initialise to
    # None here; None means "not yet computed" (pending/running/failed), while [] means
    # "ready but no mode declared by any canonical blueprint".
    return SourceArtifactStatus(
        session_id=state.confirmation.session_id,
        ready=state.ready,
        canonical_status=status,
        total_questions=state.confirmation.total_questions,
        completed_count=state.confirmation.total_questions - len(state.pending_source_question_ids),
        pending_source_question_ids=state.pending_source_question_ids,
        production=state.production,
        supported_modes=state.supported_modes,
    )

async def run_producer(
    worker: Client, blueprints: BlueprintService, session_id: str, count: int
) -> None:
    # One job-wide budget, three requests per source; each claimed source has a
    # 360s deadline and420s DB lease. No review permits/counter are consumed here.
    budget = RequestBudget(3 * count)
    context = RequestContext(time.monotonic() + 360 * count + 60, budget.reserve)
    try:
        await ConfirmedArtifactProducer(SourceArtifactRepository(worker), blueprints).resume(
            session_id, context
        )
    except Exception as exc:
        # Failure state/lease lives in DB. Never log source/provider payloads or
        # pretend a background exception rolled back the confirmed source.
        logger.warning(
            "Canonical production incomplete for session %s (%s)", session_id, type(exc).__name__
        )


def query_rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ReviewDomainException(503, "ERR_SOURCE_UNAVAILABLE", "Invalid source query response")
    return cast(list[dict[str, Any]], value)


async def confirm_source_flow(
    session_id: str,
    actor_id: str,
    key: str | None,
    client_revision: str,
    db: Client,
    worker: Client,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ConfirmSourceResponse:
    resource_ids(session_id)
    confirmation_id = action_key(key)
    assert_ownership("exam_sessions", session_id, actor_id, db=db)
    sessions = query_rows(
        db.table("exam_sessions").select("status").eq("id", session_id).execute().data
    )
    if len(sessions) != 1:
        raise HTTPException(404, "Session not found")
    session = sessions[0]
    if session["status"] != "draft" and key is None:
        raise HTTPException(
            409, "Source already confirmed; read artifact status or retry production"
        )

    rows = query_rows(
        db.table("source_questions")
        .select("*")
        .eq("session_id", session_id)
        .order("question_no")
        .execute()
        .data
    )
    if not rows or any(row.get("has_missing_answer") is True for row in rows):
        raise HTTPException(422, "Source requires questions with complete answers")
    repository = SourceArtifactRepository(worker)
    try:
        confirmation = await ConfirmedArtifactProducer(repository, None).confirm(
            session_id,
            actor_id,
            confirmation_id,
            client_revision,
            rows,
        )
    except ToolError as exc:
        if exc.code == "SOURCE_ARTIFACT_INVALID":
            raise HTTPException(422, "Source input is invalid") from exc
        raise ReviewDomainException(503, "ERR_SOURCE_UNAVAILABLE", "Source preparation unavailable") from exc
    # A read failure here is a post-commit uncertainty, not a rollback. The client
    # can reconcile with the same key or read the session's artifact status.
    state = await repository.load(session_id)
    blueprints = blueprint_service(request) if not state.ready else None
    if blueprints is not None:
        background_tasks.add_task(
            run_producer, worker, blueprints, session_id, confirmation.total_questions
        )
    summary = status_payload(state)
    return ConfirmSourceResponse(
        session_id=session_id,
        status="blueprinted",
        confirmation_id=str(confirmation.confirmation_id),
        confirmed_at=confirmation.confirmed_at.isoformat(),
        total_questions=confirmation.total_questions,
        total_blueprints=summary.completed_count,
        canonical_status=summary.canonical_status,
        message="Đã xác nhận đề nguồn; dữ liệu sinh đề được chuẩn bị ở nền.",
    )


@router.get("/{session_id}/source-artifacts", response_model=SourceArtifactStatus)
async def get_source_artifact_status(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> SourceArtifactStatus:
    resource_ids(session_id)
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    state = await SourceArtifactRepository(db).load(session_id)
    result = status_payload(state)
    return result


@router.post(
    "/{session_id}/source-artifacts/retry", response_model=SourceArtifactStatus, status_code=202
)
async def retry_source_artifacts(
    session_id: str,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
    worker: Client = Depends(get_service_db),
) -> SourceArtifactStatus:
    resource_ids(session_id)
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    state = await SourceArtifactRepository(db).load(session_id)
    summary = status_payload(state)
    if state.ready:
        response.status_code = 200
        return summary
    sessions = query_rows(
        db.table("exam_sessions").select("status,approved_at").eq("id", session_id).execute().data
    )
    if len(sessions) != 1:
        raise HTTPException(404, "Session not found")
    if (
        sessions[0].get("status") in ("approved", "exported")
        or sessions[0].get("approved_at") is not None
    ):
        raise ReviewDomainException(423, "ERR_SESSION_LOCKED", "Session is locked")
    if sessions[0].get("status") == "generating":
        raise ReviewDomainException(
            409, "ERR_SESSION_BUSY_GENERATING", "Session generation is in progress"
        )
    if state.production and all(item.status in ("running", "ready") for item in state.production):
        return summary
    blueprints = blueprint_service(request)
    if blueprints is None:
        raise ReviewDomainException(
            503, "ERR_AI_SERVICE_UNAVAILABLE", "Dịch vụ chuẩn bị dữ liệu tạm thời không khả dụng"
        )
    background_tasks.add_task(
        run_producer, worker, blueprints, session_id, state.confirmation.total_questions
    )
    return summary

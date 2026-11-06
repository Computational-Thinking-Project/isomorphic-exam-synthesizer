from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.routes import (
    finalize,
    generation_config,
    generation_jobs,
    generation_snapshot,
    generation_stream,
    health,
    review,
    sessions,
    source_artifacts,
    users,
)
from app.core.config import settings
from app.core.cors import register_cors
from app.core.database import get_service_role_client
from app.core.rate_limit import register_rate_limiter
from app.models.generation_events import SessionOutcome
from app.models.schemas import ReviewDomainException
from app.services.ai.runtime import AIRuntime
from app.services.generation.ai_batch_adapter import AIBatchAdapter
from app.services.generation.config_repository import GenerationConfigRepository
from app.services.generation.events import GenerationEventBroker
from app.services.generation.job_repository import GenerationJobRepository
from app.services.generation.jobs import GenerationJobRunner
from app.services.generation.tickets import StreamTicketStore
from app.services.observability.runtime_registry import RuntimeRegistry

generation_registry = RuntimeRegistry()
generation_events = GenerationEventBroker()
generation_tickets = StreamTicketStore()


def _batch_adapter() -> AIBatchAdapter:
    return AIBatchAdapter(app.state.ai_services.generation)


generation_runner = GenerationJobRunner(
    None, generation_events, generation_registry, batch=_batch_adapter
)


async def _is_current_owner(session_id: UUID, user_id: UUID) -> bool:
    def lookup() -> bool:
        rows = (
            get_service_role_client()
            .table("exam_sessions")
            .select("user_id")
            .eq("id", str(session_id))
            .limit(1)
            .execute()
            .data
        )
        if (
            not isinstance(rows, list)
            or len(rows) > 1
            or any(not isinstance(row, dict) for row in rows)
        ):
            raise ValueError("Owner lookup returned malformed rows.")
        return len(rows) == 1 and cast(dict[str, Any], rows[0]).get("user_id") == str(user_id)

    return await run_in_threadpool(lookup)


async def _terminal_generation_state(
    session_id: UUID,
) -> tuple[SessionOutcome, int, int] | None:
    def read() -> tuple[SessionOutcome, int, int] | None:
        db = get_service_role_client()
        rows = (
            db.table("exam_sessions")
            .select("status")
            .eq("id", str(session_id))
            .limit(1)
            .execute()
            .data
        )
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError("Terminal session lookup failed.")
        status = cast(dict[str, Any], rows[0]).get("status")
        if status not in {"generated", "partial_generated", "failed"}:
            return None
        loaded = (
            db.rpc("load_generation_completed_results", {"p_session_id": str(session_id)})
            .execute()
            .data
        )
        if not isinstance(loaded, dict) or loaded.get("session_id") != str(session_id):
            raise ValueError("Terminal generation snapshot changed.")
        context = loaded.get("context")
        completed = loaded.get("completed")
        if not isinstance(context, dict) or not isinstance(completed, list):
            raise ValueError("Terminal generation results are malformed.")
        sources = context.get("confirmed_sources")
        versions = context.get("n_versions")
        if not isinstance(sources, list) or type(versions) is not int:
            raise ValueError("Terminal generation shape is malformed.")
        total = len(sources) * versions
        return cast(SessionOutcome, status), len(completed), total

    return await run_in_threadpool(read)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ai_services = AIRuntime(settings)
    generation_registry.start()
    try:
        yield
    finally:
        await app.state.ai_services.aclose()


app = FastAPI(
    title="Isomorphic Exam Synthesizer API",
    description="Backend engine for isomorphic math exam synthesis, validation, and export.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

register_rate_limiter(app)
register_cors(app)


@app.exception_handler(ReviewDomainException)
async def review_domain_exception_handler(
    request: Request, exc: ReviewDomainException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "detail": exc.detail},
    )


# Include Routers
app.include_router(health.router)
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(
    generation_config.create_generation_config_router(GenerationConfigRepository),
    prefix="/api/sessions",
    tags=["Generation configuration"],
)
app.include_router(
    generation_jobs.create_generation_job_router(GenerationJobRepository, runner=generation_runner),
    prefix="/api/sessions",
    tags=["Generation jobs"],
)
app.include_router(
    generation_snapshot.create_generation_snapshot_router(generation_events),
    prefix="/api/sessions",
    tags=["Generation jobs"],
)
app.include_router(
    generation_stream.create_generation_stream_router(
        tickets=generation_tickets,
        events=generation_events,
        registry=generation_registry,
        is_current_owner=_is_current_owner,
        terminal_state=_terminal_generation_state,
    ),
    prefix="/api/sessions",
    tags=["Generation events"],
)
app.include_router(source_artifacts.router, prefix="/api/sessions", tags=["Sources"])
app.include_router(review.router, prefix="/api/sessions", tags=["Review"])
app.include_router(finalize.router, prefix="/api/sessions", tags=["Finalize"])

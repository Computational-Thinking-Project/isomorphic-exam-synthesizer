"""Generation HTTP factory requiring real durable store and AI runner wiring."""

from collections.abc import Callable
from functools import partial
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.core.rate_limit import generation_rate_limit
from app.core.rate_limit import limiter as default_limiter
from app.models.schemas import CurrentUser
from app.services.generation.job_contracts import GenerationJobError, GenerationJobStore
from app.services.generation.jobs import GenerationJobRunner


class GenerationAccepted(BaseModel):
    session_id: UUID
    status: Literal["generating"] = "generating"


def create_generation_job_router(
    store_factory: Callable[[Client], GenerationJobStore],
    *,
    runner: GenerationJobRunner,
    limiter_instance: Limiter = default_limiter,
) -> APIRouter:
    router = APIRouter()
    limit_generate = partial(generation_rate_limit, limiter_instance=limiter_instance)

    async def start(
        session_id: UUID,
        user: CurrentUser,
        db: Client,
        background_tasks: BackgroundTasks,
        *,
        retry: bool,
    ) -> GenerationAccepted:
        await run_in_threadpool(assert_ownership, "exam_sessions", str(session_id), user.id, db=db)
        try:
            store = store_factory(db)
            plan = await runner.claim(store, session_id, retry=retry)
        except GenerationJobError as exc:
            raise HTTPException(
                exc.status_code, {"code": exc.code, "message": exc.message}
            ) from exc
        except Exception:
            raise HTTPException(
                503,
                {
                    "code": "ERR_GENERATION_UNAVAILABLE",
                    "message": "Generation is temporarily unavailable. Verify session state before retrying.",
                },
            ) from None
        background_tasks.add_task(runner.run, plan, store)
        return GenerationAccepted(session_id=session_id)

    @router.post("/{session_id}/generate", response_model=GenerationAccepted, status_code=202)
    @limit_generate
    async def generate(
        session_id: UUID,
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
        user: CurrentUser = Depends(get_current_user),
        db: Client = Depends(get_user_db),
    ) -> GenerationAccepted:
        return await start(session_id, user, db, background_tasks, retry=False)

    @router.post(
        "/{session_id}/retry-generation", response_model=GenerationAccepted, status_code=202
    )
    @limit_generate
    async def retry_generation(
        session_id: UUID,
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
        user: CurrentUser = Depends(get_current_user),
        db: Client = Depends(get_user_db),
    ) -> GenerationAccepted:
        return await start(session_id, user, db, background_tasks, retry=True)

    return router

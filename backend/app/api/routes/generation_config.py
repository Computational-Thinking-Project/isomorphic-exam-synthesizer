"""Configuration router factory awaiting a real atomic save adapter.

Importing this module registers no endpoint. Product integration must explicitly
supply a store factory and register this router after the save RPC is ready.
Fixture-only stores belong in tests, never in this module or the product app.
"""

from collections.abc import Callable
from functools import partial
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi import Limiter
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.core.rate_limit import crud_rate_limit
from app.core.rate_limit import limiter as default_limiter
from app.models.generation_config import GenerationConfigRequest, GenerationConfigResponse
from app.models.schemas import CurrentUser
from app.services.generation.config_repository import GenerationConfigStore
from app.services.generation.config_service import GenerationConfigError, validate_generation_config


def create_generation_config_router(
    repository_factory: Callable[[Client], GenerationConfigStore],
    *,
    limiter_instance: Limiter = default_limiter,
) -> APIRouter:
    """Build a router for /api/sessions; require explicit persistence wiring."""
    router = APIRouter()
    limit_crud = partial(crud_rate_limit, limiter_instance=limiter_instance)

    @router.post(
        "/{session_id}/config",
        response_model=GenerationConfigResponse,
        status_code=200,
        summary="Save generation configuration for an owned session",
    )
    @limit_crud
    def save_generation_configuration(
        session_id: UUID,
        payload: GenerationConfigRequest,
        request: Request,
        response: Response,
        current_user: CurrentUser = Depends(get_current_user),
        db: Client = Depends(get_user_db),
    ) -> GenerationConfigResponse:
        try:
            assert_ownership("exam_sessions", str(session_id), current_user.id, db=db)
            repository = repository_factory(db)
            context = repository.load_context(session_id)
            if context is None:
                raise HTTPException(status_code=404, detail="Session not found")
            if context.session_id != session_id:
                raise ValueError("Repository context does not match the requested session.")
            config = validate_generation_config(payload, context)
            saved = repository.save_config(session_id, config)
            if isinstance(saved, GenerationConfigResponse):
                # Revalidate model instances too: models can be mutated internally.
                saved = saved.model_dump()
            result = GenerationConfigResponse.model_validate(saved)
            if result.session_id != session_id:
                raise ValueError("Saved configuration does not match the requested session.")
            return result
        except HTTPException:
            raise
        except GenerationConfigError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "ERR_CONFIG_STORAGE_FAILURE",
                    "message": "Generation configuration could not be processed.",
                },
            ) from exc

    return router

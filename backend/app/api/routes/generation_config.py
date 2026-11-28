"""Owned-session generation configuration endpoint."""

from collections.abc import Callable
from functools import partial
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from postgrest.exceptions import APIError
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
        # A receipt from a database before migration 028 has no generation_mode;
        # do not invent one in the response (EXT-02).
        response_model_exclude_unset=True,
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
        # Preserve established auth/ownership HTTP errors, but never trust HTTP
        # exceptions raised by a storage adapter as public response bodies.
        try:
            assert_ownership("exam_sessions", str(session_id), current_user.id, db=db)
        except HTTPException:
            raise
        except Exception as exc:
            raise _storage_failure() from exc
        try:
            repository = repository_factory(db)
            context = repository.load_context(session_id)
        except GenerationConfigError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc
        except Exception as exc:
            raise _storage_failure() from exc
        if context is None:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            if context.session_id != session_id:
                raise ValueError("Repository context does not match the requested session.")
            config = validate_generation_config(payload, context)
            saved = repository.save_config(session_id, config, context.expected_snapshot)
            # Revalidate model instances too: models can be mutated internally.
            saved_data: object = (
                saved.model_dump(exclude_unset=True)
                if isinstance(saved, GenerationConfigResponse)
                else saved
            )
            result = GenerationConfigResponse.model_validate(saved_data)
            if result.session_id != session_id:
                raise ValueError("Saved configuration does not match the requested session.")
            return result
        except GenerationConfigError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc
        except Exception as exc:
            raise _storage_failure() from exc

    @router.post(
        "/{session_id}/shuffle-only/confirm",
        status_code=200,
        summary="Recovery: confirm the copies of a generated shuffle-only session (EXT-02)",
    )
    @limit_crud
    def confirm_shuffle_only_copies(
        session_id: UUID,
        request: Request,
        response: Response,
        current_user: CurrentUser = Depends(get_current_user),
        db: Client = Depends(get_user_db),
    ) -> dict[str, object]:
        # The worker confirms automatically; this only retries a deferred confirmation.
        assert_ownership("exam_sessions", str(session_id), current_user.id, db=db)
        try:
            data = db.rpc("confirm_shuffle_only_copies", {"p_session_id": str(session_id)}).execute().data
        except APIError as exc:
            raise _confirm_error(exc) from exc
        except Exception as exc:
            raise _storage_failure() from exc
        if (
            not isinstance(data, dict)
            or data.get("success") is not True
            or data.get("session_id") != str(session_id)
            or data.get("session_status") != "reviewed"
        ):
            raise _storage_failure()
        return data

    return router


_CONFIRM_ERRORS = {
    "ERR_MODE_NOT_SHUFFLE_ONLY": (409, "The session is not a shuffle-only generation."),
    "ERR_SHUFFLE_ONLY_NOT_READY": (409, "The copies are not complete or do not match the source."),
    "REVIEW_BUSY": (409, "A review operation is still running; try again later."),
    "REVIEW_LOCKED": (423, "The session is already approved."),
}


def _confirm_error(exc: APIError) -> HTTPException:
    code = str(getattr(exc, "code", "") or "").upper()
    message = str(getattr(exc, "message", "") or "")
    if code == "P0002":
        return HTTPException(status_code=404, detail="Session not found")
    if code == "42501":
        return HTTPException(status_code=403, detail="Access denied")
    for prefix, (status_code, text) in _CONFIRM_ERRORS.items():
        if code in {"55000", "55006"} and message.startswith(prefix):
            return HTTPException(status_code=status_code, detail={"code": prefix, "message": text})
    return _storage_failure()


def _storage_failure() -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={
            "code": "ERR_CONFIG_STORAGE_FAILURE",
            "message": "Generation configuration could not be processed.",
        },
    )

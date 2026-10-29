"""FastAPI dependencies for authentication and authorization.

Includes:
- get_current_user: Verifies Supabase JWT token from Authorization header.
- get_user_db: Returns an authenticated Supabase client for RLS enforcement.
- assert_ownership: Defense-in-depth resource ownership check against ALLOWED_TABLES whitelist.
"""

import logging
from typing import Any, Optional, cast

import httpx
from fastapi import Depends, Header, HTTPException, Request, status
from supabase import AuthApiError, AuthRetryableError, Client

from app.core.database import get_authenticated_client, get_service_role_client, get_supabase_client
from app.models.schemas import CurrentUser

logger = logging.getLogger(__name__)

# Whitelist of tables permitted for ownership verification (SEC-07)
ALLOWED_TABLES: set[str] = {
    "exam_sessions",
    "source_questions",
    "question_blueprints",
    "generation_configs",
    "exam_versions",
    "version_questions",
    "answer_keys",
    "review_logs",
}


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> CurrentUser:
    """Extract and verify Bearer JWT token from Authorization header.

    Calls Supabase Auth to validate the token and returns the CurrentUser object.
    Raises HTTP 401 if token is missing, malformed, expired, or invalid.
    Also populates ``request.state.authenticated_user_id`` for downstream rate limiting.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1].strip()

    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        logger.error("Supabase client configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is misconfigured",
        ) from exc
    except Exception as exc:
        logger.error("Failed to initialize Supabase client: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service initialization error",
        ) from exc

    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not getattr(user_response, "user", None):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = user_response.user
        metadata = getattr(user, "user_metadata", {}) or {}
        user_name = metadata.get("full_name") or metadata.get("name")

        current_user = CurrentUser(
            id=str(user.id),
            email=str(getattr(user, "email", "") or ""),
            name=user_name,
            access_token=token,
        )

        # Populate authenticated_user_id on request state for rate limiting (TASK-005 contract)
        if hasattr(request, "state"):
            request.state.authenticated_user_id = current_user.id

        return current_user
    except HTTPException:
        raise
    except (httpx.RequestError, httpx.TimeoutException, AuthRetryableError) as exc:
        logger.error("Network or retryable error communicating with Supabase Auth: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from exc
    except AuthApiError as exc:
        if exc.status >= 500:
            logger.error("Supabase Auth server error (%d): %s", exc.status, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            ) from exc
        if exc.status == status.HTTP_429_TOO_MANY_REQUESTS:
            logger.warning("Supabase Auth rate limit reached: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Authentication service rate limit exceeded. Please try again later.",
            ) from exc
        logger.warning("Supabase Auth rejected token (%d): %s", exc.status, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except Exception as exc:
        logger.warning("Token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_user_db(
    current_user: CurrentUser = Depends(get_current_user),
) -> Client:
    """Dependency that returns an authenticated Supabase client for the current user."""
    return get_authenticated_client(current_user.access_token)


async def get_current_admin_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Verify administrator privileges (SEC-08 / TASK-207c).

    In development and test environments, any authenticated user is granted access.
    In production/staging environments, strictly checks whether user email is
    enrolled in ADMIN_EMAILS. Missing privileges return HTTP 403 Forbidden.
    """
    from app.core.config import settings

    if settings.ENVIRONMENT in ("development", "test"):
        return current_user

    admin_list = [
        email.strip().lower() for email in settings.ADMIN_EMAILS.split(",") if email.strip()
    ]
    if current_user.email and current_user.email.strip().lower() in admin_list:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Administrator privileges required to access this resource",
    )


def assert_ownership(
    table: str,
    resource_id: str,
    user_id: str,
    db: Optional[Client] = None,
) -> None:
    """Verify that a given resource in an allowed table belongs to the user.

    Traverses the relational hierarchy back to exam_sessions.user_id:
    - exam_sessions -> direct user_id check
    - source_questions, generation_configs, exam_versions -> via session_id
    - question_blueprints -> via source_questions -> session_id
    - version_questions, answer_keys -> via exam_versions -> session_id
    - review_logs -> via version_questions -> exam_versions -> session_id

    Raises:
        HTTPException(400): If table is not in ALLOWED_TABLES whitelist.
        HTTPException(404): If resource (or parent relationship) is not found.
        HTTPException(403): If resource does not belong to user_id.
    """
    if table not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Table '{table}' is not permitted for ownership check",
        )

    client = db if db is not None else get_service_role_client()

    # 1. Direct owner on exam_sessions
    if table == "exam_sessions":
        response = client.table("exam_sessions").select("user_id").eq("id", resource_id).execute()
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found in '{table}'",
            )
        owner_id = str(rows[0].get("user_id", ""))
        if owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return

    # 2. Directly linked to exam_sessions via session_id
    if table in {"source_questions", "generation_configs", "exam_versions"}:
        response = client.table(table).select("session_id").eq("id", resource_id).execute()
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found in '{table}'",
            )
        session_id = str(rows[0].get("session_id", ""))
        return assert_ownership("exam_sessions", session_id, user_id, db=client)

    # 3. question_blueprints -> source_questions -> exam_sessions
    if table == "question_blueprints":
        response = (
            client.table("question_blueprints")
            .select("source_question_id")
            .eq("id", resource_id)
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found in '{table}'",
            )
        source_question_id = str(rows[0].get("source_question_id", ""))
        return assert_ownership("source_questions", source_question_id, user_id, db=client)

    # 4. version_questions, answer_keys -> exam_versions -> exam_sessions
    if table in {"version_questions", "answer_keys"}:
        response = client.table(table).select("version_id").eq("id", resource_id).execute()
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found in '{table}'",
            )
        version_id = str(rows[0].get("version_id", ""))
        return assert_ownership("exam_versions", version_id, user_id, db=client)

    # 5. review_logs -> version_questions -> exam_versions -> exam_sessions
    if table == "review_logs":
        response = (
            client.table("review_logs")
            .select("version_question_id")
            .eq("id", resource_id)
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found in '{table}'",
            )
        version_question_id = str(rows[0].get("version_question_id", ""))
        return assert_ownership("version_questions", version_question_id, user_id, db=client)

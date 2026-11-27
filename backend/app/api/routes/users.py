"""User endpoints for profile retrieval and session management."""

import logging
from typing import Any, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from postgrest.exceptions import APIError
from supabase import Client

from app.api.dependencies import get_current_user, get_user_db
from app.core.rate_limit import crud_rate_limit
from app.models.exam_metadata import ExamMetadata
from app.models.schemas import (
    CurrentUser,
    SessionStatisticsResponse,
    SessionStatusCounts,
    UserProfile,
)

logger = logging.getLogger(__name__)

IN_PROGRESS_STATUSES = (
    "draft", "blueprinted", "configured", "generating", "partial_generated", "generated", "reviewed",
)

router = APIRouter()

_SETTINGS_COLUMNS = ",".join(ExamMetadata.model_fields)


def _read_exam_settings(db: Client, owner_id: str) -> ExamMetadata:
    rows = (
        db.table("user_exam_settings")
        .select(_SETTINGS_COLUMNS)
        .eq("user_id", owner_id)
        .limit(1)
        .execute()
        .data
    )
    if not isinstance(rows, list):
        raise ValueError("Expected exam settings rows")
    return ExamMetadata.model_validate(rows[0]) if rows else ExamMetadata()


@router.get("/me/settings", response_model=ExamMetadata)
@crud_rate_limit
async def get_my_exam_settings(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ExamMetadata:
    """Return all printable defaults for the current user."""
    try:
        settings = _read_exam_settings(db, current_user.id)
    except (APIError, httpx.HTTPError, ValueError) as exc:
        logger.warning("Exam settings read failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Exam settings temporarily unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return settings


@router.patch("/me/settings", response_model=ExamMetadata)
@crud_rate_limit
async def patch_my_exam_settings(
    request: Request,
    response: Response,
    payload: ExamMetadata,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ExamMetadata:
    """Apply only supplied defaults, including explicit nulls, in one DB write."""
    patch = payload.model_dump(mode="json", exclude_unset=True)
    try:
        if patch:
            updated = db.rpc("patch_my_exam_settings", {"p_patch": patch}).execute().data
            settings = ExamMetadata.model_validate(updated)
        else:
            settings = _read_exam_settings(db, current_user.id)
    except (APIError, httpx.HTTPError, ValueError) as exc:
        logger.warning("Exam settings write failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Exam settings temporarily unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return settings


def _session_statistics(rows: Any) -> SessionStatisticsResponse:
    if not isinstance(rows, list):
        raise ValueError("Expected a list of session status counts")

    counts = dict.fromkeys(SessionStatusCounts.model_fields, 0)
    for row in rows:
        if not isinstance(row, dict) or "status" not in row or "count" not in row:
            raise ValueError("Invalid session status count row")
        stored_status, count = row["status"], row["count"]
        if stored_status is not None and not isinstance(stored_status, str):
            raise ValueError("Invalid session status type")
        if type(count) is not int or count < 1:
            raise ValueError("Invalid grouped session count")
        bucket = stored_status if stored_status is not None and stored_status in counts else "unknown"
        counts[bucket] += count

    return SessionStatisticsResponse(
        total_sessions=sum(counts.values()),
        in_progress_sessions=sum(counts[key] for key in IN_PROGRESS_STATUSES),
        approved_not_exported_sessions=counts["approved"],
        exported_sessions=counts["exported"],
        by_status=SessionStatusCounts.model_validate(counts),
    )


@router.get("/me/statistics", response_model=SessionStatisticsResponse)
@crud_rate_limit
async def get_my_statistics(
    request: Request,
    response: Response,
    db: Client = Depends(get_user_db),
) -> SessionStatisticsResponse:
    """Count sessions visible to the authenticated caller in one database read."""
    try:
        result = _session_statistics(db.rpc("get_my_session_status_counts", {}).execute().data)
    except (APIError, httpx.HTTPError, ValueError) as exc:
        logger.warning("Session statistics unavailable (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Session statistics temporarily unavailable") from exc

    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/me", response_model=UserProfile, summary="Get current user profile")
async def get_my_profile(
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> UserProfile:
    """Retrieve profile of the currently authenticated user.

    Queries public.users table with RLS applied. Falls back to token claims
    if the record has not yet been populated by the auth webhook/trigger.
    """
    response = db.table("users").select("id, email, name, created_at").eq("id", current_user.id).execute()
    rows = cast(list[dict[str, Any]], response.data or [])
    if rows:
        record = rows[0]
        created_at_val = record.get("created_at")
        name_val = record.get("name")
        return UserProfile(
            id=str(record.get("id")),
            email=str(record.get("email")),
            name=str(name_val) if name_val is not None else None,
            created_at=str(created_at_val) if created_at_val is not None else None,
        )

    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        created_at=None,
    )

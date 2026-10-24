"""User endpoints for profile retrieval and session management."""

from typing import Any, cast

from fastapi import APIRouter, Depends
from supabase import Client

from app.api.dependencies import get_current_user, get_user_db
from app.models.schemas import CurrentUser, UserProfile

router = APIRouter()


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

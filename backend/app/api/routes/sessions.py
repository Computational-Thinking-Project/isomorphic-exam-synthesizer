"""Exam Sessions CRUD and Clone API endpoints (BE-01, BE-02, BE-03, UC03).

Provides endpoints for:
- Creating a new exam session (draft status)
- Listing exam sessions of the current user with pagination and optional status filter
- Getting full session details including source questions and exam versions
- Updating session metadata (title, subject, grade)
- Deleting an exam session with relational cascade
- Cloning an existing session (deep copying source questions and blueprints)
"""

from typing import Any, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.types import CountMethod
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.models.schemas import (
    CurrentUser,
    SessionCloneRequest,
    SessionCreate,
    SessionDetailResponse,
    SessionItem,
    SessionListResponse,
    SessionUpdate,
)

router = APIRouter()


@router.post(
    "",
    response_model=SessionItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new exam session",
)
async def create_session(
    payload: SessionCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> SessionItem:
    """Create a new exam session for the authenticated user with 'draft' status."""
    new_session_data: dict[str, Any] = {
        "user_id": current_user.id,
        "title": payload.title.strip(),
        "subject": payload.subject.strip(),
        "grade": payload.grade,
        "status": "draft",
        "gemini_call_count": 0,
        "retry_count": 0,
        "gemini_review_calls": 0,
    }

    response = db.table("exam_sessions").insert(cast(Any, new_session_data)).execute()
    rows = cast(List[dict[str, Any]], response.data or [])
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session",
        )

    return SessionItem(**rows[0])


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List exam sessions for current user",
)
async def list_sessions(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (e.g., draft, approved)"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> SessionListResponse:
    """Retrieve paginated list of sessions owned by the current user, ordered by created_at DESC."""
    query = db.table("exam_sessions").select("*", count=CountMethod.exact).eq("user_id", current_user.id)

    if status_filter:
        query = query.eq("status", status_filter)

    start = (page - 1) * page_size
    end = start + page_size - 1

    query = query.order("created_at", desc=True).range(start, end)
    response = query.execute()

    rows = cast(List[dict[str, Any]], response.data or [])
    total_count: int = response.count if response.count is not None else len(rows)

    items = [SessionItem(**r) for r in rows]
    return SessionListResponse(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get session details with source questions and versions",
)
async def get_session_detail(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> SessionDetailResponse:
    """Retrieve session details by ID, validating ownership and fetching nested questions and versions."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    s_res = db.table("exam_sessions").select("*").eq("id", session_id).execute()
    s_rows = cast(List[dict[str, Any]], s_res.data or [])
    if not s_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    session_record = s_rows[0]

    # Fetch source_questions ordered by question_no ASC
    q_res = (
        db.table("source_questions")
        .select("*")
        .eq("session_id", session_id)
        .order("question_no", desc=False)
        .execute()
    )
    source_questions = cast(List[dict[str, Any]], q_res.data or [])

    # Fetch exam_versions ordered by created_at ASC
    v_res = (
        db.table("exam_versions")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    exam_versions = cast(List[dict[str, Any]], v_res.data or [])

    return SessionDetailResponse(
        **session_record,
        source_questions=source_questions,
        exam_versions=exam_versions,
    )


@router.patch(
    "/{session_id}",
    response_model=SessionItem,
    summary="Update session metadata",
)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> SessionItem:
    """Update editable fields of an exam session (title, subject, grade)."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    update_data: dict[str, Any] = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None
    }
    if not update_data:
        res = db.table("exam_sessions").select("*").eq("id", session_id).execute()
        rows = cast(List[dict[str, Any]], res.data or [])
        if not rows:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return SessionItem(**rows[0])

    response = db.table("exam_sessions").update(cast(Any, update_data)).eq("id", session_id).execute()
    rows = cast(List[dict[str, Any]], response.data or [])
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return SessionItem(**rows[0])


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an exam session and cascade all related data",
)
async def delete_session(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> None:
    """Delete an exam session and cascade all associated questions, blueprints, and versions."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)
    db.table("exam_sessions").delete().eq("id", session_id).execute()
    return None


@router.post(
    "/{session_id}/clone",
    response_model=SessionItem,
    status_code=status.HTTP_201_CREATED,
    summary="Clone an existing session (deep copy source questions and blueprints)",
)
async def clone_session(
    session_id: str,
    payload: Optional[SessionCloneRequest] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> SessionItem:
    """Deep clone a session: creates a new session in draft status and duplicates all questions and blueprints."""
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    # 1. Fetch original session details
    orig_res = db.table("exam_sessions").select("*").eq("id", session_id).execute()
    orig_rows = cast(List[dict[str, Any]], orig_res.data or [])
    if not orig_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source session not found")
    orig = orig_rows[0]

    # 2. Determine new title
    custom_title = payload.new_title.strip() if payload and payload.new_title else None
    new_title = custom_title if custom_title else f"{orig.get('title', '')} (Bản sao)"

    # 3. Insert cloned session record
    new_session_data: dict[str, Any] = {
        "user_id": current_user.id,
        "title": new_title,
        "subject": orig.get("subject", "Toán"),
        "grade": orig.get("grade", 12),
        "status": "draft",
        "gemini_call_count": 0,
        "retry_count": 0,
        "gemini_review_calls": 0,
    }
    create_res = db.table("exam_sessions").insert(cast(Any, new_session_data)).execute()
    create_rows = cast(List[dict[str, Any]], create_res.data or [])
    if not create_rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create cloned session",
        )
    new_session = create_rows[0]
    new_session_id = str(new_session["id"])

    # 4. Fetch and deep copy all source questions & blueprints with atomicity / cleanup guarantee
    try:
        sq_res = (
            db.table("source_questions")
            .select("*")
            .eq("session_id", session_id)
            .order("question_no", desc=False)
            .execute()
        )
        sq_rows = cast(List[dict[str, Any]], sq_res.data or [])

        for sq in sq_rows:
            old_sq_id = str(sq["id"])
            new_sq_payload: dict[str, Any] = {
                "session_id": new_session_id,
                "question_no": sq.get("question_no"),
                "raw_content": sq.get("raw_content", ""),
                "options": sq.get("options", {}),
                "correct_key": sq.get("correct_key", ""),
                "solution_md": sq.get("solution_md"),
                "has_missing_answer": sq.get("has_missing_answer", False),
                "has_security_warning": sq.get("has_security_warning", False),
            }
            ins_sq_res = db.table("source_questions").insert(cast(Any, new_sq_payload)).execute()
            ins_sq_rows = cast(List[dict[str, Any]], ins_sq_res.data or [])
            if not ins_sq_rows:
                raise RuntimeError(f"Failed to clone source question {old_sq_id}")

            new_sq_id = str(ins_sq_rows[0]["id"])

            # 5. Clone corresponding blueprint if one exists
            bp_res = db.table("question_blueprints").select("*").eq("source_question_id", old_sq_id).execute()
            bp_rows = cast(List[dict[str, Any]], bp_res.data or [])
            if bp_rows:
                bp = bp_rows[0]
                new_bp_payload: dict[str, Any] = {
                    "source_question_id": new_sq_id,
                    "variables": bp.get("variables", {}),
                    "domains": bp.get("domains", {}),
                    "invariants": bp.get("invariants", []),
                    "variation_modes": bp.get("variation_modes", []),
                    "rule_summary": bp.get("rule_summary"),
                    "confirmed_at": bp.get("confirmed_at"),
                }
                ins_bp_res = db.table("question_blueprints").insert(cast(Any, new_bp_payload)).execute()
                ins_bp_rows = cast(List[dict[str, Any]], ins_bp_res.data or [])
                if not ins_bp_rows:
                    raise RuntimeError(f"Failed to clone blueprint for question {old_sq_id}")

    except Exception as exc:
        # Rollback/cleanup: remove the partially cloned session to avoid orphaned data
        try:
            db.table("exam_sessions").delete().eq("id", new_session_id).execute()
        except Exception:
            pass  # Best effort cleanup
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clone session questions or blueprints",
        ) from exc

    return SessionItem(**new_session)

"""Exam Sessions CRUD and Clone API endpoints (BE-01, BE-02, BE-03, UC03).

Provides endpoints for:
- Creating a new exam session (draft status)
- Listing exam sessions of the current user with pagination and optional status filter
- Getting full session details including source questions and exam versions
- Updating session metadata (title, subject, grade)
- Deleting an exam session with relational cascade
- Cloning an existing session (deep copying source questions and blueprints)
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from postgrest.types import CountMethod
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.core.rate_limit import crud_rate_limit
from app.models.schemas import (
    ConfirmSourceRequest,
    ConfirmSourceResponse,
    CurrentUser,
    IngestSuccessResponse,
    IngestTextRequest,
    SessionCloneRequest,
    SessionCreate,
    SessionDetailResponse,
    SessionItem,
    SessionListResponse,
    SessionUpdate,
)
from app.services.parser import (
    assert_zero_mutation_or_raise,
    ensure_blueprints_for_session,
    parse_docx,
    parse_latex,
    parse_markdown,
    upload_exam_file_to_storage,
    validate_file_security,
)
from app.services.parser.ingestion_service import (
    replace_source_questions_atomically,
    trigger_blueprint_pipeline,
)

logger = logging.getLogger(__name__)

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
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status (e.g., draft, approved)"
    ),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> SessionListResponse:
    """Retrieve paginated list of sessions owned by the current user, ordered by created_at DESC."""
    query = (
        db.table("exam_sessions")
        .select("*", count=CountMethod.exact)
        .eq("user_id", current_user.id)
    )

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

    response = (
        db.table("exam_sessions").update(cast(Any, update_data)).eq("id", session_id).execute()
    )
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source session not found"
        )
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
            bp_res = (
                db.table("question_blueprints")
                .select("*")
                .eq("source_question_id", old_sq_id)
                .execute()
            )
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
                ins_bp_res = (
                    db.table("question_blueprints").insert(cast(Any, new_bp_payload)).execute()
                )
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


@router.post(
    "/{session_id}/ingest-file",
    response_model=IngestSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest exam file (.docx, .tex, .md) with safe in-memory validation",
)
@crud_rate_limit
async def ingest_file(
    session_id: str,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> IngestSuccessResponse:
    """Ingest exam file (.docx, .tex, .md) for a session in draft status.

    Validates ownership, SEC-04 file security, performs 100% in-memory parsing,
    raises HTTP 422 if incomplete, and executes atomic DB replacement on success.
    """
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    # State Precondition check: must be in 'draft' status
    s_res = db.table("exam_sessions").select("status").eq("id", session_id).execute()
    s_rows = cast(List[dict[str, Any]], s_res.data or [])
    if not s_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_status = str(s_rows[0].get("status", ""))
    if session_status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot ingest questions: session is in '{session_status}' state (must be 'draft')",
        )

    # Read uploaded file bytes in-memory
    file_bytes = await file.read()
    filename = file.filename or "exam"

    # SEC-04 File Security Validation (extension, size, zip bomb, magic bytes)
    ext = validate_file_security(filename, file_bytes)

    # In-Memory Parsing
    if ext == ".docx":
        parsed_questions, parser_errors = parse_docx(file_bytes)
    elif ext == ".tex":
        text_content = file_bytes.decode("utf-8", errors="replace")
        parsed_questions, parser_errors = parse_latex(text_content)
    elif ext == ".md":
        text_content = file_bytes.decode("utf-8", errors="replace")
        parsed_questions, parser_errors = parse_markdown(text_content)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {ext}",
        )

    # Zero Mutation Guard: In-Memory Pre-validation
    assert_zero_mutation_or_raise(parsed_questions, parser_errors)

    # Upload to Supabase Storage (Method 1C: only after 100% valid)
    await upload_exam_file_to_storage(
        db=db,
        session_id=session_id,
        filename=filename,
        file_bytes=file_bytes,
        content_type=file.content_type,
    )

    # Atomic Database Replacement (Method 2A RPC with fallback)
    saved_questions = await replace_source_questions_atomically(
        db=db,
        session_id=session_id,
        questions=parsed_questions,
    )

    # Trigger background Blueprint extraction pipeline (TASK-203 hook)
    background_tasks.add_task(trigger_blueprint_pipeline, session_id, saved_questions)

    return IngestSuccessResponse(
        session_id=session_id,
        message="Exam file ingested and validated successfully",
        total_questions=len(saved_questions),
        questions=saved_questions,
    )


@router.post(
    "/{session_id}/ingest-text",
    response_model=IngestSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest raw exam text with safe in-memory validation",
)
@crud_rate_limit
async def ingest_text(
    session_id: str,
    payload: IngestTextRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> IngestSuccessResponse:
    """Ingest raw exam text (LaTeX or Markdown) for a session in draft status.

    Validates ownership, performs 100% in-memory parsing, raises HTTP 422 if incomplete,
    and executes atomic DB replacement on success.
    """
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    # State Precondition check: must be in 'draft' status
    s_res = db.table("exam_sessions").select("status").eq("id", session_id).execute()
    s_rows = cast(List[dict[str, Any]], s_res.data or [])
    if not s_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_status = str(s_rows[0].get("status", ""))
    if session_status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot ingest questions: session is in '{session_status}' state (must be 'draft')",
        )

    raw_text = payload.raw_text

    # Parse with markdown parser or latex parser if latex environments are present
    if "\\begin{enumerate}" in raw_text or "\\item" in raw_text:
        parsed_questions, parser_errors = parse_latex(raw_text)
    else:
        parsed_questions, parser_errors = parse_markdown(raw_text)

    # Zero Mutation Guard: In-Memory Pre-validation
    assert_zero_mutation_or_raise(parsed_questions, parser_errors)

    # Atomic Database Replacement
    saved_questions = await replace_source_questions_atomically(
        db=db,
        session_id=session_id,
        questions=parsed_questions,
    )

    # Trigger background Blueprint extraction pipeline (TASK-203 hook)
    background_tasks.add_task(trigger_blueprint_pipeline, session_id, saved_questions)

    return IngestSuccessResponse(
        session_id=session_id,
        message="Exam text ingested and validated successfully",
        total_questions=len(saved_questions),
        questions=saved_questions,
    )


@router.post(
    "/{session_id}/confirm-source",
    response_model=ConfirmSourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm source exam and activate blueprints (TASK-205)",
)
@crud_rate_limit
async def confirm_source(
    session_id: str,
    payload: ConfirmSourceRequest,
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> ConfirmSourceResponse:
    """Confirm source exam questions, lock blueprints, and transition session to Stage 2.

    Guards:
    1. Ownership: Current user owns the exam session (Sync call).
    2. State Precondition: Session must be in 'draft' status (HTTP 409 if not).
    3. Data Integrity: Session must have source questions and none with missing answers (HTTP 422).
    4. Security (SEC-02): If any question has security warnings, payload must have acknowledged_security_warnings=True (HTTP 422).
    5. Blueprint Engine: Ensures all questions have active blueprints.
    6. Atomic State Transition: Updates blueprints confirmed_at and session status to 'blueprinted'.
    """
    # Guard 1: Ownership verification (Sync function)
    assert_ownership("exam_sessions", session_id, current_user.id, db=db)

    # Guard 2: State Precondition (must be 'draft')
    s_res = db.table("exam_sessions").select("status, updated_at").eq("id", session_id).execute()
    s_rows = cast(List[dict[str, Any]], s_res.data or [])
    if not s_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_status = str(s_rows[0].get("status", ""))
    session_updated_at = s_rows[0].get("updated_at")
    if session_status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is in '{session_status}' state; cannot confirm source unless in 'draft'",
        )

    # Guard 3: Fetch & validate source questions
    q_res = (
        db.table("source_questions")
        .select("*")
        .eq("session_id", session_id)
        .order("question_no", desc=False)
        .execute()
    )
    questions = cast(List[dict[str, Any]], q_res.data or [])
    if not questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot confirm source: Session has no source questions",
        )

    missing_answer_questions = [
        q.get("question_no", "?") for q in questions if q.get("has_missing_answer") is True
    ]
    if missing_answer_questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot confirm source: Questions {missing_answer_questions} have missing answers",
        )

    # Guard 4: Security warnings acknowledgment (SEC-02)
    security_warning_questions = [
        q.get("question_no", "?") for q in questions if q.get("has_security_warning") is True
    ]
    if security_warning_questions and not payload.acknowledged_security_warnings:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Questions {security_warning_questions} have security warnings (SEC-02). "
                "Explicit acknowledgment is required by setting acknowledged_security_warnings=True"
            ),
        )

    # Guard 5: Ensure blueprints exist for all source questions
    total_blueprints = await ensure_blueprints_for_session(db, session_id, questions)

    # Guard 6: Atomic state transition (RPC only, strictly transactional)
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        rpc_res = db.rpc(
            "confirm_exam_source",
            {
                "p_session_id": session_id,
                "p_expected_question_count": len(questions),
                "p_acknowledged_security_warnings": payload.acknowledged_security_warnings,
                "p_expected_updated_at": session_updated_at,
            },
        ).execute()

        if rpc_res.data and isinstance(rpc_res.data, dict) and rpc_res.data.get("success"):
            confirmed_at_str = rpc_res.data.get("confirmed_at") or now_iso
            actual_total_questions = rpc_res.data.get("total_questions", len(questions))
            actual_total_blueprints = rpc_res.data.get("total_blueprints", total_blueprints)
            return ConfirmSourceResponse(
                session_id=session_id,
                status="blueprinted",
                confirmed_at=str(confirmed_at_str),
                total_questions=actual_total_questions,
                total_blueprints=actual_total_blueprints,
                message="Source confirmed and blueprints locked successfully",
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm source: database returned unsuccessful response",
        )
    except HTTPException:
        raise
    except Exception as exc:
        err_msg = str(exc)
        err_lower = err_msg.lower()
        logger.error(
            "RPC confirm_exam_source failed for session %s: %s",
            session_id,
            exc,
        )
        if "42501" in err_msg or "Access denied" in err_msg or "Unauthorized" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied or session ownership mismatch",
            ) from exc
        if (
            "22023" in err_msg
            or "draft" in err_lower
            or "mismatch" in err_lower
            or "state" in err_lower
            or "warning" in err_lower
            or "missing" in err_lower
            or "concurrent" in err_lower
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot confirm source: {err_msg}",
            ) from exc
        if "P0002" in err_msg or "not found" in err_lower:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            ) from exc

        # Differentiate network timeout (uncertain commit status) from confirmed database rollback
        is_timeout = (
            "timeout" in err_lower
            or "timed out" in err_lower
            or "connection closed" in err_lower
            or "connection reset" in err_lower
            or "transport error" in err_lower
        )
        if is_timeout:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=(
                    "Database atomic confirmation status is uncertain due to network timeout. "
                    "The transaction may have completed. Please verify session state before retrying."
                ),
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database atomic confirmation failed and was rolled back: {err_msg}",
        ) from exc



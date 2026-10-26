"""Ingestion Service for Atomic Database Replacement and Blueprint Trigger (TASK-202)."""

import logging
from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException, status
from supabase import Client

from app.models.schemas import ParsedQuestionItem

logger = logging.getLogger(__name__)


async def replace_source_questions_atomically(
    db: Client,
    session_id: str,
    questions: List[ParsedQuestionItem],
) -> List[Dict[str, Any]]:
    """Atomically replace source questions for an exam session.

    Uses PostgreSQL Stored Procedure `replace_source_questions` (Method 2A) to ensure
    100% database ACID atomicity (Zero orphaned data on failure).
    Fails fast without client-side mutations if RPC is unavailable, guaranteeing Zero Cloud Mutation.
    """
    payload: List[Dict[str, Any]] = [
        {
            "question_no": q.question_no,
            "raw_content": q.raw_content,
            "options": q.options,
            "correct_key": q.correct_key,
            "solution_md": q.solution_md,
            "has_missing_answer": q.has_missing_answer,
            "has_security_warning": q.has_security_warning,
        }
        for q in questions
    ]

    try:
        # Method 2A: Atomic RPC Stored Procedure execution
        rpc_res = db.rpc(
            "replace_source_questions",
            {"p_session_id": session_id, "p_questions": payload},
        ).execute()

        if not (rpc_res.data and isinstance(rpc_res.data, dict) and rpc_res.data.get("success")):
            logger.error(
                "RPC replace_source_questions returned unexpected response for session %s: %s",
                session_id,
                rpc_res.data,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database atomic replacement failed: unexpected RPC response",
            )

        logger.info(
            "Successfully executed atomic RPC replace_source_questions for session %s",
            session_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        err_msg = str(exc)
        err_lower = err_msg.lower()
        logger.error("RPC replace_source_questions failed for session %s: %s", session_id, exc)
        if "42501" in err_msg or "Access denied" in err_msg or "Unauthorized" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied or session ownership mismatch",
            ) from exc
        if "22023" in err_msg or "draft" in err_lower:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot ingest questions: session is not in draft status",
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
                    "Database atomic replacement status is uncertain due to network timeout. "
                    "The transaction may have completed. Please verify session state before retrying."
                ),
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database atomic replacement failed and was rolled back.",
        ) from exc

    # Query and return the newly inserted records
    fetch_res = (
        db.table("source_questions")
        .select("*")
        .eq("session_id", session_id)
        .order("question_no", desc=False)
        .execute()
    )
    return cast(List[Dict[str, Any]], fetch_res.data or [])


async def trigger_blueprint_pipeline(
    session_id: str,
    questions: List[Dict[str, Any]],
    db: Optional[Any] = None,
) -> None:
    """Non-blocking background trigger for AI Blueprint Extraction (TASK-203 hook / TASK-205).

    LIMITATION / SCOPE NOTE:
    This function serves as an asynchronous event hook ensuring blueprints are persisted
    for the session (via deterministic fallback / background pipeline before TASK-203 Gemini AI
    full integration).
    """
    try:
        if db is None:
            try:
                from app.core.database import get_service_role_client

                db = get_service_role_client()
            except Exception as client_err:
                logger.warning(
                    "Could not obtain service role client for background blueprint extraction: %s",
                    client_err,
                )

        if db is not None:
            from app.services.parser.blueprint_service import ensure_blueprints_for_session

            await ensure_blueprints_for_session(db, session_id, questions)
            logger.info("Blueprint pipeline ensured blueprints for session %s", session_id)
        else:
            logger.debug(
                "Blueprint background task completed without DB client for session %s", session_id
            )
    except Exception as exc:
        logger.error("Error in background blueprint pipeline for session %s: %s", session_id, exc)


"""Ingestion Service for Atomic Database Replacement and Blueprint Trigger (TASK-202)."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, cast

import httpx
from fastapi import HTTPException, status

try:
    import httpcore
except ImportError:  # pragma: no cover
    httpcore = None
from postgrest.exceptions import APIError
from supabase import Client

from app.models.schemas import ParsedQuestionItem

logger = logging.getLogger(__name__)

NETWORK_TIMEOUT_EXCEPTIONS = (
    httpx.TimeoutException,
    TimeoutError,
)
if httpcore is not None:
    NETWORK_TIMEOUT_EXCEPTIONS = (
        httpx.TimeoutException,
        httpcore.TimeoutException,
        TimeoutError,
    )

NETWORK_TRANSPORT_EXCEPTIONS = (
    httpx.TransportError,
    httpx.NetworkError,
    httpx.ProtocolError,
    ConnectionError,
)
if httpcore is not None:
    NETWORK_TRANSPORT_EXCEPTIONS = (
        httpx.TransportError,
        httpx.NetworkError,
        httpx.ProtocolError,
        httpcore.NetworkError,
        httpcore.ProtocolError,
        ConnectionError,
    )


def is_network_timeout(exc: BaseException) -> bool:
    """Check if exception or any nested cause/context represents a network timeout."""
    cur: Optional[BaseException] = exc
    while cur is not None:
        if isinstance(cur, NETWORK_TIMEOUT_EXCEPTIONS):
            return True
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    err_lower = str(exc).lower()
    return "timeout" in err_lower or "timed out" in err_lower


def is_network_transport(exc: BaseException) -> bool:
    """Check if exception or any nested cause/context represents a network transport or disconnection error."""
    cur: Optional[BaseException] = exc
    while cur is not None:
        if isinstance(cur, NETWORK_TRANSPORT_EXCEPTIONS):
            return True
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    err_lower = str(exc).lower()
    transport_indicators = (
        "disconnected",
        "connection reset",
        "connection closed",
        "connection error",
        "transport error",
        "remote protocol",
        "remoteprotocolerror",
        "read error",
        "readerror",
        "network error",
        "broken pipe",
    )
    return any(ind in err_lower for ind in transport_indicators)


def is_database_rollback_evidence(exc: BaseException) -> bool:
    """Check if there is concrete evidence from PostgreSQL that the transaction failed and rolled back."""
    cur: Optional[BaseException] = exc
    while cur is not None:
        if isinstance(cur, APIError):
            return True
        if hasattr(cur, "code") and getattr(cur, "code", None):
            return True
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    err_lower = str(exc).lower()
    return any(
        k in err_lower
        for k in (
            "p0001",
            "p0002",
            "23505",
            "22023",
            "42501",
            "sqlstate",
            "transaction error",
            "postgresql",
            "violates",
        )
    )


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
        code = getattr(exc, "code", "") or ""

        if code == "42501" or "42501" in err_msg or "access denied" in err_lower or "unauthorized" in err_lower:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied or session ownership mismatch",
            ) from exc
        if code == "22023" or "22023" in err_msg or "draft" in err_lower:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot ingest questions: session is not in draft status",
            ) from exc
        if code == "P0002" or "p0002" in err_lower or "not found" in err_lower:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            ) from exc

        # 4. Network Timeout (504): Commit status is uncertain
        if is_network_timeout(exc):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=(
                    "Database atomic replacement status is uncertain due to network timeout. "
                    "The transaction may have completed. Please verify session state before retrying."
                ),
            ) from exc

        # 5. Network Disconnection / Lost Response / Transport Error (504): Commit status is uncertain
        if is_network_transport(exc):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=(
                    "Database atomic replacement status is uncertain due to network communication error. "
                    "The transaction may have completed. Please verify session state before retrying."
                ),
            ) from exc

        # 6. Confirmed Database Execution Failure with Rollback Evidence (500)
        if is_database_rollback_evidence(exc):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database atomic replacement failed and was rolled back.",
            ) from exc

        # 7. Unverified / Unexpected Failure without DB Evidence (500):
        # Do not falsely affirm that the transaction was rolled back.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database atomic replacement failed. Please verify session state before retrying.",
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
) -> None:
    """Non-blocking background trigger for AI Blueprint Extraction (TASK-203 integration hook).

    LIMITATION / SCOPE NOTE (TASK-202):
    This function currently serves as an asynchronous event hook / placeholder logging the
    ingestion event with bounded concurrency. Actual Gemini AI extraction and blueprint storage
    are integrated in the subsequent TASK-203 pipeline.
    """
    semaphore = asyncio.Semaphore(3)

    async def _extract_question(q_data: Dict[str, Any]) -> None:
        async with semaphore:
            # Placeholder for TASK-203 Gemini call
            logger.debug(
                "Blueprint hook ready: processing session %s, question %s",
                session_id,
                q_data.get("question_no"),
            )
            await asyncio.sleep(0.01)

    try:
        tasks = [_extract_question(q) for q in questions]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(
            "Blueprint pipeline trigger completed for session %s (%d questions)",
            session_id,
            len(questions),
        )
    except Exception as exc:
        logger.error("Error in background blueprint pipeline for session %s: %s", session_id, exc)

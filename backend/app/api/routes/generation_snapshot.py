"""Durable Stage 2 progress projection for FE2 reload and SSE resync."""

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from postgrest.exceptions import APIError
from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.models.schemas import CurrentUser
from app.services.generation.events import GenerationEventBroker


def create_generation_snapshot_router(events: GenerationEventBroker) -> APIRouter:
    router = APIRouter()

    @router.get("/{session_id}/generation-snapshot")
    async def generation_snapshot(
        session_id: UUID,
        response: Response,
        user: CurrentUser = Depends(get_current_user),
        db: Client = Depends(get_user_db),
    ) -> dict[str, object]:
        await run_in_threadpool(assert_ownership, "exam_sessions", str(session_id), user.id, db=db)
        # Capture the replay mark first. Events published during the database
        # reads will replay after this mark, even when the snapshot already sees them.
        cursor = await events.cursor(session_id)

        def read_session_revision() -> object:
            return (
                db.table("exam_sessions")
                .select("id,status,updated_at")
                .eq("id", str(session_id))
                .limit(1)
                .execute()
                .data
            )

        try:
            # The RPC owns its transaction and does not return session status.
            # Bracket it with the session revision so a finish or retry cannot
            # pair a new status with counts from the preceding job state.
            before, loaded, rows = await run_in_threadpool(
                lambda: (
                    read_session_revision(),
                    db.rpc("load_generation_completed_results", {"p_session_id": str(session_id)})
                    .execute()
                    .data,
                    read_session_revision(),
                )
            )
            if (
                not isinstance(loaded, dict)
                or not isinstance(rows, list)
                or len(rows) != 1
                or not isinstance(rows[0], dict)
            ):
                raise ValueError("Malformed generation snapshot.")
            if loaded.get("session_id") != str(session_id) or rows[0].get("id") != str(session_id):
                raise ValueError("Generation snapshot session changed.")
            if before != rows:
                raise HTTPException(
                    409, {"code": "ERR_CONFIG_CONFLICT", "message": "Reload session state."}
                )
            context = loaded["context"]
            completed = loaded["completed"]
            failures = loaded["failures"]
            if (
                not isinstance(context, dict)
                or not isinstance(completed, list)
                or not isinstance(failures, list)
            ):
                raise ValueError("Malformed generation result collection.")
            sources = context["confirmed_sources"]
            n_versions = context["n_versions"]
            if (
                not isinstance(sources, list)
                or not 1 <= len(sources) <= 20
                or type(n_versions) is not int
                or not 1 <= n_versions <= 4
            ):
                raise ValueError("Malformed frozen generation shape.")
            total = len(sources) * n_versions
            if len(completed) > total:
                raise ValueError("Completed count exceeds frozen targets.")
            status = rows[0]["status"]
            if status not in {"generating", "generated", "partial_generated", "failed"}:
                raise ValueError("Session is outside generation progress states.")
            error_code = loaded.get("generation_error_code")
            if error_code is not None and (
                not isinstance(error_code, str)
                or re.fullmatch(r"[A-Z0-9_]{3,64}", error_code) is None
            ):
                raise ValueError("Malformed durable generation error code.")
            question_statuses: dict[str, dict[str, object]] = {}
            for row in completed:
                if not isinstance(row, dict) or row.get("is_success") is not True:
                    raise ValueError("Malformed completed target.")
                key = f"{row['version_index']}-{row['question_no']}"
                if key in question_statuses:
                    raise ValueError("Duplicate completed target.")
                question_statuses[key] = {"status": "done", "message": "Đã lưu câu hỏi."}
            for row in failures:
                if not isinstance(row, dict) or row.get("is_success") is not False:
                    raise ValueError("Malformed failed target.")
                key = f"{row['version_index']}-{row['question_no']}"
                if key in question_statuses:
                    raise ValueError("Target is both complete and failed.")
                question_statuses[key] = {
                    "status": "failed",
                    "message": "Sinh câu hỏi chưa thành công.",
                }
            response.headers["Cache-Control"] = "no-store"
            return {
                "session_id": str(session_id),
                "session_status": status,
                "status": status,
                "snapshot_id": loaded["snapshot_id"],
                "generation_error_code": error_code,
                "progress": {
                    "completed_count": len(completed),
                    "total_count": total,
                    "percent_complete": len(completed) * 100 / total,
                    "message": "Đã sinh một phần."
                    if status == "partial_generated"
                    else "Tiến trình sinh đề.",
                },
                "question_statuses": question_statuses,
                "stream_epoch": events.epoch,
                "resume_after_event_id": cursor,
            }
        except HTTPException:
            raise
        except APIError as exc:
            if str(getattr(exc, "code", "")) == "55006":
                raise HTTPException(
                    409, {"code": "ERR_CONFIG_CONFLICT", "message": "Reload session state."}
                ) from None
            raise HTTPException(503, "Generation snapshot is temporarily unavailable.") from None
        except Exception:
            raise HTTPException(503, "Generation snapshot is temporarily unavailable.") from None

    return router

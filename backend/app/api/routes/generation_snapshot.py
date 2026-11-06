"""Durable Stage 2 progress projection for FE2 reload and SSE resync."""

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
        try:
            loaded, rows = await run_in_threadpool(
                lambda: (
                    db.rpc("load_generation_completed_results", {"p_session_id": str(session_id)})
                    .execute()
                    .data,
                    db.table("exam_sessions")
                    .select("id,status")
                    .eq("id", str(session_id))
                    .limit(1)
                    .execute()
                    .data,
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
        except APIError as exc:
            if str(getattr(exc, "code", "")) == "55006":
                raise HTTPException(
                    409, {"code": "ERR_CONFIG_CONFLICT", "message": "Reload session state."}
                ) from None
            raise HTTPException(503, "Generation snapshot is temporarily unavailable.") from None
        except Exception:
            raise HTTPException(503, "Generation snapshot is temporarily unavailable.") from None

    return router

"""SSE router factory; explicit current-owner lookup is required for product wiring."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import partial
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter
from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.core.rate_limit import crud_rate_limit
from app.core.rate_limit import limiter as default_limiter
from app.models.schemas import CurrentUser
from app.services.generation.events import (
    EventBufferCapacityError,
    EventHistoryLost,
    GenerationEventBroker,
)
from app.services.generation.tickets import (
    InvalidStreamTicket,
    StreamTicketStore,
    TicketCapacityError,
)
from app.services.observability.runtime_registry import RuntimeRegistry


class StreamTicketResponse(BaseModel):
    ticket: UUID
    expires_at: datetime


def create_generation_stream_router(
    *,
    tickets: StreamTicketStore,
    events: GenerationEventBroker,
    registry: RuntimeRegistry,
    is_current_owner: Callable[[UUID, UUID], Awaitable[bool]],
    limiter_instance: Limiter = default_limiter,
) -> APIRouter:
    """is_current_owner must use trusted server-side data, not request claims.

    It is mandatory because EventSource supplies a ticket rather than a Bearer
    token. No default service-role client or editable user metadata is used.
    """
    router = APIRouter()
    limit_crud = partial(crud_rate_limit, limiter_instance=limiter_instance)

    @router.post("/{session_id}/events/ticket", response_model=StreamTicketResponse)
    @limit_crud
    async def issue_ticket(
        session_id: UUID,
        request: Request,
        response: Response,
        user: CurrentUser = Depends(get_current_user),
        db: Client = Depends(get_user_db),
    ) -> StreamTicketResponse:
        await run_in_threadpool(assert_ownership, "exam_sessions", str(session_id), user.id, db=db)
        try:
            ticket = await tickets.issue(session_id, UUID(user.id))
        except TicketCapacityError:
            raise HTTPException(503, "Stream ticket service is temporarily unavailable.") from None
        response.headers["Cache-Control"] = "no-store"
        return StreamTicketResponse(ticket=ticket.ticket_id, expires_at=ticket.expires_at)

    @router.get("/{session_id}/events")
    async def stream_events(
        session_id: UUID,
        ticket: UUID,
        last_event_id: Annotated[int | None, Query(ge=0)] = None,
        last_event_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        if last_event_id is None:
            if last_event_header is not None and not last_event_header.isascii():
                raise HTTPException(422, "Invalid event cursor.")
            if last_event_header is not None and not last_event_header.isdecimal():
                raise HTTPException(422, "Invalid event cursor.")
            try:
                last_event_id = int(last_event_header) if last_event_header is not None else 0
            except ValueError:
                raise HTTPException(422, "Invalid event cursor.") from None
        try:
            identity = await tickets.consume(ticket, session_id)
        except InvalidStreamTicket:
            raise HTTPException(401, "Invalid or expired stream ticket.") from None
        try:
            authorized = await is_current_owner(identity.session_id, identity.user_id)
        except Exception:
            raise HTTPException(503, "Stream authorization is temporarily unavailable.") from None
        if authorized is not True:
            raise HTTPException(403, "You do not have permission to access this stream.")
        try:
            await events.check_cursor(session_id, last_event_id)
        except EventHistoryLost:
            raise HTTPException(
                409,
                {
                    "code": "ERR_EVENT_HISTORY_LOST",
                    "message": "Reload saved progress before reconnecting.",
                },
            ) from None
        except EventBufferCapacityError:
            raise HTTPException(503, "Stream service is temporarily unavailable.") from None
        try:
            registry.snapshot()
        except Exception:
            raise HTTPException(503, "Stream service is temporarily unavailable.") from None
        return StreamingResponse(
            events.stream(session_id, last_event_id=last_event_id, registry=registry),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router

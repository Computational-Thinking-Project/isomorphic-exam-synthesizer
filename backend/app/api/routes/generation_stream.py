"""SSE router factory; explicit current-owner lookup is required for product wiring."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime
from functools import partial
from typing import Annotated
from uuid import UUID

from anyio import CancelScope
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter
from starlette.concurrency import run_in_threadpool
from starlette.types import Receive, Scope, Send
from supabase import Client

from app.api.dependencies import assert_ownership, get_current_user, get_user_db
from app.core.rate_limit import crud_rate_limit
from app.core.rate_limit import limiter as default_limiter
from app.models.schemas import CurrentUser
from app.services.generation.events import (
    EventBufferCapacityError,
    EventBufferLease,
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


class GenerationStreamingResponse(StreamingResponse):
    """Own the generator across ASGI send failures and disconnect cancellation.

    StreamingResponse can fail while sending a yielded chunk, outside the
    generator's finally block. Explicitly close it, without relying on GC.
    """

    def __init__(
        self, stream: AsyncGenerator[str, None], *, lease: EventBufferLease | None = None
    ) -> None:
        self._stream = stream
        self._lease = lease
        super().__init__(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # ASGI <2.4 uses an AnyIO cancellation scope for disconnects. Its
            # cancellation must not interrupt the broker's async cleanup lock.
            with CancelScope(shield=True):
                try:
                    await self._stream.aclose()
                finally:
                    if self._lease is not None:
                        await self._lease.close()


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
            registry.snapshot()
            lease = await events.reserve_session(session_id, last_event_id=last_event_id)
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
        except Exception:
            raise HTTPException(503, "Stream service is temporarily unavailable.") from None
        return GenerationStreamingResponse(
            events.stream(session_id, last_event_id=last_event_id, registry=registry),
            lease=lease,
        )

    return router

"""Single-worker, single-use SSE tickets issued only after Auth/ownership."""

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4


class InvalidStreamTicket(ValueError):
    pass


class TicketCapacityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StreamTicket:
    ticket_id: UUID
    session_id: UUID
    user_id: UUID
    expires_at: datetime


class StreamTicketStore:
    """Bounded live tickets, no JWTs; expiry uses monotonic time, not wall time.

    One store per event loop/worker. The HTTP issuer must verify ownership first;
    the stream route must recheck current ownership after consuming a ticket.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        max_tickets: int = 4096,
    ) -> None:
        if type(max_tickets) is not int or max_tickets < 1:
            raise ValueError("Ticket capacity must be positive.")
        self._clock = clock
        self._utcnow = utcnow
        self._capacity = max_tickets
        self._lock = asyncio.Lock()
        self._tickets: dict[UUID, tuple[StreamTicket, float]] = {}

    def _now(self) -> float:
        now = self._clock()
        if isinstance(now, bool) or not math.isfinite(now):
            raise ValueError("Invalid ticket clock.")
        return now

    def _prune(self, now: float) -> None:
        expired = [key for key, (_, deadline) in self._tickets.items() if deadline <= now]
        for key in expired:
            del self._tickets[key]

    async def issue(self, session_id: UUID, user_id: UUID) -> StreamTicket:
        if not isinstance(session_id, UUID) or not isinstance(user_id, UUID):
            raise TypeError("Ticket identities must be UUIDs.")
        now = self._now()
        wall = self._utcnow()
        if wall.tzinfo is None or wall.utcoffset() is None:
            raise ValueError("Ticket expiration must have a timezone.")
        ticket = StreamTicket(uuid4(), session_id, user_id, wall + timedelta(seconds=60))
        async with self._lock:
            self._prune(now)
            if len(self._tickets) >= self._capacity:
                raise TicketCapacityError("Stream ticket capacity reached.")
            self._tickets[ticket.ticket_id] = (ticket, now + 60)
        return ticket

    async def consume(self, ticket_id: UUID, session_id: UUID) -> StreamTicket:
        async with self._lock:
            now = self._now()
            self._prune(now)
            entry = self._tickets.get(ticket_id)
            if entry is None or entry[0].session_id != session_id:
                raise InvalidStreamTicket("Invalid or expired stream ticket.")
            del self._tickets[ticket_id]
            return entry[0]

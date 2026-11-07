"""Single-worker, single-use SSE tickets issued only after Auth/ownership."""

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.services.generation.events import EventBufferLease


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
    lease: EventBufferLease | None = field(default=None, compare=False, repr=False)


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

    def _prune(self, now: float) -> list[EventBufferLease]:
        expired = [key for key, (_, deadline) in self._tickets.items() if deadline <= now]
        leases = []
        for key in expired:
            ticket, _ = self._tickets.pop(key)
            if ticket.lease is not None:
                leases.append(ticket.lease)
        return leases

    @staticmethod
    async def _close_leases(leases: list[EventBufferLease]) -> None:
        for lease in leases:
            await lease.close()

    async def issue(
        self, session_id: UUID, user_id: UUID, *, lease: EventBufferLease | None = None
    ) -> StreamTicket:
        if not isinstance(session_id, UUID) or not isinstance(user_id, UUID):
            raise TypeError("Ticket identities must be UUIDs.")
        now = self._now()
        wall = self._utcnow()
        if wall.tzinfo is None or wall.utcoffset() is None:
            raise ValueError("Ticket expiration must have a timezone.")
        ticket = StreamTicket(uuid4(), session_id, user_id, wall + timedelta(seconds=60), lease)
        async with self._lock:
            expired = self._prune(now)
        await self._close_leases(expired)
        async with self._lock:
            if len(self._tickets) >= self._capacity:
                raise TicketCapacityError("Stream ticket capacity reached.")
            self._tickets[ticket.ticket_id] = (ticket, self._now() + 60)
        return ticket

    async def consume(self, ticket_id: UUID, session_id: UUID) -> StreamTicket:
        async with self._lock:
            expired = self._prune(self._now())
        await self._close_leases(expired)
        async with self._lock:
            entry = self._tickets.get(ticket_id)
            if entry is not None and entry[0].session_id == session_id:
                del self._tickets[ticket_id]
                if entry[1] > self._now():
                    return entry[0]
                expired_ticket = entry[0]
            else:
                expired_ticket = None
        if expired_ticket is not None and expired_ticket.lease is not None:
            await expired_ticket.lease.close()
        raise InvalidStreamTicket("Invalid or expired stream ticket.")

    async def prune_expired(self) -> None:
        async with self._lock:
            expired = self._prune(self._now())
        await self._close_leases(expired)

    async def close(self) -> None:
        async with self._lock:
            leases = [ticket.lease for ticket, _ in self._tickets.values() if ticket.lease]
            self._tickets.clear()
        await self._close_leases(leases)

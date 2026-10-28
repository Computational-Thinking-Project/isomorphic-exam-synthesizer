"""Bounded per-session event history, replay, heartbeat and disconnect cleanup."""

import asyncio
import math
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from app.models.generation_events import EventName, GenerationEvent, GenerationEventData
from app.services.observability.runtime_registry import RuntimeRegistry


class EventHistoryLost(ValueError):
    """Client must reload durable progress before taking a fresh stream cursor."""


class EventBufferCapacityError(RuntimeError):
    pass


@dataclass
class _SessionEvents:
    events: deque[GenerationEvent] = field(default_factory=lambda: deque(maxlen=50))
    next_id: int = 1
    terminal: bool = False
    subscribers: int = 0
    reservations: set[object] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class EventBufferLease:
    """An idempotent reservation for a pending job or HTTP stream response."""

    _release: Callable[[], Awaitable[None]]

    async def close(self) -> None:
        await self._release()


class GenerationEventBroker:
    """Share one instance per loop/worker. Never await network I/O under the condition.

    History survives disconnects and contains at most 50 events per session.
    Capacity fails explicitly, rather than silently evicting a running session.
    """

    def __init__(self, *, max_sessions: int = 1024) -> None:
        if type(max_sessions) is not int or max_sessions < 1:
            raise ValueError("Event session capacity must be positive.")
        self._capacity = max_sessions
        self._sessions: dict[UUID, _SessionEvents] = {}
        self._condition = asyncio.Condition()

    def _session(self, session_id: UUID) -> _SessionEvents:
        if session_id not in self._sessions:
            if len(self._sessions) >= self._capacity:
                raise EventBufferCapacityError("Event session capacity reached.")
            self._sessions[session_id] = _SessionEvents()
        return self._sessions[session_id]

    @staticmethod
    def _after(session: _SessionEvents, cursor: int) -> tuple[GenerationEvent, ...]:
        latest = session.next_id - 1
        if cursor > latest or (session.events and cursor < session.events[0].id - 1):
            raise EventHistoryLost("Event history unavailable; reload saved progress.")
        return tuple(
            event
            for event in session.events
            if event.id > cursor
            and (event.event not in {"done", "error"} or (session.terminal and event.id == latest))
        )

    async def publish(
        self,
        session_id: UUID,
        event: EventName,
        data: GenerationEventData,
    ) -> GenerationEvent:
        # Revalidate even mutated/model_construct instances before retaining data.
        checked = GenerationEventData.model_validate(data.model_dump())
        async with self._condition:
            session = self._session(session_id)
            if session.terminal:
                raise ValueError("A terminal stream must be reopened before publishing.")
            result = GenerationEvent(id=session.next_id, event=event, data=checked)
            session.events.append(result)
            session.next_id += 1
            session.terminal = event in {"done", "error"}
            self._condition.notify_all()
            return result

    async def reopen(self, session_id: UUID) -> None:
        """After a durable retry claim, retain history and monotonic event IDs."""
        async with self._condition:
            self._session(session_id).terminal = False

    def _drop_empty(self, session_id: UUID, session: _SessionEvents) -> None:
        # Called under the condition. A failed claim/disconnected empty watcher
        # has no history to retain, but another owner may still need this slot.
        if (
            self._sessions.get(session_id) is session
            and not session.events
            and not session.subscribers
            and not session.reservations
        ):
            del self._sessions[session_id]

    async def reserve_session(
        self,
        session_id: UUID,
        *,
        last_event_id: int | None = None,
    ) -> EventBufferLease:
        if last_event_id is not None and (type(last_event_id) is not int or last_event_id < 0):
            raise ValueError("Event cursor must be a nonnegative integer.")
        token = object()
        async with self._condition:
            existing = self._sessions.get(session_id)
            if last_event_id is not None:
                # Validate before allocating; a bad cursor must not consume capacity.
                self._after(existing if existing is not None else _SessionEvents(), last_event_id)
            session = self._session(session_id)
            session.reservations.add(token)
        return EventBufferLease(lambda: self._release_session(session_id, session, token))

    async def _release_session(
        self, session_id: UUID, session: _SessionEvents, token: object
    ) -> None:
        async with self._condition:
            if self._sessions.get(session_id) is not session:
                return
            session.reservations.discard(token)
            self._drop_empty(session_id, session)

    async def check_cursor(self, session_id: UUID, cursor: int = 0) -> None:
        if type(cursor) is not int or cursor < 0:
            raise ValueError("Event cursor must be a nonnegative integer.")
        async with self._condition:
            session = self._sessions.get(session_id)
            self._after(session if session is not None else _SessionEvents(), cursor)
            if session is None and len(self._sessions) >= self._capacity:
                raise EventBufferCapacityError("Event session capacity reached.")

    async def forget(self, session_id: UUID) -> bool:
        """Explicit cleanup only for terminal histories with no active subscribers."""
        async with self._condition:
            session = self._sessions.get(session_id)
            if session is None:
                return True
            if not session.terminal or session.subscribers or session.reservations:
                return False
            del self._sessions[session_id]
            return True

    async def stream(
        self,
        session_id: UUID,
        *,
        last_event_id: int = 0,
        registry: RuntimeRegistry,
        heartbeat_seconds: float = 15,
    ) -> AsyncGenerator[str, None]:
        if (
            isinstance(heartbeat_seconds, bool)
            or not math.isfinite(heartbeat_seconds)
            or heartbeat_seconds <= 0
        ):
            raise ValueError("Heartbeat interval must be positive and finite.")
        await self.check_cursor(session_id, last_event_id)
        async with self._condition:
            session = self._session(session_id)
            try:
                handle = registry.begin_sse_connection()
            except Exception:
                self._drop_empty(session_id, session)
                raise
            session.subscribers += 1
        cursor = last_event_id
        try:
            # Establish immediately; no need to wait 15 seconds for the first bytes.
            yield ": connected\n\n"
            while True:
                heartbeat = False
                async with self._condition:
                    try:
                        pending = self._after(session, cursor)
                    except EventHistoryLost:
                        pending = ()
                        lost = True
                    else:
                        lost = False
                    terminal = session.terminal
                    if not pending and not terminal and not lost:
                        try:
                            await asyncio.wait_for(self._condition.wait(), heartbeat_seconds)
                        except TimeoutError:
                            heartbeat = True
                        if not heartbeat:
                            continue
                if lost:
                    error = GenerationEvent(
                        id=cursor + 1,
                        event="error",
                        data=GenerationEventData(
                            timestamp=datetime.now(timezone.utc),
                            status="warning",
                            percent_complete=0,
                            error_code="ERR_EVENT_HISTORY_LOST",
                            error_message="Reload saved progress before reconnecting.",
                        ),
                    )
                    # This is a connection error, not a newly persisted job event.
                    yield f"event: error\ndata: {error.data.model_dump_json()}\n\n"
                    return
                if heartbeat:
                    yield ": heartbeat\n\n"
                    continue
                for event in pending:
                    cursor = event.id
                    yield event.to_sse()
                if terminal:
                    return
        finally:
            handle.close()
            async with self._condition:
                session.subscribers -= 1
                self._drop_empty(session_id, session)

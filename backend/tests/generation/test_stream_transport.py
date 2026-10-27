import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.generation_events import GenerationEvent, GenerationEventData
from app.services.generation.events import EventHistoryLost, GenerationEventBroker
from app.services.generation.tickets import (
    InvalidStreamTicket,
    StreamTicketStore,
    TicketCapacityError,
)
from app.services.observability.runtime_registry import RuntimeRegistry


def data(percent: float = 0) -> GenerationEventData:
    return GenerationEventData(
        timestamp=datetime.now(timezone.utc), status="generating", percent_complete=percent
    )


def test_ticket_expiry_binding_single_use_and_pruning() -> None:
    async def scenario() -> None:
        now = [0.0]
        wall = datetime(2026, 10, 27, tzinfo=timezone.utc)
        tickets = StreamTicketStore(clock=lambda: now[0], utcnow=lambda: wall, max_tickets=1)
        sid, uid = uuid4(), uuid4()
        ticket = await tickets.issue(sid, uid)
        assert (ticket.expires_at - wall).total_seconds() == 60
        with pytest.raises(InvalidStreamTicket):
            await tickets.consume(ticket.ticket_id, uuid4())
        assert (await tickets.consume(ticket.ticket_id, sid)).user_id == uid
        with pytest.raises(InvalidStreamTicket):
            await tickets.consume(ticket.ticket_id, sid)
        expired = await tickets.issue(sid, uid)
        with pytest.raises(TicketCapacityError):
            await tickets.issue(sid, uid)
        now[0] = 60
        with pytest.raises(InvalidStreamTicket):
            await tickets.consume(expired.ticket_id, sid)
        assert await tickets.issue(sid, uid)

    asyncio.run(scenario())


def test_ticket_concurrent_consume_has_one_winner() -> None:
    async def scenario() -> None:
        tickets = StreamTicketStore()
        sid = uuid4()
        ticket = await tickets.issue(sid, uuid4())
        results = await asyncio.gather(
            *(tickets.consume(ticket.ticket_id, sid) for _ in range(20)), return_exceptions=True
        )
        assert sum(not isinstance(result, BaseException) for result in results) == 1

    asyncio.run(scenario())


def test_sse_json_cannot_inject_frames_and_native_fields_match() -> None:
    event = GenerationEvent(
        id=3,
        event="warning",
        data=data().model_copy(update={"error_message": "line\n\nevent: done"}),
    )
    frame = event.to_sse()
    assert frame.startswith("id: 3\nevent: warning\ndata: ")
    assert frame.count("\n\n") == 1
    payload = json.loads(frame.split("data: ", 1)[1])
    assert payload["id"] == 3 and payload["data"]["error_message"] == "line\n\nevent: done"


@pytest.mark.parametrize("bad", [True, -1, float("nan"), float("inf"), 101, "5"])
def test_event_percent_rejects_invalid_values(bad: object) -> None:
    with pytest.raises(ValidationError):
        GenerationEventData.model_validate(
            {
                "timestamp": datetime.now(timezone.utc),
                "status": "generating",
                "percent_complete": bad,
            }
        )


def test_replay_terminal_close_and_runtime_cleanup() -> None:
    async def scenario() -> None:
        registry = RuntimeRegistry()
        registry.start()
        broker = GenerationEventBroker()
        sid = uuid4()
        await broker.publish(sid, "progress", data(10))
        await broker.publish(sid, "question_done", data(80))
        await broker.publish(sid, "done", data(100))
        stream = broker.stream(sid, last_event_id=1, registry=registry)
        assert await anext(stream) == ": connected\n\n"
        assert registry.snapshot().active_sse_connections == 1
        assert "id: 2\n" in await anext(stream)
        assert "id: 3\n" in await anext(stream)
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        assert registry.snapshot().active_sse_connections == 0
        await broker.reopen(sid)
        assert (await broker.publish(sid, "progress", data())).id == 4

    asyncio.run(scenario())


def test_ring_capacity_and_stale_future_cursors() -> None:
    async def scenario() -> None:
        registry = RuntimeRegistry()
        registry.start()
        broker = GenerationEventBroker()
        sid = uuid4()
        for _ in range(60):
            await broker.publish(sid, "progress", data())
        with pytest.raises(EventHistoryLost):
            await broker.check_cursor(sid, 9)
        with pytest.raises(EventHistoryLost):
            await broker.check_cursor(sid, 61)
        stream = broker.stream(sid, last_event_id=10, registry=registry)
        await anext(stream)
        assert "id: 11\n" in await anext(stream)
        await stream.aclose()
        assert registry.snapshot().active_sse_connections == 0

    asyncio.run(scenario())


def test_heartbeat_live_delivery_disconnect_and_slow_subscriber() -> None:
    async def scenario() -> None:
        registry = RuntimeRegistry()
        registry.start()
        broker = GenerationEventBroker()
        sid = uuid4()
        stream = broker.stream(sid, registry=registry, heartbeat_seconds=0.01)
        await anext(stream)
        assert await anext(stream) == ": heartbeat\n\n"
        waiter = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        await broker.publish(sid, "progress", data(30))
        assert "id: 1\n" in await waiter
        for _ in range(51):
            await broker.publish(sid, "progress", data(40))
        message = await anext(stream)
        assert "ERR_EVENT_HISTORY_LOST" in message
        assert not message.startswith("id:")
        assert "id" not in json.loads(message.split("data: ", 1)[1])
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        assert registry.snapshot().active_sse_connections == 0

    asyncio.run(scenario())


def test_cancelled_waiter_releases_connection_and_allows_cleanup() -> None:
    async def scenario() -> None:
        registry = RuntimeRegistry()
        registry.start()
        broker = GenerationEventBroker()
        sid = uuid4()
        stream = broker.stream(sid, registry=registry)
        await anext(stream)
        waiter = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert registry.snapshot().active_sse_connections == 0
        assert not await broker.forget(sid)
        await broker.publish(sid, "error", data())
        assert await broker.forget(sid)

    asyncio.run(scenario())


def test_two_subscribers_count_connections_not_sessions() -> None:
    async def scenario() -> None:
        registry = RuntimeRegistry()
        registry.start()
        broker = GenerationEventBroker()
        sid = uuid4()
        streams = [broker.stream(sid, registry=registry) for _ in range(2)]
        for stream in streams:
            await anext(stream)
        assert registry.snapshot().active_sse_connections == 2
        for stream in streams:
            await stream.aclose()
        assert registry.snapshot().active_sse_connections == 0

    asyncio.run(scenario())


def test_retry_replay_does_not_deliver_terminal_event_from_previous_job() -> None:
    async def scenario() -> None:
        registry = RuntimeRegistry()
        registry.start()
        broker = GenerationEventBroker()
        sid = uuid4()
        await broker.publish(sid, "progress", data(10))
        await broker.publish(sid, "error", data(10))
        await broker.reopen(sid)
        await broker.publish(sid, "progress", data(50))
        await broker.publish(sid, "done", data(100))
        frames = [frame async for frame in broker.stream(sid, registry=registry)]
        assert not any("event: error\n" in frame for frame in frames)
        assert sum("event: done\n" in frame for frame in frames) == 1
        assert "id: 4\n" in frames[-1]

    asyncio.run(scenario())


def test_retry_watcher_waits_for_new_progress_instead_of_old_terminal() -> None:
    async def scenario() -> None:
        registry = RuntimeRegistry()
        registry.start()
        broker = GenerationEventBroker()
        sid = uuid4()
        await broker.publish(sid, "error", data())
        await broker.reopen(sid)
        stream = broker.stream(sid, registry=registry)
        await anext(stream)
        waiter = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        await broker.publish(sid, "progress", data(50))
        assert "event: progress\n" in await waiter
        await stream.aclose()

    asyncio.run(scenario())

"""Single-worker scanner for migration 017's fenced stale-job RPCs."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.core.database import get_service_role_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StaleCursor:
    activity_at: datetime
    session_id: UUID


@dataclass(frozen=True, slots=True)
class StaleJob:
    session_id: UUID
    job_token: UUID


@dataclass(frozen=True, slots=True)
class StalePage:
    items: tuple[StaleJob, ...]
    next_cursor: StaleCursor | None
    has_more: bool


class StaleJobRepository:
    """Only a trusted server-side service-role client may call these RPCs."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    def _db(self) -> Client:
        return self._client if self._client is not None else get_service_role_client()

    async def list_page(self, cursor: StaleCursor | None) -> StalePage:
        params: dict[str, object] = {"p_cutoff_seconds": 720, "p_limit": 100}
        if cursor is not None:
            params["p_after_activity_at"] = cursor.activity_at.isoformat()
            params["p_after_session_id"] = str(cursor.session_id)
        value = await run_in_threadpool(
            lambda: self._db().rpc("list_stale_generation_jobs", params).execute().data
        )
        if not isinstance(value, dict) or value.get("cutoff_seconds") != 720:
            raise ValueError("Malformed stale-job page.")
        scan_as_of = datetime.fromisoformat(value["scan_as_of"])
        if scan_as_of.tzinfo is None:
            raise ValueError("Stale-job scan timestamp needs a timezone.")
        rows = value.get("items")
        more = value.get("has_more")
        raw_cursor = value.get("next_cursor")
        if not isinstance(rows, list) or len(rows) > 100 or type(more) is not bool:
            raise ValueError("Malformed stale-job page.")
        items: list[StaleJob] = []
        last_activity: datetime | None = None
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Malformed stale-job item.")
            items.append(StaleJob(UUID(row["session_id"]), UUID(row["job_token"])))
            last_activity = datetime.fromisoformat(row["last_activity_at"])
            if last_activity.tzinfo is None:
                raise ValueError("Stale-job activity timestamp needs a timezone.")
        next_cursor = None
        if more:
            if not rows or not isinstance(raw_cursor, dict):
                raise ValueError("Missing stale-job cursor.")
            next_cursor = StaleCursor(
                datetime.fromisoformat(raw_cursor["last_activity_at"]),
                UUID(raw_cursor["session_id"]),
            )
            if next_cursor.activity_at.tzinfo is None:
                raise ValueError("Stale-job cursor needs a timezone.")
            if (
                next_cursor.session_id != items[-1].session_id
                or next_cursor.activity_at != last_activity
            ):
                raise ValueError("Stale-job cursor differs from the last item.")
        elif raw_cursor is not None:
            raise ValueError("Unexpected stale-job cursor.")
        return StalePage(tuple(items), next_cursor, more)

    async def fail_if_current(self, item: StaleJob) -> bool:
        value = await run_in_threadpool(
            lambda: (
                self._db()
                .rpc(
                    "fail_stale_generation_job_if_current",
                    {
                        "p_session_id": str(item.session_id),
                        "p_expected_job_token": str(item.job_token),
                        "p_cutoff_seconds": 720,
                    },
                )
                .execute()
                .data
            )
        )
        if (
            not isinstance(value, dict)
            or value.get("session_id") != str(item.session_id)
            or type(value.get("recovered")) is not bool
        ):
            raise ValueError("Malformed fenced recovery receipt.")
        if value["recovered"] and (
            value.get("previous_job_id") != str(item.job_token)
            or value.get("status") != "failed"
            or value.get("error_code") != "ERR_GENERATION_INTERRUPTED"
        ):
            raise ValueError("Malformed recovered job receipt.")
        if not value["recovered"] and value.get("reason") not in {
            "status_not_generating",
            "token_mismatch",
            "activity_not_stale",
        }:
            raise ValueError("Malformed stale-job no-op receipt.")
        return value["recovered"]


class GenerationRecoveryScanner:
    def __init__(self, repository: StaleJobRepository) -> None:
        self._repository = repository
        self._cursor: StaleCursor | None = None

    async def scan_once(self) -> int:
        """Process one bounded page; advance the cursor only after every item."""
        try:
            page = await self._repository.list_page(self._cursor)
            recovered = 0
            for item in page.items:
                recovered += int(await self._repository.fail_if_current(item))
            self._cursor = page.next_cursor
            return recovered
        except Exception:
            self._cursor = None
            raise

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                recovered = await self.scan_once()
                if recovered:
                    logger.info("Recovered %d stale generation jobs.", recovered)
            except Exception:
                logger.warning("Generation recovery scan failed; will retry.")
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except TimeoutError:
                pass

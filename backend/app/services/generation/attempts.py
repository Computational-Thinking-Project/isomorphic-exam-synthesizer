"""Database-free dispatch permits for review regeneration.

The repository callback owns durable accounting. Acknowledged permits are a
conservative local count, never proof of how many requests reached the provider.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.services.ai.gateway import GatewayError


class AttemptPermit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    attempt_id: UUID
    dispatch_permitted: StrictBool
    calls_used: Annotated[StrictInt, Field(ge=0, le=30)]
    remaining_calls: Annotated[StrictInt, Field(ge=0, le=30)]
    replayed: StrictBool


AcquireAttempt = Callable[[UUID, UUID], Awaitable[AttemptPermit]]


class DurableAttemptBudget:
    def __init__(self, limit: int, operation_id: UUID, acquire_attempt: AcquireAttempt):
        if not 1 <= limit <= 4:
            raise ValueError("Review operations allow 1–4 attempts")
        self.limit = limit
        self.operation_id = operation_id
        self.acquire_attempt = acquire_attempt
        self.used = 0
        self._lock = asyncio.Lock()
        self._failure: str | None = None

    async def reserve(self) -> None:
        async with self._lock:
            if self._failure:
                raise GatewayError(self._failure)
            if self.used >= self.limit:
                raise GatewayError("REQUEST_BUDGET_EXHAUSTED")
            attempt_id = uuid4()
            # Until a valid initial grant is acknowledged, outcome is uncertain.
            # Cancellation/transport loss must never authorize another dispatch.
            self._failure = "REVIEW_PERMIT_UNCERTAIN"
            try:
                permit = await self.acquire_attempt(self.operation_id, attempt_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                raise GatewayError(self._failure) from None
            if (
                not isinstance(permit, AttemptPermit)
                or permit.operation_id != self.operation_id
                or permit.attempt_id != attempt_id
            ):
                self._failure = "REVIEW_PERMIT_INVALID"
            elif permit.replayed:
                self._failure = "REVIEW_ATTEMPT_REPLAYED"
            elif not permit.dispatch_permitted:
                self._failure = "REVIEW_QUOTA_EXHAUSTED"
            elif permit.calls_used < self.used + 1:
                self._failure = "REVIEW_PERMIT_INVALID"
            else:
                self.used += 1
                self._failure = None
                return
            raise GatewayError(self._failure)

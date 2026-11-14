"""Shared async transport: one call is one accounted Gemini request.

Content repair/retry belongs to the caller. This module only selects available
credentials and bounds concurrency, waiting and transport time.
"""

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import Settings

logger = logging.getLogger(__name__)

GeminiAttemptOutcome = Literal["success", "error", "timeout", "cancelled"]
_OBSERVABLE_ERROR_CODES = {
    "API_AUTH",
    "API_CLIENT",
    "API_RATE_LIMIT",
    "API_REQUEST",
    "API_TIMEOUT",
    "API_TRANSPORT",
    "JOB_DEADLINE",
}


@dataclass(frozen=True)
class GeminiAttemptEvent:
    attempt_id: UUID
    model: str
    stage: str | None
    duration_seconds: float
    outcome: GeminiAttemptOutcome
    error_code: str | None


GeminiAttemptCompletion = Callable[[GeminiAttemptEvent], None]
GeminiAttemptObserver = Callable[[], GeminiAttemptCompletion]


class GatewayError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class RequestBudget:
    """Atomic budget for a local job; DB-backed reservation can replace reserve."""

    def __init__(self, limit: int):
        if limit < 1:
            raise ValueError("Request budget must be positive")
        self.limit = limit
        self.used = 0
        self._lock = asyncio.Lock()

    async def reserve(self) -> None:
        async with self._lock:
            if self.used >= self.limit:
                raise GatewayError("REQUEST_BUDGET_EXHAUSTED")
            self.used += 1


@dataclass(frozen=True)
class RequestContext:
    # Absolute monotonic time, shared across retries and all job stages.
    deadline: float
    reserve_request: Callable[[], Awaitable[None]]


@dataclass
class _Credential:
    client: genai.Client
    available_at: float = 0
    disabled: bool = False


class GeminiGateway:
    def __init__(self, config: Settings, *, attempt_observer: GeminiAttemptObserver | None = None):
        keys = config.get_gemini_api_keys()
        if not keys:
            raise GatewayError("API_KEY_MISSING")
        self.model = config.GEMINI_MODEL
        self._timeout = config.GEMINI_REQUEST_TIMEOUT_SECONDS
        self._cooldown = config.GEMINI_KEY_COOLDOWN_SECONDS
        self._semaphore = asyncio.Semaphore(config.GEMINI_MAX_CONCURRENCY)
        self._selection_lock = asyncio.Lock()
        self._closed = False
        self._attempt_observer = attempt_observer
        self._credentials = [
            _Credential(
                genai.Client(
                    api_key=key,
                    http_options=types.HttpOptions(
                        timeout=int(self._timeout * 1000),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
            )
            for key in keys
        ]

    async def _select(self) -> _Credential:
        while True:
            if self._closed:
                raise GatewayError("GATEWAY_CLOSED")
            async with self._selection_lock:
                enabled = [entry for entry in self._credentials if not entry.disabled]
                if not enabled:
                    raise GatewayError("API_NO_AVAILABLE_KEYS")
                now = time.monotonic()
                ready = [entry for entry in enabled if entry.available_at <= now]
                if ready:
                    return secrets.choice(ready)
                delay = min(entry.available_at for entry in enabled) - now
            await asyncio.sleep(delay)

    async def generate_content(
        self, *, contents: str, config: types.GenerateContentConfig, context: RequestContext
    ) -> types.GenerateContentResponse:
        if self._closed:
            raise GatewayError("GATEWAY_CLOSED")
        completion = None
        attempt_id = None
        started_at = 0.0
        outcome: GeminiAttemptOutcome = "cancelled"
        error_code = None
        try:
            async with asyncio.timeout_at(context.deadline):
                async with self._semaphore:
                    entry = await self._select()
                    if time.monotonic() >= context.deadline:
                        raise GatewayError("JOB_DEADLINE")
                    # Reserve immediately before transport, never when merely queued.
                    await context.reserve_request()
                    if time.monotonic() >= context.deadline:
                        raise GatewayError("JOB_DEADLINE")
                    if self._attempt_observer is not None:
                        try:
                            attempt_id = uuid4()
                            completion = self._attempt_observer()
                            started_at = time.monotonic()
                        except Exception:
                            logger.warning("Gemini attempt observer could not start.")
                    response = await self._send(entry, contents, config)
        except TimeoutError:
            outcome = "timeout"
            error_code = "JOB_DEADLINE"
            raise GatewayError(error_code, retryable=False) from None
        except GatewayError as exc:
            outcome = "timeout" if exc.code == "API_TIMEOUT" else "error"
            error_code = exc.code if exc.code in _OBSERVABLE_ERROR_CODES else "API_CLIENT"
            raise
        else:
            outcome = "success"
            return response
        finally:
            if completion is not None and attempt_id is not None:
                try:
                    completion(
                        GeminiAttemptEvent(
                            attempt_id=attempt_id,
                            model=self.model,
                            stage=None,
                            duration_seconds=time.monotonic() - started_at,
                            outcome=outcome,
                            error_code=error_code,
                        )
                    )
                except Exception:
                    logger.warning("Gemini attempt observer could not finish.")

    async def _send(
        self, entry: _Credential, contents: str, config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        try:
            async with asyncio.timeout(self._timeout):
                return await entry.client.aio.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
        except errors.APIError as exc:
            status = exc.code
            if status in {401, 403}:
                entry.disabled = True
                raise GatewayError(
                    "API_AUTH", retryable=any(not key.disabled for key in self._credentials)
                ) from None
            if status == 429:
                entry.available_at = time.monotonic() + self._cooldown
            raise GatewayError(
                "API_RATE_LIMIT" if status == 429 else "API_REQUEST",
                retryable=status in {408, 429, 500, 502, 503, 504},
            ) from None
        except TimeoutError:
            raise GatewayError("API_TIMEOUT", retryable=True) from None
        except (httpx.TransportError, OSError):
            raise GatewayError("API_TRANSPORT", retryable=True) from None
        except GatewayError:
            raise
        except Exception:
            # SDK exceptions may contain credentials or request URLs.
            raise GatewayError("API_CLIENT") from None

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await asyncio.gather(*(entry.client.aio.aclose() for entry in self._credentials))
        finally:
            for entry in self._credentials:
                entry.client.close()

    async def __aenter__(self) -> "GeminiGateway":
        if self._closed:
            raise GatewayError("GATEWAY_CLOSED")
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

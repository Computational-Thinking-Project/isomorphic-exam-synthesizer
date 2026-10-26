"""Shared async transport: one call is one accounted Gemini request.

Content repair/retry belongs to the caller. This module only selects available
credentials and bounds concurrency, waiting and transport time.
"""

import asyncio
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import Settings


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
    def __init__(self, config: Settings):
        keys = config.get_gemini_api_keys()
        if not keys:
            raise GatewayError("API_KEY_MISSING")
        self.model = config.GEMINI_MODEL
        self._timeout = config.GEMINI_REQUEST_TIMEOUT_SECONDS
        self._cooldown = config.GEMINI_KEY_COOLDOWN_SECONDS
        self._semaphore = asyncio.Semaphore(config.GEMINI_MAX_CONCURRENCY)
        self._selection_lock = asyncio.Lock()
        self._closed = False
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
                        raise
                    except (httpx.TransportError, OSError):
                        raise GatewayError("API_TRANSPORT", retryable=True) from None
                    except GatewayError:
                        raise
                    except Exception:
                        # SDK exceptions may contain credentials or request URLs.
                        raise GatewayError("API_CLIENT") from None
        except TimeoutError:
            raise GatewayError(
                "JOB_DEADLINE" if time.monotonic() >= context.deadline else "API_TIMEOUT",
                retryable=time.monotonic() < context.deadline,
            ) from None

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

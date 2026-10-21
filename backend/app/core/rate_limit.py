"""Rate-limiting primitives for the FastAPI application.

The entry point calls ``register_rate_limiter`` once. Protected routes opt in
using the exported decorators after their authentication dependencies run.
"""

from collections.abc import Callable
from math import ceil
from typing import Any, TypeVar, cast

from fastapi import FastAPI, Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse, Response

CRUD_RATE_LIMIT = "60/minute"
GENERATION_RATE_LIMIT = "10/minute"
RATE_LIMIT_EXEMPT_PATHS = frozenset({"/health", "/api/health/metrics"})

AUTHENTICATED_USER_STATE_ATTRIBUTE = "authenticated_user_id"
RATE_LIMIT_KEY_PREFIX = "exam-synthesizer"

Endpoint = TypeVar("Endpoint", bound=Callable[..., Any])


def get_user_or_ip_key(request: Request) -> str:
    """Return a stable rate-limit key for a verified user or the client IP.

    Authentication code must only set ``request.state.authenticated_user_id``
    after the bearer token has been verified.  An absent, empty, or invalid
    state value intentionally falls back to the remote address instead of
    trusting unverified JWT claims.
    """

    user_id = getattr(request.state, AUTHENTICATED_USER_STATE_ATTRIBUTE, None)
    if isinstance(user_id, str) and user_id.strip():
        return f"user:{user_id.strip()}"

    remote_address = get_remote_address(request) or "unknown"
    return f"ip:{remote_address}"


def create_limiter() -> Limiter:
    """Create an isolated in-memory limiter suitable for the MVP or tests."""

    return Limiter(
        key_func=get_user_or_ip_key,
        headers_enabled=True,
        storage_uri="memory://",
        strategy="fixed-window",
        retry_after="delta-seconds",
        key_prefix=RATE_LIMIT_KEY_PREFIX,
    )


limiter = create_limiter()


def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> Response:
    """Return the project-compatible 429 body and SlowAPI limit headers."""

    response = JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
    )

    limiter_instance = getattr(request.app.state, "limiter", None)
    current_limit = getattr(request.state, "view_rate_limit", None)
    if limiter_instance is not None and current_limit is not None:
        # SlowAPI's own default handler uses this method to calculate the
        # X-RateLimit-* and Retry-After headers for the active window.
        response = cast(JSONResponse, limiter_instance._inject_headers(response, current_limit))
        # Round up fractional seconds so clients do not retry early. Missing or
        # malformed headers must not turn a quota response into a server error.
        raw_retry = response.headers.get("Retry-After", "1")
        try:
            retry_seconds = max(1, ceil(float(raw_retry)))
        except (ValueError, OverflowError):
            retry_seconds = 1
        response.headers["Retry-After"] = str(retry_seconds)
        return response

    # Defensive fallback for a partially configured app.  Normal registered
    # requests use the branch above, but a positive Retry-After value is still
    # preferable to omitting the required header.
    exceeded_limit = exc.limit
    expiry_seconds = exceeded_limit.limit.get_expiry() if exceeded_limit is not None else 1
    response.headers["Retry-After"] = str(max(1, int(expiry_seconds)))
    return response


def register_rate_limiter(
    app: FastAPI,
    limiter_instance: Limiter = limiter,
) -> None:
    """Attach a limiter and its 429 handler to a FastAPI application."""

    app.state.limiter = limiter_instance
    app.add_exception_handler(
        RateLimitExceeded,
        rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )


def crud_rate_limit(endpoint: Endpoint, *, limiter_instance: Limiter = limiter) -> Endpoint:
    """Apply the shared CRUD budget to an endpoint.

    Decorated FastAPI endpoints must accept both ``request: Request`` and
    ``response: Response`` so SlowAPI can identify the request and inject its
    response headers, or return a Response directly. A custom limiter instance
    must also be passed to register_rate_limiter for the same app.
    """

    decorated = limiter_instance.shared_limit(
        CRUD_RATE_LIMIT,
        scope="session-crud",
    )(endpoint)
    return cast(Endpoint, decorated)


def generation_rate_limit(endpoint: Endpoint, *, limiter_instance: Limiter = limiter) -> Endpoint:
    """Apply the generation budget to an endpoint.

    Decorated FastAPI endpoints must accept both ``request: Request`` and
    ``response: Response`` or return a Response directly. All session IDs share
    one budget per verified user (or remote IP for a public endpoint).
    """

    decorated = limiter_instance.shared_limit(
        GENERATION_RATE_LIMIT,
        scope="session-generation",
    )(endpoint)
    return cast(Endpoint, decorated)

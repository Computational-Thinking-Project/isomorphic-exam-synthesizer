"""Check the real app's security registration without adding production routes."""

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import (
    RATE_LIMIT_EXEMPT_PATHS,
    limiter,
    rate_limit_exceeded_handler,
)
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _configured_origins() -> list[str]:
    middleware = next(item for item in app.user_middleware if item.cls is CORSMiddleware)
    return cast(list[str], middleware.kwargs["allow_origins"])


def _allowed_origin() -> str:
    origins = _configured_origins()
    # This suite requires a local test origin, not real external credentials.
    assert origins, "Configure at least one CORS_ORIGINS entry for app integration tests"
    return str(origins[0])


def test_app_registers_one_cors_middleware_and_limiter() -> None:
    assert sum(item.cls is CORSMiddleware for item in app.user_middleware) == 1
    assert app.state.limiter is limiter
    assert app.exception_handlers[RateLimitExceeded] is rate_limit_exceeded_handler


@pytest.mark.parametrize("path", sorted(RATE_LIMIT_EXEMPT_PATHS))
def test_real_health_endpoints_remain_available(client: TestClient, path: str) -> None:
    origin = _allowed_origin()
    for _ in range(65):
        response = client.get(path, headers={"Origin": origin})
        assert response.status_code == 200
        assert "Retry-After" not in response.headers
        assert response.headers["access-control-allow-origin"] == origin


def test_real_app_preflight_uses_strict_cors_policy(client: TestClient) -> None:
    headers = {
        "Origin": _allowed_origin(),
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization,Content-Type",
    }
    response = client.options("/health", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-credentials"] == "true"
    headers["Access-Control-Request-Method"] = "PUT"
    assert client.options("/health", headers=headers).status_code == 400
    headers["Access-Control-Request-Method"] = "POST"
    headers["Access-Control-Request-Headers"] = "X-Unapproved-Header"
    assert client.options("/health", headers=headers).status_code == 400


def test_real_app_rejects_untrusted_origin_preflight(client: TestClient) -> None:
    # Choose an origin not present even if developer settings were customized.
    origin = "https://untrusted.example"
    while origin in _configured_origins():
        origin = origin.replace("https://", "https://other.")
    response = client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers

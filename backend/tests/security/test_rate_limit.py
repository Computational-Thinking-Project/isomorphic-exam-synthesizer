"""Exercise the exported policies using isolated apps and mock verified users."""

from collections.abc import Iterator
from functools import partial
from types import SimpleNamespace
from typing import Annotated, cast
from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from app.core import rate_limit as policy
from app.core.cors import register_cors

ORIGIN = "http://localhost:3000"


def _make_request(client_ip: str = "203.0.113.10") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "client": (client_ip, 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "state": {},
        }
    )


def _create_test_app() -> FastAPI:
    app = FastAPI()
    test_limiter = policy.create_limiter()
    policy.register_rate_limiter(app, test_limiter)
    register_cors(app, ORIGIN)
    limit_crud = partial(policy.crud_rate_limit, limiter_instance=test_limiter)
    limit_generation = partial(policy.generation_rate_limit, limiter_instance=test_limiter)

    async def attach_verified_user(
        request: Request,
        x_test_user: Annotated[str | None, Header()] = None,
    ) -> None:
        # Fixture-only verified-identity stand-in, never a production auth header.
        if x_test_user:
            request.state.authenticated_user_id = x_test_user

    @app.get("/test/crud", dependencies=[Depends(attach_verified_user)])
    @limit_crud
    async def list_sessions(request: Request, response: Response) -> dict[str, str]:
        return {"key": policy.get_user_or_ip_key(request)}

    @app.post("/test/crud", dependencies=[Depends(attach_verified_user)])
    @limit_crud
    async def create_session(request: Request, response: Response) -> dict[str, bool]:
        return {"ok": True}

    @app.patch("/test/crud/{session_id}", dependencies=[Depends(attach_verified_user)])
    @limit_crud
    async def update_session(
        session_id: str, request: Request, response: Response
    ) -> dict[str, str]:
        return {"id": session_id}

    @app.delete("/test/crud/{session_id}", dependencies=[Depends(attach_verified_user)])
    @limit_crud
    async def delete_session(session_id: str, request: Request) -> Response:
        return Response(status_code=204)

    @app.post("/test/sessions/{session_id}/generate", dependencies=[Depends(attach_verified_user)])
    @limit_generation
    async def generate(session_id: str, request: Request, response: Response) -> dict[str, str]:
        return {"id": session_id}

    @app.get("/health")
    @test_limiter.exempt
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/api/health/metrics")
    @test_limiter.exempt
    async def metrics() -> dict[str, str]:
        return {"status": "operational"}

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(_create_test_app()) as test_client:
        yield test_client


def test_generation_quota_is_shared_across_session_ids(client: TestClient) -> None:
    headers = {"X-Test-User": "teacher-a"}
    for index in range(10):
        assert client.post(f"/test/sessions/{index}/generate", headers=headers).status_code == 200
    assert client.post("/test/sessions/new-id/generate", headers=headers).status_code == 429


def test_crud_quota_is_shared_across_routes_methods_and_session_ids(client: TestClient) -> None:
    headers = {"X-Test-User": "teacher-a"}
    for index in range(15):
        assert client.get("/test/crud", headers=headers).status_code == 200
        assert client.post("/test/crud", headers=headers).status_code == 200
        assert client.patch(f"/test/crud/{index}", headers=headers).status_code == 200
        deleted = client.delete(f"/test/crud/{index}", headers=headers)
        assert deleted.status_code == 204
        assert deleted.content == b""
    response = client.get("/test/crud", headers=headers)
    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}


def test_generation_request_11_on_one_session_returns_429(client: TestClient) -> None:
    for _ in range(10):
        assert client.post("/test/sessions/one/generate").status_code == 200
    assert client.post("/test/sessions/one/generate").status_code == 429


def test_auth_dependency_runs_before_bucket_selection(client: TestClient) -> None:
    response = client.get("/test/crud", headers={"X-Test-User": "teacher-a"})
    assert response.status_code == 200
    assert response.json()["key"] == "user:teacher-a"


def test_two_users_on_same_ip_have_separate_quotas(client: TestClient) -> None:
    for _ in range(10):
        assert (
            client.post(
                "/test/sessions/one/generate", headers={"X-Test-User": "teacher-a"}
            ).status_code
            == 200
        )
    assert (
        client.post("/test/sessions/one/generate", headers={"X-Test-User": "teacher-a"}).status_code
        == 429
    )
    assert (
        client.post("/test/sessions/one/generate", headers={"X-Test-User": "teacher-b"}).status_code
        == 200
    )


def test_anonymous_ips_have_separate_quotas() -> None:
    app = _create_test_app()
    with (
        TestClient(app, client=("198.51.100.1", 1234)) as first,
        TestClient(app, client=("198.51.100.2", 1234)) as second,
    ):
        for _ in range(10):
            assert first.post("/test/sessions/one/generate").status_code == 200
        assert first.post("/test/sessions/one/generate").status_code == 429
        assert second.post("/test/sessions/one/generate").status_code == 200


def test_verified_user_keeps_quota_when_ip_changes() -> None:
    app = _create_test_app()
    headers = {"X-Test-User": "teacher-a"}
    with (
        TestClient(app, client=("198.51.100.1", 1234)) as first,
        TestClient(app, client=("198.51.100.2", 1234)) as second,
    ):
        for _ in range(10):
            assert first.post("/test/sessions/one/generate", headers=headers).status_code == 200
        assert second.post("/test/sessions/one/generate", headers=headers).status_code == 429


def test_crud_and_generation_have_independent_budgets(client: TestClient) -> None:
    headers = {"X-Test-User": "teacher-a"}
    for _ in range(10):
        assert client.post("/test/sessions/one/generate", headers=headers).status_code == 200
    assert client.post("/test/sessions/one/generate", headers=headers).status_code == 429
    for _ in range(60):
        assert client.get("/test/crud", headers=headers).status_code == 200
    assert client.get("/test/crud", headers=headers).status_code == 429


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123, object()])
def test_invalid_verified_state_falls_back_to_ip(invalid_id: object) -> None:
    request = _make_request()
    request.state.authenticated_user_id = invalid_id
    assert policy.get_user_or_ip_key(request) == "ip:203.0.113.10"


def test_unverified_headers_do_not_select_identity_or_ip() -> None:
    request = _make_request()
    request.scope["headers"] = [
        (b"authorization", b"Bearer unverified-token"),
        (b"x-test-user", b"forged-user"),
        (b"x-forwarded-for", b"198.51.100.99"),
        (b"x-real-ip", b"198.51.100.99"),
    ]
    assert policy.get_user_or_ip_key(request) == "ip:203.0.113.10"
    request.scope["headers"] = [(b"authorization", b"Bearer another-unverified-token")]
    assert policy.get_user_or_ip_key(request) == "ip:203.0.113.10"


def test_429_carries_positive_retry_after_and_cors(client: TestClient) -> None:
    headers = {"Origin": ORIGIN}
    for _ in range(10):
        assert client.post("/test/sessions/one/generate", headers=headers).status_code == 200
    response = client.post("/test/sessions/one/generate", headers=headers)
    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}
    assert 1 <= int(response.headers["Retry-After"]) <= 61
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "retry-after" in response.headers["access-control-expose-headers"].lower()


def test_untrusted_origin_has_no_allow_origin_on_429(client: TestClient) -> None:
    for _ in range(11):
        response = client.post(
            "/test/sessions/one/generate", headers={"Origin": "https://untrusted.example"}
        )
    assert response.status_code == 429
    assert "access-control-allow-origin" not in response.headers


def test_preflight_does_not_consume_generation_quota(client: TestClient) -> None:
    for _ in range(15):
        preflight = client.options(
            "/test/sessions/one/generate",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
        )
        assert preflight.status_code == 200
    for _ in range(10):
        assert client.post("/test/sessions/one/generate").status_code == 200
    assert client.post("/test/sessions/one/generate").status_code == 429


@pytest.mark.parametrize("path", sorted(policy.RATE_LIMIT_EXEMPT_PATHS))
def test_health_still_works_after_quota_is_exhausted(client: TestClient, path: str) -> None:
    for _ in range(11):
        response = client.post("/test/sessions/one/generate")
    assert response.status_code == 429
    for _ in range(65):
        assert client.get(path).status_code == 200


def test_request_allowed_after_window_resets(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Expire only this fixture's windows; no sleep or process-wide clock changes.
    for _ in range(10):
        assert client.post("/test/sessions/one/generate").status_code == 200
    assert client.post("/test/sessions/one/generate").status_code == 429
    test_app = cast(FastAPI, client.app)
    storage = test_app.state.limiter._storage
    for key in list(storage.expirations):
        monkeypatch.setitem(storage.expirations, key, 0.0)
    assert client.post("/test/sessions/one/generate").status_code == 200


def test_handler_fallback_without_limit_state() -> None:
    request = _make_request()
    request.scope["app"] = FastAPI()
    error = Mock(spec=RateLimitExceeded)
    error.limit = None
    response = policy.rate_limit_exceeded_handler(request, cast(RateLimitExceeded, error))
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"


@pytest.mark.parametrize(
    "raw_retry, expected",
    [
        pytest.param("60", "60", id="integer"),
        pytest.param("59.9", "60", id="decimal-rounds-up"),
        pytest.param("1.1", "2", id="small-decimal-rounds-up"),
        pytest.param("0", "1", id="window-boundary"),
        pytest.param("0.9", "1", id="fraction-below-one"),
        pytest.param("-5", "1", id="negative"),
        pytest.param(None, "1", id="missing-header"),
        pytest.param("", "1", id="empty"),
        pytest.param("not-a-number", "1", id="invalid-text"),
        pytest.param("NaN", "1", id="nan"),
        pytest.param("inf", "1", id="positive-infinity"),
        pytest.param("-inf", "1", id="negative-infinity"),
    ],
)
def test_handler_normalizes_retry_after(raw_retry: str | None, expected: str) -> None:
    # Inject defensive edge cases; decimals are not a confirmed SlowAPI output.
    request = _make_request()
    request.scope["app"] = FastAPI()
    request.state.view_rate_limit = object()

    def inject_headers(response: Response, current_limit: object) -> Response:
        if raw_retry is not None:
            response.headers["Retry-After"] = raw_retry
        response.headers["X-RateLimit-Remaining"] = "0"
        return response

    request.app.state.limiter = SimpleNamespace(_inject_headers=inject_headers)
    response = policy.rate_limit_exceeded_handler(request, cast(RateLimitExceeded, Mock()))
    assert response.status_code == 429
    assert response.body == b'{"detail":"Rate limit exceeded"}'
    assert response.headers["Retry-After"] == expected
    assert int(response.headers["Retry-After"]) >= 1
    assert response.headers["X-RateLimit-Remaining"] == "0"

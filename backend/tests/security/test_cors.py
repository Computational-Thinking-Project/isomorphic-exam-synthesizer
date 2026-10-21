"""Tests for strict credentialed CORS configuration."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.cors import parse_cors_origins, register_cors

LOCALHOST_ORIGIN = "http://localhost:3000"
LOOPBACK_ORIGIN = "http://127.0.0.1:3000"
CONFIGURED_ORIGINS = f"{LOCALHOST_ORIGIN},{LOOPBACK_ORIGIN}"


def _create_test_app() -> FastAPI:
    app = FastAPI()
    register_cors(app, CONFIGURED_ORIGINS)

    @app.get("/resource")
    async def get_resource() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/resource")
    async def create_resource() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_create_test_app())


@pytest.mark.parametrize("origin", [LOCALHOST_ORIGIN, LOOPBACK_ORIGIN])
def test_configured_origins_are_allowed(client: TestClient, origin: str) -> None:
    response = client.get("/resource", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unknown_origin_is_not_allowed(client: TestClient) -> None:
    response = client.get(
        "/resource",
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_unknown_origin_fails_preflight(client: TestClient) -> None:
    response = client.options(
        "/resource",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_unknown_custom_header_fails_preflight(client: TestClient) -> None:
    response = client.options(
        "/resource",
        headers={
            "Origin": LOCALHOST_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Unapproved-Header",
        },
    )
    assert response.status_code == 400


def test_cors_uses_settings_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://configured.example")
    app = FastAPI()
    assert register_cors(app) == ["https://configured.example"]
    with TestClient(app) as test_client:
        response = test_client.options(
            "/resource",
            headers={
                "Origin": "https://configured.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://configured.example"


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
def test_configured_methods_pass_preflight(client: TestClient, method: str) -> None:
    response = client.options(
        "/resource",
        headers={
            "Origin": LOCALHOST_ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCALHOST_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_put_method_is_rejected_by_preflight(client: TestClient) -> None:
    response = client.options(
        "/resource",
        headers={
            "Origin": LOCALHOST_ORIGIN,
            "Access-Control-Request-Method": "PUT",
        },
    )

    assert response.status_code == 400


@pytest.mark.parametrize("raw_origins", ["*", " */ ", f"{LOCALHOST_ORIGIN},*/"])
def test_wildcard_origin_is_rejected(raw_origins: str) -> None:
    app = FastAPI()

    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        register_cors(app, raw_origins)


def test_origin_parser_trims_and_deduplicates() -> None:
    parsed = parse_cors_origins(f" {LOCALHOST_ORIGIN},, {LOOPBACK_ORIGIN}, {LOCALHOST_ORIGIN} ")

    assert parsed == [LOCALHOST_ORIGIN, LOOPBACK_ORIGIN]


@pytest.mark.parametrize(
    "raw_origins, expected",
    [
        pytest.param(f" {LOCALHOST_ORIGIN}/ ", [LOCALHOST_ORIGIN], id="trim-and-strip-slash"),
        pytest.param(
            f"{LOCALHOST_ORIGIN}/,{LOCALHOST_ORIGIN},{LOOPBACK_ORIGIN}//",
            [LOCALHOST_ORIGIN, LOOPBACK_ORIGIN],
            id="deduplicate-after-normalization",
        ),
        pytest.param(f"/, ,{LOCALHOST_ORIGIN}/", [LOCALHOST_ORIGIN], id="discard-normalized-empty"),
    ],
)
def test_origin_parser_normalizes_trailing_slashes(raw_origins: str, expected: list[str]) -> None:
    assert parse_cors_origins(raw_origins) == expected


@pytest.mark.parametrize("origin", [LOCALHOST_ORIGIN, LOOPBACK_ORIGIN])
def test_trailing_slash_configuration_matches_browser_origin(
    monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "CORS_ORIGINS", f" {origin}/ ")
    app = FastAPI()
    register_cors(app)
    with TestClient(app) as test_client:
        response = test_client.options(
            "/resource",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"

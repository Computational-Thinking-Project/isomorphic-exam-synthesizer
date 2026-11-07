"""Protected runtime metrics HTTP contract with the existing Auth helper."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.routes.health import router
from app.core.config import settings
from app.models.schemas import CurrentUser
from app.services.observability.collector import RuntimeMetricsCollector
from app.services.observability.runtime_registry import RuntimeRegistry


def metrics_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    registry = RuntimeRegistry()
    registry.start()
    app.state.runtime_metrics = RuntimeMetricsCollector(
        registry, gemini_model="fixture-model", memory_reader=lambda: 12.5
    )
    return app


def user(email: str) -> CurrentUser:
    return CurrentUser(
        id="00000000-0000-0000-0000-000000000001", email=email, access_token="fixture"
    )


def test_metrics_requires_bearer_but_health_remains_public():
    with TestClient(metrics_app()) as client:
        health = client.get("/health")
        metrics = client.get("/api/health/metrics")
    assert health.status_code == 200
    assert metrics.status_code == 401
    assert metrics.headers["WWW-Authenticate"] == "Bearer"


def test_metrics_allows_authenticated_development_user(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    app = metrics_app()
    app.dependency_overrides[get_current_user] = lambda: user("normal@example.test")
    with TestClient(app) as client:
        response = client.get("/api/health/metrics")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["gemini_model"] == "fixture-model"
    assert response.json()["process_memory_mb"] == 12.5
    assert response.json()["gemini_call_count"] == 0


def test_metrics_restricts_nonadmin_outside_development(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "admin@example.test")
    app = metrics_app()
    app.dependency_overrides[get_current_user] = lambda: user("normal@example.test")
    with TestClient(app) as client:
        assert client.get("/api/health/metrics").status_code == 403
        app.dependency_overrides[get_current_user] = lambda: user("admin@example.test")
        assert client.get("/api/health/metrics").status_code == 200


def test_metrics_unavailable_fails_safely():
    app = metrics_app()
    app.dependency_overrides[get_current_user] = lambda: user("admin@example.test")
    app.state.runtime_metrics = None
    with TestClient(app) as client:
        response = client.get("/api/health/metrics")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ERR_RUNTIME_METRICS_UNAVAILABLE"

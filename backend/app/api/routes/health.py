"""Health and diagnostic endpoints."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.dependencies import get_current_admin_user
from app.models.runtime_metrics import RuntimeMetricsResponse
from app.models.schemas import CurrentUser
from app.services.observability.collector import RuntimeMetricsUnavailableError

router = APIRouter()


@router.get("/health", tags=["System"])
async def health_check():
    """Liveness probe endpoint for Docker healthcheck."""
    return {
        "status": "healthy",
        "service": "backend",
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


@router.get("/api/health/metrics", tags=["System"], response_model=RuntimeMetricsResponse)
async def metrics_check(
    request: Request,
    response: Response,
    _admin: CurrentUser = Depends(get_current_admin_user),
) -> RuntimeMetricsResponse:
    """Read an authenticated snapshot of this worker's live runtime counters."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return request.app.state.runtime_metrics.collect()
    except (AttributeError, RuntimeMetricsUnavailableError):
        raise HTTPException(
            503,
            {
                "code": "ERR_RUNTIME_METRICS_UNAVAILABLE",
                "message": "Runtime metrics are temporarily unavailable.",
            },
        ) from None

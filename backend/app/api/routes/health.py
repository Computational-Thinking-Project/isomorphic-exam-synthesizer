"""Health and diagnostic endpoints."""

import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["System"])
async def health_check():
    """Liveness probe endpoint for Docker healthcheck."""
    return {
        "status": "healthy",
        "service": "backend",
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


@router.get("/api/health/metrics", tags=["System"])
async def metrics_check():
    """Basic health metrics check for backend service."""
    return {
        "status": "operational",
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    }

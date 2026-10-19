import os

from fastapi import FastAPI

from app.core.cors import register_cors
from app.core.rate_limit import limiter, register_rate_limiter

app = FastAPI(
    title="Isomorphic Exam Synthesizer API",
    description="Backend engine for isomorphic math exam synthesis, validation, and export.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

register_rate_limiter(app)
register_cors(app)


@app.get("/health", tags=["System"])
@limiter.exempt
async def health_check():
    """Liveness probe endpoint for Docker healthcheck."""
    return {
        "status": "healthy",
        "service": "backend",
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


@app.get("/api/health/metrics", tags=["System"])
@limiter.exempt
async def metrics_check():
    """Basic health metrics check for backend service."""
    return {
        "status": "operational",
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    }

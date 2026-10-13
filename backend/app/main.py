import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Isomorphic Exam Synthesizer API",
    description="Backend engine for isomorphic math exam synthesis, validation, and export.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration (SEC-06)
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe endpoint for Docker healthcheck."""
    return {
        "status": "healthy",
        "service": "backend",
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


@app.get("/api/health/metrics", tags=["System"])
async def metrics_check():
    """Basic health metrics check for backend service."""
    return {
        "status": "operational",
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    }

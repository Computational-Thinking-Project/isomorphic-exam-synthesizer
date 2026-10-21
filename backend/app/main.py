from fastapi import FastAPI

from app.api.routes import health, sessions, users
from app.core.cors import register_cors
from app.core.rate_limit import register_rate_limiter

app = FastAPI(
    title="Isomorphic Exam Synthesizer API",
    description="Backend engine for isomorphic math exam synthesis, validation, and export.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

register_rate_limiter(app)
register_cors(app)

# Include Routers
app.include_router(health.router)
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])

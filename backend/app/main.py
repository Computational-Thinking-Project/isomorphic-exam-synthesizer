from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import (
    finalize,
    generation_config,
    health,
    review,
    sessions,
    source_artifacts,
    users,
)
from app.core.config import settings
from app.core.cors import register_cors
from app.core.rate_limit import register_rate_limiter
from app.models.schemas import ReviewDomainException
from app.services.ai.runtime import AIRuntime
from app.services.generation.config_repository import GenerationConfigRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ai_services = AIRuntime(settings)
    try:
        yield
    finally:
        await app.state.ai_services.aclose()


app = FastAPI(
    title="Isomorphic Exam Synthesizer API",
    description="Backend engine for isomorphic math exam synthesis, validation, and export.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

register_rate_limiter(app)
register_cors(app)


@app.exception_handler(ReviewDomainException)
async def review_domain_exception_handler(
    request: Request, exc: ReviewDomainException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "detail": exc.detail},
    )


# Include Routers
app.include_router(health.router)
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(
    generation_config.create_generation_config_router(GenerationConfigRepository),
    prefix="/api/sessions",
    tags=["Generation configuration"],
)
app.include_router(source_artifacts.router, prefix="/api/sessions", tags=["Sources"])
app.include_router(review.router, prefix="/api/sessions", tags=["Review"])
app.include_router(finalize.router, prefix="/api/sessions", tags=["Finalize"])

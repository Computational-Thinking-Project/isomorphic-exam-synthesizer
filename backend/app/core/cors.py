"""Strict CORS configuration shared by the FastAPI entry point and tests."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

ALLOWED_CORS_METHODS = ("GET", "POST", "PATCH", "DELETE")
ALLOWED_CORS_HEADERS = ("Authorization", "Content-Type")


def parse_cors_origins(raw_origins: str) -> list[str]:
    """Normalize trailing slashes, trim, and de-duplicate configured origins.

    A wildcard origin is rejected because this application allows credentialed
    browser requests and must enumerate trusted origins explicitly.
    """

    origins: list[str] = []
    for candidate in raw_origins.split(","):
        origin = candidate.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            raise ValueError("Wildcard CORS origin is not allowed with credentials")
        if origin not in origins:
            origins.append(origin)
    return origins


def register_cors(
    app: FastAPI,
    raw_origins: str | None = None,
) -> list[str]:
    """Register credentialed CORS middleware and return configured origins."""

    configured_origins = settings.CORS_ORIGINS if raw_origins is None else raw_origins
    origins = parse_cors_origins(configured_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=list(ALLOWED_CORS_METHODS),
        allow_headers=list(ALLOWED_CORS_HEADERS),
        expose_headers=["Retry-After"],
    )
    return origins

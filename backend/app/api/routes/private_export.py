"""Accepted Q10 routes. Runtime remains opt-in until the OPS handoff."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from supabase import Client

from app.api.dependencies import get_current_user, get_user_db
from app.models.schemas import CurrentUser, ReviewDomainException
from app.services.exporter.private_models import DownloadGrant, ExportFailure, ExportResult
from app.services.exporter.private_runtime import ExportOperation, run_private_export

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}


async def _handle(
    operation: ExportOperation, request: Request, session_id: str, user: CurrentUser, db: Client
) -> JSONResponse:
    # Reject client content/owner/revision without buffering an unbounded body.
    async for chunk in request.stream():
        if chunk:
            return JSONResponse(
                {"error_code": "ERR_EXPORT_REQUEST_BODY_NOT_ALLOWED"}, 400, headers=NO_STORE
            )
    try:
        result = await asyncio.to_thread(run_private_export, operation, session_id, user.id, db)
        content: dict[str, Any]
        status_code = 200
        if isinstance(result, DownloadGrant) and operation == "download":
            content = {
                "url": result.url,
                "expires_at": result.expires_at,
                "expires_in": result.expires_in,
                "filename": result.filename,
            }
        elif isinstance(result, ExportResult) and operation != "download":
            content = {"state": "preparing" if result.state == "pending" else result.state}
            if operation == "export":
                if result.state not in {"pending", "ready"}:
                    raise ExportFailure("ERR_EXPORT_METADATA_INVALID")
                status_code = 202 if result.state == "pending" else 200
            if result.state == "ready":
                if result.artifact is None:
                    raise ExportFailure("ERR_EXPORT_METADATA_INVALID")
                content.update(
                    filename=result.artifact.filename,
                    sha256=result.artifact.sha256,
                    size_bytes=result.artifact.size_bytes,
                )
            elif result.state == "failed":
                content["error_code"] = result.error_code
        else:
            raise ExportFailure("ERR_EXPORT_METADATA_INVALID")
        return JSONResponse(content, status_code, headers=NO_STORE)
    except ReviewDomainException as exc:
        return JSONResponse(
            {"error_code": exc.error_code, "detail": exc.detail}, exc.status_code, headers=NO_STORE
        )
    except ExportFailure as exc:
        return JSONResponse({"error_code": exc.code}, exc.http_status, headers=NO_STORE)
    except Exception:
        return JSONResponse({"error_code": "ERR_EXPORT_UNAVAILABLE"}, 503, headers=NO_STORE)


@router.post("/{session_id}/export")
async def export_endpoint(
    session_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> JSONResponse:
    return await _handle("export", request, session_id, user, db)


@router.get("/{session_id}/export")
async def export_status_endpoint(
    session_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> JSONResponse:
    return await _handle("status", request, session_id, user, db)


@router.post("/{session_id}/export/download-url")
async def export_download_endpoint(
    session_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_user_db),
) -> JSONResponse:
    return await _handle("download", request, session_id, user, db)

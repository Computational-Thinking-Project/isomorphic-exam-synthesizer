"""Privileged clients live/close inside the worker, including after cancellation.

No application automatic retry or background task. Timeouts bound individual IO,
not the total export runtime or the RPC900s lease.
"""

from typing import Literal

import httpx
from supabase import Client, ClientOptions, create_client

from app.core.config import settings

from .private_models import DownloadGrant, ExportFailure, ExportResult
from .private_repository import SupabaseExportLedger
from .private_service import PrivateExportService, user_snapshot_loader
from .private_storage import SupabasePrivateExportStore

ExportOperation = Literal["export", "status", "download", "files"]


def run_private_export(
    operation: ExportOperation, session_id: str, owner_id: str, user_db: Client
) -> ExportResult | DownloadGrant | dict[str, bytes]:
    """Called via to_thread; a disconnected caller does not roll back the worker."""
    rpc_timeout = settings.PRIVATE_EXPORT_RPC_TIMEOUT_SECONDS
    storage_timeout = settings.PRIVATE_EXPORT_STORAGE_TIMEOUT_SECONDS
    key = settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()
    if (
        not settings.PRIVATE_EXPORT_ENABLED
        or rpc_timeout is None
        or storage_timeout is None
        or settings.PRIVATE_EXPORT_BUCKET != "exam-export-bundles"
        or not settings.SUPABASE_URL
        or not key
    ):
        # Another bucket would require changing RPC020's policy, not just env.
        raise ExportFailure("ERR_EXPORT_UNAVAILABLE")
    with (
        httpx.Client(timeout=rpc_timeout) as rpc_http,
        httpx.Client(timeout=storage_timeout) as storage_http,
    ):
        writer = create_client(
            settings.SUPABASE_URL,
            key,
            options=ClientOptions(
                httpx_client=rpc_http, auto_refresh_token=False, persist_session=False
            ),
        )
        storage = create_client(
            settings.SUPABASE_URL,
            key,
            options=ClientOptions(
                httpx_client=storage_http, auto_refresh_token=False, persist_session=False
            ),
        )
        service = PrivateExportService(
            user_snapshot_loader(user_db, provenance_db=writer),
            SupabaseExportLedger(writer),
            SupabasePrivateExportStore(storage, settings.PRIVATE_EXPORT_BUCKET),
        )
        return getattr(service, operation)(session_id, owner_id)

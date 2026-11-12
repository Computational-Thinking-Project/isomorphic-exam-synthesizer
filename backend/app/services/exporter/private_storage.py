"""Supabase SDK adapter. Instantiation does not create/alter buckets or ACLs.

Only wire this with the OPS-confirmed private bucket and authorized server client.
The service authorizes the owner before reaching this privileged boundary.
"""

import hashlib
from typing import Any
from urllib.parse import urlsplit

from .bundle_models import BundleArtifact
from .private_models import SIGNED_URL_TTL, ExportFailure, ReadyExport


class SupabasePrivateExportStore:
    def __init__(self, client: Any, bucket: str):
        if not bucket:
            raise ValueError("A confirmed private bucket is required")
        self.bucket = client.storage.from_(bucket)

    def upload(self, path: str, artifact: BundleArtifact) -> None:
        self.bucket.upload(
            path,
            artifact.data,
            file_options={
                "content-type": "application/zip",
                "upsert": "false",
                "cache-control": "0",
            },
        )

    def verify(self, artifact: ReadyExport) -> None:
        data = self.bucket.download(artifact.object_path)
        if (
            not isinstance(data, bytes)
            or len(data) != artifact.size_bytes
            or hashlib.sha256(data).hexdigest() != artifact.sha256
        ):
            raise ExportFailure("ERR_EXPORT_CHECKSUM_MISMATCH")

    def sign(self, artifact: ReadyExport) -> str:
        response = self.bucket.create_signed_url(
            artifact.object_path,
            SIGNED_URL_TTL,
            {"download": artifact.filename},
        )
        url = response.get("signedURL")
        if not isinstance(url, str) or urlsplit(url).scheme != "https" or not urlsplit(url).netloc:
            raise ExportFailure("ERR_EXPORT_SIGNING_FAILED")
        return url

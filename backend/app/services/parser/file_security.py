"""File security and validation utilities for exam ingestion (SEC-04).

Enforces:
- Path Traversal prevention on uploaded filenames
- Allowed extension verification (.docx, .tex, .md)
- File size check (default <= 10MB)
- Magic bytes and zip structure validation for DOCX
- Anti-Zip Bomb decompression limit check (<= 50MB uncompressed)
- Secure Supabase Storage upload with prefix {session_id}/{uuid}_{clean_name}
"""

import io
import logging
import re
import uuid
import zipfile
from typing import Optional

from fastapi import HTTPException, status
from supabase import Client

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: set[str] = {".docx", ".tex", ".md"}
DOCX_MAGIC_BYTES: bytes = b"PK\x03\x04"
MAX_DOCX_UNCOMPRESSED_SIZE: int = 50 * 1024 * 1024  # 50MB limit against zip bombs
DEFAULT_STORAGE_BUCKET: str = "exam-sources"


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filename to prevent Path Traversal attacks.

    Replaces any character outside [a-zA-Z0-9._-] with an underscore,
    and collapses any consecutive dots (..) to avoid path traversal.
    """
    clean_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename or "uploaded_exam")
    # Collapse consecutive dots to prevent .. traversal
    clean_name = re.sub(r"\.{2,}", "_", clean_name)
    # Ensure it's not empty
    if not clean_name.strip("._-"):
        clean_name = f"exam_{uuid.uuid4().hex[:8]}"
    return clean_name


def get_file_extension(filename: str) -> str:
    """Extract and validate file extension in lower case."""
    dot_index = filename.rfind(".")
    if dot_index == -1:
        return ""
    return filename[dot_index:].lower()


def validate_file_security(filename: str, file_bytes: bytes) -> str:
    """Validate raw uploaded file against size, format, and zip structure.

    Returns the validated extension (e.g., '.docx', '.tex', '.md').
    Raises HTTPException(400) if any security check fails.
    """
    # 1. File extension check
    ext = get_file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Only .docx, .tex, and .md files are accepted.",
        )

    # 2. File size check (raw upload size)
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_MB}MB.",
        )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 3. For .docx: inspect magic bytes and inner zip archive
    if ext == ".docx":
        if not file_bytes.startswith(DOCX_MAGIC_BYTES):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid DOCX file: missing valid PK zip header.",
            )

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                # Anti-Zip Bomb check
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > MAX_DOCX_UNCOMPRESSED_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="File decompression size exceeds 50MB limit (potential Zip Bomb).",
                    )

                # Required Word document entries check
                namelist = set(zf.namelist())
                if "[Content_Types].xml" not in namelist or "word/document.xml" not in namelist:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid DOCX package structure: missing required XML entries.",
                    )
        except zipfile.BadZipFile as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Corrupted or malformed DOCX archive.",
            ) from exc

    # 4. For text-based formats (.md, .tex): validate strict UTF-8 decoding
    if ext in (".md", ".tex"):
        try:
            file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {ext} file: content is not valid UTF-8 text.",
            ) from exc

    return ext


async def upload_exam_file_to_storage(
    db: Client,
    session_id: str,
    filename: str,
    file_bytes: bytes,
    content_type: Optional[str] = None,
    bucket_name: str = DEFAULT_STORAGE_BUCKET,
) -> Optional[str]:
    """Upload validated exam file to Supabase Storage with prefix {session_id}/{uuid}_{clean_name}.

    Returns the storage object path on success, or None if storage upload fails or is unavailable.
    Does not crash the request if Supabase Storage is not configured in dev/mock environment.
    """
    clean_name = sanitize_filename(filename)
    unique_key = f"{uuid.uuid4().hex[:8]}_{clean_name}"
    storage_path = f"{session_id}/{unique_key}"

    # Determine default MIME type
    if not content_type:
        ext = get_file_extension(filename)
        if ext == ".docx":
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif ext == ".tex":
            content_type = "application/x-tex"
        elif ext == ".md":
            content_type = "text/markdown"
        else:
            content_type = "application/octet-stream"

    try:
        # Attempt upload to primary bucket (exam-sources), fallback only if bucket not found
        try:
            db.storage.from_(bucket_name).upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        except Exception as primary_exc:
            err_msg = str(primary_exc).lower()
            if "not found" in err_msg or "nosuchbucket" in err_msg or "404" in err_msg:
                # Try fallback bucket only when primary bucket is missing
                db.storage.from_("exam-raw-files").upload(
                    path=storage_path,
                    file=file_bytes,
                    file_options={"content-type": content_type, "upsert": "true"},
                )
            else:
                raise primary_exc
        logger.info("Successfully uploaded exam file to storage: %s", storage_path)
        return storage_path
    except Exception as exc:
        logger.warning(
            "Could not upload file to Supabase storage (%s): %s. Continuing with ingestion.",
            storage_path,
            exc,
        )
        return None

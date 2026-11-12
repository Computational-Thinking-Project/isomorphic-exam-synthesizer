"""Add a deterministic manifest without changing the W3 bundler's public contract."""

import hashlib
import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .bundle_builder import MAX_BUNDLE_BYTES
from .bundle_models import ApprovedExportSnapshot, BundleArtifact, BundleBuildError
from .export_pipeline import build_compiled_bundle
from .private_models import PACKAGER_VERSION


def with_manifest(snapshot: ApprovedExportSnapshot, artifact: BundleArtifact) -> BundleArtifact:
    root = f"exam_bundle_{snapshot.session_id}/"
    if (
        len(artifact.data) > MAX_BUNDLE_BYTES
        or hashlib.sha256(artifact.data).hexdigest() != artifact.sha256
    ):
        raise BundleBuildError("EXPORT_BUNDLE_INVALID")
    entries: dict[str, bytes] = {}
    with ZipFile(BytesIO(artifact.data)) as archive:
        size = 0
        for entry in archive.infolist():
            name = entry.filename
            size += entry.file_size
            if (
                not name.startswith(root)
                or name in entries
                or name.endswith("/")
                or "\\" in name
                or any(p in ("", ".", "..") for p in name.split("/"))
                or name == root + "manifest.json"
                or size > MAX_BUNDLE_BYTES
            ):
                raise BundleBuildError("EXPORT_BUNDLE_INVALID")
            entries[name] = archive.read(entry)
    manifest = {
        "format": PACKAGER_VERSION,
        "session_id": str(snapshot.session_id),
        "revision": snapshot.revision,
        "files": [
            {
                "path": name.removeprefix(root),
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for name, data in sorted(entries.items())
        ],
    }
    # Manifest excludes itself; the complete ZIP digest is stored in the ledger.
    entries[root + "manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if sum(map(len, entries.values())) > MAX_BUNDLE_BYTES:
        raise BundleBuildError("EXPORT_BUNDLE_TOO_LARGE")
    result = BytesIO()
    with ZipFile(result, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    payload = result.getvalue()
    if len(payload) > MAX_BUNDLE_BYTES:
        raise BundleBuildError("EXPORT_BUNDLE_TOO_LARGE")
    return BundleArtifact(artifact.filename, payload, hashlib.sha256(payload).hexdigest())


def build_private_bundle(snapshot: ApprovedExportSnapshot) -> BundleArtifact:
    return with_manifest(snapshot, build_compiled_bundle(snapshot))

"""Source of ``ApprovedExportSnapshot.revision`` (W4-MVP-07).

Decision on PR #58: SHA-256 of the normalized exported content, including title.
Lifecycle timestamps and status are deliberately excluded: approval/export do not
change the identity of an otherwise identical artifact.
"""

import hashlib
import json
from typing import Any, Mapping, Sequence


def snapshot_revision(
    session_meta: Mapping[str, Any], versions: Sequence[Mapping[str, Any]]
) -> str:
    """Return a deterministic revision for the validated, normalized content.

    ``versions`` is the JSON-mode dump of the validated display versions, so the
    revision depends only on persisted approved content: the same locked session
    yields the same value before and after an ``approved -> exported`` change.
    """
    payload = {
        "session_id": str(session_meta["id"]),
        "title": session_meta["title"],
        "versions": list(versions),
    }
    wire = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(wire.encode("utf-8")).hexdigest()

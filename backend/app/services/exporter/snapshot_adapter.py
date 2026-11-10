"""Entry point for task 08: persisted, locked session -> ``ApprovedExportSnapshot``."""

from supabase import Client

from app.services.exporter.bundle_models import ApprovedExportSnapshot
from app.services.exporter.snapshot_builder import RevisionSource, build_approved_snapshot
from app.services.exporter.snapshot_reader import ExportSnapshotReader
from app.services.exporter.snapshot_revision import snapshot_revision


async def load_approved_export_snapshot(
    db: Client,
    session_id: str,
    user_id: str,
    *,
    revision_of: RevisionSource = snapshot_revision,
) -> ApprovedExportSnapshot:
    """Read and validate the export snapshot; ``user_id`` must come from verified auth.

    Raises ``ReviewDomainException`` (400/403/404/409). Never accepts keys, questions
    or permutations from a client: everything comes from persisted rows.
    """
    rows = ExportSnapshotReader(db).load_rows(session_id, user_id)
    return build_approved_snapshot(rows, revision_of=revision_of)

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
    """Read the snapshot with the verified user's RLS client (``get_user_db``).

    Raises ``ReviewDomainException`` (400/403/404/409). Never accepts keys, questions
    or permutations from a client: everything comes from persisted rows.
    Network/SDK errors propagate for the route to handle as availability errors;
    they must not be mapped to 409 or returned as raw SDK/transport messages.

    The reader uses the synchronous supabase client (like the repositories under
    ``finalize/``), so this coroutine blocks the event loop while reading; a caller may
    wrap it with ``run_in_threadpool`` if that matters.

    Not re-derived here (enforced at shuffle/approval, migration 009): option/key
    permutation against canonical data, solution label sync, source/canonical numbering.
    """
    rows = ExportSnapshotReader(db).load_rows(session_id, user_id)
    return build_approved_snapshot(rows, revision_of=revision_of)

"""Entry point for task 08: persisted, locked session -> ``ApprovedExportSnapshot``."""

from dataclasses import dataclass

from supabase import Client

from app.services.exporter.bank_snapshot import (
    BankExportSnapshot,
    RoundKind,
    build_bank_snapshot,
    classify_round,
)
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
    provenance_db: Client | None = None,
) -> ApprovedExportSnapshot:
    """Read the snapshot with the verified user's RLS client (``get_user_db``).

    Raises ``ReviewDomainException`` (400/403/404/409). Never accepts keys, questions
    or permutations from a client: everything comes from persisted rows.
    Optional ``provenance_db`` is restricted to server-side generation evidence
    for empty fallback/clone solutions; it never reads user content or ownership.
    Network/SDK errors propagate for the route to handle as availability errors;
    they must not be mapped to 409 or returned as raw SDK/transport messages.

    The reader uses the synchronous supabase client (like the repositories under
    ``finalize/``), so this coroutine blocks the event loop while reading; a caller may
    wrap it with ``run_in_threadpool`` if that matters.

    Not re-derived here (enforced at shuffle/approval, migration 009): option/key
    permutation against canonical data, solution label sync, source/canonical numbering.
    """
    rows = ExportSnapshotReader(db, provenance_db=provenance_db).load_rows(session_id, user_id)
    return build_approved_snapshot(rows, revision_of=revision_of)


@dataclass(frozen=True)
class ExportSource:
    """EXT-03 G3: what one approved round exports, and from which source."""

    kind: RoundKind
    snapshot: ApprovedExportSnapshot
    bank: BankExportSnapshot | None = None


def load_export_source(
    db: Client,
    session_id: str,
    user_id: str,
    *,
    provenance_db: Client | None = None,
) -> ExportSource:
    """Dispatch on the Bank link (I-EXT-02): MVP projection or EXT Approve snapshot.

    Unlinked and legacy rounds reuse the MVP reader unchanged, so their revision and
    artifacts stay identical. EXT rounds read only ``approved_exam_snapshots``.
    Empty EXT solutions fail closed until the R09 verifier (G2) supplies evidence.
    Requires the EXT-04 tables; the export route switches to this after Q05.
    """
    reader = ExportSnapshotReader(db, provenance_db=provenance_db)
    bank_rows = reader.load_bank_round(session_id, user_id)
    kind = classify_round(str(bank_rows.session["id"]), user_id, bank_rows.links)
    if kind is RoundKind.EXT:
        bank = build_bank_snapshot(bank_rows.session, bank_rows.snapshots)
        return ExportSource(kind=kind, snapshot=bank.snapshot, bank=bank)
    snapshot = build_approved_snapshot(reader.load_rows(session_id, user_id))
    return ExportSource(kind=kind, snapshot=snapshot)

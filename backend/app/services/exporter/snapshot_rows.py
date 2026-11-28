"""Boundary type between the DB reader and the pure snapshot builder (W4-MVP-07).

The reader (table reads today, possibly a read RPC later) must return exactly this
shape. The builder never touches the database, so changing how rows are read does
not change validation.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RawSnapshotRows:
    """Raw persisted rows for one locked session; values are NOT yet validated.

    session: id, user_id, title, status, approved_at, updated_at.
    n_versions: ``generation_configs.n_versions`` as stored.
    source_question_ids: ids of ``source_questions`` rows of the session.
    versions: ``exam_versions`` rows (id, version_code, is_finalized, shuffle_seed,
        permutations).
    questions: ``version_questions`` rows, current candidates only (id, version_id,
        source_question_id, question_no, canonical_question_no, content, options,
        correct_key, solution_md, status, is_current).
    answer_keys: ``answer_keys`` rows (version_id, question_no, display_no,
        correct_option, display_correct_key, canonical_question_no).
    generation_config/provenance_results/provenance_snapshots: internal Q01
        evidence, optional for nonempty solutions. Empty tuples fail closed for
        empty solutions. These are never accepted from public HTTP request JSON.
    """

    session: Mapping[str, Any]
    n_versions: Any
    source_question_ids: tuple[Any, ...]
    versions: tuple[Mapping[str, Any], ...]
    questions: tuple[Mapping[str, Any], ...]
    answer_keys: tuple[Mapping[str, Any], ...]
    generation_config: Mapping[str, Any] = field(default_factory=dict)
    provenance_results: tuple[Mapping[str, Any], ...] = ()
    provenance_snapshots: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class BankRoundRows:
    """Raw EXT-04 rows for one owned, locked session (EXT-03 G3); NOT yet validated.

    session: same columns as ``RawSnapshotRows.session``.
    links: ``exam_bank_rounds`` rows (session_id, bank_item_id, owner_id, is_legacy).
    snapshots: ``approved_exam_snapshots`` rows (session_id, snapshot_revision,
        snapshot_payload); read only for a non-legacy link.
    """

    session: Mapping[str, Any]
    links: tuple[Mapping[str, Any], ...]
    snapshots: tuple[Mapping[str, Any], ...] = ()

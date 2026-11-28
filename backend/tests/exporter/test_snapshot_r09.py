"""EXT-03 G1 — R09 provenance compatibility for empty or placeholder solutions.

Cases follow the I-EXT-01 policy fixture (#111 ``8fb21e6``) and the I-EXT-03 v2
fixture (#112 ``452937a``, v3 ``b230f7b``): a mapping 1.1/1.2 job freezes one policy per source
question, so a clone slot may lack a solution while the session also has AI slots.

Tests marked ``xfail(strict=True)`` reproduce the gaps that EXT-03 G2 fixes
(docs/tasks/EXT-03.md §3): today the verifier checks the clone rule session-wide
and treats the Q06 placeholder as a real solution. When G2 lands, each strict xfail
starts passing and must be turned into a plain test.

Revert cases follow Q-I01-R (#111, Duy, 28/11) and migration 024: a ``w4_frozen``
Revert candidate has ``is_reverted = true``, ``validation_report.reason = "REVERT"``
and no ledger row of its own; its source revision, source fingerprint and confirmed
source hash must match the frozen job snapshot for the same session and source, and
the placeholder is valid only when the frozen source solution is really missing.
"""

from dataclasses import replace

import pytest
from snapshot_fixtures import SESSION_ID, golden_rows, to_rows

from app.models.schemas import ReviewDomainException
from app.services.exporter.snapshot_builder import build_approved_snapshot

SNAPSHOT_ID = "77777777-7777-4777-8777-777777777777"
PLACEHOLDER = "Không có lời giải cho câu hỏi này."
G2 = "EXT-03 G2: per-slot frozen policy and Q06 placeholder are not verified yet"


def _ledger(row, kind):
    return {
        "version_question_id": row["id"],
        "snapshot_id": SNAPSHOT_ID,
        "session_id": SESSION_ID,
        "source_question_id": row["source_question_id"],
        "is_success": True,
        "result_kind": kind,
        "clone_fingerprint": "c" * 64,
    }


def _rows(*, solution, mapping_version, clone_slot_kind="ORIGINAL_CLONE", ledger_kind=None):
    """Version 101 slot 1 is the only question without a usable solution.

    ``clone_slot_kind`` is the frozen policy of that slot's source question; the other
    two sources are frozen as ``AI_RESULT``. Mapping 1.0 has no per-slot policy and
    uses the session-wide rule, so its job and config carry empty modes.
    """
    data = golden_rows()
    row = data["questions"][0]
    row.update(
        solution_md=solution,
        canonical_solution_md=solution,
        regenerated_from_id=None,
        has_warning=False,
        validation_report=None,
    )
    sources = data["source_question_ids"]
    if mapping_version == "1.0":
        config = {"active_variation_modes": [], "canonical_dimensions": []}
        snapshot = {"public_modes": [], "canonical_dimensions": [], "snapshot_payload": {}}
    else:
        policies = {
            sid: (
                {"canonical_dimensions": [], "result_kind": clone_slot_kind}
                if sid == row["source_question_id"]
                else {"canonical_dimensions": ["values"], "result_kind": "AI_RESULT"}
            )
            for sid in sources
        }
        config = {
            "active_variation_modes": ["parameter_variation"],
            "canonical_dimensions": ["values"],
        }
        payload = {"question_policies": policies}
        snapshot = {
            "public_modes": ["parameter_variation"],
            "canonical_dimensions": ["values"],
            "snapshot_payload": payload,
        }
        if mapping_version == "1.2":
            payload["generation_mode"] = "ai_generation"
            snapshot["generation_mode"] = "ai_generation"
    return replace(
        to_rows(data),
        generation_config=config,
        provenance_results=(_ledger(row, ledger_kind or clone_slot_kind),),
        provenance_snapshots=(
            {
                "id": SNAPSHOT_ID,
                "session_id": SESSION_ID,
                "mapping_version": mapping_version,
                **snapshot,
            },
        ),
    )


def _first(snapshot):
    return snapshot.versions[0].questions[0]


def _rejected(rows):
    with pytest.raises(ReviewDomainException) as caught:
        build_approved_snapshot(rows)
    assert (caught.value.status_code, caught.value.error_code) == (
        409,
        "ERR_EXPORT_SNAPSHOT_INVALID",
    )


# --- behaviour that must be kept --------------------------------------------------


def test_legacy_1_0_clone_with_null_solution_is_still_accepted():
    assert (
        _first(build_approved_snapshot(_rows(solution=None, mapping_version="1.0"))).solution_md
        == ""
    )


def test_legacy_1_0_ai_ledger_without_solution_is_still_rejected():
    _rejected(_rows(solution=None, mapping_version="1.0", ledger_kind="AI_RESULT"))


@pytest.mark.parametrize("mapping_version", ["1.1", "1.2"])
def test_ai_slot_without_solution_is_rejected_in_mixed_jobs(mapping_version):
    _rejected(_rows(solution=None, mapping_version=mapping_version, clone_slot_kind="AI_RESULT"))


# --- gaps reproduced for G2 -------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=G2)
@pytest.mark.parametrize("mapping_version", ["1.1", "1.2"])
def test_mixed_policy_clone_with_null_solution_is_accepted(mapping_version):
    rows = _rows(solution=None, mapping_version=mapping_version)
    assert _first(build_approved_snapshot(rows)).solution_md == ""


@pytest.mark.xfail(strict=True, reason=G2)
@pytest.mark.parametrize("mapping_version", ["1.1", "1.2"])
def test_clone_ledger_on_a_frozen_ai_slot_is_rejected(mapping_version):
    rows = _rows(
        solution=None,
        mapping_version=mapping_version,
        clone_slot_kind="AI_RESULT",
        ledger_kind="ORIGINAL_CLONE",
    )
    # Without the per-slot check this case slips through once the session-wide rule
    # is relaxed; keep the config/job modes empty to show the slot policy decides.
    rows = replace(
        rows,
        generation_config={"active_variation_modes": [], "canonical_dimensions": []},
        provenance_snapshots=(
            {**rows.provenance_snapshots[0], "public_modes": [], "canonical_dimensions": []},
        ),
    )
    _rejected(rows)


@pytest.mark.xfail(strict=True, reason=G2)
def test_unknown_mapping_version_fails_closed():
    rows = _rows(solution=None, mapping_version="1.0")
    rows = replace(
        rows, provenance_snapshots=({**rows.provenance_snapshots[0], "mapping_version": "9.9"},)
    )
    _rejected(rows)


@pytest.mark.xfail(strict=True, reason=G2)
def test_placeholder_on_verified_clone_is_treated_as_missing_solution():
    rows = _rows(solution=PLACEHOLDER, mapping_version="1.0")
    assert _first(build_approved_snapshot(rows)).solution_md == ""


@pytest.mark.xfail(strict=True, reason=G2)
def test_placeholder_on_ai_slot_is_rejected():
    _rejected(_rows(solution=PLACEHOLDER, mapping_version="1.0", ledger_kind="AI_RESULT"))


# --- Revert evidence (Q-I01-R) ----------------------------------------------------

REVISION_ID = "88888888-8888-4888-8888-888888888888"
SOURCE_FP = "a" * 64
SOURCE_HASH = "b" * 64


def _revert_rows(*, source_solution=None, report_overrides=None, frozen_source_id=None):
    """Version 101 slot 1 is a Revert candidate from a mapping 1.1 frozen job."""
    rows = _rows(solution=None, mapping_version="1.1")
    question = dict(rows.questions[0])
    sid = question["source_question_id"]
    report = {
        "reason": "REVERT",
        "validation_status": "not_validated",
        "source_revision_id": REVISION_ID,
        "source_fingerprint": SOURCE_FP,
        "confirmed_source_hash": SOURCE_HASH,
        **(report_overrides or {}),
    }
    question.update(
        solution_md=PLACEHOLDER,
        canonical_solution_md=PLACEHOLDER,
        is_reverted=True,
        has_warning=True,
        validation_report=report,
    )
    job = dict(rows.provenance_snapshots[0])
    job["confirmed_source_hash"] = SOURCE_HASH
    job["snapshot_payload"] = {
        **job["snapshot_payload"],
        "confirmed_sources": [
            {
                "source_question_id": frozen_source_id or sid,
                "source_revision_id": REVISION_ID,
                "source_fingerprint": SOURCE_FP,
                "confirmed_input": {
                    "question_text": question["content"],
                    "options": question["options"],
                    "correct_answer": question["correct_key"],
                    "solution": source_solution,
                },
            }
        ],
    }
    return replace(
        rows,
        questions=(question, *rows.questions[1:]),
        provenance_results=(),
        provenance_snapshots=(job,),
    )


@pytest.mark.xfail(strict=True, reason=G2)
@pytest.mark.parametrize("source_solution", [None, "", "   "])
def test_revert_placeholder_with_missing_frozen_solution_is_accepted(source_solution):
    rows = _revert_rows(source_solution=source_solution)
    assert _first(build_approved_snapshot(rows)).solution_md == ""


@pytest.mark.xfail(strict=True, reason=G2)
def test_revert_placeholder_when_frozen_source_has_a_solution_is_rejected():
    _rejected(_revert_rows(source_solution="Lời giải nguồn đã xác nhận."))


@pytest.mark.xfail(strict=True, reason=G2)
@pytest.mark.parametrize(
    "overrides",
    [
        {"reason": "ACCEPT"},
        {"source_revision_id": "99999999-9999-4999-8999-999999999999"},
        {"source_fingerprint": "d" * 64},
        {"confirmed_source_hash": "e" * 64},
    ],
    ids=["reason", "revision", "fingerprint", "source-hash"],
)
def test_revert_placeholder_with_mismatched_evidence_is_rejected(overrides):
    _rejected(_revert_rows(report_overrides=overrides))


@pytest.mark.xfail(strict=True, reason=G2)
def test_revert_placeholder_bound_to_another_source_is_rejected():
    _rejected(_revert_rows(frozen_source_id="00000000-0000-4000-8000-000000000000"))

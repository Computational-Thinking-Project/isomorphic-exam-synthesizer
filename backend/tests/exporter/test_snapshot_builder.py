"""Fail-closed tests for the pure approved export snapshot builder (W4-MVP-07)."""

import json
from pathlib import Path

import pytest
from snapshot_fixtures import (
    SESSION_ID,
    VERSION_IDS,
    golden_rows,
    key_row,
    mutated,
    question,
    to_rows,
)

from app.models.schemas import ReviewDomainException
from app.services.exporter.bundle_models import ApprovedExportSnapshot
from app.services.exporter.snapshot_builder import build_approved_snapshot, snapshot_identity

INVALID = ("ERR_EXPORT_SNAPSHOT_INVALID", 409)
KEYS = ("ERR_INCONSISTENT_ANSWER_KEYS", 409)
STATE = ("ERR_INVALID_SESSION_STATE", 409)


def _fail(rows):
    with pytest.raises(ReviewDomainException) as caught:
        build_approved_snapshot(rows)
    return caught.value


def test_golden_snapshot_matches_persisted_display_order_and_keys():
    snapshot = build_approved_snapshot(to_rows(golden_rows()))
    assert isinstance(snapshot, ApprovedExportSnapshot)
    assert [v.code for v in snapshot.versions] == ["101", "102"]
    assert str(snapshot.session_id) == SESSION_ID
    assert snapshot.status == "approved"
    keys = {v.code: [q.correct_key for q in v.questions] for v in snapshot.versions}
    assert keys == {"101": ["A", "B", "C"], "102": ["B", "D", "A"]}
    assert [q.question_no for q in snapshot.versions[1].questions] == [1, 2, 3]
    # Version 102 slot 1 is canonical source question 3 with permuted options.
    first = snapshot.versions[1].questions[0]
    assert "Câu nguồn 3" in first.content
    assert first.options == ("12", "9", "11", "10")


def test_revision_is_stable_and_not_changed_by_exported_status():
    approved = build_approved_snapshot(to_rows(golden_rows()))
    again = build_approved_snapshot(to_rows(golden_rows()))
    exported = build_approved_snapshot(
        mutated(lambda d: d["session"].update(status="exported", updated_at="2026-11-11T01:00:00Z"))
    )
    assert approved.revision == again.revision == exported.revision
    assert approved.revision.startswith("sha256:")
    assert exported.status == "exported"


def test_revision_changes_when_approved_content_changes():
    changed = mutated(lambda d: question(d, "101", 1).update(content="Nội dung khác."))
    assert (
        build_approved_snapshot(changed).revision
        != build_approved_snapshot(to_rows(golden_rows())).revision
    )


def test_revision_source_is_a_single_replaceable_seam():
    seen = {}

    def source(session, versions):
        seen["versions"] = len(versions)
        return "approved_at:" + session["approved_at"]

    snapshot = build_approved_snapshot(to_rows(golden_rows()), revision_of=source)
    assert snapshot.revision == "approved_at:2026-11-10T03:00:00+00:00"
    assert seen["versions"] == 2


def test_identity_is_sanitized():
    identity = snapshot_identity(build_approved_snapshot(to_rows(golden_rows())))
    assert set(identity) == {
        "session_id",
        "revision",
        "status",
        "versions",
        "questions_per_version",
    }
    assert identity["questions_per_version"] == 3
    assert "Câu nguồn" not in str(identity) and "Lời giải" not in str(identity)


def _status(d, value):
    d["session"]["status"] = value


CASES = {
    "session_generated": (lambda d: _status(d, "generated"), STATE),
    "session_reviewed": (lambda d: _status(d, "reviewed"), STATE),
    "missing_approved_at": (lambda d: d["session"].update(approved_at=None), INVALID),
    "bad_approved_at": (lambda d: d["session"].update(approved_at="yesterday"), INVALID),
    "blank_title": (lambda d: d["session"].update(title="  "), INVALID),
    "bad_session_id": (lambda d: d["session"].update(id="nope"), INVALID),
    "n_versions_mismatch": (lambda d: d.update(n_versions=3), INVALID),
    "n_versions_bool": (lambda d: d.update(n_versions=True), INVALID),
    "n_versions_zero": (lambda d: d.update(n_versions=0), INVALID),
    "no_sources": (lambda d: d.update(source_question_ids=[]), INVALID),
    "version_not_finalized": (lambda d: d["versions"][0].update(is_finalized=False), INVALID),
    "version_missing_seed": (lambda d: d["versions"][0].update(shuffle_seed=None), INVALID),
    "version_missing_permutations": (lambda d: d["versions"][1].update(permutations=None), INVALID),
    "duplicate_version_code": (lambda d: d["versions"][1].update(version_code="101"), INVALID),
    "empty_solution": (lambda d: question(d, "101", 1).update(solution_md=""), INVALID),
    "blank_solution": (lambda d: question(d, "101", 1).update(solution_md="   \n"), INVALID),
    "null_solution": (lambda d: question(d, "102", 2).update(solution_md=None), INVALID),
    "empty_content": (lambda d: question(d, "101", 2).update(content=" "), INVALID),
    "duplicate_options": (
        lambda d: question(d, "101", 1).update(options=["1", "2", " 2 ", "4"]),
        INVALID,
    ),
    "three_options": (lambda d: question(d, "101", 1).update(options=["1", "2", "3"]), INVALID),
    "pending_status": (lambda d: question(d, "101", 3).update(status="pending_review"), INVALID),
    "not_current": (lambda d: question(d, "101", 3).update(is_current=False), INVALID),
    "missing_slot": (lambda d: d["questions"].remove(question(d, "102", 3)), INVALID),
    "extra_question": (
        lambda d: d["questions"].append(
            {**question(d, "102", 1), "id": "6" * 8 + "-6666-4666-8666-666666666666"}
        ),
        INVALID,
    ),
    "duplicate_source_in_version": (
        lambda d: question(d, "102", 2).update(
            source_question_id=question(d, "102", 1)["source_question_id"]
        ),
        INVALID,
    ),
    "gap_in_question_no": (lambda d: question(d, "101", 3).update(question_no=5), INVALID),
    "question_no_not_int": (lambda d: question(d, "101", 3).update(question_no="3"), INVALID),
    "canonical_not_permutation": (
        lambda d: question(d, "101", 3).update(canonical_question_no=1),
        INVALID,
    ),
    "question_in_unknown_version": (
        lambda d: question(d, "101", 1).update(version_id="7" * 8 + "-7777-4777-8777-777777777777"),
        INVALID,
    ),
    "key_correct_option_differs": (lambda d: key_row(d, "101", 1).update(correct_option="B"), KEYS),
    "key_display_key_differs": (
        lambda d: key_row(d, "102", 2).update(display_correct_key="A"),
        KEYS,
    ),
    "key_display_no_differs": (lambda d: key_row(d, "101", 2).update(display_no=3), KEYS),
    "key_canonical_differs": (lambda d: key_row(d, "102", 1).update(canonical_question_no=1), KEYS),
    "key_missing": (lambda d: d["answer_keys"].remove(key_row(d, "101", 2)), KEYS),
    "key_duplicate": (lambda d: d["answer_keys"].append(dict(key_row(d, "101", 1))), KEYS),
    "key_extra_slot": (
        lambda d: d["answer_keys"].append(
            {**key_row(d, "101", 1), "question_no": 99, "display_no": 99}
        ),
        KEYS,
    ),
    "key_for_unknown_version": (
        lambda d: key_row(d, "101", 1).update(version_id="8" * 8 + "-8888-4888-8888-888888888888"),
        KEYS,
    ),
    "key_question_no_not_int": (lambda d: key_row(d, "101", 1).update(question_no="1"), KEYS),
    "question_key_not_abcd": (lambda d: question(d, "101", 1).update(correct_key="E"), KEYS),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_invalid_persisted_data_fails_closed(name):
    change, (code, status) = CASES[name]
    error = _fail(mutated(change))
    assert (error.error_code, error.status_code) == (code, status), name


def test_error_messages_never_leak_content_solutions_or_raw_values():
    secret = "SECRET-CONTENT-9137"

    def leak(d):
        q = question(d, "101", 1)
        q.update(content=secret, solution_md=secret, options=[secret, secret, "x", "y"])

    error = _fail(mutated(leak))
    assert secret not in str(error.detail)
    assert error.error_code == "ERR_EXPORT_SNAPSHOT_INVALID"
    assert "options" in error.detail  # field names only
    # the ID of an unknown version row is not echoed either
    other = "9" * 8 + "-9999-4999-8999-999999999999"
    error = _fail(mutated(lambda d: question(d, "101", 1).update(version_id=other)))
    assert other not in str(error.detail)


def test_duplicate_current_rows_in_database_are_rejected_by_the_builder():
    """The DB partial unique index normally forbids this; the builder must still refuse it."""

    def duplicate(d):
        copy = {
            **question(d, "101", 1),
            "id": "a" * 8 + "-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "question_no": 2,
        }
        d["questions"].append(copy)

    assert _fail(mutated(duplicate)).error_code == "ERR_EXPORT_SNAPSHOT_INVALID"


def test_other_version_rows_do_not_satisfy_this_versions_slots():
    def swap(d):
        question(d, "101", 1).update(version_id=VERSION_IDS["102"])

    assert _fail(mutated(swap)).error_code == "ERR_EXPORT_SNAPSHOT_INVALID"


def test_golden_json_fixture_matches_builder_and_loads_into_the_export_model():
    """Regenerate with the snippet in docs/api/export-snapshot-contract.md if this fails."""
    path = Path(__file__).parents[1] / "fixtures" / "export_snapshot_golden.json"
    expected = json.loads(path.read_text(encoding="utf-8"))
    built = build_approved_snapshot(to_rows(golden_rows()))
    assert built.model_dump(mode="json") == expected
    assert ApprovedExportSnapshot.model_validate(expected) == built

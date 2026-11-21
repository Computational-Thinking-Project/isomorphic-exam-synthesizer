"""Q01: exception eligibility comes from persisted provenance, never warning flags alone."""

import shutil
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from pydantic import ValidationError
from snapshot_fixtures import OWNER_ID, SESSION_ID, golden_rows, to_rows
from test_snapshot_reader import Client

from app.models.schemas import ReviewDomainException
from app.services.exporter.bundle_models import DisplayQuestion, revalidate_snapshot
from app.services.exporter.export_pipeline import build_compiled_bundle
from app.services.exporter.snapshot_adapter import load_approved_export_snapshot
from app.services.exporter.snapshot_builder import build_approved_snapshot
from app.services.exporter.typst_compiler import TypstCompiler

SNAPSHOT_ID = "77777777-7777-4777-8777-777777777777"


def q01_rows(kind="CONFIRMED_SOURCE_FALLBACK", empty=None):
    data = golden_rows()
    row = data["questions"][0]
    row.update(
        solution_md=empty,
        canonical_solution_md=empty,
        regenerated_from_id=None,
        has_warning=kind == "CONFIRMED_SOURCE_FALLBACK",
    )
    row["validation_report"] = (
        {
            "fallback_source": True,
            "reason": "GENERATION_RETRIES_EXHAUSTED",
            "validation_status": "not_validated",
            "attempts": 4,
            "source_revision_id": SNAPSHOT_ID,
            "source_fingerprint": "a" * 64,
            "confirmed_source_hash": "b" * 64,
        }
        if kind == "CONFIRMED_SOURCE_FALLBACK"
        else {}
    )
    return replace(
        to_rows(data),
        generation_config={"active_variation_modes": [], "canonical_dimensions": []},
        provenance_results=(
            {
                "version_question_id": row["id"],
                "snapshot_id": SNAPSHOT_ID,
                "session_id": SESSION_ID,
                "source_question_id": row["source_question_id"],
                "is_success": True,
                "result_kind": kind,
                "clone_fingerprint": "c" * 64,
            },
        ),
        provenance_snapshots=(
            {
                "id": SNAPSHOT_ID,
                "session_id": SESSION_ID,
                "public_modes": [],
                "canonical_dimensions": [],
            },
        ),
    )


@pytest.mark.parametrize("kind", ["CONFIRMED_SOURCE_FALLBACK", "ORIGINAL_CLONE"])
@pytest.mark.parametrize("empty", [None, "", " \n\t "])
def test_verified_exception_normalizes_without_adding_output_fields(kind, empty):
    rows = q01_rows(kind, empty)
    snapshot = build_approved_snapshot(rows)
    q = snapshot.versions[0].questions[0]
    assert q.solution_md == ""
    assert snapshot.versions[0].questions[1].solution_md
    assert set(q.model_dump()) == {
        "id",
        "question_no",
        "content",
        "options",
        "correct_key",
        "solution_md",
        "status",
    }
    assert (
        snapshot.revision
        == build_approved_snapshot(
            replace(rows, session={**rows.session, "status": "exported"})
        ).revision
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda r: replace(r, provenance_results=()),
        lambda r: replace(r, provenance_results=r.provenance_results * 2),
        lambda r: replace(
            r, provenance_results=({**r.provenance_results[0], "result_kind": "AI_RESULT"},)
        ),
        lambda r: replace(
            r, provenance_results=({**r.provenance_results[0], "is_success": False},)
        ),
        lambda r: replace(
            r, provenance_results=({**r.provenance_results[0], "session_id": "foreign"},)
        ),
        lambda r: replace(
            r, provenance_results=({**r.provenance_results[0], "source_question_id": "foreign"},)
        ),
    ],
)
@pytest.mark.parametrize("kind", ["CONFIRMED_SOURCE_FALLBACK", "ORIGINAL_CLONE"])
def test_wrong_missing_or_ambiguous_provenance_fails_closed(kind, change):
    with pytest.raises(ReviewDomainException) as caught:
        build_approved_snapshot(change(q01_rows(kind)))
    assert (caught.value.status_code, caught.value.error_code) == (
        409,
        "ERR_EXPORT_SNAPSHOT_INVALID",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"canonical_solution_md": "Lời giải gốc phải được giữ."},
        {"regenerated_from_id": SNAPSHOT_ID},
        {"validation_report": {"has_warning": True}},
        {"has_warning": False},
        {"solution_md": 42},
    ],
)
def test_ai_warning_regeneration_and_dropped_canonical_solution_are_rejected(change):
    rows = q01_rows()
    rows.questions[0].update(change)
    with pytest.raises(ReviewDomainException):
        build_approved_snapshot(rows)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: replace(r, generation_config={}),
        lambda r: replace(r, provenance_snapshots=()),
        lambda r: replace(r, provenance_snapshots=r.provenance_snapshots * 2),
        lambda r: replace(
            r, provenance_snapshots=({**r.provenance_snapshots[0], "public_modes": ["NUMERICAL"]},)
        ),
        lambda r: replace(
            r, provenance_results=({**r.provenance_results[0], "clone_fingerprint": "bad"},)
        ),
    ],
)
def test_clone_requires_frozen_empty_modes_dimensions_and_fingerprint(change):
    with pytest.raises(ReviewDomainException):
        build_approved_snapshot(change(q01_rows("ORIGINAL_CLONE")))


def test_plain_model_construction_cannot_opt_in_through_json():
    q = build_approved_snapshot(to_rows(golden_rows())).versions[0].questions[0].model_dump()
    q["solution_md"] = ""
    with pytest.raises(ValidationError):
        DisplayQuestion.model_validate(q)
    with pytest.raises(ValidationError):
        DisplayQuestion.model_validate({**q, "verified_empty_solution": True})


def test_revert_to_verified_root_is_allowed_without_reinterpreting_as_regeneration():
    rows = q01_rows()
    rows.questions[0]["is_reverted"] = True
    assert build_approved_snapshot(rows).versions[0].questions[0].solution_md == ""


def test_malformed_empty_question_id_is_a_sanitized_domain_error():
    rows = q01_rows()
    rows.questions[0]["id"] = "raw-invalid-secret-like-id"
    rows.provenance_results[0]["version_question_id"] = "raw-invalid-secret-like-id"
    with pytest.raises(ReviewDomainException) as caught:
        build_approved_snapshot(rows)
    assert caught.value.error_code == "ERR_EXPORT_SNAPSHOT_INVALID"
    assert "raw-invalid" not in caught.value.detail


class Q01Client(Client):
    def __init__(self, rows):
        self.boundary = rows
        super().__init__(
            {
                "session": dict(rows.session),
                "n_versions": rows.n_versions,
                "source_question_ids": list(rows.source_question_ids),
                "versions": list(rows.versions),
                "questions": list(rows.questions),
                "answer_keys": list(rows.answer_keys),
            },
            config_rows=[
                {"session_id": SESSION_ID, "n_versions": rows.n_versions, **rows.generation_config}
            ],
        )

    def rows(self, name):
        if name == "generation_target_results":
            return deepcopy(self.boundary.provenance_results)
        if name == "generation_job_snapshots":
            return deepcopy(self.boundary.provenance_snapshots)
        return super().rows(name)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["CONFIRMED_SOURCE_FALLBACK", "ORIGINAL_CLONE"])
async def test_reader_privilege_is_limited_to_authorized_empty_solution_provenance(kind):
    rows = q01_rows(kind)
    user, privileged = Q01Client(rows), Q01Client(rows)
    result = await load_approved_export_snapshot(
        user, SESSION_ID, OWNER_ID, provenance_db=privileged
    )
    assert result.versions[0].questions[0].solution_md == ""
    assert "generation_target_results" not in user.calls
    assert set(privileged.calls) <= {"generation_target_results", "generation_job_snapshots"}
    assert privileged.calls
    assert user.calls[0] == user.calls[-1] == "exam_sessions"


@pytest.mark.asyncio
async def test_missing_verifier_is_rejected_and_foreign_owner_never_reads_ledger():
    rows = q01_rows()
    with pytest.raises(ReviewDomainException):
        await load_approved_export_snapshot(Q01Client(rows), SESSION_ID, OWNER_ID)
    privileged = Q01Client(rows)
    with pytest.raises(ReviewDomainException) as caught:
        await load_approved_export_snapshot(
            Q01Client(rows), SESSION_ID, SNAPSHOT_ID, provenance_db=privileged
        )
    assert caught.value.status_code == 403
    assert privileged.calls == []


@pytest.mark.asyncio
async def test_nonempty_snapshot_never_needs_privileged_provenance():
    privileged = Q01Client(q01_rows())
    await load_approved_export_snapshot(
        Client(golden_rows()), SESSION_ID, OWNER_ID, provenance_db=privileged
    )
    assert privileged.calls == []


def test_empty_capability_survives_pipeline_revalidation_but_not_json_or_ai_copy():
    snapshot = build_approved_snapshot(q01_rows())
    assert revalidate_snapshot(snapshot).versions[0].questions[0].solution_md == ""
    with pytest.raises(ValidationError):
        type(snapshot).model_validate(snapshot.model_dump())
    ai = build_approved_snapshot(to_rows(golden_rows()))
    first = ai.versions[0]
    forged = first.questions[0].model_copy(update={"solution_md": ""})
    invalid = ai.model_copy(
        update={
            "versions": (
                first.model_copy(update={"questions": (forged, *first.questions[1:])}),
                *ai.versions[1:],
            )
        }
    )
    with pytest.raises(ValidationError):
        revalidate_snapshot(invalid)


def test_all_output_formats_keep_blank_solution_at_its_display_slot():
    snapshot = build_approved_snapshot(q01_rows())
    compiler = Mock(wraps=TypstCompiler())
    compiler.compile_document.side_effect = lambda source, name: b"%PDF-1.4\n%%EOF\n"
    artifact = build_compiled_bundle(snapshot, compiler=compiler)
    source = compiler.compile_document.call_args_list[0].args[0]
    assert "Câu 1 (Đáp án A):" in source and "Lời giải chi tiết:" in source
    assert "  \n]\n" in source  # heading stays, the solution body is blank
    with ZipFile(BytesIO(artifact.data)) as archive:
        root = f"exam_bundle_{snapshot.session_id}"
        markdown = archive.read(f"{root}/markdown/exam_101.md").decode()
        latex = archive.read(f"{root}/latex/exam_101.tex").decode()
        assert "## Câu 1 — Đáp án A\n\n\n\n## Câu 2" in markdown
        assert "Câu 1 — Đáp án A" in latex and "Câu 2 — Đáp án B" in latex
        assert snapshot.versions[0].questions[1].solution_md in markdown
        assert archive.testzip() is None


@pytest.mark.skipif(shutil.which("typst") is None, reason="Typst executable unavailable")
def test_verified_empty_solution_compiles_into_real_pdf_bundle():
    snapshot = build_approved_snapshot(q01_rows("ORIGINAL_CLONE"))
    artifact = build_compiled_bundle(snapshot)
    with ZipFile(BytesIO(artifact.data)) as archive:
        pdfs = [name for name in archive.namelist() if name.endswith(".pdf")]
        assert len(pdfs) == 2
        assert all(archive.read(name).startswith(b"%PDF-") for name in pdfs)

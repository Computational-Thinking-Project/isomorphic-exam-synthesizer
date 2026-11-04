import copy
import shutil
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from app.services.exporter.bundle_builder import required_pdf_names
from app.services.exporter.bundle_models import ApprovedExportSnapshot, BundleBuildError
from app.services.exporter.exceptions import TypstCompilationError
from app.services.exporter.export_pipeline import build_compiled_bundle
from app.services.exporter.typst_compiler import TypstCompiler
from app.services.shuffler.service import shuffle_exam_version


@pytest.fixture
def shuffled_snapshot(snapshot_data):
    data = copy.deepcopy(snapshot_data)
    other = copy.deepcopy(data["versions"][0])
    other["code"] = "102"
    for question in other["questions"]:
        old_key = question["correct_key"]
        question["options"] = question["options"][1:] + question["options"][:1]
        question["correct_key"] = "ABCD"[("ABCD".index(old_key) - 1) % 4]
        question["solution_md"] = question["solution_md"].replace(
            f"Đáp án {old_key}", f"Đáp án {question['correct_key']}"
        )
    data["versions"].append(other)
    return ApprovedExportSnapshot.model_validate(data)


def test_pipeline_preserves_each_versions_display_data(shuffled_snapshot):
    compiler = Mock(wraps=TypstCompiler())
    compiler.compile_document.side_effect = lambda source, name: (
        b"%PDF-1.4\n" + name.encode() + b"\n%%EOF\n"
    )
    before = shuffled_snapshot.model_dump()
    artifact = build_compiled_bundle(shuffled_snapshot, compiler=compiler)
    assert shuffled_snapshot.model_dump() == before
    assert compiler.compile_document.call_count == 5
    assert {
        call.args[1] for call in compiler.compile_document.call_args_list
    } == required_pdf_names(shuffled_snapshot)
    for index, version in enumerate(shuffled_snapshot.versions):
        expected = [question.model_dump(mode="json") for question in version.questions]
        for renderer in (compiler.render_exam_document, compiler.render_solution_document):
            call = renderer.call_args_list[index]
            assert call.args == (version.code, expected)
            assert call.kwargs == {"exam_title": shuffled_snapshot.title}
    assert compiler.render_answers_matrix_document.call_args.args[0] == [
        {"version_code": "101", "answer_keys": {1: "C", 2: "B"}},
        {"version_code": "102", "answer_keys": {1: "B", 2: "A"}},
    ]
    with ZipFile(BytesIO(artifact.data)) as archive:
        root = f"exam_bundle_{shuffled_snapshot.session_id}"
        for version in shuffled_snapshot.versions:
            tex = archive.read(f"{root}/latex/exam_{version.code}.tex").decode("utf-8")
            md = archive.read(f"{root}/markdown/exam_{version.code}.md").decode("utf-8")
            for question in version.questions:
                answer = f"Câu {question.question_no} — Đáp án {question.correct_key}"
                assert answer in tex and answer in md
        assert archive.testzip() is None


def test_invalid_snapshot_fails_before_compilation(snapshot):
    compiler = Mock(spec=TypstCompiler)
    invalid = snapshot.model_copy(update={"status": "reviewed"})
    with pytest.raises(ValidationError):
        build_compiled_bundle(invalid, compiler=compiler)
    compiler.compile_document.assert_not_called()


def test_compiler_failure_stops_without_partial_bundle(snapshot, monkeypatch):
    compiler = Mock(wraps=TypstCompiler())
    error = TypstCompilationError(message="compile failed")
    compiler.compile_document.side_effect = [b"%PDF-1.4\n%%EOF\n", error]
    bundler = Mock()
    monkeypatch.setattr("app.services.exporter.export_pipeline.build_bundle", bundler)
    with pytest.raises(TypstCompilationError) as caught:
        build_compiled_bundle(snapshot, compiler=compiler)
    assert caught.value is error
    assert compiler.compile_document.call_count == 2
    bundler.assert_not_called()


def test_pipeline_rejects_invalid_pdf_from_compiler(snapshot):
    compiler = Mock(wraps=TypstCompiler())
    compiler.compile_document.return_value = b"not a PDF"
    with pytest.raises(BundleBuildError, match="EXPORT_PDF_INVALID"):
        build_compiled_bundle(snapshot, compiler=compiler)


@pytest.mark.parametrize("shuffle_questions,shuffle_options", [(True, True), (False, True), (True, False)])
def test_real_shuffler_answers_survive_export(snapshot_data, shuffle_questions, shuffle_options):
    """Exercise the upstream shuffler, rather than a hand-written permutation fixture."""
    canonical = [
        {
            "id": q["id"], "content": q["content"],
            "canonical_question_no": q["question_no"], "canonical_options": q["options"],
            "canonical_correct_key": q["correct_key"],
            "canonical_solution_md": q["solution_md"], "status": "approved",
        }
        for q in snapshot_data["versions"][0]["questions"]
    ]
    original = copy.deepcopy(canonical)
    versions = []
    for index in (1, 2):
        result = shuffle_exam_version(
            snapshot_data["session_id"], index, canonical,
            preferences={"shuffle_questions": shuffle_questions, "shuffle_options": shuffle_options},
        )
        questions = []
        for q, answer in zip(result.questions, result.answer_keys, strict=True):
            source = next(item for item in canonical if item["id"] == q.id)
            assert q.options["ABCD".index(q.display_correct_key)] == (
                source["canonical_options"]["ABCD".index(source["canonical_correct_key"])]
            )
            assert (answer.display_no, answer.display_correct_key) == (
                q.display_no, q.display_correct_key
            )
            questions.append({
                "id": q.id, "question_no": q.display_no, "content": q.content,
                "options": q.options, "correct_key": q.display_correct_key,
                "solution_md": q.solution_md, "status": "approved",
            })
        versions.append({"code": result.version_code, "questions": questions})
    snapshot = ApprovedExportSnapshot.model_validate({**snapshot_data, "versions": versions})
    compiler = Mock(wraps=TypstCompiler())
    compiler.compile_document.return_value = b"%PDF-1.4\nfixture\n%%EOF\n"
    artifact = build_compiled_bundle(snapshot, compiler=compiler)
    matrix = compiler.render_answers_matrix_document.call_args.args[0]
    with ZipFile(BytesIO(artifact.data)) as archive:
        root = f"exam_bundle_{snapshot.session_id}"
        for version, row in zip(snapshot.versions, matrix, strict=True):
            assert row["version_code"] == version.code
            for extension, folder in (("md", "markdown"), ("tex", "latex")):
                text = archive.read(f"{root}/{folder}/exam_{version.code}.{extension}").decode("utf-8")
                for q in version.questions:
                    assert row["answer_keys"][q.question_no] == q.correct_key
                    assert f"Câu {q.question_no} — Đáp án {q.correct_key}" in text
                    assert f"Đáp án {q.correct_key}." in q.solution_md
    assert canonical == original


@pytest.mark.skipif(shutil.which("typst") is None, reason="Requires real Typst CLI")
def test_real_typst_to_bundle(shuffled_snapshot):
    before = shuffled_snapshot.model_dump()
    artifact = build_compiled_bundle(shuffled_snapshot)
    with ZipFile(BytesIO(artifact.data)) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == 11
        pdfs = [name for name in names if name.endswith(".pdf")]
        assert len(pdfs) == 5
        for name in pdfs:
            data = archive.read(name)
            assert data.startswith(b"%PDF-") and b"%%EOF" in data[-1024:]
    assert shuffled_snapshot.model_dump() == before


@pytest.mark.skipif(shutil.which("typst") is None, reason="Requires real Typst CLI")
def test_real_typst_solution_with_plain_multiplication(snapshot_data):
    snapshot_data["versions"][0]["questions"][0]["solution_md"] = (
        "**Tính toán:** 3190 * (32 / 55) = 1856.\n\n"
        r"Số cách chọn: $\binom{12}{4}=495$. Đáp án C."
    )
    snapshot = ApprovedExportSnapshot.model_validate(snapshot_data)
    artifact = build_compiled_bundle(snapshot)
    with ZipFile(BytesIO(artifact.data)) as archive:
        assert archive.testzip() is None
        root = f"exam_bundle_{snapshot.session_id}"
        md = archive.read(f"{root}/markdown/exam_101.md").decode("utf-8")
        assert "3190 * (32 / 55) = 1856" in md

import copy
import hashlib
import shutil
import subprocess
from io import BytesIO
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from app.services.exporter import bundle_builder
from app.services.exporter.bundle_builder import build_bundle, required_pdf_names
from app.services.exporter.bundle_models import ApprovedExportSnapshot, BundleBuildError
from app.services.exporter.source_renderer import latex_text


def pdfs(snapshot):
    # Deliberately only a structural PDF fixture, not a rendered exam.
    return {name: b"%PDF-1.4\nfixture\n%%EOF\n" for name in required_pdf_names(snapshot)}


def test_archive_matches_layout_and_preserves_shuffled_answers(snapshot):
    before = snapshot.model_dump()
    inputs = pdfs(snapshot)
    result = build_bundle(snapshot, inputs)
    root = f"exam_bundle_{snapshot.session_id}"
    assert result.filename == f"{root}.zip"
    assert result.content_type == "application/zip"
    assert result.size_bytes == len(result.data)
    assert result.sha256 == hashlib.sha256(result.data).hexdigest()
    with ZipFile(BytesIO(result.data)) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {
            f"{root}/pdf/exam_101.pdf", f"{root}/pdf/solutions_101.pdf",
            f"{root}/pdf/answers_matrix.pdf", f"{root}/latex/exam_101.tex",
            f"{root}/latex/README_huong_dan_bien_dich.txt",
            f"{root}/markdown/exam_101.md", f"{root}/README.txt",
        }
        tex = archive.read(f"{root}/latex/exam_101.tex")
        md = archive.read(f"{root}/markdown/exam_101.md").decode("utf-8")
        assert not tex.startswith(b"\xef\xbb\xbf")
        text = tex.decode("utf-8")
        assert "Đề Toán" in text and r"\usepackage{fontspec}" in text
        assert r"\frac{1}{2}" in text and r"\frac{1}{2}" in md
        assert "Câu 1 — Đáp án C" in text and "Câu 1 — Đáp án C" in md
        assert text.index(r"\item 3") < text.index(r"\item 4") < text.index(r"\item 5")
        assert archive.read(f"{root}/pdf/exam_101.pdf") == inputs["exam_101.pdf"]
        assert "Revision: approved-revision-7" in archive.read(f"{root}/README.txt").decode("utf-8")
    assert snapshot.model_dump() == before
    assert result.data == build_bundle(snapshot, inputs).data


@pytest.mark.parametrize("change", ["missing", "extra", "traversal", "invalid", "truncated"])
def test_bad_pdf_manifest_or_structural_data_fails(snapshot, change):
    inputs = pdfs(snapshot)
    if change == "missing":
        inputs.pop("exam_101.pdf")
    elif change in {"extra", "traversal"}:
        inputs["../secret.pdf" if change == "traversal" else "extra.pdf"] = b"%PDF-1.4\n%%EOF"
    else:
        inputs["exam_101.pdf"] = b"not a PDF" if change == "invalid" else b"%PDF-1.4\ntruncated"
    with pytest.raises(BundleBuildError):
        build_bundle(snapshot, inputs)


@pytest.mark.parametrize("change", ["status", "order", "duplicate", "key", "code", "collision", "count"])
def test_snapshot_guards(snapshot_data, change):
    data = copy.deepcopy(snapshot_data)
    version = data["versions"][0]
    if change == "status":
        data["status"] = "generated"
    elif change == "order":
        version["questions"].reverse()
    elif change == "duplicate":
        version["questions"][0]["options"] = ["1", " 1 ", "2", "3"]
    elif change == "key":
        version["questions"][0]["correct_key"] = "5"
    elif change == "code":
        version["code"] = "../101"
    elif change == "collision":
        data["versions"].append(copy.deepcopy(version))
    else:
        data["versions"].append({**version, "code": "102", "questions": version["questions"][:1]})
    with pytest.raises(ValidationError):
        ApprovedExportSnapshot.model_validate(data)


def test_literal_tex_and_template_syntax_are_not_executed():
    value = r"Tỉ lệ 50% & x_y # {literal} \input{secret} {{7*7}} $\frac{1}{2}$"
    output = latex_text(value)
    assert r"50\% \& x\_y \#" in output
    assert r"\textbackslash{}input\{secret\}" in output
    assert r"\frac{1}{2}" in output
    assert r"\{\{7*7\}\}" in output


@pytest.mark.parametrize("value", [
    r"$\input{secret}$", r"$\write18{command}$", r"$\csname input\endcsname$",
    r"$\^^69nput{secret}$", r"$\begin{document}x\end{document}$", "$x%comment$",
    "$unclosed", "control\x00character",
])
def test_unsupported_math_and_commands_fail_explicitly(value):
    with pytest.raises(BundleBuildError):
        latex_text(value)


def test_resource_limits(snapshot, monkeypatch):
    monkeypatch.setattr(bundle_builder, "MAX_PDF_BYTES", 5)
    with pytest.raises(BundleBuildError, match="EXPORT_PDF_TOO_LARGE"):
        build_bundle(snapshot, pdfs(snapshot))
    monkeypatch.setattr(bundle_builder, "MAX_PDF_BYTES", 100)
    monkeypatch.setattr(bundle_builder, "MAX_BUNDLE_BYTES", 30)
    with pytest.raises(BundleBuildError, match="EXPORT_BUNDLE_TOO_LARGE"):
        build_bundle(snapshot, pdfs(snapshot))


def test_four_versions_have_complete_pdf_and_source_manifest(snapshot_data):
    snapshot_data["versions"] *= 4
    snapshot_data["versions"] = [dict(version, code=str(101 + i))
                                 for i, version in enumerate(snapshot_data["versions"])]
    snapshot = ApprovedExportSnapshot.model_validate(snapshot_data)
    with ZipFile(BytesIO(build_bundle(snapshot, pdfs(snapshot)).data)) as archive:
        assert len(archive.namelist()) == 19  # 9 PDFs + 8 sources + 2 README


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="XeLaTeX not installed; source tests do not prove rendering")
def test_compile_real_xelatex_when_available(snapshot, tmp_path):
    from app.services.exporter.source_renderer import render_tex

    tex = tmp_path / "exam_101.tex"
    tex.write_text(render_tex(snapshot, snapshot.versions[0]), encoding="utf-8")
    result = subprocess.run(
        ["xelatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", tex.name],
        cwd=tmp_path, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout.decode("utf-8", errors="replace")
    assert (tmp_path / "exam_101.pdf").is_file()

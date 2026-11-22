"""Per-version export contract; actual page boundaries also receive PDF visual QA."""

import hashlib
import json
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from app.services.exporter.bundle_models import ApprovedExportSnapshot
from app.services.exporter.export_pipeline import build_compiled_bundle
from app.services.exporter.manifest_bundle import with_manifest
from app.services.exporter.private_models import PACKAGER_VERSION
from app.services.exporter.private_service import PrivateExportService
from app.services.exporter.typst_compiler import TypstCompiler


@pytest.mark.parametrize("count", [1, 2, 4])
def test_one_file_per_version_per_format_with_ordered_matrix(snapshot_data, count):
    first = snapshot_data["versions"][0]
    snapshot_data["versions"] = [{**first, "code": str(101 + i)} for i in range(count)]
    snapshot = ApprovedExportSnapshot.model_validate(snapshot_data)
    compiler = Mock(wraps=TypstCompiler())
    compiler.compile_document.return_value = b"%PDF-1.4\n%%EOF\n"
    artifact = with_manifest(snapshot, build_compiled_bundle(snapshot, compiler=compiler))
    root = f"exam_bundle_{snapshot.session_id}/"
    with ZipFile(BytesIO(artifact.data)) as archive:
        expected = {
            root + f"{folder}/exam_{version.code}.{suffix}"
            for version in snapshot.versions
            for folder, suffix in (("pdf", "pdf"), ("latex", "tex"), ("markdown", "md"))
        } | {root + name for name in (
            "README.txt", "latex/README_huong_dan_bien_dich.txt", "manifest.json"
        )}
        assert set(archive.namelist()) == expected
        assert len(archive.namelist()) == 3 * count + 3
        manifest = json.loads(archive.read(root + "manifest.json"))
        assert manifest["format"] == "w4-export-v2"
        assert {entry["path"] for entry in manifest["files"]} == {
            name.removeprefix(root) for name in expected - {root + "manifest.json"}
        }
        for version in snapshot.versions:
            md = archive.read(root + f"markdown/exam_{version.code}.md").decode()
            tex = archive.read(root + f"latex/exam_{version.code}.tex").decode()
            assert md.index("## Câu 2") < md.index("# Ma trận đáp án") < md.index("# Đáp án và lời giải")
            assert tex.index(r"\clearpage") < tex.index("Ma trận đáp án") < tex.index("Đáp án và lời giải")
            for question in version.questions:
                assert f"| {question.question_no} | {question.correct_key} |" in md
                assert f"{question.question_no} & {question.correct_key}" in tex
    assert compiler.compile_document.call_count == count
    for call in compiler.compile_document.call_args_list:
        source, _ = call.args
        assert source.count("#set page(") == 1
        assert source.count("#pagebreak()") == 1
        # Exam pages can be detached without suggesting missing teacher-only pages.
        assert "Trang #p]]" in source and "Trang #p / #t" not in source
        assert source.index("HẾT") < source.index("#pagebreak()") < source.index("MA TRẬN ĐÁP ÁN")
        assert source.index("MA TRẬN ĐÁP ÁN") < source.index("II. LỜI GIẢI")


def test_v2_uses_new_identity_and_keeps_v1_artifact_separate(snapshot):
    snapshot = snapshot.model_copy(update={"revision": "sha256:" + "a" * 64})
    service = PrivateExportService(Mock(return_value=snapshot), Mock(), Mock())
    _, identity = service._snapshot(str(snapshot.session_id), "00000000-0000-0000-0000-000000000099")
    old_key = hashlib.sha256(f"w4-export-v1\n{snapshot.revision}".encode()).hexdigest()
    assert PACKAGER_VERSION == identity.packager_version == "w4-export-v2"
    assert identity.packaging_key != old_key
    assert identity.packaging_key == hashlib.sha256(
        f"w4-export-v2\n{snapshot.revision}".encode()
    ).hexdigest()

"""TASK-12: unchanged Golden real compiler oracle; not provenance/Storage evidence.

RENDER12-01 is fixed by the integrated TASK-306 converter. Keep the original
math as a positive real-compiler regression, without replacing difficult content.
"""

import hashlib
import json
import shutil
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile

import pytest

from app.services.exporter.bundle_models import ApprovedExportSnapshot
from app.services.exporter.manifest_bundle import build_private_bundle


@pytest.mark.skipif(shutil.which("typst") is None, reason="Typst executable unavailable")
@pytest.mark.parametrize("empty_solutions", [False, True])
def test_unchanged_golden_compiles_to_private_bundle(empty_solutions):
    fixture = Path(__file__).parents[1] / "fixtures/export_preview_off_off.json"
    golden = json.loads(fixture.read_text(encoding="utf-8"))
    fields = ("id", "question_no", "content", "options", "correct_key", "solution_md", "status")
    versions = []
    empty_ids = set()
    for version in golden["versions"]:
        questions = [{key: q[key] for key in fields} for q in version["questions"]]
        if empty_solutions:
            for question in questions:
                question["solution_md"] = ""
                empty_ids.add(UUID(question["id"]))
        versions.append({"code": version["version_code"], "questions": questions})
    # Renderer-only fixture: internal context stands in for already-verified
    # provenance. Eligibility is tested separately through the real SQL reader.
    snapshot = ApprovedExportSnapshot.model_validate(
        {
            "session_id": golden["session_id"],
            "revision": "renderer-only-golden",
            "title": "Golden export",
            "status": "approved",
            "versions": versions,
        },
        context={"verified_empty_solution_ids": empty_ids},
    )
    artifact = build_private_bundle(snapshot)
    assert artifact.size_bytes > 0
    root = f"exam_bundle_{snapshot.session_id}/"
    with ZipFile(BytesIO(artifact.data)) as archive:
        expected_pdfs = {
            f"pdf/exam_{version.code}.pdf"
            for version in snapshot.versions
        }
        expected_entries = expected_pdfs | {
            f"{directory}/exam_{version.code}.{extension}"
            for version in snapshot.versions
            for directory, extension in (("latex", "tex"), ("markdown", "md"))
        } | {"README.txt", "latex/README_huong_dan_bien_dich.txt", "manifest.json"}
        assert set(archive.namelist()) == {root + name for name in expected_entries}
        assert len(archive.namelist()) == len(expected_entries)
        for name in expected_pdfs:
            assert archive.read(root + name).startswith(b"%PDF-")
        manifest = json.loads(archive.read(root + "manifest.json"))
        assert manifest["format"] == "w4-export-v2"
        assert manifest["revision"] == snapshot.revision
        assert manifest["session_id"] == str(snapshot.session_id)
        assert {entry["path"] for entry in manifest["files"]} == expected_entries - {"manifest.json"}
        assert len(manifest["files"]) == len(expected_entries) - 1
        for entry in manifest["files"]:
            data = archive.read(root + entry["path"])
            assert entry["sha256"] == hashlib.sha256(data).hexdigest()
            assert entry["size_bytes"] == len(data)

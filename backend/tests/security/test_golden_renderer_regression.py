"""TASK-12: unchanged Golden real compiler oracle; not provenance/Storage evidence.

RENDER12-01 belongs to TASK-306 (Tam). Keep the original math rather than replacing
it with easier content. A changed failure or a fix must trigger review of this
strict expected-failure marker before claiming Golden acceptance.
"""

import json
import shutil
from pathlib import Path
from uuid import UUID

import pytest

from app.services.exporter.bundle_models import ApprovedExportSnapshot
from app.services.exporter.exceptions import TypstCompilationError
from app.services.exporter.manifest_bundle import build_private_bundle


@pytest.mark.skipif(shutil.which("typst") is None, reason="Typst executable unavailable")
@pytest.mark.xfail(
    strict=True,
    raises=TypstCompilationError,
    reason=r"RENDER12-01 / TASK-306: original Golden \int compiles as unknown variable nt",
)
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
    try:
        artifact = build_private_bundle(snapshot)
    except TypstCompilationError as exc:
        # Only this known compiler error is expected, never arbitrary failures.
        assert "unknown variable: nt" in str(exc)
        assert r"\int" in str(exc)
        raise
    assert artifact.size_bytes > 0

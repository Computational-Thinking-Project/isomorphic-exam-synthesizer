"""Q01 through owner-RLS loader and private HTTP orchestration, with fake durable ports.

Real Typst on success; these tests do not attest deployed JWT/PostgREST/Storage ACLs.
"""

import shutil
from dataclasses import replace
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from test_private_http import http as shared_http
from test_private_http import workflow as shared_workflow
from test_snapshot_q01 import Q01Client, q01_rows

from app.services.exporter.manifest_bundle import build_private_bundle
from app.services.exporter.private_service import user_snapshot_loader
from app.services.exporter.snapshot_builder import build_approved_snapshot

http = shared_http


@pytest.fixture
def workflow():
    return shared_workflow.__wrapped__(build_approved_snapshot(q01_rows()))


@pytest.mark.parametrize("kind", ["CONFIRMED_SOURCE_FALLBACK", "ORIGINAL_CLONE"])
def test_empty_solution_http_build_replay_download_preserves_section(http, workflow, kind):
    if not shutil.which("typst"):
        pytest.skip("Typst compiler not installed")
    client, path, _, _ = http
    rows = q01_rows(kind)
    user, provenance = Q01Client(rows), Q01Client(rows)
    service, ledger, store, _, _ = workflow
    service.loader = user_snapshot_loader(user, provenance_db=provenance)
    service.build = Mock(side_effect=build_private_bundle)
    first = client.post(path)
    assert first.status_code == 200 and first.json()["state"] == "ready"
    assert client.post(path).json() == first.json()
    assert client.get(path).json() == first.json()
    assert client.post(path + "/download-url").status_code == 200
    assert store.uploads == ledger.completions == service.build.call_count == store.signs == 1
    with ZipFile(BytesIO(next(iter(store.objects.values())))) as archive:
        assert archive.testzip() is None
        solutions = next(n for n in archive.namelist() if n.endswith("markdown/exam_101.md"))
        text = archive.read(solutions).decode()
        assert "## Câu 1 — Đáp án A\n\n\n\n## Câu 2" in text
        assert any(n.endswith("manifest.json") for n in archive.namelist())
    assert not any(
        t in {"generation_target_results", "generation_job_snapshots"} for t in user.calls
    )


@pytest.mark.parametrize("failure", ["missing_verifier", "ai_result", "foreign_owner", "transport"])
def test_q01_all_routes_fail_before_claim_build_upload_or_sign(http, workflow, failure):
    client, path, _, _ = http
    rows = q01_rows()
    if failure == "ai_result":
        rows = replace(
            rows, provenance_results=({**rows.provenance_results[0], "result_kind": "AI_RESULT"},)
        )
    if failure == "foreign_owner":
        rows.session["user_id"] = "99999999-9999-4999-8999-999999999999"
    user, provenance = Q01Client(rows), Q01Client(rows)
    if failure == "transport":
        provenance.table = Mock(side_effect=RuntimeError("secret transport details"))
    service, ledger, store, _, builder = workflow
    service.loader = user_snapshot_loader(
        user, provenance_db=None if failure == "missing_verifier" else provenance
    )
    for method, target in [
        (client.post, path),
        (client.get, path),
        (client.post, path + "/download-url"),
    ]:
        response = method(target)
        expected = 503 if failure == "transport" else 403 if failure == "foreign_owner" else 409
        assert response.status_code == expected
        assert "secret" not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert ledger.current is None and ledger.ready is None
    assert builder.call_count == store.uploads == store.signs == 0
    if failure == "foreign_owner":
        assert provenance.calls == []

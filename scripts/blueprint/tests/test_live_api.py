"""Explicit opt-in only; ordinary pytest and CI never call Gemini."""

import json
import os
import subprocess
import sys

import pytest

from blueprint_tool.common import ROOT


@pytest.mark.skipif(
    os.environ.get("BLUEPRINT_RUN_LIVE_TESTS") != "1", reason="Live API test is opt-in"
)
def test_gemini_single(tmp_path):
    assert os.environ.get("GEMINI_API_KEY"), "GEMINI_API_KEY required"
    output = tmp_path / "live.json"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/blueprint/create_blueprints.py"),
            "--mode",
            "single",
            "--input",
            str(ROOT / "scripts/blueprint/tests/fixtures/single_input.json"),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=400,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["summary"]["succeeded"] == 1
    assert result["run_metadata"]["provider"] == "gemini"

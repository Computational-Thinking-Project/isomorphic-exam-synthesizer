import json
import os
import subprocess
import sys

from blueprint_tool.common import ROOT, atomic_write

SCRIPT = ROOT / "scripts/blueprint/create_blueprints.py"


def call(tmp_path, payload, mode="single", *extra):
    output = tmp_path / "result.json"
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            mode,
            "--input",
            "-",
            "--output",
            str(output),
            "--provider",
            "mock",
            *extra,
        ],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        timeout=20,
    )
    return process, json.loads(output.read_text(encoding="utf-8"))


def test_single_stdin_from_other_cwd(tmp_path, item):
    process, result = call(tmp_path, item)
    assert process.returncode == 0, process.stderr
    assert result["summary"] == {"total": 1, "succeeded": 1, "failed": 0}
    assert result["results"][0]["blueprint"]["requirement"]["source"] == item["source"]
    assert json.loads(process.stdout)["output"].endswith("result.json")


def test_batch_partial_and_missing_id(tmp_path, item):
    process, result = call(tmp_path, {"questions": [item, {"source": {}}]}, "batch")
    assert process.returncode == 3, process.stderr
    assert result["summary"] == {"total": 2, "succeeded": 1, "failed": 1}
    assert result["results"][1]["index"] == 1 and result["results"][1]["question_id"] is None


def test_global_duplicate_ids(tmp_path, item):
    process, result = call(tmp_path, {"questions": [item, item]}, "batch")
    assert process.returncode == 2
    assert result["error"]["code"] == "DUPLICATE_QUESTION_ID"
    assert result["results"] == [] and result["summary"]["total"] == 0


def test_all_failed_and_unknown_mock(tmp_path, item):
    item["source"]["content"][0]["text"] += " Một câu mới."
    process, result = call(tmp_path, item)
    assert process.returncode == 4
    assert result["results"][0]["error"]["code"] == "MOCK_NO_FIXTURE"


def test_bad_json_cli_and_input_size(tmp_path):
    output = tmp_path / "error.json"
    for data, extra, expected in [
        ("{} {}", [], "INVALID_JSON"),
        ("{}", ["--concurrency", "0"], "CONFIG_INVALID"),
        (" " * 262145, [], "INPUT_TOO_LARGE"),
    ]:
        process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--mode",
                "single",
                "--input",
                "-",
                "--output",
                str(output),
                "--provider",
                "mock",
                *extra,
            ],
            input=data,
            text=True,
            capture_output=True,
            timeout=20,
        )
        assert process.returncode == 2
        assert json.loads(output.read_text(encoding="utf-8"))["error"]["code"] == expected


def test_atomic_failure_preserves_previous_file(tmp_path, monkeypatch):
    output = tmp_path / "old.json"
    output.write_text('{"old":true}', encoding="utf-8")

    def fail(*args):
        raise OSError("simulated disk error")

    monkeypatch.setattr(os, "replace", fail)
    import pytest

    with pytest.raises(OSError):
        atomic_write(output, {"new": True})
    assert output.read_text(encoding="utf-8") == '{"old":true}'
    assert not list(tmp_path.glob(".blueprint_*.tmp"))


def test_output_cannot_overwrite_input(tmp_path, item):
    path = tmp_path / "input.json"
    original = json.dumps(item, ensure_ascii=False)
    path.write_text(original, encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "single",
            "--input",
            str(path),
            "--output",
            str(path),
            "--provider",
            "mock",
        ],
        capture_output=True,
        timeout=20,
    )
    assert process.returncode == 2
    assert path.read_text(encoding="utf-8") == original


def test_key_not_written_or_logged(tmp_path, item):
    key = "test_key_do_not_log_123456"
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "single",
            "--input",
            "-",
            "--output",
            str(tmp_path / "out.json"),
            "--provider",
            "mock",
        ],
        input=json.dumps(item),
        text=True,
        capture_output=True,
        env={**os.environ, "GEMINI_API_KEY": key},
        timeout=20,
    )
    assert process.returncode == 0
    assert key not in process.stdout + process.stderr + (tmp_path / "out.json").read_text(
        encoding="utf-8"
    )


def test_missing_key_writes_global_error(tmp_path, item):
    env = {k: v for k, v in os.environ.items() if k not in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}}
    output = tmp_path / "missing-key.json"
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "single",
            "--input",
            "-",
            "--output",
            str(output),
            "--provider",
            "gemini",
        ],
        input=json.dumps(item),
        text=True,
        capture_output=True,
        env=env,
        timeout=20,
    )
    assert process.returncode == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["error"]["code"] == "API_KEY_MISSING"
    assert result["results"] == []


def test_output_directory_returns_io_error(tmp_path, item):
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "single",
            "--input",
            "-",
            "--output",
            str(tmp_path),
            "--provider",
            "mock",
        ],
        input=json.dumps(item),
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert process.returncode == 1
    assert json.loads(process.stderr)["error"] == "OUTPUT_IO"

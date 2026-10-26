"""Strict JSON, safe errors and file utilities shared by the standalone tool."""

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL_DIR = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 262_144
MAX_RESPONSE_BYTES = 2_097_152


class ToolError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []

    def as_dict(self):
        return {"code": self.code, "message": self.message, "details": self.details}


def pointer(parts):
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def strict_json(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ToolError("DUPLICATE_JSON_KEY", "JSON chứa tên trường trùng lặp.")
            result[key] = value
        return result

    def nonfinite(_):
        raise ToolError("INVALID_JSON", "JSON không được chứa NaN hoặc Infinity.")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, RecursionError) as exc:
        raise ToolError("INVALID_JSON", "Không đọc được một JSON document hợp lệ.") from exc


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def load_json(path):
    return strict_json(Path(path).read_text(encoding="utf-8-sig"))


def preflight_output(path, protected=()):
    path = Path(path).resolve()
    if path in {Path(p).resolve() for p in protected}:
        raise ToolError(
            "OUTPUT_COLLISION", "Output không được ghi đè input hoặc tài nguyên của script."
        )
    if path.is_dir():
        raise ToolError("OUTPUT_IO", "Đường dẫn output đang là một thư mục.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".blueprint_probe_", delete=True):
        pass


def atomic_write(path, value):
    path = Path(path).resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=".blueprint_",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

"""Single/batch command, safe preflight and one atomic JSON result file."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from . import __version__
from .common import (
    MAX_INPUT_BYTES,
    ROOT,
    TOOL_DIR,
    ToolError,
    atomic_write,
    canonical,
    load_json,
    preflight_output,
    strict_json,
)
from .config import resolve_config
from .extractor import Extractor
from .input_adapter import Contracts, input_items
from .prompt_builder import FILES, PROMPT_VERSION, Prompts
from .schema_adapter import build_api_schema
from .validators import schema_issues


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError("CLI_INVALID", "Tham số không hợp lệ; dùng --help để xem cách gọi.")


def parser():
    result = Parser(description="Tạo blueprint từ JSON câu mẫu; không sinh candidate.")
    result.add_argument("--mode", choices=("single", "batch"), required=True)
    result.add_argument("--input", required=True, help="File UTF-8 hoặc - để đọc stdin")
    result.add_argument("--output", required=True, help="File JSON kết quả")
    result.add_argument("--config")
    result.add_argument("--schema")
    result.add_argument("--prompt-directory")
    result.add_argument("--provider", choices=("gemini", "mock"))
    result.add_argument("--model")
    for name in (
        "concurrency",
        "request-timeout-seconds",
        "item-timeout-seconds",
        "max-requests-per-item",
        "max-output-tokens",
    ):
        result.add_argument("--" + name)
    return result


def _hint(argv, name):
    value = None
    for index, arg in enumerate(argv):
        if arg == name and index + 1 < len(argv):
            value = argv[index + 1]
        elif arg.startswith(name + "="):
            value = arg.split("=", 1)[1]
    return value


def _safe_output(argv, args=None, config=None):
    value = args.output if args else _hint(argv, "--output")
    if not value or value == "-":
        raise ToolError("OUTPUT_IO", "Cần một đường dẫn file output, không dùng stdout.")
    path = Path(value).resolve()
    if path.is_relative_to(TOOL_DIR) or (
        path.exists() and path.is_relative_to(ROOT / "scripts/blueprint")
    ):
        raise ToolError(
            "OUTPUT_COLLISION", "Output không được ghi vào tài nguyên và code của script."
        )
    protected = [ROOT / "docs/blueprints/science-blueprint.schema.json"]
    for name in ("input", "schema", "config"):
        candidate = getattr(args, name, None) if args else _hint(argv, "--" + name)
        if candidate and candidate != "-":
            protected.append(candidate)
    if config:
        protected.append(config.schema_path)
        protected.extend(config.prompt_directory / filename for filename in FILES)
    preflight_output(path, protected)
    return path


async def _run(extractor, items):
    try:
        return await extractor.run(items)
    finally:
        await extractor.client.close()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.getLogger("google").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    start = time.monotonic()
    mode = _hint(argv, "--mode")
    mode = mode if mode in {"single", "batch"} else "single"
    metadata = {
        "run_id": "run_" + uuid.uuid4().hex,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "tool_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "items": [],
        "requests": 0,
    }
    envelope = {
        "contract_version": "1.0.0",
        "mode": mode,
        "results": [],
        "summary": {"total": 0, "succeeded": 0, "failed": 0},
        "error": None,
        "run_metadata": metadata,
    }
    output, contracts, args, config = None, None, None, None
    exit_code = 2
    try:
        args = parser().parse_args(argv)
        envelope["mode"] = args.mode
        output = _safe_output(argv, args)
        config = resolve_config(args)
        output = _safe_output(argv, args, config)
        try:
            schema = load_json(config.schema_path)
            contracts = Contracts(schema)
            if schema["$defs"]["requirement"]["properties"]["schema_version"] != {"const": "0.4.0"}:
                raise ToolError("SCHEMA_UNSUPPORTED", "Chỉ hỗ trợ hợp đồng blueprint 0.4.0.")
            api_schema, manifest = build_api_schema(schema)
            prompts = Prompts(config.prompt_directory)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(
                "RESOURCE_INVALID", "Không tải được schema, contracts hoặc prompts của script."
            ) from exc
        metadata.update(
            provider=config.provider,
            model_requested=config.model,
            config=config.public(),
            packages={name: version(name) for name in ("google-genai", "jsonschema")},
            schema_sha256=hashlib.sha256(canonical(schema).encode()).hexdigest(),
            api_schema_sha256=hashlib.sha256(canonical(api_schema).encode()).hexdigest(),
            schema_adapter_manifest=manifest,
            prompt_version=PROMPT_VERSION,
            prompt_sha256=prompts.hash,
        )
        try:
            if args.input == "-":
                data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
            else:
                with Path(args.input).open("rb") as stream:
                    data = stream.read(MAX_INPUT_BYTES + 1)
        except OSError as exc:
            raise ToolError("INPUT_IO", "Không đọc được file input.") from exc
        if len(data) > MAX_INPUT_BYTES:
            raise ToolError(
                "INPUT_TOO_LARGE", "Input vượt giới hạn 262144 byte; script không tự cắt nội dung."
            )
        try:
            raw = strict_json(data.decode("utf-8-sig"))
        except UnicodeError as exc:
            raise ToolError("INPUT_ENCODING", "Input phải dùng UTF-8.") from exc
        items = input_items(raw, args.mode)
        if config.provider == "gemini":
            from .ai_client import GeminiClient

            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not api_key:
                raise ToolError("API_KEY_MISSING", "Cần GEMINI_API_KEY trong môi trường process.")
            client = GeminiClient(config, api_key)
        else:
            from .mock_client import MockClient

            client = MockClient()
        extractor = Extractor(config, schema, api_schema, contracts, prompts, client)
        results, item_metadata = asyncio.run(_run(extractor, items))
        envelope["results"] = results
        metadata["items"] = item_metadata
        metadata["requests"] = sum(m["requests"] for m in item_metadata)
        succeeded = sum(result["blueprint"] is not None for result in results)
        envelope["summary"] = {
            "total": len(results),
            "succeeded": succeeded,
            "failed": len(results) - succeeded,
        }
        exit_code = 0 if succeeded == len(results) else 3 if succeeded else 4
    except ToolError as exc:
        envelope["error"] = exc.as_dict()
        exit_code = 1 if exc.code == "OUTPUT_IO" else 2
    except OSError:
        envelope["error"] = ToolError(
            "OUTPUT_IO", "Không truy cập được đường dẫn output."
        ).as_dict()
        exit_code = 1
    except KeyboardInterrupt:
        envelope["error"] = ToolError(
            "INTERRUPTED", "Process bị ngắt trước khi hoàn tất."
        ).as_dict()
        exit_code = 1
    except Exception:
        envelope["error"] = ToolError(
            "INTERNAL", "Lỗi nội bộ; không dùng kết quả cũ để tiếp tục generate."
        ).as_dict()
        exit_code = 1
    metadata["elapsed_seconds"] = round(time.monotonic() - start, 3)
    metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    try:
        if envelope["error"] is not None:
            envelope["results"] = []
            envelope["summary"] = {"total": 0, "succeeded": 0, "failed": 0}
        if contracts and schema_issues(envelope, contracts.result, contracts.registry):
            raise ToolError("OUTPUT_INVALID", "Envelope không thỏa hợp đồng kết quả.")
        output = _safe_output(argv, args, config)
        atomic_write(output, envelope)
    except Exception:
        print(
            json.dumps(
                {
                    "error": "OUTPUT_IO",
                    "message": "Không ghi được file kết quả mới; không dùng file cũ.",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1 if exit_code != 2 else 2
    if envelope["error"]:
        print(json.dumps(envelope["error"], ensure_ascii=False), file=sys.stderr)
    print(json.dumps({"output": str(output), "summary": envelope["summary"]}, ensure_ascii=False))
    return exit_code

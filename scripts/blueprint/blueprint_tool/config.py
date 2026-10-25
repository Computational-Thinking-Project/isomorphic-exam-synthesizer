"""CLI > environment > explicitly supplied TOML > defaults. Never reads .env."""

import math
import os
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from .common import ROOT, TOOL_DIR, ToolError


@dataclass
class Config:
    provider: str = "gemini"
    model: str = "gemini-3.5-flash-lite"
    request_timeout_seconds: float = 120
    item_timeout_seconds: float = 360
    max_requests_per_item: int = 3
    max_output_tokens: int = 16384
    concurrency: int = 3
    schema_path: Path = ROOT / "docs/blueprints/science-blueprint.schema.json"
    prompt_directory: Path = TOOL_DIR / "prompts"

    def public(self):
        return {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(self).items()
        }


def resolve_config(args, env=None):
    env = os.environ if env is None else env
    values = {}
    sections = {
        "ai": {
            "provider",
            "model",
            "request_timeout_seconds",
            "item_timeout_seconds",
            "max_requests_per_item",
            "max_output_tokens",
        },
        "batch": {"concurrency"},
        "resources": {"schema_path", "prompt_directory"},
        "output": {"encoding", "atomic_write", "log_level"},
    }
    if args.config:
        try:
            with Path(args.config).open("rb") as stream:
                data = tomllib.load(stream)
        except (OSError, ValueError) as exc:
            raise ToolError("CONFIG_INVALID", "Không đọc được file cấu hình TOML.") from exc
        for section, content in data.items():
            if (
                section not in sections
                or not isinstance(content, dict)
                or set(content) - sections[section]
            ):
                raise ToolError("CONFIG_INVALID", "TOML có section hoặc trường không hỗ trợ.")
            if section == "output":
                if any(
                    content.get(k, v) != v
                    for k, v in {
                        "encoding": "utf-8",
                        "atomic_write": True,
                        "log_level": "INFO",
                    }.items()
                ):
                    raise ToolError(
                        "CONFIG_INVALID", "Output dùng UTF-8, ghi nguyên tử và log INFO cố định."
                    )
            else:
                values.update(content)
    for name in Config.__dataclass_fields__:
        env_name = "BLUEPRINT_" + name.upper()
        if env.get(env_name):
            values[name] = env[env_name]
        cli_name = {"schema_path": "schema", "prompt_directory": "prompt_directory"}.get(name, name)
        if getattr(args, cli_name, None) is not None:
            values[name] = getattr(args, cli_name)
    # GEMINI_MODEL is a legacy fallback below BLUEPRINT_MODEL, above TOML.
    if args.model is None and not env.get("BLUEPRINT_MODEL") and env.get("GEMINI_MODEL"):
        values["model"] = env["GEMINI_MODEL"]
    config = Config()
    for name, value in values.items():
        try:
            if name in {"request_timeout_seconds", "item_timeout_seconds"}:
                if isinstance(value, bool):
                    raise ValueError
                value = float(value)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError
            elif name in {"concurrency", "max_requests_per_item", "max_output_tokens"}:
                if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
                    raise ValueError
                value = int(value)
                if value < 1:
                    raise ValueError
            elif name in {"schema_path", "prompt_directory"}:
                value = Path(value)
                value = value.resolve() if value.is_absolute() else (ROOT / value).resolve()
            elif not isinstance(value, str) or not value.strip():
                raise ValueError
            setattr(config, name, value)
        except (TypeError, ValueError) as exc:
            raise ToolError(
                "CONFIG_INVALID", "Giá trị cấu hình không hợp lệ.", [{"field": name}]
            ) from exc
    if config.provider not in {"gemini", "mock"}:
        raise ToolError("CONFIG_INVALID", "Provider chỉ hỗ trợ gemini hoặc mock.")
    if (
        config.max_requests_per_item > 3
        or config.concurrency > 32
        or config.max_output_tokens > 65536
    ):
        raise ToolError(
            "CONFIG_INVALID", "Giới hạn tối đa: 3 request/câu, concurrency 32, output 65536 token."
        )
    return config

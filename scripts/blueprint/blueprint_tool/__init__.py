"""Compatibility imports for the standalone CLI; implementation lives in backend."""

import importlib
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[3] / "backend"
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

from app.services.blueprint import __version__  # noqa: E402,F401

for _name in (
    "ai_client",
    "cli",
    "common",
    "config",
    "extractor",
    "input_adapter",
    "mock_client",
    "prompt_builder",
    "schema_adapter",
    "validators",
):
    _module = importlib.import_module(f"app.services.blueprint.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    setattr(sys.modules[__name__], _name, _module)

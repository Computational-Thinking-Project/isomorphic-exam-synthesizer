import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from blueprint_tool.common import ROOT, load_json  # noqa: E402
from blueprint_tool.config import Config  # noqa: E402
from blueprint_tool.extractor import Extractor  # noqa: E402
from blueprint_tool.input_adapter import Contracts  # noqa: E402
from blueprint_tool.prompt_builder import Prompts  # noqa: E402
from blueprint_tool.schema_adapter import build_api_schema  # noqa: E402


@pytest.fixture
def science_schema():
    return load_json(Config().schema_path)


@pytest.fixture
def example():
    return load_json(ROOT / "docs/blueprints/examples/physics_newton_acceleration.json")


@pytest.fixture
def item(example):
    return {
        "source": example["requirement"]["source"],
        "context": {"subject": "physics", "language": "vi"},
    }


@pytest.fixture
def make_extractor(science_schema):
    def make(client, **kwargs):
        config = Config(provider="mock", **kwargs)
        api_schema, _ = build_api_schema(science_schema)
        return Extractor(
            config,
            science_schema,
            api_schema,
            Contracts(science_schema),
            Prompts(config.prompt_directory),
            client,
        )

    return make

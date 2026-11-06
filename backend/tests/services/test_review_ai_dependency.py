"""Configuration boundary uses real Settings, without constructing a gateway."""

from types import SimpleNamespace

import pytest

from app.api.routes.review import get_ai_generator
from app.core.config import Settings
from app.services.generation.targeted_service import TargetedRegenerator


def configured(**overrides):
    values = dict.fromkeys(
        ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"], ""
    )
    return Settings(_env_file=None, **(values | overrides))


@pytest.mark.parametrize("key", ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_3"])
def test_real_settings_configured_keys_enable_targeted_adapter(key):
    runtime = SimpleNamespace(settings=configured(**{key: "offline-fixture"}), generation=object())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(ai_services=runtime)))
    adapter = get_ai_generator(request)
    assert isinstance(adapter, TargetedRegenerator)
    assert adapter.service is runtime.generation
    assert adapter.max_api_calls == 4


def test_unconfigured_runtime_does_not_construct_generation_or_gateway():
    class Runtime:
        settings = configured()

        @property
        def generation(self):
            raise AssertionError("Unconfigured runtime must not access gateway")

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(ai_services=Runtime())))
    assert get_ai_generator(request) is None

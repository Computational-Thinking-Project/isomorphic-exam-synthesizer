"""Exercise real request routing without sending credentials or calling Gemini."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.genai import types

from app.core.config import Settings
from app.models.schemas import SourceQuestion
from app.services.ai import client as client_module


def test_settings_collect_distinct_nonempty_keys():
    config = Settings(
        _env_file=None,
        GEMINI_API_KEY="legacy-test",
        GEMINI_API_KEY_1=" first-test ",
        GEMINI_API_KEY_2="first-test",
        GEMINI_API_KEY_3=" ",
    )
    assert config.get_gemini_api_keys() == ["legacy-test", "first-test"]
    assert "legacy-test" not in repr(config)
    assert "first-test" not in repr(config)


@pytest.fixture
def sdk_pool(monkeypatch):
    clients = []

    def create_client(**kwargs):
        sdk = SimpleNamespace(models=SimpleNamespace(generate_content=Mock()))
        clients.append((kwargs, sdk))
        return sdk

    monkeypatch.setattr(client_module, "settings", SimpleNamespace(
        get_gemini_api_keys=lambda: ["test-1", "test-2"], GEMINI_MODEL="test-model"
    ))
    monkeypatch.setattr(client_module.genai, "Client", create_client)
    selections = iter([0, 1, 0, 1])
    monkeypatch.setattr(client_module.secrets, "choice", lambda pool: pool[next(selections)])
    monkeypatch.setattr(client_module.time, "sleep", lambda seconds: None)
    return clients


def test_each_request_selects_key_and_disables_hidden_sdk_retries(sdk_pool):
    client = client_module.GeminiClient()
    config = types.GenerateContentConfig(response_mime_type="application/json")
    client.generate_content(contents="one", config=config)
    client.generate_content(contents="two", config=config)
    assert [sdk.models.generate_content.call_count for _, sdk in sdk_pool] == [1, 1]
    assert all(args["http_options"].retry_options.attempts == 1 for args, _ in sdk_pool)


def test_explicit_key_overrides_pool(sdk_pool):
    client_module.GeminiClient(api_key="explicit-test")
    assert len(sdk_pool) == 1
    assert sdk_pool[0][0]["api_key"] == "explicit-test"


@pytest.mark.parametrize("first_result", ["broken JSON", RuntimeError("503 temporary")])
def test_repair_and_retry_choose_key_again(sdk_pool, first_result):
    client = client_module.GeminiClient()
    valid_data = {
        "variant_id": "v1",
        "source_question_id": "q1",
        "question_text": "Compute $1+1$",
        "options": ["1", "2", "3", "4"],
        "correct_answer": "2",
        "solution_steps": "$1+1=2$",
    }
    first = sdk_pool[0][1].models.generate_content
    if isinstance(first_result, Exception):
        first.side_effect = first_result
    else:
        first.return_value = SimpleNamespace(text=first_result)
    sdk_pool[1][1].models.generate_content.return_value = SimpleNamespace(text=json.dumps(valid_data))
    result = client.generate_variant(
        SourceQuestion(id="q1", question_text="Compute $1+1$", options=["1", "2", "3", "4"], correct_answer="2")
    )
    assert result.correct_answer == "2"
    assert [sdk.models.generate_content.call_count for _, sdk in sdk_pool] == [1, 1]


def test_missing_keys_fail_before_creating_sdk(monkeypatch):
    monkeypatch.setattr(client_module, "settings", SimpleNamespace(get_gemini_api_keys=lambda: []))
    create_client = Mock()
    monkeypatch.setattr(client_module.genai, "Client", create_client)
    with pytest.raises(ValueError, match="Chưa cấu hình"):
        client_module.GeminiClient()
    create_client.assert_not_called()

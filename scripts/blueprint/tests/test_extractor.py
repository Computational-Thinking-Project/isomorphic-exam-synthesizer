import asyncio
import copy

from blueprint_tool.ai_client import ProviderError, Reply
from blueprint_tool.common import canonical
from blueprint_tool.schema_adapter import generation_payload


class SequenceClient:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0
        self.prompts = []

    async def generate(self, **kwargs):
        self.calls += 1
        self.prompts.append(kwargs["prompt"])
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return Reply(value, "fake-model", {"total_token_count": 1})


def test_repair_cannot_rewrite_source(make_extractor, example, item):
    wrong = generation_payload(example)
    wrong["requirement"]["source"] = copy.deepcopy(item["source"])
    wrong["requirement"]["source"]["content"][0]["text"] = "Changed"
    client = SequenceClient([canonical(wrong), canonical(generation_payload(example))])
    results, metadata = asyncio.run(make_extractor(client).run([item]))
    assert results[0]["error"] is None
    assert results[0]["blueprint"]["requirement"]["source"] == item["source"]
    assert metadata[0]["requests"] == client.calls == 2
    assert "VALIDATION_ERRORS" in client.prompts[-1]


def test_request_budget_includes_json_repairs(make_extractor, item):
    client = SequenceClient(['{"truncated":', "{}", "{}", "{}"])
    results, metadata = asyncio.run(make_extractor(client).run([item]))
    assert results[0]["error"]["code"] == "BLUEPRINT_INVALID"
    assert metadata[0]["requests"] == client.calls == 3


def test_auth_error_is_not_retried(make_extractor, item):
    client = SequenceClient([ProviderError("API_AUTH", "Denied")])
    results, metadata = asyncio.run(make_extractor(client).run([item]))
    assert results[0]["error"]["code"] == "API_AUTH"
    assert metadata[0]["requests"] == 1


def test_temporary_error_retries_in_same_budget(make_extractor, item, example):
    client = SequenceClient(
        [
            ProviderError("API_REQUEST", "Busy", retryable=True),
            canonical(generation_payload(example)),
        ]
    )
    results, metadata = asyncio.run(make_extractor(client).run([item]))
    assert results[0]["blueprint"] is not None
    assert metadata[0]["requests"] == 2


def test_invalid_item_does_not_call_ai(make_extractor):
    client = SequenceClient([])
    results, metadata = asyncio.run(make_extractor(client).run([{"source": {}}]))
    assert results[0]["error"]["code"] == "ITEM_INPUT_INVALID"
    assert metadata[0]["requests"] == 0


def test_truncated_provider_output_uses_compact_repair(make_extractor, item, example):
    client = SequenceClient(
        [
            ProviderError("AI_TRUNCATED", "Truncated", retryable=True),
            canonical(generation_payload(example)),
        ]
    )
    results, metadata = asyncio.run(make_extractor(client).run([item]))
    assert results[0]["blueprint"] is not None
    assert metadata[0]["requests"] == 2
    assert "AI_TRUNCATED" in client.prompts[-1]
    assert "VALIDATION_ERRORS" in client.prompts[-1]


def test_concurrency_order_and_timeout(make_extractor, example, item):
    payload = canonical(generation_payload(example))

    class Delayed:
        active = 0
        maximum = 0

        async def generate(self, **kwargs):
            self.active += 1
            self.maximum = max(self.active, self.maximum)
            try:
                await asyncio.sleep(
                    0.2 if kwargs["item"]["source"]["question_id"] == "q_slow" else 0.001
                )
                return Reply(payload)
            finally:
                self.active -= 1

    items = [copy.deepcopy(item) for _ in range(3)]
    for question, qid in zip(items, ["q_slow", "q_fast", "q_third"], strict=True):
        question["source"]["question_id"] = qid
    client = Delayed()
    results, metadata = asyncio.run(
        make_extractor(client, concurrency=2, item_timeout_seconds=0.05).run(items)
    )
    assert [r["question_id"] for r in results] == ["q_slow", "q_fast", "q_third"]
    assert results[0]["error"]["code"] == "ITEM_TIMEOUT"
    assert results[1]["error"] is None and results[2]["error"] is None
    assert client.maximum == 2

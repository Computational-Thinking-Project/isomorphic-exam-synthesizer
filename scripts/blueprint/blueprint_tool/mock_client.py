"""Replay a reviewed example, never pretend to extract arbitrary mock questions."""

from .ai_client import ProviderError, Reply
from .common import ROOT, canonical, load_json
from .schema_adapter import generation_payload


class MockClient:
    def __init__(self, examples=None):
        self.examples = examples or [
            load_json(path) for path in sorted((ROOT / "docs/blueprints/examples").glob("*.json"))
        ]

    async def generate(self, *, item, prompt, system, api_schema):
        expected = {key: value for key, value in item["source"].items() if key != "question_id"}
        for example in self.examples:
            actual = {
                key: value
                for key, value in example["requirement"]["source"].items()
                if key != "question_id"
            }
            if canonical(expected) == canonical(actual):
                return Reply(canonical(generation_payload(example)), "mock-reviewed-example")
        raise ProviderError(
            "MOCK_NO_FIXTURE", "Mock chỉ replay câu có fixture khớp nội dung nguồn."
        )

    async def close(self):
        pass

import json

import pytest

from app.models.schemas import GeneratedVariant
from app.services.ai.schema_repair import (
    SchemaRepairFailedError,
    extract_json_str,
    repair_json_output,
)


def test_extract_json_str_with_markdown_fences():
    """Kiểm tra trích xuất JSON khi AI bọc trong markdown code fence."""
    raw = """```json
    {
      "variant_id": "v1",
      "source_question_id": "q1",
      "question_text": "Giải pt $x^2=4$?",
      "options": ["2", "-2", "0", "4"],
      "correct_answer": "2",
      "solution_steps": "$x = \\pm 2$"
    }
    ```"""
    cleaned = extract_json_str(raw)
    assert cleaned.startswith("{")
    assert cleaned.endswith("}")

    data = json.loads(cleaned)
    variant = GeneratedVariant(**data)
    assert variant.variant_id == "v1"


def test_heuristic_repair_success():
    """Kiểm tra trường hợp bọc markdown fence được tự sửa ở bước Heuristic mà chưa cần gọi AI."""
    raw = """Dưới đây là kết quả của bạn:
```json
{
  "variant_id": "var_auto_01",
  "source_question_id": "q10",
  "question_text": "Tìm $x$ biết $2x = 6$?",
  "options": ["1", "2", "3", "4"],
  "correct_answer": "3",
  "solution_steps": "$x = 3$",
  "seed": 99
}
```
Chúc bạn học tốt!"""

    variant = repair_json_output(
        raw_text=raw,
        error_details="Extra text outside JSON",
        target_schema=GeneratedVariant,
        max_attempts=2
    )

    assert isinstance(variant, GeneratedVariant)
    assert variant.variant_id == "var_auto_01"
    assert variant.correct_answer == "3"


class MockRepairAIClient:
    """Mock client giả lập Gemini sửa lỗi thành công ở lượt 1."""
    def __init__(self, fixed_data: dict):
        self.fixed_data = fixed_data
        self.call_count = 0

    def repair_response(self, text: str) -> str:
        self.call_count += 1
        return json.dumps(self.fixed_data)


def test_ai_repair_loop_success():
    """Kiểm tra vòng lặp AI repair khi JSON hỏng cú pháp hoàn toàn."""
    broken_json = '{"variant_id": "v2", "source_question_id": "q2", options: [broken'

    fixed_data = {
        "variant_id": "v2_repaired",
        "source_question_id": "q2",
        "question_text": "Tính $1+1=2$?",
        "options": ["1", "2", "3", "4"],
        "correct_answer": "2",
        "solution_steps": "1 + 1 = 2",
        "seed": 10
    }
    mock_ai = MockRepairAIClient(fixed_data=fixed_data)

    variant = repair_json_output(
        raw_text=broken_json,
        error_details="JSONDecodeError: Expecting property name enclosed in double quotes",
        target_schema=GeneratedVariant,
        ai_client=mock_ai,
        max_attempts=2
    )

    assert isinstance(variant, GeneratedVariant)
    assert variant.variant_id == "v2_repaired"
    assert mock_ai.call_count == 1


def test_repair_exceed_max_attempts_raises_error():
    """Kiểm tra khi vượt quá số lần thử tối đa (2 lần) thì ném SchemaRepairFailedError."""
    broken_json = "VĂN BẢN KHÔNG PHẢI LÀ JSON"

    with pytest.raises(SchemaRepairFailedError) as exc_info:
        repair_json_output(
            raw_text=broken_json,
            error_details="No JSON object could be decoded",
            target_schema=GeneratedVariant,
            ai_client=None,  # Không có client để cứu
            max_attempts=2
        )

    assert "Schema Repair thất bại" in str(exc_info.value)

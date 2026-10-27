import json
import logging
import re
from typing import Any, Optional, Type, TypeVar

from google.genai import types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class SchemaRepairFailedError(Exception):
    """Ném ra khi việc sửa lỗi JSON/Schema thất bại sau số lần thử tối đa."""
    pass


def sanitize_latex_backslashes(json_str: str) -> str:
    """Tự động sửa các ký tự escape LaTeX phổ biến (như \\pm, \\sqrt, \\dfrac) không hợp lệ trong cú pháp JSON."""
    return re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', json_str)


def extract_json_str(text: str) -> str:
    """Trích xuất chuỗi JSON thuần từ văn bản thô (loại bỏ markdown code blocks nếu có)."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return sanitize_latex_backslashes(text)


def repair_json_output(
    raw_text: str,
    error_details: str,
    target_schema: Type[T],
    ai_client: Optional[Any] = None,
    max_attempts: int = 2
) -> T:
    """
    Tự động sửa chuỗi JSON/Pydantic bị lỗi thông qua:
    1. Heuristic cleaning: Loại bỏ markdown code blocks, khoảng trắng thừa.
    2. AI-assisted repair pass: Gửi lại lỗi và chuỗi hỏng cho Gemini để tái cấu trúc JSON (tối đa max_attempts lần).

    :param raw_text: Chuỗi văn bản thô AI trả về bị lỗi
    :param error_details: Chi tiết lỗi (ValidationError hoặc JSONDecodeError)
    :param target_schema: Lớp Pydantic model đích cần parse
    :param ai_client: Đối tượng GeminiClient hoặc MockClient để thực hiện cuộc gọi repair
    :param max_attempts: Số lượt repair tối đa (mặc định: 2)
    :return: Đối tượng Pydantic đã được sửa hợp lệ
    :raises SchemaRepairFailedError: Khi không thể sửa sau số lần thử tối đa
    """
    logger.warning("Bắt đầu quy trình Schema Repair Pass. Lỗi ban đầu: %s", error_details)

    # Bước 1: Thử làm sạch cơ bản (Heuristic repair)
    cleaned_text = extract_json_str(raw_text)
    try:
        data = json.loads(cleaned_text)
        return target_schema(**data)
    except Exception as e:
        logger.info("Heuristic repair không đủ, tiến hành gọi AI repair: %s", e)

    # Bước 2: AI-Assisted Repair Loop (tối đa max_attempts lượt)
    current_text = cleaned_text
    current_error = str(error_details)

    for attempt in range(1, max_attempts + 1):
        logger.info("Thực hiện AI Repair lượt %d/%d", attempt, max_attempts)

        repair_prompt = f"""Dưới đây là một phản hồi JSON bị lỗi khi parse vào Pydantic model `{target_schema.__name__}`:

[NỘI DUNG GẶP LỖI]
{current_text}

[CHI TIẾT LỖI GẶP PHẢI]
{current_error}

YÊU CẦU:
1. Hãy sửa lại chuỗi trên thành MỘT chuỗi JSON hợp lệ 100%, thỏa mãn đầy đủ các trường của `{target_schema.__name__}`.
2. Tuyệt đối giữ nguyên giá trị toán học, câu hỏi, các phương án và lời giải; chỉ sửa cấu trúc và định dạng cú pháp JSON.
3. Chỉ trả về duy nhất chuỗi JSON hợp lệ, không kèm văn bản giải thích.
"""

        try:
            if ai_client is not None and hasattr(ai_client, "client"):
                # Gọi qua SDK chính thức của GeminiClient
                config = types.GenerateContentConfig(
                    system_instruction="Bạn là chuyên gia sửa lỗi cú pháp JSON và Pydantic schema validation.",
                    response_mime_type="application/json",
                    response_schema=target_schema,
                )
                if callable(getattr(ai_client, "generate_content", None)):
                    response = ai_client.generate_content(contents=repair_prompt, config=config)
                else:
                    response = ai_client.client.models.generate_content(
                        model=ai_client.model_name,
                        contents=repair_prompt,
                        config=config,
                    )
                repaired_raw = extract_json_str(response.text or "")
                data = json.loads(repaired_raw)
                repaired_obj = target_schema(**data)
                logger.info("AI Repair thành công ở lượt %d!", attempt)
                return repaired_obj

            elif ai_client is not None and hasattr(ai_client, "repair_response"):
                # Dành cho MockClient trong unit test
                repaired_raw = ai_client.repair_response(current_text)
                data = json.loads(extract_json_str(repaired_raw))
                return target_schema(**data)

            else:
                # Không có client để gọi repair
                break

        except Exception as repair_exc:
            current_error = str(repair_exc)
            logger.warning("Lượt repair %d thất bại: %s", attempt, current_error)

    raise SchemaRepairFailedError(
        f"Schema Repair thất bại sau {max_attempts} lượt thử. Lỗi cuối cùng: {current_error}"
    )

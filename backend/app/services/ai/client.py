import html
import json
import logging
import re
import secrets
import time
import unicodedata
from typing import Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.models.schemas import GeneratedVariant, SourceQuestion
from app.services.ai.mock_client import BaseAIClient
from app.services.ai.schema_repair import repair_json_output

logger = logging.getLogger(__name__)

# Pattern quét các chỉ thị prompt injection độc hại (SEC-02)
SUSPICIOUS_PROMPT_PATTERNS = re.compile(
    r"(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+(all\s+)?(previous|above)|you\s+are\s+now|system\s+prompt|dan\s+mode|override\s+instructions)"
)


def detect_prompt_injection(text: str) -> bool:
    """Quét phát hiện các mẫu chỉ thị độc hại hoặc prompt injection (SEC-02)."""
    if not text:
        return False
    return bool(SUSPICIOUS_PROMPT_PATTERNS.search(text))


def sanitize_and_escape_text(text: str, max_length: int = 2000) -> str:
    """Chuẩn hóa Unicode NFC, giới hạn độ dài và escape ký tự XML để chống thoát thẻ (SEC-02)."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)[:max_length]
    return html.escape(normalized, quote=True)


DEFAULT_SYSTEM_INSTRUCTION = """Bạn là một chuyên gia toán học và khảo thí giáo dục chuyên sâu về sinh đề thi toán đẳng cấu (Isomorphic Math Problem Generation - IMPG).
Nhiệm vụ của bạn:
1. Nhận một câu hỏi toán học trắc nghiệm nguồn (gồm đề bài, các lựa chọn, đáp án đúng và lời giải).
2. Sinh ra MỘT biến thể đẳng cấu mới:
   - Giữ nguyên cấu trúc logic, phương pháp giải và mức độ tư duy của bài toán gốc.
   - Thay đổi các hệ số số học một cách hợp lý để tạo ra bài toán mới.
   - Đảm bảo nghiệm toán học là số đẹp, không có mẫu số bằng 0, không vi phạm miền xác định.
   - Sinh chính xác 4 phương án trả lời khác nhau (A, B, C, D), trong đó có 1 đáp án đúng và 3 phương án gây nhiễu hợp lý.
   - Cung cấp lời giải chi tiết từng bước bằng LaTeX chuẩn ($...$ hoặc $$...$$).
   - Đáp án đúng (correct_answer) bắt buộc phải khớp chính xác với 1 trong 4 lựa chọn trong options.
3. Luôn trả về dữ liệu đúng định dạng JSON khớp với cấu trúc GeneratedVariant được yêu cầu.
"""


class GeminiClient(BaseAIClient):
    """Client tích hợp Google Gemini API chính thức sử dụng google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        max_retries: int = 3
    ):
        """
        Khởi tạo GeminiClient.
        :param api_key: Khóa API (mặc định lấy từ settings.GEMINI_API_KEY)
        :param model_name: Tên model Gemini (mặc định lấy từ settings.GEMINI_MODEL)
        :param max_retries: Số lần thử lại tối đa khi gặp lỗi tạm thời (429, 503)
        """
        api_keys = [api_key] if api_key else settings.get_gemini_api_keys()
        if not api_keys:
            raise ValueError(
                "Chưa cấu hình Gemini API key. Điền GEMINI_API_KEY hoặc GEMINI_API_KEY_1..3 vào .env."
            )

        self.model_name = model_name or settings.GEMINI_MODEL
        self.max_retries = max_retries
        self._clients = tuple(
            genai.Client(
                api_key=key,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            for key in api_keys
        )
        self.client = self._clients[0]  # Compatibility for existing callers.

    def generate_content(
        self, *, contents: str, config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        """Choose a key for each actual request, including retries and repair."""
        client = secrets.choice(self._clients)
        return client.models.generate_content(
            model=self.model_name, contents=contents, config=config
        )

    def generate_variant(
        self,
        source: SourceQuestion,
        seed: Optional[int] = None,
        system_instruction: Optional[str] = None,
        feedback: Optional[str] = None
    ) -> GeneratedVariant:
        """
        Gọi Gemini sinh biến thể câu hỏi toán học với Structured Output.
        """
        instruction = system_instruction or DEFAULT_SYSTEM_INSTRUCTION

        # 1. Giám sát & Ghi vết chuỗi khả nghi (SEC-02)
        if detect_prompt_injection(source.question_text) or any(detect_prompt_injection(opt) for opt in source.options):
            source.has_security_warning = True
            logger.warning(
                "Phát hiện chuỗi khả nghi Prompt Injection trong câu hỏi ID=%s! Gắn cờ has_security_warning=True",
                source.id
            )

        # 2. Chuẩn hóa NFC và escape XML để triệt tiêu nguy cơ XML Tag Escape Injection
        escaped_q = sanitize_and_escape_text(source.question_text)
        escaped_options = [sanitize_and_escape_text(opt) for opt in source.options]
        escaped_ans = sanitize_and_escape_text(source.correct_answer)
        escaped_sol = sanitize_and_escape_text(source.solution)
        used_seed = seed if seed is not None else int(time.time())

        # 3. Đóng gói an toàn trong thẻ XML thụ động
        user_prompt = f"""Hãy sinh một biến thể toán học đẳng cấu từ câu hỏi gốc được đóng gói trong thẻ XML sau:

<source_question id="{source.id}">
  <topic>{source.topic or 'Toán học'}</topic>
  <question_text>{escaped_q}</question_text>
  <options>{json.dumps(escaped_options, ensure_ascii=False)}</options>
  <correct_answer>{escaped_ans}</correct_answer>
  <solution>{escaped_sol}</solution>
  <suggested_seed>{used_seed}</suggested_seed>
</source_question>
"""
        if feedback:
            user_prompt += f"""
[LƯU Ý / GÓP Ý ĐẶC BIỆT TỪ LẦN SINH TRƯỚC HOẶC TỪ HỆ THỐNG KIỂM TRA]
{feedback}
Vui lòng khắc phục hoàn toàn các lỗi hoặc góp ý trên khi tạo biến thể mới!
"""

        user_prompt += f"""
Yêu cầu:
- variant_id đặt theo quy tắc: var_{source.id}_s{seed or 'auto'}
- source_question_id: {source.id}
- Tạo các hệ số số học mới, giải chi tiết và đưa ra 4 phương án trắc nghiệm chuẩn LaTeX.
"""

        # Cấu hình chuẩn cho gemini-3.5-flash-lite (không dùng custom temperature)
        config = types.GenerateContentConfig(
            system_instruction=instruction,
            response_mime_type="application/json",
            response_schema=GeneratedVariant,
        )

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "Gọi Gemini API model=%s (lần thử %d/%d) cho câu hỏi %s",
                    self.model_name, attempt, self.max_retries, source.id
                )
                response = self.generate_content(
                    contents=user_prompt,
                    config=config,
                )

                # Parse JSON từ response của Gemini
                raw_text = response.text or ""
                if not raw_text:
                    raise ValueError("Gemini API trả về phản hồi rỗng.")
                try:
                    variant_data = json.loads(raw_text)
                    return GeneratedVariant(**variant_data)
                except Exception as parse_err:
                    logger.warning(
                        "Parse thô thất bại (%s), kích hoạt Schema Repair Pass tự động...",
                        parse_err
                    )
                    return repair_json_output(
                        raw_text=raw_text,
                        error_details=str(parse_err),
                        target_schema=GeneratedVariant,
                        ai_client=self,
                    )

            except Exception as e:
                last_error = e
                err_msg = str(e)
                logger.warning(
                    "Lỗi khi gọi Gemini (lần %d/%d): %s",
                    attempt, self.max_retries, err_msg
                )
                # Retry nếu là lỗi Rate limit hoặc quá tải tạm thời
                if attempt < self.max_retries and ("429" in err_msg or "503" in err_msg or "ResourceExhausted" in err_msg):
                    backoff = 2 ** attempt
                    time.sleep(backoff)
                else:
                    break

        raise RuntimeError(
            f"Không thể sinh biến thể từ Gemini sau {self.max_retries} lần thử: {last_error}"
        )

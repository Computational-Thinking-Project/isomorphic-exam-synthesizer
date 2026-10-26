"""One SDK request per call; retry budget belongs to the extractor."""

from dataclasses import dataclass, field

from .common import ToolError


class ProviderError(ToolError):
    def __init__(self, code, message, *, retryable=False, http_status=None):
        super().__init__(code, message, [{"http_status": http_status}] if http_status else [])
        self.retryable = retryable


@dataclass
class Reply:
    text: str
    model_version: str | None = None
    tokens: dict = field(default_factory=dict)


class GeminiClient:
    def __init__(self, config, api_key):
        from google import genai
        from google.genai import types

        self.config = config
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(config.request_timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    async def generate(self, *, item, prompt, system, api_schema):
        from google.genai import errors, types

        try:
            response = await self.client.aio.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=api_schema,
                    max_output_tokens=self.config.max_output_tokens,
                ),
            )
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            code = int(code) if str(code).isdigit() else None
            if code in {401, 403}:
                raise ProviderError(
                    "API_AUTH",
                    "Gemini từ chối quyền truy cập; kiểm tra key và quyền model.",
                    http_status=code,
                ) from None
            if code == 404:
                raise ProviderError(
                    "API_MODEL",
                    "Không tìm thấy model hoặc tài nguyên Gemini được yêu cầu.",
                    http_status=code,
                ) from None
            raise ProviderError(
                "API_REQUEST",
                "Gemini API không hoàn tất request.",
                retryable=code in {408, 429, 500, 502, 503, 504},
                http_status=code,
            ) from None
        except Exception as exc:
            # Never serialize SDK/transport exceptions: they can contain credential URLs.
            import httpx

            if isinstance(exc, (httpx.TransportError, OSError)):
                raise ProviderError(
                    "API_TRANSPORT", "Không kết nối được Gemini API.", retryable=True
                ) from None
            raise ProviderError(
                "API_CLIENT", "SDK không hoàn tất request; kiểm tra cấu hình SDK."
            ) from None
        return reply_from_response(response)

    async def close(self):
        await self.client.aio.aclose()
        self.client.close()


def reply_from_response(response):
    """Interpret SDK output identically in the CLI and shared backend gateway."""
    candidates = response.candidates or []
    if not candidates:
        raise ProviderError("AI_BLOCKED", "Gemini không trả nội dung để trích xuất blueprint.")
    reason = getattr(candidates[0].finish_reason, "value", candidates[0].finish_reason)
    if reason == "MAX_TOKENS":
        raise ProviderError("AI_TRUNCATED", "Output bị cắt ở giới hạn token.", retryable=True)
    if reason not in {None, "STOP"}:
        raise ProviderError("AI_BLOCKED", "Gemini dừng sinh trước khi hoàn tất JSON.")
    usage = response.usage_metadata
    tokens = (
        {
            name: getattr(usage, name, None)
            for name in (
                "prompt_token_count",
                "candidates_token_count",
                "thoughts_token_count",
                "total_token_count",
            )
        }
        if usage
        else {}
    )
    return Reply(response.text or "", getattr(response, "model_version", None), tokens)

"""Bounded, strict parsing with the existing LaTeX/Markdown cleanup heuristic."""

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.services.ai.schema_repair import extract_json_str
from app.services.blueprint.common import MAX_RESPONSE_BYTES, ToolError, strict_json

T = TypeVar("T", bound=BaseModel)


def parse_model_output(text: str, model: type[T]) -> T:
    if len(text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ToolError("AI_OUTPUT_TOO_LARGE", "Output AI vượt giới hạn kích thước.")
    try:
        data = strict_json(text)
    except ToolError as exc:
        if exc.code != "INVALID_JSON":
            raise
        # Same heuristic as the legacy schema repair; still reject duplicate keys/nonfinite JSON.
        data = strict_json(extract_json_str(text))
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        details = [
            {"rule": error["type"], "pointer": "/".join(str(p) for p in error["loc"])}
            for error in exc.errors(include_input=False, include_context=False)[:24]
        ]
        raise ToolError("AI_SCHEMA_INVALID", "Output không thỏa contract.", details) from None

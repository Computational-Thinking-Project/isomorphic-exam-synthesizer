"""Lossless source mapping and the application's four-option mathematics profile."""

import hashlib
import unicodedata
from typing import Any

from app.models.schemas import SourceQuestion
from app.services.validator.logic_checker import normalize_latex_string

from .common import ToolError
from .validators import language_hint, validate_blueprint, validate_input


def normalized_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", normalize_latex_string(text)).split())


def resolve_answer_key(answer: str, options: list[str]) -> str:
    """Resolve a legacy key or exact normalized content; never guess on ambiguity."""
    if len(options) != 4 or any(not option.strip() for option in options):
        raise ToolError("SOURCE_OPTIONS_INVALID", "Cần đúng bốn phương án có nội dung.")
    normalized = [normalized_text(option) for option in options]
    if len(set(normalized)) != 4:
        raise ToolError("SOURCE_OPTIONS_INVALID", "Phương án nguồn bị trùng.")
    matches = [index for index, option in enumerate(normalized) if option == normalized_text(answer)]
    key = answer.strip()
    if key in "ABCD" and len(key) == 1:
        index = "ABCD".index(key)
        if matches and matches != [index]:
            raise ToolError("SOURCE_ANSWER_AMBIGUOUS", "Key và nội dung đáp án nguồn mâu thuẫn.")
        return key
    if len(matches) != 1:
        raise ToolError("SOURCE_ANSWER_INVALID", "Không ánh xạ duy nhất được đáp án nguồn.")
    return "ABCD"[matches[0]]


def source_to_item(source: SourceQuestion) -> dict[str, Any]:
    key = resolve_answer_key(source.correct_answer, source.options)
    # DB UUIDs may start with a digit; canonical Blueprint IDs must start with a letter.
    qid = "q_" + hashlib.sha256(source.id.encode("utf-8")).hexdigest()[:24]
    canonical_source = {
        "question_id": qid,
        "content": [{"id": qid + ".stem", "type": "text", "text": source.question_text}],
        "options": [
            {"id": qid + "." + letter,
             "content": [{"id": qid + "." + letter + ".text", "type": "text", "text": text}]}
            for letter, text in zip("ABCD", source.options, strict=True)
        ],
        "supplied_answer": {"option_ids": [qid + "." + key], "value": None, "explanation": None},
        "supplied_solution": (
            [{"id": qid + ".solution", "type": "text", "text": source.solution}]
            if source.solution.strip() else None
        ),
        "references": [],
    }
    return {
        "source": canonical_source,
        "context": {"subject": "mathematics", "language": language_hint(canonical_source) or "vi"},
    }


def prepare_sources(sources: list[SourceQuestion]) -> list[dict[str, Any]]:
    if not 1 <= len(sources) <= 20 or len({source.id for source in sources}) != len(sources):
        raise ToolError("SOURCE_BATCH_INVALID", "Cần 1–20 câu nguồn có ID duy nhất.")
    return [source_to_item(source) for source in sources]


def validate_math_blueprint(blueprint: dict[str, Any], item: dict[str, Any], contracts, schema) -> None:
    validate_input(item, contracts.single, contracts.registry)
    issues = validate_blueprint(blueprint, schema, item["source"], item["context"])
    if issues:
        raise ToolError("BLUEPRINT_INVALID", "Blueprint không khớp nguồn hoặc contract.", issues)
    response = blueprint["requirement"]["response_spec"]
    if (
        blueprint["requirement"]["subject"] != "mathematics"
        or response["format"] != "single_choice"
        or response["option_count"] != 4
        or response["correct_option_count"] != 1
    ):
        raise ToolError("BLUEPRINT_PROFILE_INVALID", "Ứng dụng yêu cầu Toán, bốn options, một đáp án.")
    computed = blueprint["constraint"]["source_check"]["computed_answer"]
    supplied = item["source"]["supplied_answer"]["option_ids"]
    if computed and computed["option_ids"] and computed["option_ids"] != supplied:
        # Detect a declared contradiction; this does not prove which answer is right.
        raise ToolError("BLUEPRINT_SOURCE_ANSWER_CONFLICT", "Blueprint và đáp án nguồn mâu thuẫn; cần rà soát nguồn.")

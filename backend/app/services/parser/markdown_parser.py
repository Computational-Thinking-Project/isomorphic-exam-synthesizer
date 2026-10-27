"""Markdown Ingestion Parser (TASK-202).

Handles:
- Parsing Markdown exam files (.md) and direct text input
- Markdown headers ("### Câu X:", "**Câu X:**", "Câu X:")
- 4 options A, B, C, D (list items "- A. ...", "* A. ...", or inline)
- Inline and block LaTeX math formulas ($...$, $$...$$)
- Separate answer key mapping
- Prompt injection detection (SEC-02) and Unicode NFC normalization
"""

import logging
import re
from typing import Any, Dict, List, Tuple

from app.models.schemas import ParsedQuestionItem, ParserErrorItem
from app.services.parser.utils import (
    RawAnswerKeyInfo,
    check_prompt_injection,
    extract_options_from_text,
    mask_markdown_code_blocks,
    normalize_unicode_nfc,
    parse_separate_answer_key,
)

logger = logging.getLogger(__name__)

MD_QUESTION_HEADER = re.compile(
    r"(?:^|\n)(?:#{1,6}\s*|\*{1,2}|_{1,2})?(?:câu|bài)\s+(?P<num>\d+)(?:\*{1,2}|_{1,2})?\s*[\.:\-](?:\*{1,2}|_{1,2})?\s*",
    re.IGNORECASE,
)


def parse_markdown(raw_content: str) -> Tuple[List[ParsedQuestionItem], List[ParserErrorItem]]:
    """Parse raw Markdown exam text and return parsed questions and errors.

    Guarantees:
    - Code fences (```...```) and inline code are masked across the entire pipeline
      so code snippets containing question headers or option markers never distort exam structure.
    - True empty question stems are detected (is_empty_stem) without being masked by option fallback.
    - Captures conflicting answer keys from the answer section.
    """
    text = normalize_unicode_nfc(raw_content)

    # 1. Mask code blocks across the pipeline (preserves 100% exact character length and newlines)
    masked_text = mask_markdown_code_blocks(text)

    # 2. Parse separate answer table at the end
    answer_map, masked_without_keys, key_info = parse_separate_answer_key(
        masked_text, return_info=True
    )
    cutoff_len = len(masked_without_keys)
    text_without_keys = text[:cutoff_len]

    # 3. Segment text by question headers on masked text, slicing original unmasked text
    matches = list(MD_QUESTION_HEADER.finditer(masked_without_keys))
    questions_raw: List[Dict[str, Any]] = []

    if matches:
        for idx, m in enumerate(matches):
            q_no = int(m.group("num"))
            start_pos = m.end()
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(text_without_keys)
            q_body = text_without_keys[start_pos:end_pos].strip()
            questions_raw.append({"question_no": q_no, "text": q_body})
    else:
        # Fallback: check if numbered like "1.", "2."
        numbered_matches = list(re.finditer(r"(?:^|\n)(?P<num>\d+)\.\s+", masked_without_keys))
        if numbered_matches:
            for idx, m in enumerate(numbered_matches):
                q_no = int(m.group("num"))
                start_pos = m.end()
                end_pos = (
                    numbered_matches[idx + 1].start()
                    if idx + 1 < len(numbered_matches)
                    else len(text_without_keys)
                )
                q_body = text_without_keys[start_pos:end_pos].strip()
                questions_raw.append({"question_no": q_no, "text": q_body})

    # 4. Process each question
    parsed_questions: List[ParsedQuestionItem] = []
    errors: List[ParserErrorItem] = []

    # Record any conflicting answer keys found in the answer section
    for conf_q, conf_keys in key_info.conflicts.items():
        errors.append(
            ParserErrorItem(
                question_no=conf_q,
                error_type="CONFLICTING_ANSWER_KEY",
                message=f"Question {conf_q} has conflicting answer keys in answer section: {conf_keys}",
            )
        )

    for q_data in questions_raw:
        q_no = q_data["question_no"]
        q_text = q_data["text"]

        stem, options, inline_key = extract_options_from_text(q_text)

        # If options not found by standard extractor, try bullet list formats:
        # - A. ... or * A. ...
        if len(options) < 4:
            bullet_opts = re.findall(
                r"(?:^|\n)\s*[\-\*]\s*(?P<opt>[A-D])\s*[\.\)]\s*(?P<content>.*?)(?=(?:\n\s*[\-\*]\s*[A-D]\s*[\.\)]|$))",
                q_text,
                re.DOTALL,
            )
            if len(bullet_opts) == 4:
                options = {b[0].upper(): b[1].strip() for b in bullet_opts}
                first_bullet = re.search(r"(?:^|\n)\s*[\-\*]\s*[A-D]\s*[\.\)]", q_text)
                if first_bullet:
                    stem = q_text[: first_bullet.start()].strip()

        # Check for empty stem
        is_empty_stem = not bool(stem.strip())
        if is_empty_stem:
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="EMPTY_STEM",
                    message=f"Question {q_no} has an empty question stem (no prompt text).",
                )
            )

        correct_key = answer_map.get(q_no) or inline_key or ""
        has_missing_answer = False
        if not correct_key or correct_key.upper() not in {"A", "B", "C", "D"}:
            has_missing_answer = True
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="MISSING_ANSWER",
                    message=f"Question {q_no} has no valid correct answer key identified.",
                )
            )

        if (
            len(options) != 4
            or not all(k in options for k in ["A", "B", "C", "D"])
            or any(not (options.get(k) or "").strip() for k in ["A", "B", "C", "D"])
        ):
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="INVALID_FORMAT",
                    message=f"Question {q_no} is missing one or more options or contains empty option content (A, B, C, D required).",
                )
            )

        has_sec_warning = check_prompt_injection(q_text)

        parsed_questions.append(
            ParsedQuestionItem(
                question_no=q_no,
                raw_content=stem,
                options=options,
                correct_key=correct_key if not has_missing_answer else "",
                solution_md=None,
                has_missing_answer=has_missing_answer,
                has_unparsed_omml=False,
                has_unparsed_image=False,
                is_empty_stem=is_empty_stem,
                has_security_warning=has_sec_warning,
            )
        )

    return parsed_questions, errors

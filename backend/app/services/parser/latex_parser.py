r"""LaTeX Ingestion Parser (TASK-202).

Handles:
- Parsing LaTeX exam files (.tex) and environments:
  \begin{enumerate} ... \item ... \end{enumerate} or "Câu X:"
- Extracting 4 options A, B, C, D (\item[A.], \task, or standard format)
- Preserving 100% of math expressions ($...$, $$...$$, \[...\])
- Separate answer key parsing
- Prompt injection detection (SEC-02) and Unicode NFC normalization
"""

import logging
import re
from typing import Any, Dict, List, Tuple

from app.models.schemas import ParsedQuestionItem, ParserErrorItem
from app.services.parser.utils import (
    check_prompt_injection,
    extract_options_from_text,
    normalize_unicode_nfc,
    parse_separate_answer_key,
)

logger = logging.getLogger(__name__)

# Regex for LaTeX item matching
LATEX_ITEM_PATTERN = re.compile(r"\\item(?:\[(?P<label>[^\]]+)\])?\s*", re.DOTALL)
LATEX_QUESTION_HEADER = re.compile(
    r"(?:\\textbf\{\s*(?:câu|bài)\s+(?P<num1>\d+)[\.:\-]?\s*\}|(?:câu|bài)\s+(?P<num2>\d+)\s*[\.:\-])",
    re.IGNORECASE,
)


def parse_latex(raw_content: str) -> Tuple[List[ParsedQuestionItem], List[ParserErrorItem]]:
    """Parse raw LaTeX exam text and return parsed questions and errors."""
    text = normalize_unicode_nfc(raw_content)

    # 1. Parse separate answer table
    answer_map, text_without_keys = parse_separate_answer_key(text)

    # 2. Strategy A: Check for enumerate environment
    questions_raw: List[Dict[str, Any]] = []

    # Look for \begin{enumerate} blocks
    enum_match = re.search(
        r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", text_without_keys, re.DOTALL
    )
    if enum_match:
        enum_body = enum_match.group(1)
        # Split by \item
        items = re.split(r"\\item(?![a-zA-Z])", enum_body)
        q_counter = 1
        for item in items:
            item_text = item.strip()
            if not item_text:
                continue

            # Check if there is an explicit label like [Câu 1:]
            lbl_match = re.match(r"^\[(.*?)\]", item_text)
            if lbl_match:
                lbl = lbl_match.group(1)
                item_text = item_text[lbl_match.end() :].strip()
                num_match = re.search(r"\d+", lbl)
                q_no = int(num_match.group(0)) if num_match else q_counter
            else:
                q_no = q_counter

            questions_raw.append({"question_no": q_no, "text": item_text})
            q_counter += 1

    # Strategy B: If no enumerate or few items found, segment by "Câu X:" or "\textbf{Câu X:}"
    if not questions_raw:
        # Split by question header
        matches = list(LATEX_QUESTION_HEADER.finditer(text_without_keys))
        if matches:
            for idx, m in enumerate(matches):
                q_no = int(m.group("num1") or m.group("num2"))
                start_pos = m.end()
                end_pos = (
                    matches[idx + 1].start() if idx + 1 < len(matches) else len(text_without_keys)
                )
                q_body = text_without_keys[start_pos:end_pos].strip()
                questions_raw.append({"question_no": q_no, "text": q_body})

    # 3. Process question items
    parsed_questions: List[ParsedQuestionItem] = []
    errors: List[ParserErrorItem] = []

    for q_data in questions_raw:
        q_no = q_data["question_no"]
        q_text = q_data["text"]

        stem, options, inline_key = extract_options_from_text(q_text)

        # If options not found by standard extractor, try LaTeX \task or \item[A.] format
        if len(options) < 4:
            task_opts = re.findall(
                r"(?:\\task|\\item\[([A-D])[\.\)]?\])\s*(.*?)(?=(?:\\task|\\item\[[A-D][\.\)]?\])|$)",
                q_text,
                re.DOTALL,
            )
            if len(task_opts) == 4:
                labels = ["A", "B", "C", "D"]
                options = {}
                for idx, t in enumerate(task_opts):
                    opt_lbl = t[0].upper() if t[0] else labels[idx]
                    options[opt_lbl] = t[1].strip()

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

        if len(options) != 4 or not all(k in options for k in ["A", "B", "C", "D"]):
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="INVALID_FORMAT",
                    message=f"Question {q_no} does not contain all 4 options A, B, C, D.",
                )
            )

        has_sec_warning = check_prompt_injection(q_text)

        parsed_questions.append(
            ParsedQuestionItem(
                question_no=q_no,
                raw_content=stem if stem else q_text,
                options=options,
                correct_key=correct_key if not has_missing_answer else "",
                solution_md=None,
                has_missing_answer=has_missing_answer,
                has_unparsed_omml=False,
                has_security_warning=has_sec_warning,
            )
        )

    return parsed_questions, errors

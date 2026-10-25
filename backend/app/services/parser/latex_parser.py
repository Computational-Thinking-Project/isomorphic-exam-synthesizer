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
from typing import Any, Dict, List, Optional, Tuple

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


def find_outer_latex_environments(text: str, env_name: str = "enumerate") -> List[str]:
    """Find top-level LaTeX environment bodies by balancing \\begin and \\end tags."""
    begin_tag = f"\\begin{{{env_name}}}"
    end_tag = f"\\end{{{env_name}}}"
    results: List[str] = []

    pos = 0
    while pos < len(text):
        start = text.find(begin_tag, pos)
        if start == -1:
            break

        depth = 1
        idx = start + len(begin_tag)
        while depth > 0 and idx < len(text):
            next_begin = text.find(begin_tag, idx)
            next_end = text.find(end_tag, idx)

            if next_end == -1:
                break

            if next_begin != -1 and next_begin < next_end:
                depth += 1
                idx = next_begin + len(begin_tag)
            else:
                depth -= 1
                if depth == 0:
                    results.append(text[start + len(begin_tag) : next_end])
                idx = next_end + len(end_tag)
        pos = idx if depth == 0 else len(text)
    return results


def split_latex_items(enum_body: str) -> List[str]:
    """Split LaTeX enumerate body into top-level question items.

    Ignores \\item inside nested environments and \\item with option labels like \\item[A.].
    """
    items: List[str] = []
    token_pattern = re.compile(r"(\\begin\{[a-zA-Z*]+\}|\\end\{[a-zA-Z*]+\}|\\item(?![a-zA-Z]))")

    tokens = list(token_pattern.finditer(enum_body))
    if not tokens:
        trimmed = enum_body.strip()
        return [trimmed] if trimmed else []

    depth = 0
    last_end = 0
    option_label_pattern = re.compile(r"^\s*\[\s*[A-Da-d][\.\)]?\s*\]")

    for match in tokens:
        tok = match.group(1)
        start = match.start()

        if tok.startswith(r"\begin"):
            depth += 1
        elif tok.startswith(r"\end"):
            depth = max(0, depth - 1)
        elif tok.startswith(r"\item") and depth == 0:
            tail = enum_body[match.end() :]
            if option_label_pattern.match(tail):
                # An option item like \item[A.], do NOT treat as question boundary
                pass
            else:
                # Top-level question \item boundary
                prev_chunk = enum_body[last_end:start].strip()
                if prev_chunk:
                    items.append(prev_chunk)
                last_end = match.end()

    final_chunk = enum_body[last_end:].strip()
    if final_chunk:
        items.append(final_chunk)

    return items


def parse_latex(raw_content: str) -> Tuple[List[ParsedQuestionItem], List[ParserErrorItem]]:
    """Parse raw LaTeX exam text and return parsed questions and errors."""
    text = normalize_unicode_nfc(raw_content)

    # 1. Parse separate answer table
    answer_map, text_without_keys = parse_separate_answer_key(text)

    # 2. Strategy A: Check for enumerate environment
    questions_raw: List[Dict[str, Any]] = []

    enum_bodies = find_outer_latex_environments(text_without_keys, "enumerate")
    q_counter = 1
    for enum_body in enum_bodies:
        items = split_latex_items(enum_body)
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

        options: Dict[str, str] = {}
        inline_key: Optional[str] = None
        stem = q_text

        # 1. Try LaTeX \task or \item[A.] format
        task_opts = re.findall(
            r"(?:\\task|\\item\[\s*([A-Da-d])[\.\)]?\s*\])\s*(.*?)(?=(?:\\task|\\item\[\s*[A-Da-d][\.\)]?\s*\])|$)",
            q_text,
            re.DOTALL,
        )
        if len(task_opts) == 4:
            labels = ["A", "B", "C", "D"]
            for idx, t in enumerate(task_opts):
                opt_lbl = t[0].upper() if t[0] else labels[idx]
                options[opt_lbl] = t[1].strip()

            first_opt_match = re.search(r"(?:\\task|\\item\[\s*[A-Da-d][\.\)]?\s*\])", q_text)
            if first_opt_match:
                stem = q_text[: first_opt_match.start()].strip()

        # 2. If not found, try nested enumerate environment
        if len(options) < 4:
            nested_enums = find_outer_latex_environments(q_text, "enumerate")
            for n_body in nested_enums:
                sub_items = [
                    it.strip() for it in re.split(r"\\item(?![a-zA-Z])", n_body) if it.strip()
                ]
                if len(sub_items) == 4:
                    labels = ["A", "B", "C", "D"]
                    options = {labels[i]: sub_items[i] for i in range(4)}
                    opt_pos = q_text.find(r"\begin{enumerate}")
                    if opt_pos != -1:
                        stem = q_text[:opt_pos].strip()
                    break

        # 3. If still not found, try standard text extractor (A. ... B. ...)
        if len(options) < 4:
            extracted_stem, extracted_opts, detected_inline_key = extract_options_from_text(q_text)
            if len(extracted_opts) == 4:
                stem = extracted_stem
                options = extracted_opts
                inline_key = detected_inline_key

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

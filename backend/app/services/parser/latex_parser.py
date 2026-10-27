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

STEM_LIST_START_PATTERN = re.compile(
    r"\\begin\{(?:enumerate|tasks|itemize|multicols)\}(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})*\s*$",
    re.IGNORECASE,
)
OPT_LIST_END_PATTERN = re.compile(
    r"\\end\{(?:enumerate|tasks|itemize|multicols)\}\s*$",
    re.IGNORECASE,
)
OPT_LIST_START_PATTERN = re.compile(
    r"^\s*\\begin\{(?:enumerate|tasks|itemize|multicols)\}(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})*",
    re.IGNORECASE,
)


def clean_latex_list_wrappers(stem: str, options: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Clean list layout environments (enumerate, tasks, itemize, multicols) from question stem and options.

    Guarantees 100% preservation of actual LaTeX math environments (matrix, pmatrix, cases, aligned, etc.).
    """
    cleaned_stem = stem.strip()
    while True:
        subbed = STEM_LIST_START_PATTERN.sub("", cleaned_stem).strip()
        if subbed == cleaned_stem:
            break
        cleaned_stem = subbed

    cleaned_options: Dict[str, str] = {}
    for key, val in options.items():
        opt_str = val.strip()
        while True:
            subbed = OPT_LIST_END_PATTERN.sub("", opt_str).strip()
            if subbed == opt_str:
                break
            opt_str = subbed
        while True:
            subbed = OPT_LIST_START_PATTERN.sub("", opt_str).strip()
            if subbed == opt_str:
                break
            opt_str = subbed
        cleaned_options[key] = opt_str

    return cleaned_stem, cleaned_options


def find_outer_latex_environment_spans(
    text: str, env_name: str = "enumerate"
) -> List[Tuple[int, int, str]]:
    """Find top-level LaTeX environment spans (start_pos, end_pos, body) by balancing \\begin and \\end tags."""
    begin_tag = f"\\begin{{{env_name}}}"
    end_tag = f"\\end{{{env_name}}}"
    spans: List[Tuple[int, int, str]] = []

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
                    spans.append(
                        (start, next_end + len(end_tag), text[start + len(begin_tag) : next_end])
                    )
                idx = next_end + len(end_tag)
        pos = idx if depth == 0 else len(text)
    return spans


def find_outer_latex_environments(text: str, env_name: str = "enumerate") -> List[str]:
    """Find top-level LaTeX environment bodies by balancing \\begin and \\end tags."""
    return [body for _, _, body in find_outer_latex_environment_spans(text, env_name)]


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

    # 2. Segment questions: distinguish between top-level question enumerate and option enumerate
    questions_raw: List[Dict[str, Any]] = []

    enum_spans = find_outer_latex_environment_spans(text_without_keys, "enumerate")
    header_matches = list(LATEX_QUESTION_HEADER.finditer(text_without_keys))

    # Detect if question headers exist outside of any top-level enumerate environment
    headers_outside_enumerate = [
        m
        for m in header_matches
        if not any(start <= m.start() < end for start, end, _ in enum_spans)
    ]

    if headers_outside_enumerate:
        # Strategy B: Document is organized by question headers (e.g. \textbf{Câu 1:}, Câu 1:).
        # Any enumerate environments inside belong to question bodies (e.g. options list).
        for idx, m in enumerate(headers_outside_enumerate):
            q_no = int(m.group("num1") or m.group("num2"))
            start_pos = m.end()
            end_pos = (
                headers_outside_enumerate[idx + 1].start()
                if idx + 1 < len(headers_outside_enumerate)
                else len(text_without_keys)
            )
            q_body = text_without_keys[start_pos:end_pos].strip()
            questions_raw.append({"question_no": q_no, "text": q_body})
    elif enum_spans:
        # Strategy A: Document is organized as top-level enumerate question list
        q_counter = 1
        for _, _, enum_body in enum_spans:
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
    elif header_matches:
        # Fallback: Split by any question header
        for idx, m in enumerate(header_matches):
            q_no = int(m.group("num1") or m.group("num2"))
            start_pos = m.end()
            end_pos = (
                header_matches[idx + 1].start()
                if idx + 1 < len(header_matches)
                else len(text_without_keys)
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
            r"(?:\\task|\\item\[\s*\(?([A-Da-d])\)?[\.\)]?\s*\])\s*(.*?)(?=(?:\\task|\\item\[\s*\(?[A-Da-d]\)?[\.\)]?\s*\])|$)",
            q_text,
            re.DOTALL,
        )
        if len(task_opts) == 4:
            labels = ["A", "B", "C", "D"]
            for idx, t in enumerate(task_opts):
                opt_lbl = t[0].upper() if t[0] else labels[idx]
                options[opt_lbl] = t[1].strip()

            first_opt_match = re.search(
                r"(?:\\task|\\item\[\s*\(?[A-Da-d]\)?[\.\)]?\s*\])", q_text
            )
            if first_opt_match:
                stem = q_text[: first_opt_match.start()].strip()

        # 2. If not found, try nested enumerate environment
        if len(options) < 4:
            nested_enums = find_outer_latex_environments(q_text, "enumerate")
            for n_body in nested_enums:
                # Discard optional parameter before first \item (e.g. [(A)] or [label=...])
                first_item_match = re.search(r"\\item(?![a-zA-Z])", n_body)
                if first_item_match:
                    items_body = n_body[first_item_match.end() :]
                    sub_items = [
                        it.strip()
                        for it in re.split(r"\\item(?![a-zA-Z])", items_body)
                        if it.strip()
                    ]
                else:
                    sub_items = [
                        it.strip() for it in re.split(r"\\item(?![a-zA-Z])", n_body) if it.strip()
                    ]

                if len(sub_items) == 4:
                    labels = ["A", "B", "C", "D"]
                    cleaned_sub = []
                    for it in sub_items:
                        cleaned_it = re.sub(
                            r"^\[\s*\(?[A-Da-d]\)?[\.\)]?\s*\]\s*", "", it
                        ).strip()
                        cleaned_sub.append(cleaned_it)
                    options = {labels[i]: cleaned_sub[i] for i in range(4)}
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

        # Clean list layout wrappers (\begin{enumerate}, \end{enumerate}, \begin{tasks}, etc.)
        # while 100% preserving actual math environments (matrix, cases, aligned)
        stem, options = clean_latex_list_wrappers(stem, options)

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

        # Check options completeness and non-empty content
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

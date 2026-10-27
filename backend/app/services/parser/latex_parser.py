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


def mask_latex_verbatim_spans(text: str) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Mask verbatim, verbatim*, lstlisting, and \\verb environments preserving exact length and newlines.

    Uses an exact-matching environment scanner so mismatched environments (e.g. \\begin{verbatim}...\\end{lstlisting})
    are never cross-paired. Supports custom delimiters for \\verb.
    """
    spans: List[Tuple[int, int, str]] = []
    i = 0
    n = len(text)
    ENV_NAMES = {"verbatim", "verbatim*", "lstlisting"}

    while i < n:
        # Check for LaTeX comment: % not preceded by an odd number of backslashes
        if text[i] == "%":
            bs_count = 0
            b_idx = i - 1
            while b_idx >= 0 and text[b_idx] == "\\":
                bs_count += 1
                b_idx -= 1
            if bs_count % 2 == 0:
                nl = text.find("\n", i)
                if nl == -1:
                    break
                i = nl + 1
                continue

        if text.startswith(r"\begin", i):
            m = re.match(r"^\\begin\{([a-zA-Z*]+)\}", text[i:])
            if m:
                env_name = m.group(1).lower()
                if env_name in ENV_NAMES:
                    start_pos = i
                    end_tag = f"\\end{{{m.group(1)}}}"
                    end_idx = text.lower().find(end_tag.lower(), i + len(m.group(0)))
                    if end_idx != -1:
                        end_pos = end_idx + len(end_tag)
                        spans.append((start_pos, end_pos, text[start_pos:end_pos]))
                        i = end_pos
                        continue
                    else:
                        # Unclosed verbatim environment: mask to EOF
                        spans.append((start_pos, n, text[start_pos:n]))
                        break
        elif text.startswith(r"\verb", i):
            verb_prefix = r"\verb*" if text.startswith(r"\verb*", i) else r"\verb"
            delim_pos = i + len(verb_prefix)
            if delim_pos < n:
                delim = text[delim_pos]
                if delim not in ("\n", "\r", " ", "\t") and not delim.isalpha():
                    newline_pos = text.find("\n", delim_pos + 1)
                    if newline_pos == -1:
                        newline_pos = n
                    closing_delim_pos = text.find(delim, delim_pos + 1, newline_pos)
                    if closing_delim_pos != -1:
                        end_pos = closing_delim_pos + 1
                        spans.append((i, end_pos, text[i:end_pos]))
                        i = end_pos
                        continue
        i += 1

    chars = list(text)
    for start, end, _ in spans:
        for k in range(start, end):
            if chars[k] != "\n":
                chars[k] = "~"
    return "".join(chars), spans


def strip_latex_comments_preserve_len(text: str) -> str:
    """Strip LaTeX comments (% to end of line), taking care of escaped \\% vs \\\\%.

    Rules:
    - Count consecutive backslashes preceding '%'.
    - If odd number of backslashes (\\%, \\\\\\%): escaped percent sign -> NOT a comment.
    - If even number of backslashes (%, \\\\%, \\\\\\\\%): genuine comment -> strip to end of line.
    - Preserves exact line length and newlines by padding stripped comment with spaces.
    """
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        comment_start = -1
        for i, ch in enumerate(line):
            if ch == "%":
                bs_count = 0
                j = i - 1
                while j >= 0 and line[j] == "\\":
                    bs_count += 1
                    j -= 1
                if bs_count % 2 == 0:
                    comment_start = i
                    break
        if comment_start != -1:
            cleaned_lines.append(line[:comment_start] + " " * (len(line) - comment_start))
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


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
        # Check for optional bracket arguments right after \begin{env}: e.g. [label=\arabic*.]
        body_start = idx
        while body_start < len(text) and text[body_start] in " \t\r\n":
            body_start += 1
        if body_start < len(text) and text[body_start] == "[":
            bracket_depth = 1
            b_idx = body_start + 1
            while b_idx < len(text) and bracket_depth > 0:
                if text[b_idx] == "[":
                    bracket_depth += 1
                elif text[b_idx] == "]":
                    bracket_depth -= 1
                b_idx += 1
            if bracket_depth == 0:
                body_start = b_idx
            else:
                body_start = idx
        else:
            body_start = idx

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
                        (start, next_end + len(end_tag), text[body_start : next_end])
                    )
                idx = next_end + len(end_tag)
        pos = idx if depth == 0 else len(text)
    return spans


def find_outer_latex_environments(text: str, env_name: str = "enumerate") -> List[str]:
    """Find top-level LaTeX environment bodies by balancing \\begin and \\end tags."""
    return [body for _, _, body in find_outer_latex_environment_spans(text, env_name)]


def split_latex_items(enum_body: str, source_body: Optional[str] = None) -> List[str]:
    """Split LaTeX enumerate body into top-level question items.

    Ignores \\item inside nested environments and \\item with option labels like \\item[A.].
    If source_body is provided, structural boundary detection runs on enum_body (masked)
    while slices are extracted from source_body.
    """
    items: List[str] = []
    token_pattern = re.compile(r"(\\begin\{[a-zA-Z*]+\}|\\end\{[a-zA-Z*]+\}|\\item(?![a-zA-Z]))")

    tokens = list(token_pattern.finditer(enum_body))
    src = source_body if source_body is not None else enum_body
    if not tokens:
        trimmed = src.strip()
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
                prev_chunk = src[last_end:start].strip()
                # Ignore configuration bracket chunks or whitespace before first item
                if prev_chunk and not (last_end == 0 and not items and re.match(r"^(?:\[[^\]]*\]|\s)*$", prev_chunk)):
                    items.append(prev_chunk)
                last_end = match.end()

    final_chunk = src[last_end:].strip()
    if final_chunk:
        items.append(final_chunk)

    return items


def parse_latex(raw_content: str) -> Tuple[List[ParsedQuestionItem], List[ParserErrorItem]]:
    """Parse raw LaTeX exam text and return parsed questions and errors."""
    text = normalize_unicode_nfc(raw_content)

    # 1. Mask verbatim/lstlisting first to protect code % characters
    masked_verbatim, verbatim_spans = mask_latex_verbatim_spans(text)

    # 2. Strip comments preserving length and newlines with backslash parity check on masked text
    stripped_structure = strip_latex_comments_preserve_len(masked_verbatim)

    # 3. Create clean source_text: strip comments outside verbatim from original text
    source_chars = list(text)
    for k in range(len(text)):
        if stripped_structure[k] == " " and masked_verbatim[k] != "~" and text[k] != " ":
            source_chars[k] = " "
    source_text = "".join(source_chars)

    # 4. Parse separate answer table on structure text
    answer_map, struct_without_keys, key_info = parse_separate_answer_key(
        stripped_structure, return_info=True
    )
    cutoff_len = len(struct_without_keys)
    text_without_keys = source_text[:cutoff_len]

    # 5. Segment questions: distinguish between top-level question enumerate and option enumerate
    questions_raw: List[Dict[str, Any]] = []

    enum_spans = find_outer_latex_environment_spans(struct_without_keys, "enumerate")
    header_matches = list(LATEX_QUESTION_HEADER.finditer(struct_without_keys))

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
        for start, end, _ in enum_spans:
            begin_tag = r"\begin{enumerate}"
            end_tag = r"\end{enumerate}"
            inner_start = start + len(begin_tag)
            inner_end = end - len(end_tag)
            enum_body_struct = struct_without_keys[inner_start:inner_end]
            enum_body_source = text_without_keys[inner_start:inner_end]

            items = split_latex_items(enum_body_struct, source_body=enum_body_source)
            for item in items:
                item_text = item.strip()
                if not item_text:
                    continue

                # Check if there is an explicit label like [Câu 1:] or prefix "Câu X:"
                lbl_match = re.match(r"^\[(.*?)\]", item_text)
                if lbl_match:
                    lbl = lbl_match.group(1)
                    item_text = item_text[lbl_match.end() :].strip()
                    num_match = re.search(r"\d+", lbl)
                    q_no = int(num_match.group(0)) if num_match else q_counter
                else:
                    q_hdr = re.match(r"^(?:câu|bài)\s+(\d+)\s*[\.:\-]", item_text, re.IGNORECASE)
                    if q_hdr:
                        q_no = int(q_hdr.group(1))
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

    # 6. Process question items
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
        opt_res = extract_options_from_text(q_text)
        if opt_res.error_type == "AMBIGUOUS_FORMAT":
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="AMBIGUOUS_FORMAT",
                    message=f"Question {q_no} has ambiguous option structure or multiple marked answers.",
                )
            )
        elif len(options) < 4:
            if len(opt_res.options) == 4:
                stem = opt_res.stem
                options = opt_res.options
                inline_key = opt_res.detected_key

        # Clean list layout wrappers (\begin{enumerate}, \end{enumerate}, \begin{tasks}, etc.)
        stem, options = clean_latex_list_wrappers(stem, options)

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

        # Check conflicting answer: separate answer map vs inline marker
        table_key = answer_map.get(q_no)
        if inline_key and table_key and inline_key.upper() != table_key.upper():
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="CONFLICTING_ANSWER_KEY",
                    message=f"Question {q_no} has conflicting answers: inline marker indicates '{inline_key}' but answer section indicates '{table_key}'.",
                )
            )

        correct_key = table_key or inline_key or ""
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

    # Validate answer section metadata against parsed questions (FIX-03, FIX-04, FIX-10)
    seen_q_nums = {q.question_no for q in parsed_questions}
    for dup_q in set(key_info.duplicate_keys):
        if not any(e.question_no == dup_q and e.error_type == "CONFLICTING_ANSWER_KEY" for e in errors):
            errors.append(
                ParserErrorItem(
                    question_no=dup_q,
                    error_type="CONFLICTING_ANSWER_KEY",
                    message=f"Answer section contains duplicate entries for question {dup_q}.",
                )
            )

    for pair_q, _ in key_info.raw_pairs:
        if pair_q <= 0:
            if not any(e.question_no == pair_q and e.error_type == "INVALID_QUESTION_NO" for e in errors):
                errors.append(
                    ParserErrorItem(
                        question_no=pair_q,
                        error_type="INVALID_QUESTION_NO",
                        message=f"Answer section contains invalid question number {pair_q} (must be positive integer).",
                    )
                )
        elif pair_q not in seen_q_nums and parsed_questions:
            if not any(e.question_no == pair_q and e.error_type == "SURPLUS_ANSWER_KEY" for e in errors):
                errors.append(
                    ParserErrorItem(
                        question_no=pair_q,
                        error_type="SURPLUS_ANSWER_KEY",
                        message=f"Answer section contains answer for question {pair_q} which does not exist in exam.",
                    )
                )

    errors.sort(key=lambda x: x.question_no)
    return parsed_questions, errors

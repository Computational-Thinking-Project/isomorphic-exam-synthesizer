"""DOCX Ingestion Parser using python-docx and XML inspection (TASK-202).

Handles:
- Paragraph and table question extraction ("Câu X:", "Câu X.")
- 4 options A, B, C, D extraction
- Separate answer key mapping
- OMML / Equation Editor detection (<w:oMath>, <m:oMath>, embedded equation pictures)
- Unicode NFC normalization and Prompt Injection detection (SEC-02)
"""

import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import docx
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.models.schemas import ParsedQuestionItem, ParserErrorItem
from app.services.parser.utils import (
    ANSWER_SECTION_PATTERNS,
    KEY_PAIR_PATTERN,
    check_prompt_injection,
    extract_options_from_text,
    normalize_unicode_nfc,
    parse_separate_answer_key,
)

logger = logging.getLogger(__name__)

QUESTION_START_PATTERN = re.compile(
    r"^(?:câu|bài)\s+(?P<num>\d+)\s*[\.:\-]\s*",
    re.IGNORECASE,
)

OMML_MATH_TAGS = ("<m:oMath", "<w:oMath", "<m:oMathPara", "<w:oMathPara")
EMBEDDED_OLE_MATH_TAGS = ("<w:object", 'progid="Equation.', "Equation.3", "MathType")


def inspect_paragraph_omml(paragraph) -> Tuple[bool, bool]:
    """Inspect paragraph XML for OMML math equations or embedded equation objects.

    Returns:
        (has_omml, is_unparsed)
        If math tags exist and cannot be represented cleanly as text/LaTeX, is_unparsed=True.
    """
    try:
        xml_str = paragraph._p.xml
    except Exception:
        return False, False

    has_omml = any(tag in xml_str for tag in OMML_MATH_TAGS)
    has_ole_equation = any(tag in xml_str for tag in EMBEDDED_OLE_MATH_TAGS)

    if has_ole_equation:
        # Legacy Word Equation 3.0 / MathType OLE objects are binary/images and cannot be parsed to LaTeX text
        return True, True

    if has_omml:
        # All unconverted OMML math structures (<m:oMath>, <m:sSup>, <m:f>, etc.)
        # drop their math runs (<m:t>) from paragraph.text and must be flagged as incomplete.
        return True, True

    return False, False


def inspect_cell_omml(cell) -> Tuple[bool, bool]:
    """Inspect table cell XML for OMML math equations or embedded equation objects."""
    try:
        xml_str = cell._tc.xml
    except Exception:
        return False, False

    has_omml = any(tag in xml_str for tag in OMML_MATH_TAGS)
    has_ole_equation = any(tag in xml_str for tag in EMBEDDED_OLE_MATH_TAGS)

    if has_ole_equation or has_omml:
        return True, True

    return False, False


def parse_docx(file_bytes: bytes) -> Tuple[List[ParsedQuestionItem], List[ParserErrorItem]]:
    """Parse a DOCX file in-memory and return extracted questions and validation errors."""
    try:
        doc: DocumentObject = docx.Document(io.BytesIO(file_bytes))
    except Exception as exc:
        logger.error("Failed to read DOCX document: %s", exc)
        return [], [
            ParserErrorItem(
                question_no=0,
                error_type="INVALID_FORMAT",
                message=f"Could not read DOCX document: {str(exc)}",
            )
        ]

    # 1. Aggregate text and paragraph info in strict document order (both paragraphs and tables)
    full_paragraphs: List[str] = []
    paragraph_omml_flags: List[bool] = []

    for child in doc.element.body:
        if child.tag.endswith("p"):
            p = Paragraph(child, doc)
            text = normalize_unicode_nfc(p.text)
            has_omml, is_unparsed_omml = inspect_paragraph_omml(p)
            full_paragraphs.append(text)
            paragraph_omml_flags.append(is_unparsed_omml)
        elif child.tag.endswith("tbl"):
            tbl = Table(child, doc)
            for row in tbl.rows:
                seen_tc = set()
                unique_cells = []
                for cell in row.cells:
                    if cell._tc not in seen_tc:
                        seen_tc.add(cell._tc)
                        unique_cells.append(cell)

                row_has_unparsed_omml = any(
                    inspect_cell_omml(cell)[1] for cell in unique_cells
                ) or any(
                    inspect_paragraph_omml(p)[1]
                    for cell in unique_cells
                    for p in cell.paragraphs
                )

                if len(unique_cells) == 1:
                    # Single-cell row: preserve individual paragraphs
                    cell = unique_cells[0]
                    _, cell_unparsed = inspect_cell_omml(cell)
                    for cp in cell.paragraphs:
                        text = normalize_unicode_nfc(cp.text)
                        _, cp_unparsed = inspect_paragraph_omml(cp)
                        full_paragraphs.append(text)
                        paragraph_omml_flags.append(cp_unparsed or cell_unparsed)
                else:
                    # Multi-cell row (e.g. question columns, option grid, or answer key row)
                    row_parts = []
                    for cell in unique_cells:
                        c_text = normalize_unicode_nfc(cell.text.strip())
                        if c_text:
                            row_parts.append(c_text)
                    row_text = "  ".join(row_parts)
                    if row_text or row_has_unparsed_omml:
                        full_paragraphs.append(row_text)
                        paragraph_omml_flags.append(row_has_unparsed_omml)

    # Combine full text for separate answer key parsing
    all_text = "\n".join(full_paragraphs)

    # 2. Extract separate answer table at the end
    answer_map, text_without_keys = parse_separate_answer_key(all_text)

    # Cut off trailing answer key paragraphs to prevent contamination of the last question/options
    cutoff_idx = len(full_paragraphs)
    if answer_map:
        for i, p_text in enumerate(full_paragraphs):
            # Check for explicit answer section heading
            if any(pat.search(p_text) for pat in ANSWER_SECTION_PATTERNS) or re.search(
                r"^\s*(?:bảng\s+đáp\s+án|đáp\s+án|hướng\s+dẫn\s+chấm|answer\s+key)\b",
                p_text,
                re.IGNORECASE,
            ):
                cutoff_idx = i
                break
            # Check for compact answer key line (only towards the tail of the document)
            if i >= max(0, len(full_paragraphs) - 10):
                _, found_opts, _ = extract_options_from_text(p_text)
                if len(found_opts) < 4:
                    pairs_in_p = list(KEY_PAIR_PATTERN.finditer(p_text))
                    residual = KEY_PAIR_PATTERN.sub("", p_text)
                    if (
                        len(pairs_in_p) >= 2
                        and not QUESTION_START_PATTERN.match(p_text.strip())
                        and not re.search(r"[a-zA-Zà-ỹÀ-Ỹ]{2,}", residual)
                    ):
                        cutoff_idx = i
                        break

    content_paragraphs = full_paragraphs[:cutoff_idx]
    content_omml_flags = paragraph_omml_flags[:cutoff_idx]

    # 3. Segment paragraphs into question blocks
    questions_raw: List[Dict[str, Any]] = []
    current_q: Optional[Dict[str, Any]] = None
    errors: List[ParserErrorItem] = []

    for idx, p_text in enumerate(content_paragraphs):
        trimmed = p_text.strip()
        if not trimmed:
            # Handle standalone OMML equation paragraphs (python-docx p.text is empty for OMML)
            if content_omml_flags[idx]:
                if current_q is not None:
                    current_q["has_unparsed_omml"] = True
                    current_q["lines"].append("[CÔNG THỨC OMML CHƯA ĐỌC ĐƯỢC]")
                else:
                    errors.append(
                        ParserErrorItem(
                            question_no=0,
                            error_type="UNPARSED_OMML",
                            message="Tệp DOCX chứa công thức OMML đứng trước câu hỏi đầu tiên không thể đọc được nội dung.",
                        )
                    )
            continue

        match = QUESTION_START_PATTERN.match(trimmed)
        if match:
            # Save previous question if exists
            if current_q:
                questions_raw.append(current_q)

            q_num = int(match.group("num"))
            content_start = match.end()
            body_text = trimmed[content_start:].strip()

            current_q = {
                "question_no": q_num,
                "lines": [body_text] if body_text else [],
                "has_unparsed_omml": content_omml_flags[idx],
            }
        else:
            if current_q is not None:
                current_q["lines"].append(trimmed)
                if content_omml_flags[idx]:
                    current_q["has_unparsed_omml"] = True

    if current_q:
        questions_raw.append(current_q)

    # 4. Process each question block into ParsedQuestionItem and collect errors
    parsed_questions: List[ParsedQuestionItem] = []

    for q_data in questions_raw:
        q_no = q_data["question_no"]
        joined_text = "\n".join(q_data["lines"]).strip()

        # Extract options
        stem, options, inline_key = extract_options_from_text(joined_text)

        # Determine correct key: precedence (1) separate answer map, (2) inline marker
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

        has_unparsed_omml = q_data.get("has_unparsed_omml", False)
        if has_unparsed_omml:
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="UNPARSED_OMML",
                    message=f"Question {q_no} contains unparsed Word OMML / Equation formulas.",
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

        # Check security / prompt injection (SEC-02)
        has_sec_warning = check_prompt_injection(joined_text)

        parsed_questions.append(
            ParsedQuestionItem(
                question_no=q_no,
                raw_content=stem if stem else joined_text,
                options=options,
                correct_key=correct_key if not has_missing_answer else "",
                solution_md=None,
                has_missing_answer=has_missing_answer,
                has_unparsed_omml=has_unparsed_omml,
                has_security_warning=has_sec_warning,
            )
        )

    return parsed_questions, errors

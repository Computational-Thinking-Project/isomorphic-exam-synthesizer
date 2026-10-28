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
    extract_key_pair,
    extract_options_from_text,
    normalize_unicode_nfc,
    parse_separate_answer_key,
)

logger = logging.getLogger(__name__)

QUESTION_START_PATTERN = re.compile(
    r"^(?:câu|bài)\s+(?P<num>\d+)\s*[\.:\-\)]\s*",
    re.IGNORECASE,
)

OMML_MATH_TAGS = ("<m:oMath", "<w:oMath", "<m:oMathPara", "<w:oMathPara")
EMBEDDED_OLE_MATH_TAGS = ("<w:object", 'progid="Equation.', "Equation.3", "MathType")
WORD_IMAGE_DRAWING_TAGS = ("<w:drawing", "<w:pict", "<a:blip", "<v:shape", "<v:imagedata")


def inspect_paragraph_visuals(paragraph) -> Tuple[bool, bool, bool]:
    """Inspect paragraph XML for OMML math equations and embedded drawings/images.

    Returns:
        (has_omml, is_unparsed_omml, has_unparsed_image)
    """
    try:
        xml_str = paragraph._p.xml
    except Exception:
        return False, False, False

    has_omml = any(tag in xml_str for tag in OMML_MATH_TAGS)
    has_ole = any(tag in xml_str for tag in EMBEDDED_OLE_MATH_TAGS)
    has_image = any(tag in xml_str for tag in WORD_IMAGE_DRAWING_TAGS)

    is_unparsed_omml = has_omml or has_ole
    return has_omml, is_unparsed_omml, has_image


def inspect_paragraph_omml(paragraph) -> Tuple[bool, bool]:
    """Backward-compatible helper returning (has_omml, is_unparsed_omml)."""
    has_omml, is_unparsed_omml, _ = inspect_paragraph_visuals(paragraph)
    return has_omml, is_unparsed_omml


def inspect_cell_visuals(cell) -> Tuple[bool, bool, bool]:
    """Inspect table cell XML for OMML math equations and embedded drawings/images."""
    try:
        xml_str = cell._tc.xml
    except Exception:
        return False, False, False

    has_omml = any(tag in xml_str for tag in OMML_MATH_TAGS)
    has_ole = any(tag in xml_str for tag in EMBEDDED_OLE_MATH_TAGS)
    has_image = any(tag in xml_str for tag in WORD_IMAGE_DRAWING_TAGS)

    is_unparsed_omml = has_omml or has_ole
    return has_omml, is_unparsed_omml, has_image


def inspect_cell_omml(cell) -> Tuple[bool, bool]:
    """Backward-compatible helper returning (has_omml, is_unparsed_omml)."""
    has_omml, is_unparsed_omml, _ = inspect_cell_visuals(cell)
    return has_omml, is_unparsed_omml


def extract_cell_elements(
    cell: Any, doc: DocumentObject
) -> List[Tuple[str, bool, bool]]:
    """Recursively extract text lines and (unparsed_omml, unparsed_image) flags from a cell.

    Traverses child paragraphs and child tables in document order, deduplicating merged cells.
    Inspects each paragraph individually to prevent visual flags from leaking to unrelated questions.

    Returns:
        List of (subline_text, is_unparsed_omml, has_unparsed_image)
    """
    results: List[Tuple[str, bool, bool]] = []
    seen_sub_tc: set = set()

    for child in cell._tc:
        if child.tag.endswith("p"):
            cp = Paragraph(child, doc)
            text = normalize_unicode_nfc(cp.text)
            _, cp_omml, cp_img = inspect_paragraph_visuals(cp)
            for subline in text.split("\n"):
                results.append((subline, cp_omml, cp_img))
        elif child.tag.endswith("tbl"):
            sub_tbl = Table(child, doc)
            for sub_row in sub_tbl.rows:
                for sub_cell in sub_row.cells:
                    tc_id = id(sub_cell._tc)
                    if tc_id not in seen_sub_tc:
                        seen_sub_tc.add(tc_id)
                        results.extend(extract_cell_elements(sub_cell, doc))
    return results


def try_parse_table_as_answer_key(
    tbl: Table,
    is_tail: bool = False,
    preceding_text: Optional[str] = None,
) -> Optional[List[str]]:
    """Detect if a table is an answer key table and normalize its entries into key pairs.

    Recognizes:
    - Alternating cells in a row (e.g. ['1', 'A', '2', 'B'] or ['Câu 1', 'A'])
    - 2-row grid (Row 2k: question numbers, Row 2k+1: answer letters, e.g. ['1', '2'] / ['A', 'B'])
    - Direct key pairs in cells (e.g. ['1.A', '2.B'])
    - Tables with 'BẢNG ĐÁP ÁN' headers or column headers ('Câu' / 'Đ/A')

    Returns normalized lines (e.g. ['BẢNG ĐÁP ÁN:', '1.A  2.B']) or None if not an answer key table.
    """
    def _is_num_cell(text: str) -> Optional[int]:
        m = re.match(r"^(?:câu\s*)?(\d+)\s*[\.:\-\)]?$", text.strip(), re.IGNORECASE)
        return int(m.group(1)) if m else None

    def _is_ans_cell(text: str) -> Optional[str]:
        m = re.match(r"^[\(\[]?\s*([A-D])\s*[\)\]]?[\.:]?$", text.strip(), re.IGNORECASE)
        return m.group(1).upper() if m else None

    grid: List[List[str]] = []
    for row in tbl.rows:
        seen_tc = set()
        row_cells = []
        for cell in row.cells:
            tc_id = id(cell._tc)
            if tc_id not in seen_tc:
                seen_tc.add(tc_id)
                row_cells.append(cell.text.strip())
        if any(c for c in row_cells):
            grid.append(row_cells)

    if not grid:
        return None

    # Filter out question/content tables: answer key cells are short and contain no option markers with stems
    for r in grid:
        for c in r:
            if len(c) > 60:
                return None
            if re.search(r"\b[A-D]\.\s+[^\s]+", c):
                return None

    extracted_pairs: List[Tuple[int, str]] = []

    # Check for header row (e.g. 'BẢNG ĐÁP ÁN') in table or preceding paragraph
    start_r = 0
    header_found = False
    first_text = " ".join(grid[0]).lower()
    answer_keywords = ["bảng đáp án", "đáp án", "answer key", "hướng dẫn chấm"]
    if any(w in first_text for w in answer_keywords):
        header_found = True
        start_r = 1
    elif preceding_text and any(w in preceding_text.lower() for w in answer_keywords):
        header_found = True

    content_rows = grid[start_r:]
    if not content_rows:
        return None

    # Check if first column has header labels: e.g. Row 0: 'Câu' / Row 1: 'Đ/A'
    if len(content_rows) >= 2 and content_rows[0] and content_rows[1]:
        c0_r0 = content_rows[0][0].strip().lower()
        c0_r1 = content_rows[1][0].strip().lower()
        if re.search(r"^(?:câu|stt|no)$", c0_r0) and re.search(r"^(?:đ/a|đáp\s*án|ans)$", c0_r1):
            header_found = True

    # Check if cells contain explicit labels like "Câu 1:" or "1.A"
    has_explicit_labels = False
    for r in content_rows:
        for c in r:
            if re.search(r"^(?:câu|bài)\s*\d+", c, re.IGNORECASE) or KEY_PAIR_PATTERN.search(c):
                has_explicit_labels = True
                break

    # Pattern A: Alternating cells in rows (e.g. 1 | A | 2 | B or Câu 1 | A)
    alt_pairs: List[Tuple[int, str]] = []
    for r in content_rows:
        # Skip header rows like ['Câu', 'Đáp án', 'Câu', 'Đáp án']
        if all(re.search(r"^(?:câu|đáp án|đ/a|stt|no|ans)$", c, re.IGNORECASE) for c in r):
            continue
        if len(r) >= 2:
            # Strip trailing empty padding cells
            r_clean = list(r)
            while r_clean and not r_clean[-1]:
                r_clean.pop()
            row_pairs = []
            for i in range(0, len(r_clean) - 1, 2):
                n = _is_num_cell(r_clean[i])
                a = _is_ans_cell(r_clean[i + 1])
                if n is not None and a is not None:
                    row_pairs.append((n, a))
            if row_pairs and len(row_pairs) * 2 == len(r_clean):
                alt_pairs.extend(row_pairs)

    if len(alt_pairs) >= 2:
        extracted_pairs = alt_pairs

    # Pattern B: 2-row grid (Row 2k numbers, Row 2k+1 answers)
    if not extracted_pairs and len(content_rows) >= 2:
        grid_pairs: List[Tuple[int, str]] = []
        r_idx = 0
        while r_idx < len(content_rows) - 1:
            r_num = content_rows[r_idx]
            r_ans = content_rows[r_idx + 1]
            c_nums = [_is_num_cell(c) for c in r_num]
            c_ans = [_is_ans_cell(c) for c in r_ans]

            # If leading column is a label ('Câu' / 'Đáp án'), strip it
            if c_nums and c_nums[0] is None and len(c_nums) == len(c_ans):
                c_nums = c_nums[1:]
                c_ans = c_ans[1:]

            if (
                len(c_nums) >= 2
                and len(c_nums) == len(c_ans)
                and all(n is not None for n in c_nums)
                and all(a is not None for a in c_ans)
            ):
                for n, a in zip(c_nums, c_ans):
                    if n is not None and a is not None:
                        grid_pairs.append((n, a))
                r_idx += 2
            else:
                r_idx += 1
        if len(grid_pairs) >= 2:
            extracted_pairs = grid_pairs

    # Pattern C: Direct key pair in cells (e.g. '1.A', '2.B')
    if not extracted_pairs:
        direct_pairs: List[Tuple[int, str]] = []
        for r in content_rows:
            for c in r:
                for p in KEY_PAIR_PATTERN.finditer(c):
                    direct_pairs.append(extract_key_pair(p))
        if len(direct_pairs) >= 2:
            extracted_pairs = direct_pairs

    if not extracted_pairs:
        return None

    # Validation against false-positive content tables (FIX-01 / P1-1):
    # A table is accepted as an answer key when there is EXPLICIT semantic evidence:
    #   (a) a header row or preceding paragraph containing 'BẢNG ĐÁP ÁN', 'Đáp án', etc.
    #   (b) explicit 'Câu N' labels or '1.A'-style key-pair cells in the data
    #   (c) column-header format detected (row0='Câu', row1='Đ/A')
    # Or (d) at document tail (is_tail=True), a single-row grid table with multiple question-answer
    #        pairs across columns (e.g. 4+ cells: 1 | A | 2 | B), unlike standard 2-column data tables
    #        (which have rows=[['1', 'A'], ['2', 'B']] where each row is a 2-element tuple).
    is_multi_pair_row = (
        is_tail
        and len(content_rows) == 1
        and len(content_rows[0]) >= 4
        and len(extracted_pairs) >= 2
    )
    if not header_found and not has_explicit_labels and not is_multi_pair_row:
        return None

    sorted_pairs = sorted(extracted_pairs, key=lambda p: p[0])
    lines = ["BẢNG ĐÁP ÁN:"]
    chunk: List[str] = []
    for num, key in sorted_pairs:
        chunk.append(f"{num}.{key}")
        if len(chunk) == 10:
            lines.append("  ".join(chunk))
            chunk = []
    if chunk:
        lines.append("  ".join(chunk))
    return lines


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
    paragraph_image_flags: List[bool] = []

    body_elements = list(doc.element.body)
    for idx_el, child in enumerate(body_elements):
        if child.tag.endswith("p"):
            p = Paragraph(child, doc)
            text = normalize_unicode_nfc(p.text)
            _, is_unparsed_omml, has_image = inspect_paragraph_visuals(p)
            full_paragraphs.append(text)
            paragraph_omml_flags.append(is_unparsed_omml)
            paragraph_image_flags.append(has_image)
        elif child.tag.endswith("tbl"):
            tbl = Table(child, doc)
            # Check if this table is at the tail of the document (no questions start after it)
            has_subsequent_q = False
            for rem in body_elements[idx_el + 1:]:
                if rem.tag.endswith("p"):
                    p_rem = Paragraph(rem, doc)
                    if QUESTION_START_PATTERN.match(p_rem.text.strip()):
                        has_subsequent_q = True
                        break

            # Find text of the nearest preceding non-empty paragraph
            preceding_p_text = None
            for prev_el in reversed(body_elements[:idx_el]):
                if prev_el.tag.endswith("p"):
                    prev_txt = Paragraph(prev_el, doc).text.strip()
                    if prev_txt:
                        preceding_p_text = prev_txt
                        break

            ans_lines = try_parse_table_as_answer_key(
                tbl, is_tail=not has_subsequent_q, preceding_text=preceding_p_text
            )
            if ans_lines:
                tbl_has_unparsed_omml = any(
                    inspect_cell_visuals(c)[1] for row in tbl.rows for c in row.cells
                )
                tbl_has_image = any(
                    inspect_cell_visuals(c)[2] for row in tbl.rows for c in row.cells
                )
                for line in ans_lines:
                    full_paragraphs.append(line)
                    paragraph_omml_flags.append(tbl_has_unparsed_omml)
                    paragraph_image_flags.append(tbl_has_image)
                continue

            # Otherwise, it's a content/question table: iterate cell-by-cell in document order
            # preserving question boundaries and recursively traversing nested tables
            for row in tbl.rows:
                seen_tc = set()
                unique_cells = []
                for cell in row.cells:
                    tc_id = id(cell._tc)
                    if tc_id not in seen_tc:
                        seen_tc.add(tc_id)
                        unique_cells.append(cell)

                for cell in unique_cells:
                    cell_elements = extract_cell_elements(cell, doc)
                    for subline, u_omml, u_img in cell_elements:
                        full_paragraphs.append(subline)
                        paragraph_omml_flags.append(u_omml)
                        paragraph_image_flags.append(u_img)

    # Combine full text for separate answer key parsing
    all_text = "\n".join(full_paragraphs)

    # 2. Extract separate answer table at the end
    answer_map, text_without_keys, key_info = parse_separate_answer_key(
        all_text, return_info=True
    )

    # Cut off trailing answer key paragraphs to prevent contamination of the last question/options.
    # Also detect answer-section headers located mid-document (P1-3).
    cutoff_idx = len(full_paragraphs)
    # Set of paragraph indices that belong to an answer-section appearing mid-document
    mid_answer_poison_indices: set = set()

    def _is_answer_heading(text: str) -> bool:
        """Return True if the paragraph looks like an answer-section heading."""
        return bool(
            any(pat.search(text) for pat in ANSWER_SECTION_PATTERNS)
            or re.search(
                r"^\s*(?:#{1,6}\s*)?(?:\*{1,2}|_{1,2})?(?:bảng\s+đáp\s+án|đáp\s+án|hướng\s+dẫn\s+chấm|answer\s+key)\b",
                text,
                re.IGNORECASE,
            )
        )

    i = 0
    while i < len(full_paragraphs):
        p_text = full_paragraphs[i]
        is_header = _is_answer_heading(p_text)
        has_subsequent_q = any(
            QUESTION_START_PATTERN.match(full_paragraphs[j].strip())
            for j in range(i + 1, len(full_paragraphs))
        )
        if is_header and not has_subsequent_q:
            # Tail answer section — cut here
            cutoff_idx = i
            break
        if is_header and has_subsequent_q:
            # Mid-document answer section (P1-3): mark heading + following key lines as poison
            mid_answer_poison_indices.add(i)
            j = i + 1
            while j < len(full_paragraphs):
                nxt = full_paragraphs[j].strip()
                if QUESTION_START_PATTERN.match(nxt):
                    break
                if nxt and not KEY_PAIR_PATTERN.search(nxt):
                    # Non-key line that is not empty and not a question: stop poison
                    break
                mid_answer_poison_indices.add(j)
                j += 1
            i = j
            continue
        # Trailing raw key-pair lines (no heading)
        if i >= max(0, len(full_paragraphs) - 10) and not has_subsequent_q:
            pairs_in_p = list(KEY_PAIR_PATTERN.finditer(p_text))
            if len(pairs_in_p) >= 2 and not QUESTION_START_PATTERN.match(p_text.strip()):
                residual = KEY_PAIR_PATTERN.sub("", p_text)
                if not re.search(r"[a-zA-Zà-ỹÀ-Ỹ]{3,}", residual):
                    cutoff_idx = i
                    break
        i += 1

    content_paragraphs = full_paragraphs[:cutoff_idx]
    content_omml_flags = paragraph_omml_flags[:cutoff_idx]
    content_image_flags = paragraph_image_flags[:cutoff_idx]

    # 3. Segment paragraphs into question blocks
    questions_raw: List[Dict[str, Any]] = []
    current_q: Optional[Dict[str, Any]] = None
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

    # Track which questions have already had an AMBIGUOUS_FORMAT error emitted for mid-doc answer sections
    ambiguous_format_emitted: set = set()

    for idx, p_text in enumerate(content_paragraphs):
        # P1-3: skip lines that belong to a mid-document answer section
        if idx in mid_answer_poison_indices:
            if current_q is not None:
                q_no = current_q["question_no"]
                if q_no not in ambiguous_format_emitted:
                    ambiguous_format_emitted.add(q_no)
                    errors.append(
                        ParserErrorItem(
                            question_no=q_no,
                            error_type="AMBIGUOUS_FORMAT",
                            message=(
                                f"Question {q_no}: an answer section heading or key data was found "
                                "mid-document (between questions). The answer section could not be "
                                "safely mapped. Please move the answer section to the end of the document."
                            ),
                        )
                    )
            continue

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
            if content_image_flags[idx]:
                if current_q is not None:
                    current_q["has_unparsed_image"] = True
                else:
                    errors.append(
                        ParserErrorItem(
                            question_no=0,
                            error_type="UNPARSED_IMAGE",
                            message="Tệp DOCX chứa hình ảnh đứng trước câu hỏi đầu tiên không thể đọc được nội dung.",
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
                "has_unparsed_image": content_image_flags[idx],
            }
        else:
            if current_q is not None:
                current_q["lines"].append(trimmed)
                if content_omml_flags[idx]:
                    current_q["has_unparsed_omml"] = True
                if content_image_flags[idx]:
                    current_q["has_unparsed_image"] = True

    if current_q:
        questions_raw.append(current_q)

    # 4. Process each question block into ParsedQuestionItem and collect errors
    parsed_questions: List[ParsedQuestionItem] = []

    for q_data in questions_raw:
        q_no = q_data["question_no"]
        joined_text = "\n".join(q_data["lines"]).strip()

        # Extract options
        opt_res = extract_options_from_text(joined_text)
        stem = opt_res.stem
        options = opt_res.options
        inline_key = opt_res.detected_key

        if opt_res.error_type == "AMBIGUOUS_FORMAT":
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="AMBIGUOUS_FORMAT",
                    message=f"Question {q_no} has ambiguous option structure or multiple marked answers.",
                )
            )

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

        # Determine correct key: precedence (1) separate answer map, (2) inline marker
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

        has_unparsed_omml = q_data.get("has_unparsed_omml", False)
        if has_unparsed_omml:
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="UNPARSED_OMML",
                    message=f"Question {q_no} contains unparsed Word OMML / Equation formulas.",
                )
            )

        has_unparsed_image = q_data.get("has_unparsed_image", False)
        if has_unparsed_image:
            errors.append(
                ParserErrorItem(
                    question_no=q_no,
                    error_type="UNPARSED_IMAGE",
                    message=f"Question {q_no} contains unparsed embedded images or drawings.",
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
                raw_content=stem,
                options=options,
                correct_key=correct_key if not has_missing_answer else "",
                solution_md=None,
                has_missing_answer=has_missing_answer,
                has_unparsed_omml=has_unparsed_omml,
                has_unparsed_image=has_unparsed_image,
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

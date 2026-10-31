"""
Typst Subprocess PDF Compiler Engine (TASK-306).

Provides safe, isolated, and deterministic compilation of Typst markup documents
into standard PDF files with magic-byte validation and error sanitization.
"""

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.exporter.exceptions import (
    TypstCompilationError,
    TypstNotFoundError,
    TypstTimeoutError,
)
from app.services.exporter.typst_converter import convert_markdown_to_typst, escape_typst_text

# PDF File Header Magic Bytes
PDF_MAGIC_BYTES = b"%PDF-"
DEFAULT_TIMEOUT_SECONDS = 30.0


def generate_pdf_filename(kind: str, code: Optional[str] = None) -> str:
    """
    Generate standardized PDF artifact filenames conforming to W3_ASSIGNMENT.md#L41:
    - exam_{code}.pdf: Exam paper for a specific version code.
    - answers_matrix.pdf: Complete cross-version answer key matrix.
    - solutions_{code}.pdf: Step-by-step solution explanations for a specific version code.
    """
    normalized_kind = kind.lower().strip()
    c = str(code).strip() if code is not None else "101"

    if normalized_kind in ("exam", "exam_paper", "questions", "question_paper"):
        return f"exam_{c}.pdf"
    if normalized_kind in ("matrix", "answers_matrix", "answer_matrix", "answer_keys"):
        return "answers_matrix.pdf"
    if normalized_kind in ("solution", "solutions", "solutions_detail", "solution_paper"):
        return f"solutions_{c}.pdf"

    # Fallback convention
    return f"{normalized_kind}_{c}.pdf" if code is not None else f"{normalized_kind}.pdf"


def sanitize_compiler_error(raw_stderr: str, temp_dir: Optional[str] = None) -> str:
    """
    Sanitize Typst compiler output by stripping absolute host paths,
    preventing sensitive filesystem exposure in logs and error responses.
    """
    if not raw_stderr:
        return "Typst compilation failed with no error output."

    sanitized = raw_stderr
    if temp_dir:
        # Normalize and escape temp dir path
        norm_temp = os.path.normpath(temp_dir)
        sanitized = sanitized.replace(norm_temp, "<working_dir>")
        sanitized = sanitized.replace(temp_dir, "<working_dir>")

    # Strip generic OS temp paths (Windows C:\\...\\Temp, Unix /tmp/...)
    sanitized = re.sub(r"[A-Za-z]:\\[^\n:?*<>|]+\\input\.typ", "input.typ", sanitized)
    sanitized = re.sub(r"/tmp/[^\n:]+/input\.typ", "input.typ", sanitized)

    return sanitized.strip()


def _clean_typst_string(s: str) -> str:
    """Escape string literal for Typst #set document(title: "...", author: "...")."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()


class TypstCompiler:
    """
    Thread-safe Typst CLI subprocess runner.
    Executes compilation within temporary working directories with strict
    execution timeouts and PDF magic bytes validation.
    """

    def __init__(
        self,
        binary_path: str = "typst",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.binary_path = binary_path
        self.timeout = timeout

    def is_available(self) -> bool:
        """Check if Typst binary is accessible on PATH or configured location."""
        return shutil.which(self.binary_path) is not None

    def compile_document(
        self,
        typst_content: str,
        output_filename: str = "document.pdf",
    ) -> bytes:
        """
        Compile Typst source content into PDF bytes.

        Args:
            typst_content: Typst markup string.
            output_filename: Name of the generated PDF inside the temporary directory.

        Returns:
            bytes: Binary content of the compiled PDF.

        Raises:
            ValueError: If output_filename is invalid, contains traversal components, or is absolute.
            TypstNotFoundError: If the Typst CLI is missing.
            TypstTimeoutError: If execution exceeds configured timeout (30s).
            TypstCompilationError: If compilation fails or output is not a valid PDF.
        """
        # Validate output_filename parameter strictly before execution (F04)
        if not output_filename or not isinstance(output_filename, str):
            raise ValueError("output_filename must be a non-empty string.")

        if (
            os.path.isabs(output_filename)
            or "/" in output_filename
            or "\\" in output_filename
            or ".." in output_filename
        ):
            raise ValueError(
                f"Invalid output_filename: {output_filename!r}. "
                "Must be a simple .pdf filename without path separators or directory traversal."
            )

        clean_filename = os.path.basename(output_filename).strip()
        if not clean_filename.lower().endswith(".pdf") or clean_filename in (".", ".."):
            raise ValueError(
                f"Invalid output_filename: {output_filename!r}. Filename must end with '.pdf'."
            )

        if not self.is_available():
            raise TypstNotFoundError(binary_path=self.binary_path)

        with tempfile.TemporaryDirectory(prefix="typst_export_") as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.typ")
            output_path = os.path.join(tmp_dir, clean_filename)

            # Defensive containment check
            resolved_output = os.path.abspath(output_path)
            resolved_tmp = os.path.abspath(tmp_dir)
            if not resolved_output.startswith(resolved_tmp + os.sep):
                raise ValueError(
                    f"Security violation: output path {resolved_output} escapes temporary directory {resolved_tmp}."
                )

            with open(input_path, "w", encoding="utf-8") as f:
                f.write(typst_content)

            cmd = [self.binary_path, "compile", input_path, output_path]

            try:
                result = subprocess.run(
                    cmd,
                    shell=False,
                    timeout=self.timeout,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise TypstTimeoutError(
                    timeout_seconds=self.timeout,
                    message=f"Typst compilation timed out after {self.timeout} seconds.",
                ) from exc
            except FileNotFoundError as exc:
                raise TypstNotFoundError(binary_path=self.binary_path) from exc

            if result.returncode != 0:
                sanitized_msg = sanitize_compiler_error(result.stderr, temp_dir=tmp_dir)
                raise TypstCompilationError(
                    message=f"Typst compilation error (exit {result.returncode}): {sanitized_msg}",
                    exit_code=result.returncode,
                    raw_stderr=result.stderr,
                )

            if not os.path.exists(output_path):
                raise TypstCompilationError(
                    message="Compilation succeeded but output PDF file was not created.",
                    exit_code=result.returncode,
                    raw_stderr=result.stderr,
                )

            with open(output_path, "rb") as f:
                pdf_bytes = f.read()

            # Verify PDF magic bytes
            if not pdf_bytes.startswith(PDF_MAGIC_BYTES):
                raise TypstCompilationError(
                    message="Generated output is corrupted or not a valid PDF file (missing %PDF- header).",
                    exit_code=result.returncode,
                )

            return pdf_bytes

    def render_exam_document(
        self,
        version_code: str,
        questions: Sequence[Dict[str, Any]],
        exam_title: str = "KỲ THI KHẢO SÁT CHẤT LƯỢNG",
        subject: str = "Toán học",
    ) -> str:
        """
        Generate complete Typst source code for an exam paper.
        Supports both display_* schema (shuffler) and persisted question models.
        """
        clean_title_meta = _clean_typst_string(exam_title)
        clean_title_display = escape_typst_text(exam_title)
        clean_subject_display = escape_typst_text(subject)
        clean_version_display = escape_typst_text(str(version_code))

        q_blocks: List[str] = []
        labels = ["A", "B", "C", "D"]

        for idx, q in enumerate(questions, 1):
            disp_no = q.get("display_no") or q.get("question_no") or q.get("display_order") or idx
            raw_stem = q.get("content") or q.get("canonical_content") or q.get("stem") or ""
            stem = convert_markdown_to_typst(raw_stem)
            opts = q.get("options") or q.get("canonical_options") or ["", "", "", ""]

            opts_typst = [
                f"[*{labels[i]}.* {convert_markdown_to_typst(opt)}]" for i, opt in enumerate(opts)
            ]

            # Use 2-column or 4-column grid depending on option length
            max_opt_len = max((len(opt) for opt in opts), default=0)
            if max_opt_len <= 15:
                grid_cols = "(1fr, 1fr, 1fr, 1fr)"
            elif max_opt_len <= 45:
                grid_cols = "(1fr, 1fr)"
            else:
                grid_cols = "(1fr,)"

            grid_markup = f"#grid(columns: {grid_cols}, gutter: 8pt, {', '.join(opts_typst)})"

            block = (
                f"#block(breakable: false)[\n"
                f"  *Câu {disp_no}:* {stem}\n"
                f"  #v(4pt)\n"
                f"  {grid_markup}\n"
                f"]\n#v(6pt)"
            )
            q_blocks.append(block)

        questions_content = "\n".join(q_blocks)

        template = f"""// Auto-generated Exam Document
#set document(title: "{clean_title_meta}", author: "Isomorphic Exam Synthesizer")
#set page(
  paper: "a4",
  margin: (top: 2cm, bottom: 2cm, left: 2cm, right: 2cm),
  footer: locate(loc => {{
    let p = counter(page).at(loc).first()
    let t = counter(page).final(loc).first()
    align(center)[#text(size: 9pt, fill: luma(100))[Trang #p / #t]]
  }})
)
#set text(font: ("Liberation Serif", "Times New Roman", "DejaVu Serif"), size: 11pt, lang: "vi")
#set par(justify: true, leading: 0.7em)

#grid(
  columns: (1.2fr, 1fr),
  gutter: 10pt,
  align: (center, center),
  [
    #text(weight: "bold")[SỞ GIÁO DỤC VÀ ĐÀO TẠO]\\
    #text(weight: "bold")[TRƯỜNG THPT CHUYÊN]\\
    #text(size: 10pt, style: "italic")[(Đề thi gồm có các trang)]
  ],
  [
    #text(weight: "bold")[{clean_title_display}]\\
    #text(weight: "bold")[Môn: {clean_subject_display}]\\
    #text(weight: "bold", size: 12pt)[MÃ ĐỀ THI: {clean_version_display}]
  ]
)

#v(6pt)
#line(length: 100%, stroke: 1pt)
#v(4pt)

#block(
  width: 100%,
  stroke: 0.5pt + luma(150),
  inset: 8pt,
  radius: 3pt,
  [
    #grid(
      columns: (1.5fr, 1fr),
      gutter: 12pt,
      [Họ và tên thí sinh: #box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))],
      [Số báo danh: #box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))]
    )
    #v(4pt)
    #grid(
      columns: (1.5fr, 1fr),
      gutter: 12pt,
      [Phòng thi: #box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))],
      [Lớp: #box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))]
    )
  ]
)

#v(10pt)

{questions_content}

#v(16pt)
#align(center)[
  #text(weight: "bold")[-------------------- HẾT --------------------]\\
  #text(size: 9pt, style: "italic")[Thí sinh không được sử dụng tài liệu. Cán bộ coi thi không giải thích gì thêm.]
]
"""
        return template

    def render_solution_document(
        self,
        version_code: str,
        questions: Sequence[Dict[str, Any]],
        exam_title: str = "HƯỚNG DẪN GIẢI VÀ BẢNG ĐÁP ÁN CHI TIẾT",
    ) -> str:
        """
        Generate complete Typst source code for solution explanations and answer table.
        Supports both display_* schema (shuffler) and persisted question models.
        """
        clean_title_meta = _clean_typst_string(exam_title)
        clean_title_display = escape_typst_text(exam_title)
        clean_version_display = escape_typst_text(str(version_code))

        # 1. Build Answer Matrix Table (columns of 10)
        row1: List[str] = []
        row2: List[str] = []

        for idx, q in enumerate(questions, 1):
            disp_no = q.get("display_no") or q.get("question_no") or q.get("display_order") or idx
            corr_key = (
                q.get("display_correct_key")
                or q.get("correct_key")
                or q.get("canonical_correct_key")
                or "A"
            )
            row1.append(f"[*Câu {disp_no}*]")
            row2.append(f"[*{corr_key}*]")

        # Break into chunks of 10 columns
        chunk_size = 10
        table_blocks: List[str] = []
        for c_idx in range(0, len(questions), chunk_size):
            chunk_r1 = row1[c_idx : c_idx + chunk_size]
            chunk_r2 = row2[c_idx : c_idx + chunk_size]
            curr_cols = f"({', '.join(['1fr'] * len(chunk_r1))})"
            t_block = (
                f"#table(\n"
                f"  columns: {curr_cols},\n"
                f"  align: center,\n"
                f"  {', '.join(chunk_r1)},\n"
                f"  {', '.join(chunk_r2)}\n"
                f")"
            )
            table_blocks.append(t_block)

        answer_table_markup = "\n#v(4pt)\n".join(table_blocks)

        # 2. Build Detailed Solutions
        sol_blocks: List[str] = []
        for idx, q in enumerate(questions, 1):
            disp_no = q.get("display_no") or q.get("question_no") or q.get("display_order") or idx
            corr_key = (
                q.get("display_correct_key")
                or q.get("correct_key")
                or q.get("canonical_correct_key")
                or "A"
            )
            raw_stem = q.get("content") or q.get("canonical_content") or q.get("stem") or ""
            stem = convert_markdown_to_typst(raw_stem)
            raw_sol = (
                q.get("solution_md") or q.get("canonical_solution_md") or q.get("solution") or ""
            )
            sol_typst = convert_markdown_to_typst(raw_sol)

            sol_block = (
                f"#block(breakable: false)[\n"
                f"  *Câu {disp_no} (Đáp án {corr_key}):* {stem}\n"
                f"  #v(3pt)\n"
                f'  #text(style: "italic")[*Lời giải chi tiết:*]\n'
                f"  #v(2pt)\n"
                f"  {sol_typst}\n"
                f"]\n"
                f"#v(4pt)\n"
                f"#line(length: 100%, stroke: 0.5pt + luma(200))\n"
                f"#v(4pt)"
            )
            sol_blocks.append(sol_block)

        solutions_content = "\n".join(sol_blocks)

        template = f"""// Auto-generated Solution Document
#set document(title: "{clean_title_meta}", author: "Isomorphic Exam Synthesizer")
#set page(
  paper: "a4",
  margin: (top: 2cm, bottom: 2cm, left: 2cm, right: 2cm),
  footer: locate(loc => {{
    let p = counter(page).at(loc).first()
    let t = counter(page).final(loc).first()
    align(center)[#text(size: 9pt, fill: luma(100))[Trang #p / #t]]
  }})
)
#set text(font: ("Liberation Serif", "Times New Roman", "DejaVu Serif"), size: 11pt, lang: "vi")
#set par(justify: true, leading: 0.7em)

#align(center)[
  #text(weight: "bold", size: 14pt)[{clean_title_display}]\\
  #text(weight: "bold", size: 12pt)[MÃ ĐỀ THI: {clean_version_display}]\\
  #text(style: "italic", size: 10pt)[(Hệ thống tự động biên dịch và đối soát ma trận đáp án)]
]

#v(8pt)
#line(length: 100%, stroke: 1pt)
#v(10pt)

#text(weight: "bold", size: 12pt)[I. BẢNG ĐÁP ÁN NHANH]
#v(6pt)

{answer_table_markup}

#v(16pt)

#text(weight: "bold", size: 12pt)[II. LỜI GIẢI CHI TIẾT TỪNG CÂU]
#v(8pt)

{solutions_content}
"""
        return template

    def render_answers_matrix_document(
        self,
        versions_matrix: Sequence[Dict[str, Any]],
        exam_title: str = "BẢNG MA TRẬN ĐÁP ÁN TOÀN KHÓA",
        subject: str = "Toán học",
    ) -> str:
        """
        Generate complete Typst source code for cross-version answers matrix (TASK-306 / TASK-305).

        Args:
            versions_matrix: Sequence of version dicts, each containing:
                - version_code / code: str (e.g. "101", "102")
                - answer_keys: mapping from question_no (int or str) to correct_key (str)
                  OR list of questions/keys with display_no and display_correct_key
            exam_title: Document title.
            subject: Subject name.
        """
        clean_title_meta = _clean_typst_string(exam_title)
        clean_title_display = escape_typst_text(exam_title)
        clean_subject_display = escape_typst_text(subject)

        # Normalize version codes and their answer mappings
        version_data: List[Tuple[str, Dict[int, str]]] = []
        max_q_num = 0

        for v in versions_matrix:
            v_code = str(v.get("version_code") or v.get("code") or "101")
            raw_keys = v.get("answer_keys") or v.get("keys") or []
            q_map: Dict[int, str] = {}

            if isinstance(raw_keys, dict):
                for q_str, k in raw_keys.items():
                    try:
                        q_i = int(q_str)
                        q_map[q_i] = str(k)
                        if q_i > max_q_num:
                            max_q_num = q_i
                    except (ValueError, TypeError):
                        continue
            elif isinstance(raw_keys, (list, tuple)):
                for idx, item in enumerate(raw_keys, 1):
                    if isinstance(item, dict):
                        q_i = int(item.get("display_no") or item.get("question_no") or idx)
                        k = str(item.get("display_correct_key") or item.get("correct_key") or "A")
                        q_map[q_i] = k
                        if q_i > max_q_num:
                            max_q_num = q_i
                    elif isinstance(item, str):
                        q_map[idx] = item
                        if idx > max_q_num:
                            max_q_num = idx

            version_data.append((v_code, q_map))

        if max_q_num == 0:
            max_q_num = 1

        # Build table header
        num_v = len(version_data)
        col_specs = ["1.2fr"] + ["1fr"] * num_v
        cols_str = f"({', '.join(col_specs)})"

        headers = ["[#text(weight: 'bold')[Câu]]"] + [
            f"[#text(weight: 'bold')[Mã {escape_typst_text(vc)}]]" for vc, _ in version_data
        ]
        table_rows = [", ".join(headers)]

        # Build rows for each question
        for q_i in range(1, max_q_num + 1):
            row_items = [f"[#text(weight: 'bold')[Câu {q_i}]]"]
            for _, q_map in version_data:
                k = q_map.get(q_i, "-")
                row_items.append(f"[{escape_typst_text(k)}]")
            table_rows.append(", ".join(row_items))

        table_body = ",\n  ".join(table_rows)

        template = f"""// Auto-generated Answers Matrix Document
#set document(title: "{clean_title_meta}", author: "Isomorphic Exam Synthesizer")
#set page(
  paper: "a4",
  margin: (top: 2cm, bottom: 2cm, left: 2cm, right: 2cm),
  footer: locate(loc => {{
    let p = counter(page).at(loc).first()
    let t = counter(page).final(loc).first()
    align(center)[#text(size: 9pt, fill: luma(100))[Trang #p / #t]]
  }})
)
#set text(font: ("Liberation Serif", "Times New Roman", "DejaVu Serif"), size: 11pt, lang: "vi")
#set par(justify: true, leading: 0.7em)

#align(center)[
  #text(weight: "bold", size: 14pt)[{clean_title_display}]\\
  #text(weight: "bold", size: 12pt)[Môn: {clean_subject_display}]\\
  #text(style: "italic", size: 10pt)[(Bảng ma trận đối soát đáp án tất cả các phiên bản đề thi)]
]

#v(8pt)
#line(length: 100%, stroke: 1pt)
#v(10pt)

#align(center)[
  #table(
    columns: {cols_str},
    align: center,
    {table_body}
  )
]

#v(16pt)
#align(center)[
  #text(size: 9pt, style: "italic")[Hệ thống Isomorphic Exam Synthesizer - Bảng ma trận đối soát đáp án chính thức]
]
"""
        return template

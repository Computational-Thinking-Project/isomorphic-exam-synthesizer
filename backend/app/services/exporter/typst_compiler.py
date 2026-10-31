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
from typing import Any, Dict, List, Optional, Sequence

from app.services.exporter.exceptions import (
    TypstCompilationError,
    TypstNotFoundError,
    TypstTimeoutError,
)
from app.services.exporter.typst_converter import convert_markdown_to_typst

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
            TypstNotFoundError: If the Typst CLI is missing.
            TypstTimeoutError: If execution exceeds configured timeout (30s).
            TypstCompilationError: If compilation fails or output is not a valid PDF.
        """
        if not self.is_available():
            raise TypstNotFoundError(binary_path=self.binary_path)

        with tempfile.TemporaryDirectory(prefix="typst_export_") as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.typ")
            output_path = os.path.join(tmp_dir, output_filename)

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
        """
        q_blocks: List[str] = []
        labels = ["A", "B", "C", "D"]

        for idx, q in enumerate(questions, 1):
            disp_no = q.get("display_no", idx)
            stem = convert_markdown_to_typst(q.get("content", ""))
            opts = q.get("options", ["", "", "", ""])

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
#set document(title: [{exam_title}], author: [Isomorphic Exam Synthesizer])
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
    #text(weight: "bold")[{exam_title}]\\
    #text(weight: "bold")[Môn: {subject}]\\
    #text(weight: "bold", size: 12pt)[MÃ ĐỀ THI: {version_code}]
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
        """
        # 1. Build Answer Matrix Table (columns of 10)
        table_cells: List[str] = []
        for q in questions:
            disp_no = q.get("display_no", 1)
            corr_key = q.get("display_correct_key") or q.get("canonical_correct_key", "A")
            table_cells.append(f"[*Câu {disp_no}*], [*{corr_key}*]")

        # Group table cells in blocks of 5 or 10 columns
        row1 = [f"[*Câu {q.get('display_no', i + 1)}*]" for i, q in enumerate(questions)]
        row2 = [
            f"[*{q.get('display_correct_key') or q.get('canonical_correct_key', 'A')}*]"
            for q in questions
        ]

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
            disp_no = q.get("display_no", idx)
            corr_key = q.get("display_correct_key") or q.get("canonical_correct_key", "A")
            stem = convert_markdown_to_typst(q.get("content", ""))
            sol_md = q.get("solution_md") or q.get("canonical_solution_md") or ""
            sol_typst = convert_markdown_to_typst(sol_md)

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
#set document(title: [{exam_title}], author: [Isomorphic Exam Synthesizer])
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
  #text(weight: "bold", size: 14pt)[{exam_title}]\\
  #text(weight: "bold", size: 12pt)[MÃ ĐỀ THI: {version_code}]\\
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

"""
Unit Test Suite for Typst Subprocess PDF Compiler Engine (TASK-306).

Verifies:
1. Standardized PDF filename generator conforming to W3_ASSIGNMENT.md#L41.
2. Compiler error sanitization (preventing sensitive OS path disclosure).
3. LaTeX-to-Typst math syntax converter (including control word boundary (?![a-zA-Z])).
4. Markdown-to-Typst markup converter with math boundary preservation and code injection escaping.
5. TypstCompiler subprocess runner:
   - Successful compilation with magic byte validation (b"%PDF-").
   - Strict 30s timeout enforcement (TypstTimeoutError).
   - Compilation error reporting with sanitized error diagnostics (TypstCompilationError).
   - Corrupted non-PDF output rejection.
   - Missing binary detection (TypstNotFoundError).
   - Subprocess safety verification (shell=False).
   - Output filename isolation and directory traversal rejection (F04).
6. Document layout renderers:
   - Exam paper document with string author metadata (F01).
   - Solution paper document with string author metadata (F01).
   - Cross-version answers matrix document (Contract Q2).
   - Persisted question model adapter (Contract Q1).
7. Real CLI compilation integration test (conditionally executed if typst binary is present).
"""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from app.services.exporter.bundle_models import (
    ApprovedExportSnapshot,
    DisplayQuestion,
    DisplayVersion,
)
from app.services.exporter.exceptions import (
    TypstCompilationError,
    TypstNotFoundError,
    TypstTimeoutError,
)
from app.services.exporter.export_pipeline import build_compiled_bundle
from app.services.exporter.typst_compiler import (
    PDF_MAGIC_BYTES,
    TypstCompiler,
    generate_pdf_filename,
    sanitize_compiler_error,
)
from app.services.exporter.typst_converter import (
    convert_markdown_to_typst,
    escape_typst_text,
    latex_math_to_typst,
)


class TestPdfFilenameGenerator:
    def test_exam_paper_filename_convention(self):
        assert generate_pdf_filename("exam", "101") == "exam_101.pdf"
        assert generate_pdf_filename("exam_paper", "102") == "exam_102.pdf"
        assert generate_pdf_filename("questions", "201") == "exam_201.pdf"

    def test_answers_matrix_filename_convention(self):
        assert generate_pdf_filename("matrix") == "answers_matrix.pdf"
        assert generate_pdf_filename("answers_matrix") == "answers_matrix.pdf"
        assert generate_pdf_filename("answer_keys") == "answers_matrix.pdf"

    def test_solution_paper_filename_convention(self):
        assert generate_pdf_filename("solution", "101") == "solutions_101.pdf"
        assert generate_pdf_filename("solutions", "102") == "solutions_102.pdf"
        assert generate_pdf_filename("solutions_detail", "201") == "solutions_201.pdf"

    def test_default_fallback_filename(self):
        assert generate_pdf_filename("custom", "999") == "custom_999.pdf"
        assert generate_pdf_filename("custom") == "custom.pdf"


class TestSanitizeCompilerError:
    def test_sanitize_temp_dir_paths(self):
        raw = "error: failed to load font at C:\\Users\\Administrator\\AppData\\Local\\Temp\\typst_xyz\\input.typ:12:4"
        temp_dir = "C:\\Users\\Administrator\\AppData\\Local\\Temp\\typst_xyz"
        sanitized = sanitize_compiler_error(raw, temp_dir=temp_dir)
        assert temp_dir not in sanitized
        assert "<working_dir>" in sanitized or "input.typ" in sanitized

    def test_sanitize_unix_temp_paths(self):
        raw = "error at /tmp/typst_export_12345/input.typ:5:10: unknown variable"
        sanitized = sanitize_compiler_error(raw, temp_dir="/tmp/typst_export_12345")
        assert "/tmp/typst_export_12345" not in sanitized
        assert "input.typ" in sanitized

    def test_empty_error_returns_fallback(self):
        assert "failed" in sanitize_compiler_error("")


class TestLatexMathToTypstConverter:
    def test_fractions_conversion(self):
        assert latex_math_to_typst(r"\frac{1}{2}") == "((1)/(2))"
        assert latex_math_to_typst(r"\dfrac{x + 1}{x - 1}") == "((x + 1)/(x - 1))"

    def test_nested_fractions_conversion(self):
        res = latex_math_to_typst(r"\frac{\frac{1}{2}}{3}")
        assert "((((1)/(2)))/(3))" in res

    def test_square_roots_conversion(self):
        assert latex_math_to_typst(r"\sqrt{16}") == "sqrt(16)"
        assert latex_math_to_typst(r"\sqrt{x^2 + 1}") == "sqrt(x^2 + 1)"
        assert latex_math_to_typst(r"\sqrt{x^{2} + 1}") == "sqrt(x^(2) + 1)"
        assert latex_math_to_typst(r"\sqrt[3]{8}") == "root(3, 8)"

    def test_text_and_symbols_conversion(self):
        latex = r"\text{cm} \cdot \text{s}^{-1} \le 10 \implies x \in [0; 1]"
        converted = latex_math_to_typst(latex)
        assert '"cm"' in converted
        assert '"s"' in converted
        assert "<=" in converted
        assert "=>" in converted
        assert "in" in converted

    def test_greek_letters_and_functions(self):
        latex = r"\sin(\alpha) + \cos(\pi) + \ln(x) = \Delta"
        converted = latex_math_to_typst(latex)
        assert "sin" in converted
        assert "alpha" in converted
        assert "cos" in converted
        assert "pi" in converted
        assert "ln" in converted
        assert "Delta" in converted

    def test_bracket_removal(self):
        latex = r"\left( \frac{a}{b} \right)"
        converted = latex_math_to_typst(latex)
        assert r"\left" not in converted
        assert r"\right" not in converted
        assert "((a)/(b))" in converted


class TestConvertMarkdownToTypst:
    def test_inline_math_preserved_and_converted(self):
        md = r"Cho phương trình $2x - \sqrt{4} = 0$, tìm $x$."
        typst = convert_markdown_to_typst(md)
        assert "$2x - sqrt(4) = 0$" in typst
        assert "$x$" in typst

    def test_display_math_converted_to_block_math(self):
        md = "Giải phương trình:\n$$\\frac{x^2 - 1}{x + 1} = 0$$\nTìm tập nghiệm."
        typst = convert_markdown_to_typst(md)
        assert " $ ((x^2 - 1)/(x + 1)) = 0 $ " in typst

    def test_parentheses_and_bracket_math_delimiters(self):
        md = r"Ta có \(x \le 2\) và \[x \ge 0\]."
        typst = convert_markdown_to_typst(md)
        assert "$x <= 2$" in typst
        assert " $ x >= 0 $ " in typst

    def test_markdown_bold_and_escaping(self):
        md = "**Câu 1:** Đề số #1 do @admin tạo với giá $100."
        typst = convert_markdown_to_typst(md)
        assert "*Câu 1:*" in typst
        assert r"\#1" in typst
        assert r"\@admin" in typst

    def test_empty_string(self):
        assert convert_markdown_to_typst("") == ""
        assert escape_typst_text("") == ""


class TestReviewerFindingsF01ToF04:
    def test_f01_author_metadata_is_string(self):
        """F01: Typst 0.11.1 requires author to be a string or array of strings, not content."""
        compiler = TypstCompiler()
        exam_typst = compiler.render_exam_document("101", [])
        assert 'author: "Isomorphic Exam Synthesizer"' in exam_typst
        assert "author: [" not in exam_typst

        sol_typst = compiler.render_solution_document("101", [])
        assert 'author: "Isomorphic Exam Synthesizer"' in sol_typst
        assert "author: [" not in sol_typst

        matrix_typst = compiler.render_answers_matrix_document([])
        assert 'author: "Isomorphic Exam Synthesizer"' in matrix_typst

    def test_f01_template_files_author_is_string(self):
        """F01: templates/exam.typ and templates/solution.typ must not use [content] for author."""
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app",
            "services",
            "exporter",
            "templates",
        )
        exam_path = os.path.join(templates_dir, "exam.typ")
        sol_path = os.path.join(templates_dir, "solution.typ")

        if os.path.exists(exam_path):
            with open(exam_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert 'author: "Isomorphic Exam Synthesizer"' in content
                assert "author: [" not in content

        if os.path.exists(sol_path):
            with open(sol_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert 'author: "Isomorphic Exam Synthesizer"' in content
                assert "author: [" not in content

    def test_f02_latex_control_word_boundary_adjacent_tokens(self):
        """F02: Regex must match control word boundaries (?![a-zA-Z]) and preserve token separation."""
        # 1. \pm followed immediately by digit 2
        res1 = convert_markdown_to_typst(r"$x=\pm2$")
        assert "plus.minus 2" in res1
        assert "pm2" not in res1

        # 2. \in preceded immediately by variable x and followed by [
        res2 = convert_markdown_to_typst(r"$x\in[0;1]$")
        assert "x in [0;1]" in res2
        assert "xin" not in res2

        # 3. \le followed immediately by digits
        res3 = convert_markdown_to_typst(r"$x\le10$")
        assert "<= 10" in res3

        # 4. Function followed immediately by digit
        res4 = convert_markdown_to_typst(r"$\sin2x$")
        assert "sin 2x" in res4

        # 5. Greek letter preceded immediately by coefficient
        res5 = convert_markdown_to_typst(r"$2\alpha$")
        assert "2 alpha" in res5

    def test_f03_typst_code_injection_prevention_prose(self):
        """F03: Backslash followed by # in prose must not execute code."""
        prose = "\\" + '#panic("REVIEW_MARKER")'
        converted = convert_markdown_to_typst(prose)
        # Pre-existing backslash is escaped to \\ and hash is escaped to \#
        # In memory: converted starts with r"\\\#" (literal \\ followed by \#)
        assert converted.startswith("\\\\\\#")
        # Ensure # is escaped so Typst treats it as text, not code invocation
        assert r"\#panic" in converted

    def test_f03_typst_code_injection_prevention_math(self):
        """F03: # in math mode must be neutralized so Typst does not execute embedded code."""
        math_content = '$#panic("REVIEW_MARKER")$'
        converted = convert_markdown_to_typst(math_content)
        # Hash is converted to symbol 'hash' and code keywords are stripped
        assert "#" not in converted
        assert "panic" not in converted

    def test_f03_method_chaining_code_injection_prevention_math(self):
        """F03: Chained method calls on escaped hash in math must not execute code."""
        payload = r'$\#.replace("", panic("REVIEW_MARKER"))$'
        source = convert_markdown_to_typst(payload)
        assert "#" not in source
        assert "panic" not in source
        assert ".replace" not in source

    def test_f05_answers_matrix_uses_double_quotes_for_bold(self):
        """F05: Typst requires double quotes for string literals; single quotes 'bold' cause compile error."""
        compiler = TypstCompiler()
        source = compiler.render_answers_matrix_document(
            [
                {"version_code": "101", "answer_keys": {1: "A", 2: "C"}},
                {"version_code": "102", "answer_keys": {1: "B", 2: "D"}},
            ]
        )
        assert "'bold'" not in source
        assert 'weight: "bold"' in source

    def test_f06_decimal_coefficients_preserved_with_parentheses(self):
        """F06: Decimal numbers preceding parentheses must not be corrupted by method call filter."""
        assert convert_markdown_to_typst("$0.5(x+1)$") == "$0.5(x+1)$"
        assert convert_markdown_to_typst("$1.25(x-2)$") == "$1.25(x-2)$"
        assert convert_markdown_to_typst("$0.5 (x + 1)$") == "$0.5 (x + 1)$"
        assert convert_markdown_to_typst("$3.14159(r^2)$") == "$3.14159(r^2)$"

    def test_f03_metadata_code_injection_prevention(self):
        """F03: Metadata titles with quotes and code markers must be escaped."""
        compiler = TypstCompiler()
        malicious_title = 'Exam " #panic("PWN") \\'
        exam_typst = compiler.render_exam_document("101", [], exam_title=malicious_title)
        # Quotes and backslashes in title must be escaped inside string literal
        assert 'title: "Exam \\" #panic(\\"PWN\\") \\\\"' in exam_typst
        # In document body, the display title must escape # to \#
        assert r"\#panic" in exam_typst

    def test_f04_compile_document_output_filename_validation(self):
        """F04: Reject absolute paths, directory traversal, and non-pdf filenames."""
        compiler = TypstCompiler()
        with patch.object(compiler, "is_available", return_value=True):
            # Absolute paths
            with pytest.raises(ValueError, match="path separators"):
                compiler.compile_document("= Doc", output_filename="/tmp/evil.pdf")

            with pytest.raises(ValueError, match="path separators"):
                compiler.compile_document("= Doc", output_filename="C:\\evil.pdf")

            # Directory traversal
            with pytest.raises(ValueError, match="path separators|traversal"):
                compiler.compile_document("= Doc", output_filename="../evil.pdf")

            with pytest.raises(ValueError, match="path separators"):
                compiler.compile_document("= Doc", output_filename="evidence/escaped-output.pdf")

            # Non-pdf filenames
            with pytest.raises(ValueError, match="must end with '.pdf'"):
                compiler.compile_document("= Doc", output_filename="evil.exe")

            with pytest.raises(ValueError, match="must be a non-empty string"):
                compiler.compile_document("= Doc", output_filename="")


class TestPersistedDataAdapterAndAnswersMatrix:
    def test_persisted_keys_adapter_in_exam_renderer(self):
        """Contract Q1: Accepts persisted question models with question_no, stem, canonical_options."""
        compiler = TypstCompiler()
        questions = [
            {
                "question_no": 1,
                "stem": "Phương trình $x+1=0$ có nghiệm là:",
                "canonical_options": ["-1", "1", "2", "3"],
            }
        ]
        typst = compiler.render_exam_document("101", questions)
        assert "*Câu 1:*" in typst
        assert "$x+1=0$" in typst
        assert "*A.* -1" in typst

    def test_persisted_keys_adapter_in_solution_renderer(self):
        """Contract Q1: Accepts persisted question models with correct_key and canonical_solution_md."""
        compiler = TypstCompiler()
        questions = [
            {
                "question_no": 1,
                "correct_key": "B",
                "stem": "Cho $x=2$.",
                "canonical_solution_md": "Lời giải chi tiết: chọn B.",
            }
        ]
        typst = compiler.render_solution_document("101", questions)
        assert "*Câu 1 (Đáp án B):*" in typst
        assert "Lời giải chi tiết: chọn B." in typst

    def test_render_answers_matrix_document(self):
        """Contract Q2: Callable render_answers_matrix_document produces cross-version answers matrix."""
        compiler = TypstCompiler()
        versions = [
            {
                "version_code": "101",
                "answer_keys": {1: "A", 2: "B", 3: "C", 4: "D"},
            },
            {
                "version_code": "102",
                "answer_keys": {1: "B", 2: "C", 3: "D", 4: "A"},
            },
        ]
        typst = compiler.render_answers_matrix_document(versions)
        assert 'author: "Isomorphic Exam Synthesizer"' in typst
        assert "Mã 101" in typst
        assert "Mã 102" in typst
        assert "Câu 1" in typst
        assert "Câu 4" in typst


class TestTypstCompilerSubprocess:
    @patch("shutil.which")
    def test_is_available_checks_path(self, mock_which):
        mock_which.return_value = "/usr/local/bin/typst"
        compiler = TypstCompiler()
        assert compiler.is_available() is True

        mock_which.return_value = None
        assert compiler.is_available() is False

    @patch("shutil.which", return_value=None)
    def test_compile_raises_not_found_when_binary_missing(self, mock_which):
        compiler = TypstCompiler(binary_path="typst")
        with pytest.raises(TypstNotFoundError) as exc_info:
            compiler.compile_document("= Hello World")
        assert "not found" in str(exc_info.value).lower()

    @patch("shutil.which", return_value="/usr/local/bin/typst")
    @patch("subprocess.run")
    def test_compile_successful_pdf(self, mock_run, mock_which):
        def fake_run(cmd, **kwargs):
            assert kwargs.get("shell") is False
            assert kwargs.get("timeout") == 30.0
            out_file = cmd[3]
            with open(out_file, "wb") as f:
                f.write(b"%PDF-1.4\n%Fake PDF content for test\n%%EOF")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run

        compiler = TypstCompiler(timeout=30.0)
        pdf_bytes = compiler.compile_document("= Tiêu đề đề thi", output_filename="exam_101.pdf")

        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(PDF_MAGIC_BYTES)
        assert b"%PDF-1.4" in pdf_bytes

    @patch("shutil.which", return_value="/usr/local/bin/typst")
    @patch("subprocess.run")
    def test_compile_timeout_expired(self, mock_run, mock_which):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["typst", "compile"], timeout=30.0)

        compiler = TypstCompiler(timeout=30.0)
        with pytest.raises(TypstTimeoutError) as exc_info:
            compiler.compile_document("= Stalling document")

        assert exc_info.value.timeout_seconds == 30.0
        assert "timed out after 30.0 seconds" in str(exc_info.value)

    @patch("shutil.which", return_value="/usr/local/bin/typst")
    @patch("subprocess.run")
    def test_compile_syntax_error_sanitization(self, mock_run, mock_which):
        raw_err = "error at /tmp/typst_export_test/input.typ:3:1: unexpected token '##'"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["typst", "compile"],
            returncode=1,
            stdout="",
            stderr=raw_err,
        )

        compiler = TypstCompiler()
        with pytest.raises(TypstCompilationError) as exc_info:
            compiler.compile_document("= Document with syntax error")

        err = exc_info.value
        assert err.exit_code == 1
        assert "unexpected token" in str(err)
        assert "/tmp/typst_export_test" not in str(err)

    @patch("shutil.which", return_value="/usr/local/bin/typst")
    @patch("subprocess.run")
    def test_compile_corrupted_output_missing_magic_bytes(self, mock_run, mock_which):
        def fake_run(cmd, **kwargs):
            out_file = cmd[3]
            with open(out_file, "wb") as f:
                f.write(b"<html><body>502 Bad Gateway</body></html>")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run

        compiler = TypstCompiler()
        with pytest.raises(TypstCompilationError) as exc_info:
            compiler.compile_document("= Document returning html instead of pdf")

        assert "not a valid PDF" in str(exc_info.value)


class TestDocumentLayoutRenderers:
    def test_render_exam_document_structure(self):
        compiler = TypstCompiler()
        questions = [
            {
                "display_no": 1,
                "content": r"Phương trình $x^2 - 4 = 0$ có nghiệm là:",
                "options": ["$x = 2$", "$x = -2$", "$x = \\pm 2$", "$x = 0$"],
            },
            {
                "display_no": 2,
                "content": r"Cho tam giác ABC có AB = 3, AC = 4.",
                "options": ["5", "6", "7", "8"],
            },
        ]

        typst_code = compiler.render_exam_document(
            version_code="101",
            questions=questions,
            exam_title="ĐỀ THI TOÁN HỌC KỲ I",
        )

        assert "MÃ ĐỀ THI: 101" in typst_code
        assert "ĐỀ THI TOÁN HỌC KỲ I" in typst_code
        assert "Họ và tên thí sinh:" in typst_code
        assert "*Câu 1:*" in typst_code
        assert "*Câu 2:*" in typst_code
        assert "*A.*" in typst_code
        assert "*B.*" in typst_code
        assert "*C.*" in typst_code
        assert "*D.*" in typst_code
        assert "HẾT" in typst_code

    def test_render_solution_document_structure(self):
        compiler = TypstCompiler()
        questions = [
            {
                "display_no": 1,
                "display_correct_key": "C",
                "content": r"Phương trình $x^2 - 4 = 0$ có nghiệm là:",
                "solution_md": r"Phương trình có 2 nghiệm $x = \pm 2$. Đáp án C: $x = \pm 2$",
            },
            {
                "display_no": 2,
                "display_correct_key": "A",
                "content": r"Tính tích phân $\int_0^1 x dx$.",
                "solution_md": "Ta có $\\int_0^1 x dx = 1/2$. Do đó chọn A.",
            },
        ]

        typst_code = compiler.render_solution_document(
            version_code="101",
            questions=questions,
        )

        assert "BẢNG ĐÁP ÁN NHANH" in typst_code
        assert "LỜI GIẢI CHI TIẾT TỪNG CÂU" in typst_code
        assert "MÃ ĐỀ THI: 101" in typst_code
        assert "*Câu 1 (Đáp án C):*" in typst_code
        assert "*Câu 2 (Đáp án A):*" in typst_code


class TestRealTypstIntegration:
    def test_real_typst_compile_if_installed(self):
        compiler = TypstCompiler()
        if not compiler.is_available():
            pytest.skip("Typst CLI is not installed on host PATH; skipping real compile test.")

        minimal_content = (
            '#set page(paper: "a4", margin: 2cm)\n'
            '#set text(lang: "vi")\n'
            "= Kiểm tra biên dịch Typst tiếng Việt\n"
            "Cho phương trình $x^2 - 4 = 0$.\n"
        )

        pdf_bytes = compiler.compile_document(minimal_content, output_filename="test_real.pdf")
        assert len(pdf_bytes) > 0
        assert pdf_bytes.startswith(PDF_MAGIC_BYTES)

    def test_real_typst_compile_full_exam_and_solution_documents(self):
        compiler = TypstCompiler()
        if not compiler.is_available():
            pytest.skip("Typst CLI is not installed on host PATH; skipping real compile test.")

        questions = [
            {
                "display_no": 1,
                "display_correct_key": "C",
                "content": r"Cho phương trình $x^2 - 4 = 0$ và $x \in [0; 2]$. Tìm $x = \pm 2$.",
                "options": ["$x = 2$", "$x = -2$", "$x = \\pm 2$", "$x = 0$"],
                "solution_md": r"Phương trình có 2 nghiệm $x = \pm 2$. Do $x \in [0; 2]$, chọn C: $x = 2$.",
            }
        ]
        exam_src = compiler.render_exam_document("101", questions)
        exam_pdf = compiler.compile_document(exam_src, "exam_101.pdf")
        assert exam_pdf.startswith(PDF_MAGIC_BYTES)

        sol_src = compiler.render_solution_document("101", questions)
        sol_pdf = compiler.compile_document(sol_src, "solutions_101.pdf")
        assert sol_pdf.startswith(PDF_MAGIC_BYTES)

    def test_real_typst_compile_answers_matrix_document(self):
        compiler = TypstCompiler()
        if not compiler.is_available():
            pytest.skip("Typst CLI is not installed on host PATH; skipping real compile test.")

        versions = [
            {"version_code": "101", "answer_keys": {1: "A", 2: "C", 3: "B", 4: "D"}},
            {"version_code": "102", "answer_keys": {1: "B", 2: "D", 3: "A", 4: "C"}},
            {"version_code": "103", "answer_keys": {1: "C", 2: "A", 3: "D", 4: "B"}},
        ]
        matrix_src = compiler.render_answers_matrix_document(versions)
        matrix_pdf = compiler.compile_document(matrix_src, "answers_matrix.pdf")
        assert matrix_pdf.startswith(PDF_MAGIC_BYTES)

    def test_real_typst_compile_f03_neutralized_payload(self):
        compiler = TypstCompiler()
        if not compiler.is_available():
            pytest.skip("Typst CLI is not installed on host PATH; skipping real compile test.")

        payload = r'$\#.replace("", panic("REVIEW_MARKER"))$'
        source = (
            '#set page(paper: "a4")\n'
            "= Test F03 Neutralization\n"
            f"{convert_markdown_to_typst(payload)}\n"
        )
        pdf_bytes = compiler.compile_document(source, "f03_test.pdf")
        assert pdf_bytes.startswith(PDF_MAGIC_BYTES)

    def test_real_typst_compile_f06_decimal_expressions(self):
        compiler = TypstCompiler()
        if not compiler.is_available():
            pytest.skip("Typst CLI is not installed on host PATH; skipping real compile test.")

        payload = "$0.5(x+1) + 1.25(x-2) = 0$"
        source = (
            '#set page(paper: "a4")\n'
            "= Test F06 Decimal Expressions\n"
            f"{convert_markdown_to_typst(payload)}\n"
        )
        pdf_bytes = compiler.compile_document(source, "f06_test.pdf")
        assert pdf_bytes.startswith(PDF_MAGIC_BYTES)

    def test_real_typst_compile_golden_snapshot_bundle(self):
        compiler = TypstCompiler()
        if not compiler.is_available():
            pytest.skip("Typst CLI is not installed on host PATH; skipping real compile test.")

        fixture_path = (
            Path(__file__).resolve().parents[1] / "fixtures" / "w4_preview_snapshot_fixture.json"
        )
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        snapshot = ApprovedExportSnapshot(
            session_id=raw["session_id"],
            revision="golden-rev-1",
            title="Golden Renderer Regression Exam",
            status="approved",
            versions=tuple(
                DisplayVersion(
                    code=ver["version_code"],
                    questions=tuple(
                        DisplayQuestion(
                            id=q["id"],
                            question_no=q["question_no"],
                            content=q["content"],
                            options=tuple(q["options"]),
                            correct_key=q["correct_key"],
                            solution_md=q["solution_md"],
                            status=q["status"],
                        )
                        for q in ver["questions"]
                    ),
                )
                for ver in raw["versions"]
            ),
        )

        bundle = build_compiled_bundle(snapshot, compiler=compiler)
        assert bundle.size_bytes > 0
        from io import BytesIO

        with ZipFile(BytesIO(bundle.data), "r") as zf:
            names = set(zf.namelist())
            root = f"exam_bundle_{snapshot.session_id}"
            for expected_pdf in (
                f"{root}/pdf/exam_101.pdf",
                f"{root}/pdf/exam_102.pdf",
                f"{root}/pdf/solutions_101.pdf",
                f"{root}/pdf/solutions_102.pdf",
                f"{root}/pdf/answers_matrix.pdf",
            ):
                assert expected_pdf in names
                data = zf.read(expected_pdf)
                assert data.startswith(PDF_MAGIC_BYTES)

    def test_real_typst_compile_golden_empty_solutions_and_extended_math(self):
        compiler = TypstCompiler()
        if not compiler.is_available():
            pytest.skip("Typst CLI is not installed on host PATH; skipping real compile test.")

        fixture_path = (
            Path(__file__).resolve().parents[1] / "fixtures" / "w4_preview_snapshot_fixture.json"
        )
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        empty_questions = [
            {
                "question_no": q["question_no"],
                "correct_key": q["correct_key"],
                "content": q["content"],
                "options": q["options"],
                "solution_md": "",
            }
            for q in raw["versions"][0]["questions"]
        ]
        sol_empty_src = compiler.render_solution_document("101", empty_questions)
        sol_empty_pdf = compiler.compile_document(sol_empty_src, "golden_solutions_empty.pdf")
        assert sol_empty_pdf.startswith(PDF_MAGIC_BYTES)

        extended_payload = "\n\n".join(
            [
                r"Tich phan: $I = \int_{0}^{1} (3x^2 + 2x) dx + \iint_{D} f(x,y)\,dx\,dy$.",
                r"Toa do: $Oxyz$, doan $AB$, diem $IN$, khoang cach $\overline{AB}$, $\vec{CD}$, $\hat{x}$, $\bar{y}$, $\ddot{z}$.",
                r"Tong va gioi han: $\sum_{k=1}^{n} k^2$, $\prod_{i=1}^{n} a_i$, $\lim_{x \to 0} \frac{\sin x}{x} = 1$, $\sin^2 x + \cos^2 x = 1$.",
                r"Tap hop va ky hieu: $x \in \mathbb{R} \setminus \{0\}$, $A \subseteq B$, $A \cong B$, $A \sim B$, $a \propto b$, $90^\circ$, $\angle ABC$, $\triangle ABC$, $d \perp \Delta$, $d \parallel d'$, $\langle u, v \rangle$, $\lVert u \rVert$, $\cdots$, $\vdots$, $\ddots$, $5\,\mathrm{cm} + 2\,\mathrm{kg} + 3\,\mathrm{km} + \mathrm{cm}^2 + \mathrm{cm^2}$, $\text{don vi } 5\,\text{cm}$.",
                r"He phuong trinh va ma tran: $\begin{cases} x + y = 1 \\ x - y = 3 \end{cases}$, $\begin{cases}x^2 & x\ge 0\\-x & x<0\end{cases}$, $\begin{alignedat}{2}x&=1 & y&=2\\z&=3 & t&=4\end{alignedat}$ va $\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}$.",
                r"Fallback unknown macro: $\unknownmacro + x$.",
            ]
        )
        ext_src = (
            '#set page(paper: "a4")\n'
            "= Extended Math Coverage\n"
            f"{convert_markdown_to_typst(extended_payload)}\n"
        )
        ext_pdf = compiler.compile_document(ext_src, "extended_math.pdf")
        assert ext_pdf.startswith(PDF_MAGIC_BYTES)


class TestGoldenAndExtendedMathConverter:
    def test_golden_integral_and_differential_conversion(self):
        out = latex_math_to_typst(r"I = \int_{0}^{1} (3x^2 + 2x) dx")
        assert out == "I = integral_(0)^(1) (3x^2 + 2x) d x"
        assert r"\int" not in out
        assert "dx" not in out

    def test_golden_multiletter_geometry_coordinates_split_cleanly(self):
        assert latex_math_to_typst("Oxyz") == "O x y z"
        assert latex_math_to_typst("ABC") == "A B C"
        # Case sensitivity prevents colliding uppercase point names with Typst lowercase keywords.
        assert latex_math_to_typst("IN") == "I N"
        assert latex_math_to_typst("AND") == "A N D"
        assert latex_math_to_typst(r"x \in \mathbb{R} \setminus \{0\}") == r"x in bb(R) without \{0\}"

    def test_big_operators_trig_powers_and_limits(self):
        assert latex_math_to_typst(r"\iint_{D} f(x, y)\,dx\,dy") == "integral.double_(D) f(x, y) d x d y"
        assert latex_math_to_typst(r"\sum_{k=1}^{n} k^2") == "sum_(k=1)^(n) k^2"
        assert latex_math_to_typst(r"\prod_{i=1}^{n} a_i") == "product_(i=1)^(n) a_i"
        assert latex_math_to_typst(r"\lim_{x \to 0} \frac{\sin x}{x} = 1") == "lim_(x -> 0) ((sin x)/(x)) = 1"
        assert latex_math_to_typst(r"\sin^2 x + \cos^2 x = 1") == "sin^2 x + cos^2 x = 1"

    def test_accents_environments_text_escaping_and_unknown_fallback(self):
        assert (
            latex_math_to_typst(r"\overline{AB} + \vec{CD} + \hat{x} + \bar{y} + \ddot{z}")
            == "overline(A B) + arrow(C D) + hat(x) + macron(y) + dot.double(z)"
        )
        assert latex_math_to_typst(r"\begin{cases} x + y = 1 \\ x - y = 3 \end{cases}") == "cases(x + y = 1, x - y = 3)"
        assert latex_math_to_typst(r"\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}") == "mat(1, 2; 3, 4)"
        assert latex_math_to_typst(r"\text{khi } dx > 0") == '"khi " d x > 0'
        assert latex_math_to_typst(r'\text{a "b"}') == r'"a \"b\""'
        assert latex_math_to_typst(r"\unknownmacro + x") == '"unknownmacro" + x'

    def test_security_and_decimal_invariants_preserved_with_integrals(self):
        malicious = latex_math_to_typst(r'\int_{0}^{1} \#.replace("", panic("REVIEW_MARKER")) dx')
        assert "#" not in malicious
        assert "panic" not in malicious
        assert ".replace" not in malicious
        assert "integral_(0)^(1)" in malicious
        assert "hash" in malicious
        assert "d x" in malicious

        decimal_out = latex_math_to_typst(r"\int_{0}^{1} 0.5(x+1) dx")
        assert "0.5(x+1)" in decimal_out
        assert "integral_(0)^(1)" in decimal_out
        assert "d x" in decimal_out

    def test_alignedat_consumes_alignment_count_argument_f82_01(self):
        # Regression for F82-01: \begin{alignedat}{n} mandatory {n} argument must be consumed
        # and must not leak into the generated Typst equations as stray numbers.
        raw = r"\begin{alignedat}{2}x&=1 & y&=2\\z&=3 & t&=4\end{alignedat}"
        converted = latex_math_to_typst(raw)
        assert converted == r"x & =1 & y & =2 \ z & =3 & t & =4"
        assert "{2}" not in converted
        # Ensure '2' only appears as the value assigned to y, not at the beginning of x
        assert converted.startswith("x")

        # Test with spaces and different column counts
        raw_spaces = r"\begin{alignedat} { 3 } a &= 10 & b &= 20 & c &= 30 \\ d &= 40 & e &= 50 & f &= 60 \end{alignedat}"
        converted_spaces = latex_math_to_typst(raw_spaces)
        assert "{ 3 }" not in converted_spaces
        assert "{3}" not in converted_spaces
        assert "3 " not in converted_spaces.split("&")[0]
        assert converted_spaces.startswith("a")
        assert "\\" in converted_spaces

        # Test with optional [t] / [b] / [c] specifier
        raw_valign = r"\begin{alignedat}[t]{2} u &= v \\ w &= z \end{alignedat}"
        converted_valign = latex_math_to_typst(raw_valign)
        assert converted_valign == r"u & = v \ w & = z"
        assert "[t]" not in converted_valign
        assert "{2}" not in converted_valign

    def test_cases_preserves_column_separation_f82_02(self):
        # Regression for F82-02: \begin{cases} must retain '&' alignment columns.
        assert (
            latex_math_to_typst(r"\begin{cases}x^2 & x\ge 0\\-x & x<0\end{cases}")
            == "cases(x^2 & x >= 0, -x & x<0)"
        )
        assert (
            latex_math_to_typst(
                r"\begin{cases} x^2 + 1 & \text{if } x \ge 0 \\ -x & \text{if } x < 0 \end{cases}"
            )
            == 'cases(x^2 + 1 & "if " x >= 0, -x & "if " x < 0)'
        )
        assert (
            latex_math_to_typst(r"\begin{cases} x + y = 1 \\ x - y = 3 \end{cases}")
            == "cases(x + y = 1, x - y = 3)"
        )

    def test_mathrm_preserves_unit_labels_f82_03(self):
        # Regression for F82-03: \mathrm{...} must preserve unit/text labels without splitting letters.
        assert latex_math_to_typst(r"\mathrm{cm}") == 'upright("cm")'
        assert latex_math_to_typst(r"\mathrm{kg}") == 'upright("kg")'
        assert latex_math_to_typst(r"\mathrm{km}") == 'upright("km")'
        assert latex_math_to_typst(r"5\,\mathrm{cm} + 2\,\mathrm{kg}") == '5 upright("cm") + 2 upright("kg")'
        assert latex_math_to_typst(r"\mathrm{cm}^2") == 'upright("cm")^2'
        assert latex_math_to_typst(r"\mathrm{cm^2}") == 'upright("cm"^2)'
        assert latex_math_to_typst(r"\mathrm{kg \cdot m/s^2}") == 'upright("kg" dot m/s^2)'


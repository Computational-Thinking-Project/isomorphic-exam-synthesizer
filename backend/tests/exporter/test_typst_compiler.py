"""
Unit Test Suite for Typst Subprocess PDF Compiler Engine (TASK-306).

Verifies:
1. Standardized PDF filename generator conforming to W3_ASSIGNMENT.md#L41.
2. Compiler error sanitization (preventing sensitive OS path disclosure).
3. LaTeX-to-Typst math syntax converter.
4. Markdown-to-Typst markup converter with math boundary preservation.
5. TypstCompiler subprocess runner:
   - Successful compilation with magic byte validation (b"%PDF-").
   - Strict 30s timeout enforcement (TypstTimeoutError).
   - Compilation error reporting with sanitized error diagnostics (TypstCompilationError).
   - Corrupted non-PDF output rejection.
   - Missing binary detection (TypstNotFoundError).
   - Subprocess safety verification (shell=False).
6. Document layout renderers (exam and solution documents).
7. Real CLI compilation integration test (conditionally executed if typst binary is present).
"""

import subprocess
from unittest.mock import patch

import pytest

from app.services.exporter.exceptions import (
    TypstCompilationError,
    TypstNotFoundError,
    TypstTimeoutError,
)
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
        # Simple fraction
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
        assert "sin(alpha)" in converted
        assert "cos(pi)" in converted
        assert "ln(x)" in converted
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
        # Simulate successful compilation and mock valid PDF bytes
        def fake_run(cmd, **kwargs):
            # Verify subprocess security constraints
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

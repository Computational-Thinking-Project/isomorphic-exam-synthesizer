"""ISSUE-92: guard against silently using the broken bundled fallback face.

The real PDF must embed the requested face, not merely compile. The synthetic
fixture is also rendered for visual QA; font selection alone cannot prove every
glyph's appearance. No PDF parser or QA dependency is added to the application.
"""

import re
import shutil
from pathlib import Path

import pytest

from app.services.exporter.typst_compiler import TypstCompiler

pytestmark = pytest.mark.skipif(shutil.which("typst") is None, reason="Typst unavailable")


def _embedded_faces(pdf: bytes) -> set[bytes]:
    # Typst 0.11.1 emits these PDF name objects outside compressed streams.
    return set(re.findall(rb"/BaseFont\s*/[A-Z]{6}\+([^\s/<>\[\]()]+)", pdf))


def test_vietnamese_fixture_embeds_real_regular_italic_bold_and_bold_italic_faces():
    source = (Path(__file__).parents[1] / "fixtures/vietnamese_solution_heading.typ").read_text(
        encoding="utf-8"
    )
    pdf = TypstCompiler().compile_document(source, "vietnamese_heading.pdf")
    assert {
        b"LiberationSerif",
        b"LiberationSerif-Italic",
        b"LiberationSerif-Bold",
        b"LiberationSerif-BoldItalic",
    } <= _embedded_faces(pdf), (
        "Install Liberation Serif and expose its directory to Typst "
        "(Docker: fonts-liberation2 + TYPST_FONT_PATHS)"
    )


def test_actual_solution_heading_uses_the_installed_bold_italic_font():
    compiler = TypstCompiler()
    source = compiler.render_solution_document(
        "101",
        [
            {
                "question_no": 1,
                "content": "Chờ đổi giờ: ờ ớ ợ ở ỡ.",
                "correct_key": "A",
                "solution_md": "Lời giải: $x^2 = 1$.",
            }
        ],
    )
    pdf = compiler.compile_document(source, "solutions_101.pdf")
    assert b"LiberationSerif-BoldItalic" in _embedded_faces(pdf)

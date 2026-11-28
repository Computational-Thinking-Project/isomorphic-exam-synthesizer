"""EXT-03 G4: print options (EXT v3.1 §EXT-03 ``visible_fields``/``answer_sheet``/``formats``).

Covers A17 at the source level: null metadata and hidden fields are omitted, code and
question count always print, ``written_boxes`` has one row per question, non-PDF with
PDF-only options is rejected, OMR stays closed, and ``config=None`` keeps the MVP bundle.
Page layout itself is checked on a real PDF when Typst is installed.
"""

import re
import shutil
from datetime import date
from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from app.services.exporter.bundle_models import ApprovedExportSnapshot
from app.services.exporter.export_pipeline import build_compiled_bundle
from app.services.exporter.print_layout import (
    DEFAULT_EXPORT_CONFIG,
    DEFAULT_VISIBLE_FIELDS,
    METADATA_FIELDS,
    STUDENT_FIELDS,
    VISIBLE_FIELDS,
    ExamMetadata,
    ExportConfigError,
    parse_export_config,
)
from app.services.exporter.typst_compiler import TypstCompiler

FULL_METADATA = ExamMetadata(
    school="Trường THPT Lê Quý Đôn",
    subject="Toán",
    exam_type="Kiểm tra giữa kỳ",
    grade=12,
    semester=1,
    academic_year="2026-2027",
    exam_date=date(2026, 12, 1),
    duration_minutes=45,
)
FAKE_PDF = b"%PDF-1.4\n%%EOF\n"


def _questions(count):
    return [
        {
            "id": str(uuid4()),
            "question_no": n,
            "content": f"Câu hỏi số {n}: tính $x+{n}$.",
            "options": [f"{n}", f"{n + 1}", f"{n + 2}", f"{n + 3}"],
            "correct_key": "ABCD"[n % 4],
            "solution_md": f"Lời giải {n}.",
            "status": "approved",
        }
        for n in range(1, count + 1)
    ]


def _render(config, metadata=FULL_METADATA, count=3, title="Đề Toán — lớp 12"):
    return TypstCompiler().render_configured_document(
        "105", _questions(count), exam_title=title, metadata=metadata, config=config
    )


def _exam_part(source, *, raw=False):
    """Printed exam page only: after the preamble (document title is metadata), before the
    teacher part. Unless ``raw``, Typst escapes are removed so tests read printed text."""
    exam = source[source.index("#set par(") : source.index("#pagebreak()")]
    return exam if raw else re.sub(r"\\(.)", r"\1", exam)


# --- config parsing ---------------------------------------------------------------


def test_missing_body_keys_take_the_default_config():
    assert parse_export_config({}) == DEFAULT_EXPORT_CONFIG
    assert DEFAULT_EXPORT_CONFIG.visible_fields == DEFAULT_VISIBLE_FIELDS
    assert DEFAULT_EXPORT_CONFIG.answer_sheet == "none"
    assert DEFAULT_EXPORT_CONFIG.formats == ("pdf", "tex", "md")
    assert not DEFAULT_EXPORT_CONFIG.uses_pdf_template


def test_equivalent_configs_normalize_to_the_same_identity():
    first = parse_export_config(
        {"visible_fields": ["student_id", "title", "title"], "formats": ["md", "pdf"]}
    )
    second = parse_export_config(
        {"visible_fields": ["title", "student_id"], "formats": ["pdf", "md", "md"]}
    )
    assert first == second
    assert first.canonical_json() == second.canonical_json()
    assert first.visible_fields == ("title", "student_id")
    assert first.formats == ("pdf", "md")


def test_empty_visible_fields_is_the_basic_layout_not_the_default():
    config = parse_export_config({"visible_fields": []})
    assert config.visible_fields == ()
    assert config.uses_pdf_template


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {"unknown": 1},
        {"visible_fields": ["teacher_name"]},
        {"visible_fields": "title"},
        {"visible_fields": [1]},
        {"formats": []},
        {"formats": ["docx"]},
        {"answer_sheet": "bubbles"},
        {"answer_sheet": None},
        # Non-PDF only, but a PDF-only option differs from the default.
        {"formats": ["tex", "md"], "answer_sheet": "written_boxes"},
        {"formats": ["md"], "visible_fields": ["title", "school"]},
    ],
)
def test_invalid_config_is_rejected(raw):
    with pytest.raises(ExportConfigError) as caught:
        parse_export_config(raw)
    assert caught.value.code == "ERR_EXPORT_CONFIG_INVALID"


def test_non_pdf_formats_with_default_pdf_options_are_accepted():
    assert parse_export_config({"formats": ["tex"]}).formats == ("tex",)


def test_omr_stays_closed_until_i_ext_04():
    with pytest.raises(ExportConfigError) as caught:
        parse_export_config({"answer_sheet": "omr_bubbles"})
    assert caught.value.code == "ERR_EXPORT_OMR_UNAVAILABLE"


# --- metadata ---------------------------------------------------------------------


def test_metadata_has_exactly_the_eight_locked_fields():
    assert tuple(ExamMetadata.model_fields) == METADATA_FIELDS
    assert VISIBLE_FIELDS == ("title", *METADATA_FIELDS, *STUDENT_FIELDS)
    assert ExamMetadata(school="   ").school is None


@pytest.mark.parametrize(
    "field, value",
    [
        ("grade", 0),
        ("grade", 13),
        ("grade", "12"),
        ("semester", 3),
        ("academic_year", "2026-2028"),
        ("academic_year", "2026/2027"),
        ("exam_date", "01/12/2026"),
        ("duration_minutes", 0),
        ("unknown", "x"),
    ],
)
def test_invalid_metadata_fails_closed(field, value):
    with pytest.raises(ValidationError):
        ExamMetadata(**{field: value})


# --- PDF header -------------------------------------------------------------------


def test_all_visible_fields_print_metadata_student_boxes_code_and_count():
    config = parse_export_config({"visible_fields": list(VISIBLE_FIELDS)})
    exam = _exam_part(_render(config))
    for text in (
        "TRƯỜNG THPT LÊ QUÝ ĐÔN",
        "Kiểm tra giữa kỳ",
        "Học kỳ 1 · Năm học 2026 - 2027",
        "Đề Toán — lớp 12",
        "Môn: Toán · Lớp 12",
        "Ngày thi: 01/12/2026",
        "Thời gian làm bài: 45 phút",
        "MÃ ĐỀ THI: 105",
        "Số câu: 3",
        "Họ và tên thí sinh:",
        "Số báo danh:",
        "Lớp:",
    ):
        assert text in exam, text
    assert exam.index("MÃ ĐỀ THI") < exam.index("Họ và tên") < exam.index("*Câu 1:*")


def test_null_metadata_and_hidden_fields_are_omitted_but_code_and_count_remain():
    config = parse_export_config({"visible_fields": list(VISIBLE_FIELDS)})
    exam = _exam_part(_render(config, metadata=ExamMetadata()))
    for text in ("Môn:", "Ngày thi", "Thời gian", "Học kỳ", "Năm học", "null", "None"):
        assert text not in exam, text
    assert "MÃ ĐỀ THI: 105" in exam and "Số câu: 3" in exam

    basic = _exam_part(_render(parse_export_config({"visible_fields": []})))
    for text in ("LÊ QUÝ ĐÔN", "Đề Toán", "Môn:", "Họ và tên", "Số báo danh", "PHIẾU"):
        assert text not in basic, text
    assert "MÃ ĐỀ THI: 105" in basic and "Số câu: 3" in basic
    # No placeholder school or room from the MVP template leaks into a configured PDF.
    assert "TRƯỜNG THPT CHUYÊN" not in basic and "Phòng thi" not in basic


def test_student_fields_are_independent_and_left_blank():
    exam = _exam_part(_render(parse_export_config({"visible_fields": ["student_id"]})))
    assert "Số báo danh:" in exam
    assert "Họ và tên thí sinh" not in exam and "Lớp:" not in exam


def test_metadata_text_is_escaped_for_typst():
    metadata = ExamMetadata(school="Trường #1 [A] $x$ // b", exam_type="Thi *thử* _a_ <l> @r")
    config = parse_export_config({"visible_fields": list(VISIBLE_FIELDS)})
    raw = _exam_part(_render(config, metadata, title="Đề `x` = 1"), raw=True)
    # Every markup character in the values is backslash-escaped, none left bare.
    assert r"TRƯỜNG \#1 \[A\] \$X\$ \/\/ B" in raw
    assert r"Thi \*thử\* \_a\_ \<l\> \@r" in raw
    assert r"Đề \`x\` \= 1" in raw


@pytest.mark.parametrize("count", [1, 5, 7, 20])
def test_written_boxes_has_one_row_of_a_to_d_boxes_per_question(count):
    config = parse_export_config({"answer_sheet": "written_boxes"})
    exam = _exam_part(_render(config, count=count))
    sheet = exam[exam.index("PHIẾU TRẢ LỜI") : exam.index("*Câu 1:*")]
    for n in range(1, count + 1):
        assert sheet.count(f"[*{n}.*]") == 1
    assert f"[*{count + 1}.*]" not in sheet
    assert sheet.count("box(width: 9pt") == 4 * count
    # The sheet sits above the questions, below the student box.
    assert exam.index("Họ và tên") < exam.index("PHIẾU TRẢ LỜI") < exam.index("*Câu 1:*")


def test_teacher_part_follows_the_exam_on_a_new_page():
    source = _render(parse_export_config({"answer_sheet": "written_boxes"}))
    assert source.count("#set page(") == 1
    assert source.index("HẾT") < source.index("#pagebreak()") < source.index("MA TRẬN ĐÁP ÁN")


# --- bundle -----------------------------------------------------------------------


def _bundle(snapshot, **kwargs):
    compiler = Mock(wraps=TypstCompiler())
    compiler.compile_document.return_value = FAKE_PDF
    artifact = build_compiled_bundle(snapshot, compiler=compiler, **kwargs)
    root = f"exam_bundle_{snapshot.session_id}/"
    with ZipFile(BytesIO(artifact.data)) as archive:
        names = {n.removeprefix(root) for n in archive.namelist()}
        readme = archive.read(root + "README.txt").decode()
    return artifact, compiler, names, readme


def test_config_none_keeps_the_mvp_bundle_byte_for_byte(snapshot):
    before, *_ = _bundle(snapshot)
    again, compiler, names, readme = _bundle(snapshot, config=None)
    assert before.sha256 == again.sha256
    assert compiler.render_configured_document.call_count == 0
    assert "Gói có cấu hình" not in readme


def test_default_config_uses_the_mvp_pdf_renderer(snapshot):
    _, compiler, names, readme = _bundle(snapshot, config=DEFAULT_EXPORT_CONFIG)
    assert compiler.render_combined_document.call_count == 1
    assert compiler.render_configured_document.call_count == 0
    assert {"pdf/exam_101.pdf", "latex/exam_101.tex", "markdown/exam_101.md"} <= names
    assert "chỉ áp dụng cho PDF" in readme


def test_configured_pdf_uses_metadata_and_keeps_tex_md_on_the_mvp_layout(snapshot):
    config = parse_export_config(
        {"visible_fields": ["title", "school"], "answer_sheet": "written_boxes"}
    )
    plain, *_ = _bundle(snapshot)
    _, compiler, names, _ = _bundle(snapshot, config=config, metadata=FULL_METADATA)
    source = compiler.compile_document.call_args.args[0]
    assert "TRƯỜNG THPT LÊ QUÝ ĐÔN" in source and "PHIẾU TRẢ LỜI" in source
    assert compiler.render_configured_document.call_count == 1
    with ZipFile(BytesIO(plain.data)) as archive:
        root = f"exam_bundle_{snapshot.session_id}/"
        mvp_md = archive.read(root + "markdown/exam_101.md")
    configured, *_ = _bundle(snapshot, config=config, metadata=FULL_METADATA)
    with ZipFile(BytesIO(configured.data)) as archive:
        assert archive.read(root + "markdown/exam_101.md") == mvp_md


@pytest.mark.parametrize(
    "formats, expected",
    [
        (["pdf"], {"pdf/exam_101.pdf"}),
        (["tex"], {"latex/exam_101.tex", "latex/README_huong_dan_bien_dich.txt"}),
        (["md"], {"markdown/exam_101.md"}),
        (["pdf", "md"], {"pdf/exam_101.pdf", "markdown/exam_101.md"}),
    ],
)
def test_only_chosen_formats_are_packaged(snapshot, formats, expected):
    _, compiler, names, readme = _bundle(snapshot, config=parse_export_config({"formats": formats}))
    assert names == expected | {"README.txt"}
    assert compiler.compile_document.call_count == ("pdf" in formats)
    assert ", ".join(formats) in readme


def test_more_than_twenty_questions_cannot_reach_the_packager(snapshot_data):
    snapshot_data["versions"][0]["questions"] = _questions(21)
    with pytest.raises(ValidationError):
        ApprovedExportSnapshot.model_validate(snapshot_data)


# --- real PDF ---------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("typst") is None, reason="Typst unavailable")
@pytest.mark.parametrize("count", [1, 20])
def test_configured_pdf_compiles_with_written_boxes(count):
    config = parse_export_config(
        {"visible_fields": list(VISIBLE_FIELDS), "answer_sheet": "written_boxes"}
    )
    pdf = TypstCompiler().compile_document(_render(config, count=count), "configured.pdf")
    assert pdf.startswith(b"%PDF-")

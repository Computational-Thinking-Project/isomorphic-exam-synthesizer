"""EXT-03 print options: validated config, locked metadata and the PDF header layout.

Only PDF uses the configured layout; LaTeX and Markdown keep the MVP layout
(EXT v3.1 §EXT-03 ``formats``). Nothing here reads the database or HTTP input
directly: the route parses ``config`` with :func:`parse_export_config`, and the
snapshot reader supplies the metadata locked at Approve.
"""

import json
import re
from datetime import date
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_TYPST_MARKUP = re.compile(r"([\\#$*_\[\]<>@`~=+/-])")


def _plain(text: str) -> str:
    """Escape every Typst markup character, so metadata and titles print as literal text."""
    return _TYPST_MARKUP.sub(r"\\\1", text.replace("\n", " "))


METADATA_FIELDS = (
    "school",
    "subject",
    "exam_type",
    "grade",
    "semester",
    "academic_year",
    "exam_date",
    "duration_minutes",
)
STUDENT_FIELDS = ("student_name", "student_id", "student_class")
VISIBLE_FIELDS = ("title", *METADATA_FIELDS, *STUDENT_FIELDS)
FORMATS = ("pdf", "tex", "md")
AnswerSheet = Literal["none", "written_boxes", "omr_bubbles"]

# Closest to the MVP PDF: printed title and the student box, no answer sheet.
DEFAULT_VISIBLE_FIELDS = ("title", *STUDENT_FIELDS)
DEFAULT_ANSWER_SHEET = "none"


class ExportConfigError(ValueError):
    """Maps to the I-EXT-05 422 error codes proposed in EXT-03 §4."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ExportConfig(BaseModel):
    """Normalized config: field and format order is canonical, so equal configs hash equal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    visible_fields: tuple[str, ...]
    answer_sheet: AnswerSheet
    formats: tuple[str, ...] = Field(min_length=1)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @property
    def uses_pdf_template(self) -> bool:
        return (
            self.visible_fields != DEFAULT_VISIBLE_FIELDS
            or self.answer_sheet != DEFAULT_ANSWER_SHEET
        )


def _ordered(values: Any, allowed: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ExportConfigError("ERR_EXPORT_CONFIG_INVALID")
    chosen = set(values)
    if not chosen <= set(allowed):
        raise ExportConfigError("ERR_EXPORT_CONFIG_INVALID")
    return tuple(name for name in allowed if name in chosen)


def parse_export_config(raw: Any) -> ExportConfig:
    """Validate the request body ``config``; every missing key takes its default.

    Unknown keys/fields, duplicate-insensitive order and empty ``formats`` are
    normalized or rejected here so the identity key never depends on client order.
    """
    if not isinstance(raw, Mapping) or not set(raw) <= {
        "visible_fields",
        "answer_sheet",
        "formats",
    }:
        raise ExportConfigError("ERR_EXPORT_CONFIG_INVALID")
    visible = _ordered(raw.get("visible_fields", list(DEFAULT_VISIBLE_FIELDS)), VISIBLE_FIELDS)
    formats = _ordered(raw.get("formats", list(FORMATS)), FORMATS)
    sheet = raw.get("answer_sheet", DEFAULT_ANSWER_SHEET)
    try:
        config = ExportConfig(visible_fields=visible, answer_sheet=sheet, formats=formats)
    except ValidationError as error:
        raise ExportConfigError("ERR_EXPORT_CONFIG_INVALID") from error
    if config.answer_sheet == "omr_bubbles":
        # Closed until I-EXT-04 records a printed, filled and scanned template.
        raise ExportConfigError("ERR_EXPORT_OMR_UNAVAILABLE")
    if "pdf" not in config.formats and config.uses_pdf_template:
        raise ExportConfigError("ERR_EXPORT_CONFIG_INVALID")
    return config


DEFAULT_EXPORT_CONFIG = parse_export_config({})


class ExamMetadata(BaseModel):
    """Eight nullable fields locked at Approve (EXT v3.1 §2); null is never printed."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    school: str | None = Field(default=None, max_length=255)
    subject: str | None = Field(default=None, max_length=255)
    exam_type: str | None = Field(default=None, max_length=255)
    grade: int | None = Field(default=None, ge=1, le=12, strict=True)
    semester: Literal[1, 2] | None = None
    academic_year: str | None = None
    exam_date: date | None = None
    duration_minutes: int | None = Field(default=None, gt=0, strict=True)

    @field_validator("school", "subject", "exam_type", mode="after")
    @classmethod
    def blank_is_null(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("academic_year")
    @classmethod
    def consecutive_years(cls, value: str | None) -> str | None:
        if value is None:
            return None
        match = re.fullmatch(r"(\d{4})-(\d{4})", value)
        if not match or int(match[2]) != int(match[1]) + 1:
            raise ValueError("academic_year must be two consecutive years YYYY-YYYY")
        return value


_LINE = "#box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))"
_STUDENT_LABELS = {
    "student_name": "Họ và tên thí sinh",
    "student_id": "Số báo danh",
    "student_class": "Lớp",
}


def _metadata_lines(
    title: str, metadata: ExamMetadata, visible: set[str]
) -> tuple[list[str], list[str]]:
    left: list[str] = []
    right: list[str] = []
    if "school" in visible and metadata.school:
        left.append(f'#text(weight: "bold")[{_plain(metadata.school.upper())}]')
    if "exam_type" in visible and metadata.exam_type:
        left.append(f'#text(weight: "bold")[{_plain(metadata.exam_type)}]')
    period = []
    if "semester" in visible and metadata.semester:
        period.append(f"Học kỳ {metadata.semester}")
    if "academic_year" in visible and metadata.academic_year:
        period.append(f"Năm học {metadata.academic_year.replace('-', ' - ')}")
    if period:
        left.append(_plain(" · ".join(period)))
    if "title" in visible:
        right.append(f'#text(weight: "bold")[{_plain(title)}]')
    subject = []
    if "subject" in visible and metadata.subject:
        subject.append(f"Môn: {metadata.subject}")
    if "grade" in visible and metadata.grade:
        subject.append(f"Lớp {metadata.grade}")
    if subject:
        right.append(_plain(" · ".join(subject)))
    if "exam_date" in visible and metadata.exam_date:
        right.append(_plain(f"Ngày thi: {metadata.exam_date:%d/%m/%Y}"))
    if "duration_minutes" in visible and metadata.duration_minutes:
        right.append(_plain(f"Thời gian làm bài: {metadata.duration_minutes} phút"))
    return left, right


def _written_boxes(question_count: int) -> str:
    """One row per question: number then four empty boxes labelled A–D, in up to 4 columns."""
    columns = min(4, question_count)
    rows = -(-question_count // columns)
    box = "box(width: 9pt, height: 9pt, stroke: 0.6pt, baseline: 1pt)"
    cells = []
    for col in range(columns):
        for row in range(rows):
            number = col * rows + row + 1
            if number > question_count:
                cells.append("[]")
                continue
            options = " ".join(f"#{box} {label}" for label in "ABCD")
            cells.append(f"[*{number}.* {options}]")
    # Typst fills row by row, so reorder column-major cells into reading order.
    ordered = [cells[col * rows + row] for row in range(rows) for col in range(columns)]
    return (
        "#block(width: 100%, stroke: 0.5pt + luma(150), inset: 8pt, radius: 3pt)[\n"
        '  #text(weight: "bold")[PHIẾU TRẢ LỜI] '
        '#text(size: 9pt, style: "italic")[(đánh dấu X vào một ô cho mỗi câu)]\n'
        "  #v(4pt)\n"
        f"  #grid(columns: ({', '.join(['1fr'] * columns)}), row-gutter: 6pt, "
        f"{', '.join(ordered)})\n"
        "]\n#v(8pt)"
    )


def render_exam_header(
    *,
    title: str,
    version_code: str,
    question_count: int,
    metadata: ExamMetadata,
    config: ExportConfig,
) -> str:
    """Typst header for a configured exam: metadata, code/count, student box, answer sheet."""
    visible = set(config.visible_fields)
    left, right = _metadata_lines(title, metadata, visible)
    code_line = (
        f'#text(weight: "bold", size: 12pt)[MÃ ĐỀ THI: {_plain(version_code)}]'
        f" · Số câu: {question_count}"
    )
    right.append(code_line)
    newline = " \\\n    "
    left_cell, right_cell = newline.join(left), newline.join(right)
    parts: list[str] = []
    if left:
        parts.append(
            "#grid(columns: (1.2fr, 1fr), gutter: 10pt, align: (center, center),\n"
            f"  [\n    {left_cell}\n  ],\n  [\n    {right_cell}\n  ]\n)"
        )
    else:
        parts.append(f"#align(center)[\n    {right_cell}\n]")
    parts.append("#v(6pt)\n#line(length: 100%, stroke: 1pt)\n#v(4pt)")
    students = [name for name in STUDENT_FIELDS if name in visible]
    if students:
        cells = ", ".join(f"[{_STUDENT_LABELS[name]}: {_LINE}]" for name in students)
        parts.append(
            "#block(width: 100%, stroke: 0.5pt + luma(150), inset: 8pt, radius: 3pt)[\n"
            f"  #grid(columns: ({', '.join(['1fr'] * len(students))}), gutter: 12pt, {cells})\n"
            "]\n#v(8pt)"
        )
    if config.answer_sheet == "written_boxes":
        parts.append(_written_boxes(question_count))
    return "\n".join(parts) + "\n#v(6pt)\n"

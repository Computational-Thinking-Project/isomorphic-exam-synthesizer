"""Shared metadata normalization for EXT-04 settings and printable exams."""

import re
from datetime import date, datetime
from typing import Annotated
from unicodedata import normalize

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _normalize_text(value: object) -> object:
    if isinstance(value, str):
        return normalize("NFC", value).strip() or None
    return value


def _validate_academic_year(value: object) -> object:
    value = _normalize_text(value)
    if not isinstance(value, str):
        return value
    if not re.fullmatch(r"[0-9]{4}-[0-9]{4}", value):
        raise ValueError("Academic year must use YYYY-YYYY")
    first, last = map(int, value.split("-"))
    if first == 0 or last != first + 1:
        raise ValueError("Academic year must contain two consecutive years")
    return value


def _parse_exam_date(value: object) -> date | None:
    value = _normalize_text(value)
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value)
    raise ValueError("Exam date must use YYYY-MM-DD")


MetadataText = Annotated[str | None, Field(strict=True), BeforeValidator(_normalize_text)]
AcademicYear = Annotated[str | None, Field(strict=True), BeforeValidator(_validate_academic_year)]
ExamDate = Annotated[date | None, BeforeValidator(_parse_exam_date)]
Grade = Annotated[int, Field(strict=True, ge=1, le=12)]
Semester = Annotated[int, Field(strict=True, ge=1, le=2)]
Duration = Annotated[int, Field(strict=True, gt=0)]


class ExamMetadata(BaseModel):
    """Printable metadata. A full dump includes nulls; a patch excludes unset fields."""

    model_config = ConfigDict(extra="forbid")

    school: MetadataText = None
    subject: MetadataText = None
    exam_type: MetadataText = None
    grade: Grade | None = None
    semester: Semester | None = None
    academic_year: AcademicYear = None
    exam_date: ExamDate = None
    duration_minutes: Duration | None = None

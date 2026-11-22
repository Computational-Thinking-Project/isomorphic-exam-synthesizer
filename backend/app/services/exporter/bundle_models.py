"""Pure export boundary. Owner maps the locked, shuffled DB snapshot to this model."""

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.services.blueprint.adapters import normalized_text

Text = Annotated[str, Field(min_length=1, max_length=16000)]


class DisplayQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    _empty_solution_id: UUID | None = PrivateAttr(default=None)

    id: UUID
    question_no: int = Field(ge=1, le=20)
    content: Text
    options: tuple[Text, Text, Text, Text]
    correct_key: Literal["A", "B", "C", "D"]
    solution_md: Annotated[str, Field(max_length=16000)]
    status: Literal["approved"]

    @field_validator("solution_md")
    @classmethod
    def verified_empty_solution(cls, value: str, info: ValidationInfo) -> str:
        # This is an internal construction capability, not a JSON field. Only
        # the DB builder supplies it after checking the generation provenance.
        if not value and info.data.get("id") not in (info.context or {}).get(
            "verified_empty_solution_ids", ()
        ):
            raise ValueError("Empty solution requires verified fallback/clone provenance")
        return value

    def model_post_init(self, context: object) -> None:
        # Preserve the internal authorization through downstream revalidation,
        # without serializing provenance or altering the canonical hash payload.
        if not self.solution_md:
            self._empty_solution_id = self.id

    @field_validator("options")
    @classmethod
    def distinct_options(cls, value: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
        if len({normalized_text(option) for option in value}) != 4:
            raise ValueError("Duplicate display options")
        return value


class DisplayVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
    questions: tuple[DisplayQuestion, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def check_positions(self) -> "DisplayVersion":
        if [q.question_no for q in self.questions] != list(range(1, len(self.questions) + 1)):
            raise ValueError("Questions must already be in contiguous display order")
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Duplicate question ID")
        return self


class ApprovedExportSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    session_id: UUID
    revision: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    status: Literal["approved", "exported"]
    versions: tuple[DisplayVersion, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def consistent_versions(self) -> "ApprovedExportSnapshot":
        if len({version.code.casefold() for version in self.versions}) != len(self.versions):
            raise ValueError("Version filenames collide")
        if len({len(version.questions) for version in self.versions}) != 1:
            raise ValueError("Versions must have the same question count")
        return self


@dataclass(frozen=True)
class BundleArtifact:
    filename: str
    data: bytes
    sha256: str
    content_type: str = "application/zip"

    @property
    def size_bytes(self) -> int:
        return len(self.data)


class BundleBuildError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def revalidate_snapshot(snapshot: ApprovedExportSnapshot) -> ApprovedExportSnapshot:
    """Revalidate all fields, carrying only DB-builder-verified empty-slot IDs.

    A JSON round trip intentionally drops this capability; callers must reload
    the snapshot from the DB instead of using client-supplied provenance flags.
    """
    verified_ids = {
        q.id for v in snapshot.versions for q in v.questions if q._empty_solution_id == q.id
    }
    return ApprovedExportSnapshot.model_validate(
        snapshot.model_dump(), context={"verified_empty_solution_ids": verified_ids}
    )

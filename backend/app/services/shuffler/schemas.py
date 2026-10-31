"""
Pydantic Schemas for Deterministic Fisher-Yates Shuffler (TASK-303).

Defines data contracts for:
1. Shuffle configuration and ordering preferences.
2. Canonical input questions adhering to the Canonical Data Model.
3. Permutation mapping matrices.
4. Shuffled question outputs with synchronized solution texts.
5. Answer key records for table public.answer_keys.
6. API response models conforming to w3.md#L316 contract.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class OrderingPreferences(BaseModel):
    """User preferences for shuffling exam questions and options."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    shuffle_questions: bool = Field(
        default=True,
        description="Whether to shuffle question order across exam versions",
    )
    shuffle_options: bool = Field(
        default=True,
        description="Whether to shuffle option order within each question",
    )


class CanonicalQuestionInput(BaseModel):
    """
    Input question model adhering to the Canonical Data Model.
    All shuffling algorithms read strictly from canonical_* fields.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    id: Optional[str] = Field(default=None, description="UUID of version question if available")
    source_question_id: Optional[str] = Field(default=None, description="UUID of source question")
    question_no: Optional[int] = Field(default=None, description="Current question number (1..N)")
    content: str = Field(..., description="Question stem content in Vietnamese / LaTeX")
    canonical_question_no: int = Field(
        ..., description="Canonical 1-based question number from source exam"
    )
    canonical_options: List[str] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="List of exactly 4 canonical option strings in A, B, C, D order",
    )
    canonical_correct_key: Literal["A", "B", "C", "D"] = Field(
        ..., description="Canonical correct option letter: 'A', 'B', 'C', or 'D'"
    )
    canonical_solution_md: Optional[str] = Field(
        default="",
        description="Original canonical explanation markdown before option shuffling",
    )
    is_current: bool = Field(
        default=True,
        description="Only current (active/latest) questions should be shuffled",
    )
    status: Optional[str] = Field(
        default="approved",
        description="Review status of question (e.g. approved, pending_review)",
    )


class OptionPermutation(BaseModel):
    """Option permutation mapping for a single question."""

    canonical_to_display: Dict[str, str] = Field(
        ..., description="Map canonical option letter -> display option letter"
    )
    display_to_canonical: Dict[str, str] = Field(
        ..., description="Map display option letter -> canonical option letter"
    )


class ShuffledQuestionOutput(BaseModel):
    """Shuffled version question ready for database persistence and rendering."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    id: Optional[str] = None
    source_question_id: Optional[str] = None
    display_no: int = Field(..., description="Display question number in this version (1..N)")
    content: str = Field(..., description="Question stem content")
    options: List[str] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Permuted option strings in display A, B, C, D order",
    )
    display_correct_key: str = Field(..., description="New correct answer letter for this version")
    solution_md: str = Field(..., description="Synchronized explanation markdown")
    canonical_question_no: int = Field(
        ..., description="Canonical 1-based question number preserved verbatim"
    )
    canonical_options: List[str] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Canonical option strings preserved verbatim",
    )
    canonical_correct_key: str = Field(..., description="Canonical correct key preserved verbatim")
    canonical_solution_md: Optional[str] = Field(
        default="", description="Canonical solution text preserved verbatim"
    )
    is_current: bool = True
    permutation_map: Dict[str, str] = Field(
        default_factory=dict,
        description="Permutation mapping canonical option letter to display option letter",
    )


class AnswerKeyRecord(BaseModel):
    """
    Record destined for public.answer_keys table.
    Supports both W3 specification fields (display_no, display_correct_key)
    and legacy schema baseline fields (question_no, correct_option) via aliases.
    """

    model_config = ConfigDict(populate_by_name=True)

    version_id: Optional[str] = None
    display_no: int = Field(
        ...,
        validation_alias=AliasChoices("display_no", "question_no"),
        serialization_alias="question_no",
        description="Display question number in the version (1..N), aliased as question_no",
    )
    display_correct_key: str = Field(
        ...,
        validation_alias=AliasChoices("display_correct_key", "correct_option"),
        serialization_alias="correct_option",
        description="Display correct answer letter ('A', 'B', 'C', 'D'), aliased as correct_option",
    )
    canonical_question_no: int = Field(
        ..., description="Reference back to canonical question number"
    )

    @property
    def question_no(self) -> int:
        """Backward-compatible attribute access for legacy callers."""
        return self.display_no

    @property
    def correct_option(self) -> str:
        """Backward-compatible attribute access for legacy callers."""
        return self.display_correct_key


class VersionShuffleResult(BaseModel):
    """Complete shuffle result for an individual exam version."""

    version_id: Optional[str] = None
    version_code: str = Field(..., description="Version code, e.g. '101', '102'")
    shuffle_seed: str = Field(..., description="Deterministic seed used for this version")
    total_questions: int = Field(..., description="Total count of shuffled questions")
    questions: List[ShuffledQuestionOutput] = Field(
        default_factory=list, description="List of shuffled questions"
    )
    answer_keys: List[AnswerKeyRecord] = Field(
        default_factory=list, description="Answer key mapping records"
    )
    permutations: Dict[str, Any] = Field(
        default_factory=dict,
        description="Full permutation metadata for exam_versions.permutations (JSONB)",
    )


class VersionMetadata(BaseModel):
    """Version metadata matching w3.md contract."""

    version_id: str
    version_code: str
    total_questions: int


class FinalizeShuffleResponse(BaseModel):
    """Response schema for POST /api/sessions/{session_id}/finalize/shuffle matching w3.md#L316."""

    session_id: str
    status: str = "reviewed"
    is_finalized: bool = True
    versions: List[VersionMetadata]

"""Request and response contract for TASK-207a, separate from generation itself."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class OrderingPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shuffle_questions: StrictBool
    shuffle_options: StrictBool


GenerationMode = Literal["ai_generation", "shuffle_only"]


class GenerationConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_versions: int = Field(strict=True, ge=1, le=4)
    active_variation_modes: list[StrictStr] = Field(default_factory=list, strict=True, max_length=0)
    ordering_preferences: OrderingPreferences = Field(
        default_factory=lambda: OrderingPreferences(shuffle_questions=False, shuffle_options=False)
    )
    # EXT-02: explicit mode; an omitted field keeps the pre-EXT-02 AI behaviour.
    # The mode is never inferred from an empty active_variation_modes list.
    generation_mode: GenerationMode = "ai_generation"


class SavedGenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_versions: int = Field(strict=True, ge=1, le=4)
    active_variation_modes: list[StrictStr] = Field(strict=True)
    ordering_preferences: OrderingPreferences
    source_manifest: dict[str, object]
    canonical_dimensions: list[Literal["values", "context"]]
    mapping_version: Literal["1.0", "1.1", "1.2"]
    generation_mode: GenerationMode = "ai_generation"


class GenerationConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: Literal[True]
    session_id: UUID
    config_id: UUID
    status: Literal["configured"]
    config: SavedGenerationConfig

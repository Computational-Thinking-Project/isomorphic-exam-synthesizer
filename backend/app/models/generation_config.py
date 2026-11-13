"""Request and response contract for TASK-207a, separate from generation itself."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class OrderingPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shuffle_questions: StrictBool
    shuffle_options: StrictBool


class GenerationConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_versions: int = Field(strict=True, ge=1, le=4)
    active_variation_modes: list[StrictStr] = Field(default_factory=list, strict=True, max_length=0)
    ordering_preferences: OrderingPreferences = Field(
        default_factory=lambda: OrderingPreferences(shuffle_questions=False, shuffle_options=False)
    )


class SavedGenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_versions: int = Field(strict=True, ge=1, le=4)
    active_variation_modes: list[StrictStr] = Field(strict=True)
    ordering_preferences: OrderingPreferences
    source_manifest: dict[str, object]
    canonical_dimensions: list[Literal["values", "context"]]
    mapping_version: Literal["1.0"]


class GenerationConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: Literal[True]
    session_id: UUID
    config_id: UUID
    status: Literal["configured"]
    config: SavedGenerationConfig

"""Request and response contract for TASK-207a, separate from generation itself."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator


class OrderingPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shuffle_questions: StrictBool = True
    shuffle_options: StrictBool = True


class GenerationConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_versions: int = Field(strict=True, ge=1, le=4)
    active_variation_modes: list[StrictStr] = Field(strict=True)
    ordering_preferences: OrderingPreferences = Field(default_factory=OrderingPreferences)

    @field_validator("active_variation_modes")
    @classmethod
    def normalize_modes(cls, modes: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in modes:
            mode = item.strip()
            if not mode:
                raise ValueError("Variation mode IDs must not be blank.")
            if mode not in seen:
                seen.add(mode)
                normalized.append(mode)
        return normalized


class GenerationConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    status: Literal["configured"]
    config: GenerationConfigRequest

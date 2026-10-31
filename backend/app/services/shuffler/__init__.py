"""
Shuffler Package (TASK-303).

Exports deterministic Fisher-Yates shuffle algorithms, canonical invariant
preservation utilities, solution synchronization functions, and Pydantic schemas.
"""

from app.services.shuffler.schemas import (
    AnswerKeyRecord,
    CanonicalQuestionInput,
    FinalizeShuffleResponse,
    OptionPermutation,
    OrderingPreferences,
    ShuffledQuestionOutput,
    VersionMetadata,
    VersionShuffleResult,
)
from app.services.shuffler.service import (
    fisher_yates_shuffle,
    generate_deterministic_seed,
    shuffle_exam_version,
    shuffle_session_versions,
    sync_solution_text,
)

__all__ = [
    "AnswerKeyRecord",
    "CanonicalQuestionInput",
    "FinalizeShuffleResponse",
    "OptionPermutation",
    "OrderingPreferences",
    "ShuffledQuestionOutput",
    "VersionMetadata",
    "VersionShuffleResult",
    "fisher_yates_shuffle",
    "generate_deterministic_seed",
    "shuffle_exam_version",
    "shuffle_session_versions",
    "sync_solution_text",
]

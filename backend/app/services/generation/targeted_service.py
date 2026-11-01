"""Database-free review adapter. Inject TargetedRegenerator into ReviewService.

The caller owns durable permits, ownership, atomic persistence and recovery.
This adapter never substitutes a fixture when credentials or canonical input fail.
"""

import asyncio
import time
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.models.schemas import SourceQuestion
from app.models.targeted import RegeneratedVariantResult, TargetedValidationReport
from app.services.ai.gateway import RequestContext
from app.services.blueprint.adapters import normalized_text
from app.services.blueprint.common import ToolError
from app.services.generation.attempts import AcquireAttempt, DurableAttemptBudget
from app.services.generation.service import GenerationService, fingerprint


class TargetedGenerationError(RuntimeError):
    def __init__(self, code: str, api_calls_count: int = 0):
        super().__init__(code)
        self.code = code
        self.api_calls_count = api_calls_count


def snapshot_identity(snapshot: dict[str, Any]) -> str:
    stem = snapshot.get("content", snapshot.get("stem_latex", snapshot.get("question_text")))
    options = snapshot.get("options")
    if not isinstance(stem, str) or not stem.strip() or not isinstance(options, list) or len(options) != 4:
        raise TargetedGenerationError("VARIANT_SNAPSHOT_INVALID")
    if any(not isinstance(option, str) or not option.strip() for option in options):
        raise TargetedGenerationError("VARIANT_SNAPSHOT_INVALID")
    # Persisted review options may carry their display labels; generation options do not.
    normalized = []
    for key, option in zip("ABCD", options, strict=True):
        prefix = f"{key}. "
        normalized.append(normalized_text(option.removeprefix(prefix)))
    return fingerprint([normalized_text(stem), sorted(normalized)])


class TargetedRegenerator:
    def __init__(self, service: GenerationService, *, max_api_calls: int = 4, timeout_seconds: float = 40):
        if not 1 <= max_api_calls <= 4 or not 0 < timeout_seconds <= 40:
            raise ValueError("Use 1–4 reserved calls and a deadline no longer than 40 seconds")
        self.service = service
        self.max_api_calls = max_api_calls
        self.timeout_seconds = timeout_seconds

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        return (await self.regenerate_question_variant(**kwargs)).to_review_payload()

    async def regenerate_question_variant(
        self, session_id: UUID | str, question_id: UUID | str,
        source_snapshot: dict[str, Any], blueprint: dict[str, Any],
        current_variant: dict[str, Any], peer_variants: list[dict[str, Any]],
        *, operation_id: UUID | str | None = None, acquire_attempt: AcquireAttempt | None = None,
    ) -> RegeneratedVariantResult:
        budget: DurableAttemptBudget | None = None
        try:
            UUID(str(session_id))
            UUID(str(question_id))
            if operation_id is None or not callable(acquire_attempt):
                raise TargetedGenerationError("REVIEW_PERMIT_REQUIRED")
            budget = DurableAttemptBudget(self.max_api_calls, UUID(str(operation_id)), acquire_attempt)
            source = SourceQuestion.model_validate({
                "id": str(source_snapshot["id"]),
                "question_text": source_snapshot.get("question_text", source_snapshot.get("raw_content", source_snapshot.get("raw_text"))),
                "options": source_snapshot["options"],
                "correct_answer": source_snapshot.get("correct_answer", source_snapshot.get("correct_key")),
                "solution": source_snapshot.get("solution", source_snapshot.get("solution_md", "")) or "",
            })
            if current_variant.get("source_question_id") != source.id:
                raise TargetedGenerationError("PREVIOUS_VARIANT_MISMATCH")
            if str(current_variant.get("id")) != str(question_id):
                raise TargetedGenerationError("PREVIOUS_VARIANT_MISMATCH")
            if any(peer.get("source_question_id") != source.id for peer in peer_variants):
                raise TargetedGenerationError("PREVIOUS_VARIANT_MISMATCH")
            excluded = {snapshot_identity(value) for value in [current_variant, *peer_variants]}
            result = await self.service.regenerate_from_snapshots(
                source, blueprint, confirmed_source_hash=source_snapshot.get("content_hash", ""),
                context=RequestContext(time.monotonic() + self.timeout_seconds, budget.reserve),
                excluded_identities=excluded,
            )
            if result.candidate is None or result.validation is None:
                raise TargetedGenerationError(result.error_code or "GENERATION_INVALID", budget.used)
            report = result.validation
            math_verified = any(
                check.check_name == "answer_verified" and check.passed
                and check.status == "verified" and check.confidence == "sympy_verified"
                for check in report.checks
            )
            return RegeneratedVariantResult(
                stem_latex=result.candidate.question_text, options=result.candidate.options,
                correct_key=result.candidate.correct_key, solution_md=result.candidate.solution_md,
                validation_report=TargetedValidationReport(
                    is_valid=not report.failures, math_verified=math_verified, checks=report.checks,
                    warnings=[check.detail or check.check_name for check in report.checks if not check.passed],
                ), api_calls_count=budget.used,
            )
        except TargetedGenerationError:
            raise
        except ToolError as exc:
            raise TargetedGenerationError(exc.code, budget.used if budget else 0) from None
        except (ValueError, KeyError, TypeError, ValidationError):
            raise TargetedGenerationError("REGENERATION_INPUT_INVALID", budget.used if budget else 0) from None
        except asyncio.CancelledError:
            # Cancellation must propagate. Caller reconciles the durable ledger.
            raise
        except Exception:
            raise TargetedGenerationError("GENERATION_INTERNAL", budget.used if budget else 0) from None


async def mock_regenerate_question_variant(
    session_id: UUID | str, question_id: UUID | str, source_snapshot: dict[str, Any],
    blueprint: dict[str, Any], current_variant: dict[str, Any], peer_variants: list[dict[str, Any]],
    *, operation_id: UUID | str | None = None, acquire_attempt: AcquireAttempt | None = None,
) -> dict[str, Any]:
    """Explicit integration fixture: no Gemini calls, no mathematical verification."""
    return RegeneratedVariantResult(
        stem_latex=r"[MOCK] Giải phương trình $x^2-25=0$.",
        options=[r"$x=\pm5$", "$x=5$", "$x=-5$", "Vô nghiệm"], correct_key="A",
        solution_md=r"[MOCK] $x^2=25$, suy ra $x=\pm5$. Đáp án A.",
        validation_report=TargetedValidationReport(
            is_valid=True, warnings=["Dữ liệu mẫu tích hợp; chưa chạy validator hoặc Gemini."],
        ), api_calls_count=0,
    ).to_review_payload()

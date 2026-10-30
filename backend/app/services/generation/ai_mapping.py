"""Lossless mapping at the DB/AI boundary; no I/O or implicit confirmation."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.models.generation import QuestionResult, render_solution
from app.models.schemas import SourceQuestion
from app.services.blueprint.adapters import normalized_text, prepare_sources
from app.services.blueprint.common import ToolError
from app.services.generation.job_contracts import GeneratedDraft, GenerationPlan, QuestionTarget


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise ValueError("Expected a source/session UUID.")


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonblank source/result text.")
    return value


def map_source_questions(
    rows: Sequence[Mapping[str, object]], session_id: UUID
) -> tuple[SourceQuestion, ...]:
    """Map already-loaded rows, ordered by question_no; never fix source content.

    Confirmation/hash and the database visibility of these rows remain the
    caller's responsibility. Canonical IDs are created by the AI's own helper.
    """
    if not isinstance(session_id, UUID) or not 1 <= len(rows) <= 20:
        raise ValueError("Expected a session and 1–20 source questions.")
    sources: list[tuple[int, SourceQuestion]] = []
    ids: set[UUID] = set()
    numbers: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Expected source question rows.")
        source_id = _uuid(row.get("id"))
        number = row.get("question_no")
        if _uuid(row.get("session_id")) != session_id or source_id in ids:
            raise ValueError("Source identity is duplicated or outside this session.")
        if type(number) is not int or number < 1 or number in numbers:
            raise ValueError("Expected unique positive question numbers.")
        options = row.get("options")
        if not isinstance(options, Mapping) or set(options) != set("ABCD"):
            raise ValueError("Expected exactly A, B, C, D source options.")
        option_list = [_text(options[key]) for key in "ABCD"]
        key = _text(row.get("correct_key"))
        if key not in {"A", "B", "C", "D"}:
            raise ValueError("Expected an A–D source answer key.")
        solution = row.get("solution_md")
        if solution is not None and not isinstance(solution, str):
            raise ValueError("Expected source solution text or null.")
        warning = row.get("has_security_warning", False)
        if not isinstance(warning, bool):
            raise ValueError("Expected a boolean source warning.")
        source = SourceQuestion(
            id=row["id"] if isinstance(row["id"], str) else str(source_id),
            question_text=_text(row.get("raw_content")),
            options=option_list,
            correct_answer=key,
            solution=solution if solution is not None else "",
            topic=None,
            has_security_warning=warning,
        )
        ids.add(source_id)
        numbers.add(number)
        sources.append((number, source))
    ordered = tuple(source for _, source in sorted(sources, key=lambda item: item[0]))
    try:
        prepare_sources(list(ordered))
    except ToolError:
        raise ValueError("Source questions are not valid AI inputs.") from None
    return ordered


@dataclass(frozen=True, slots=True)
class PreparedAIResult:
    """Store the whole raw result for resume, alongside the display projection."""

    target: QuestionTarget
    draft: GeneratedDraft | None
    raw_result: QuestionResult


def prepare_question_result(result: QuestionResult, plan: GenerationPlan) -> PreparedAIResult:
    """Validate identities/acceptance before handing a result to a save callback.

    None candidates stay errors/missing targets. This function does not decide
    a new warning-after-exhaustion policy or replace the AI's validation steps.
    """
    if type(result.version_index) is not int or type(result.attempts) is not int:
        raise ValueError("Expected integer result version and attempt count.")
    if result.attempts < 0:
        raise ValueError("Result attempts must not be negative.")
    checked = QuestionResult.model_validate(result.model_dump())
    source_id = _uuid(checked.source_question_id)
    target = next(
        (
            target
            for target in plan.targets
            if target.source_question_id == source_id
            and target.version_index == checked.version_index
        ),
        None,
    )
    if target is None:
        raise ValueError("AI result is outside the generation plan.")
    _text(checked.request_fingerprint)
    candidate = checked.candidate
    if candidate is None:
        return PreparedAIResult(target, None, checked)
    report = checked.validation
    if (
        checked.error_code is not None
        or report is None
        or report.failures
        or _uuid(candidate.source_question_id) != source_id
    ):
        raise ValueError("AI candidate has inconsistent identity or validation state.")
    _text(candidate.variant_id)
    _text(candidate.blueprint_fingerprint)
    if (
        candidate.solution.correct_key != candidate.correct_key
        or normalized_text(candidate.solution.final_answer)
        != normalized_text(candidate.options["ABCD".index(candidate.correct_key)])
        or candidate.solution_md != render_solution(candidate.solution)
    ):
        raise ValueError("AI solution does not match the candidate's answer.")
    draft = GeneratedDraft(
        content=candidate.question_text,
        options=dict(zip("ABCD", candidate.options, strict=True)),
        correct_key=candidate.correct_key,
        solution_md=candidate.solution_md,
        has_warning=candidate.has_warning or report.has_warning,
        retry_count=max(checked.attempts - 1, 0),
        validation_report=report.model_dump(mode="json"),
    )
    return PreparedAIResult(target, draft, checked)

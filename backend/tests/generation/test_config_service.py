from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.models.generation_config import GenerationConfigRequest
from app.services.generation.config_service import (
    BlueprintConfigContext,
    GenerationConfigContext,
    GenerationConfigError,
    SourceQuestionConfigContext,
    validate_generation_config,
)

SESSION_ID = UUID(int=1)
QUESTION_1 = UUID(int=2)
QUESTION_2 = UUID(int=3)
CONFIRMED_AT = datetime(2026, 10, 26, tzinfo=timezone.utc)


def make_context() -> GenerationConfigContext:
    return GenerationConfigContext(
        session_id=SESSION_ID,
        status="blueprinted",
        source_questions=(
            SourceQuestionConfigContext(id=QUESTION_1, session_id=SESSION_ID),
            SourceQuestionConfigContext(id=QUESTION_2, session_id=SESSION_ID),
        ),
        blueprints=(
            BlueprintConfigContext(
                source_question_id=QUESTION_1,
                variation_modes=["NUMERICAL", "NONE"],
                confirmed_at=CONFIRMED_AT,
            ),
            BlueprintConfigContext(
                source_question_id=QUESTION_2,
                variation_modes=["NONE"],
                confirmed_at=CONFIRMED_AT,
            ),
        ),
    )


def make_config(modes: list[str] | None = None) -> GenerationConfigRequest:
    return GenerationConfigRequest(
        n_versions=2, active_variation_modes=["NONE"] if modes is None else modes
    )


def assert_domain_error(
    config: GenerationConfigRequest,
    context: GenerationConfigContext,
    status_code: int,
    code: str,
) -> GenerationConfigError:
    with pytest.raises(GenerationConfigError) as exc_info:
        validate_generation_config(config, context)
    error = exc_info.value
    assert error.status_code == status_code
    assert error.to_detail()["code"] == code
    assert isinstance(error.to_detail()["message"], str)
    assert error.to_detail()["message"]
    return error


@pytest.mark.parametrize("status", ["blueprinted", "configured"])
def test_accept_initial_save_and_overwrite_without_mutating_input(status: str) -> None:
    context = replace(make_context(), status=status)
    config = make_config()
    original_context = deepcopy(context)
    original_config = config.model_dump()
    validated = validate_generation_config(config, context)
    assert validated == config
    assert context == original_context
    assert config.model_dump() == original_config


@pytest.mark.parametrize(
    "status",
    [
        "draft",
        "generating",
        "partial_generated",
        "generated",
        "reviewed",
        "approved",
        "exported",
        "failed",
        "unknown-state",
    ],
)
def test_reject_non_configurable_states_even_for_empty_modes(status: str) -> None:
    error = assert_domain_error(
        make_config([]),
        replace(make_context(), status=status),
        409,
        "ERR_SESSION_NOT_CONFIGURABLE",
    )
    assert "conflicts" not in error.to_detail()


@pytest.mark.parametrize("count", [1, 20])
def test_accept_source_count_boundaries(count: int) -> None:
    sources = tuple(
        SourceQuestionConfigContext(id=UUID(int=100 + i), session_id=SESSION_ID)
        for i in range(count)
    )
    context = replace(
        make_context(),
        source_questions=sources,
        blueprints=tuple(
            BlueprintConfigContext(
                source_question_id=source.id,
                variation_modes=["NONE"],
                confirmed_at=CONFIRMED_AT,
            )
            for source in sources
        ),
    )
    assert validate_generation_config(make_config(), context).n_versions == 2


@pytest.mark.parametrize("count", [0, 21])
def test_reject_invalid_source_counts(count: int) -> None:
    context = replace(
        make_context(),
        source_questions=tuple(
            SourceQuestionConfigContext(id=UUID(int=100 + i), session_id=SESSION_ID)
            for i in range(count)
        ),
        blueprints=(),
    )
    assert_domain_error(make_config([]), context, 422, "ERR_SOURCE_NOT_READY")


@pytest.mark.parametrize("requested", [[], ["NONE"]])
@pytest.mark.parametrize("problem", ["missing", "duplicate", "unconfirmed", "orphan"])
def test_reject_blueprint_readiness_problems(problem: str, requested: list[str]) -> None:
    context = make_context()
    first, second = context.blueprints
    blueprints: tuple[BlueprintConfigContext, ...]
    if problem == "missing":
        blueprints = (first,)
    elif problem == "duplicate":
        blueprints = (first, second, first)
    elif problem == "unconfirmed":
        blueprints = (first, replace(second, confirmed_at=None))
    else:
        blueprints = (first, replace(second, source_question_id=UUID(int=999)))
    assert_domain_error(
        make_config(requested),
        replace(context, blueprints=blueprints),
        422,
        "ERR_SOURCE_NOT_READY",
    )


def test_reject_sources_from_another_session() -> None:
    context = make_context()
    first, second = context.source_questions
    context = replace(context, source_questions=(first, replace(second, session_id=UUID(int=999))))
    assert_domain_error(make_config([]), context, 422, "ERR_SOURCE_NOT_READY")


def test_reject_duplicate_sources() -> None:
    context = make_context()
    context = replace(context, source_questions=(context.source_questions[0],) * 2)
    assert_domain_error(make_config([]), context, 422, "ERR_SOURCE_NOT_READY")


def test_only_intersection_is_allowed_and_conflict_ids_are_json_safe() -> None:
    error = assert_domain_error(
        make_config(["NUMERICAL"]), make_context(), 400, "ERR_CONFIG_CONFLICT"
    )
    assert error.to_detail()["conflicts"] == [
        {"source_question_id": str(QUESTION_2), "unsupported_modes": ["NUMERICAL"]}
    ]


def test_conflicts_keep_question_and_requested_mode_order() -> None:
    error = assert_domain_error(
        make_config(["NEW_MODE", "NUMERICAL", "numerical"]),
        make_context(),
        400,
        "ERR_CONFIG_CONFLICT",
    )
    assert error.to_detail()["conflicts"] == [
        {"source_question_id": str(QUESTION_1), "unsupported_modes": ["NEW_MODE", "numerical"]},
        {
            "source_question_id": str(QUESTION_2),
            "unsupported_modes": ["NEW_MODE", "NUMERICAL", "numerical"],
        },
    ]


def test_supports_new_mode_ids_without_an_enum() -> None:
    context = make_context()
    context = replace(
        context,
        blueprints=tuple(replace(bp, variation_modes=["CUSTOM_MODE"]) for bp in context.blueprints),
    )
    assert validate_generation_config(
        make_config(["CUSTOM_MODE"]), context
    ).active_variation_modes == ["CUSTOM_MODE"]


def test_all_blueprints_can_support_numerical() -> None:
    context = make_context()
    context = replace(
        context,
        blueprints=tuple(replace(bp, variation_modes=["NUMERICAL"]) for bp in context.blueprints),
    )
    assert validate_generation_config(make_config(["NUMERICAL"]), context).n_versions == 2


def test_empty_request_does_not_select_modes_even_when_intersection_is_empty() -> None:
    context = make_context()
    first, second = context.blueprints
    context = replace(context, blueprints=(replace(first, variation_modes=["NUMERICAL"]), second))
    assert validate_generation_config(make_config([]), context).active_variation_modes == []


def test_empty_stored_modes_allow_only_an_empty_request() -> None:
    context = make_context()
    first, second = context.blueprints
    context = replace(context, blueprints=(first, replace(second, variation_modes=[])))
    assert validate_generation_config(make_config([]), context).active_variation_modes == []
    error = assert_domain_error(make_config(), context, 400, "ERR_CONFIG_CONFLICT")
    assert error.to_detail()["conflicts"] == [
        {"source_question_id": str(QUESTION_2), "unsupported_modes": ["NONE"]}
    ]


@pytest.mark.parametrize("requested", [[], ["NONE"]])
@pytest.mark.parametrize(
    "stored_modes", [None, "NONE", {"NONE": True}, [None], [1], [True], [""], [" \t"]]
)
def test_malformed_stored_modes_fail_safely_even_for_empty_request(
    stored_modes: object, requested: list[str]
) -> None:
    context = make_context()
    first, second = context.blueprints
    context = replace(context, blueprints=(first, replace(second, variation_modes=stored_modes)))
    error = assert_domain_error(make_config(requested), context, 500, "ERR_CONFIG_STORAGE_FAILURE")
    assert error.to_detail() == {
        "code": "ERR_CONFIG_STORAGE_FAILURE",
        "message": "Generation configuration could not be processed.",
    }


def test_duplicate_stored_modes_do_not_change_support_or_mutate_context() -> None:
    context = make_context()
    first, second = context.blueprints
    context = replace(
        context, blueprints=(first, replace(second, variation_modes=["NONE", "NONE"]))
    )
    original = deepcopy(context)
    validate_generation_config(make_config(), context)
    assert context == original

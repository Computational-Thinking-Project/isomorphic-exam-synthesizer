from copy import deepcopy
from dataclasses import replace
from uuid import UUID

import pytest

from app.models.generation_config import GenerationConfigRequest
from app.services.generation.config_service import (
    CanonicalBlueprintConfigContext,
    GenerationConfigContext,
    GenerationConfigError,
    SourceQuestionConfigContext,
    validate_generation_config,
)

SESSION_ID = UUID(int=1)
QUESTION_1 = UUID(int=2)
QUESTION_2 = UUID(int=3)


def make_context(count: int = 2) -> GenerationConfigContext:
    ids = (QUESTION_1, QUESTION_2) if count == 2 else tuple(UUID(int=100 + i) for i in range(count))
    transformation = {
        "id": "replace_values",
        "dimension": "values",
        "description": "Replace numerical values",
        "target_refs": [],
        "preconditions": [],
        "limits": [],
    }
    blueprint = {"requirement": {"variation_policy": {"allowed_transformations": [transformation]}}}
    return GenerationConfigContext(
        session_id=SESSION_ID,
        status="blueprinted",
        source_questions=tuple(SourceQuestionConfigContext(source, SESSION_ID) for source in ids),
        snapshot_ready=True,
        expected_snapshot={"confirmation_id": "fixture", "sources": []},
        canonical_blueprints=tuple(
            CanonicalBlueprintConfigContext(source, deepcopy(blueprint)) for source in ids
        ),
    )


def make_config() -> GenerationConfigRequest:
    return GenerationConfigRequest(n_versions=2)


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
    assert validated.active_variation_modes == []
    assert validated.n_versions == config.n_versions
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
    assert_domain_error(
        make_config(),
        replace(make_context(), status=status),
        409,
        "ERR_SESSION_NOT_CONFIGURABLE",
    )


def test_reject_approved_session_even_when_status_is_configured() -> None:
    assert_domain_error(
        make_config(),
        replace(make_context(), status="configured", approved=True),
        409,
        "ERR_SESSION_NOT_CONFIGURABLE",
    )


@pytest.mark.parametrize("count", [1, 20])
def test_accept_source_count_boundaries(count: int) -> None:
    assert validate_generation_config(make_config(), make_context(count)).n_versions == 2


@pytest.mark.parametrize("count", [0, 21])
def test_reject_invalid_source_counts(count: int) -> None:
    assert_domain_error(make_config(), make_context(count), 422, "ERR_SOURCE_NOT_READY")


@pytest.mark.parametrize(
    "reason", ["NO_CONFIRMATION", "ARTIFACT_STALE", "CANONICAL_BLUEPRINTS_INCOMPLETE"]
)
def test_unready_snapshot_is_rejected_even_when_sources_are_present(reason: str) -> None:
    context = replace(make_context(), snapshot_ready=False, snapshot_reason=reason)
    assert_domain_error(make_config(), context, 422, "ERR_SOURCE_NOT_READY")


def test_ready_snapshot_requires_manifest() -> None:
    context = replace(make_context(), expected_snapshot=None)
    assert_domain_error(make_config(), context, 500, "ERR_CONFIG_STORAGE_FAILURE")


@pytest.mark.parametrize("problem", ["missing", "duplicate", "orphan"])
def test_reject_blueprint_scope_problems(problem: str) -> None:
    context = make_context()
    first, second = context.canonical_blueprints
    broken = {
        "missing": (first,),
        "duplicate": (first, second, first),
        "orphan": (first, replace(second, source_question_id=UUID(int=999))),
    }
    assert_domain_error(
        make_config(),
        replace(context, canonical_blueprints=broken[problem]),
        422,
        "ERR_SOURCE_NOT_READY",
    )


def test_reject_sources_from_another_session() -> None:
    context = make_context()
    first, second = context.source_questions
    context = replace(context, source_questions=(first, replace(second, session_id=UUID(int=999))))
    assert_domain_error(make_config(), context, 422, "ERR_SOURCE_NOT_READY")


def test_reject_duplicate_sources() -> None:
    context = make_context()
    context = replace(context, source_questions=(context.source_questions[0],) * 2)
    assert_domain_error(make_config(), context, 422, "ERR_SOURCE_NOT_READY")


@pytest.mark.parametrize("damage", ["empty", "missing", "extra", "bad_dimension", "bad_reference"])
def test_malformed_canonical_policy_is_rejected_before_save(damage: str) -> None:
    context = make_context()
    first, second = context.canonical_blueprints
    blueprint = deepcopy(first.canonical_blueprint)
    transforms = blueprint["requirement"]["variation_policy"]["allowed_transformations"]
    if damage == "empty":
        transforms.clear()
    elif damage == "missing":
        del transforms[0]["id"]
    elif damage == "extra":
        transforms[0]["unexpected"] = True
    elif damage == "bad_dimension":
        transforms[0]["dimension"] = []
    else:
        transforms[0]["target_refs"] = [False]
    context = replace(
        context, canonical_blueprints=(replace(first, canonical_blueprint=blueprint), second)
    )
    assert_domain_error(make_config(), context, 422, "ERR_SOURCE_NOT_READY")

from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, call
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient
from supabase import Client

from app.api import dependencies
from app.api.routes import generation_config
from app.core import rate_limit
from app.core.cors import register_cors
from app.models.generation_config import GenerationConfigRequest, GenerationConfigResponse
from app.models.schemas import CurrentUser
from app.services.generation.config_repository import GenerationConfigStore
from app.services.generation.config_service import (
    BlueprintConfigContext,
    GenerationConfigContext,
    GenerationConfigError,
    SourceQuestionConfigContext,
    VariationModeConflict,
)

SESSION_ID = UUID(int=101)
SECOND_SESSION_ID = UUID(int=102)
OTHER_SESSION_ID = UUID(int=103)
USER_A = str(UUID(int=1))
USER_B = str(UUID(int=2))
TOKEN_A = "fixture-teacher-a-token"
TOKEN_B = "fixture-teacher-b-token"
HEADERS = {"Authorization": f"Bearer {TOKEN_A}"}
ORIGIN = "http://localhost:3000"
_UNSET = object()
STORAGE_DETAIL = {
    "code": "ERR_CONFIG_STORAGE_FAILURE",
    "message": "Generation configuration could not be processed.",
}


def make_context(session_id: UUID = SESSION_ID) -> GenerationConfigContext:
    ids = (UUID(int=session_id.int * 10 + 1), UUID(int=session_id.int * 10 + 2))
    return GenerationConfigContext(
        session_id=session_id,
        status="blueprinted",
        source_questions=tuple(
            SourceQuestionConfigContext(id=question_id, session_id=session_id)
            for question_id in ids
        ),
        blueprints=tuple(
            BlueprintConfigContext(
                source_question_id=question_id,
                variation_modes=["NUMERICAL", "NONE"] if index == 0 else ["NONE"],
                confirmed_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
            )
            for index, question_id in enumerate(ids)
        ),
    )


def payload(**overrides: object) -> dict[str, object]:
    return {"n_versions": 2, "active_variation_modes": ["NONE"], **overrides}


class FakeConfigStore:
    """Fixture-only persistence. This dictionary does not prove DB atomicity or RLS."""

    def __init__(self) -> None:
        self.contexts: dict[UUID, GenerationConfigContext | None] = {
            session_id: make_context(session_id)
            for session_id in (SESSION_ID, SECOND_SESSION_ID, OTHER_SESSION_ID)
        }
        self.saved: dict[UUID, dict[str, object]] = {}
        self.load_calls: list[UUID] = []
        self.save_calls: list[tuple[UUID, GenerationConfigRequest]] = []
        self.load_error: Exception | None = None
        self.save_error: Exception | None = None
        self.saved_result: object = _UNSET

    def load_context(self, session_id: UUID) -> GenerationConfigContext | None:
        self.load_calls.append(session_id)
        if self.load_error is not None:
            raise self.load_error
        return self.contexts.get(session_id)

    def save_config(self, session_id: UUID, config: GenerationConfigRequest) -> object:
        self.save_calls.append((session_id, config.model_copy(deep=True)))
        if self.save_error is not None:
            raise self.save_error
        if self.saved_result is not _UNSET:
            return self.saved_result
        context = self.contexts[session_id]
        assert context is not None
        self.contexts[session_id] = replace(context, status="configured")
        result: dict[str, object] = {
            "session_id": str(session_id),
            "status": "configured",
            "config": config.model_dump(),
        }
        self.saved[session_id] = deepcopy(result)
        return result


@dataclass
class ApiHarness:
    client: TestClient
    store: FakeConfigStore
    db: MagicMock
    factory: MagicMock
    ownership: MagicMock
    auth: MagicMock
    authenticated_client: MagicMock
    owners: dict[str, str]

    def post(self, body: object, session_id: UUID | str = SESSION_ID):
        return self.client.post(f"/api/sessions/{session_id}/config", json=body, headers=HEADERS)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    store = FakeConfigStore()
    db = MagicMock(spec=Client)
    owners = {
        str(SESSION_ID): USER_A,
        str(SECOND_SESSION_ID): USER_A,
        str(OTHER_SESSION_ID): USER_B,
    }
    query = MagicMock()
    query.select.return_value = query
    selected_id = {"id": ""}

    def select_id(column: str, value: str) -> MagicMock:
        assert column == "id"
        selected_id["id"] = value
        return query

    def owner_result() -> SimpleNamespace:
        owner = owners.get(selected_id["id"])
        return SimpleNamespace(data=[] if owner is None else [{"user_id": owner}])

    query.eq.side_effect = select_id
    query.execute.side_effect = owner_result
    db.table.return_value = query

    auth = MagicMock()

    def verified_user(token: str) -> SimpleNamespace:
        user_id = {TOKEN_A: USER_A, TOKEN_B: USER_B}.get(token)
        user = (
            SimpleNamespace(id=user_id, email="teacher@example.test", user_metadata={})
            if user_id is not None
            else None
        )
        return SimpleNamespace(user=user)

    auth.auth.get_user.side_effect = verified_user
    authenticated_client = MagicMock(return_value=db)
    monkeypatch.setattr(dependencies, "get_supabase_client", lambda: auth)
    monkeypatch.setattr(dependencies, "get_authenticated_client", authenticated_client)
    ownership = MagicMock(wraps=dependencies.assert_ownership)
    monkeypatch.setattr(generation_config, "assert_ownership", ownership)
    factory = MagicMock(return_value=store)
    factory_function = cast(Callable[[Client], GenerationConfigStore], factory)

    app = FastAPI()
    test_limiter = rate_limit.create_limiter()
    rate_limit.register_rate_limiter(app, test_limiter)
    register_cors(app, ORIGIN)
    app.include_router(
        generation_config.create_generation_config_router(
            factory_function, limiter_instance=test_limiter
        ),
        prefix="/api/sessions",
    )

    def shared_crud(
        request: Request,
        response: Response,
        current_user: CurrentUser = Depends(dependencies.get_current_user),
    ) -> dict[str, str]:
        return {"user_id": current_user.id}

    app.add_api_route(
        "/test/shared-crud",
        rate_limit.crud_rate_limit(shared_crud, limiter_instance=test_limiter),
        methods=["GET"],
    )
    with TestClient(app) as client:
        yield ApiHarness(client, store, db, factory, ownership, auth, authenticated_client, owners)


def test_success_normalizes_request_and_reuses_auth_and_ownership(api: ApiHarness) -> None:
    response = api.post(payload(active_variation_modes=[" NONE ", "NONE"]))
    assert response.status_code == 200
    assert response.json() == {
        "session_id": str(SESSION_ID),
        "status": "configured",
        "config": {
            "n_versions": 2,
            "active_variation_modes": ["NONE"],
            "ordering_preferences": {"shuffle_questions": True, "shuffle_options": True},
        },
    }
    api.auth.auth.get_user.assert_called_once_with(TOKEN_A)
    api.authenticated_client.assert_called_once_with(TOKEN_A)
    api.ownership.assert_called_once_with("exam_sessions", str(SESSION_ID), USER_A, db=api.db)
    api.factory.assert_called_once_with(api.db)
    assert api.store.load_calls == [SESSION_ID]
    assert api.store.save_calls[0][1].active_variation_modes == ["NONE"]
    assert response.headers["X-RateLimit-Limit"] == "60"


@pytest.mark.parametrize("session_status", ["blueprinted", "configured"])
def test_empty_modes_and_partial_false_ordering_are_preserved(
    api: ApiHarness, session_status: str
) -> None:
    api.store.contexts[SESSION_ID] = replace(make_context(), status=session_status)
    response = api.post(
        payload(active_variation_modes=[], ordering_preferences={"shuffle_options": False})
    )
    assert response.status_code == 200
    assert response.json()["config"]["active_variation_modes"] == []
    assert response.json()["config"]["ordering_preferences"] == {
        "shuffle_questions": True,
        "shuffle_options": False,
    }


def test_save_again_uses_configured_context_and_returns_latest_fake_record(api: ApiHarness) -> None:
    assert api.post(payload()).status_code == 200
    response = api.post(payload(n_versions=4, active_variation_modes=[]))
    assert response.status_code == 200
    assert response.json()["config"]["n_versions"] == 4
    assert len(api.store.saved) == 1
    assert api.store.saved[SESSION_ID] == response.json()
    assert len(api.store.save_calls) == 2


def test_returns_validated_saved_data_instead_of_echoing_request(api: ApiHarness) -> None:
    api.store.saved_result = {
        "session_id": str(SESSION_ID),
        "status": "configured",
        "config": payload(n_versions=4),
    }
    response = api.post(payload(n_versions=2))
    assert response.status_code == 200
    assert response.json()["config"]["n_versions"] == 4


@pytest.mark.parametrize(
    "authorization", [None, "Basic invalid", "Bearer", "Bearer ", "Bearer invalid"]
)
def test_invalid_or_missing_auth_stops_before_repository(
    api: ApiHarness, authorization: str | None
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}
    response = api.client.post(
        f"/api/sessions/{SESSION_ID}/config", json=payload(), headers=headers
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    api.authenticated_client.assert_not_called()
    api.ownership.assert_not_called()
    api.factory.assert_not_called()
    assert api.store.save_calls == []


def test_non_owner_is_rejected_before_repository(api: ApiHarness) -> None:
    response = api.post(payload(), OTHER_SESSION_ID)
    assert response.status_code == 403
    api.factory.assert_not_called()
    assert api.store.load_calls == []


def test_ownership_not_found_or_rls_hidden_row_returns_404(api: ApiHarness) -> None:
    del api.owners[str(SESSION_ID)]
    assert api.post(payload()).status_code == 404
    api.factory.assert_not_called()


def test_session_disappearing_after_ownership_returns_404(api: ApiHarness) -> None:
    api.store.contexts[SESSION_ID] = None
    response = api.post(payload())
    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found"}
    assert api.store.save_calls == []


def test_invalid_uuid_is_rejected_before_endpoint_body(api: ApiHarness) -> None:
    response = api.post(payload(), "invalid-uuid")
    assert response.status_code == 422
    api.ownership.assert_not_called()
    api.factory.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"n_versions": 2},
        payload(n_versions=True),
        payload(n_versions=5),
        payload(n_versions="2"),
        payload(active_variation_modes=None),
        payload(active_variation_modes=[""]),
        payload(ordering_preferences=None),
        payload(ordering_preferences={"shuffle_options": "false"}),
        payload(user_id=USER_B),
        payload(status="configured"),
    ],
)
def test_invalid_payload_does_not_reach_ownership_or_repository(
    api: ApiHarness, body: object
) -> None:
    response = api.post(body)
    assert response.status_code == 422
    api.ownership.assert_not_called()
    api.factory.assert_not_called()
    assert api.store.save_calls == []


@pytest.mark.parametrize("session_status", ["draft", "generating", "generated"])
def test_invalid_session_state_returns_domain_409_without_save(
    api: ApiHarness, session_status: str
) -> None:
    api.store.contexts[SESSION_ID] = replace(make_context(), status=session_status)
    response = api.post(payload())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_SESSION_NOT_CONFIGURABLE"
    assert api.store.save_calls == []


@pytest.mark.parametrize("problem", ["empty_sources", "missing_blueprint", "unconfirmed_blueprint"])
def test_source_readiness_returns_domain_422_without_save(api: ApiHarness, problem: str) -> None:
    context = make_context()
    if problem == "empty_sources":
        context = replace(context, source_questions=(), blueprints=())
    elif problem == "missing_blueprint":
        context = replace(context, blueprints=context.blueprints[:1])
    else:
        first, second = context.blueprints
        context = replace(context, blueprints=(replace(first, confirmed_at=None), second))
    api.store.contexts[SESSION_ID] = context
    response = api.post(payload(active_variation_modes=[]))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ERR_SOURCE_NOT_READY"
    assert api.store.save_calls == []


def test_mode_conflicts_return_question_details_without_save(api: ApiHarness) -> None:
    response = api.post(payload(active_variation_modes=["NUMERICAL"]))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_CONFIG_CONFLICT"
    assert response.json()["detail"]["conflicts"] == [
        {
            "source_question_id": str(make_context().source_questions[1].id),
            "unsupported_modes": ["NUMERICAL"],
        }
    ]
    assert api.store.save_calls == []


def test_malformed_stored_modes_return_safe_500(api: ApiHarness) -> None:
    context = make_context()
    first, second = context.blueprints
    api.store.contexts[SESSION_ID] = replace(
        context, blueprints=(replace(first, variation_modes=None), second)
    )
    response = api.post(payload(active_variation_modes=[]))
    assert response.status_code == 500
    assert response.json() == {"detail": STORAGE_DETAIL}
    assert api.store.save_calls == []


@pytest.mark.parametrize("phase", ["factory", "read", "save"])
def test_unexpected_repository_failures_do_not_leak_or_retry(api: ApiHarness, phase: str) -> None:
    error = RuntimeError("private storage details must not appear in HTTP")
    if phase == "factory":
        api.factory.side_effect = error
    elif phase == "read":
        api.store.load_error = error
    else:
        api.store.save_error = error
    response = api.post(payload())
    assert response.status_code == 500
    assert response.json() == {"detail": STORAGE_DETAIL}
    assert api.store.saved == {}
    assert len(api.store.save_calls) == (1 if phase == "save" else 0)


@pytest.mark.parametrize("phase", ["factory", "read", "save"])
def test_adapter_http_exceptions_are_not_trusted_public_errors(api: ApiHarness, phase: str) -> None:
    from fastapi import HTTPException

    error = HTTPException(502, "private DB endpoint and credentials")
    if phase == "factory":
        api.factory.side_effect = error
    elif phase == "read":
        api.store.load_error = error
    else:
        api.store.save_error = error
    response = api.post(payload())
    assert response.status_code == 500
    assert response.json() == {"detail": STORAGE_DETAIL}


def test_unexpected_ownership_storage_failure_is_safe(api: ApiHarness) -> None:
    api.ownership.side_effect = RuntimeError("private DB endpoint")
    response = api.post(payload())
    assert response.status_code == 500
    assert response.json() == {"detail": STORAGE_DETAIL}
    api.factory.assert_not_called()


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (409, "ERR_SESSION_NOT_CONFIGURABLE"),
        (422, "ERR_SOURCE_NOT_READY"),
        (500, "ERR_CONFIG_STORAGE_FAILURE"),
    ],
)
def test_save_recheck_errors_are_propagated_without_success(
    api: ApiHarness, status_code: int, code: str
) -> None:
    api.store.save_error = GenerationConfigError(status_code, code, "Save recheck rejected.")
    response = api.post(payload())
    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert len(api.store.save_calls) == 1
    assert api.store.saved == {}


def test_save_recheck_mode_conflicts_keep_details(api: ApiHarness) -> None:
    question_id = make_context().source_questions[0].id
    api.store.save_error = GenerationConfigError(
        400,
        "ERR_CONFIG_CONFLICT",
        "Blueprint changed before save.",
        (VariationModeConflict(question_id, ("NONE",)),),
    )
    response = api.post(payload())
    assert response.status_code == 400
    assert response.json()["detail"]["conflicts"] == [
        {"source_question_id": str(question_id), "unsupported_modes": ["NONE"]}
    ]
    assert api.store.saved == {}


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        {},
        {"session_id": str(SESSION_ID), "status": "blueprinted", "config": payload()},
        {"session_id": str(OTHER_SESSION_ID), "status": "configured", "config": payload()},
        {"session_id": str(SESSION_ID), "status": "configured", "config": payload(n_versions="2")},
        {"session_id": str(SESSION_ID), "status": "configured", "config": None},
    ],
)
def test_malformed_or_wrong_session_saved_results_never_return_success(
    api: ApiHarness, result: object
) -> None:
    api.store.saved_result = result
    response = api.post(payload())
    assert response.status_code == 500
    assert response.json() == {"detail": STORAGE_DETAIL}
    assert len(api.store.save_calls) == 1


def test_saved_response_model_is_revalidated_at_http_boundary(api: ApiHarness) -> None:
    saved = GenerationConfigResponse.model_validate(
        {"session_id": str(SESSION_ID), "status": "configured", "config": payload()}
    )
    saved.config.n_versions = 99
    api.store.saved_result = saved
    response = api.post(payload())
    assert response.status_code == 500
    assert response.json() == {"detail": STORAGE_DETAIL}


def test_wrong_context_session_is_rejected_before_save(api: ApiHarness) -> None:
    api.store.contexts[SESSION_ID] = make_context(OTHER_SESSION_ID)
    response = api.post(payload())
    assert response.status_code == 500
    assert response.json() == {"detail": STORAGE_DETAIL}
    assert api.store.save_calls == []


def test_quota_is_shared_across_crud_routes_and_config_session_ids(api: ApiHarness) -> None:
    for index in range(30):
        session_id = SESSION_ID if index % 2 == 0 else SECOND_SESSION_ID
        assert api.post(payload(), session_id).status_code == 200
        assert api.client.get("/test/shared-crud", headers=HEADERS).status_code == 200
    response = api.client.post(
        f"/api/sessions/{SESSION_ID}/config",
        json=payload(),
        headers={**HEADERS, "Origin": ORIGIN},
    )
    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}
    assert int(response.headers["Retry-After"]) >= 1
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "retry-after" in response.headers["Access-Control-Expose-Headers"].lower()
    assert len(api.store.save_calls) == 30


def test_verified_users_on_same_test_client_have_separate_quotas(api: ApiHarness) -> None:
    for _ in range(60):
        assert api.post(payload()).status_code == 200
    assert api.post(payload()).status_code == 429
    response = api.client.post(
        f"/api/sessions/{OTHER_SESSION_ID}/config",
        json=payload(),
        headers={"Authorization": f"Bearer {TOKEN_B}"},
    )
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "59"
    assert api.store.load_calls[-1] == OTHER_SESSION_ID
    assert api.authenticated_client.call_args == call(TOKEN_B)

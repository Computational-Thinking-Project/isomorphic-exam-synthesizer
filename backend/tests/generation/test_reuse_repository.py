"""EXT-02 Step 7 core: reuse repository contract (RPC is covered by test_reuse_source_pg.py)."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError
from pydantic import ValidationError

from app.services.generation.reuse_repository import ReuseError, ReuseRequest, reuse_source

SESSION = uuid4()
VERSION = uuid4()


def request(**overrides) -> ReuseRequest:
    data = dict(source_session_id=SESSION, source_type="version", source_version_id=VERSION,
                generation_mode="shuffle_only", idempotency_key="key-1")
    data.update(overrides)
    return ReuseRequest(**data)


def receipt(**overrides) -> dict:
    data = {
        "success": True, "replayed": False, "session_id": str(uuid4()), "status": "draft",
        "next_step": "confirm_source", "generation_mode": "shuffle_only", "question_count": 3,
        "source": {"source_type": "version", "source_session_id": str(SESSION),
                   "source_version_id": str(VERSION), "new_source_order": [3, 1, 2]},
    }
    data.update(overrides)
    return data


def client(data=None, error: APIError | None = None) -> MagicMock:
    db = MagicMock()
    if error is not None:
        db.rpc.return_value.execute.side_effect = error
    else:
        db.rpc.return_value.execute.return_value = SimpleNamespace(data=data)
    return db


def test_sends_exact_rpc_parameters_and_returns_receipt() -> None:
    db = client(receipt())
    result = reuse_source(db, request())
    assert result.next_step == "confirm_source" and result.source.new_source_order == [3, 1, 2]
    db.rpc.assert_called_once_with("reuse_session_source", {
        "p_source_session_id": str(SESSION), "p_source_type": "version",
        "p_source_version_id": str(VERSION), "p_generation_mode": "shuffle_only",
        "p_idempotency_key": "key-1",
    })


def test_original_source_sends_null_version() -> None:
    data = receipt(generation_mode="ai_generation")
    data["source"].update(source_type="original", source_version_id=None)
    db = client(data)
    reuse_source(db, request(source_type="original", source_version_id=None, generation_mode="ai_generation"))
    assert db.rpc.call_args.args[1]["p_source_version_id"] is None


@pytest.mark.parametrize("overrides", [
    {"source_type": "version", "source_version_id": None},
    {"source_type": "original", "source_version_id": VERSION},
    {"generation_mode": "bogus"},
    {"idempotency_key": ""},
    {"source_type": "clone"},
])
def test_request_validation(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        request(**overrides)


@pytest.mark.parametrize(("code", "message", "status", "error"), [
    ("P0002", "Session not found", 404, "ERR_NOT_FOUND"),
    ("42501", "Access denied", 403, "ERR_FORBIDDEN"),
    ("22023", "ERR_IDEMPOTENCY_CONFLICT", 409, "ERR_IDEMPOTENCY_CONFLICT"),
    ("55000", "ERR_SOURCE_NOT_APPROVED", 409, "ERR_SOURCE_NOT_APPROVED"),
    ("22023", "ERR_SOURCE_NOT_READY: source must have 1-20 questions", 422, "ERR_SOURCE_NOT_READY"),
    ("XX000", "boom", 500, "ERR_REUSE_STORAGE_FAILURE"),
])
def test_maps_database_errors(code: str, message: str, status: int, error: str) -> None:
    with pytest.raises(ReuseError) as exc_info:
        reuse_source(client(error=APIError({"code": code, "message": message})), request())
    assert (exc_info.value.status_code, exc_info.value.code) == (status, error)


@pytest.mark.parametrize("damage", [
    {"generation_mode": "ai_generation"},
    {"status": "reviewed"},
    {"question_count": 2},
    {"question_count": 21},
    {"source": {"source_type": "original", "source_session_id": str(SESSION), "source_version_id": None,
                "new_source_order": [1, 2, 3]}},
    {"extra": True},
])
def test_rejects_receipt_that_does_not_match_request(damage: dict) -> None:
    with pytest.raises(ReuseError) as exc_info:
        reuse_source(client(receipt(**damage)), request())
    assert exc_info.value.status_code == 500

"""API Endpoint and Integration Tests for Post-Shuffle Pre-Approval Preview Projection (W4-MVP-05).

Covers:
1. Authentication & Ownership:
   - 401 unauthenticated
   - 403 forbidden / unauthorized ownership
2. Parameter & Session Validation:
   - 400 ERR_INVALID_SESSION_ID (malformed UUID)
   - 404 ERR_SESSION_NOT_FOUND (nonexistent session)
   - 409 ERR_INVALID_SESSION_STATE (status not reviewed/approved/exported)
   - 409 ERR_SHUFFLE_REQUIRED (reviewed session before finalize shuffle)
3. Consistency Checks:
   - 409 ERR_INCONSISTENT_ANSWER_KEYS (missing questions, non-contiguous question_no, mismatched answer key)
4. Success Scenarios:
   - 200 OK pre-approval preview projection (session status = 'reviewed', is_finalized = True)
   - 200 OK post-approval preview projection (session status = 'approved')
   - Deterministic repeated GET (idempotent, read-only, zero side effects)
   - Parity with ApprovedExportSnapshot schema
"""

from typing import Any, Dict
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.main import app
from app.models.schemas import (
    CurrentUser,
    PreviewSnapshotResponse,
    ReviewDomainException,
)
from app.services.exporter.bundle_models import (
    ApprovedExportSnapshot,
    DisplayQuestion,
    DisplayVersion,
)
from app.services.finalize.service import FinalizeService
from tests.services.finalize_test_client import MockSupabaseClient

MOCK_SESSION_ID = "00000000-0000-0000-0000-000000000001"
MOCK_USER_ID = "user-123456"
OTHER_USER_ID = "user-999999"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer mock-valid-jwt-token"}


@pytest.fixture
def mock_current_user() -> CurrentUser:
    return CurrentUser(
        id=MOCK_USER_ID,
        email="teacher@school.edu.vn",
        name="Thầy Nguyễn Bá Duy",
        access_token="mock-valid-jwt-token",
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _build_valid_preview_db_state(
    session_id: str = MOCK_SESSION_ID,
    user_id: str = MOCK_USER_ID,
    status: str = "reviewed",
    is_finalized: bool = True,
) -> Dict[str, Any]:
    v1_id = "10100000-0000-0000-0000-000000000101"
    v2_id = "10200000-0000-0000-0000-000000000102"
    s1_id = "00000000-0000-0000-0000-000000000001"
    s2_id = "00000000-0000-0000-0000-000000000002"

    return {
        "exam_sessions": [
            {
                "id": session_id,
                "user_id": user_id,
                "status": status,
                "is_finalized": is_finalized,
                "updated_at": "2026-11-06T10:00:00Z",
            }
        ],
        "generation_configs": [
            {
                "id": str(uuid4()),
                "session_id": session_id,
                "n_versions": 2,
            }
        ],
        "exam_versions": [
            {
                "id": v1_id,
                "session_id": session_id,
                "version_code": "101",
                "is_finalized": is_finalized,
                "shuffle_seed": "seed-101",
            },
            {
                "id": v2_id,
                "session_id": session_id,
                "version_code": "102",
                "is_finalized": is_finalized,
                "shuffle_seed": "seed-102",
            },
        ],
        "source_questions": [
            {"id": s1_id, "session_id": session_id, "question_no": 1},
            {"id": s2_id, "session_id": session_id, "question_no": 2},
        ],
        "version_questions": [
            # Version 101 questions
            {
                "id": str(uuid4()),
                "version_id": v1_id,
                "source_question_id": s2_id,
                "question_no": 1,
                "canonical_question_no": 2,
                "content": "Câu hỏi đạo hàm",
                "options": ["A1", "B1", "C1", "D1"],
                "correct_key": "C",
                "solution_md": "Lời giải câu 1. Đáp án đúng là C.",
                "status": "approved",
                "is_current": True,
            },
            {
                "id": str(uuid4()),
                "version_id": v1_id,
                "source_question_id": s1_id,
                "question_no": 2,
                "canonical_question_no": 1,
                "content": "Câu hỏi tích phân",
                "options": ["A2", "B2", "C2", "D2"],
                "correct_key": "A",
                "solution_md": "Lời giải câu 2. Đáp án đúng là A.",
                "status": "approved",
                "is_current": True,
            },
            # Version 102 questions
            {
                "id": str(uuid4()),
                "version_id": v2_id,
                "source_question_id": s1_id,
                "question_no": 1,
                "canonical_question_no": 1,
                "content": "Câu hỏi tích phân",
                "options": ["B2", "A2", "D2", "C2"],
                "correct_key": "B",
                "solution_md": "Lời giải câu 1 mã 102. Đáp án đúng là B.",
                "status": "approved",
                "is_current": True,
            },
            {
                "id": str(uuid4()),
                "version_id": v2_id,
                "source_question_id": s2_id,
                "question_no": 2,
                "canonical_question_no": 2,
                "content": "Câu hỏi đạo hàm",
                "options": ["D1", "C1", "B1", "A1"],
                "correct_key": "B",
                "solution_md": "Lời giải câu 2 mã 102. Đáp án đúng là B.",
                "status": "approved",
                "is_current": True,
            },
        ],
        "answer_keys": [
            {"version_id": v1_id, "question_no": 1, "correct_option": "C", "display_no": 1, "display_correct_key": "C"},
            {"version_id": v1_id, "question_no": 2, "correct_option": "A", "display_no": 2, "display_correct_key": "A"},
            {"version_id": v2_id, "question_no": 1, "correct_option": "B", "display_no": 1, "display_correct_key": "B"},
            {"version_id": v2_id, "question_no": 2, "correct_option": "B", "display_no": 2, "display_correct_key": "B"},
        ],
    }


# ==============================================================================
# 1. Authentication and Ownership Tests
# ==============================================================================


def test_preview_endpoint_unauthenticated(client: TestClient):
    """Calling GET /finalize/preview without Authorization header returns 401."""
    app.dependency_overrides.clear()
    res = client.get(f"/api/sessions/{MOCK_SESSION_ID}/finalize/preview")
    assert res.status_code == 401


def test_preview_endpoint_invalid_uuid_format(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """Calling with malformed session_id returns 400 ERR_INVALID_SESSION_ID before DB call."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with patch("app.api.routes.finalize.assert_ownership") as mock_assert:
            res = client.get(
                "/api/sessions/invalid-uuid-string/finalize/preview",
                headers=auth_headers,
            )
            assert res.status_code == 400
            assert res.json().get("error_code") == "ERR_INVALID_SESSION_ID"
            mock_assert.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_preview_ownership_denied(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """assert_ownership raising 403 Forbidden is propagated properly."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with patch(
            "app.api.routes.finalize.assert_ownership",
            side_effect=HTTPException(status_code=403, detail="Forbidden resource"),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/finalize/preview",
                headers=auth_headers,
            )
            assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. Domain & State Guard Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_preview_session_not_found():
    """Requesting preview for nonexistent session raises 404 ERR_SESSION_NOT_FOUND."""
    client = MockSupabaseClient({})
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "ERR_SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_preview_cross_user_forbidden():
    """Requesting preview for session owned by another user raises 403 ERR_UNAUTHORIZED."""
    db_state = _build_valid_preview_db_state(user_id=OTHER_USER_ID)
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "ERR_UNAUTHORIZED"


@pytest.mark.asyncio
async def test_preview_invalid_session_state_generating():
    """Requesting preview when session is still 'generating' raises 409 ERR_INVALID_SESSION_STATE."""
    db_state = _build_valid_preview_db_state(status="generating")
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INVALID_SESSION_STATE"


@pytest.mark.asyncio
async def test_preview_shuffle_required_when_not_finalized():
    """Requesting preview on reviewed session where shuffle has not run raises 409 ERR_SHUFFLE_REQUIRED."""
    db_state = _build_valid_preview_db_state(is_finalized=False)
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_SHUFFLE_REQUIRED"


@pytest.mark.asyncio
async def test_preview_inconsistent_missing_questions():
    """When a version has fewer questions than source questions, raises 409 ERR_INCONSISTENT_ANSWER_KEYS."""
    db_state = _build_valid_preview_db_state()
    # Remove one question from version 101
    db_state["version_questions"].pop(0)
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"


@pytest.mark.asyncio
async def test_preview_inconsistent_answer_key_mismatch():
    """When answer_keys table does not match version_questions.correct_key, raises 409."""
    db_state = _build_valid_preview_db_state()
    # Change answer key for question 1 in version 101 to 'D' (question has 'C')
    db_state["answer_keys"][0]["correct_option"] = "D"
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"


# ==============================================================================
# 3. Success & Consistency Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_preview_success_reviewed_state():
    """Pre-approval preview returns 200 OK with full display projection in reviewed state."""
    db_state = _build_valid_preview_db_state()
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    res = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert isinstance(res, PreviewSnapshotResponse)
    assert res.session_id == MOCK_SESSION_ID
    assert res.status == "reviewed"
    assert res.is_finalized is True
    assert res.n_versions == 2
    assert res.total_questions == 2
    assert len(res.versions) == 2

    # Verify version 101
    v101 = res.versions[0]
    assert v101.version_code == "101"
    assert v101.total_questions == 2
    assert [q.question_no for q in v101.questions] == [1, 2]
    assert v101.questions[0].canonical_question_no == 2
    assert v101.questions[0].correct_key == "C"
    assert v101.questions[0].options == ["A1", "B1", "C1", "D1"]
    assert "C" in v101.questions[0].solution_md
    assert v101.answer_keys == {"1": "C", "2": "A"}

    # Verify version 102
    v102 = res.versions[1]
    assert v102.version_code == "102"
    assert v102.answer_keys == {"1": "B", "2": "B"}

    # Verify cross-version matrix
    assert len(res.matrix) == 2
    assert res.matrix[0].question_no == 1
    assert res.matrix[0].answers == {"101": "C", "102": "B"}
    assert res.matrix[1].question_no == 2
    assert res.matrix[1].answers == {"101": "A", "102": "B"}


@pytest.mark.asyncio
async def test_preview_success_approved_state():
    """Post-approval preview returns 200 OK (read-only immutable access)."""
    db_state = _build_valid_preview_db_state(status="approved")
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    res = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert res.status == "approved"
    assert res.is_finalized is True
    assert len(res.versions) == 2


@pytest.mark.asyncio
async def test_preview_repeat_get_deterministic():
    """Repeated calls to get_preview_snapshot produce identical results with zero mutations."""
    db_state = _build_valid_preview_db_state()
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    res1 = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    res2 = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)

    assert res1.model_dump() == res2.model_dump()
    # Confirm zero write operations occurred
    assert len(client.call_log) == 0


@pytest.mark.asyncio
async def test_preview_direct_parity_with_approved_export_snapshot():
    """Projection matches the exact requirements to instantiate ApprovedExportSnapshot."""
    db_state = _build_valid_preview_db_state()
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    res = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)

    # Transform into bundle_models structure
    export_versions = []
    for v in res.versions:
        display_questions = [
            DisplayQuestion(
                id=UUID(q.id),
                question_no=q.question_no,
                content=q.content,
                options=(q.options[0], q.options[1], q.options[2], q.options[3]),
                correct_key=q.correct_key,
                solution_md=q.solution_md,
                status="approved",
            )
            for q in v.questions
        ]
        export_versions.append(
            DisplayVersion(code=v.version_code, questions=tuple(display_questions))
        )

    export_snapshot = ApprovedExportSnapshot(
        session_id=UUID(res.session_id),
        revision="rev-01",
        title="Đề thi thử THPT",
        status="approved",
        versions=tuple(export_versions),
    )

    assert len(export_snapshot.versions) == 2
    assert export_snapshot.versions[0].code == "101"
    assert export_snapshot.versions[1].code == "102"
    assert export_snapshot.versions[0].questions[0].correct_key == "C"


# ==============================================================================
# 4. HTTP Router Integration Test
# ==============================================================================


def test_preview_router_integration_success(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """Full HTTP GET test via FastAPI TestClient returning 200 OK."""
    db_state = _build_valid_preview_db_state()
    mock_db = MockSupabaseClient(db_state)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: mock_db

    try:
        with patch("app.api.routes.finalize.assert_ownership"):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/finalize/preview",
                headers=auth_headers,
            )
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            data = res.json()
            assert data["session_id"] == MOCK_SESSION_ID
            assert data["status"] == "reviewed"
            assert data["is_finalized"] is True
            assert len(data["versions"]) == 2
            assert len(data["matrix"]) == 2
            assert data["matrix"][0]["answers"] == {"101": "C", "102": "B"}
    finally:
        app.dependency_overrides.clear()

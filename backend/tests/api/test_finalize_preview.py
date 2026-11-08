"""API Endpoint and Integration Tests for Post-Shuffle Pre-Approval Preview Projection (W4-MVP-05).

Covers:
1. Authentication & Ownership:
   - 401 unauthenticated
   - 403 forbidden / unauthorized ownership
   - 404 session not found
2. Parameter & Session Validation:
   - 400 ERR_INVALID_SESSION_ID (malformed UUID)
   - 404 ERR_SESSION_NOT_FOUND (nonexistent session)
   - 409 ERR_INVALID_SESSION_STATE (status not reviewed/approved/exported)
   - 409 ERR_SHUFFLE_REQUIRED (reviewed session before finalize shuffle)
3. Exporter Invariants & Consistency Checks:
   - 409 ERR_INCONSISTENT_ANSWER_KEYS for empty content
   - 409 ERR_INCONSISTENT_ANSWER_KEYS for empty/whitespace solution_md
   - 409 ERR_INCONSISTENT_ANSWER_KEYS for duplicate normalized options
   - 409 ERR_INCONSISTENT_ANSWER_KEYS for unapproved question status
   - 409 ERR_INCONSISTENT_ANSWER_KEYS for missing/corrupted shuffle permutations
   - 409 ERR_INCONSISTENT_ANSWER_KEYS for invalid/mismatched canonical question mapping
   - 409 ERR_INCONSISTENT_ANSWER_KEYS for duplicate/mismatched answer keys
   - 409 ERR_INCONSISTENT_ANSWER_KEYS for > 20 questions
4. Success Scenarios:
   - 200 OK Golden 3-question x 2-version OFF/OFF fixture
   - 200 OK ON/ON shuffled case
   - 200 OK post-approval preview projection (session status = 'approved')
   - Deterministic repeated GET (idempotent, read-only, zero side effects)
   - Construction of ApprovedExportSnapshot using actual session title and revision
"""

import json
import os
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
from app.services.finalize.repository import FinalizeRepository
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
    n_questions: int = 3,
) -> Dict[str, Any]:
    """Build a valid 3-question x 2-version Golden OFF/OFF test database state."""
    v1_id = "10100000-0000-0000-0000-000000000101"
    v2_id = "10200000-0000-0000-0000-000000000102"
    s1_id = "00000000-0000-0000-0000-000000000001"
    s2_id = "00000000-0000-0000-0000-000000000002"
    s3_id = "00000000-0000-0000-0000-000000000003"

    identity_permutations = {
        "question_order": [1, 2, 3],
        "display_to_canonical": {"1": 1, "2": 2, "3": 3},
        "canonical_to_display": {"1": 1, "2": 2, "3": 3},
        "option_permutations": {
            "1": {"A": "A", "B": "B", "C": "C", "D": "D"},
            "2": {"A": "A", "B": "B", "C": "C", "D": "D"},
            "3": {"A": "A", "B": "B", "C": "C", "D": "D"},
        },
    }

    return {
        "exam_sessions": [
            {
                "id": session_id,
                "user_id": user_id,
                "title": "Đề thi thử THPT Quốc Gia môn Toán 2026",
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
                "shuffle_seed": "golden-seed-w4-101",
                "permutations": identity_permutations,
            },
            {
                "id": v2_id,
                "session_id": session_id,
                "version_code": "102",
                "is_finalized": is_finalized,
                "shuffle_seed": "golden-seed-w4-102",
                "permutations": identity_permutations,
            },
        ],
        "source_questions": [
            {"id": s1_id, "session_id": session_id, "question_no": 1},
            {"id": s2_id, "session_id": session_id, "question_no": 2},
            {"id": s3_id, "session_id": session_id, "question_no": 3},
        ],
        "version_questions": [
            # Version 101 questions
            {
                "id": "11111111-0000-0000-0000-000000000101",
                "version_id": v1_id,
                "source_question_id": s1_id,
                "question_no": 1,
                "canonical_question_no": 1,
                "content": "Cho hàm số $y = x^3 - 3x + 2$. Điểm cực đại của hàm số đã cho là:",
                "options": ["$x = -1$", "$x = 1$", "$x = 2$", "$x = 0$"],
                "correct_key": "A",
                "solution_md": "Đạo hàm $y' = 3x^2 - 3 = 0 \\iff x = \\pm 1$. Vì $y''(-1) = -6 < 0$ nên điểm cực đại là $x = -1$. Do đó đáp án đúng là A.",
                "canonical_options": ["$x = -1$", "$x = 1$", "$x = 2$", "$x = 0$"],
                "canonical_correct_key": "A",
                "canonical_solution_md": "Đạo hàm $y' = 3x^2 - 3 = 0 \\iff x = \\pm 1$. Vì $y''(-1) = -6 < 0$ nên điểm cực đại là $x = -1$. Do đó đáp án đúng là A.",
                "status": "approved",
                "is_current": True,
            },
            {
                "id": "11111111-0000-0000-0000-000000000102",
                "version_id": v1_id,
                "source_question_id": s2_id,
                "question_no": 2,
                "canonical_question_no": 2,
                "content": "Tính tích phân $I = \\int_{0}^{1} (3x^2 + 2x) dx$.",
                "options": ["$I = 1$", "$I = 3$", "$I = 2$", "$I = 4$"],
                "correct_key": "C",
                "solution_md": "Ta có nguyên hàm $F(x) = x^3 + x^2$. Khi đó $I = F(1) - F(0) = (1 + 1) - 0 = 2$. Do đó đáp án đúng là C.",
                "canonical_options": ["$I = 1$", "$I = 3$", "$I = 2$", "$I = 4$"],
                "canonical_correct_key": "C",
                "canonical_solution_md": "Ta có nguyên hàm $F(x) = x^3 + x^2$. Khi đó $I = F(1) - F(0) = (1 + 1) - 0 = 2$. Do đó đáp án đúng là C.",
                "status": "approved",
                "is_current": True,
            },
            {
                "id": "11111111-0000-0000-0000-000000000103",
                "version_id": v1_id,
                "source_question_id": s3_id,
                "question_no": 3,
                "canonical_question_no": 3,
                "content": "Trong không gian $Oxyz$, cho mặt cầu $(S): (x-1)^2 + (y+2)^2 + z^2 = 9$. Bán kính của mặt cầu $(S)$ là:",
                "options": ["$R = 9$", "$R = 81$", "$R = \\sqrt{3}$", "$R = 3$"],
                "correct_key": "D",
                "solution_md": "Phương trình mặt cầu có dạng $(x-a)^2 + (y-b)^2 + (z-c)^2 = R^2$. Suy ra $R^2 = 9 \\implies R = 3$. Do đó đáp án đúng là D.",
                "canonical_options": ["$R = 9$", "$R = 81$", "$R = \\sqrt{3}$", "$R = 3$"],
                "canonical_correct_key": "D",
                "canonical_solution_md": "Phương trình mặt cầu có dạng $(x-a)^2 + (y-b)^2 + (z-c)^2 = R^2$. Suy ra $R^2 = 9 \\implies R = 3$. Do đó đáp án đúng là D.",
                "status": "approved",
                "is_current": True,
            },
            # Version 102 questions
            {
                "id": "22222222-0000-0000-0000-000000000101",
                "version_id": v2_id,
                "source_question_id": s1_id,
                "question_no": 1,
                "canonical_question_no": 1,
                "content": "Cho hàm số $y = x^3 - 3x + 2$. Điểm cực đại của hàm số đã cho là:",
                "options": ["$x = -1$", "$x = 1$", "$x = 2$", "$x = 0$"],
                "correct_key": "A",
                "solution_md": "Đạo hàm $y' = 3x^2 - 3 = 0 \\iff x = \\pm 1$. Vì $y''(-1) = -6 < 0$ nên điểm cực đại là $x = -1$. Do đó đáp án đúng là A.",
                "canonical_options": ["$x = -1$", "$x = 1$", "$x = 2$", "$x = 0$"],
                "canonical_correct_key": "A",
                "canonical_solution_md": "Đạo hàm $y' = 3x^2 - 3 = 0 \\iff x = \\pm 1$. Vì $y''(-1) = -6 < 0$ nên điểm cực đại là $x = -1$. Do đó đáp án đúng là A.",
                "status": "approved",
                "is_current": True,
            },
            {
                "id": "22222222-0000-0000-0000-000000000102",
                "version_id": v2_id,
                "source_question_id": s2_id,
                "question_no": 2,
                "canonical_question_no": 2,
                "content": "Tính tích phân $I = \\int_{0}^{1} (3x^2 + 2x) dx$.",
                "options": ["$I = 1$", "$I = 3$", "$I = 2$", "$I = 4$"],
                "correct_key": "C",
                "solution_md": "Ta có nguyên hàm $F(x) = x^3 + x^2$. Khi đó $I = F(1) - F(0) = (1 + 1) - 0 = 2$. Do đó đáp án đúng là C.",
                "canonical_options": ["$I = 1$", "$I = 3$", "$I = 2$", "$I = 4$"],
                "canonical_correct_key": "C",
                "canonical_solution_md": "Ta có nguyên hàm $F(x) = x^3 + x^2$. Khi đó $I = F(1) - F(0) = (1 + 1) - 0 = 2$. Do đó đáp án đúng là C.",
                "status": "approved",
                "is_current": True,
            },
            {
                "id": "22222222-0000-0000-0000-000000000103",
                "version_id": v2_id,
                "source_question_id": s3_id,
                "question_no": 3,
                "canonical_question_no": 3,
                "content": "Trong không gian $Oxyz$, cho mặt cầu $(S): (x-1)^2 + (y+2)^2 + z^2 = 9$. Bán kính của mặt cầu $(S)$ là:",
                "options": ["$R = 9$", "$R = 81$", "$R = \\sqrt{3}$", "$R = 3$"],
                "correct_key": "D",
                "solution_md": "Phương trình mặt cầu có dạng $(x-a)^2 + (y-b)^2 + (z-c)^2 = R^2$. Suy ra $R^2 = 9 \\implies R = 3$. Do đó đáp án đúng là D.",
                "canonical_options": ["$R = 9$", "$R = 81$", "$R = \\sqrt{3}$", "$R = 3$"],
                "canonical_correct_key": "D",
                "canonical_solution_md": "Phương trình mặt cầu có dạng $(x-a)^2 + (y-b)^2 + (z-c)^2 = R^2$. Suy ra $R^2 = 9 \\implies R = 3$. Do đó đáp án đúng là D.",
                "status": "approved",
                "is_current": True,
            },
        ],
        "answer_keys": [
            {"version_id": v1_id, "question_no": 1, "correct_option": "A", "display_no": 1, "display_correct_key": "A", "canonical_question_no": 1},
            {"version_id": v1_id, "question_no": 2, "correct_option": "C", "display_no": 2, "display_correct_key": "C", "canonical_question_no": 2},
            {"version_id": v1_id, "question_no": 3, "correct_option": "D", "display_no": 3, "display_correct_key": "D", "canonical_question_no": 3},
            {"version_id": v2_id, "question_no": 1, "correct_option": "A", "display_no": 1, "display_correct_key": "A", "canonical_question_no": 1},
            {"version_id": v2_id, "question_no": 2, "correct_option": "C", "display_no": 2, "display_correct_key": "C", "canonical_question_no": 2},
            {"version_id": v2_id, "question_no": 3, "correct_option": "D", "display_no": 3, "display_correct_key": "D", "canonical_question_no": 3},
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


# ==============================================================================
# 3. Exporter Invariants & Integrity Negative Tests (P1-1, P1-2, P1-3)
# ==============================================================================


@pytest.mark.asyncio
async def test_preview_rejects_empty_content():
    """Fails closed with 409 when question content is empty or whitespace only."""
    db_state = _build_valid_preview_db_state()
    db_state["version_questions"][0]["content"] = "   "
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "bị rỗng" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_empty_solution():
    """Fails closed with 409 when solution_md is empty or whitespace only."""
    db_state = _build_valid_preview_db_state()
    db_state["version_questions"][0]["solution_md"] = ""
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "Lời giải" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_duplicate_normalized_options():
    """Fails closed with 409 when options contain duplicates after normalization."""
    db_state = _build_valid_preview_db_state()
    # Add duplicate option after normalized_text: '$x = 1$' and '$x =  1$'
    db_state["version_questions"][0]["options"] = ["$x = -1$", "$x = 1$", "$x =  1$", "$x = 0$"]
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "trùng lặp sau chuẩn hóa" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_unapproved_question():
    """Fails closed with 409 when a current question has status other than 'approved'."""
    db_state = _build_valid_preview_db_state()
    db_state["version_questions"][0]["status"] = "pending_review"
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "chưa được thẩm định phê duyệt" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_missing_permutation_metadata():
    """Fails closed with 409 when exam_versions.permutations is missing required keys."""
    db_state = _build_valid_preview_db_state()
    db_state["exam_versions"][0]["permutations"] = {"question_order": [1, 2, 3]}  # missing display_to_canonical
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "thiếu trường" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_invalid_canonical_mapping():
    """Fails closed with 409 without falling back to question_no when canonical_question_no is invalid."""
    db_state = _build_valid_preview_db_state()
    db_state["version_questions"][0]["canonical_question_no"] = 99  # Invalid canonical number
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "canonical_question_no" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_asymmetric_permutation_mapping():
    """Fails closed with 409 when permutations display_to_canonical and canonical_to_display are not inverse bijections."""
    db_state = _build_valid_preview_db_state()
    # Change permutations canonical_to_display without updating display_to_canonical
    db_state["exam_versions"][0]["permutations"]["canonical_to_display"]["1"] = 2
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "Ánh xạ hai chiều hoán vị không đối xứng" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_mismatched_permutation_mapping():
    """Fails closed with 409 when version_question mapping does not match permutations dict."""
    db_state = _build_valid_preview_db_state()
    # Permutations validly swaps 1 and 2, but version_questions retains canonical_question_no = 1 for Q1
    db_state["exam_versions"][0]["permutations"]["question_order"] = [2, 1, 3]
    db_state["exam_versions"][0]["permutations"]["canonical_to_display"] = {"1": 2, "2": 1, "3": 3}
    db_state["exam_versions"][0]["permutations"]["display_to_canonical"] = {"1": 2, "2": 1, "3": 3}
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "không khớp giữa version_questions và permutations" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_duplicate_answer_keys():
    """Fails closed with 409 when answer_keys contains duplicate entries for same (version_id, question_no)."""
    db_state = _build_valid_preview_db_state()
    v1_id = db_state["exam_versions"][0]["id"]
    # Append duplicate key row for v1 question 1
    db_state["answer_keys"].append(
        {"version_id": v1_id, "question_no": 1, "correct_option": "A", "display_no": 1, "display_correct_key": "A", "canonical_question_no": 1}
    )
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "trùng lặp hoặc thừa" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_mismatched_canonical_no_in_answer_keys():
    """Fails closed with 409 when answer_keys.canonical_question_no does not match version_questions."""
    db_state = _build_valid_preview_db_state()
    db_state["answer_keys"][0]["canonical_question_no"] = 2  # question 1 is canonical 1
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "Thứ tự câu hỏi gốc trong bảng tra không khớp" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_too_many_questions():
    """Fails closed with 409 when source question count exceeds upper bound of 20."""
    db_state = _build_valid_preview_db_state()
    # Add 21 sources
    db_state["source_questions"] = [{"id": str(uuid4()), "session_id": MOCK_SESSION_ID, "question_no": i} for i in range(1, 22)]
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "không nằm trong giới hạn cho phép" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_empty_shuffle_seed():
    """Fails closed with 409 when exam_versions.shuffle_seed is empty or whitespace."""
    db_state = _build_valid_preview_db_state()
    db_state["exam_versions"][0]["shuffle_seed"] = "   "
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "shuffle_seed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_empty_option_permutations():
    """Fails closed with 409 when option_permutations is empty dict or missing questions."""
    db_state = _build_valid_preview_db_state()
    db_state["exam_versions"][0]["permutations"]["option_permutations"] = {}
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "option_permutations" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_swapped_source_question_id():
    """Fails closed with 409 when source_question_id does not match canonical_question_no."""
    db_state = _build_valid_preview_db_state()
    # Swap source_question_id of question 1 and question 2 in version 101
    s1_id = db_state["source_questions"][0]["id"]
    s2_id = db_state["source_questions"][1]["id"]
    db_state["version_questions"][0]["source_question_id"] = s2_id
    db_state["version_questions"][1]["source_question_id"] = s1_id
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "source_question_id" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_missing_source_question_coverage():
    """Fails closed with 409 when a version does not have 1:1 coverage of all source questions."""
    db_state = _build_valid_preview_db_state()
    # Replace version 101 question 2 source_question_id with source 1
    s1_id = db_state["source_questions"][0]["id"]
    db_state["version_questions"][1]["source_question_id"] = s1_id
    db_state["version_questions"][1]["canonical_question_no"] = 1
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"


@pytest.mark.asyncio
async def test_preview_rejects_displayed_options_mismatching_canonical():
    """Fails closed with 409 when displayed options diverge from canonical_options under perm_map (Duy counterexample)."""
    db_state = _build_valid_preview_db_state()
    # Swap displayed options A and B while leaving identity permutation map and answer_keys untouched
    orig_options = list(db_state["version_questions"][0]["options"])
    db_state["version_questions"][0]["options"] = [orig_options[1], orig_options[0], orig_options[2], orig_options[3]]
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "không khớp phương án gốc" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_display_key_mismatching_perm_map():
    """Fails closed with 409 when correct_key does not equal perm_map[canonical_correct_key]."""
    db_state = _build_valid_preview_db_state()
    # Invert perm_map for Q1 to map A -> B, but leave correct_key as A
    db_state["exam_versions"][0]["permutations"]["option_permutations"]["1"] = {
        "A": "B", "B": "A", "C": "C", "D": "D"
    }
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "không khớp bảng hoán vị" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_rejects_desynchronized_solution():
    """Fails closed with 409 when solution_md diverges from synced canonical_solution_md."""
    db_state = _build_valid_preview_db_state()
    # Tamper with solution_md so it does not match sync_solution_text
    db_state["version_questions"][0]["solution_md"] = "Lời giải bị sửa sai khác gốc"
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"
    assert "không khớp lời giải sau đồng bộ" in exc_info.value.detail


# ==============================================================================
# 4. Golden Fixture & Success Tests (P1-4, F03)
# ==============================================================================


def test_preview_golden_off_off_fixture_validation():
    """Validates the official 3-question x 2-version Golden OFF/OFF fixture."""
    fixture_path = os.path.join(
        os.path.dirname(__file__), "../fixtures/w4_preview_snapshot_fixture.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    resp = PreviewSnapshotResponse.model_validate(data)
    assert resp.session_id == MOCK_SESSION_ID
    assert resp.status == "reviewed"
    assert resp.is_finalized is True
    assert resp.n_versions == 2
    assert resp.total_questions == 3
    assert len(resp.versions) == 2

    # Verify all 6 display slots in OFF/OFF
    for v in resp.versions:
        assert len(v.questions) == 3
        assert [q.question_no for q in v.questions] == [1, 2, 3]
        assert [q.canonical_question_no for q in v.questions] == [1, 2, 3]
        assert v.questions[0].correct_key == "A"
        assert v.questions[1].correct_key == "C"
        assert v.questions[2].correct_key == "D"
        assert v.answer_keys == {"1": "A", "2": "C", "3": "D"}

    # Verify cross-version matrix
    assert len(resp.matrix) == 3
    assert resp.matrix[0].answers == {"101": "A", "102": "A"}
    assert resp.matrix[1].answers == {"101": "C", "102": "C"}
    assert resp.matrix[2].answers == {"101": "D", "102": "D"}


@pytest.mark.asyncio
async def test_preview_success_golden_off_off_from_repository():
    """Verify repository fetch on the 3-question x 2-version Golden OFF/OFF state."""
    db_state = _build_valid_preview_db_state()
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    res = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert isinstance(res, PreviewSnapshotResponse)
    assert res.total_questions == 3
    assert len(res.versions) == 2
    assert res.versions[0].questions[0].canonical_question_no == 1
    assert res.versions[0].questions[1].canonical_question_no == 2
    assert res.versions[0].questions[2].canonical_question_no == 3


@pytest.mark.asyncio
async def test_preview_on_on_shuffled_case():
    """Verify preview when both question shuffling and option shuffling are ON."""
    v1_id = "10100000-0000-0000-0000-000000000101"
    v2_id = "10200000-0000-0000-0000-000000000102"
    s1_id = "00000000-0000-0000-0000-000000000001"
    s2_id = "00000000-0000-0000-0000-000000000002"

    on_on_permutations = {
        "question_order": [2, 1],
        "display_to_canonical": {"1": 2, "2": 1},
        "canonical_to_display": {"2": 1, "1": 2},
        "option_permutations": {
            "1": {"A": "B", "B": "C", "C": "D", "D": "A"},
            "2": {"A": "A", "B": "B", "C": "C", "D": "D"},
        },
    }

    db_state = {
        "exam_sessions": [
            {
                "id": MOCK_SESSION_ID,
                "user_id": MOCK_USER_ID,
                "title": "Đề thi ON/ON",
                "status": "reviewed",
                "is_finalized": True,
                "updated_at": "2026-11-06T12:00:00Z",
            }
        ],
        "generation_configs": [{"session_id": MOCK_SESSION_ID, "n_versions": 2}],
        "exam_versions": [
            {"id": v1_id, "session_id": MOCK_SESSION_ID, "version_code": "101", "is_finalized": True, "shuffle_seed": "on-on-seed-101", "permutations": on_on_permutations},
            {"id": v2_id, "session_id": MOCK_SESSION_ID, "version_code": "102", "is_finalized": True, "shuffle_seed": "on-on-seed-102", "permutations": on_on_permutations},
        ],
        "source_questions": [
            {"id": s1_id, "session_id": MOCK_SESSION_ID, "question_no": 1},
            {"id": s2_id, "session_id": MOCK_SESSION_ID, "question_no": 2},
        ],
        "version_questions": [
            # v1: Q1 is canonical 2, Q2 is canonical 1
            {
                "id": str(uuid4()), "version_id": v1_id, "source_question_id": s2_id, "question_no": 1,
                "canonical_question_no": 2, "content": "Tích phân",
                "options": ["Tích phân D", "Tích phân A", "Tích phân B", "Tích phân C"],
                "correct_key": "B", "solution_md": "Đáp án đúng là B",
                "canonical_options": ["Tích phân A", "Tích phân B", "Tích phân C", "Tích phân D"],
                "canonical_correct_key": "A", "canonical_solution_md": "Đáp án đúng là A",
                "status": "approved", "is_current": True,
            },
            {
                "id": str(uuid4()), "version_id": v1_id, "source_question_id": s1_id, "question_no": 2,
                "canonical_question_no": 1, "content": "Đạo hàm",
                "options": ["Đạo hàm W", "Đạo hàm X", "Đạo hàm Y", "Đạo hàm Z"],
                "correct_key": "A", "solution_md": "Đáp án đúng là A",
                "canonical_options": ["Đạo hàm W", "Đạo hàm X", "Đạo hàm Y", "Đạo hàm Z"],
                "canonical_correct_key": "A", "canonical_solution_md": "Đáp án đúng là A",
                "status": "approved", "is_current": True,
            },
            # v2: Q1 is canonical 2, Q2 is canonical 1
            {
                "id": str(uuid4()), "version_id": v2_id, "source_question_id": s2_id, "question_no": 1,
                "canonical_question_no": 2, "content": "Tích phân",
                "options": ["Tích phân D", "Tích phân A", "Tích phân B", "Tích phân C"],
                "correct_key": "B", "solution_md": "Đáp án đúng là B",
                "canonical_options": ["Tích phân A", "Tích phân B", "Tích phân C", "Tích phân D"],
                "canonical_correct_key": "A", "canonical_solution_md": "Đáp án đúng là A",
                "status": "approved", "is_current": True,
            },
            {
                "id": str(uuid4()), "version_id": v2_id, "source_question_id": s1_id, "question_no": 2,
                "canonical_question_no": 1, "content": "Đạo hàm",
                "options": ["Đạo hàm W", "Đạo hàm X", "Đạo hàm Y", "Đạo hàm Z"],
                "correct_key": "A", "solution_md": "Đáp án đúng là A",
                "canonical_options": ["Đạo hàm W", "Đạo hàm X", "Đạo hàm Y", "Đạo hàm Z"],
                "canonical_correct_key": "A", "canonical_solution_md": "Đáp án đúng là A",
                "status": "approved", "is_current": True,
            },
        ],
        "answer_keys": [
            {"version_id": v1_id, "question_no": 1, "correct_option": "B", "display_no": 1, "display_correct_key": "B", "canonical_question_no": 2},
            {"version_id": v1_id, "question_no": 2, "correct_option": "A", "display_no": 2, "display_correct_key": "A", "canonical_question_no": 1},
            {"version_id": v2_id, "question_no": 1, "correct_option": "B", "display_no": 1, "display_correct_key": "B", "canonical_question_no": 2},
            {"version_id": v2_id, "question_no": 2, "correct_option": "A", "display_no": 2, "display_correct_key": "A", "canonical_question_no": 1},
        ],
    }

    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    res = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    assert res.total_questions == 2
    assert res.versions[0].questions[0].canonical_question_no == 2
    assert res.versions[0].questions[0].correct_key == "B"
    assert res.versions[0].questions[1].canonical_question_no == 1
    assert res.versions[0].questions[1].correct_key == "A"


@pytest.mark.asyncio
async def test_preview_repeat_get_deterministic():
    """Repeated calls to get_preview_snapshot produce identical results with zero mutations."""
    db_state = _build_valid_preview_db_state()
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    res1 = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)
    res2 = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)

    assert res1.model_dump() == res2.model_dump()
    assert len(client.call_log) == 0


@pytest.mark.asyncio
async def test_preview_export_snapshot_mapping_with_real_session_metadata():
    """Proves W4-MVP-07 consumer can construct ApprovedExportSnapshot using actual session metadata."""
    db_state = _build_valid_preview_db_state()
    client = MockSupabaseClient(db_state)
    service = FinalizeService(client)

    # 1. Fetch preview response
    res = await service.get_preview_snapshot(MOCK_SESSION_ID, MOCK_USER_ID)

    # 2. Fetch actual session record (source of title and revision)
    repo = FinalizeRepository(client)
    session_row = await repo.get_session_meta(MOCK_SESSION_ID)
    assert session_row is not None

    actual_title = session_row.get("title") or "Đề thi thử THPT"
    actual_revision = session_row["updated_at"]

    # 3. Construct ApprovedExportSnapshot
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
        revision=actual_revision,
        title=actual_title,
        status="approved",
        versions=tuple(export_versions),
    )

    assert export_snapshot.title == "Đề thi thử THPT Quốc Gia môn Toán 2026"
    assert export_snapshot.revision == "2026-11-06T10:00:00Z"
    assert len(export_snapshot.versions) == 2
    assert export_snapshot.versions[0].code == "101"
    assert export_snapshot.versions[0].questions[0].correct_key == "A"


# ==============================================================================
# 5. HTTP Router Integration Test
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
            assert len(data["matrix"]) == 3
            assert data["matrix"][0]["answers"] == {"101": "A", "102": "A"}
    finally:
        app.dependency_overrides.clear()

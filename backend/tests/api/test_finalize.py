"""API Endpoint Tests for Finalize & Content Lock (TASK-305).

Tests:
1. Authentication & Ownership:
   - 401 unauthenticated
   - 403 / 404 via assert_ownership
2. POST /api/sessions/{session_id}/finalize/approve:
   - Happy path: 200 OK with approved_at, status='approved'
   - Idempotency: calling twice returns 200 OK with identical approved_at
   - Pre-condition failure: unapproved questions -> 400 ERR_NOT_ALL_QUESTIONS_APPROVED
   - Pre-condition failure: regenerating questions -> 409 ERR_QUESTION_REGENERATING
   - Pre-condition failure: unfinalized versions -> 400 ERR_VERSIONS_NOT_FINALIZED
   - Pre-condition failure: invalid session state -> 409 ERR_INVALID_SESSION_STATE
3. Content Lock (HTTP 423):
   - Review operations (/accept, /reject, /revert) return 423 ERR_SESSION_LOCKED
4. GET /api/sessions/{session_id}/finalize/matrix:
   - Reads matrix from answer_keys (correct_option)
   - Fallback to version_questions (correct_key) when answer_keys is empty
   - Proper sort order by question_no and version_codes
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_user_db
from app.main import app
from app.models.schemas import (
    AnswersMatrixResponse,
    CurrentUser,
    FinalizeApproveResponse,
    MatrixItem,
    ReviewDomainException,
)
from app.services.finalize.repository import FinalizeRepository
from app.services.finalize.service import FinalizeService
from app.services.review.repository import ReviewRepository
from app.services.review.service import ReviewService
from tests.services.test_review_lifecycle import MockSupabaseClient

MOCK_SESSION_ID = "00000000-0000-0000-0000-000000000001"
MOCK_QUESTION_ID = "11111111-1111-1111-1111-111111111111"
MOCK_USER_ID = "user-123456"


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


# ==============================================================================
# 1. Authentication & Ownership Guard Tests
# ==============================================================================


def test_finalize_endpoints_unauthenticated(client: TestClient):
    """Calling any finalize endpoint without Authorization header returns 401."""
    app.dependency_overrides.clear()

    res_approve = client.post(f"/api/sessions/{MOCK_SESSION_ID}/finalize/approve")
    assert res_approve.status_code == 401

    res_matrix = client.get(f"/api/sessions/{MOCK_SESSION_ID}/finalize/matrix")
    assert res_matrix.status_code == 401


def test_finalize_ownership_denied(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """assert_ownership raising 403 or 404 is properly propagated."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with patch(
            "app.api.routes.finalize.assert_ownership",
            side_effect=HTTPException(status_code=403, detail="Forbidden resource"),
        ):
            res = client.post(
                f"/api/sessions/{MOCK_SESSION_ID}/finalize/approve",
                headers=auth_headers,
            )
            assert res.status_code == 403
            assert res.json()["detail"] == "Forbidden resource"
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. Finalize Approve Tests (Happy path, Idempotency, Preconditions)
# ==============================================================================


def test_approve_session_happy_path(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """Approve succeeds when all 4 conditions are met, returns 200 FinalizeApproveResponse."""
    expected_resp = FinalizeApproveResponse(
        session_id=MOCK_SESSION_ID,
        status="approved",
        approved_at="2026-10-30T01:00:00Z",
        message="Phê duyệt phiên thi thành công và đã khóa nội dung",
    )

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.finalize.assert_ownership", return_value=None),
            patch.object(
                FinalizeService,
                "approve_session",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.post(
                f"/api/sessions/{MOCK_SESSION_ID}/finalize/approve",
                headers=auth_headers,
            )
            assert res.status_code == 200
            data = res.json()
            assert data["session_id"] == MOCK_SESSION_ID
            assert data["status"] == "approved"
            assert data["approved_at"] == "2026-10-30T01:00:00Z"
    finally:
        app.dependency_overrides.clear()


def test_approve_session_idempotent(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """Calling approve a second time returns 200 with identical approved_at."""
    initial_timestamp = "2026-10-30T01:00:00Z"
    idempotent_resp = FinalizeApproveResponse(
        session_id=MOCK_SESSION_ID,
        status="approved",
        approved_at=initial_timestamp,
        message="Phiên đề đã được phê duyệt trước đó",
    )

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.finalize.assert_ownership", return_value=None),
            patch.object(
                FinalizeService,
                "approve_session",
                new_callable=AsyncMock,
                return_value=idempotent_resp,
            ),
        ):
            res = client.post(
                f"/api/sessions/{MOCK_SESSION_ID}/finalize/approve",
                headers=auth_headers,
            )
            assert res.status_code == 200
            data = res.json()
            assert data["approved_at"] == initial_timestamp
            assert data["message"] == "Phiên đề đã được phê duyệt trước đó"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "error_code,status_code,detail",
    [
        ("ERR_NOT_ALL_QUESTIONS_APPROVED", 400, "Còn 2 câu hỏi chưa được duyệt"),
        ("ERR_QUESTION_REGENERATING", 409, "Còn 1 câu hỏi đang sinh lại"),
        ("ERR_VERSIONS_NOT_FINALIZED", 400, "Còn 1 phiên bản đề thi chưa hoán vị"),
        ("ERR_INVALID_SESSION_STATE", 409, "Phiên đề ở trạng thái 'draft' không thể phê duyệt"),
    ],
)
def test_approve_session_precondition_failures(
    client: TestClient,
    mock_current_user: CurrentUser,
    auth_headers: dict,
    error_code: str,
    status_code: int,
    detail: str,
):
    """Pre-condition failures raise ReviewDomainException mapped to corresponding HTTP errors."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.finalize.assert_ownership", return_value=None),
            patch.object(
                FinalizeService,
                "approve_session",
                new_callable=AsyncMock,
                side_effect=ReviewDomainException(status_code, error_code, detail),
            ),
        ):
            res = client.post(
                f"/api/sessions/{MOCK_SESSION_ID}/finalize/approve",
                headers=auth_headers,
            )
            assert res.status_code == status_code
            data = res.json()
            assert data["error_code"] == error_code
            assert data["detail"] == detail
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 3. Content Lock Tests (HTTP 423 on mutations once session is approved)
# ==============================================================================


@pytest.mark.asyncio
async def test_review_service_guards_raise_423_when_approved():
    """ReviewService.check_session_guards raises 423 ERR_SESSION_LOCKED when status is approved."""
    mock_db = MagicMock()
    service = ReviewService(mock_db)

    # Mock repository returning status 'approved'
    service.repo.get_session_status_and_quota = AsyncMock(
        return_value={"id": MOCK_SESSION_ID, "status": "approved"}
    )

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.check_session_guards(MOCK_SESSION_ID)

    assert exc_info.value.status_code == 423
    assert exc_info.value.error_code == "ERR_SESSION_LOCKED"


@pytest.mark.asyncio
async def test_review_service_guards_raise_423_when_exported():
    """ReviewService.check_session_guards raises 423 ERR_SESSION_LOCKED when status is exported."""
    mock_db = MagicMock()
    service = ReviewService(mock_db)

    service.repo.get_session_status_and_quota = AsyncMock(
        return_value={"id": MOCK_SESSION_ID, "status": "exported"}
    )

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.check_session_guards(MOCK_SESSION_ID)

    assert exc_info.value.status_code == 423
    assert exc_info.value.error_code == "ERR_SESSION_LOCKED"


# ==============================================================================
# 4. Answers Matrix Tests (Happy path & Fallback)
# ==============================================================================


def test_get_answers_matrix_success(
    client: TestClient, mock_current_user: CurrentUser, auth_headers: dict
):
    """GET /finalize/matrix returns 200 AnswersMatrixResponse with sorted questions."""
    expected_resp = AnswersMatrixResponse(
        session_id=MOCK_SESSION_ID,
        total_questions=2,
        version_codes=["101", "102"],
        matrix=[
            MatrixItem(question_no=1, answers={"101": "A", "102": "B"}),
            MatrixItem(question_no=2, answers={"101": "C", "102": "D"}),
        ],
    )

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_user_db] = lambda: MagicMock()

    try:
        with (
            patch("app.api.routes.finalize.assert_ownership", return_value=None),
            patch.object(
                FinalizeService,
                "get_answers_matrix",
                new_callable=AsyncMock,
                return_value=expected_resp,
            ),
        ):
            res = client.get(
                f"/api/sessions/{MOCK_SESSION_ID}/finalize/matrix",
                headers=auth_headers,
            )
            assert res.status_code == 200
            data = res.json()
            assert data["session_id"] == MOCK_SESSION_ID
            assert data["total_questions"] == 2
            assert data["version_codes"] == ["101", "102"]
            assert len(data["matrix"]) == 2
            assert data["matrix"][0]["question_no"] == 1
            assert data["matrix"][0]["answers"]["101"] == "A"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_finalize_service_matrix_fallback_logic():
    """FinalizeService.get_answers_matrix builds matrix properly from repository fetch_matrix_raw."""
    mock_db = MagicMock()
    mock_repo = MagicMock()
    mock_repo.get_session_meta = AsyncMock(
        return_value={"id": MOCK_SESSION_ID, "status": "approved"}
    )
    # Simulate repository fallback data
    mock_repo.fetch_matrix_raw = AsyncMock(
        return_value=(
            ["101", "102"],
            [
                {"question_no": 2, "version_code": "101", "answer": "B"},
                {"question_no": 1, "version_code": "101", "answer": "A"},
                {"question_no": 2, "version_code": "102", "answer": "D"},
                {"question_no": 1, "version_code": "102", "answer": "C"},
            ],
        )
    )

    service = FinalizeService(mock_db, repo=mock_repo)
    result = await service.get_answers_matrix(MOCK_SESSION_ID, MOCK_USER_ID)

    assert result.total_questions == 2
    assert result.version_codes == ["101", "102"]
    # Ensure sorted by question_no
    assert result.matrix[0].question_no == 1
    assert result.matrix[0].answers == {"101": "A", "102": "C"}
    assert result.matrix[1].question_no == 2
    assert result.matrix[1].answers == {"101": "B", "102": "D"}


# ==============================================================================
# 5. Service Pre-condition Business Logic Unit Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_finalize_service_happy_path_unit():
    """Unit test for FinalizeService.approve_session happy path."""
    mock_db = MagicMock()
    mock_repo = MagicMock()
    mock_repo.get_session_meta = AsyncMock(
        return_value={"id": MOCK_SESSION_ID, "status": "reviewed"}
    )
    mock_repo.check_preconditions = AsyncMock(
        return_value={
            "total_versions": 4,
            "unfinalized_versions_count": 0,
            "total_questions": 40,
            "unapproved_count": 0,
            "regenerating_count": 0,
        }
    )
    mock_repo.update_session_approved = AsyncMock(
        return_value={
            "id": MOCK_SESSION_ID,
            "status": "approved",
            "approved_at": "2026-10-30T01:30:00Z",
        }
    )

    service = FinalizeService(mock_db, repo=mock_repo)
    res = await service.approve_session(MOCK_SESSION_ID, MOCK_USER_ID)

    assert res.status == "approved"
    assert res.approved_at == "2026-10-30T01:30:00Z"
    mock_repo.update_session_approved.assert_called_once_with(
        MOCK_SESSION_ID, expected_updated_at=None, allowed_statuses=["reviewed"]
    )


# ==============================================================================
# 6. Reviewer Findings Regression Tests (F01, F02, F03)
# ==============================================================================


@pytest.mark.asyncio
async def test_f01_interleaving_mutation_prevents_approval():
    """F01: When another worker mutates session state before update, approve_session fails."""
    initial_updated_at = "2026-10-30T00:00:00+00:00"
    db_state = {
        "exam_sessions": [
            {
                "id": MOCK_SESSION_ID,
                "status": "reviewed",
                "updated_at": initial_updated_at,
                "user_id": MOCK_USER_ID,
            }
        ],
        "exam_versions": [
            {"id": "v-101", "session_id": MOCK_SESSION_ID, "version_code": "101", "is_finalized": True}
        ],
        "source_questions": [
            {"id": "s-1", "session_id": MOCK_SESSION_ID}
        ],
        "version_questions": [
            {
                "id": "q-1",
                "version_id": "v-101",
                "source_question_id": "s-1",
                "status": "approved",
                "is_current": True,
            }
        ],
    }
    client = MockSupabaseClient(db_state)
    repo = FinalizeRepository(client)
    service = FinalizeService(client, repo=repo)

    # Interleaving hook: before update_session_approved executes, simulate another worker
    # rejecting a question, changing session status to 'generated' and updating updated_at
    original_update = repo.update_session_approved

    async def hooked_update(session_id, expected_updated_at=None, allowed_statuses=None):
        # Worker B mutates in the background
        db_state["exam_sessions"][0]["status"] = "generated"
        db_state["exam_sessions"][0]["updated_at"] = "2026-10-30T00:01:00+00:00"
        return await original_update(
            session_id, expected_updated_at=expected_updated_at, allowed_statuses=allowed_statuses
        )

    repo.update_session_approved = hooked_update

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.approve_session(MOCK_SESSION_ID, MOCK_USER_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INVALID_SESSION_STATE"
    # Session must NOT have been approved
    assert db_state["exam_sessions"][0]["status"] == "generated"


@pytest.mark.asyncio
async def test_f01_post_approval_mutations_blocked():
    """F01: Mutations on already approved session are blocked at DB level with HTTP 423."""
    db_state = {
        "exam_sessions": [
            {
                "id": MOCK_SESSION_ID,
                "status": "approved",
                "gemini_review_calls": 5,
                "user_id": MOCK_USER_ID,
            }
        ],
        "version_questions": [
            {
                "id": MOCK_QUESTION_ID,
                "version_id": "v-101",
                "source_question_id": "s-1",
                "status": "approved",
                "is_current": True,
                "is_reverted": False,
                "regenerated_from_id": "old-q",
            }
        ],
    }
    client = MockSupabaseClient(db_state)
    review_repo = ReviewRepository(client)

    # 1. Accept must be rejected
    with pytest.raises(ReviewDomainException) as exc_accept:
        await review_repo.accept_question_tx(MOCK_SESSION_ID, MOCK_QUESTION_ID, MOCK_USER_ID)
    assert exc_accept.value.status_code == 423
    assert exc_accept.value.error_code == "ERR_SESSION_LOCKED"

    # 2. Revert must be rejected
    with pytest.raises(ReviewDomainException) as exc_revert:
        await review_repo.atomic_revert_tx(MOCK_SESSION_ID, MOCK_QUESTION_ID, MOCK_USER_ID)
    assert exc_revert.value.status_code == 423
    assert exc_revert.value.error_code == "ERR_SESSION_LOCKED"

    # 3. Reserve quota / reject phase 1 must be rejected
    with pytest.raises(ReviewDomainException) as exc_reserve:
        await review_repo.reserve_max_quota_and_start_regenerating(MOCK_SESSION_ID, MOCK_QUESTION_ID, MOCK_USER_ID)
    assert exc_reserve.value.status_code == 423
    assert exc_reserve.value.error_code == "ERR_SESSION_LOCKED"


@pytest.mark.asyncio
async def test_f01_reverse_interleaving_approval_blocks_concurrent_reserve():
    """F01: When approval happens after worker reads session but before writing child question, reserve is aborted."""
    db_state = {
        "exam_sessions": [
            {
                "id": MOCK_SESSION_ID,
                "status": "reviewed",
                "gemini_review_calls": 2,
                "user_id": MOCK_USER_ID,
                "updated_at": "2026-10-30T00:00:00+00:00",
            }
        ],
        "exam_versions": [
            {"id": "v-101", "session_id": MOCK_SESSION_ID, "version_code": "101", "is_finalized": True}
        ],
        "source_questions": [
            {"id": "s-1", "session_id": MOCK_SESSION_ID}
        ],
        "version_questions": [
            {
                "id": MOCK_QUESTION_ID,
                "version_id": "v-101",
                "source_question_id": "s-1",
                "status": "approved",
                "is_current": True,
            }
        ],
    }
    client = MockSupabaseClient(db_state)
    review_repo = ReviewRepository(client)

    # Simulate Worker B starting reserve_max_quota_and_start_regenerating:
    # Hook into db.table("version_questions").select to simulate Worker A approving the session
    # after Worker B's initial read of session_meta but right when Worker B checks question state.
    original_table = client.table

    def hooked_table(name: str):
        builder = original_table(name)
        if name == "version_questions":
            orig_select = builder.select

            def hooked_select(*args, **kwargs):
                # Worker A approves session concurrently!
                db_state["exam_sessions"][0]["status"] = "approved"
                db_state["exam_sessions"][0]["approved_at"] = "2026-10-30T00:05:00+00:00"
                db_state["exam_sessions"][0]["updated_at"] = "2026-10-30T00:05:00+00:00"
                return orig_select(*args, **kwargs)

            builder.select = hooked_select
        return builder

    client.table = hooked_table

    # Worker B calls reserve: must be blocked with HTTP 423 ERR_SESSION_LOCKED
    with pytest.raises(ReviewDomainException) as exc_info:
        await review_repo.reserve_max_quota_and_start_regenerating(
            MOCK_SESSION_ID, MOCK_QUESTION_ID, MOCK_USER_ID
        )

    assert exc_info.value.status_code == 423
    assert exc_info.value.error_code == "ERR_SESSION_LOCKED"

    # Invariants verification:
    # 1. Question MUST remain 'approved' (never converted to 'regenerating')
    assert db_state["version_questions"][0]["status"] == "approved"
    # 2. Session quota must remain untouched (still 2)
    assert db_state["exam_sessions"][0]["gemini_review_calls"] == 2
    # 3. Session status remains 'approved'
    assert db_state["exam_sessions"][0]["status"] == "approved"


@pytest.mark.asyncio
async def test_f02_missing_current_question_for_a_version_aborts_approval():
    """F02: Reject approval when a version is missing an active approved variant for a source question."""
    db_state = {
        "exam_sessions": [
            {"id": MOCK_SESSION_ID, "status": "reviewed", "user_id": MOCK_USER_ID}
        ],
        "exam_versions": [
            {"id": "v-101", "session_id": MOCK_SESSION_ID, "version_code": "101", "is_finalized": True},
            {"id": "v-102", "session_id": MOCK_SESSION_ID, "version_code": "102", "is_finalized": True},
        ],
        "source_questions": [
            {"id": "s-1", "session_id": MOCK_SESSION_ID}
        ],
        "version_questions": [
            # Version 101 has current approved question for s-1
            {
                "id": "q-101",
                "version_id": "v-101",
                "source_question_id": "s-1",
                "status": "approved",
                "is_current": True,
            },
            # Version 102 only has historical is_current=False row, no active replacement
            {
                "id": "q-102-old",
                "version_id": "v-102",
                "source_question_id": "s-1",
                "status": "approved",
                "is_current": False,
            },
        ],
    }
    client = MockSupabaseClient(db_state)
    repo = FinalizeRepository(client)
    service = FinalizeService(client, repo=repo)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.approve_session(MOCK_SESSION_ID, MOCK_USER_ID)

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "ERR_NOT_ALL_QUESTIONS_APPROVED"
    assert "chưa được thẩm định phê duyệt hoặc bị thiếu" in exc_info.value.detail


@pytest.mark.asyncio
async def test_f03_partial_answer_keys_missing_version_raises_409():
    """F03: If answer_keys is partially populated (missing a version), raise 409."""
    db_state = {
        "exam_sessions": [
            {"id": MOCK_SESSION_ID, "status": "approved", "user_id": MOCK_USER_ID}
        ],
        "exam_versions": [
            {"id": "v-101", "session_id": MOCK_SESSION_ID, "version_code": "101"},
            {"id": "v-102", "session_id": MOCK_SESSION_ID, "version_code": "102"},
        ],
        "source_questions": [
            {"id": "s-1", "session_id": MOCK_SESSION_ID}
        ],
        "answer_keys": [
            # Only version 101 has an answer key record; version 102 is missing!
            {"version_id": "v-101", "question_no": 1, "correct_option": "B"}
        ],
    }
    client = MockSupabaseClient(db_state)
    repo = FinalizeRepository(client)
    service = FinalizeService(client, repo=repo)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_answers_matrix(MOCK_SESSION_ID, MOCK_USER_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"


@pytest.mark.asyncio
async def test_f03_partial_answer_keys_missing_question_raises_409():
    """F03: If answer_keys is missing a question for one version, raise 409."""
    db_state = {
        "exam_sessions": [
            {"id": MOCK_SESSION_ID, "status": "approved", "user_id": MOCK_USER_ID}
        ],
        "exam_versions": [
            {"id": "v-101", "session_id": MOCK_SESSION_ID, "version_code": "101"},
            {"id": "v-102", "session_id": MOCK_SESSION_ID, "version_code": "102"},
        ],
        "source_questions": [
            {"id": "s-1", "session_id": MOCK_SESSION_ID},
            {"id": "s-2", "session_id": MOCK_SESSION_ID},
        ],
        "answer_keys": [
            {"version_id": "v-101", "question_no": 1, "correct_option": "A"},
            {"version_id": "v-101", "question_no": 2, "correct_option": "B"},
            # Version 102 only has question 1, missing question 2!
            {"version_id": "v-102", "question_no": 1, "correct_option": "C"},
        ],
    }
    client = MockSupabaseClient(db_state)
    repo = FinalizeRepository(client)
    service = FinalizeService(client, repo=repo)

    with pytest.raises(ReviewDomainException) as exc_info:
        await service.get_answers_matrix(MOCK_SESSION_ID, MOCK_USER_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "ERR_INCONSISTENT_ANSWER_KEYS"


@pytest.mark.asyncio
async def test_f03_complete_answer_keys_success():
    """F03: When answer_keys is complete across all versions and questions, matrix returns normally."""
    db_state = {
        "exam_sessions": [
            {"id": MOCK_SESSION_ID, "status": "approved", "user_id": MOCK_USER_ID}
        ],
        "exam_versions": [
            {"id": "v-101", "session_id": MOCK_SESSION_ID, "version_code": "101"},
            {"id": "v-102", "session_id": MOCK_SESSION_ID, "version_code": "102"},
        ],
        "source_questions": [
            {"id": "s-1", "session_id": MOCK_SESSION_ID},
            {"id": "s-2", "session_id": MOCK_SESSION_ID},
        ],
        "answer_keys": [
            {"version_id": "v-101", "question_no": 1, "correct_option": "A"},
            {"version_id": "v-101", "question_no": 2, "correct_option": "B"},
            {"version_id": "v-102", "question_no": 1, "correct_option": "C"},
            {"version_id": "v-102", "question_no": 2, "correct_option": "D"},
        ],
    }
    client = MockSupabaseClient(db_state)
    repo = FinalizeRepository(client)
    service = FinalizeService(client, repo=repo)

    res = await service.get_answers_matrix(MOCK_SESSION_ID, MOCK_USER_ID)
    assert res.total_questions == 2
    assert res.version_codes == ["101", "102"]
    assert res.matrix[0].question_no == 1
    assert res.matrix[0].answers == {"101": "A", "102": "C"}
    assert res.matrix[1].question_no == 2
    assert res.matrix[1].answers == {"101": "B", "102": "D"}


@pytest.mark.asyncio
async def test_f03_empty_answer_keys_fallback_to_version_questions():
    """F03: When answer_keys is empty, safely fallback to version_questions."""
    db_state = {
        "exam_sessions": [
            {"id": MOCK_SESSION_ID, "status": "approved", "user_id": MOCK_USER_ID}
        ],
        "exam_versions": [
            {"id": "v-101", "session_id": MOCK_SESSION_ID, "version_code": "101"},
            {"id": "v-102", "session_id": MOCK_SESSION_ID, "version_code": "102"},
        ],
        "source_questions": [
            {"id": "s-1", "session_id": MOCK_SESSION_ID}
        ],
        "answer_keys": [],
        "version_questions": [
            {"version_id": "v-101", "question_no": 1, "correct_key": "A", "is_current": True},
            {"version_id": "v-102", "question_no": 1, "correct_key": "C", "is_current": True},
        ],
    }
    client = MockSupabaseClient(db_state)
    repo = FinalizeRepository(client)
    service = FinalizeService(client, repo=repo)

    res = await service.get_answers_matrix(MOCK_SESSION_ID, MOCK_USER_ID)
    assert res.total_questions == 1
    assert res.version_codes == ["101", "102"]
    assert res.matrix[0].answers == {"101": "A", "102": "C"}


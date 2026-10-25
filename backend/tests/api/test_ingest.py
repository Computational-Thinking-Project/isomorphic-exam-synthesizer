"""Unit tests for Exam Ingestion API Endpoints (TASK-202)."""

import io
from unittest.mock import MagicMock, patch

import docx
import pytest

MOCK_SESSION_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer mock-valid-jwt-token"}


@pytest.fixture
def mock_auth_user(mock_user_response):
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = mock_user_response
    return mock_supabase


def create_sample_docx_bytes() -> bytes:
    """Helper to generate a valid .docx exam file."""
    doc = docx.Document()
    doc.add_paragraph("Câu 1: Giải phương trình bậc hai $x^2 - 1 = 0$.")
    doc.add_paragraph("A. $x = \\pm 1$  B. $x = 1$  C. $x = -1$  D. $x = 0$")
    doc.add_paragraph("Câu 2: Đạo hàm của $y = 2x$ là:")
    doc.add_paragraph("A. $2$  B. $1$  C. $x$  D. $0$")
    doc.add_paragraph("BẢNG ĐÁP ÁN:")
    doc.add_paragraph("1.A 2.A")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Unauthenticated & Authorization Tests
# ---------------------------------------------------------------------------


def test_ingest_file_unauthenticated(client):
    """POST /api/sessions/{id}/ingest-file without token returns 401."""
    response = client.post(
        f"/api/sessions/{MOCK_SESSION_ID}/ingest-file",
        files={
            "file": (
                "test.docx",
                b"dummy content",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 401


def test_ingest_text_unauthenticated(client):
    """POST /api/sessions/{id}/ingest-text without token returns 401."""
    response = client.post(
        f"/api/sessions/{MOCK_SESSION_ID}/ingest-text",
        json={"raw_text": "Câu 1: Test"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. State Precondition Tests (Status != draft returns 409)
# ---------------------------------------------------------------------------


def test_ingest_text_session_not_in_draft_returns_409(client, mock_auth_user, auth_headers):
    """Ingestion rejected with 409 Conflict if session status is already 'blueprinted' or 'generating'."""
    mock_db = MagicMock()
    mock_ownership = MagicMock()
    mock_ownership.data = [{"user_id": "00000000-0000-0000-0000-000000000001"}]
    mock_status = MagicMock()
    mock_status.data = [{"status": "generating"}]

    mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        mock_ownership,
        mock_status,
    ]

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/ingest-text",
            json={"raw_text": "Câu 1: Nội dung câu 1\nA. 1 B. 2 C. 3 D. 4\nĐÁP ÁN: 1.A"},
            headers=auth_headers,
        )
    assert response.status_code == 409
    assert "draft" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 3. File Security Tests (SEC-04)
# ---------------------------------------------------------------------------


def test_ingest_file_unsupported_pdf_returns_400(client, mock_auth_user, auth_headers):
    """Reject PDF upload with HTTP 400 Bad Request."""
    mock_db = MagicMock()
    mock_ownership = MagicMock()
    mock_ownership.data = [{"user_id": "00000000-0000-0000-0000-000000000001"}]
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]

    mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        mock_ownership,
        mock_status,
    ]

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/ingest-file",
            files={"file": ("exam.pdf", b"%PDF-1.4...", "application/pdf")},
            headers=auth_headers,
        )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 4. Zero Mutation & In-Memory Pre-validation (HTTP 422)
# ---------------------------------------------------------------------------


def test_ingest_text_missing_answer_returns_422(client, mock_auth_user, auth_headers):
    """Missing answer key triggers HTTP 422 and database is untouched."""
    mock_db = MagicMock()
    mock_ownership = MagicMock()
    mock_ownership.data = [{"user_id": "00000000-0000-0000-0000-000000000001"}]
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]

    mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        mock_ownership,
        mock_status,
    ]

    raw_text = """
### Câu 1: Cho hàm số $f(x) = x^2$.
A. 1  B. 2  C. 3  D. 4

### Câu 2: Không có đáp án đúng
A. 1  B. 2  C. 3  D. 4

BẢNG ĐÁP ÁN:
1.A
"""
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/ingest-text",
            json={"raw_text": raw_text},
            headers=auth_headers,
        )

    assert response.status_code == 422
    data = response.json()["detail"]
    assert any(
        err["question_no"] == 2 and err["error_type"] == "MISSING_ANSWER" for err in data["errors"]
    )

    # Ensure NO insert or delete called on database (Database untouched!)
    mock_db.table.return_value.insert.assert_not_called()
    mock_db.table.return_value.delete.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Success Ingestion (HTTP 200) & Atomic Replacement
# ---------------------------------------------------------------------------


def test_ingest_text_success_200(client, mock_auth_user, auth_headers):
    """Valid text ingestion replaces questions atomically and returns 200."""
    mock_db = MagicMock()
    mock_ownership = MagicMock()
    mock_ownership.data = [{"user_id": "00000000-0000-0000-0000-000000000001"}]
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]

    mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        mock_ownership,
        mock_status,
    ]

    # Mock RPC replacement success
    mock_rpc_exec = MagicMock()
    mock_rpc_exec.data = {"success": True, "count": 1}
    mock_db.rpc.return_value.execute.return_value = mock_rpc_exec

    # Mock query returning inserted questions
    mock_q_res = MagicMock()
    mock_q_res.data = [
        {
            "id": "q-1",
            "session_id": MOCK_SESSION_ID,
            "question_no": 1,
            "raw_content": "Giải phương trình $x + 1 = 2$",
            "options": {"A": "$x = 1$", "B": "$x = 2$", "C": "$x = 3$", "D": "$x = 4$"},
            "correct_key": "A",
            "has_missing_answer": False,
            "has_security_warning": False,
        }
    ]
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_q_res

    raw_text = """
### Câu 1: Giải phương trình $x + 1 = 2$
A. $x = 1$
B. $x = 2$
C. $x = 3$
D. $x = 4$

BẢNG ĐÁP ÁN:
1.A
"""
    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/ingest-text",
            json={"raw_text": raw_text},
            headers=auth_headers,
        )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["total_questions"] == 1
    assert res_data["session_id"] == MOCK_SESSION_ID
    assert len(res_data["questions"]) == 1


def test_ingest_file_docx_success_200(client, mock_auth_user, auth_headers):
    """Upload valid DOCX file, saves to storage, and replaces questions atomically."""
    mock_db = MagicMock()
    mock_ownership = MagicMock()
    mock_ownership.data = [{"user_id": "00000000-0000-0000-0000-000000000001"}]
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]

    mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        mock_ownership,
        mock_status,
    ]

    # Mock storage upload
    mock_db.storage.from_.return_value.upload.return_value = MagicMock()

    # Mock RPC
    mock_rpc_exec = MagicMock()
    mock_rpc_exec.data = {"success": True, "count": 2}
    mock_db.rpc.return_value.execute.return_value = mock_rpc_exec

    # Mock query returning inserted questions
    mock_q_res = MagicMock()
    mock_q_res.data = [
        {"id": "q-1", "question_no": 1, "correct_key": "A"},
        {"id": "q-2", "question_no": 2, "correct_key": "A"},
    ]
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_q_res

    docx_bytes = create_sample_docx_bytes()

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/ingest-file",
            files={
                "file": (
                    "toan12.docx",
                    docx_bytes,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["total_questions"] == 2
    assert "successfully" in res_data["message"]


def test_ingest_file_rpc_failure_returns_500_zero_mutation(client, mock_auth_user, auth_headers):
    """If RPC fails, ingestion returns 500 without performing client-side mutations or deletions."""
    mock_db = MagicMock()
    mock_ownership = MagicMock()
    mock_ownership.data = [{"user_id": "00000000-0000-0000-0000-000000000001"}]
    mock_status = MagicMock()
    mock_status.data = [{"status": "draft"}]

    mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        mock_ownership,
        mock_status,
    ]

    # Mock storage upload
    mock_db.storage.from_.return_value.upload.return_value = MagicMock()

    # Mock RPC failure (e.g. Postgres exception)
    mock_db.rpc.return_value.execute.side_effect = RuntimeError("RPC failure or network timeout")

    docx_bytes = create_sample_docx_bytes()

    with (
        patch("app.api.dependencies.get_supabase_client", return_value=mock_auth_user),
        patch("app.api.dependencies.get_authenticated_client", return_value=mock_db),
    ):
        response = client.post(
            f"/api/sessions/{MOCK_SESSION_ID}/ingest-file",
            files={
                "file": (
                    "toan12.docx",
                    docx_bytes,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            headers=auth_headers,
        )

    assert response.status_code == 500
    assert "Database atomic replacement failed" in response.json()["detail"]
    # Ensure NO client-side delete was called on question_blueprints or source_questions
    assert not mock_db.table.return_value.delete.called

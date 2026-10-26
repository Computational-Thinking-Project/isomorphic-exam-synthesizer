---
name: session-endpoints
description: Technical specification, error handling contracts, and implementation rules for exam session ingestion and state confirmation endpoints (TASK-202 / TASK-205).
---

# Session Endpoints Skill: Ingestion & Source Confirmation

Tài liệu đặc tả kỹ thuật, ràng buộc máy trạng thái, cơ chế an toàn CSDL và quy tắc xử lý lỗi phân tán cho bộ API quản lý phiên đề thi:
- `POST /api/sessions/{session_id}/ingest-file` (TASK-202 - BE-02 / SEC-04)
- `POST /api/sessions/{session_id}/ingest-text` (TASK-202 - BE-02)
- `POST /api/sessions/{session_id}/confirm-source` (TASK-205 - BE-03 / SEC-02)

---

## 1. Endpoints Specification

### A. File Ingestion Endpoint
- **Route:** `POST /api/sessions/{session_id}/ingest-file`
- **Content-Type:** `multipart/form-data`
- **Flow:**
  1. Xác thực người dùng và kiểm tra quyền sở hữu phiên:
     ```python
     # assert_ownership là hàm SYNC — KHÔNG dùng await
     assert_ownership("exam_sessions", session_id, current_user.id, db=db)
     ```
  2. Kiểm tra điều kiện máy trạng thái: Chỉ cho phép nạp đề khi `status == 'draft'`. Nếu khác `draft`, ném `HTTP 409 Conflict`.
  3. Kiểm tra an toàn file **SEC-04**:
     - Làm sạch filename chống Path Traversal: `clean_name = re.sub(r'[^a-zA-Z0-9._-]', '_', file.filename)`
     - Kiểm tra kích thước tệp raw: $\le 10\text{MB}$.
     - Đối với `.docx`: Kiểm tra magic bytes `PK\x03\x04`, mở zip kiểm tra cấu trúc `[Content_Types].xml` và `word/document.xml`, tỷ lệ giải nén $\le 50\text{MB}$ (chống Zip Bomb).
  4. Bóc tách 100% In-Memory (xem skill `parser-evaluator`).
  5. Nếu phát hiện lỗi cấu trúc / thiếu đáp án / lỗi OMML $\rightarrow$ ném **HTTP 422 Unprocessable Entity** (CSDL hoàn toàn không bị thay đổi).
  6. Nếu hợp lệ 100% $\rightarrow$ lưu file lên Supabase Storage với prefix: `{session_id}/{uuid}_{clean_name}`.
  7. Thực thi giao dịch nguyên tử thay thế câu hỏi nguồn qua Stored Procedure RPC (Mục 2) và kích hoạt background Blueprint pipeline (Mục 3).

---

### B. Direct Text Ingestion Endpoint
- **Route:** `POST /api/sessions/{session_id}/ingest-text`
- **Content-Type:** `application/json`
- **Payload:** `{"raw_text": "..."}` ($\le 100,000$ ký tự).
- **Flow:**
  1. `assert_ownership("exam_sessions", session_id, current_user.id, db=db)` (sync call, không dùng await).
  2. Kiểm tra trạng thái phiên: bắt buộc `draft` (nếu không $\rightarrow$ `HTTP 409 Conflict`).
  3. Bóc tách in-memory với `parse_markdown` hoặc `parse_latex`.
  4. Tiền kiểm tra tính toàn vẹn in-memory (nếu lỗi $\rightarrow$ `HTTP 422 Unprocessable Entity`).
  5. Ghi đè CSDL nguyên tử bằng Stored Procedure RPC `replace_source_questions`.

---

### C. Source Confirmation & Auto-Blueprint Activation (TASK-205)
- **Route:** `POST /api/sessions/{session_id}/confirm-source`
- **Content-Type:** `application/json`
- **Payload:**
  ```json
  {
    "acknowledged_security_warnings": false
  }
  ```
- **Guards & Status Codes:**
  1. **Ownership:** Kiểm tra phiên thuộc về `current_user.id` (`assert_ownership` - sync call, không dùng await).
  2. **Precondition (State Machine):** Kiểm tra trạng thái phiên. Nếu khác `'draft'` (ví dụ đã `'blueprinted'` hoặc `'generating'`), ném:
     ```python
     raise HTTPException(status_code=409, detail="Session is not in draft state")
     ```
  3. **Strict Validation:** Xác nhận toàn bộ `source_questions` hợp lệ (`has_missing_answer == False`, `has_unparsed_omml == False`) và bản ghi Blueprint nội bộ tương ứng đã sẵn sàng. Nếu chưa đầy đủ, ném `HTTP 422`.
  4. **Security Guard (SEC-02):** Nếu bất kỳ câu hỏi nào có `has_security_warning == True`:
     - Nếu `acknowledged_security_warnings` là `False` hoặc thiếu $\rightarrow$ ném `HTTP 422` yêu cầu người dùng xác nhận an toàn trước khi tiếp tục.
  5. **State Transition:** Kích hoạt toàn bộ blueprint tương ứng (`confirmed_at = NOW()`) và chuyển trạng thái phiên sang `'blueprinted'` qua RPC nguyên tử `confirm_exam_source`. Trả về HTTP 200.

---

## 2. Giao Dịch Nguyên Tử CSDL (Method 2A Stored Procedure) & Xử Lý Ngoại Lệ Phân Tán

### A. Mẫu Gọi Stored Procedure Nguyên Tử
Tuyệt đối không dùng các lệnh `delete` và `insert` riêng lẻ từ backend. Sử dụng hàm PostgreSQL `replace_source_questions` (TASK-202) hoặc `confirm_exam_source` (TASK-205) để thực thi trong một transaction nội bộ duy nhất:

```python
async def replace_source_questions_atomically(
    db: Client,
    session_id: str,
    questions: List[ParsedQuestionItem],
) -> List[Dict[str, Any]]:
    payload = [q.model_dump() for q in questions]

    try:
        rpc_res = db.rpc(
            "replace_source_questions",
            {"p_session_id": session_id, "p_questions": payload},
        ).execute()

        if not (rpc_res.data and isinstance(rpc_res.data, dict) and rpc_res.data.get("success")):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database atomic replacement failed: unexpected RPC response",
            )
    except HTTPException:
        raise
    except Exception as exc:
        handle_distributed_rpc_exception(exc, session_id)
```

---

### B. Quy Tắc Bắt Lỗi Phân Tán Bắt Buộc (Type-based Error Classification)
Xử lý ngoại lệ phát sinh từ lời gọi RPC phải tuân thủ nghiêm ngặt nguyên tắc **nhận diện bằng `isinstance`** và **không suy đoán kết quả**:

```python
import httpx
try:
    import httpcore
except ImportError:
    httpcore = None
from postgrest.exceptions import APIError

NETWORK_TIMEOUT_EXCEPTIONS = (httpx.TimeoutException, TimeoutError) if httpcore is None else (httpx.TimeoutException, httpcore.TimeoutException, TimeoutError)
NETWORK_TRANSPORT_EXCEPTIONS = (httpx.TransportError, httpx.NetworkError, httpx.ProtocolError, ConnectionError) if httpcore is None else (httpx.TransportError, httpx.NetworkError, httpx.ProtocolError, httpcore.NetworkError, httpcore.ProtocolError, ConnectionError)

def handle_distributed_rpc_exception(exc: Exception, session_id: str) -> None:
    code = getattr(exc, "code", "") or ""
    err_lower = str(exc).lower()

    # 1. Phân quyền & Sở hữu (403)
    if code == "42501" or "42501" in str(exc) or "access denied" in err_lower:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied or session ownership mismatch") from exc

    # 2. Ràng buộc máy trạng thái (409)
    if code == "22023" or "22023" in str(exc) or "draft" in err_lower:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot ingest questions: session is not in draft status") from exc

    # 3. Không tìm thấy phiên (404)
    if code == "P0002" or "not found" in err_lower:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found") from exc

    # 4. Timeout Mạng (504): Trạng thái commit chưa xác định
    if is_network_timeout(exc):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Database atomic replacement status is uncertain due to network timeout. The transaction may have completed. Please verify session state before retrying.",
        ) from exc

    # 5. Mất kết nối / Ngắt phản hồi (504): Trạng thái commit chưa xác định
    if is_network_transport(exc):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Database atomic replacement status is uncertain due to network communication error. The transaction may have completed. Please verify session state before retrying.",
        ) from exc

    # 6. Có bằng chứng xác nhận rollback từ CSDL (500)
    # Lưu ý: Loại trừ mã Gateway (500, 502, 503, 504), SQLSTATE Class 08 (08006, 08007) và 40003
    if is_database_rollback_evidence(exc):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database atomic replacement failed and was rolled back.",
        ) from exc

    # 7. Lỗi nội bộ không xác định (500): Không khẳng định rollback khi chưa có xác nhận từ CSDL
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database atomic replacement failed. Please verify session state before retrying.",
    ) from exc
```

---

## 3. Background Blueprint Extraction Trigger

Sau khi nạp đề thành công, kích hoạt pipeline nền qua `FastAPI BackgroundTasks` với giới hạn đồng thời (`asyncio.Semaphore(3)`):

```python
async def trigger_blueprint_pipeline(
    session_id: str,
    questions: List[Dict[str, Any]],
    db: Optional[Any] = None,
) -> None:
    """Non-blocking background trigger for AI Blueprint Extraction (TASK-203 integration hook / TASK-205)."""
    semaphore = asyncio.Semaphore(3)

    async def _extract_question(q_data: Dict[str, Any]) -> None:
        async with semaphore:
            logger.debug("Processing session %s, question %s", session_id, q_data.get("question_no"))
            # Call Gemini extraction logic (TASK-203)

    tasks = [_extract_question(q) for q in questions]
    await asyncio.gather(*tasks, return_exceptions=True)
```

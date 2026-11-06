# TASK-305 — Kế hoạch triển khai chi tiết (Đã chuẩn hóa theo Codebase thực tế)

**Phạm vi:** API phê duyệt cuối cùng, kích hoạt khóa nội dung sau phê duyệt (HTTP 423), và API ma trận đối soát đáp án các đề thi sau hoán vị.  
**Nhánh theo đặc tả:** `feat/duy-task-305-approval-lock`  
**ETA trong đặc tả:** 02/11/2026; hạn đợt: 03/11/2026.  
**Nguyên tắc:** Tái sử dụng cơ chế ownership, exception handler, schema và service hiện có; không viết lại TASK-301/TASK-303; không tự thêm nghiệp vụ ngoài đặc tả; không chèn RPC hoặc migration không cần thiết.

---

## 1. Mục tiêu và ranh giới công việc

### 1.1. Kết quả cần bàn giao

1. `POST /api/sessions/{session_id}/finalize/approve`:
   - Xác thực ownership qua `assert_ownership("exam_sessions", session_id, user.id, db=db)`.
   - Kiểm tra 4 điều kiện chốt đề (100% câu hỏi hiện hành approved, 0 câu regenerating, 100% version finalized, session status $\in \{\text{'reviewed'}, \text{'generated'}\}$).
   - Chuyển `status = 'approved'`, cập nhật `approved_at = now()`, `updated_at = now()` (nguyên tử qua 1 câu UPDATE).
   - Xử lý idempotent: nếu session đã `approved`, trả 200 kèm `approved_at` cũ, không đổi timestamp, không side-effect.
2. Khóa nội dung HTTP 423 (`ERR_SESSION_LOCKED`):
   - Kích hoạt cơ chế khóa sẵn có trong `ReviewService.check_session_guards` (ngay khi session chuyển sang `approved`/`exported`, toàn bộ `/accept`, `/reject`, `/revert` sẽ tự động trả `423 ERR_SESSION_LOCKED`).
   - Kiểm thử bảo đảm không có thao tác review nào lọt qua sau khi đã approve.
3. `GET /api/sessions/{session_id}/finalize/matrix`:
   - Trả ma trận đáp án theo `question_no` sau shuffle.
   - Ưu tiên đọc từ bảng `answer_keys` (cột `correct_option`).
   - Fallback sang bảng `version_questions` (cột `correct_key`) khi `answer_keys` chưa có dữ liệu.
4. Schemas, Clean Architecture code (`Route -> Service -> Repository`) và bộ unit test tự động.
5. Bàn giao hợp đồng dữ liệu chuẩn cho downstream (TASK-306 Typst PDF & TASK-307 XeLaTeX/MD Bundler).

### 1.2. Không làm trong task này (Out-of-scope)

- Không sửa đổi hay tạo mới bảng trong database (schema đã đủ).
- Không chèn bản ghi vào `review_logs` khi approve session (bảng `review_logs` chỉ dành cho audit câu hỏi đơn lẻ với các action `ACCEPT`, `REJECT`, `REVERT`, `REJECT_FAILED`).
- Không triển khai thuật toán Fisher–Yates (thuộc TASK-303 của Tâm).
- Không biên dịch Typst/XeLaTeX, không đóng gói ZIP, không tạo signed URL (thuộc TASK-306, TASK-307, TASK-308).
- Không xây dựng chức năng unlock (logic hệ thống cấm mở khóa phiên thi đã duyệt).
- Không mở rộng sửa đổi các route ingestion, blueprint, configuration ngoài phạm vi task được giao.

---

## 2. Xác thực cấu trúc dữ liệu và logic thực tế trong Codebase

Đã được xác minh trực tiếp từ `backend/scripts/schema.sql`, `dependencies.py` và `backend/app/services/review/service.py`:

| Thành phần | Cấu trúc thực tế trong repo | Cách triển khai trong TASK-305 |
|---|---|---|
| **Bảng `exam_sessions`** | Cột `status public.session_status`, `approved_at TIMESTAMPTZ NULL`, `updated_at` | Update trực tiếp `status='approved'`, `approved_at=now()` khi đủ điều kiện. |
| **Trạng thái hợp lệ** | Enum `session_status`: `'generated'`, `'reviewed'` | Cho phép approve từ 2 trạng thái này. Nếu đang `draft`, `generating`, `failed` $\rightarrow$ raise 409 `ERR_INVALID_SESSION_STATE`. |
| **Bảng `exam_versions`** | Cột `id`, `session_id`, `version_code`, `is_finalized BOOLEAN` | Kiểm tra tất cả version thuộc session đều có `is_finalized = true`. |
| **Bảng `version_questions`** | Cột `is_current BOOLEAN`, `status public.question_status`, `correct_key TEXT` | Đếm câu vi phạm: `is_current=true AND status != 'approved'`, hoặc `status = 'regenerating'`. |
| **Bảng `answer_keys`** | Cột `version_id`, `question_no INT`, `correct_option TEXT` | Đọc `question_no`, `correct_option` theo `version_id`. Lưu ý tên cột là **`correct_option`**, không phải `correct_key`. |
| **Audit Log** | Bảng `review_logs` chỉ có FK `version_question_id` (NOT NULL) và enum 4 giá trị | Audit của session nằm trực tiếp ở `exam_sessions(status, approved_at, updated_at)`. Không insert `review_logs`. |
| **Xác thực quyền sở hữu** | `assert_ownership("exam_sessions", session_id, user.id, db=db)` | Có sẵn trong `app.api.dependencies`, tự động trả 404 nếu không tìm thấy, 403 nếu không chính chủ. |
| **Xử lý Exception** | `ReviewDomainException(status_code, error_code, detail)` | Đã đăng ký exception handler ở `main.py`, tự động serialize JSON `{ "error_code": ..., "detail": ... }`. |
| **Khóa HTTP 423** | `check_session_guards` trong `ReviewService` | Đã có sẵn: `if status in ("approved", "exported"): raise ReviewDomainException(423, "ERR_SESSION_LOCKED", ...)`. |

---

## 3. Thiết kế chi tiết theo Clean Architecture

```
Client (Teacher / Downstream)
           │
           ▼
[app/api/routes/finalize.py]  <-- Router, HTTP Status, assert_ownership
           │
           ▼
[app/services/finalize/service.py]  <-- Business Logic, Pre-condition rules, Idempotency, Matrix formatting
           │
           ▼
[app/services/finalize/repository.py]  <-- Supabase Client Queries (Atomic update, aggregations, matrix select)
           │
           ▼
[Supabase Database] (exam_sessions, exam_versions, version_questions, answer_keys)
```

---

## 4. Các giai đoạn triển khai chi tiết

### Giai đoạn 1 — Pydantic Response Schemas
**File:** `backend/app/models/schemas.py`

1. **`FinalizeApproveResponse`**:
   ```python
   class FinalizeApproveResponse(BaseModel):
       session_id: UUID
       status: str  # "approved"
       approved_at: datetime
       message: str
   ```
2. **`MatrixItem`**:
   ```python
   class MatrixItem(BaseModel):
       question_no: int
       answers: dict[str, str]  # {"101": "A", "102": "C", "103": "B", "104": "D"}
   ```
3. **`AnswersMatrixResponse`**:
   ```python
   class AnswersMatrixResponse(BaseModel):
       session_id: UUID
       total_questions: int
       version_codes: list[str]  # ["101", "102", "103", "104"]
       matrix: list[MatrixItem]
   ```

---

### Giai đoạn 2 — `FinalizeRepository`
**File:** `backend/app/services/finalize/repository.py`

1. **`get_session_meta(session_id: str) -> Optional[dict]`**:
   - Truy vấn `exam_sessions`: `select("id, status, approved_at, user_id")`.
   - Trả về `None` nếu không tìm thấy.
2. **`check_preconditions(session_id: str) -> dict`**:
   - Lấy danh sách version thuộc session: `select("id, version_code, is_finalized").eq("session_id", session_id)`.
   - Kiểm tra version: đếm tổng version, đếm số version `is_finalized = false`.
   - Lấy danh sách question qua các version_id:
     - Đếm số câu `is_current = true AND status != 'approved'`.
     - Đếm số câu `status = 'regenerating'`.
   - Trả về dict tóm tắt:
     ```python
     {
         "unapproved_count": int,
         "regenerating_count": int,
         "unfinalized_versions_count": int,
         "total_versions": int,
         "total_questions": int,
     }
     ```
3. **`update_session_approved(session_id: str) -> dict`**:
   - Chạy atomic UPDATE trên `exam_sessions`:
     ```python
     res = (
         self.db.table("exam_sessions")
         .update({"status": "approved", "approved_at": _now_iso(), "updated_at": _now_iso()})
         .eq("id", session_id)
         .in_("status", ["reviewed", "generated"])
         .execute()
     )
     ```
   - Trả về bản ghi đã cập nhật.
4. **`fetch_matrix_raw(session_id: str) -> tuple[list[dict], list[dict]]`**:
   - Truy vấn các versions: lấy danh sách `(id, version_code)` sắp xếp tăng dần theo `version_code`.
   - Thử lấy `answer_keys`:
     `select("version_id, question_no, correct_option").in_("version_id", version_ids).order("question_no")`.
   - Nếu `answer_keys` rỗng, fallback lấy từ `version_questions`:
     `select("version_id, question_no, correct_key").in_("version_id", version_ids).eq("is_current", True).order("question_no")`.

---

### Giai đoạn 3 — `FinalizeService`
**File:** `backend/app/services/finalize/service.py`

1. **`approve_session(session_id: str, user_id: str) -> FinalizeApproveResponse`**:
   - **Bước 1 (Idempotent Check):**
     - Đọc session meta từ repository. Nếu `status == 'approved'`:
       - Trả về ngay `FinalizeApproveResponse` với `status="approved"`, `approved_at=meta["approved_at"]`, `message="Session already approved"`.
   - **Bước 2 (State Validation):**
     - Nếu `status not in ("reviewed", "generated")`:
       - Raise `ReviewDomainException(409, "ERR_INVALID_SESSION_STATE", f"Phiên ở trạng thái '{status}' không thể phê duyệt")`.
   - **Bước 3 (Preconditions Validation):**
     - Gọi `check_preconditions(session_id)`:
       - Nếu `total_versions == 0`:
         - Raise `ReviewDomainException(400, "ERR_VERSIONS_NOT_FINALIZED", "Phiên chưa có đề hoán vị nào")`.
       - Nếu `unfinalized_versions_count > 0`:
         - Raise `ReviewDomainException(400, "ERR_VERSIONS_NOT_FINALIZED", f"Còn {count} đề thi chưa hoàn tất hoán vị")`.
       - Nếu `regenerating_count > 0`:
         - Raise `ReviewDomainException(409, "ERR_QUESTION_REGENERATING", f"Còn {count} câu hỏi đang trong tiến trình sinh lại")`.
       - Nếu `unapproved_count > 0`:
         - Raise `ReviewDomainException(400, "ERR_NOT_ALL_QUESTIONS_APPROVED", f"Còn {count} câu hỏi hiện hành chưa được duyệt")`.
   - **Bước 4 (Atomic Update):**
     - Gọi `update_session_approved(session_id)`.
     - Trả về `FinalizeApproveResponse(session_id=..., status="approved", approved_at=..., message="Phê duyệt phiên thi thành công và đã khóa nội dung")`.

2. **`get_answers_matrix(session_id: str, user_id: str) -> AnswersMatrixResponse`**:
   - Gọi repository lấy danh sách version và dữ liệu đáp án (ưu tiên `answer_keys`, fallback `version_questions`).
   - Ghép ma trận:
     - Tạo cấu trúc `map_matrix: dict[int, dict[str, str]] = defaultdict(dict)`.
     - Với mỗi record: `map_matrix[q_no][version_code] = ans`.
     - Sort theo `question_no` tăng dần.
   - Trả về `AnswersMatrixResponse`.

---

### Giai đoạn 4 — Router & Đăng ký App
**File:** `backend/app/api/routes/finalize.py` và `backend/app/main.py`

1. **`finalize.py`**:
   - Route `POST /{session_id}/finalize/approve`:
     - Depends: `assert_ownership("exam_sessions", session_id, current_user.id, db=db)`
     - Status: 200 OK
     - Response: `FinalizeApproveResponse`
   - Route `GET /{session_id}/finalize/matrix`:
     - Depends: `assert_ownership("exam_sessions", session_id, current_user.id, db=db)`
     - Status: 200 OK
     - Response: `AnswersMatrixResponse`
2. **`main.py`**:
   - Import `finalize` router.
   - Đăng ký: `app.include_router(finalize.router, prefix="/api/sessions", tags=["Finalize"])`.

---

### Giai đoạn 5 — Bộ kiểm thử tự động (Unit & Integration Tests)
**File:** `backend/tests/api/test_finalize.py`

1. **Happy Path:**
   - Approve session thành công khi tất cả câu hỏi approved và versions finalized $\rightarrow$ HTTP 200, status `approved`.
2. **Idempotency:**
   - Gọi approve lần 2 $\rightarrow$ HTTP 200, trả lại đúng `approved_at` cũ.
3. **Precondition Violations:**
   - Có câu đang `regenerating` $\rightarrow$ HTTP 409 `ERR_QUESTION_REGENERATING`.
   - Có câu `pending_review` hoặc `rejected` $\rightarrow$ HTTP 400 `ERR_NOT_ALL_QUESTIONS_APPROVED`.
   - Có version `is_finalized = false` $\rightarrow$ HTTP 400 `ERR_VERSIONS_NOT_FINALIZED`.
   - Session status là `generating` hoặc `failed` $\rightarrow$ HTTP 409 `ERR_INVALID_SESSION_STATE`.
4. **Content Lock (HTTP 423):**
   - Sau khi session approved, gọi `/accept`, `/reject`, `/revert` từ `ReviewAPI` $\rightarrow$ tất cả trả HTTP 423 `ERR_SESSION_LOCKED`.
5. **Answers Matrix:**
   - Đọc từ `answer_keys` $\rightarrow$ ma trận đúng format, đúng thứ tự `question_no` và `version_codes`.
   - Khi `answer_keys` rỗng $\rightarrow$ fallback mượt mà sang `version_questions`.
6. **Ownership / Security:**
   - User khác gọi $\rightarrow$ HTTP 403 Forbidden.
   - Session không tồn tại $\rightarrow$ HTTP 404 Not Found.

---

## 5. Kế hoạch kiểm tra chất lượng trước khi nộp PR

1. Chạy linter:
   ```bash
   python -m ruff check backend/app
   ```
2. Chạy test suite:
   ```bash
   pytest backend/tests/api/test_finalize.py backend/tests/api/test_review_api.py -v
   ```
3. Đảm bảo toàn bộ test của TASK-301 và TASK-305 đều xanh 100%.

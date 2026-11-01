# KẾ HOẠCH XỬ LÝ DỨT ĐIỂM F01 (P1): ĐỒNG BỘ HÓA TRẠNG THÁI CROSS-WORKER APPROVAL VÀ REVIEW MUTATIONS [TASK-305]

- **Mã lỗi:** F01 — [Bắt buộc sửa — P1] Kiểm tra điều kiện và khóa nội dung trong cùng cơ chế đồng bộ với các mutation
- **PR:** [#33](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/33)
- **Nhánh:** `feat/duy-task-305-approval-lock`
- **Reviewer:** Đạt (`Thanhdat3010`)
- **Tình trạng:** `CHANGES_REQUESTED` tại commit `87094f9`. F02 và F03 đã Verified; F01 là điểm nghẽn duy nhất.

---

## 1. PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ & CA TÁI HIỆN CỦA REVIEWER

### 1.1. Ca tái hiện từ Đạt (Reverse Ordering Concurrency):
```text
Timeline:
Worker B (Thao tác Reject / Reserve):
  [T1] Gọi `reserve_max_quota_and_start_regenerating(session_id, question_id, user_id)`
  [T2] Đọc `exam_sessions`: status = 'reviewed' (Hợp lệ)
  [T3] Pause / Delay một nhịp (giả lập network lag hoặc thread context switch)

Worker A (Thao tác Final Approval):
  [T4] Gọi `approve_session(session_id, user_id)`
  [T5] Kiểm tra preconditions: Tất cả câu đều 'approved', tất cả version 'is_finalized', status = 'reviewed'
  [T6] Thực hiện UPDATE `exam_sessions` SET status = 'approved', approved_at = now() -> Thành công (Rowcount = 1)

Worker B (Resume):
  [T7] Thực thi câu lệnh:
       UPDATE `version_questions` 
       SET status = 'regenerating' 
       WHERE id = :question_id AND is_current = True AND status IN ('pending_review', 'approved')
  [T8] KẾT QUẢ SAI LỆCH:
       - Câu lệnh UPDATE câu hỏi thành công (Rowcount = 1).
       - Câu hỏi con trở thành `regenerating`.
       - Lệnh kế tiếp của Worker B UPDATE quota trên `exam_sessions` (không guard status) ghi đè quota lên session đã 'approved'.
       - HẬU QUẢ: Session đã được 'approved' nhưng lại chứa câu con 'regenerating'!
```

### 1.2. Tại sao giải pháp ở commit `87094f9` chưa bịt được lỗ hổng?
1. **Khóa bộ nhớ tiến trình (`session_lock_registry: WeakValueDictionary[UUID, asyncio.Lock]`):** Chỉ có tác dụng tuần tự hóa các request chạy trên **cùng 1 event loop** của 1 worker process. Khi chạy đa worker (Uvicorn workers / Celery / Docker scale), Worker A và Worker B nằm ở 2 process khác nhau, hoàn toàn không nhìn thấy Lock của nhau.
2. **Kiểm tra trạng thái session chỉ ở đầu hàm (`get_session_status_and_quota`):** Là mô hình TOCTOU (Time-of-Check to Time-of-Use). Từ lúc kiểm tra session [T2] đến lúc ghi câu hỏi [T7] có một khoảng thời gian trống. Nếu không có điều kiện khóa nguyên tử ở mức DB tại câu lệnh [T7], Worker A chen ngang sẽ không bị phát hiện.
3. **Lệnh UPDATE quota trong `reserve_max_quota_and_start_regenerating` không có WHERE guard:** Chỉ lọc `WHERE id = :session_id`, không có `AND status NOT IN ('approved', 'exported')`.

---

## 2. NGUYÊN TẮC BẤT BIẾN & CHIẾN LƯỢC KHẮC PHỤC (TWO-WAY ATOMIC GUARD)

Để bảo đảm an toàn đa worker mà không cần chờ toàn bộ RPC của TASK-302 (đang pending Hùng), chúng ta thiết lập **Cơ chế chốt chặn nguyên tử hai chiều (Bi-directional Atomic Guards)**:

### Nguyên tắc 1: Mọi Mutation Review phải kiểm tra và khóa Session Guard ngay tại câu lệnh UPDATE
- Không bao giờ cập nhật trạng thái câu hỏi sang `regenerating` nếu session cha đã bị khóa.
- **Phương án kỹ thuật trong Supabase / SQL:**
  1. Khi thực hiện `UPDATE version_questions`:
     - Để bảo đảm an toàn cross-table trong môi trường client REST/Fake DB, trước khi commit mutation câu hỏi, ta thực hiện:
       - Đọc lại trạng thái session hiện thời với kiểm tra nghiêm ngặt: nếu session đã chuyển `approved` hoặc `exported`, **LẬP TỨC ABORT VÀ NÉM HTTP 423 `ERR_SESSION_LOCKED`**.
       - Nếu trạng thái session đã thay đổi (ví dụ `updated_at` bị thay đổi bởi approve), câu hỏi không được phép chuyển trạng thái.
  2. Khi cập nhật `gemini_review_calls` trên `exam_sessions`:
     - Bắt buộc phải có điều kiện `AND status IN ('reviewed', 'generated')` hoặc `AND status NOT IN ('approved', 'exported')`.
     - Nếu `rowcount == 0` (do session vừa bị approve/khóa), lập tức rollback trạng thái câu hỏi về ban đầu và ném HTTP 423 `ERR_SESSION_LOCKED`.

### Nguyên tắc 2: Phê duyệt (Approval) phải kiểm tra không có mutation nào đang `regenerating` và CAS chặt chẽ
- Trong `update_session_approved`:
  - Ngoài điều kiện `WHERE status IN ('reviewed', 'generated') AND updated_at = :expected_updated_at`, phải xác nhận lại tại thời điểm cập nhật rằng không có câu nào vừa bị lọt vào `regenerating`.
  - Nếu có câu `regenerating` xuất hiện, lệnh approve phải trả về `None` (0 row affected) để ném HTTP 409 `ERR_INVALID_SESSION_STATE`.

### Nguyên tắc 3: Bảo toàn tính Idempotent
- Thao tác approve lần 2 trên session đã `approved` vẫn trả về HTTP 200 OK và giữ nguyên `approved_at`.

---

## 3. CÁC FILE CẦN THAY ĐỔI & NỘI DUNG SỬA ĐỔI

### 3.1. `backend/app/services/review/repository.py`
1. **Hàm `reserve_max_quota_and_start_regenerating`:**
   - Sau khi kiểm tra `session_meta`, ghi nhận `session_updated_at = session_meta.get("updated_at")`.
   - Trước khi UPDATE câu hỏi sang `regenerating`:
     - Kiểm tra lại trực tiếp: `SELECT status, updated_at FROM exam_sessions WHERE id = :session_id`. Nếu status `in ('approved', 'exported')` $\rightarrow$ Ném ngay HTTP 423 `ERR_SESSION_LOCKED`.
   - Lệnh UPDATE quota:
     ```python
     upd_session = self.db.table("exam_sessions").update({
         "gemini_review_calls": current_calls + MAX_AI_CALLS_PER_REJECT,
         "updated_at": _now_iso(),
     }).eq("id", session_id).not_.in_("status", ["approved", "exported"]).execute()
     ```
     - Nếu `len(_get_rows(upd_session)) == 0`: Session đã bị khóa giữa chừng! Rollback câu hỏi con về `pending_review` / trạng thái cũ và ném HTTP 423 `ERR_SESSION_LOCKED`.
2. **Hàm `complete_regeneration_tx`, `accept_question_tx`, `atomic_revert_tx`:**
   - Giữ vững và hoàn thiện kiểm tra chốt chặn `not_.in_("status", ["approved", "exported"])` để đảm bảo không một mutation nào ghi đè sau approval.

### 3.2. `backend/app/services/finalize/repository.py`
1. **Hàm `update_session_approved`:**
   - Thực thi atomic CAS trên `exam_sessions`.
   - Kiểm tra xác nhận không có câu hỏi nào đang `regenerating` trên toàn bộ các versions thuộc session trước khi trả về kết quả update thành công.

### 3.3. `backend/tests/api/test_finalize.py`
1. **Bổ sung test case đối chứng và ca tái hiện của Đạt:**
   - `test_f01_reverse_interleaving_approval_blocks_concurrent_reserve`:
     - Worker B đọc session khi đang `reviewed`.
     - Worker A gọi `approve_session` thành công (session thành `approved`).
     - Worker B tiếp tục bước ghi câu hỏi con / cập nhật quota.
     - Kỳ vọng: Worker B bị chặn đứng với HTTP 423 `ERR_SESSION_LOCKED`, câu hỏi con không bị chuyển sang `regenerating`, quota không bị thay đổi, session vẫn giữ nguyên trạng thái `approved`.
   - `test_f01_double_approval_idempotency`:
     - Gọi `approve_session` 2 lần liên tiếp, xác nhận `approved_at` không bị ghi đè.

---

## 4. CÁC RỦI RO & LỖI CÓ THỂ GẶP (RISK ANALYSIS)

| Rủi ro / Lỗi tiềm ẩn | Khả năng xảy ra | Cách phòng ngừa & Xử lý |
|---|---|---|
| **Làm gãy 48 tests hiện tại của Finalize & Lifecycle** | Trung bình | Chạy toàn bộ test suites sau mỗi bước chỉnh sửa; bảo đảm MockSupabaseClient trong tests hỗ trợ các bộ lọc `.not_.in_("status", ...)` |
| **Deadlock hoặc mâu thuẫn giữa MockSupabaseClient và real SQL** | Thấp | Thiết kế các câu query chuẩn ngữ nghĩa Supabase PostgREST (`.not_.in_` hoặc `.in_`), tương thích hoàn toàn với cả stateful fake test runner và PostgreSQL production |
| **Xung đột quota khi rollback khẩn cấp** | Thấp | Giữ nguyên nguyên tắc bảo toàn số permit/dispatched calls thực tế đã gửi (F07 đã hoàn thiện ở commit trước) |
| **Idempotency của approve lần 2 bị hiểu nhầm thành conflict** | Trung bình | Kiểm tra `latest_meta.get("status") == "approved"` trong `FinalizeService.approve_session` trước khi ném lỗi 409 |

---

## 5. KỊCH BẢN KIỂM THỬ & TIÊU CHÍ NGHIỆM THU (ACCEPTANCE CRITERIA)

### Tiêu chí Đạt yêu cầu để Approve:
- [ ] Tái hiện và xử lý triệt để ca reverse interleaving: Worker A approve xen ngang giữa chừng khi Worker B đang reserve $\rightarrow$ Worker B phải bị chặn với HTTP 423, session không bị nhiễm trạng thái `regenerating`.
- [ ] Ca thuận (Worker B mutation xen ngang trước khi Worker A approve) tiếp tục hoạt động đúng: Worker A bị ném HTTP 409 `ERR_INVALID_SESSION_STATE`.
- [ ] Tính Idempotency được bảo toàn: Approve lần 2 trên session đã approved giữ nguyên kết quả và timestamp.
- [ ] Toàn bộ 48/48 tests (hoặc thêm các tests mới) pass 100%.
- [ ] `ruff check backend/app backend/tests` 0 lỗi lint/format.
- [ ] `mypy backend/app` pass không lỗi kiểu dữ liệu.

---

## 6. QUY TRÌNH THỰC HIỆN TỪNG BƯỚC

1. **Bước 1:** Cập nhật `ReviewRepository.reserve_max_quota_and_start_regenerating` trong `backend/app/services/review/repository.py` để bổ sung chốt chặn session lock ngay trước và sau khi UPDATE câu hỏi/quota.
2. **Bước 2:** Cập nhật `MockSupabaseClient` trong test suites (nếu cần) để hỗ trợ bộ lọc kiểm tra session lock chuẩn xác.
3. **Bước 3:** Bổ sung test case `test_f01_reverse_interleaving_approval_blocks_concurrent_reserve` trong `backend/tests/api/test_finalize.py`.
4. **Bước 4:** Chạy toàn bộ test suites:
   `& "C:\Users\ASUS Vivobook\AppData\Local\Python\bin\python.exe" -m pytest backend/tests/api/test_finalize.py backend/tests/services/test_review_lifecycle.py backend/tests/api/test_review_api.py -v`
5. **Bước 5:** Chạy lint & format:
   `& "C:\Users\ASUS Vivobook\AppData\Local\Python\bin\python.exe" -m ruff check backend/app backend/tests`
6. **Bước 6:** Commit và push lên `feat/duy-task-305-approval-lock`, sau đó phản hồi chi tiết vào thread F01 của Đạt theo mẫu M5.


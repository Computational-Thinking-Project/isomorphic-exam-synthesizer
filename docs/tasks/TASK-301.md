# TASK-301 — Plan và Bàn Giao: API Thẩm Định 1-1, Vòng Đời `is_current`, Revert Nguyên Tử & Safe Re-shuffle Invalidation

- **Nguồn giao việc:** [W3_ASSIGNMENT.md](../../W3_ASSIGNMENT.md) (v2.1; 28/10/2026), [w3.md](../../w3.md)
- **Phụ trách:** Duy (`johannguyen015` — Lead); Hùng (`benalexx007` — Contributor)
- **Reviewer:** Hùng (`benalexx007` — đã chốt)
- **Repo/nhánh:** `feat/duy-task-301-review-lifecycle-api`; PR: [Draft PR URL](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/new/feat/duy-task-301-review-lifecycle-api)
- **Hạn đợt:** tối thứ 3 03/11/2026; **ETA task:** Thứ 7 31/10/2026 (Duy xác nhận)

---

## Mình cần làm gì?

### Hành vi / Tiêu chí đạt:
1. **Kiểm soát phiên & Bảo vệ quyền sở hữu:**
   - Mọi endpoint thẩm định đều qua `assert_ownership` xác minh quyền sở hữu tài nguyên của user.
   - Kiểm tra `session.status`: nếu đang `generating` $\rightarrow$ trả về `HTTP 409 Conflict`; nếu đã `approved` hoặc `exported` $\rightarrow$ trả về `HTTP 423 Locked`.
2. **Endpoint Chấp nhận câu hỏi (`POST /api/sessions/{session_id}/questions/{version_question_id}/accept`):**
   - Xác minh bản ghi có `is_current = true`.
   - Cập nhật `status = "approved"`, ghi nhận bản ghi audit log vào `review_logs` (`action_type = "ACCEPT"`).
3. **Endpoint Từ chối & Sinh lại biến thể (`POST /api/sessions/{session_id}/questions/{version_question_id}/reject`):**
   - **Trần Quota Thẩm định độc lập:** Kiểm tra `exam_sessions.gemini_review_calls < 30`. Nếu đã chạm 30 lượt $\rightarrow$ từ chối ngay với mã `ERR_REVIEW_QUOTA_EXHAUSTED` (HTTP 429). Mỗi lượt gọi AI sinh lại thành công/thất bại đều tính `gemini_review_calls += 1`.
   - **Kiểm soát đồng thời:** Sử dụng `asyncio.Semaphore(1)` theo từng `session_id` để tránh race condition khi người dùng bấm reject dồn dập.
   - **Mô hình 2 Transaction Ngắn (Chống cạn kiệt DB Connection Pool):**
     - *Short DB Transaction 1:* Kiểm tra `is_current = true`, cập nhật `status = "regenerating"`, `updated_at = now()` và commit giải phóng connection ngay.
     - *AI Regeneration ngoài DB Transaction (10–30s):* Gọi module TASK-304 sinh biến thể câu hỏi đạt chuẩn toán học + lời giải chi tiết mới. Tuyệt đối không giữ DB connection.
     - *Short DB Transaction 2:*
       - Đánh dấu câu cũ: `is_current = false`, `status = "rejected"`.
       - Chèn câu mới: `is_current = true`, `regenerated_from_id = old_id`, `status = "pending_review"`.
       - Ghi audit log vào `review_logs` (`action_type = "REJECT"`, `reason = reason`).
4. **Cơ chế Tự động Mở Khóa Crash (Stale Regeneration Guard):**
   - Quét các câu có `status = "regenerating"` mà `updated_at < now() - interval '3 minutes'` $\rightarrow$ tự động giải phóng về `pending_review` kèm ghi log `REJECT_FAILED`.
5. **Quy trình Hoàn nguyên Nguyên tử (Atomic Revert Flow):**
   - Endpoint `POST /api/sessions/{session_id}/questions/{version_question_id}/revert`: Thực thi trong 1 PostgreSQL Transaction duy nhất:
     - Đánh dấu biến thể hiện tại: `is_current = false`.
     - Chèn bản ghi mới sao chép nguyên văn từ câu gốc (`source_questions`): `is_current = true`, `is_reverted = true`, `status = "approved"`, `regenerated_from_id = old_id`.
     - Ghi `review_logs` (`action_type = "REVERT"`).
6. **Vô hiệu hóa Trạng thái Hoán vị An toàn (Safe Re-shuffle Invalidation):**
   - Nếu thực hiện Reject hoặc Revert khi phiên đã từng bấm Shuffle (`exam_versions.is_finalized = true`) $\rightarrow$ tự động hạ trạng thái phiên về `generated` và reset `exam_versions.is_finalized = false`. Bắt buộc phải bấm Shuffle lại trước khi Approve.
7. **Endpoint Theo dõi Tiến độ Duyệt (`GET /api/sessions/{session_id}/review/progress`):**
   - Trả về JSON: `required_count`, `current_count`, `approved_count`, danh sách câu chưa duyệt, `is_complete`, `can_finalize`.

### Ngoài phạm vi:
- Giữ DB connection trong lúc chờ Gemini sinh biến thể.
- Triển khai UI/UX Frontend (đã thống nhất hoãn toàn bộ frontend trong Tuần 3).
- Chỉnh sửa các bảng CSDL không thuộc phạm vi Stage 3 review.

### Hiện đã có:
- Hạ tầng Auth Supabase JWT, `assert_ownership` trong `backend/app/api/dependencies.py` (đã pass CI ở Stage 1 & 2).
- Bảng `exam_sessions`, `exam_versions`, `version_questions` cơ bản.
- Pipeline kiểm định toán học 4 tầng từ Stage 2 (`backend/app/services/validator/`).

---

## File và thứ tự triển khai từ thứ 6 (30/10/2026)

| Lượt / file dự kiến | Mục đích sửa | Output mong muốn | Cần input gì trước | Cách kiểm |
|---|---|---|---|---|
| Lượt 1: `backend/app/models/schemas.py` | Bổ sung Pydantic models cho Review request/response | `ReviewActionResponse`, `RejectQuestionRequest`, `ReviewProgressResponse` | Thống nhất API conventions | `mypy backend/app/models/schemas.py` |
| Lượt 2: `backend/app/services/review/service.py` | Xây dựng logic nghiệp vụ: 2 short transactions, quota guard, stale guard, atomic revert | ReviewService với các hàm `accept_question`, `reject_and_regenerate`, `revert_to_source`, `get_review_progress` | TASK-302 (Schema & Repo từ Hùng), TASK-304 (Mock AI từ Đạt) | Unit test mock DB & AI calls |
| Lượt 3: `backend/app/api/routes/review.py` | Router FastAPI nối các endpoints `/accept`, `/reject`, `/revert`, `/progress` | Bộ 4 endpoints hoạt động theo chuẩn RESTful | Router cấu hình trong `backend/app/main.py` | FastAPI TestClient / pytest |
| Lượt 4: `backend/tests/services/test_review_lifecycle.py` | Viết bộ integration test kiểm thử vòng đời thẩm định | Suite test tự động bao phủ 100% các ca: accept, reject 2-tx, revert, 30 calls quota, stale guard, safe invalidation | DB test environment | `pytest backend/tests/services/test_review_lifecycle.py` |

---

## Đầu vào và câu hỏi — giải đáp trên Draft PR trong thứ 5 (29/10/2026)

| Cần ai/task nào | Câu hỏi/input cụ thể | Cần trước | ETA bên cung cấp xác nhận | Phần làm ngay/chờ | Link trả lời/contract |
|---|---|---|---|---|---|
| Hùng (`benalexx007` / TASK-302) | Migration SQL: cột `canonical_*`, `is_current`, `regenerated_from_id`, `is_reverted`, Partial Unique Index `uq_version_questions_current`, bảng `review_logs`, cột `gemini_review_calls` | Trưa Thứ 6 (30/10) | Trưa Thứ 6 (30/10) | Nháp Router & Schema Pydantic trước, chờ SQL để chạy tích hợp DB | PR TASK-302 |
| Đạt (`Thanhdat3010` / TASK-304) | Pydantic Schema output & Mock hàm `regenerate_question(session_id, question_id, reason)` | Trưa Thứ 6 (30/10) | Trưa Thứ 6 (30/10) | Viết khung 2-transactions với mock data trước, chờ AI engine thật | PR TASK-304 |

- **Output Duy cần giao cho task sau:**
  - Cho Tâm (TASK-303): Toàn bộ câu hỏi biến thể đạt `status = approved`, sẵn sàng để Shuffler đọc dữ liệu `canonical_*` vào sáng Chủ Nhật 01/11.
  - Cho Đạt (TASK-304): `session_id`, `question_id`, `reason` từ body request reject của người dùng.
- **Lịch có khả thi không?** Khả thi. Đã có kế hoạch dùng mock function của Đạt trong Thứ 6 nếu AI engine chưa hoàn tất 100%, bảo đảm không bị nghẽn tiến độ.
- **Quyết định đã thống nhất:** Không giữ DB connection quá 1s trong suốt quá trình người dùng reject; mọi cuộc gọi AI chạy ngoài transaction.

---

## Kế hoạch tự kiểm

1. **Kiểm tra Chấp nhận (Accept):**
   - Gọi `POST .../accept` khi `is_current = true` $\rightarrow$ trả về 200, DB có `status = "approved"`, `review_logs` có bản ghi `ACCEPT`.
   - Gọi `POST .../accept` khi `is_current = false` $\rightarrow$ trả về 400/404 lỗi không hợp lệ.
2. **Kiểm tra Từ chối (Reject) & 2 Transactions:**
   - Gọi `POST .../reject` với lý do cụ thể $\rightarrow$ xác nhận trạng thái câu cũ thành `is_current = false, status = "rejected"`, câu mới có `is_current = true, status = "pending_review"`, `review_logs` có bản ghi `REJECT`.
   - Giả lập tải: Kiểm tra không có DB connection nào bị chiếm dụng trong lúc hàm AI đang ngủ 5 giây.
3. **Kiểm tra Hạn mức Quota Thẩm định (30 calls):**
   - Gọi reject liên tiếp 30 lần $\rightarrow$ lần thứ 31 trả về `HTTP 429 Too Many Requests` (`ERR_REVIEW_QUOTA_EXHAUSTED`).
4. **Kiểm tra Stale Regeneration Guard:**
   - Cố tình chèn 1 câu mang `status = "regenerating"` với `updated_at` cách đây 4 phút $\rightarrow$ gọi `GET .../progress` $\rightarrow$ xác nhận câu tự động được phục hồi về `pending_review` kèm log `REJECT_FAILED`.
5. **Kiểm tra Hoàn nguyên Nguyên tử (Revert):**
   - Gọi `POST .../revert` $\rightarrow$ câu biến thể bị hạ `is_current = false`, bản ghi mới được tạo chép nguyên văn câu gốc với `is_current = true, is_reverted = true, status = "approved"`.
6. **Kiểm tra Vô hiệu hóa Shuffle (Safe Invalidation):**
   - Bật giả lập `exam_versions.is_finalized = true` $\rightarrow$ gọi reject hoặc revert $\rightarrow$ xác minh `is_finalized` bị reset về `false` và session bị hạ về `generated`.

---

## Bàn giao — điền theo kết quả thực tế

- **PR/commit/output:** `feat/duy-task-301-review-lifecycle-api`
- **Đã làm / đã kiểm:** *[Sẽ cập nhật khi bắt đầu code từ Thứ 6]*
- **Đã chấp nhận:** *[Chờ Hùng review và approve]*
- **Còn chờ/bước tiếp:** Chờ Hùng bàn giao SQL Migration và Đạt bàn giao Mock AI vào trưa Thứ 6 30/10.

# Giải Đáp Đầu Vào & Thống Nhất Kỹ Thuật (Q01 – Q05) — TASK-201 / PR #29

- **Dự án:** Isomorphic Exam Synthesizer — Nhóm 04
- **Người trả lời:** Nguyễn Bá Duy (`johannguyen015` — Leader & Backend Lead)
- **Người nhận:** Philip / Trung Anh (`philip-kkk` — FE1 Lead / Tác giả PR #29)
- **Liên kết liên quan:**
  - Pull Request: [#29 `docs(stage1): plan source ingestion and confirmation (TASK-201/203b/204)`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29)
  - Kế hoạch M2: [`docs/tasks/TASK-201.md`](TASK-201.md)
  - Quy trình áp dụng: [WORKFLOW.md](../review/WORKFLOW.md) (v0.1 proposed), [TEMPLATES.md](../review/TEMPLATES.md)
- **Thời điểm giải đáp:** Thứ 5, 29/10/2026

---

## Tóm Tắt Quyết Định Điều Phối (Executive Summary)

1. **Phê duyệt Kế hoạch M2:** Kế hoạch phân chia 3 task (TASK-201, TASK-203b, TASK-204) trong PR #29 được **chấp thuận**. Tác giả được phép bắt đầu triển khai code từ **Thứ 6 (30/10/2026)**.
2. **Tiến độ & Deadline:** Đồng bộ theo nhịp tuần mới; hạn hoàn thành và nghiệm thu toàn bộ cụm Stage 1 là **Tối Thứ 3 tuần sau (03/11/2026)**.
3. **Phân công Review:** Lead Reviewer là Duy (`johannguyen015`); Reviewer phối hợp kiểm tra tích hợp Stage 1 $\rightarrow$ Stage 2 là Bội Anh (`htbaax`).
4. **Hợp đồng kỹ thuật chốt:** 
   - Tuân thủ nghiêm ngặt theo backend đã merge tại PR #16 ([`docs/api/confirm-source-endpoint.md`](../api/confirm-source-endpoint.md)) và PR #15 ([`docs/api/ingestion-endpoints.md`](../api/ingestion-endpoints.md)).
   - Không cần UI checkbox xác nhận an ninh (ADR-004 Silent Security Audit).
   - Sau khi confirm thành công (HTTP 200), điều hướng thẳng sang `/session/:sessionId/stage2` (đã sẵn sàng từ PR #22).

---

## Chi Tiết Giải Đáp Từng Câu Hỏi (Q01 – Q05)

### Q01 — Gate Toàn W1, Phân Công Reviewer & Thời Gian Biểu

| Mục | Nội dung chốt | Căn cứ & Ghi chú |
| :--- | :--- | :--- |
| **Trạng thái Gate W1** | **ĐÃ MỞ (UNBLOCKED)** cho tác vụ Frontend Stage 1. | Nhánh `dev` đã merge toàn bộ các module cốt lõi: Auth (#7), Ingestion BE1 (#15), Confirm Source BE1 (#16), Dashboard & Session (#6, #17), Stage 2 UI (#22). Các PR #19 / #20 còn lại thuộc tầng AI Validation chuyên sâu, không chặn luồng Ingestion/Confirm của FE1. |
| **Reviewer phân công** | **Lead Reviewer:** Duy (`johannguyen015`)<br>**Reviewer phối hợp:** Bội Anh (`htbaax` — FE2 Lead) | Bội Anh hỗ trợ review chéo để đảm bảo tính thông suốt khi bàn giao phiên làm việc từ Stage 1 sang Stage 2. |
| **Kế hoạch thời gian** | - Thứ 6 (30/10): Bắt đầu triển khai code theo lượt 3 (Services & Ingestion State).<br>- Thứ 7 – Chủ Nhật (31/10 – 01/11): Triển khai Error Handling & Confirm UI.<br>- Thứ 2 (02/11): Tự kiểm thử (Unit test, Lint, Build) và mở review M3/M4.<br>- **Hạn chót (DoD): Tối Thứ 3 (03/11/2026)**. | Đồng bộ theo nhịp tuần chính thức tại [WORKFLOW.md](../review/WORKFLOW.md). Hạn cũ 31/10 của W2 được chuyển tiếp thành mốc 03/11 để đội ngũ hoàn thiện chất lượng cao nhất. |

---

### Q02 — Chuẩn Quy Trình Confirm Source, Blueprint Fallback & Schema Tích Hợp

- **Hợp đồng chuẩn áp dụng:** Tài liệu đặc tả kỹ thuật [`docs/api/confirm-source-endpoint.md`](../api/confirm-source-endpoint.md) (đã merge qua PR #16).
- **Cơ chế hoạt động:**
  - Khi người dùng bấm "Xác nhận đề nguồn", FE gửi `POST /api/sessions/{session_id}/confirm-source`.
  - Backend mở 1 PostgreSQL Transaction duy nhất: kiểm tra toàn vẹn câu hỏi, kích hoạt cơ chế `ensure_blueprints_for_session` (tự động tạo Blueprint fallback tất định nếu AI Pipeline nền chưa chạy xong), chuyển trạng thái phiên sang `status = "blueprinted"` và đóng dấu `confirmed_at = now()`.
  - **FE không cần triển khai polling hay đợi AI Blueprint nền.** Toàn bộ quá trình là đồng bộ (atomic transaction).
- **Hợp đồng dữ liệu (API Contract):**
  - **Endpoint:** `POST /api/sessions/{session_id}/confirm-source`
  - **Request Header:** `Authorization: Bearer <token>`, `Content-Type: application/json`
  - **Request Body:** `{}` (hoặc `{"acknowledged_security_warnings": false}` để tương thích ngược).
  - **Phản hồi Thành công (`HTTP 200 OK`):**
    ```json
    {
      "session_id": "11111111-1111-1111-1111-111111111111",
      "status": "blueprinted",
      "confirmed_at": "2026-10-22T04:10:00.000000+00:00",
      "total_questions": 10,
      "total_blueprints": 10,
      "message": "Source confirmed and blueprints locked successfully"
    }
    ```
    *Ý nghĩa:* Nhận `status: "blueprinted"` đồng nghĩa với việc phiên đề đã **AI-ready 100%**, sẵn sàng chuyển sang bước cấu hình Stage 2.
  - **Xung đột trạng thái (`HTTP 409 Conflict`):**
    - Trả về khi phiên không ở trạng thái `draft` (ví dụ: đã được confirm trước đó, hoặc đang trong tiến trình sinh đề `generating`).
    - *Xử lý phía FE:* Không báo lỗi sập màn hình; gọi `GET /api/sessions/{session_id}` lấy trạng thái thực tế và tự động điều hướng sang Stage 2 nếu phiên đã là `blueprinted`.
  - **Lỗi toàn vẹn dữ liệu (`HTTP 422 Unprocessable Entity`):**
    - Trả về khi phiên có 0 câu hỏi hoặc có câu hỏi thiếu đáp án (`has_missing_answer == true`).
    - Định dạng: `{"detail": "Cannot confirm source: Session contains no questions"}` hoặc `{"detail": "Cannot confirm source: X question(s) have missing answer keys"}`.
    - *Xử lý phía FE:* Giữ nguyên màn hình preview, hiển thị thông báo/dialog lỗi chỉ rõ câu thiếu đáp án để người dùng chỉnh sửa hoặc nạp lại file.

---

### Q03 — Chính Sách An Ninh & UI Badge / Acknowledgment (ADR-004)

- **Quyết định:** **Tuân thủ triệt để theo [ADR-004 / SEC-02 Silent Security Audit](../change_log.md#adr-004--sec-02-silent-security-audit) và Backend Contract hiện hành.**
- **Yêu cầu cụ thể cho FE1 (TASK-204):**
  - **KHÔNG** làm checkbox hoặc dialog bắt người dùng click xác nhận/acknowledge các cảnh báo an ninh.
  - Backend đã tự động kiểm tra và ghi nhận ngầm các vi phạm vào bảng `public.security_events`.
  - Trường `acknowledged_security_warnings` trong request body đã bị deprecated và backend bỏ qua (ignored).
  - Nút **"Xác nhận đề nguồn"** chỉ bị khóa (disabled) khi:
    1. Chưa có câu hỏi nào được nạp thành công.
    2. Có câu hỏi bị thiếu phương án/đáp án đúng (`has_missing_answer == true`).
    3. Đang trong quá trình gửi request (`isSubmitting == true`).
  - *Gợi ý UI:* Nếu câu hỏi có cờ cảnh báo an ninh (`has_security_warning == true`), có thể hiển thị một icon / badge thông tin nhỏ dạng tooltip (nếu cần), nhưng tuyệt đối không chặn luồng người dùng.

---

### Q04 — Khớp Nối Điều Hướng & Sẵn Sàng Sang Stage 2 (FE2 Handoff)

- **Tuyến đường chuẩn:** `/session/:sessionId/stage2` (đã được cấu hình trong `App.jsx` và bao bọc bởi `ProtectedRoute`).
- **Luồng chuyển giao:**
  - Sau khi `confirm-source` trả về HTTP 200, FE1 thực hiện điều hướng:
    ```javascript
    navigate(`/session/${sessionId}/stage2`);
    ```
- **Xác thực dữ liệu sẵn sàng (Readiness Contract):**
  - Màn hình `Stage2ConfigPage` khi mount sẽ gọi `fetchSessionDetail(sessionId)` (từ [`frontend/src/services/stage2Service.js`](../../frontend/src/services/stage2Service.js)).
  - Trong `stage2Service.js` (dòng 44–51), hệ thống kiểm tra: nếu `source_questions` có đầy đủ `question_blueprints` tương ứng với số lượng câu hỏi, cờ `blueprintSummary.is_ready` sẽ tự động mang giá trị `true`.
  - Vì endpoint `confirm-source` đã đảm bảo tạo đủ blueprint cho 100% câu hỏi nguồn, `Stage2ConfigPage` sẽ hiển thị ngay lập tức thẻ cấu hình `Stage2ConfigCard` mà không gặp bất kỳ xung đột dữ liệu hay tình trạng thiếu trường nào.

---

### Q05 — Môi Trường Kiểm Thử, Database Migrations & Tài Khoản Test

| Thành phần | Thông tin chi tiết & Hướng dẫn |
| :--- | :--- |
| **Database & Migrations** | - Toàn bộ cấu trúc CSDL chuẩn được duy trì tại [`backend/scripts/schema.sql`](../../backend/scripts/schema.sql).<br>- Migration 002 ([`backend/migrations/002_replace_source_questions_rpc.sql`](../../backend/migrations/002_replace_source_questions_rpc.sql)) đã cung cấp RPC `replace_source_questions` với đầy đủ quyền thực thi cho vai trò `authenticated`.<br>- Supabase Storage bucket `exam-source-files` đã được cấu hình cơ chế fallback an toàn (nếu môi trường test chưa gắn bucket thì lưu trữ vẫn không gián đoạn luồng bóc tách). |
| **Môi trường Test cho FE** | - Tác giả có thể chạy backend local trực tiếp qua lệnh:<br>  `cd backend && poetry run uvicorn app.main:app --reload`<br>  hoặc sử dụng `docker-compose.dev.yml`.<br>- Frontend kết nối backend qua cấu hình proxy của Vite hoặc biến môi trường `VITE_API_BASE_URL=http://localhost:8000`. |
| **Xác thực (JWT)** | Đăng nhập tài khoản kiểm thử thông qua giao diện Google Login (PR #7) hoặc sử dụng tính năng tạo người dùng trực tiếp trên local Supabase. Mọi API Ingestion và Confirm đều yêu cầu header `Authorization: Bearer <token>`. |
| **Dữ liệu mẫu (Fixtures) cho Unit Test** | - Tham khảo trực tiếp bộ 400+ ca kiểm thử trong [`backend/tests/test_parsers.py`](../../backend/tests/test_parsers.py) và [`backend/tests/api/test_ingest.py`](../../backend/tests/api/test_ingest.py).<br>- Đảm bảo FE kiểm thử đủ các ca: file `.docx`, `.tex`, `.md`, raw text; lỗi `422` kèm danh sách `ParserErrorItem`; lỗi `400` quá dung lượng 10MB; lỗi `409` khi phiên đã confirm. |

---

## Kết Luận & Hành Động Tiếp Theo

1. Bạn (`philip-kkk`) cập nhật trạng thái bảng câu hỏi Q01–Q05 trong [`docs/tasks/TASK-201.md`](TASK-201.md) thành **Đã giải đáp (Resolved)** và dẫn link tới văn bản này.
2. Tiến hành triển khai code Lượt 3 từ Thứ 6 (30/10/2026) theo đúng kế hoạch.
3. Nếu phát sinh vấn đề phát sinh trong quá trình code, tiếp tục trao đổi trực tiếp trên Conversation của PR [#29](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29).


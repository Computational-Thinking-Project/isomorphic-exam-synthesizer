# TASK-303 — Plan và Bàn Giao: Thuật Toán Hoán Vị Xác Định Fisher-Yates & Đồng Bộ Lời Giải Chi Tiết

- Nguồn giao việc: [docs/tasks/W3_ASSIGNMENT.md](W3_ASSIGNMENT.md) (v2.1; 28/10/2026).
- Phụ trách: Tâm (`@AI-WFox`); Reviewer: Duy (`@johannguyen015` — đề xuất).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `feat/tam-task-303-fisher-yates-shuffler`; PR: <sẽ điền link khi tạo Draft PR>.
- Hạn đợt: Tối thứ 3 03/11/2026; ETA task: Chủ Nhật 01/11/2026 (bàn giao trước sáng thứ 2 02/11/2026 để Duy làm TASK-305).

## Mình cần làm gì?

- Hành vi/tiêu chí đạt:
  - Xây dựng service xáo trộn xác định `backend/app/services/shuffler/service.py` dựa trên thuật toán Fisher-Yates shuffle.
  - Sinh seed ngẫu nhiên xác định cho từng mã đề: `seed = hash(session_id + str(version_index))`. Cùng seed và cùng dữ liệu gốc phải luôn luôn tạo ra cùng một kết quả xáo trộn bất biến.
  - **Bảo vệ tính toàn vẹn Canonical (Canonical Invariant):**
    - Mọi lượt shuffle luôn đọc từ các trường dữ liệu chuẩn `canonical_question_no`, `canonical_options`, `canonical_correct_key`, `canonical_solution_md` của các câu hỏi mang cờ `is_current = true`.
    - Tuyệt đối không bao giờ shuffle đè lên dữ liệu đã bị xáo trộn ở các lượt trước.
  - **Cơ chế hoán vị linh hoạt theo cấu hình `ordering_preferences`:**
    - Nếu `shuffle_questions == true`: Đảo thứ tự câu hỏi và gán lại số thứ tự hiển thị `display_no` (1..M).
    - Nếu `shuffle_options == true`: Hoán vị ngẫu nhiên thứ tự 4 đáp án A/B/C/D, xác định chữ cái đáp án đúng mới (`display_correct_key`), và cập nhật danh sách `options`.
  - **Đồng bộ lời giải chi tiết (`solution_md`):**
    - Phân tích và tự động thay thế các chỉ dẫn đáp án cũ (ví dụ: "Chọn A", "Đáp án đúng là A", "Phương án đúng: A") bằng chữ cái đáp án đúng mới tương ứng sau khi hoán vị.
  - **Ghi nhận CSDL & Đồng bộ Bảng `answer_keys`:**
    - Lưu ma trận hoán vị vào cột `exam_versions.permutations` (JSONB) và `exam_versions.shuffle_seed`.
    - Ghi mới toàn bộ bản ghi đối soát vào bảng `answer_keys` (`version_id`, `display_no`, `display_correct_key`, `canonical_question_no`).
    - Đánh dấu `exam_versions.is_finalized = true`.
  - **API Endpoint:** Triển khai endpoint `POST /api/sessions/{session_id}/finalize/shuffle`:
    - Gọi `assert_ownership`.
    - Kiểm tra điều kiện tiên quyết: phiên làm việc phải ở trạng thái `reviewed` (100% câu hỏi hiện hành đã đạt `approved`).
- Ngoài phạm vi:
  - Không phê duyệt phiên hoặc kích hoạt khóa `HTTP 423 Locked` (thuộc phạm vi TASK-305 của Duy).
  - Không sinh lại biến thể câu hỏi (thuộc phạm vi TASK-304 của Đạt).
- Cần input từ ai/task nào:
  - Dữ liệu `canonical_*` và migration schema từ Hùng (`TASK-302`).
  - Trạng thái 100% câu approved từ Duy (`TASK-301`).
- Output giao cho ai/task nào:
  - Bàn giao API `POST /finalize/shuffle` và bảng ma trận `answer_keys` cho Duy (`TASK-305`) trước sáng thứ 2 02/11/2026.

## File dự kiến sửa hoặc thêm

| File | Mục đích | Output chính | Cách kiểm tự động hoặc thủ công |
|---|---|---|---|
| `backend/app/services/shuffler/__init__.py` | Module package init | Service exports | Import check |
| `backend/app/services/shuffler/schemas.py` | Pydantic schemas cho Shuffler | Input/Output contract models | Schema validation tests |
| `backend/app/services/shuffler/service.py` | Thuật toán Fisher-Yates, sync solution_md | Logic hoán vị xác định | Unit tests |
| `backend/app/api/routes/finalize.py` | Route API POST /finalize/shuffle | Endpoint tích hợp | Integration tests |
| `backend/tests/shuffler/test_shuffler.py` | Kiểm thử toàn diện thuật toán và đồng bộ | Bộ test suite deterministic shuffle | `pytest backend/tests/shuffler/` |
| `docs/tasks/TASK-303.md` | Tài liệu kế hoạch và bàn giao task | Plan chuẩn hóa M2 | Đọc và rà soát tài liệu |

## Tự kiểm và giới hạn

- [ ] Lệnh kiểm thuật toán shuffler: `pytest backend/tests/shuffler/ -v`
- [ ] Lệnh kiểm API finalize: `pytest backend/tests/api/test_finalize.py -v`
- [ ] Lệnh kiểm linter: `ruff check backend/app/services/shuffler/ backend/tests/shuffler/`
- [ ] Lệnh kiểm format: `ruff format --check backend/app/services/shuffler/ backend/tests/shuffler/`
- Giới hạn: Trong giai đoạn chờ Hùng hoàn tất migration `TASK-302` vào chiều thứ 6, core shuffler service được xây dựng và kiểm thử độc lập với in-memory fixture / mock repository.

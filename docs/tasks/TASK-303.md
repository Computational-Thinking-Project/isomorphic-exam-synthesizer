# TASK-303 — Plan và bàn giao

- Nguồn giao việc: [docs/planning.md#task-303](../planning.md) (commit 506384b; 28/10/2026).
- Phụ trách: Tâm (`@AI-WFox`); reviewer: Duy (`@johannguyen015` — đề xuất).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `feat/tam-task-303-fisher-yates-shuffler`; PR: [#24](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/24).
- Hạn đạt: tối thứ 3 03/11/2026; ETA task: Chủ Nhật 01/11/2026 (Tâm tự xác nhận, bàn giao trước sáng thứ 2 02/11/2026 cho Duy làm TASK-305).

## Mình cần làm gì?

- Hành vi/tiêu chí đạt:
  - Xây dựng service xáo trộn xác định `backend/app/services/shuffler/service.py` dựa trên thuật toán Fisher-Yates shuffle.
  - Sinh seed ngẫu nhiên xác định cho từng mã đề: `seed = hash(session_id + str(version_index))`. Cùng seed và cùng dữ liệu gốc luôn tạo ra cùng một kết quả xáo trộn bất biến.
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
  - Phê duyệt phiên hoặc kích hoạt khóa `HTTP 423 Locked` (thuộc TASK-305 của Duy).
  - Sinh lại biến thể câu hỏi (thuộc TASK-304 của Đạt).
- Hiện đã có:
  - Cấu trúc cơ sở dữ liệu và bảng `exam_versions`, `version_questions`, `answer_keys` trong migrations ban đầu (`backend/migrations/`).
  - Đã kiểm: Xác thực quyền sở hữu `assert_ownership` trong `backend/app/services/session.py`.

## File và thứ tự triển khai từ thứ 6

| Lượt / file dự kiến | Mục đích sửa | Output mong muốn | Cần input gì trước | Cách kiểm |
|---|---|---|---|---|
| 1. `backend/app/services/shuffler/__init__.py` | Module package init | Service exports | Không có | Import check |
| 2. `backend/app/services/shuffler/schemas.py` | Pydantic schemas cho Shuffler | Input/Output contract models | Không có | Schema validation tests |
| 3. `backend/app/services/shuffler/service.py` | Thuật toán Fisher-Yates, sync solution_md | Logic hoán vị xác định | Task 302 (hoặc mock) | Unit tests in-memory |
| 4. `backend/app/api/routes/finalize.py` | Route API POST /finalize/shuffle | Endpoint tích hợp | Service shuffler | Integration tests |
| 5. `backend/tests/shuffler/test_shuffler.py` | Kiểm thử toàn diện thuật toán và đồng bộ | Bộ test suite deterministic shuffle | Không có | `pytest backend/tests/shuffler/` |
| 6. `docs/tasks/TASK-303.md` | Cập nhật tài liệu và tiến độ task | Plan chuẩn hóa M2 | Không có | Manual check |

## Đầu vào và câu hỏi – giải đáp trên Draft PR trong thứ 5

| Cần ai/task nào | Câu hỏi/input cụ thể | Cần trước | ETA bên cung cấp xác nhận | Phần làm ngay/chờ | Link trả lời/contract |
|---|---|---|---|---|---|
| Hùng (`@benalexx007` - TASK-302) | Cấu trúc JSONB cụ thể của `canonical_options` là list các chuỗi `["A...", "B..."]` hay object `{"A": "...", ...}`? | Sáng thứ 6 30/10 | Chiều thứ 5 29/10 | Resolved | [docs/tasks/TASK-303_ANSWERS.md](TASK-303_ANSWERS.md) (Mảng 4 chuỗi `["A...", "B...", "C...", "D..."]` theo `generation.py#L37`) |
| Duy (`@johannguyen015` - TASK-305) | Response của `POST /finalize/shuffle` trả về permutation list hay object map theo question_id? | Sáng thứ 6 30/10 | Chiều thứ 5 29/10 | Resolved | [docs/tasks/TASK-303_ANSWERS.md](TASK-303_ANSWERS.md) (Metadata version theo `w3.md#L316`; ma trận lưu DB `answer_keys`) |

- Output mình cần giao cho task sau: Bàn giao API `POST /finalize/shuffle`, service xáo trộn và bảng `answer_keys` cho Duy (`TASK-305`) trước sáng thứ 2 02/11/2026.
- Lịch có khả thi không? Hoàn toàn khả thi vì logic Fisher-Yates thuần thuật toán toán học và test in-memory có thể triển khai độc lập trước khi DB migration hoàn tất.
- Quyết định đã thống nhất: Canonical Invariant là bắt buộc, không được mutate in-place dữ liệu `canonical_*`.

## Kế hoạch tự kiểm

- Tình huống thành công:
  - Shuffle cùng một seed ra cùng kết quả 100%.
  - Shuffle nhiều lần trên cùng dữ liệu không làm mất dữ liệu canonical gốc.
  - `solution_md` được cập nhật chính xác nhãn đáp án mới.
- Tình huống lỗi:
  - Phiên chưa `reviewed` (chưa đủ 100% approved) bị chặn với HTTP 400 Bad Request.
  - User không phải chủ sở hữu bị chặn với HTTP 403 Forbidden.
- Môi trường: Pytest local, in-memory fixtures. Chưa thể kiểm với DB thật cho tới khi migration hoàn tất.

## Bàn giao – điền theo kết quả thực tế

- PR/commit/output: PR [#24](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/24) (Draft plan-only).
- Đã làm / đã kiểm: Kế hoạch triển khai Template M2, câu hỏi contract cho Hùng và Duy.
- Đã chấp nhận: Chờ review từ Duy (`@johannguyen015`).
- Còn chờ/bước tiếp: Phản hồi từ Hùng và Duy trên PR #24; bắt đầu triển khai code và unit test từ thứ 6.

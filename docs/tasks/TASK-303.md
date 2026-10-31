# TASK-303 — Plan và bàn giao

- Nguồn giao việc: [docs/planning.md#task-303](../planning.md) (commit 506384b; 28/10/2026).
- Phụ trách: Tâm (`@AI-WFox`); reviewer: Duy (`@johannguyen015` — đề xuất).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `feat/tam-task-303-fisher-yates-shuffler`; PR: [#24](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/24).
- Hạn đạt: tối thứ 3 03/11/2026; ETA task: Hoàn thành phần Core Service Shuffler (sẵn sàng bàn giao cho Duy tích hợp TASK-305).

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

## Kế hoạch tự kiểm và kết quả thực tế

- [x] Lệnh kiểm: `pytest backend/tests/shuffler/test_shuffler.py -v`
- [x] Kết quả: 23/23 passed (100% green trong 0.20s).
- [x] Lệnh kiểm linter: `ruff check backend/app/services/shuffler/ backend/tests/shuffler/`
- [x] Kết quả: All checks passed.
- [x] Lệnh kiểm format: `ruff format --check backend/app/services/shuffler/ backend/tests/shuffler/`
- [x] Kết quả: 4 files already formatted.
- [x] Lệnh kiểm typecheck: `mypy backend/app/services/shuffler/ --ignore-missing-imports`
- [x] Kết quả: Success: no issues found in 3 source files.

Tình huống đã kiểm thử:
- [x] Tính xác định (Deterministic Idempotence): Cùng seed luôn tạo ra thứ tự câu hỏi và hoán vị đáp án bất biến 100%. Các phiên bản khác nhau có seed khác nhau.
- [x] Bảo vệ dữ liệu gốc (Canonical Invariant): Đọc trực tiếp từ `canonical_*`, không mutate in-place dữ liệu đầu vào.
- [x] Đồng bộ nhãn đáp án giải thích (`solution_md`): Tự động đồng bộ các mẫu chỉ dẫn tiếng Việt ("Đáp án A:", "Chọn A", "Phương án đúng: A", v.v.) sang nhãn mới, bảo toàn biến số toán học và hình học (tam giác ABC, đỉnh A).
- [x] Tạo đầy đủ bản ghi `answer_keys` và ma trận `permutations` (JSONB) cho database.
- [x] Payload phản hồi phiên bản khớp 100% chuẩn hợp đồng `w3.md#L316`.

## Bàn giao – điền theo kết quả thực tế

- PR/commit/output: PR [#24](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/24).
- Đã làm / đã kiểm:
  - Triển khai `backend/app/services/shuffler/schemas.py`: Pydantic models cho OrderingPreferences, CanonicalQuestionInput, ShuffledQuestionOutput, AnswerKeyRecord, VersionShuffleResult, FinalizeShuffleResponse.
  - Triển khai `backend/app/services/shuffler/service.py`: Thuật toán Fisher-Yates, sinh seed xác định SHA-256, đồng bộ solution text regex tiếng Việt, tạo ma trận hoán vị và bản ghi answer_keys.
  - Triển khai `backend/tests/shuffler/test_shuffler.py`: 23 test cases bao phủ toàn bộ chức năng, tính xác định, bất biến canonical, và edge cases.
- Đã chấp nhận: Sẵn sàng để Duy (`@johannguyen015`) kết nối endpoint `POST /api/sessions/{session_id}/finalize/shuffle` trong TASK-305.
- Còn chờ/bước tiếp: Duy review PR #24 và tích hợp endpoint.
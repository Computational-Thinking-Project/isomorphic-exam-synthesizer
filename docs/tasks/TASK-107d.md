# TASK-107d — Plan và Bàn Giao: Validation Aggregator & ValidationReport Schema (VAL-05)

- Nguồn giao việc: Stage 2 Planning — VAL-05 Specification.
- Phụ trách: Tâm (`@AI-WFox`); Reviewer: Philip (`@philip-kkk` — đề xuất).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `feat/task-107d-validation-aggregator`; PR: [#20](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/20).
- Hạn đợt: Tối thứ 3; ETA task: Hoàn thành và sẵn sàng merge.

## Mình cần làm gì?

- Hành vi/tiêu chí đạt:
  - Cung cấp schema báo cáo hợp nhất `ValidationReport` chuẩn hóa kết quả kiểm định (`status`: `passed`, `warning`, `failed`; `confidence`: `sympy_verified`, `rule_only`; `checks`: danh sách `CheckResult`; `errors`, `warnings`, `execution_time_ms`), hỗ trợ serialize đầy đủ qua `.to_dict()`.
  - Bộ điều phối trung tâm `validate_question`: phối hợp tuần tự 4 tầng kiểm định:
    - **Stage 1 (Cú pháp - VAL-01):** Thân câu hỏi không rỗng, đúng 4 lựa chọn không rỗng, dấu ngoặc toán học LaTeX cân bằng.
    - **Stage 2 (Logic - VAL-02):** Đáp án đúng tồn tại và khớp phương án, chống trùng lặp phương án (so khớp chuỗi và rút gọn đại số CAS).
    - **Stage 3 (Hình thức CAS - VAL-03):** Xác thực nghiệm đại số bằng SymPy trong tiến trình cô lập với timeout 5 giây. Tự động bypass CAS khi gặp các miền toán ngoài phạm vi (hình học, xác suất/tổ hợp, toán đố, giải tích, số phức, ma trận) để tránh cạn kiệt tài nguyên / timeout giả.
    - **Stage 4 (Luật & Bất biến - VAL-04):** Thẩm định giới hạn tham số Blueprint, bất biến toán học (mẫu số, căn bậc chẵn, logarit, biệt thức, xác suất, tam giác) và phương án nhiễu.
  - Hỗ trợ giải mã nhãn đáp án linh hoạt (`_resolve_option_letter`): nhận diện chuẩn xác các nhãn `A`, `A.`, `Option A`, `(A)`, `Phương án A`, `Đáp án A` và chuyển đổi sang nội dung văn bản phương án trước khi kiểm CAS và kiểm luật.
  - Wrapper tiện ích `validate_variant`: hỗ trợ linh hoạt các kiểu đầu vào `GeneratedVariant`, `SourceQuestion`, hoặc dictionary duck-typed.
  - Hỗ trợ chế độ Fail-Fast (`fail_fast=True`) dừng sớm khi gặp lỗi cú pháp/logic; chế độ Degraded Mode (`treat_fallback_as_warning=True`) đánh dấu warning khi pass qua rule fallback.
- Ngoài phạm vi:
  - Không can thiệp vào logic sinh đề hoặc giao diện người dùng.
- Cần input từ ai/task nào:
  - Syntax Checker (TASK-107a), Logic Checker (TASK-107b), CAS SymPy Evaluator (VAL-03), Rule Fallback Checker (TASK-107c).
- Output giao cho ai/task nào:
  - Cung cấp module `aggregator.py` và schema `ValidationReport` cho toàn bộ Stage 2 Generator pipeline và Review Engine.

## File dự kiến sửa hoặc thêm

| File | Mục đích | Output chính | Cách kiểm tự động hoặc thủ công |
|---|---|---|---|
| `backend/app/services/validator/base.py` | Định nghĩa schema `ValidationReport` | Schema chuẩn hóa và serializable | `pytest backend/tests/validation/test_aggregator.py` |
| `backend/app/services/validator/aggregator.py` | Triển khai điều phối viên 4 tầng `validate_question` | Pipeline thẩm định hợp nhất | `pytest backend/tests/validation/test_aggregator.py` |
| `backend/app/services/validator/__init__.py` | Export các service và schema chính | Module interface | `pytest backend/tests/validation/` |
| `backend/app/models/schemas.py` | Re-export `ValidationReport` | Pydantic schema consistency | `pytest backend/tests/validation/` |
| `backend/tests/validation/test_aggregator.py` | Unit và integration test cho toàn bộ aggregator | 32 test cases kiểm tra kịch bản đa tầng và edge cases | `pytest backend/tests/validation/test_aggregator.py -v` |
| `docs/tasks/TASK-107d.md` | Kế hoạch và bàn giao theo chuẩn Workflow M2 | Plan chuẩn hóa | Đọc và rà soát tài liệu |

## Tự kiểm và giới hạn

- [x] Lệnh kiểm: `pytest backend/tests/validation/test_aggregator.py -v`
- [x] Kết quả: 32/32 passed (100% green).
- [x] Lệnh kiểm toàn bộ validation suite: `pytest backend/tests/validation/ -v`
- [x] Kết quả: 198/198 passed (100% green).
- [x] Lệnh kiểm linter: `ruff check backend/app/services/validator/ backend/tests/validation/`
- [x] Kết quả: All checks passed.
- [x] Lệnh kiểm format: `ruff format --check backend/app/services/validator/ backend/tests/validation/`
- [x] Kết quả: All files formatted.
- Giới hạn: Khi CAS gặp lỗi hệ thống worker process (ví dụ OSError), hệ thống bảo toàn các lỗi sai nghiệm đã phát hiện và không bao giờ ghi đè kết quả thất bại thành pass.

# TASK-107c — Plan và Bàn Giao: Rule-Based Fallback Checker (VAL-04)

- Nguồn giao việc: Stage 2 Planning — VAL-04 Specification.
- Phụ trách: Tâm (`@AI-WFox`); Reviewer: Philip (`@philip-kkk` — đã chốt).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `feat/task-107c-rule-fallback`; PR: [#19](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/19).
- Hạn đợt: Tối thứ 3; ETA task: Hoàn thành và sẵn sàng merge.

## Mình cần làm gì?

- Hành vi/tiêu chí đạt:
  - Cung cấp bộ thẩm định độc lập theo luật toán học và định tuyến dự phòng khi CAS SymPy không hỗ trợ hoặc timeout.
  - Thẩm định giới hạn tham số (`check_parameter_bounds`, `extract_parameter_domains`) theo Science Blueprint Schema Draft 2020-12 và flat format, không làm rơi cận 0 hoặc xung đột kiểu số.
  - Thẩm định bất biến toán học cốt lõi (`check_mathematical_invariants`): mẫu số khác 0 (phân số LaTeX và plain), biểu thức dưới căn bậc chẵn không âm trong miền thực, miền xác định logarit (cơ số > 0, != 1, đối số > 0), biệt thức delta bậc hai, xác suất trực tiếp [0, 1], bất đẳng thức tam giác.
  - Hỗ trợ phân tích cú pháp LaTeX lồng nhau (`_extract_balanced_braces`, `_extract_latex_fractions`, `_extract_latex_sqrts`, `_extract_latex_logs`, `_extract_latex_lns`, `_latex_to_python_numeric`) để không bỏ sót các macro lồng nhau.
  - Bộ tính toán số học an toàn AST (`SafeNumericEvaluator`, `safe_eval_numeric_expr`): sử dụng số học phân số chính xác `fractions.Fraction` thay cho float/round để triệt tiêu sai số làm tròn phân số tuần hoàn, tích hợp thuật toán tìm căn nguyên chính xác `_exact_integer_nth_root` cho số mũ hữu tỉ và fallback sang `Decimal(prec=50)` không kẹp mẫu số `limit_denominator`.
  - Kiểm tra tính hợp lý của phương án nhiễu (`check_distractor_reasonableness`): đúng 4 phương án, không trùng lặp, không rỗng/thoái hóa, hỗ trợ linh hoạt các định dạng nhãn (`A`, `A.`, `Option A`, `(A)`, `Phương án A`, `Đáp án A`).
  - Nhận diện toán ngoài phạm vi CAS (`detect_out_of_scope_math`): hình học, toán đố, tổ hợp/xác suất, giải tích, số phức, ma trận/đại số tuyến tính.
  - Định tuyến dự phòng tự động (`evaluate_rule_fallback`, `validate_rule_variant`): bảo toàn kết luận bác bỏ quyết định từ CAS (`FAILED`, `DOMAIN_ERROR`), chỉ chuyển sang `passed_rule_fallback` với `confidence="rule_only"` khi CAS trả về `TIMEOUT` hoặc `UNSUPPORTED`.
- Ngoài phạm vi:
  - Không thay thế CAS SymPy cho các phương trình đại số phức tạp cần giải nghiệm hình thức.
  - Không sửa đổi mã nguồn các bảng CSDL hoặc API routing ngoài phạm vi validation.
- Cần input từ ai/task nào:
  - Blueprint schema và logic equivalence từ TASK-107a / TASK-107b.
- Output giao cho ai/task nào:
  - Cung cấp module `rule_checker.py` độc lập cho Validation Aggregator (`TASK-107d` của Tâm) và pipeline sinh đề.

## File dự kiến sửa hoặc thêm

| File | Mục đích | Output chính | Cách kiểm tự động hoặc thủ công |
|---|---|---|---|
| `backend/app/services/validator/rule_checker.py` | Triển khai Rule-Based Fallback Checker | Các hàm kiểm tra độc lập và bộ điều phối fallback | `pytest backend/tests/validation/test_rule_checker.py` |
| `backend/tests/validation/test_rule_checker.py` | Unit tests toàn diện và regression tests | 74 test cases bao phủ toàn bộ chức năng và edge cases | `pytest backend/tests/validation/ -v` |
| `docs/tasks/TASK-107c.md` | Tài liệu kế hoạch và bàn giao task theo chuẩn Workflow M2 | Plan chuẩn hóa | Đọc và rà soát tài liệu |

## Tự kiểm và giới hạn

- [x] Lệnh kiểm: `pytest backend/tests/validation/test_rule_checker.py -v`
- [x] Kết quả: 74/74 passed (100% green).
- [x] Lệnh kiểm linter: `ruff check backend/app/services/validator/rule_checker.py backend/tests/validation/test_rule_checker.py`
- [x] Kết quả: All checks passed.
- [x] Lệnh kiểm format: `ruff format --check backend/app/services/validator/rule_checker.py backend/tests/validation/test_rule_checker.py`
- [x] Kết quả: 2 files already formatted.
- [x] Lệnh kiểm toàn bộ suite validation: `pytest backend/tests/validation/ -v`
- [x] Kết quả: 166/166 passed.
- Giới hạn: Biểu thức chứa các hàm số lượng giác thuần túy hoặc số vô tỉ siêu việt ($e, \pi$) mà không có CAS hỗ trợ sẽ được đánh giá qua xấp xỉ số học hoặc phân loại ngoài phạm vi.

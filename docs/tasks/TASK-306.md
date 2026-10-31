# TASK-306 — Plan và bàn giao

- Nguồn giao việc: [docs/planning.md#task-306a](../planning.md) (commit 506384b; 28/10/2026).
- Phụ trách: Tâm (`@AI-WFox`); reviewer: Duy (`@johannguyen015` — đề xuất) / Đạt (`@dat-001` — cross-review).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `feat/tam-task-306-typst-compiler-engine`; PR: [#25](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/25).
- Hạn đạt: tối thứ 3 03/11/2026; ETA task: Thứ 2 02/11/2026 (Tâm tự xác nhận, bàn giao trước thứ 3 03/11/2026 cho TASK-307 Export Center).

## Mình cần làm gì?

- Hành vi/tiêu chí đạt:
  - **Typst Compiler Service (`backend/app/services/exporter/typst_compiler.py`):**
    - Thiết kế runner gọi binary Typst CLI (`typst compile input.typ output.pdf`) an toàn.
    - Bảo mật subprocess: gọi với `shell=False`, giới hạn timeout tối đa 30s.
    - Cô lập môi trường biên dịch trong thư mục tạm (`tempfile.TemporaryDirectory()`).
    - Kiểm tra Magic Bytes `%PDF-` ở 4 bytes đầu tiên của file output để xác thực file PDF hợp lệ.
    - Xử lý lỗi compilation chặt chẽ: bắt stdout/stderr từ Typst, làm sạch toàn bộ đường dẫn tuyệt đối của hệ điều hành, map sang `TypstCompilationError` và `TypstTimeoutError`.
  - **Typst Template System:**
    - Template Đề thi chuẩn A4 (`backend/app/services/exporter/templates/exam.typ`):
      - Tiêu đề kỳ thi, trường/bộ môn, tên bài thi, mã đề thi.
      - Khung điền thông tin thí sinh (Họ và tên, Số báo danh, Lớp, Phòng thi).
      - Bố cục câu hỏi trắc nghiệm tiếng Việt chuẩn mực, hỗ trợ căn lề 4 phương án A/B/C/D đẹp mắt.
      - Render mượt mà công thức toán học Typst.
    - Template Bảng đáp án & Lời giải (`backend/app/services/exporter/templates/solution.typ`):
      - Ma trận đáp án trắc nghiệm trực quan dạng Grid (Bảng tra cứu nhanh: Câu - Đáp án).
      - Lời giải chi tiết từng bước cho từng câu hỏi dựa trên `canonical_solution_md`.
  - **Typst Content Converter (`backend/app/services/exporter/typst_converter.py`):**
    - Chuyển đổi an toàn từ LaTeX math markdown sang cú pháp công thức Typst ($...$).
    - Thoát các ký tự đặc biệt trong văn bản Typst (`#`, `@`, `_`, `*`, `$`).
  - **Unit & Integration Test Suite (`backend/tests/exporter/test_typst_compiler.py`):**
    - Kiểm thử mock subprocess cho CI không có Typst binary.
    - Kiểm thử biên dịch thực tế khi có Typst CLI khả dụng trên PATH.
- Ngoài phạm vi:
  - Không xây dựng UI Export Center (thuộc TASK-307 của Đạt/FE).
  - Không thực hiện đóng gói ZIP hoặc XeLaTeX/Markdown Bundler (thuộc TASK-306b).
  - Không phê duyệt phiên hoặc kích hoạt khóa `HTTP 423 Locked` (thuộc TASK-305 của Duy).
- Hiện đã có:
  - Cấu hình backend, database, và endpoint conventions trong `docs/api/endpoint-conventions.md`.
  - Quy chuẩn bảo mật subprocess và timeout đã áp dụng ở `backend/app/services/validator/process_runner.py`.

## File và thứ tự triển khai từ thứ 6

| Lượt / file dự kiến | Mục đích sửa | Output mong muốn | Cần input gì trước | Cách kiểm |
|---|---|---|---|---|
| 1. `backend/app/services/exporter/__init__.py` | Module package init | Service exports | Không có | Import check |
| 2. `backend/app/services/exporter/exceptions.py` | Định nghĩa các custom exceptions | `TypstCompilationError`, `TypstTimeoutError` | Không có | Unit tests |
| 3. `backend/app/services/exporter/typst_converter.py` | Chuyển đổi Markdown/LaTeX sang Typst | Hàm convert math & text format | Không có | Unit tests |
| 4. `backend/app/services/exporter/templates/exam.typ` | Typst template đề thi | File template A4 tiếng Việt | Không có | Render test |
| 5. `backend/app/services/exporter/templates/solution.typ` | Typst template bảng đáp án + lời giải | File template grid + giải thích | Không có | Render test |
| 6. `backend/app/services/exporter/typst_compiler.py` | Subprocess compilation runner | Service biên dịch an toàn sinh PDF | Typst CLI | Unit & Mock tests |
| 7. `backend/tests/exporter/test_typst_compiler.py` | Test suite cho exporter | Mock test & compilation validation | Exporter service | `pytest backend/tests/exporter/` |
| 8. `docs/tasks/TASK-306.md` | Tài liệu kế hoạch và bàn giao task | Plan chuẩn hóa M2 | Không có | Manual check |

## Đầu vào và câu hỏi – giải đáp trên Draft PR trong thứ 5

| Cần ai/task nào | Câu hỏi/input cụ thể | Cần trước | ETA bên cung cấp xác nhận | Phần làm ngay/chờ | Link trả lời/contract |
|---|---|---|---|---|---|
| Duy (`@johannguyen015` - Leader & Docker setup) | Môi trường Docker dev/staging đã cài đặt sẵn binary Typst CLI chưa, hay cần bổ sung Typst vào `Dockerfile`? | Sáng thứ 6 30/10 | Chiều thứ 5 29/10 | Resolved | [docs/tasks/TASK-306_ANSWERS.md](TASK-306_ANSWERS.md) (Typst v0.11.1 đã cài tại `/usr/local/bin/typst`) |
| Đạt (`@dat-001` - TASK-307) | Định dạng tên file PDF xuất bản mong muốn là gì (ví dụ: `De_thi_{session_id}_{version_code}.pdf`)? | Sáng thứ 6 30/10 | Chiều thứ 5 29/10 | Resolved | [docs/tasks/TASK-306_ANSWERS.md](TASK-306_ANSWERS.md) (`exam_{code}.pdf`, `answers_matrix.pdf`, `solutions_{code}.pdf`) |

- Output mình cần giao cho task sau: Service `TypstCompiler` và hàm compile PDF cho Đạt (`TASK-307`) tích hợp vào Export Center trước thứ 3 03/11/2026.
- Lịch có khả thi không? Hoàn toàn khả thi, logic biên dịch độc lập và mockable 100% trong môi trường CI.
- Quyết định đã thống nhất: Bắt buộc `shell=False`, timeout 30s và kiểm tra magic bytes `%PDF-`.

## Kế hoạch tự kiểm

- Tình huống thành công:
  - Biên dịch template hợp lệ trả về bytes file PDF có `%PDF-` ở đầu.
  - Văn bản tiếng Việt có dấu không bị lỗi font hay vỡ ký tự.
  - Công thức toán học LaTeX được chuyển đổi chính xác sang cú pháp Typst.
- Tình huống lỗi:
  - Lỗi cú pháp Typst trả về `TypstCompilationError` với thông báo đã được lọc đường dẫn nhạy cảm.
  - Lệnh chạy quá 30 giây kích hoạt `TypstTimeoutError` và tiến trình con bị terminate sạch sẽ.
  - Typst CLI chưa cài đặt kích hoạt `TypstNotFoundError` rõ ràng.
- Môi trường: Pytest local với mock `subprocess.run` và kiểm thử thực tế với Typst CLI local nếu có.

## Bàn giao – điền theo kết quả thực tế

- PR/commit/output: PR [#25](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/25) (Draft plan-only).
- Đã làm / đã kiểm: Kế hoạch triển khai Template M2, câu hỏi môi trường Docker cho Duy và naming format cho Đạt.
- Đã chấp nhận: Chờ review từ Duy (`@johannguyen015`) và Đạt (`@dat-001`).
- Còn chờ/bước tiếp: Mở Draft PR, chờ phản hồi câu hỏi môi trường Docker, bắt đầu triển khai code từ thứ 6.

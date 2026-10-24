# Backend Core Rules & Architectural Guidelines (BE1 Scope)

## 1. Kiến trúc Bất biến & Nguyên tắc Dữ liệu (W2 Critical)
- **100% In-Memory Pre-validation:** Mọi khâu bóc tách file (.docx, .tex, .md), quét bảng đáp án, và phát hiện OMML phải thực hiện hoàn toàn in-memory trước khi ghi dữ liệu.
- **Database Untouched on Error:** Nếu phát hiện lỗi (thiếu đáp án, lỗi OMML không parse được, số câu ngoài khoảng [1, 20]), TUYỆT ĐỐI không ghi đè hoặc thay đổi DB. Trả về ngay mã `HTTP 422 Unprocessable Entity` với schema lỗi: `{"errors": [{"question_no": int, "error_type": "MISSING_ANSWER" | "UNPARSED_OMML"}]}`.
- **Atomic Ingestion & Idempotent Replace:** Khi và chỉ khi 100% câu hỏi hợp lệ:
  1. Mở một transaction PostgreSQL duy nhất.
  2. Xóa các bản ghi `source_questions` và `question_blueprints` cũ của session_id.
  3. Bulk insert toàn bộ câu hỏi mới.
  4. Commit transaction nguyên tử.
- **State Machine Guard:** `POST /api/sessions/{session_id}/confirm-source` CHỈ cho phép khi session ở trạng thái `draft`. Nếu khác `draft`, trả về `HTTP 409 Conflict`.
- **Security Check (SEC-02):** Nếu câu hỏi có cờ `has_security_warning == true`, bắt buộc request body phải có `acknowledged_security_warnings: true`, nếu không trả về `HTTP 422`.

## 2. Tiêu chuẩn Mã nguồn & Thư viện
- **Ngôn ngữ & Runtime:** Python 3.11+, FastAPI, Pydantic v2.
- **Type Hinting:** Bắt buộc type annotation đầy đủ trên tất cả hàm, endpoint, và services.
- **Text & Encoding:** Chuẩn hóa toàn bộ text sang Unicode NFC (`unicodedata.normalize('NFC', text)`).
- **Linter & Type Checker:** Tuân thủ cấu hình Ruff (line-length: 100) và Mypy trong `backend/pyproject.toml`.

## 3. An ninh File Upload (SEC-04)
- Chống Path Traversal: Luôn làm sạch filename bằng `re.sub(r'[^a-zA-Z0-9._-]', '_', filename)`.
- Chống Zip Bomb: Kiểm tra cấu trúc zip của file `.docx`, bắt buộc chứa `[Content_Types].xml` và `word/document.xml`, tỷ lệ giải nén không vượt quá 50MB.

## 4. Kỷ Luật Phạm Vi Mã Nguồn & Chống Conflict Git (Scope & Git Discipline)
- **Tuyệt đối KHÔNG tự ý format toàn bộ dự án:**
  - KHÔNG chạy `ruff format app/ tests/` hoặc `ruff check --fix` trên toàn bộ codebase.
  - Chỉ được format và sửa lint trên **đúng các file thuộc phạm vi task của BE1** (ví dụ: `app/services/parser/`, `test_parsers.py`, `test_ingest.py`, các file được phân công trong task).
  - Tuyệt đối không chạm vào, không reformat các file của thành viên khác (`app/services/generation/`, `app/services/ai/`, v.v.) để tránh gây merge conflict hàng loạt trên nhánh `dev`.
- **Không tự ý commit file quản trị sprint & file cá nhân:**
  - Không commit các file kế hoạch sprint chung (như `w2_21_10.md`), file nháp hay scratchpad cá nhân trừ khi có chỉ đạo rõ ràng từ người dùng.
- **Quy trình kiểm tra tính sạch (Clean Tree Verification) trước khi commit:**
  1. Luôn chạy `git status` và `git diff --stat` để rà soát danh sách file thay đổi.
  2. Nếu phát hiện file ngoài phạm vi bị modified (do auto-format của IDE hoặc script), phải dùng `git restore <file>` khôi phục ngay trước khi stage.
  3. Chỉ `git add` đúng các file cần thiết cho task.

## 5. Kỷ Luật Lập Kế Hoạch & Kiểm Chứng Thực Tế (Grounding & Planning Rule)
- **Tuyệt đối không suy diễn dựa trên phỏng đoán:**
  - Bắt buộc kích hoạt skill `codebase-grounding` trước khi viết bất kỳ file kế hoạch hoặc code mới nào.
  - Phân biệt rõ giữa tầng Pydantic DTO (in-memory) và tầng PostgreSQL persistence (`schema.sql`). Không giả định trường in-memory có trong DB.
  - Phải mở xem định nghĩa hàm phụ trợ (sync `def` vs async `async def`) trước khi gọi; không tự động thêm `await` nếu hàm trả về sync.
- **Quy trình lập kế hoạch 2 pha (2-Phase Planning):**
  - Mọi kế hoạch triển khai phải tuân theo skill `task-planning`: Pha 1 (Draft) $\rightarrow$ Pha 2 (Audit thực chứng trên schema, dependencies, SDK).
  - Bắt buộc có **Mục 0: Phát hiện & Sửa lỗi logic** trong mọi file implementation plan để ghi lại kết quả audit trước khi bước vào lập trình.



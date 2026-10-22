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

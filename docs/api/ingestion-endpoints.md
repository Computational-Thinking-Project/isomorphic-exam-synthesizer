# Tài Liệu Đặc Tả Kỹ Thuật API Ingestion (TASK-202 / BE-02 / SEC-04)

> **Người phụ trách:** BE1 (`johannguyen015` / Nguyễn Bá Duy)  
> **Người phối hợp chính:** FE1 (`philip-kkk` / TASK-201, TASK-203b, TASK-204)  
> **Phiên bản:** 1.0 (Tuần 2 — W2)  
> **Base URL:** `/api/sessions/{session_id}`

---

## 1. Tổng Quan

Module Ingestion cung cấp 2 endpoints nhận và bóc tách đề thi nguồn, bảo đảm:
- **Bảo mật tệp (SEC-04):** Chống Path Traversal, chống Zip Bomb ($\le 50\text{MB}$ uncompressed), kiểm tra Magic Bytes `PK\x03\x04` và cấu trúc DOCX XML.
- **Tiền kiểm tra 100% In-Memory (ADR-002):** Nếu phát hiện lỗi cấu trúc / dữ liệu (thiếu đáp án, lỗi công thức OMML, số câu ngoài khoảng $[1, 20]$), hệ thống trả về ngay mã **HTTP 422 Unprocessable Entity** và giữ nguyên vẹn 100% CSDL và Storage ("Zero Cloud Mutation").
- **Ghi đè Nguyên tử (Atomic Replace):** Sử dụng PostgreSQL Stored Procedure `replace_source_questions` để xóa dữ liệu cũ và chèn dữ liệu mới trong một transaction ACID duy nhất.
- **Kích hoạt ngầm Blueprint (AI-02):** Tự động khởi chạy pipeline trích xuất Blueprint nội bộ qua background task (`asyncio.Semaphore(3)`).

---

## 2. Danh Sách Endpoints

### 2.1. Ingest Qua Tải Tệp (`POST /api/sessions/{session_id}/ingest-file`)

* **Mô tả:** Nhận file upload (`.docx`, `.tex`, `.md`), kiểm tra an toàn và bóc tách câu hỏi.
* **Content-Type:** `multipart/form-data`
* **Headers:**
  ```http
  Authorization: Bearer <supabase_jwt_token>
  ```
* **Parameters:**
  * `session_id` (Path, UUID): Mã phiên làm việc (phải thuộc quyền sở hữu của user và ở trạng thái `draft`).
* **Request Body (Form Data):**
  * `file`: Tệp tin đề thi (`.docx`, `.tex`, `.md`), dung lượng tối đa 10MB.
  * *Lưu ý:* Chặn tuyệt đối `.pdf` (trả về HTTP 400).

#### Phản Hồi Thành Công (HTTP 200 OK):
```json
{
  "session_id": "11111111-1111-1111-1111-111111111111",
  "message": "Exam file ingested and validated successfully",
  "total_questions": 10,
  "questions": [
    {
      "id": "sq-uuid-1",
      "session_id": "11111111-1111-1111-1111-111111111111",
      "question_no": 1,
      "raw_content": "Giải phương trình bậc hai $x^2 - 4 = 0$.",
      "options": {
        "A": "$x = \\pm 2$",
        "B": "$x = 2$",
        "C": "$x = -2$",
        "D": "$x = 0$"
      },
      "correct_key": "A",
      "solution_md": null,
      "has_missing_answer": false,
      "has_security_warning": false
    }
  ]
}
```

---

### 2.2. Ingest Qua Nhập Trực Tiếp (`POST /api/sessions/{session_id}/ingest-text`)

* **Mô tả:** Nhận văn bản thô dán từ clipboard (Markdown hoặc LaTeX).
* **Content-Type:** `application/json`
* **Headers:**
  ```http
  Authorization: Bearer <supabase_jwt_token>
  ```
* **Parameters:**
  * `session_id` (Path, UUID): Mã phiên làm việc.
* **Request Body:**
  ```json
  {
    "raw_text": "### Câu 1: Cho hàm số $y = x^2$...\nA. ... B. ... C. ... D. ...\n\nBẢNG ĐÁP ÁN:\n1.A"
  }
  ```
  *Ràng buộc:* $1 \le \text{length}(raw\_text) \le 100,000$ ký tự.

---

### 2.3. Asynchronous Blueprint Hook (`trigger_blueprint_pipeline`)

> [!NOTE]
> **Giới hạn kiến trúc (TASK-202):**
> Hàm `trigger_blueprint_pipeline` hiện tại hoạt động như một asynchronous event hook / placeholder với bounded concurrency (`asyncio.Semaphore(3)`) nhằm phục vụ việc ghi nhận log và kiểm thử an toàn luồng bất đồng bộ ngay sau khi câu hỏi được nạp thành công.
> 
> Việc gọi Gemini AI trích xuất Blueprint và ghi dữ liệu phân tích vào bảng `question_blueprints` là phạm vi tích hợp tiếp theo của nhiệm vụ **TASK-203**.

---

## 3. Mã Lỗi & Hợp Đồng Với Frontend (TASK-203b)

### 3.1. HTTP 422 Unprocessable Entity (Nội dung không đầy đủ / lỗi cấu trúc)
Khi phát hiện bất kỳ lỗi nào trong quá trình bóc tách in-memory, backend trả về danh sách lỗi chi tiết để Frontend (FE1) hiển thị hộp thoại cảnh báo:

```json
{
  "detail": {
    "message": "Exam content incomplete or unprocessable",
    "errors": [
      {
        "question_no": 3,
        "error_type": "MISSING_ANSWER",
        "message": "Question 3 does not have a valid correct answer key."
      },
      {
        "question_no": 7,
        "error_type": "UNPARSED_OMML",
        "message": "Question 7 contains unparsed OMML / Equation formulas."
      }
    ]
  }
}
```

* **Các mã `error_type`:**
  * `MISSING_ANSWER`: Câu hỏi không tìm thấy đáp án đúng trong bảng đáp án rời hoặc inline.
  * `UNPARSED_OMML`: File DOCX chứa công thức Equation / MathType không đọc được text dạng LaTeX (kể cả công thức đứng riêng 1 đoạn).
  * `INVALID_FORMAT`: Không đủ 4 phương án A/B/C/D hoặc số lượng câu không thuộc $[1, 20]$.
* **Hành vi an toàn:** Database và Storage hoàn toàn không bị thay đổi khi gặp mã lỗi này.

### 3.2. HTTP 409 Conflict (Ràng buộc trạng thái phiên)
Chỉ cho phép nạp đề khi phiên ở trạng thái `draft`. Nếu phiên đã được xác nhận (`blueprinted`, `generating`, `approved`, v.v.):
```json
{
  "detail": "Cannot ingest questions: session is in 'blueprinted' state (must be 'draft')"
}
```

### 3.3. HTTP 400 Bad Request (Lỗi an toàn tệp tin SEC-04)
* File vượt quá 10MB: `"File size exceeds maximum allowed limit of 10MB."`
* Đuôi file không được hỗ trợ (ví dụ `.pdf`): `"Unsupported file format '.pdf'. Only .docx, .tex, and .md files are accepted."`
* File zip rỗng hoặc cấu trúc DOCX hỏng: `"Invalid DOCX package structure: missing required XML entries."`
* Phát hiện Zip Bomb: `"File decompression size exceeds 50MB limit (potential Zip Bomb)."`

### 3.4. HTTP 401 / 403 / 404
* `401 Unauthorized`: Thiếu hoặc token JWT không hợp lệ.
* `403 Forbidden`: Session không thuộc quyền sở hữu của user đăng nhập (`assert_ownership`) hoặc caller nặc danh gọi RPC.
* `404 Not Found`: Không tìm thấy session.

### 3.5. HTTP 504 Gateway Timeout (Lỗi mạng / Không xác định trạng thái commit)
Khi xảy ra lỗi timeout mạng trong quá trình gọi Stored Procedure RPC (PostgreSQL có thể đã commit thành công nhưng HTTP response bị timeout):
```json
{
  "detail": "Database atomic replacement status is uncertain due to network timeout. The transaction may have completed. Please verify session state before retrying."
}
```
* **Hành vi an toàn:** Backend không hứa trước dữ liệu chưa đổi mà yêu cầu người dùng/frontend kiểm tra trạng thái session trước khi thử lại để tránh xung đột.

### 3.6. HTTP 500 Internal Server Error (Lỗi CSDL đã rollback)
Khi RPC gặp lỗi thực thi trong PostgreSQL và transaction đã được hủy hoàn toàn:
```json
{
  "detail": "Database atomic replacement failed and was rolled back."
}
```

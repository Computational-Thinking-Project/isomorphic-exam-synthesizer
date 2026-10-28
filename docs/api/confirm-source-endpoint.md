# Tài Liệu Đặc Tả Kỹ Thuật API Xác Nhận Đề Nguồn & Khóa Blueprint (TASK-205 / BE-03)

> **Người phụ trách:** BE1 (`johannguyen015` / Nguyễn Bá Duy)  
> **Người phối hợp chính:** FE1 (`philip-kkk` / TASK-204)  
> **Phiên bản:** 1.0 (Tuần 2 — W2)  
> **Base URL:** `/api/sessions/{session_id}/confirm-source`  
> **Phương thức:** `POST`

---

## 1. Tổng Quan Nghiệp Vụ

Endpoint này phục vụ việc **xác nhận đề thi nguồn** sau khi giảng viên đã xem trước kết quả bóc tách (Review Stage 1). Khi gọi thành công, endpoint sẽ:
1. **Kiểm tra quyền sở hữu (Ownership):** Xác thực người dùng và kiểm tra quyền trên phiên làm việc.
2. **Kiểm tra trạng thái phiên (State Precondition):** Phiên bắt buộc phải ở trạng thái `draft`. Nếu ở trạng thái khác (ví dụ `blueprinted` hoặc `generating`), trả về mã `HTTP 409 Conflict`.
3. **Kiểm tra toàn vẹn câu hỏi nguồn (Data Integrity):** Phiên phải có ít nhất 1 câu hỏi nguồn và **không có câu nào thiếu đáp án** (`has_missing_answer == true`).
4. **Kiểm soát An ninh Âm thầm (SEC-02 / ADR-004 Silent Security Audit):** Nếu có câu hỏi nguồn chứa cảnh báo an ninh (`has_security_warning == true`), hệ thống tự động ghi vết kiểm toán vào bảng `public.security_events` mà không hiển thị cảnh báo hay bắt buộc người dùng xác nhận trên giao diện. Quá trình xác nhận đề nguồn vẫn diễn ra bình thường (HTTP 200).
5. **Động cơ Blueprint Tự Động & Hợp Đồng Với TASK-203 (Automatic Blueprint Engine):** Đảm bảo 100% câu hỏi nguồn đều có Blueprint tương ứng trong bảng `question_blueprints` (có ràng buộc `UNIQUE (source_question_id)`).
   - **Hợp đồng với TASK-203:** Pipeline AI nền (TASK-203) phụ trách sinh các Blueprint toán học chuẩn xác với điều kiện bất biến (`invariants`), chứng minh tính khả giải và miền biến thiên phức tạp (`extraction_source: "AI_PIPELINE"`).
   - **Cơ chế Fallback Tất Định (Deterministic Fallback):** Nếu giảng viên bấm xác nhận đề trước khi pipeline nền hoàn tất hoặc trong môi trường offline/test, endpoint tự động kích hoạt `ensure_blueprints_for_session` trích xuất biến số mặc định ($\pm 5$) có đóng dấu `is_fallback: true` và `extraction_source: "FALLBACK_DETERMINISTIC"` qua cơ chế `upsert(..., ignore_duplicates=True)` để chống nhân bản khi chạy song song.
6. **Chuyển Trạng Thái Nguyên Tử (Atomic State Transition):** Thông qua PostgreSQL Stored Procedure `confirm_exam_source`, hệ thống khóa dòng phiên làm việc (`FOR UPDATE`), đối chiếu số lượng câu hỏi và thực hiện đồng thời việc đóng dấu `confirmed_at = now()` trên các blueprints và chuyển trạng thái phiên làm việc sang `status = 'blueprinted'` trong **1 transaction ACID duy nhất**.

---

## 2. Chi Tiết Endpoint

### Request
* **URL:** `POST /api/sessions/{session_id}/confirm-source`
* **Headers:**
  ```http
  Authorization: Bearer <supabase_jwt_token>
  Content-Type: application/json
  ```
* **Path Parameters:**
  * `session_id` (string, UUID): Mã định danh phiên làm việc.
* **Request Body:**
  ```json
  {
    "acknowledged_security_warnings": false
  }
  ```

| Trường | Kiểu | Bắt buộc | Mặc định | Mô tả |
|---|---|---|---|---|
| `acknowledged_security_warnings` | `boolean` | Không | `false` | [DEPRECATED per ADR-004] Trước đây dùng để xác nhận SEC-02. Nay trường này không còn bắt buộc và được bỏ qua ở backend (tự động ghi nhận log kiểm toán ngầm). Giữ lại vì mục đích tương thích ngược. |

---

### Response

#### Thành Công: `HTTP 200 OK`
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

| Trường | Kiểu | Mô tả |
|---|---|---|
| `session_id` | `string` | Mã phiên làm việc |
| `status` | `string` | Trạng thái mới của phiên: luôn là `"blueprinted"` |
| `confirmed_at` | `string` | Thời điểm khóa đề nguồn theo chuẩn ISO 8601 UTC |
| `total_questions` | `integer` | Tổng số câu hỏi nguồn đã được xác nhận |
| `total_blueprints` | `integer` | Tổng số blueprint toán học đã sẵn sàng cho khâu sinh đề (Stage 2) |
| `message` | `string` | Thông báo thành công |

---

## 3. Bảng Mã Lỗi (Error Responses)

| HTTP Status | Điều kiện kích hoạt | Schema / Detail mẫu |
|---|---|---|
| **401 Unauthorized** | Thiếu token hoặc token JWT không hợp lệ | `{"detail": "Not authenticated"}` |
| **403 Forbidden** | Phiên thuộc về người dùng khác | `{"detail": "Forbidden: Not resource owner"}` |
| **404 Not Found** | Phiên không tồn tại trong hệ thống | `{"detail": "Session not found"}` |
| **409 Conflict** | Trạng thái phiên khác `draft` (đã `blueprinted`, `generating`), hoặc số lượng câu hỏi bị thay đổi đồng thời giữa lúc đọc và chốt | `{"detail": "Cannot confirm source: Session status has changed concurrently or is not in draft status"}` |
| **422 Unprocessable** | Phiên chưa có câu hỏi nguồn nào | `{"detail": "Cannot confirm source: Session has no source questions"}` |
| **422 Unprocessable** | Có câu hỏi thiếu đáp án (`has_missing_answer == true`) | `{"detail": "Cannot confirm source: Questions [3] have missing answers"}` |
| **429 Too Many Requests** | Vượt ngưỡng Rate Limit CRUD | `{"detail": "Rate limit exceeded"}` |
| **500 Internal Error** | Lỗi CSDL khi update trạng thái phiên hoặc blueprints | `{"detail": "Failed to confirm source and lock blueprints: ..."}` |

---

## 4. Ví Dụ Sử Dụng (cURL)

### A. Xác nhận đề nguồn thông thường
```bash
curl -X POST "http://localhost:8000/api/sessions/11111111-1111-1111-1111-111111111111/confirm-source" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### B. Xác nhận đề nguồn khi có cảnh báo an ninh (SEC-02 / ADR-004 Silent Audit)
```bash
# Vẫn gửi request bình thường (body rỗng hoặc kèm acknowledged_security_warnings tùy chọn)
# Hệ thống tự động ghi vết kiểm toán vào bảng security_events và trả về HTTP 200 OK
curl -X POST "http://localhost:8000/api/sessions/11111111-1111-1111-1111-111111111111/confirm-source" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"acknowledged_security_warnings": false}'
```

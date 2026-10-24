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
4. **Kiểm soát An ninh (SEC-02):** Nếu có câu hỏi nguồn chứa cảnh báo an ninh (`has_security_warning == true`), yêu cầu người dùng phải xác nhận tường minh thông qua trường `acknowledged_security_warnings: true`. Nếu không, trả về `HTTP 422`.
5. **Động cơ Blueprint Tự Động (Automatic Black-Box Engine):** Đảm bảo 100% câu hỏi nguồn đều có Blueprint tương ứng trong bảng `question_blueprints` (nếu pipeline background trước đó chưa hoàn thành, endpoint sẽ tự động sinh và lưu blueprint fallback có tính tất định).
6. **Chuyển Trạng Thái Nguyên Tử (Atomic State Transition):** Khóa thời gian xác nhận (`confirmed_at = now_iso`) trên bảng `question_blueprints` và chuyển trạng thái phiên làm việc sang `status = 'blueprinted'`.

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
| `acknowledged_security_warnings` | `boolean` | Không | `false` | Xác nhận đã kiểm tra và đồng ý tiếp tục với các câu hỏi có cảnh báo an ninh (SEC-02). |

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
| **409 Conflict** | Trạng thái phiên khác `draft` (đã `blueprinted`, `generating`, ...) | `{"detail": "Session is in 'blueprinted' state; cannot confirm source unless in 'draft'"}` |
| **422 Unprocessable** | Phiên chưa có câu hỏi nguồn nào | `{"detail": "Cannot confirm source: Session has no source questions"}` |
| **422 Unprocessable** | Có câu hỏi thiếu đáp án (`has_missing_answer == true`) | `{"detail": "Cannot confirm source: Questions [3] have missing answers"}` |
| **422 Unprocessable** | Có câu cảnh báo an ninh mà `acknowledged_security_warnings == false` | `{"detail": "Questions [1] have security warnings (SEC-02). Explicit acknowledgment is required by setting acknowledged_security_warnings=True"}` |
| **429 Too Many Requests** | Vượt ngưỡng Rate Limit CRUD | `{"detail": "Rate limit exceeded"}` |
| **500 Internal Error** | Lỗi CSDL khi update trạng thái phiên hoặc blueprints | `{"detail": "Failed to confirm source and lock blueprints: ..."}` |

---

## 4. Ví Dụ Sử Dụng (cURL)

### A. Xác nhận đề nguồn thông thường (Không có cảnh báo an ninh)
```bash
curl -X POST "http://localhost:8000/api/sessions/11111111-1111-1111-1111-111111111111/confirm-source" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"acknowledged_security_warnings": false}'
```

### B. Xác nhận đề nguồn có cảnh báo an ninh (SEC-02)
```bash
curl -X POST "http://localhost:8000/api/sessions/11111111-1111-1111-1111-111111111111/confirm-source" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"acknowledged_security_warnings": true}'
```

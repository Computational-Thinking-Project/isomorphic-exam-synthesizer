# Hướng Dẫn Tích Hợp Stage 2 — Cấu Hình Sinh Đề & SSE Thời Gian Thực

Tài liệu này mô tả chi tiết kiến trúc, luồng dữ liệu, hợp đồng API và hướng dẫn kiểm thử cho **Giai đoạn 2 (Stage 2)** thuộc dự án `isomorphic-exam-synthesizer`.

---

## 1. Tổng Quan Nhiệm Vụ (Scope)
- **TASK-206 (FE-06):** Màn hình cấu hình sinh đề thi đẳng cấu (`Stage2ConfigCard`, `Stage2ConfigPage`).
- **TASK-208 (FE-12):** Giao diện thanh tiến trình thời gian thực SSE (`GenerationProgressView`, hook `useSSE`).
- **Tuyến đường (Route):** `/session/:id/stage2` (được bảo vệ bởi `ProtectedRoute`).

---

## 2. Điểm Chốt Hợp Đồng API (API Contracts)

### 2.1. Cấu hình sinh đề (TASK-206)
- **Endpoint:** `POST /api/sessions/{session_id}/config`
- **Payload:**
```json
{
  "num_versions": 2,
  "variation_modes": [
    "parameter_variation",
    "context_swap"
  ],
  "ordering_preferences": {
    "shuffle_questions": true
  }
}
```
> [!NOTE]
> - Chỉ cung cấp tùy chọn `shuffle_questions` (xáo trộn thứ tự câu hỏi). Không sử dụng `shuffle_options` theo quyết định thiết kế.
> - Các chế độ `variation_modes` được đối soát với Blueprint của đề bài; nếu có xung đột, backend trả mã `ERR_CONFIG_CONFLICT` (HTTP 400).

### 2.2. Khởi động tiến trình nền
- **Endpoint:** `POST /api/sessions/{session_id}/generate`
- **Mục đích:** Kích hoạt BackgroundTasks job trên FastAPI để điều phối sinh biến thể qua Gemini API.

### 2.3. Bắt tay Ticket xác thực SSE (SEC-05, SEC-13)
- **Endpoint:** `POST /api/sessions/{session_id}/events/ticket`
- **Headers:** `Authorization: Bearer <Supabase_JWT_Token>`
- **Response:**
```json
{
  "ticket": "sse-ticket-abc-123",
  "expires_at": "2026-10-27T08:31:00Z"
}
```
> [!IMPORTANT]
> Ticket có thời hạn **60 giây** và chỉ được dùng **1 lần**. Hook `useSSE` không lưu ticket vào `localStorage`. Khi kết nối lại, hook tự động gọi API lấy một ticket mới.

### 2.4. Luồng Server-Sent Events (SSE Stream)
- **Endpoint:** `GET /api/sessions/{session_id}/events?ticket={ticket}&last_event_id={id}`
- **Sự kiện chuẩn hóa:**
  1. `progress`: `{ percent: 45, completed_count: 9, total_count: 20, message: "...", estimated_seconds: 25 }`
  2. `question_status`: `{ version_index: 1, question_no: 3, status: "analyzing" | "generating" | "validating" | "retrying" | "done", message: "..." }`
  3. `question_done`: `{ version_index: 1, question_no: 3, variant_id: "..." }`
  4. `warning`: `{ code: "...", message: "..." }`
  5. `done`: `{ total_generated: 20, duration_seconds: 35 }`

---

## 3. Trạng Thái Thân Thiện Trên Giao Diện

Nhằm tạo trải nghiệm mượt mà, trực quan cho giảng viên và loại bỏ các thuật ngữ kỹ thuật phức tạp (như "thẩm định 4 tầng", "flag cục bộ"), mỗi câu hỏi trong từng mã đề được thể hiện qua 5 trạng thái:

1. 🔍 **Đang phân tích** (`analyzing` / `preparing`): Hệ thống đọc cấu trúc và mô hình toán học của câu gốc.
2. ⏳ **Đang soạn nội dung** (`generating`): Gemini sinh nội dung biến thể đẳng cấu mới.
3. 🔍 **Đang kiểm tra** (`validating`): Kiểm tra tính nhất quán số liệu và lời giải.
4. 🔄 **Đang tinh chỉnh** (`retrying`): Tự động hiệu chỉnh câu hỏi nếu chưa đạt chuẩn nghiệm đẹp.
5. ✅ **Hoàn thành** (`done`): Câu hỏi đã sẵn sàng.

> [!TIP]
> Toàn bộ quá trình kiểm tra và tinh chỉnh diễn ra **hoàn toàn tự động**. Giảng viên không cần thao tác bấm "sinh bù" ở Stage 2. Nút "Tạo lại câu này" sẽ xuất hiện ở Stage 3 nếu giảng viên muốn đổi biến thể cụ thể sau khi xem toàn bộ đề thi.

---

## 4. Trang Xem Trước Độc Lập (Visual Previews)

Để phục vụ phát triển độc lập và demo không phụ thuộc vào backend:

1. **Xem trước Form Cấu hình (Stage 2 Config):**  
   Mở trình duyệt: `http://localhost:3000/stage2-config-preview.html`  
   Cho phép chuyển đổi giữa các kịch bản: Thành công, Xung đột Blueprint (`ERR_CONFIG_CONFLICT`), Lỗi mạng.

2. **Xem trước Luồng SSE Thời gian thực (Progress Stream):**  
   Mở trình duyệt: `http://localhost:3000/sse-progress-preview.html`  
   Cho phép mô phỏng luồng phát SSE sinh động theo 5 trạng thái câu hỏi, thử nghiệm đứt kết nối mạng và tái kết nối tự động.

---

## 5. Docker & Nginx Streaming Configuration

Để luồng SSE không bị đệm hoặc nghẽn gói tin khi chạy qua proxy Nginx:

```nginx
location /api/ {
    proxy_pass http://backend:8000/api/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding on;
    proxy_read_timeout 600s;
}
```

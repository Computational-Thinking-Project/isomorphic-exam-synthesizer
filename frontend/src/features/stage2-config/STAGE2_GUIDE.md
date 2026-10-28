# Hướng Dẫn Tích Hợp Stage 2 — Cấu Hình Sinh Đề & SSE Thời Gian Thực

Tài liệu này mô tả chi tiết kiến trúc, luồng dữ liệu, hợp đồng API và hướng dẫn kiểm thử cho **Giai đoạn 2 (Stage 2)** thuộc dự án `isomorphic-exam-synthesizer`.

---

## 1. Tổng Quan Nhiệm Vụ (Scope)
- **TASK-206 (FE-06):** Màn hình cấu hình sinh đề thi đẳng cấu (`Stage2ConfigCard`, `Stage2ConfigPage`).
- **TASK-208 (FE-12):** Giao diện thanh tiến trình thời gian thực SSE (`GenerationProgressView`, hook `useSSE`).
- **Tuyến đường (Route):** `/session/:id/stage2` (được bảo vệ bởi `ProtectedRoute`).

---

## 2. Điểm Chốt Hợp Đồng API (API Contracts)

### 2.1. Cấu hình sinh đề (TASK-206 & Contract BE2 TASK-207a)
- **Endpoint:** `POST /api/sessions/{session_id}/config`
- **Payload (Tuân thủ nghiêm ngặt schema Pydantic BE2):**
```json
{
  "n_versions": 2,
  "active_variation_modes": [
    "parameter_variation",
    "context_swap"
  ],
  "ordering_preferences": {
    "shuffle_questions": true
  }
}
```
> [!NOTE]
> - Trường số lượng mã đề là `n_versions` (in `[1, 4]`), danh sách chế độ là `active_variation_modes` (mảng string, cho phép `[]` nếu không dùng biến thể).
> - Chỉ cung cấp tùy chọn `shuffle_questions` (xáo trộn thứ tự câu hỏi). Không sử dụng `shuffle_options` theo quyết định thiết kế.
> - Các chế độ `active_variation_modes` được đối soát với Blueprint của đề bài (tính theo phần giao 100% câu hỏi hỗ trợ); nếu có xung đột, backend trả mã `ERR_CONFIG_CONFLICT` (HTTP 400 kèm `error_message` hoặc `detail`).

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

### 2.4. Luồng Server-Sent Events (SSE Stream - TASK-207b)
- **Endpoint:** `GET /api/sessions/{session_id}/events?ticket={ticket}&last_event_id={id}`
- **Sự kiện chuẩn hóa:**
  1. `progress`: `{ percent_complete: 45, completed_count: 9, total_count: 20, message: "...", estimated_seconds: 25, questions: [...] }`
  2. `question_status`: `{ version_index: 1, question_no: 3, status: "analyzing" | "generating" | "validating" | "retrying" | "done", message: "..." }`
  3. `question_done`: `{ version_index: 1, question_no: 3, variant_id: "..." }`
  4. `warning`: `{ version_index: 1, question_no: 3, message: "..." }` (tiến trình vẫn tiếp tục, cảnh báo hiển thị trên câu hỏi tương ứng)
  5. `error`: `{ error: "...", error_message: "..." }` (lỗi job AI dừng kết nối ngay, không reconnect lặp vô hạn)
  6. `done`: `{ total_generated: 20, duration_seconds: 35 }` (hoàn tất chuyển sang màn bàn giao Stage 3 `/session/:id/stage3`)

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

---

## 6. Quyết Định Thiết Kế Sản Phẩm & Phạm Vi Bàn Giao

### 6.1. Căn cứ quyết định loại bỏ `shuffle_options` (chỉ giữ `shuffle_questions`)
- **Căn cứ UX & Nghiệp vụ**: Bản chất của bài toán sinh đề thi đẳng cấu là tạo ra các phiên bản đề thi ($N \in [1, 4]$) có **nội dung câu hỏi khác nhau** (thay đổi số liệu/tham số hoặc hoán đổi ngữ cảnh thực tế theo Blueprint), đồng thời kết hợp xáo trộn thứ tự các câu hỏi trong đề (`ordering_preferences.shuffle_questions: true`). Vì vậy, thí sinh ngồi cạnh nhau đã hoàn toàn nhận các câu hỏi khác nhau.
- **An toàn kỹ thuật**: Việc xáo trộn thứ tự các phương án lựa chọn (A, B, C, D) tiềm ẩn rủi ro làm hỏng ngữ nghĩa của các câu hỏi trắc nghiệm có đáp án phụ thuộc vị trí (ví dụ: *"Cả A và B đều đúng"*, *"Tất cả các đáp án trên đều sai"*). Do đó, hệ thống thống nhất chỉ cung cấp tùy chọn xáo trộn thứ tự câu hỏi `shuffle_questions` để đảm bảo an toàn tuyệt đối.

### 6.2. Căn cứ luồng sinh tự động ngầm ở Stage 2 (không có nút sinh bù)
- **Tự động hóa hoàn toàn**: Tiến trình sinh đề của AI tại Stage 2 trải qua 5 bước: *Đang phân tích 🔍 -> Đang soạn nội dung ⏳ -> Đang kiểm tra 🔍 -> Đang tinh chỉnh 🔄 -> Hoàn thành ✅*. Nếu câu hỏi gặp lỗi hoặc chưa thỏa mãn ràng buộc nghiệm đẹp, pipeline tự động kích hoạt retry và tinh chỉnh ngầm dưới background mà không bắt người dùng phải can thiệp thủ công.
- **Trải nghiệm người dùng**: Giảng viên không cần bấm "sinh bù" ở Stage 2. Sau khi toàn bộ các mã đề sinh xong và chuyển sang Stage 3 (`/session/:id/stage3`), giảng viên sẽ được xem trực quan toàn bộ ma trận đề thi; tại đây nút *"Tạo lại câu này"* được cung cấp riêng cho từng câu hỏi nếu giảng viên muốn sinh lại biến thể theo ý muốn chủ quan.

### 6.3. Tình trạng bàn giao Stage 3 và Các đầu nối tích hợp Backend 207
- **Phạm vi đã kiểm thử độc lập ở FE2**: Đã triển khai và kiểm thử giao diện Stage 2 (TASK-206 & TASK-208) trên bộ test harness ReactDOM và contract schemas giả lập (199/199 unit tests).
- **Màn chờ Stage 3**: Tuyến đường `/session/:id/stage3` đã được định tuyến sẵn với màn chờ tích hợp an toàn (không rơi vào wildcard/Login), sẵn sàng kết nối ngay khi Stage 3 được triển khai.
- **Các đầu nối phụ thuộc BE2 cần kiểm thử tích hợp thực tế**:
  1. *Ticket handshake*: Xác thực Bearer JWT thật từ Supabase để lấy ticket dùng 1 lần (TTL 60s) và stream qua proxy Nginx không đệm.
  2. *Re-sync tiến độ khi mất kết nối*: Kiểm thử replay ring-buffer với `last_event_id` thật trên máy chủ khi client bị đứt kết nối mạng.
  3. *Trạng thái hoàn thành một phần (`partial_generated`)*: Kiểm thử luồng dừng, giữ nguyên số câu thật và giao diện phục hồi khi backend xử lý hết quota hoặc gặp câu hỏi không đạt ràng buộc nghiệm đẹp.

# TASK-206 — Plan và Bàn Giao: Giao Diện Cấu Hình Sinh Đề & Luồng Tiến Trình Thời Gian Thực SSE

- **Nguồn giao việc:** [w2.md](../../w2.md), [w2_21_10.md](../../w2_21_10.md), [docs/planning.md](../planning.md)
- **Phụ trách:** FE2 (`htbaax` — Lead tác vụ Stage 2/Stage 3 Review UI)
- **Reviewer:** Philip (`philip-kkk` — Lead reviewer), Nhật Quỳnh (`nhatquynh1107`)
- **Repo/nhánh:** `feat/task-206-stage2-config`; PR: [#22](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/22)
- **Hạn đợt:** Hết Tuần 2 (28/10/2026); **ETA task:** Hoàn tất bàn giao, đã verified F01 & approved

---

## Mình cần làm gì?

### Hành vi / Tiêu chí đạt:

1. **Form cấu hình sinh đề (`Stage2ConfigCard` - TASK-206):**
   - Chọn số lượng mã đề $N \in [1, 4]$ bằng slider hoặc nút chọn trực quan.
   - Lọc và hiển thị các chế độ biến thể dựa trên Blueprint đề bài (tính giao 100% câu hỗ trợ); kiểm tra case-sensitive chính xác (`parameter_variation`, `context_swap`, `variable_inversion`).
   - Hỗ trợ trường hợp đề bài chỉ cho phép tạo đề gốc không biến thể (`active_variation_modes: []`).
   - Hỗ trợ 2 tùy chọn xáo trộn đề độc lập trong `ordering_preferences`: `shuffle_questions` (hoán vị thứ tự câu hỏi) và `shuffle_options` (hoán vị 4 phương án A/B/C/D phòng ngừa trùng vị trí đáp án giữa các mã đề).
   - Tóm tắt tổng số biến thể dự kiến sinh $M = N \times K$ ($K$ là số câu hỏi nguồn).
   - Chặn submit khi thông tin cấu hình đang lưu hoặc phiên không ở trạng thái hợp lệ; xử lý lỗi xung đột cấu hình `ERR_CONFIG_CONFLICT` (HTTP 400).

2. **Hook quản lý kết nối thời gian thực SSE (`useSSE` - TASK-208):**
   - Bắt tay xin Ticket dùng một lần (`POST /api/sessions/{session_id}/events/ticket`, TTL 60s, không lưu persistent storage/localStorage).
   - Quản lý EventSource với token bảo mật; tự động xin ticket mới khi mất kết nối mạng và tiếp tục nhận stream từ `last_event_id`.
   - Bảo toàn cursor `last_event_id` khi kết nối lại trong cùng phiên (chống cạn buffer 50 sự kiện trên server); xóa sạch cursor khi đổi phiên.
   - Reset trạng thái `isDone` khi tái kết nối hoặc bắt đầu thao tác sinh bù (Incremental Retry).
   - Phân biệt lỗi mạng (tự động retry theo Exponential Backoff có jitter) và lỗi nghiệp vụ job AI (`error`/`error_message` dừng kết nối và hiển thị lỗi rõ ràng).
   - Nhận diện trạng thái hoàn thành một phần (`partial_generated`), giữ nguyên tỷ lệ hoàn thành thực tế thay vì ép 100% ảo.

3. **Giao diện tiến trình sinh đề (`GenerationProgressView`):**
   - Thanh tiến trình phần trăm (%) kèm thời gian ước tính còn lại.
   - Thể hiện 5 trạng thái câu hỏi thân thiện: 🔍 Đang phân tích, ⏳ Đang soạn nội dung, 🔍 Đang kiểm tra, 🔄 Đang tinh chỉnh, ✅ Hoàn thành.
   - Hiển thị cảnh báo nghiệp vụ (`warnings`) trực tiếp trên từng câu mà không ngắt quãng toàn bộ tiến trình sinh đề.
   - Khi phiên ở trạng thái `partial_generated`: các câu chưa sinh được gắn nhãn nổi bật "Chưa sinh" (missing); cung cấp nút **"Sinh bù các câu còn thiếu"** tách biệt hoàn toàn với nút kết nối lại mạng.

4. **Container điều phối vòng đời phiên (`Stage2ConfigPage`):**
   - Bảo vệ tuyến đường `/session/:id/stage2` qua `ProtectedRoute`.
   - Cô lập submit cấu hình và kết nối SSE theo từng phiên (`session_id`).
   - Hỗ trợ thao tác sinh bù (`POST /api/sessions/:id/retry-generation`) với cơ chế cô lập `retryOperationRef` và hủy kết quả nếu người dùng rời trang hoặc chuyển phiên.

5. **Giao diện duyệt đề Stage 3 (`Stage3ReviewPage` - Preview/Adapter bàn giao):**
   - Tuyến đường `/session/:id/stage3`: render KaTeX chuẩn xác cho đề bài và các phương án trắc nghiệm.
   - Badge cảnh báo nghiệm toán học hoặc ràng buộc chưa tối ưu (`variant.has_warning` / `variant.validation_report`).
   - Cung cấp nút **"Sinh bù câu này"** đối với câu mang trạng thái thiếu hoặc chưa hoàn tất.
   - Khóa an toàn các thao tác đổi biến thể câu hỏi (chờ backend hoàn tất bộ API thẩm định 1-1 tại TASK-301 / Tuần 3).
   - Quản lý bộ đếm thời gian điều hướng `navigationTimerRef` an toàn tuyệt đối: hủy timer khi unmount hoặc đổi phiên $A \rightarrow B$, xác thực phiên hiện hành `activeSessionIdRef.current === targetSessionId` và lượt thao tác `retryOperationRef.current === thisOp` trong callback, loại bỏ hoàn toàn race condition điều hướng sai lệch URL.

---

### Ngoài phạm vi:
- Logic sinh biến thể Gemini API phía Backend (thuộc nhiệm vụ AI Engine / BE2).
- Thuật toán xáo trộn Fisher-Yates nội bộ trên cơ sở dữ liệu (thuộc nhiệm vụ TASK-303 / Tuần 3).
- API thẩm định câu hỏi 1-1, revert nguyên tử và khóa nội dung HTTP 423 (thuộc nhiệm vụ TASK-301 / Tuần 3).

---

### Hiện đã có:
- Component `MathRenderer` (TASK-105) hiển thị KaTeX mượt mà.
- Service `stage2Service.js` giao tiếp đầy đủ các endpoints: `getConfig`, `saveConfig`, `startGeneration`, `getSSETicket`, `retryGeneration`, `getSessionDetail`.
- Test harness DOM `domHarness.js` hỗ trợ mô phỏng toàn diện ReactDOM client-side.

---

## File và các thành phần triển khai

| File | Mục đích | Output | Cách kiểm |
|---|---|---|---|
| `frontend/src/features/stage2-config/Stage2ConfigCard.jsx` | Form chọn mã đề, chế độ biến thể, tùy chọn xáo trộn | UI card cấu hình chuẩn contract Pydantic | `Stage2Config.test.js` |
| `frontend/src/features/stage2-config/GenerationProgressView.jsx` | Thanh tiến trình và lưới 5 trạng thái câu hỏi, cảnh báo warnings, partial retry | UI tiến trình thời gian thực | `GenerationProgress.test.js` |
| `frontend/src/hooks/useSSE.js` | Hook quản lý luồng EventSource, ticket 1 lần, reconnect, backoff, cursor bảo toàn | Hook SSE dùng chung | `useSSE.test.js` |
| `frontend/src/features/stage2-config/Stage2ConfigPage.jsx` | Container điều phối toàn bộ vòng đời Stage 2 | Trang cấu hình và theo dõi tiến trình | `Stage2ConfigPage.test.js` |
| `frontend/src/features/stage3-review/Stage3ReviewPage.jsx` | Màn hình duyệt đề Stage 3 với KaTeX, guard timer, partial retry | Giao diện duyệt đề bàn giao | `Stage3Review.test.js` |
| `frontend/src/services/stage2Service.js` | Service gọi API backend chuẩn hóa | Client API layer | `stage2Service.test.js` |
| `frontend/src/features/stage2-config/STAGE2_GUIDE.md` | Tài liệu kỹ thuật kiến trúc, schema hợp đồng, luồng retry | Tài liệu hướng dẫn tích hợp | Đọc đối chiếu code |

---

## Kế hoạch tự kiểm & Bằng chứng thực tế

1. **Unit tests toàn diện:**
   - Chạy `npm test`: **220 / 220 tests pass** (100% pass trên 6 test suites).
   - Bao phủ các tình huống:
     - Chọn cấu hình $N \in [1, 4]$, `active_variation_modes`, `shuffle_questions`, `shuffle_options`.
     - Nhận diện lỗi `ERR_CONFIG_CONFLICT` và hiển thị chi tiết lỗi.
     - Handshake ticket SSE 1 lần, retry exponent backoff, kết nối lại giữ nguyên cursor `last_event_id`.
     - Phân định rõ `partial_generated` và nút sinh bù `retry-generation`.
     - Kiểm thử toàn bộ 4 kịch bản hẹn giờ điều hướng Stage 3: chuyển phiên $A \rightarrow B$, $A \rightarrow B \rightarrow A$, unmount khi đang đếm ngược, và retry thông thường về lại Stage 2.
2. **Kiểm tra Lint:**
   - Chạy `npm run lint`: **0 warning, 0 error**.
3. **Kiểm tra Build:**
   - Chạy `npm run build`: Vite production bundle biên dịch thành công.
4. **CI Checks:**
   - Toàn bộ 5 GitHub Actions CI checks đạt màu xanh.

---

## Bàn giao — điền theo kết quả thực tế

- **PR/commit/output:** PR #22 trên nhánh `feat/task-206-stage2-config`.
- **Đã làm / đã kiểm:**
  - Triển khai toàn bộ tính năng theo DoD.
  - Tự kiểm 220 unit tests, lint và build đạt 100%.
  - Xử lý dứt điểm các góp ý review từ `@philip-kkk` và `@nhatquynh1107`.
  - F01 (Timer điều hướng đa phiên): Reviewer Philip đã xác minh `verified` tại commit `4c9fc8e`.
  - F02 (Đồng bộ tài liệu `STAGE2_GUIDE.md`): Đã hoàn tất đồng bộ tại commit `dee9b3d` và cập nhật bổ sung payload `shuffle_options`.
- **Đã chấp nhận:** Cả 2 reviewers (`philip-kkk` và `nhatquynh1107`) đều đã có quyết định `APPROVED`.
- **Còn chờ/bước tiếp:** Re-review xác nhận lần cuối từ Philip và merge vào nhánh `dev`.

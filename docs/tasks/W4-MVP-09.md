# W4-MVP-09 · M2 Kế hoạch màn hình xuất đề và tải ZIP (Export Download FE)

- Phụ trách: Trung Anh (`philip-kkk`, TV1/FE1). Reviewer đề xuất: Hùng (contract Export/Storage), Bội Anh (`htbaax`) hoặc Duy (`johannguyen015`) cho frontend/state.
- Nguồn phân công: [W4_ASSIGNMENT](W4_ASSIGNMENT.md) và [W4_TASK_DETAIL](W4_TASK_DETAIL.md) mục W4-MVP-09.
- Workflow v0.1 proposed, bản tài liệu `7b7387f` có cập nhật INPUT-20261109. [Mẫu M2](../review/TEMPLATES.md#m2).
- Nhánh: `feat/w4-mvp-09-export-download`. Base lúc lập plan: `035ce45` (`origin/dev`, đã bao gồm PR #59, #65, #30, #61 và nền route `sessionPaths.js` từ PR #60).

---

## 1. Mục tiêu và phạm vi triển khai

Xây dựng màn hình Export (`/session/:sessionId/export` — `EXPORT_ROUTE` trong `frontend/src/sessionPaths.js`) và lớp service giao tiếp với Backend Export API (`W4-MVP-08` / PR #63), giúp giảng viên:
- Xem trạng thái đóng gói đề thi (`idle`, `preparing`, `ready`, `failed`) đối với các phiên ở trạng thái `approved` hoặc `exported`.
- Kích hoạt đóng gói (`POST /api/sessions/{sessionId}/export`), theo dõi tiến trình polling có giới hạn (`GET /api/sessions/{sessionId}/export`), không tự động `POST` khi F5/reload.
- Yêu cầu signed URL tải ZIP (`POST /api/sessions/{sessionId}/export/download-url`, TTL 3600s) qua thao tác chủ động của người dùng, tự động xin cấp lại URL mới khi URL hết hạn, chặn double-click và không lưu/log signed URL.
- Xử lý an toàn các mã lỗi `401`, `403`, `404`, `409` (chưa approve hoặc artifact chưa sẵn sàng), `422` (`ERR_EXPORT_BUILD_FAILED`), `423`, `503` (outcome-unknown — kiểm tra `GET /export` trước khi cho phép retry).

**Ngoài phạm vi `W4-MVP-09`:**
- Không sửa logic đóng gói/Storage/RPC phía backend (thuộc `W4-MVP-07` / `W4-MVP-08` của Hùng).
- Không tự ý mở khóa `approved`, `exported` trong `sessionDestination.js` hay gắn `EXPORT_ROUTE` vào `App.jsx` trên nhánh này nếu chưa thống nhất bước tích hợp ở `W4-MVP-10` (tránh xung đột file chung `App.jsx` / `sessionDestination.js` với `feat/w4-mvp-10-resume-integration`).

---

## 2. Đầu vào và hợp đồng phụ thuộc (`I-...` theo chuẩn WORKFLOW v0.1)

| ID / yêu cầu | Cung cấp → Nhận | Nội dung hợp đồng & điều kiện đủ dùng | Trạng thái / Bằng chứng | Phần còn thiếu / Bước tiếp |
|---|---|---|---|---|
| `I-W4MVP09-Q10` *(liên kết `I08-Q10`)* | Hùng (`W4-MVP-08`) ↔ Philip (`W4-MVP-09`) | Hợp đồng HTTP & UI đề xuất tại `docs/api/private-export-contract.md` (nhánh `feat/w4-mvp-08-private-export`):<br>- `POST /api/sessions/{id}/export` (`200 ready` hoặc `202 pending`)<br>- `GET /api/sessions/{id}/export` (`idle \| preparing \| ready \| failed` + safe error code)<br>- `POST /api/sessions/{id}/export/download-url` (`{ url, expires_at, expires_in: 3600, filename }`, `Cache-Control: no-store`)<br>- Polling mỗi `2s`, dừng sau `120s` để hiện nút làm mới thủ công; tên file `exam_bundle_<session_id>.zip`. | **Proposed** trên nhánh `feat/w4-mvp-08-private-export` (PR #63) | Cần xác nhận chốt **Q10** giữa Philip, Hùng và Duy để mở HTTP adapter thật trên backend; code FE trước theo hợp đồng Q10 với mock/fixture, sau đó đối chiếu live khi PR #63 merge. |
| `I-W4MVP09-STATE` | Duy (`johannguyen015`) → Philip | Trạng thái phiên `approved` / `exported` từ `GET /api/sessions/{id}` và `EXPORT_ROUTE` từ `sessionPaths.js`. | **Đã chốt** (`74d2135`) | Đã có `exportPath(sessionId)` trong `sessionPaths.js`. |
| **Output giao lại** | Philip (`W4-MVP-09`) → `W4-MVP-10` & `W4-MVP-13` | Component `SessionExportPage` (export từ `frontend/src/features/export/SessionExportPage.jsx`) + unit/integration tests để `W4-MVP-10` mount vào `EXPORT_ROUTE` trong `App.jsx` và mở khóa `approved`, `exported`. | **Đang lập plan** | Giao sau khi hoàn tất code & test trên nhánh `feat/w4-mvp-09-export-download`. |

---

## 3. Thứ tự triển khai và file dự kiến

Các đường dẫn frontend tính từ `frontend/src/`:

| Lượt | File dự kiến | Mục đích & Đầu ra | Cách kiểm |
|---|---|---|---|
| **1** | `docs/tasks/W4-MVP-09.md` | Khởi tạo tài liệu kế hoạch M2, khai báo input Q10 và lộ trình commit. | Rà diff markdown và liên kết. |
| **2** | `services/exportService.js`, `services/exportService.test.js` | Service gọi `triggerExport`, `getExportStatus`, `issueDownloadUrl` qua `api.js` (kèm `AbortSignal`, check auth/account, map lỗi 401/403/404/409/422/503). | `node --test src/services/exportService.test.js` |
| **3** | `features/export/exportController.js`, `features/export/exportController.test.js` | State machine thuần: chuyển trạng thái `loading -> idle/preparing/ready/failed`, bounded polling 2s / tối đa 120s, chống double-click, xử lý hết hạn `expires_at` và recovery 503 (`GET /export` trước retry). | `node --test src/features/export/exportController.test.js` |
| **4** | `features/export/SessionExportPage.jsx`, `features/export/SessionExportPage.test.js` | Giao diện Export hoàn chỉnh: hiển thị trạng thái, nút Tạo/Tải gói ZIP, nút Làm mới khi timeout polling, thông báo lỗi an toàn, nút quay về Dashboard; kiểm trên `domHarness` (mount, F5, click, double-click, hết hạn URL, unmount). | `node --test src/features/export/SessionExportPage.test.js`, `npm run lint`, `npm run build` |
| **5** | `docs/tasks/W4-MVP-09.md` | Ghi nhận kết quả test, lint, build và ranh giới tích hợp live với PR #63 / W4-MVP-10. | Đối chiếu SHA và output thực tế. |

---

## 4. Kế hoạch tự kiểm

- **Tình huống thành công:**
  - Mở trang với session `approved` (`idle`): bấm Tạo gói đề $\rightarrow$ `POST /export` $\rightarrow$ polling `GET /export` cho đến `ready` $\rightarrow$ bấm Tải ZIP $\rightarrow$ `POST /export/download-url` $\rightarrow$ kích hoạt tải file `exam_bundle_<session_id>.zip`.
  - Mở/F5 trang với session `exported` (`ready`): `GET /export` trả `ready` ngay, không tự `POST /export` lại.
  - Signed URL hết hạn (`expires_at` đã qua hoặc cận hạn): bấm Tải lại tự động xin URL mới qua `POST /export/download-url`.
- **Tình huống lỗi & biên:**
  - Click đúp vào nút Tạo gói đề hoặc Tải ZIP chỉ gửi 1 request tại một thời điểm.
  - Polling quá `120s` tự dừng vòng lặp và hiển thị nút kiểm tra lại thủ công.
  - Lỗi `401`, `403`, `404`, `409` (phiên chưa duyệt), `422` (`ERR_EXPORT_BUILD_FAILED`), `503` (outcome-unknown) hiển thị thông báo tiếng Việt an toàn, không rò rỉ raw stack/URL.
  - Rời trang / đổi tài khoản / logout hủy mọi request và timer polling đang chạy.
- **Lệnh kiểm chuẩn:**
  - `node --test --test-concurrency=1 src/services/exportService.test.js src/features/export/exportController.test.js src/features/export/SessionExportPage.test.js`
  - `npm run lint` (`eslint . --max-warnings 0`)
  - `npm run build` (`vite build`)

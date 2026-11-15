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
- Xử lý an toàn các mã lỗi `401`, `403`, `404`, `409` (chưa approve hoặc artifact chưa sẵn sàng), `422` (`ERR_EXPORT_BUILD_FAILED`), `423`, `503`/`504` hoặc timeout/network outcome-unknown (kiểm tra/reconcile qua `GET /export` trước khi cho phép `POST /export` retry).

**Ngoài phạm vi `W4-MVP-09`:**
- Không sửa logic đóng gói/Storage/RPC phía backend (thuộc `W4-MVP-07` / `W4-MVP-08` của Hùng).
- Không tự ý mở khóa `approved`, `exported` trong `sessionDestination.js` hay gắn `EXPORT_ROUTE` vào `App.jsx` trên nhánh này nếu chưa thống nhất bước tích hợp ở `W4-MVP-10` (tránh xung đột file chung `App.jsx` / `sessionDestination.js` với `feat/w4-mvp-10-resume-integration`).

---

## 2. Đầu vào và hợp đồng phụ thuộc (`I-...` theo chuẩn WORKFLOW v0.1)

| ID / yêu cầu | Cung cấp → Nhận | Nội dung hợp đồng & điều kiện đủ dùng | Trạng thái / Bằng chứng | Phần còn thiếu / Bước tiếp |
|---|---|---|---|---|
| `I-W4MVP09-Q10` *(liên kết `I08-Q10`)* | Hùng (`W4-MVP-08`) ↔ Philip (`W4-MVP-09`) | Hợp đồng HTTP đã triển khai tại `PR #63 @ f74e34c` (`backend/app/api/routes/private_export.py`, `docs/api/private-export-contract.md`):<br>- `POST /api/sessions/{id}/export`: request body **0-byte (`undefined`)** — backend trả `400 ERR_EXPORT_REQUEST_BODY_NOT_ALLOWED` nếu có JSON/raw body; `200 ready` hoặc `202 preparing`; FE dùng `EXPORT_POST_TIMEOUT_MS = 120000`.<br>- `GET /api/sessions/{id}/export`: `{ state: 'idle' \| 'preparing' \| 'ready' \| 'failed', filename, sha256, size_bytes, error_code }`.<br>- `POST /api/sessions/{id}/export/download-url`: empty body (`undefined`), trả `{ url, expires_at, expires_in: 3600, filename }`, header `Cache-Control: no-store`, URL `https://`.<br>- Polling mỗi `2s`, dừng sau `120s` để hiện nút làm mới thủ công; tên file `exam_bundle_<session_id>.zip`.<br>- Khi `503`/`504`/timeout/network outcome-unknown ở `POST /export` (controller vào `phase === 'error'`), chặn `startExport()` retry trực tiếp và yêu cầu `refreshStatus()` (`GET /export`) reconcile trước. | **Accepted tại `PR #63 @ f74e34c`** (xác nhận trên PR #69: `#6888258177` của Đạt `@Thanhdat3010` và `#6892000660` của Hùng `@benalexx007`). | Đã nối `exportService.js` vào `SessionExportPage` + `exportController` ở mức **Local Ready**; kiểm chứng **Integrated** live chờ merge PR #58/#63 và `I08-11S` (`PRIVATE_EXPORT_ENABLED=true`). |
| `I-W4MVP09-STATE` | Duy (`johannguyen015`) → Philip | Trạng thái phiên `approved` / `exported` từ `GET /api/sessions/{id}` và `EXPORT_ROUTE` từ `sessionPaths.js`. | **Đã chốt** (`74d2135`) | Đã có `exportPath(sessionId)` trong `sessionPaths.js`. |
| **Output giao lại** | Philip (`W4-MVP-09`) → `W4-MVP-10` & `W4-MVP-13` | Component `SessionExportPage` (`frontend/src/features/export/SessionExportPage.jsx`, mặc định nối `exportService.js`) + `exportController` + 22 unit/component tests để `W4-MVP-10` mount vào `EXPORT_ROUTE` trong `App.jsx` và mở khóa `approved`, `exported`. | **Local Ready** (`bd187e4` trên `feat/w4-mvp-09-export-download`) | Sẵn sàng để `W4-MVP-10` mount vào `App.jsx` sau khi PR #69 được review/merge; chưa claim **Integrated** live E2E. |

---

## 3. Thứ tự triển khai và file dự kiến

Các đường dẫn frontend tính từ `frontend/src/`:

| Lượt | Commit thực tế | File triển khai | Mục đích & Đầu ra | Cách kiểm |
|---|---|---|---|---|
| **1** | `bd13511` | `docs/tasks/W4-MVP-09.md` | Khởi tạo tài liệu kế hoạch M2, khai báo input Q10 và lộ trình commit. | Rà diff markdown và liên kết. |
| **2** | `584dd52` | `features/export/exportController.js`, `exportController.test.js`, `SessionExportPage.jsx`, `SessionExportPage.test.js` | State machine thuần và UI shell hoàn chỉnh dùng adapter tiêm vào (`unwired` khi chưa nối HTTP), bounded polling 2s / 120s, chống double-click, xử lý `expires_at`, recovery `503`. | `node --test src/features/export/*.test.js` |
| **3** | `bd187e4` | `services/exportService.js`, `exportService.test.js`, `features/export/{exportController,SessionExportPage}.{js,jsx,test.js}` | Nối `exportService` vào `api.js` và `SessionExportPage` theo Q10 đã chốt tại `PR #63 @ f74e34c` (empty POST body 0-byte, timeout `120000ms`, `state`/`sha256`/`size_bytes`, chặn retry khi `phase === 'error'` trước `refreshStatus()`, hỗ trợ thêm `504`). | `node --test --test-concurrency=1 src/services/exportService.test.js src/features/export/exportController.test.js src/features/export/SessionExportPage.test.js`, `npm run lint`, `npm run build` |
| **4** | *(commit doc này)* | `docs/tasks/W4-MVP-09.md` | Ghi nhận nghiệm thu Q10 (`Accepted`), kết quả test/lint/build thực tế và ranh giới `Local Ready` vs `Integrated` với PR #63 / W4-MVP-10. | Đối chiếu SHA `bd187e4` và output thực tế. |

---

## 4. Kế hoạch tự kiểm

- **Tình huống thành công:**
  - Mở trang với session `approved` (`idle`): bấm Tạo gói đề $\rightarrow$ `POST /export` $\rightarrow$ polling `GET /export` cho đến `ready` $\rightarrow$ bấm Tải ZIP $\rightarrow$ `POST /export/download-url` $\rightarrow$ kích hoạt tải file `exam_bundle_<session_id>.zip`.
  - Mở/F5 trang với session `exported` (`ready`): `GET /export` trả `ready` ngay, không tự `POST /export` lại.
  - Signed URL hết hạn (`expires_at` đã qua hoặc cận hạn): bấm Tải lại tự động xin URL mới qua `POST /export/download-url`.
- **Tình huống lỗi & biên:**
  - Click đúp vào nút Tạo gói đề hoặc Tải ZIP chỉ gửi 1 request tại một thời điểm.
  - Polling quá `120s` tự dừng vòng lặp và hiển thị nút kiểm tra lại thủ công.
  - Lỗi `401`, `403`, `404`, `409` (phiên chưa duyệt), `422` (`ERR_EXPORT_BUILD_FAILED`), `423`, `503`/`504`/timeout (outcome-unknown) hiển thị thông báo tiếng Việt an toàn, không rò rỉ raw stack/URL, và chặn `startExport()` retry trực tiếp khi `phase === 'error'` cho tới khi `refreshStatus()` reconcile xong.
  - Rời trang / đổi tài khoản / logout hủy mọi request và timer polling đang chạy.
- **Lệnh kiểm chuẩn:**
  - `node --test --test-concurrency=1 src/services/exportService.test.js src/features/export/exportController.test.js src/features/export/SessionExportPage.test.js`
  - `npm run lint` (`eslint . --max-warnings 0`)
  - `npm run build` (`vite build`)

---

## 5. Bàn giao & Kiểm thử

### Chuỗi commit trên `feat/w4-mvp-09-export-download`
- `bd13511` — `docs(w4-mvp-09): add M2 plan and Q10 export contract handoff`
- `584dd52` — `feat(export): add export state controller and UI shell`
- `bd187e4` — `feat(export): wire exportService to finalized Q10 HTTP endpoints` (6 file: `frontend/src/services/exportService.js`, `frontend/src/services/exportService.test.js`, `frontend/src/features/export/exportController.js`, `frontend/src/features/export/exportController.test.js`, `frontend/src/features/export/SessionExportPage.jsx`, `frontend/src/features/export/SessionExportPage.test.js`)

### Kết quả kiểm chứng sau chỉnh sửa code cuối cùng (`bd187e4`)
*(Chạy cục bộ với `api.defaults.adapter` mock theo contract `PR #63 @ f74e34c` và JSDOM `domHarness`, chưa chạy HTTP live với backend.)*

- `node --test --test-concurrency=1 src/services/exportService.test.js src/features/export/exportController.test.js src/features/export/SessionExportPage.test.js`: **22/22 PASS** (`0` fail, `0` cancelled, `0` skipped, `0` todo):
  - `SessionExportPage.test.js` (**4/4 PASS**): trạng thái `unwired` khi adapter `null`, chặn session chưa `approved`/`exported`, luồng tạo/tải ZIP qua adapter tiêm vào, và luồng đầy đủ qua `exportService` mặc định + mock `api.defaults.adapter`.
  - `exportController.test.js` (**10/10 PASS**): chặn session chưa duyệt, `unwired`, F5/load chỉ gọi `getStatus`, chống double-click, bounded polling `maxPollDurationMs`, cấp lại signed URL hết hạn, hủy timer/`AbortSignal` khi đổi tài khoản, map lỗi `401`/`403`/`404`/`409`/`422`/`423`/`503`/`504`, đọc payload Q10 (`state`, `sha256`, `size_bytes`), và chặn `startExport()` khi `phase === 'error'` tới khi `refreshStatus()` reconcile xong.
  - `exportService.test.js` (**8/8 PASS**): kiểm tra `sessionId` rỗng/`new`, URI encoding + đọc `state`/`sha256`/`size_bytes`, các trạng thái `idle`/`preparing`/`failed`, bác bỏ payload thiếu trường hoặc metadata `ready` sai, body `undefined` 0-byte & timeout `120000ms` cho `200`/`202`, xác thực URL HTTPS + `expires_at` + `expires_in`, hủy qua `AbortSignal`/đổi tài khoản, và `401` dùng refresh/retry chung tối đa một lần.
- `npm run lint` (`eslint . --max-warnings 0`): thoát mã `0` (`0` lỗi, `0` cảnh báo).
- `npm run build` (`vite build`): thoát mã `0` (`1911 modules transformed`, built in `15.97s`).

### Ranh giới bàn giao (`Local Ready` vs `Integrated`)
- **Trạng thái hiện tại:** **Local Ready** trên nhánh `feat/w4-mvp-09-export-download` (`bd187e4` + commit doc này), sẵn sàng cho `W4-MVP-10` mount `SessionExportPage` vào `EXPORT_ROUTE` trong `App.jsx` và mở khóa `approved`/`exported` trong `sessionDestination.js` sau khi PR #69 được review/merge.
- **Phạm vi giữ nguyên trên nhánh này:** Không chạm `frontend/src/App.jsx` và `frontend/src/features/dashboard/sessionDestination.js`.
- **Phần chờ bước `Integrated` (live E2E):** Merge PR #58 và PR #63 (`W4-MVP-08`), hoàn tất bước OPS `I08-11S` (`PRIVATE_EXPORT_ENABLED=true`, xác nhận timeout budget worker với `frontend/nginx.conf` `proxy_read_timeout 600s` từ Đạt/Duy), rồi chạy nghiệm thu live theo `W4-MVP-13`.

# TASK-44 — Plan và Bàn Giao: Xác Nhận Nguồn và Gating Canonical Readiness (Stage 1)

- Nguồn giao việc: Issue #44, `docs/tasks/W4_ASSIGNMENT.md` (Mục tiêu 01 Source → Blueprint → config), `docs/adr/0001-confirm-before-blueprint.md`.
- Phụ trách: Implementation Agent (Author); Reviewer đề xuất: Philip (`@philip-kkk` — FE Integration Owner) / Duy (`@nbduy2506` — Lead).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `fix/issue-44-confirm-before-blueprint`; Base: `origin/dev` (`21887c12eeac733f091da12f3516501e1f25ef93`).
- Hạn đợt: Tối thứ 3; ETA task: Đã hoàn thành triển khai và kiểm thử 100% green.

## Mình cần làm gì?

- Hành vi/tiêu chí đạt:
  1. **Frontend Stage 1 Ingestion Boundary:**
     - Parse/ingest file hoặc text chỉ lưu trữ source questions, không tự động kích hoạt sinh Blueprint ngầm.
     - Sau khi người dùng xác nhận đề nguồn (`POST /api/sessions/{id}/source-artifacts/confirm`), giao diện chuyển sang trạng thái đã xác nhận (read-only đối với dữ liệu nguồn), **tuyệt đối không chuyển ngay sang Stage 2**.
  2. **Hiển thị trạng thái Canonical Production:**
     - Tích hợp endpoint `GET /api/sessions/{id}/source-artifacts` để đọc trạng thái canonical:
       - `pending` → "Đang chờ tạo Blueprint"
       - `running` → "Đang tạo Blueprint"
       - `ready` → "Blueprint đã sẵn sàng"
       - `failed` → "Tạo Blueprint thất bại"
     - Hỗ trợ nút **"Kiểm tra trạng thái"** (manual refresh gọi GET status).
     - Khi `failed`, hiển thị nút **"Thử tạo lại Blueprint"** (gọi `POST /api/sessions/{id}/source-artifacts/retry`), sau đó tự động truy vấn lại trạng thái.
     - Chỉ khi canonical status là `ready === true` mới hiển thị nút **"Tiếp tục Stage 2"**.
     - Khi `pending`, `running`, hoặc `failed`, vô hiệu hóa khả năng tiếp tục sang Stage 2.
  3. **Khôi phục trạng thái sau Reload (F5):**
     - Cập nhật `Stage1Route.jsx` cho phép phiên `blueprinted` nhưng chưa `ready` vẫn mở được Stage 1 dưới dạng read-only để theo dõi trạng thái.
     - Tự động gọi kiểm tra trạng thái canonical khi mount nếu session đã `blueprinted` nhưng chưa ghi nhận `canonicalReady`.
     - Khóa chỉnh sửa/upload/replace source questions sau khi đã xác nhận.
  4. **Chặn điều hướng Stage 2 khi chưa Ready:**
     - Cập nhật `sessionDestination()` trong `sessionDestination.js`:
       - `draft` → `/session/:id/stage1`.
       - `blueprinted` có `blueprint_summary.is_ready === true` → `/session/:id/stage2`.
       - `blueprinted` chưa ready hoặc thiếu `is_ready` → `/session/:id/stage1`.
       - `configured` / `generating` → duy trì đường dẫn `/session/:id/stage2`.
     - Direct URL `/session/:id/stage2` khi chưa ready:
       - Khóa toàn bộ form cấu hình (`<fieldset disabled={...}>`), ẩn/vô hiệu hóa nút lưu/sinh đề.
       - Hiển thị banner thông báo Blueprint chưa sẵn sàng kèm nút **"Quay về Giai đoạn 1"**.
       - `handleConfigSubmit` trên `Stage2ConfigPage.jsx` chặn submit phía client nếu `!isBlueprintReady`.
- Ngoài phạm vi:
  - Backend ingest triggers và retirement của legacy hook: đã được hiện thực trong PR #61 (`feat/w4-mvp-01-source-readiness`). Không nhân đôi mã nguồn backend trên nhánh này.
  - Không sửa đổi thuật toán sinh câu hỏi, prompt Gemini hay bộ thẩm định SymPy.
  - Không hiển thị UI Blueprint editor hoặc chọn variation modes cho giáo viên (theo Issue #45).
  - Không tạo thêm framework polling/SSE mới cho canonical production; tuân thủ giải pháp manual refresh theo đặc tả MVP.

## File và thứ tự triển khai

| Lượt / File | Mục đích sửa | Output mong muốn | Cần input gì trước | Cách kiểm |
|---|---|---|---|---|
| 1. `frontend/src/services/sourceConfirmation.js` | Bổ sung hàm `retrySourceArtifacts` | POST tới `/api/sessions/{id}/source-artifacts/retry` | API Contract W4 | `npm test frontend/src/services/sourceConfirmation.test.js` |
| 2. `frontend/src/features/dashboard/sessionDestination.js` | Điều chỉnh resolver đích đến của session | `blueprinted` chưa ready chuyển về Stage 1; chỉ sang Stage 2 khi `is_ready === true` | `blueprint_summary.is_ready` contract | `npm test frontend/src/features/dashboard/sessionDestination.test.js` |
| 3. `frontend/src/features/stage1-ingestion/sourceIngestion.js` | Quản lý state canonical, retry, status check | Giữ session ở Stage 1 sau confirm; cung cấp action check, retry, proceed | `retrySourceArtifacts`, `getSourceArtifactStatus` | `npm test frontend/src/features/stage1-ingestion/sourceIngestion.test.js` |
| 4. `frontend/src/features/stage1-ingestion/Stage1Route.jsx` | Cho phép session `blueprinted` mount Stage 1; bảo vệ `openConfirmed` | Read-only Stage 1 khi F5; chỉ chuyển trang khi destination là `/stage2` | `sessionDestination` | `npm test frontend/src/features/stage1-ingestion/Stage1Route.test.js` |
| 5. `frontend/src/features/stage1-ingestion/Stage1SourcePanel.jsx` | Hiển thị banner trạng thái canonical & các nút thao tác | Banner hiển thị 4 trạng thái; nút "Kiểm tra", "Thử tạo lại", "Tiếp tục Stage 2" | State từ `sourceIngestion` | `npm test frontend/src/features/stage1-ingestion/Stage1SourcePanel.test.js` |
| 6. `frontend/src/features/stage2-config/Stage2ConfigCard.jsx` & `Stage2ConfigPage.jsx` | Guard chặn tương tác khi chưa ready; nút quay về Stage 1 | Form bị disable, banner cảnh báo, chặn submit API config | Contract `isBlueprintReady` | `npm test frontend/src/features/stage2-config/Stage2ConfigPage.test.js` |
| 7. Test suites | Cập nhật và bổ sung toàn diện các kịch bản kiểm thử | 373 tests pass 100% | Mock fixtures | `npm test` |

## Kế hoạch tự kiểm và kết quả thực tế

- [x] Lệnh kiểm test frontend: `npm --prefix frontend test`
  - Kết quả: **373/373 passed (100% green)**. Bao phủ đầy đủ các ca:
    1. Confirm thành công với `canonical_status=pending` → vẫn ở Stage 1.
    2. Trạng thái `running` → không cho phép tiếp tục.
    3. Trạng thái `ready=true` → hiển thị nút chuyển Stage 2.
    4. Trạng thái `failed` → hiển thị nút thử tạo lại Blueprint.
    5. Retry thành công → cập nhật lại trạng thái canonical.
    6. Reload (F5) khi session `blueprinted` chưa ready → mở Stage 1 ở chế độ read-only, tự động check status.
    7. Direct access URL Stage 2 khi chưa ready → form bị khóa, không thể submit config/generation.
    8. Cách ly race condition: đổi session/account khi request đang chờ không làm rò rỉ trạng thái.
- [x] Lệnh kiểm linter: `npm --prefix frontend run lint`
  - Kết quả: `eslint . --max-warnings 0` passed cleanly (0 errors, 0 warnings).
- [x] Lệnh kiểm build: `npm --prefix frontend run build`
  - Kết quả: `vite build` hoàn tất thành công trong 5.99s.

## Bàn giao — điền theo kết quả thực tế

- PR/nhánh: `fix/issue-44-confirm-before-blueprint` tạo từ `origin/dev` (`21887c12eeac733f091da12f3516501e1f25ef93`).
- Đã làm / đã kiểm:
  - Đã triển khai đầy đủ 12 files frontend + unit/integration tests.
  - Xác minh toàn bộ 373 bài kiểm tra vượt qua, không có cảnh báo linter.
  - Phụ thuộc backend: Backend PR #61 (`feat/w4-mvp-01-source-readiness`, HEAD `9fda6fd`) chứa backend ingest boundary, retirement legacy hook, và DB migration 019.
- Đã chấp nhận: Chờ Philip (`@philip-kkk`) và Duy (`@nbduy2506`) review.
- Còn chờ/bước tiếp: Tạo Pull Request vào nhánh `dev` theo mẫu M3.

# W4-MVP-10 · M2 Kế hoạch tích hợp, bàn giao và kiểm chứng khôi phục phiên (Resume Integration)

- Phụ trách: Trung Anh (`philip-kkk`, TV1/FE1). Reviewer đề xuất: Bội Anh (`htbaax`) cho frontend (`Stage3PreviewPage` / route), Duy (`johannguyen015`) cho contract trạng thái và điều phối.
- Nguồn phân công: [W4_ASSIGNMENT](W4_ASSIGNMENT.md) và [W4_TASK_DETAIL](W4_TASK_DETAIL.md) mục W4-MVP-10.
- Workflow v0.1 proposed, bản tài liệu `7b7387f` có cập nhật INPUT-20261109. [Mẫu M2](../review/TEMPLATES.md#m2).
- Nhánh: `feat/w4-mvp-10-resume-integration`. Base ban đầu: `74d2135`; đã đồng bộ với `origin/dev` tại `a379ec1` (qua merge commit `7c838f8`, đã bao gồm PR #65, #59, #30, #61, #71 và #69).
- Hai đầu vào **Q11** (`I-W4MVP10-STATE` và `I-W4MVP10-FE2`) đã chốt xong ngày 12/11.

---

## 1. Phạm vi và Route Matrix Q11 (Đồng bộ toàn bộ 10 trạng thái)

Đã hoàn thành giai đoạn 1 (PR #60 nền route tại `74d2135`): định nghĩa tập trung 5 route (`STAGE1_ROUTE`, `STAGE2_ROUTE`, `STAGE3_ROUTE`, `STAGE3_PREVIEW_ROUTE`, `EXPORT_ROUTE`) và 5 helper builder (`stage1Path`, `stage2Path`, `stage3Path`, `stage3PreviewPath`, `exportPath`) trong `frontend/src/sessionPaths.js`.

Giai đoạn 2 (`feat/w4-mvp-10-resume-integration` tại head code `47c4ae9`): Mở khóa toàn bộ 10 trạng thái trong `sessionDestination.js` (làm rỗng `pendingDestinations`), gắn đầy đủ 5 route trong `App.jsx`, mở lại thao tác xuất bản trên `Stage3PreviewPage.jsx`, và bổ sung guard khóa chỉnh sửa khi deep-link Stage 1–3 cho các phiên đã sang bước sau / khóa HTTP 423.

| Trạng thái `session.status` | Đích chốt theo Q11 | Tình trạng triển khai tại `47c4ae9` | Dependency FE / BE |
|---|---|---|---|
| `draft` | `/session/:sessionId/stage1` | **Đã nối** | Sẵn sàng trên `dev`. |
| `blueprinted` | `/session/:sessionId/stage1` hoặc `/stage2` | **Đã nối**: `blueprint_summary?.is_ready === true` $\rightarrow$ `/stage2`, ngược lại giữ `/stage1` (read-only) | **PR #65** đã merge vào `dev`. |
| `configured`, `generating` | `/session/:sessionId/stage2` | **Đã nối** | **PR #30** đã merge vào `dev`. |
| `failed` | `/session/:sessionId/stage2` | **Đã nối** (gỡ `'failed'` khỏi `pendingDestinations` tại `9138377`, giữ lại khi merge `7c838f8`) | **PR #59** & **PR #52** đã merge vào `dev`. |
| `partial_generated`, `generated` | `/session/:sessionId/stage3` | **Đã nối** và chuẩn hóa 3 đường dẫn trong `Stage3ReviewPage.jsx` sang `sessionPaths.js` | **PR #59** & **PR #54** đã merge vào `dev`. |
| `reviewed` | `/session/:sessionId/stage3/preview` | **Đã nối** (`STAGE3_PREVIEW_ROUTE` & `'reviewed'` từ PR #71 `03f7e77`; giữ nguyên khi merge `7c838f8`) | FE **PR #71** đã merge. Live API chờ **PR #49** (`GET /finalize/preview`). |
| `approved`, `exported` | `/session/:sessionId/export` | **Đã nối** (`EXPORT_ROUTE -> <SessionExportPage />` trong `App.jsx`, gỡ khỏi `pendingDestinations`, mở lại nút Export & `handleApprove` ở `Stage3PreviewPage.jsx`, thêm guard deep-link Stage 1–3) | FE **PR #69** đã merge (`a379ec1`). Live ZIP chờ **PR #58**, **PR #63** & OPS `I08-11S`. |
| Status lạ (`unknown`) | Ở lại Dashboard + notice an toàn | **Đã giữ** | Fallback an toàn *"Trạng thái mới nhất của phiên chưa được hỗ trợ..."*. |

> **Nguyên tắc an toàn đã tuân thủ:** Chỉ gỡ trạng thái khỏi `pendingDestinations` sau khi màn đích đã tồn tại trên `dev` và được mount vào `<ProtectedRoute>` trong `App.jsx` (`STAGE3_PREVIEW_ROUTE` từ PR #71, `EXPORT_ROUTE` từ PR #69 + PR #66).

---

## 2. Đầu vào và Dependency (`I-...` theo chuẩn WORKFLOW v0.1)

### 2.1. Đầu vào hợp đồng đã chốt
| ID | Cung cấp → Nhận | Nội dung đã chốt | Trạng thái |
|---|---|---|---|
| `I-W4MVP10-STATE` | Duy (`johannguyen015`) → TV1/W4-MVP-10 | Dùng `GET /api/sessions/{id}` (`status`, `generation_config.n_versions`, `exam_versions[].is_finalized`, `blueprint_summary.is_ready`, `generation_error_code`) + hợp đồng `GET /finalize/preview` (`PR #49`), `generation-snapshot`/`retry-generation` (`PR #30`), `review/snapshot` (`PR #54`), Export artifact (`Q09/Q10`). | **Accepted** (12/11) |
| `I-W4MVP10-FE2` | Bội Anh (`htbaax`) → TV1/W4-MVP-10 | `partial_generated` mở `/stage3` dạng `read_only` + nút sinh bù cấp phiên; `reviewed` mở `/stage3/preview` (S07); `approved`/`exported` điều hướng sang `/export`; FE2 bổ sung Stage 2 `failed` Recovery View và mở lại điều hướng Export sau khi `EXPORT_ROUTE` được mount. | **Accepted** (12/11; đồng bộ S07→S08 sau PR #71) |

### 2.2. Danh sách PR phụ thuộc mở khóa code và tích hợp live
| ID phụ thuộc | PR / Task | Phụ trách | Tình trạng hiện tại (16/11) | Tác động với `W4-MVP-10` |
|---|---|---|---|---|
| `I-W4MVP10-PR52-PR54` | **PR #52** & **PR #54** | Duy | **Đã merge vào `dev`** | Đủ dữ liệu `generation_error_code` và review snapshot. |
| `I-W4MVP10-PR65` | **PR #65** (`fix/issue-44-confirm-before-blueprint`) | Duy | **Đã merge vào `dev`** | Đã mở khóa nhánh `blueprinted` (`is_ready`). |
| `I-W4MVP10-PR61-PR30` | **PR #61** & **PR #30** | Duy, Quỳnh | **Đã merge vào `dev`** | Đã sẵn sàng Stage 2 snapshot & preferences. |
| `I-W4MVP10-PR59` | **PR #59** (`feat/w4-mvp-04-stage3-review-ui`) | Bội Anh | **Đã merge vào `dev`** (`035ce45`) | Đã mở khóa `failed -> /stage2` và Stage 3 path cleanup. |
| `I-W4MVP10-PR71` | **PR #71** (`feat/w4-mvp-06-finalize-preview-ui`) | Bội Anh | **Đã merge vào `dev`** (`03f7e77`) | Đã mở `STAGE3_PREVIEW_ROUTE` + `'reviewed'`; PR #66 đã đồng bộ conflict và mở lại nút sang Export. |
| `I-W4MVP10-PR69` | **PR #69** (`feat/w4-mvp-09-export-download`) | Philip | **Đã merge vào `dev`** (`a379ec1`) | Đã có `SessionExportPage` cho `EXPORT_ROUTE` ở mức `Local Ready`. |
| `I-W4MVP10-BE-LIVE` | **PR #49** (`W4-MVP-05`), **PR #58** (`W4-MVP-07`), **PR #63** (`W4-MVP-08`) + OPS `I08-11S` | Tâm, Hùng, Đạt | **Đang mở (Ready for review)** | **Không chặn merge route FE**, nhưng cần merge/bật env trước khi chạy **Integrated live E2E** ở `W4-MVP-13` (PR #74). |

---

## 3. Lộ trình commit thực tế trên nhánh

| Commit | SHA | Phạm vi và file thay đổi | Tình trạng |
|---|---|---|---|
| **1** | `0669182` | `docs(w4-mvp-10): plan resume integration phases and dependencies` — lập M2 plan và route matrix. | Hoàn thành |
| **2** | `9138377` | `feat(navigation): route failed sessions to stage 2 recovery and share stage paths` — mở `failed -> stage2Path`, gating `blueprinted`, chuẩn hóa path trong `Stage3ReviewPage.jsx`. | Hoàn thành |
| **Sync** | `7c838f8` | `Merge remote-tracking branch 'origin/dev' into feat/w4-mvp-10-resume-integration` — đồng bộ `dev@a379ec1` (gồm PR #71, #69), gỡ conflict `sessionDestination.test.js` giữ cả `failed` và `reviewed`. | Hoàn thành |
| **3** | `0be1305` | `feat(navigation): wire export route and unlock stage 3 preview export actions` — gắn `EXPORT_ROUTE` (`<SessionExportPage />`) trong `App.jsx`, mở `approved`/`exported` trong `sessionDestination.js`, mở lại `handleApprove` / `btn-goto-export` / `banner-btn-goto-export` trong `Stage3PreviewPage.jsx` và tests. | Hoàn thành |
| **4** | `47c4ae9` | `feat(navigation): add locked-session guards across stage 1-3 routes` — khóa chỉnh sửa và gắn điều hướng an toàn khi deep-link vào `Stage1Route.jsx`, `Stage2ConfigPage.jsx`, `Stage3ReviewPage.jsx` cho các trạng thái sau / khóa HTTP 423 + tests. | Hoàn thành |
| **5** | *(commit doc này)* | `docs(w4-mvp-10): record resume integration verification and smoke results` — cập nhật bằng chứng kiểm chứng, ma trận dependency và ranh giới bàn giao. | Đang hoàn tất |

---

## 4. Kết quả kiểm thử & Bàn giao (`Local Ready` tại code head `47c4ae9`)

### 4.1. Kiểm thử tự động đã chạy (sau chỉnh sửa code cuối cùng `47c4ae9`)
- **Toàn bộ frontend test suite (`node --test --test-concurrency=1` tại `frontend/`):** **478/478 PASS** (`0` fail, `0` cancelled, `0` skipped, `0` todo; thời gian `81.86s`).
  - Bao gồm các bộ test đã cập nhật/bổ sung trực tiếp trong phạm vi `W4-MVP-10`: `sessionDestination.test.js` (9 ca, đủ 10 trạng thái), `Stage3PreviewPage.test.js` (mở khóa Export + `handleApprove` $\rightarrow$ `/export`), `Stage1SourcePanel.test.js` (deep-link `reviewed`/`approved`/`exported`), `Stage2ConfigPage.test.js` (deep-link khóa `reviewed`/`approved`/`exported`), `Stage3Review.test.js` (deep-link khóa HTTP 423 `approved`/`exported`), và toàn bộ `SessionExportPage.test.js` / `exportController.test.js` / `exportService.test.js` từ `dev`.
- **Static analysis (`npm run lint` — `eslint . --max-warnings 0`):** **exit `0`** (`0` errors, `0` warnings).
- **Production build (`npm run build` — `vite build`):** **exit `0`** (`1916 modules transformed`, built in `18.25s`).
- **Git hygiene (`git diff --check`):** sạch.

### 4.2. Giới hạn & Bước tiếp (`Integrated`)
- **Trạng thái nghiệm thu:** Đạt **`Local Ready`** ở tầng điều hướng, route guard và component unit/integration tests trên dữ liệu mock/adapter.
- **Phần chưa chạy trên nhánh này:** Live end-to-end Browser Smoke qua Docker stack với API thật của S07 (**PR #49**) và Export Storage (**PR #58**, **PR #63**, OPS `I08-11S`).
- **Bàn giao:** Sẵn sàng merge vào `dev` để ghép cùng `#49`, `#58`, `#63` thành candidate tích hợp phục vụ **W4-MVP-13 (`PR #74` — `@nhatquynh1107`)** chạy kiểm chứng live 10 trạng thái và Golden E2E G0/G1/G2.

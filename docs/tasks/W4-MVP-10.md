# W4-MVP-10 · M2 Kế hoạch tích hợp điều hướng và khôi phục phiên (Resume Integration)

- Phụ trách: Trung Anh (`philip-kkk`, TV1/FE1). Reviewer đề xuất: Bội Anh (`htbaax`) cho frontend, Duy (`johannguyen015`) cho contract trạng thái.
- Nguồn phân công: [W4_ASSIGNMENT](W4_ASSIGNMENT.md) và [W4_TASK_DETAIL](W4_TASK_DETAIL.md) mục W4-MVP-10.
- Workflow v0.1 proposed, bản tài liệu `7b7387f` có cập nhật INPUT-20261109. [Mẫu M2](../review/TEMPLATES.md#m2).
- Nhánh: `feat/w4-mvp-10-resume-integration`. Base lúc lập plan tích hợp: `74d2135` (`origin/dev`, đã bao gồm PR #60 nền route, PR #54 review snapshot, PR #52 durable error persistence).
- Hai đầu vào **Q11** (`I-W4MVP10-STATE` và `I-W4MVP10-FE2`) đã chốt xong ngày 12/11.

---

## 1. Phạm vi và Route Matrix Q11 (Đồng bộ toàn bộ 10 trạng thái)

Đã hoàn thành giai đoạn 1 (PR #60 nền route tại `74d2135`): định nghĩa tập trung 5 route (`STAGE1_ROUTE`, `STAGE2_ROUTE`, `STAGE3_ROUTE`, `STAGE3_PREVIEW_ROUTE`, `EXPORT_ROUTE`) và 5 helper builder (`stage1Path`, `stage2Path`, `stage3Path`, `stage3PreviewPath`, `exportPath`) trong `frontend/src/sessionPaths.js`, nối sẵn `draft -> /stage1`, `blueprinted/configured/generating -> /stage2`, `partial_generated/generated -> /stage3`.

Giai đoạn 2 (`feat/w4-mvp-10-resume-integration`): Mở khóa cuốn chiếu các trạng thái còn lại trong `pendingDestinations` (`failed`, `reviewed`, `approved`, `exported`) và tinh chỉnh gating/redirect theo tiến độ merge của các PR phụ thuộc.

| Trạng thái `session.status` | Đích chốt theo Q11 | Hiện trạng trên base `74d2135` | Đích trên `feat/w4-mvp-10-resume-integration` | Dependency mở khóa / PR phụ thuộc |
|---|---|---|---|---|
| `draft` | `/session/:sessionId/stage1` | **Đã nối** | Giữ `/stage1` | Hoạt động bình thường. |
| `blueprinted` | `/session/:sessionId/stage1` hoặc `/stage2` | Nối thẳng `/stage2` | - `blueprint_summary?.is_ready === true` $\rightarrow$ `/stage2`<br>- Chưa ready $\rightarrow$ `/stage1` | Chờ **PR #65** (`origin/fix/issue-44-confirm-before-blueprint`, Issue #44) merge vào `dev`. |
| `configured`, `generating` | `/session/:sessionId/stage2` | **Đã nối** | Giữ `/stage2` | `PR #30` bổ sung `generation-snapshot` & SSE resume đầy đủ hơn. |
| `failed` | `/session/:sessionId/stage2` | **Giữ `pendingDestinations` + notice** | Nối sang `/stage2` (Recovery View) | Chờ **PR #59** (Recovery View ở `Stage2ConfigPage.jsx` + `generation_error_code` từ PR #52) merge vào `dev`. |
| `partial_generated`, `generated` | `/session/:sessionId/stage3` | **Đã nối** | Giữ `/stage3`, chuẩn hóa điều hướng nội bộ | Sau khi **PR #59** merge, chuẩn hóa 3 lệnh `navigate` hardcode sang `sessionPaths.js`. `partial_generated` dùng `review/snapshot` (PR #54) mở `read_only` + nút sinh bù. |
| `reviewed` | `/session/:sessionId/stage3/preview` | **Giữ `pendingDestinations` + notice** | Nối sang `/stage3/preview` và đăng ký route trong `App.jsx` | Chờ màn S07 (**W4-MVP-06**) + **PR #49** (`GET /finalize/preview`, `POST /finalize/shuffle`) + **PR #61** (`PATCH /ordering-preferences`). |
| `approved`, `exported` | `/session/:sessionId/export` | **Giữ `pendingDestinations` + notice** | Nối sang `/export` và đăng ký route trong `App.jsx` | Chờ màn Export (**W4-MVP-09**) và Export API (**PR #58 / #63**); bổ sung guard khóa chỉnh sửa ở Stage 1–3. |
| Status lạ (`unknown`) | Ở lại Dashboard + notice an toàn | **Đã giữ** | Giữ fallback an toàn | Tránh lỗi điều hướng hoặc trắng trang. |

> **Nguyên tắc an toàn:** Không gỡ bỏ một trạng thái khỏi `pendingDestinations` nếu route/màn hình đích chưa được đăng ký trong `App.jsx` (tránh bị wildcard route đá về `/login`).

---

## 2. Đầu vào và Dependency (`I-...` theo chuẩn WORKFLOW v0.1)

### 2.1. Đầu vào hợp đồng đã chốt
| ID | Cung cấp → Nhận | Nội dung đã chốt | Trạng thái |
|---|---|---|---|
| `I-W4MVP10-STATE` | Duy (`johannguyen015`) → TV1/W4-MVP-10 | Dùng `GET /api/sessions/{id}` (`status`, `generation_config.n_versions`, `exam_versions[].is_finalized`, `blueprint_summary.is_ready`, `generation_error_code`) + hợp đồng `GET /finalize/preview` (`PR #49`), `generation-snapshot`/`retry-generation` (`PR #30`), `review/snapshot` (`PR #54`), Export artifact (`Q09/Q10`). | **Đã chốt** (11/11) |
| `I-W4MVP10-FE2` | Bội Anh (`htbaax`) → TV1/W4-MVP-10 | `partial_generated` mở `/stage3` dạng `read_only` + nút sinh bù cấp phiên; `reviewed` mở `/stage3/preview` (S07); `approved`/`exported` điều hướng sang `/export`; FE2 bổ sung Stage 2 `failed` Recovery View. | **Đã chốt** (12/11) |

### 2.2. Danh sách PR phụ thuộc mở khóa code
| ID phụ thuộc | PR / Task | Phụ trách | Tình trạng | Mở khóa trên `feat/w4-mvp-10-resume-integration` |
|---|---|---|---|---|
| `I-W4MVP10-PR52-PR54` | **PR #52** & **PR #54** | Duy | **Đã merge vào `dev`** (`294c69a`, `21887c1`) | Sẵn sàng cho `generation_error_code` và review snapshot. |
| `I-W4MVP10-PR65` | **PR #65** (`fix/issue-44-confirm-before-blueprint`) | Bội Anh | Đang mở (head `98d7f11`) | Mở khóa phân nhánh gating cho `blueprinted` (`is_ready`). |
| `I-W4MVP10-PR59` | **PR #59** (`feat/w4-mvp-04-stage3-review-ui`) | Bội Anh | Đang mở (head `a6e359d`) | Mở khóa `failed -> /stage2` và chuẩn hóa path Stage 3. |
| `I-W4MVP10-PR30` | **PR #30** (`feat/w4-mvp-02-generation-contract-adapter`) | Quỳnh | Đang mở | Kiểm thử live E2E snapshot recovery và session retry. |
| `I-W4MVP10-S07` | **W4-MVP-06** + **PR #49** + **PR #61** | Bội Anh, Tâm, Duy | Đang mở / Đang code | Mở khóa `reviewed -> /stage3/preview`. |
| `I-W4MVP10-EXPORT` | **W4-MVP-09** + **PR #58 / #63** | Philip, Hùng | Đang mở / Đang code | Mở khóa `approved`, `exported -> /export`. |

---

## 3. Kế hoạch commit theo từng đợt mở khóa

| Commit | Message dự kiến | Phạm vi và file thay đổi | Điều kiện cần (Pre-condition) |
|---|---|---|---|
| **1** | `docs(w4-mvp-10): plan resume integration phases and dependencies` | `docs/tasks/W4-MVP-10.md`: Ghi nhận lộ trình tích hợp, route matrix 10 trạng thái và bảng dependency `I-...`. | Sẵn sàng ngay trên base `74d2135`. |
| **2** | `feat(navigation): route failed sessions to stage 2 recovery and share stage paths` | - `sessionDestination.js` & `.test.js`: xóa `'failed'` khỏi `pendingDestinations`, nối `failed` sang `stage2Path`; chuẩn hóa phân nhánh `blueprinted` (`is_ready`).<br>- `Stage2ConfigPage.jsx`: dùng `stage1Path` cho `onReturnToStage1`.<br>- `Stage3ReviewPage.jsx`: dùng `stage2Path` và `stage3PreviewPath` từ `sessionPaths.js`. | **PR #65** và **PR #59** đã merge vào `dev`. |
| **3** | `feat(navigation): wire reviewed status and stage 3 preview route` | - `App.jsx`: đăng ký `STAGE3_PREVIEW_ROUTE` trong `<ProtectedRoute>`.<br>- `sessionDestination.js` & `.test.js`: xóa `'reviewed'` khỏi `pendingDestinations`, nối sang `stage3PreviewPath`. | Màn S07 (**W4-MVP-06**) và API **PR #49 / #61** sẵn sàng. |
| **4** | `feat(navigation): wire approved and exported sessions to export route` | - `App.jsx`: đăng ký `EXPORT_ROUTE` trong `<ProtectedRoute>`.<br>- `sessionDestination.js` & `.test.js`: xóa `'approved'`, `'exported'` khỏi `pendingDestinations`, nối sang `exportPath`.<br>- `Stage1Route.jsx` & guards: khóa chỉnh sửa / auto-redirect khi deep-link vào Stage 1–3 với phiên đã duyệt/xuất. | Màn Export (**W4-MVP-09**) và API Export (**PR #58 / #63**) sẵn sàng. |
| **5** | `docs(w4-mvp-10): record resume integration verification and smoke results` | `docs/tasks/W4-MVP-10.md`: cập nhật kết quả kiểm thử unit/integration và biên bản Browser Smoke live. | Hoàn tất tích hợp toàn bộ các màn. |

---

## 4. Kế hoạch kiểm thử

- **Unit & Integration Tests (Targeted):**
  - Chạy bộ test resolver và các entry point:
    `node --test --test-concurrency=1 src/features/dashboard/sessionDestination.test.js src/features/stage1-ingestion/Stage1SourcePanel.test.js src/features/stage2-config/Stage2ConfigPage.test.js src/features/stage3-review/Stage3Review.test.js src/services/sessions.test.js`
  - Đảm bảo 100% test pass ở từng commit.
- **Toàn bộ frontend tests:**
  - `node --test --test-concurrency=1` từ `frontend/` (hiện tại `745/745 PASS`).
- **Static analysis & Build:**
  - `npm run lint` (`eslint . --max-warnings 0`)
  - `npm run build` (`vite build`)
- **Browser Smoke:**
  - Kiểm thử trực tiếp luồng resume trên Docker stack local theo từng trạng thái phiên (`draft`, `blueprinted`, `configured`, `generating`, `failed`, `partial_generated`, `generated`, `reviewed`, `approved`, `exported`).

# W4-MVP-10 · M2 nền điều hướng

- Phụ trách: Trung Anh (`philip-kkk`, TV1/FE1). Reviewer đề xuất: Bội Anh cho frontend, Duy cho contract trạng thái. Chờ xác nhận reviewer.
- Nguồn phân công: [W4_ASSIGNMENT](W4_ASSIGNMENT.md) tại `d4350c0` và [W4_TASK_DETAIL](W4_TASK_DETAIL.md) mục W4-MVP-10.
- Workflow v0.1 proposed, bản tài liệu `7b7387f` có cập nhật INPUT-20261109. [Mẫu M2](../review/TEMPLATES.md#m2).
- Nhánh `feat/w4-mvp-10-route-foundation`. Base lúc lập plan `294c69a`, đã merge `origin/dev` (`21887c1`, gồm PR #54 `review-snapshot`). [PR #60](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/60).
- Mốc FE-H1 theo phân công: 10/11 18:00 UTC+7, đã qua. FE-H2 và kiểm live: 12/11 12:00 UTC+7. Hai đầu vào **Q11** (`I-W4MVP10-STATE` và `I-W4MVP10-FE2`) đã chốt xong ngày 12/11.

## Phạm vi triển khai và Route Matrix Q11 đã chốt

Đã chuẩn hóa dùng chung đường dẫn Stage 1/2/3, Stage 3 Preview và Export qua `frontend/src/sessionPaths.js`, đồng bộ `STAGE3_ROUTE` trong `App.jsx` và `stage3Path` trong `Stage2ConfigPage.jsx`, và mở điều hướng `partial_generated`, `generated` từ Dashboard sang Stage 3 (`35411a0`).

| Trạng thái `session.status` | Đích chốt theo Q11 | Trạng thái trên `feat/w4-mvp-10-route-foundation` (`35411a0`) | Dependency mở khóa đích / hành vi live |
|---|---|---|---|
| `draft` | `/session/:sessionId/stage1` | **Đã nối** | Đang hoạt động. |
| `blueprinted` | `/session/:sessionId/stage1` hoặc `/session/:sessionId/stage2` | **Đang nối `/stage2`** *(giữ nguyên để tránh xung đột với PR #65)* | Chốt cuối theo **PR #65** (Issue #44): chỉ sang `/stage2` khi `blueprint_summary?.is_ready === true`, ngược lại giữ ở `/stage1`. |
| `configured`, `generating` | `/session/:sessionId/stage2` | **Đã nối** | Đang hoạt động; `PR #30` bổ sung `generation-snapshot` & SSE resume đầy đủ hơn. |
| `partial_generated`, `generated` | `/session/:sessionId/stage3` | **Đã nối** | Đích Stage 3 đã đăng ký trong `App.jsx`. Trên **PR #59** (adapt snapshot **PR #54**): `partial_generated` mở `read_only: true` + nút sinh bù cấp phiên (`POST /retry-generation` ở **PR #30**); `generated` duyệt/tạo lại từng câu bình thường. |
| `reviewed` | `/session/:sessionId/stage3/preview` | **Giữ `pendingDestinations` + notice** | Chờ màn S07 trong **PR #59** + **PR #49** (`GET /finalize/preview`, `POST /finalize/shuffle`) + **PR #61** (`PATCH /ordering-preferences` flat payload `{ shuffle_questions, shuffle_options }`). |
| `approved`, `exported` | `/session/:sessionId/export` | **Giữ `pendingDestinations` + notice** | Chờ màn Export (**W4-MVP-09**) và Export API (**PR #58 / #63**); giữ `approved` khóa chỉnh sửa ở Stage 1–3. |
| `failed` | `/session/:sessionId/stage2` | **Giữ `pendingDestinations` + notice** | Chờ bổ sung nhánh Recovery View ở `Stage2ConfigPage.jsx` + `generation_error_code` từ FE2 và **PR #30** (`retry-generation`, `generation-snapshot`). |
| Status ngoài các nhóm trên | Ở lại Dashboard + thông báo chưa hỗ trợ | **Đã giữ** | Không điều hướng sai đích. |

## Thứ tự triển khai

| Lượt / file dự kiến | Đầu ra | Input đã có | Cách kiểm |
|---|---|---|---|
| 1. `sessionDestination.js`, `App.jsx`, `Stage1Route.jsx` nếu cần | Dùng chung định nghĩa đường dẫn Stage 1/2 ở những nơi khai báo và tạo URL. Giữ encode ID, luồng `stage1/new` và handoff cùng session. | Route và caller hiện hữu trên `d4350c0`. | Test resolver cho bốn trạng thái có đích và cả các trạng thái đang trả notice. Kiểm Stage 1 mới, Stage 1 đã confirm và Stage 2 direct URL. |
| 2. `DashboardRoute.jsx`, `sessionDestination.test.js`, `Stage1SourcePanel.test.js` | Kiểm lại guard hiện có qua entry point thật. Chỉ sửa handler/guard khi kiểm tái hiện được sai lệch trong phạm vi hiện tại. | `createSessionOpener` đã có abort, revision và kiểm account. `ProtectedRoute` đã phân biệt checking, profile pending và signed out. | Mở hai session liên tiếp, đăng xuất hoặc đổi account khi GET còn pending. Chỉ phiên và account hiện hành được cập nhật hoặc điều hướng. Khi profile đang xác minh, giữ URL và chặn màn protected. |
| 3. Kiểm trên build của nhánh | Gói kết quả cho phần nền điều hướng và danh sách trạng thái còn chờ. | Fixture theo shape API hiện hành. Local stack dùng cho smoke nếu chạy được trên đúng build. | Targeted Node tests, `npm run lint`, `npm run build` từ `frontend/`. Browser smoke Dashboard → Stage 1/2, F5, deep-link và đăng xuất. Ghi fixture và API thật theo môi trường thực chạy. |

Tận dụng test hiện có cho double-click, lỗi GET, response về muộn và handoff Stage 1. Chỉ thêm ca hồi quy nếu entry point đang sửa có hành vi chưa được suite hiện tại kiểm. Bước đầu dùng `node --test src/features/dashboard/sessionDestination.test.js src/features/stage1-ingestion/Stage1SourcePanel.test.js src/services/sessions.test.js` từ `frontend/`. Nếu thay đổi chạm hành vi Stage 2, chạy thêm `src/features/stage2-config/Stage2ConfigPage.test.js`.

## Kế hoạch commit cho PR #60

| Thứ tự | Commit dự kiến | Phạm vi và điểm chốt |
|---|---|---|
| 1 | `docs(w4-mvp-10): add route foundation plan` | Chỉ `docs/tasks/W4-MVP-10.md`. Ghi phạm vi, route matrix đã có căn cứ, các đầu vào Q11 và kế hoạch kiểm. Rà diff và link trước khi commit. |
| 2 | `refactor(navigation): share stage 1 and stage 2 paths` | Đổi định nghĩa route và các caller trong cùng commit để build chạy được ở từng mốc. Giữ các URL và hành vi hiện có. Chạy nhóm targeted tests, thêm `Stage2ConfigPage.test.js` nếu đổi nút quay lại Stage 1, rồi lint/build. |
| Nếu phát hiện lỗi | `fix(navigation): <hành vi tái hiện được>` | Tách lỗi điều hướng hoặc response về muộn khỏi commit refactor. Chỉ sửa file gây lỗi và thêm ca hồi quy nếu suite chưa bao phủ. Đặt tên commit sau khi có ca tái hiện. |
| Cuối | `docs(w4-mvp-10): record route foundation checks` | Cập nhật M2 với kết quả theo SHA, phạm vi browser smoke đã chạy, phần còn chờ Q11 và đầu ra cho nhánh Resume. Chỉ ghi kết quả đã kiểm. |

### Phạm vi file của commit điều hướng

Các đường dẫn dưới đây tính từ `frontend/src/`.

| File | Thay đổi dự kiến |
|---|---|
| `sessionPaths.js` (mới, đề xuất) | Chứa route pattern và hàm tạo URL Stage 1/2 dùng chung. Giữ tham số `sessionId`, encode đúng một lần và hỗ trợ `new` ở Stage 1. |
| `App.jsx` | Dùng route pattern chung cho hai đăng ký Stage 1/2 trong `ProtectedRoute`. |
| `features/dashboard/sessionDestination.js` | Dùng hàm tạo URL chung cho bốn trạng thái đã xác định. Giữ fallback và notice hiện tại. |
| `features/dashboard/DashboardRoute.jsx` | Dùng cùng hàm tạo URL cho nút tạo phiên mới. Logic mở phiên vẫn đi qua `createSessionOpener`. |
| `features/stage1-ingestion/Stage1Route.jsx` | Dùng hàm tạo URL khi nhận ID phiên mới. Handoff sau confirm tiếp tục đọc đích từ resolver, giữ guard account/session và `replace`. |
| `features/stage2-config/Stage2ConfigPage.jsx` | Nếu đổi caller này trong commit, chỉ dùng hàm tạo URL Stage 1 cho nút quay lại nguồn. Giữ nguyên điều kiện hiển thị nút. |

Chạy lại `sessionDestination.test.js`, `Stage1SourcePanel.test.js` và `sessions.test.js` để kiểm hợp đồng hành vi hiện tại. Chỉ sửa các file test khi cần bao phủ ca hồi quy hoặc entry point đã thay đổi. `ProtectedRoute.jsx` và `services/sessions.js` là điểm cần kiểm qua luồng hiện có. Hai URL Stage 2 trong `Stage3ReviewPage.jsx` thuộc màn Bội Anh đang bàn giao qua PR #59 và sẽ được đối chiếu trong nhánh Resume. Mọi thay đổi mapping theo Q11 cần căn cứ từ phản hồi provider trước khi bổ sung vào plan.

## Đầu vào Q11 đã chốt

[Thread Q11 trên PR #60](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/60#issuecomment-6792990184) đã nhận đủ phản hồi xác nhận từ Duy (`johannguyen015`, 11/11) và Bội Anh (`htbaax`, chốt cuối 12/11):

| ID | Cung cấp → nhận | Nội dung đã chốt | Trạng thái |
|---|---|---|---|
| `I-W4MVP10-STATE` | Duy → TV1/W4-MVP-10 | Dùng `GET /api/sessions/{id}` (`status`, `generation_config.n_versions`, `exam_versions[].is_finalized`) + hợp đồng `GET /finalize/preview` (`PR #49`), `generation-snapshot`/`retry-generation` (`PR #30`), `review/snapshot` (`PR #54`), Export artifact tách màn Export (`Q09/Q10`). | **Đã chốt** (`11/11`) |
| `I-W4MVP10-FE2` | Bội Anh → TV1/W4-MVP-10 | `partial_generated` mở `/stage3` dạng `read_only` + nút sinh bù cấp phiên (`POST /retry-generation` về `/stage2` SSE); `reviewed` mở `/stage3/preview` (S07 có 2 checkbox `ordering_preferences` + nút xáo toàn bộ đề `POST /finalize/shuffle`); `approved`/`exported` điều hướng sang `/export`; FE2 nhận bổ sung Stage 2 `failed` Recovery View. | **Đã chốt** (`12/11`) |

Tích hợp nối live cho `reviewed`, `failed`, `approved`/`exported` và tinh chỉnh UX sau W4 nằm ở lượt merge/nhánh tích hợp kế tiếp khi các PR phụ thuộc (`#65`, `#59`, `#30`, `#49`, `#61`, Export `#58/#63`/W4-MVP-09) đã vào `dev`.

## Bàn giao & Kiểm thử

- Đã triển khai nền route Stage 1/2/3/Preview/Export ở `sessionPaths.js` và nối `partial_generated`/`generated` $\rightarrow$ `/stage3` tại commit `35411a0` (trên nhánh đã merge `origin/dev@21887c1`).
- Kiểm targeted tại `35411a0` (`node --test --test-concurrency=1 src/features/dashboard/sessionDestination.test.js src/features/stage1-ingestion/Stage1SourcePanel.test.js src/features/stage2-config/Stage2ConfigPage.test.js src/features/stage3-review/Stage3Review.test.js src/services/sessions.test.js`): **111/111 PASS** (0 fail, 0 skipped).
- Kiểm toàn bộ frontend test suite tại `35411a0` (`node --test --test-concurrency=1` từ `frontend/`): **745/745 PASS** (0 fail, 0 skipped).
- Kiểm tĩnh & build tại `35411a0`: `npm run lint` (`eslint . --max-warnings 0`) **PASS**; `npm run build` (`vite build`) **PASS** (1910 modules, `dist/assets/index-7o-FIu99.js` 985.13 kB).
- Tự review diff: mọi builder trong `sessionPaths.js` encode `sessionId` đúng một lần qua helper dùng chung; `Stage1Route.jsx` giữ nguyên điều kiện chỉ auto-redirect khi `path === stage2Path(detail.id)`; không sửa vào `Stage3ReviewPage.jsx` hay cụm `blueprinted` của PR #65/#59; giữ các trạng thái chưa có màn/PR trên `dev` (`reviewed`, `approved`, `exported`, `failed`) trong `pendingDestinations` để tránh fallback về `/login`.
- Browser smoke trực tiếp trên Docker/app local với đầy đủ màn Stage 3 Preview / Export / `failed` recovery tiếp tục thực hiện sau khi các PR phụ thuộc merge vào `dev`.

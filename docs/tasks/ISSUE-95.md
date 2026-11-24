# ISSUE-95 — Plan và bàn giao Redesign UI/UX Giai đoạn 3 (Review, Final Preview & Export)

> **Lượt sửa `fix/stage3-ui`:** plan ngày 23/11 tại mục 6; checkpoint code C2 ngày 24/11 tại mục 6.10; phản hồi Duy/đối chiếu PR #110 tại mục 6.11; cập nhật htbaax và ranh giới chốt contract tại mục 6.12. Bàn giao mục 5 là lịch sử của lượt #95; test/build không thay bằng chứng visual của S06. C3/C4 và phần API contract chưa được nhận là hoàn tất từ việc triển khai C2.

- **Nguồn giao việc:** [Issue #95](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/95) (`[UI/UX][Giai đoạn 3] Thiết kế lại màn hình duyệt đề, xem trước bản cuối & xuất file`), đối chiếu tại `dev@e7e0088` ngày 20/11/2026.
- **Phụ trách:** Trung Anh (`philip-kkk`, FE1).
- **Reviewer đề xuất:** Bội Anh (`htbaax`, `#94` / Stage 3 logic), Tâm (`AI-WFox`, `#93` / design tokens), Hùng (`benalexx007`, `#92` / Export v2), Duy (`johannguyen015`, điều phối tích hợp & PR #91).
- **Repo / Nhánh:** `isomorphic-exam-synthesizer`, nhánh `feat/issue-95-stage3-redesign` rẽ từ `dev@e7e0088` *(đã bao gồm `PR #63`, `PR #78`, `PR #84`, `PR #82`, `PR #91`, `PR #101`)*.
- **Workflow:** v0.1 + INPUT-20261109 *(theo [TEMPLATES M2](../review/TEMPLATES.md#m2))*.

---

## 1. Mình cần làm gì?

### 1.1. Hành vi & tiêu chí đạt
Thiết kế lại giao diện và trải nghiệm người dùng cho toàn bộ **Giai đoạn 3** trên 3 màn hình:
1. **Stage 3 Review** (`frontend/src/features/stage3-review/Stage3ReviewPage.jsx`):
   - Cải thiện bố cục danh sách câu theo mã đề, thanh điều hướng câu và trạng thái đang chọn; hiển thị rõ câu hỏi, options, đáp án, lời giải và công thức Toán/LaTeX.
   - Phân biệt trực quan 4 trạng thái: chờ duyệt, đã duyệt, đang sinh lại và thiếu kết quả (`partial_generated`).
   - Thiết kế lại nhóm hành động `Duyệt biến thể` / `Tạo lại` / `Khôi phục đề gốc` (Revert) và phản hồi đang xử lý / thành công / thất bại; hiển thị tiến độ duyệt và điều kiện chuyển sang Final Preview.
   - **Bảo toàn cơ chế Issue #85 (`PR #91`):** đối soát candidate identity qua `id` / `candidate_id` / `question_id` (`isVariantApproved`, `extractApprovedIds`), không xác nhận Accept cho candidate lỗi thời, giữ guard `isReviewReadOnly` vs `isFinalLocked` và phân loại `409 ERR_SHUFFLE_REQUIRED` / `423`.
2. **Stage 3 Final Preview** (`frontend/src/features/stage3-preview/Stage3PreviewPage.jsx` + helper đọc preferences ở `frontend/src/services/stage3PreviewService.js`):
   - **Chỉ hiển thị một điều khiển `shuffle_questions`** tại Final Preview trước khi chốt/phê duyệt; **không hiển thị** điều khiển `shuffle_options`.
   - Phiên mới khởi tạo `OFF/OFF` ở Stage 2 (`#94`) và người dùng quyết định `shuffle_questions` tại Final Preview.
   - Phiên cũ có `shuffle_options: true` phải **giữ nguyên** giá trị này khi áp dụng `shuffle_questions` và hiển thị **thông báo chỉ đọc** cho biết xáo trộn đáp án vẫn đang được bật; không âm thầm đặt về `false` hoặc cập nhật khi F5/mở lại trang.
   - Nếu **không đọc được `shuffle_options` đáng tin cậy** từ backend (`ordering_preferences` thiếu hoặc không phải boolean), **khóa thao tác ghi** preferences/shuffle và yêu cầu đối soát trạng thái trước.
   - Trình bày rõ chế độ **Đề học sinh** (ẩn đáp án, nhãn gốc, lời giải, bảng đáp án) và **Chế độ giáo viên** (hiện đáp án, lời giải, bảng đáp án); phân biệt trạng thái chưa finalized / finalized / approved-locked.
   - **Bảo toàn cơ chế Issue #86 (`PR #91`):** khi phản hồi shuffle thất lạc hoặc không xác định (`shuffleRecovery === 'unknown'`), đối soát trạng thái read-only từ backend trước khi cho phép thao tác ghi tiếp; giữ reconcile `approveError` từ fresh snapshot.
3. **Export** (`frontend/src/features/export/SessionExportPage.jsx`):
   - Chuẩn hóa đường dẫn quay lại Preview bằng `stage3PreviewPath(sessionId)` từ `frontend/src/sessionPaths.js` (thay cho template string hardcode).
   - Chỉ hiển thị hành động tạo và tải **một gói ZIP duy nhất** qua `exportController` / `exportService` hiện có; không có tùy chọn chọn/tải lẻ PDF/TeX/Markdown.
   - Đồng bộ mô tả nội dung gói ZIP theo **`w4-export-v2` (`#92` / `PR #104`)**: mỗi mã đề gồm 1 PDF, 1 TeX và 1 Markdown (đề $\rightarrow$ ma trận đáp án $\rightarrow$ lời giải).
   - Không tạo gói trùng khi gói hợp lệ đã sẵn sàng; giữ chống double-click, cơ chế reconcile lỗi trước retry và không hiển thị/log signed URL hoặc dữ liệu người dùng khác.

### 1.2. Ngoài phạm vi
- Không sửa xáo trộn ở Stage 2 (thuộc `#94`); không thêm điều khiển `shuffle_options` ở bất kỳ Stage nào.
- Không thêm variation selector, tính năng generation mới, hoặc nút `"Đánh dấu đã rà từng bản"` / `"Trộn lại từng mã"` / `"Tải PDF từng mã lẻ"`.
- Không sửa backend review/finalize/shuffle/export, thuật toán shuffler, answer/solution mapping, RPC/RLS, hay logic `exportController.js` / `exportService.js` / `stage3Service.js` / `App.jsx` / `sessionDestination.js`.
- Không viết lại design system (`index.css`).

### 1.3. Đối chiếu template `ui-walkthrough` ↔ Sản phẩm thật (Tránh lệch UX & lệch tính năng)
Dùng [UI walkthrough](../ui-walkthrough/README.md) (`PREVIEW.html` các màn S06/S07/S08) và pattern header của Stage 1 (`PR #100` / `#93`) làm khuôn mẫu bố cục/thẩm mỹ, nhưng khóa chặt ranh giới nghiệp vụ theo bảng sau:

| Vùng màn hình | Kế thừa UX / Bố cục từ `ui-walkthrough` & `PR #100` | Ranh giới tính năng thật của `#95` (không copy phần giả lập của draft) |
|---|---|---|
| Header & Tokens | Header có link về `Thư viện đề`, badge `Bước 3/3 · ...`, badge trạng thái ngữ nghĩa và pills `Môn`/`Khối`; dùng đúng tokens `.paper-ui` trong `frontend/src/index.css`. | Giữ `sessionPaths.js` hiện hành; không thêm theme switch hay menu drawer giả của demo. |
| Review (S06) | Thanh điều hướng câu (`1..M`) + tabs mã đề (`X/Y` đã duyệt), đối chiếu 2 cột (`Câu gốc chỉ đọc` $\leftrightarrow$ `Biến thể`), nhóm nút thao tác cạnh nhau, sticky footer hiển thị tiến độ và CTA chuyển sang Final Preview. | Giữ `isVariantApproved` (`#85`), `accept` / `regenerate` / `revert`, bộ lọc, `Sinh bổ sung câu thiếu` (`partial_generated`), `409`/`423`; không thêm bộ đếm giờ sinh nền giả. |
| Final Preview (S07) | Trình bày tờ đề đọc sạch, nút chuyển **Đề học sinh** $\leftrightarrow$ **Hiện đáp án và lời giải**, hộp xác nhận khóa vĩnh viễn không hoàn tác (`Phê duyệt & Khóa đề`). | Chỉ có **1 bước finalize cấp phiên** với **duy nhất điều khiển `shuffle_questions`** (ẩn `shuffle_options`, bảo toàn giá trị cũ + thông báo chỉ đọc nếu `true`, chặn ghi nếu chưa đọc tin cậy); không có nút rà từng bản hay trộn lại từng mã. |
| Export (S08) | Card tóm tắt phiên đã khóa, trạng thái sẵn sàng/đang xử lý/lỗi rõ ràng, nút xem lại bản đã duyệt và quay về Dashboard. | Chỉ hỗ trợ **1 nút tạo/tải 1 gói ZIP** qua Export API thật (`w4-export-v2`), không tách nút tải PDF từng mã. |

### 1.4. Hiện đã có trên `dev@e7e0088`
- Toàn bộ logic nghiệp vụ & bảo vệ `#85`, `#86`, `PR #84`, `PR #69`, `PR #66`, token `paper-ui` (`index.css`) và `sessionPaths.js` đã có sẵn trên `dev@e7e0088`.
- Chưa có commit UI redesign cho Stage 3 (`#95`) — nhánh hiện mới ở Commit 1 lập plan M2.

---

## 2. File và thứ tự triển khai

| Lượt | File dự kiến | Mục đích sửa | Đầu vào cần trước | Cách kiểm |
|---|---|---|---|---|
| **1** | `docs/tasks/ISSUE-95.md` *(commit này)* | Lập plan M2, đối chiếu `ui-walkthrough` và bảng phụ thuộc `I-95-...`. | `dev@e7e0088`, Issue #95, `docs/ui-walkthrough/` | Rà liên kết Markdown & `git diff --check`. |
| **2** | `frontend/src/features/stage3-review/Stage3ReviewPage.jsx`, `Stage3Review.test.js` | Redesign bố cục Review theo mẫu S06 & header `Bước 3/3`, navigator theo câu, trạng thái 4 loại, giữ nguyên `#85`/`revert`/`partial`/`409`/`423`. | `I-95-TOKENS`, `I-95-PR91` | `node --test --test-concurrency=1 src/features/stage3-review/Stage3Review.test.js`, `npm run lint` |
| **3** | `frontend/src/services/stage3PreviewService.js`, `stage3PreviewService.test.js`, `frontend/src/features/stage3-preview/Stage3PreviewPage.jsx`, `Stage3PreviewPage.test.js` | Bỏ `checkbox-shuffle-options`, chỉ giữ `shuffle_questions`, thêm guard đọc `shuffle_options` đáng tin cậy + thông báo chỉ đọc khi `true`, redesign tờ đề S07, giữ `#86`. | `I-95-TOKENS`, `I-95-STAGE2`, `I-95-PR91` | `node --test --test-concurrency=1 src/services/stage3PreviewService.test.js src/features/stage3-preview/Stage3PreviewPage.test.js`, `npm run lint` |
| **4** | `frontend/src/features/export/SessionExportPage.jsx`, `SessionExportPage.test.js` | Dùng `stage3PreviewPath(sessionId)`, chuẩn hóa card/header `Bước 3/3` theo S08 và mô tả gói ZIP `w4-export-v2` (chỉ ZIP duy nhất). Không sửa `exportController.js`. | `I-95-TOKENS`, `I-95-EXPORT-V2` | `node --test --test-concurrency=1 src/features/export/SessionExportPage.test.js src/features/export/exportController.test.js src/services/exportService.test.js`, `npm run lint` |
| **5** | `docs/tasks/ISSUE-95.md`, `docs/ui-walkthrough/pr95-stage3/` *(nếu chụp được local)* | Chạy full suite (`npm test`, `npm run lint`, `npm run build`), kiểm tra responsive `1440×900` & `375×812` + keyboard focus, cập nhật bằng chứng & giới hạn. | Hoàn tất lượt 2–4 | `npm test`, `npm run lint`, `npm run build`, `git diff --check` |

---

## 3. Đầu vào và câu hỏi — giải đáp trên Draft PR

| ID / yêu cầu gốc | Cung cấp → Nhận | Mục đích & điều kiện đủ dùng | Cần trước / ETA | Mức, bằng chứng đã có | Phần còn thiếu / bước tiếp |
|---|---|---|---|---|---|
| `I-95-TOKENS` ([PR #100](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/100)) | Tâm (`#93`) $\rightarrow$ Philip (`#95`) | Đồng bộ header `Bước X/3`, pills ngữ nghĩa và responsive tokens trên `index.css`. | Sẵn dùng từ code `index.css` trên `dev@e7e0088` & `PR #100`. | Đã đối chiếu `index.css` và `Stage1Route.jsx` trên `PR #100` (`ffcd8c7`). | Chờ Tâm review tính đồng nhất UI với Stage 1 ở lượt Ready. |
| `I-95-STAGE2` ([Issue #94](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/94)) | Bội Anh (`#94`) $\leftrightarrow$ Philip (`#95`) | Stage 2 bỏ cả 2 checkbox xáo trộn và khởi tạo `false/false`; Stage 3 Final Preview là nơi duy nhất chọn `shuffle_questions` và bảo toàn `shuffle_options` đã lưu. | Thống nhất trước khi merge đồng bộ Stage 2–3; ETA `TBD`. | Contract đã ghi rõ trong Issue #94 và Issue #95; API hiện tại trên `dev` không đổi. | Xác nhận trên Draft PR rằng Stage 2 (`#94`) không gửi ghi đè `ordering_preferences` sau khi user đã chỉnh ở Stage 3 hoặc khi reload. |
| `I-95-EXPORT-V2` ([PR #104](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/104)) | Hùng (`#92`) $\rightarrow$ Philip (`#95`) | Đồng bộ mô tả nội dung gói ZIP trên `SessionExportPage.jsx` theo cấu trúc cuối (`w4-export-v2`: mỗi mã đề 1 PDF, 1 TeX, 1 MD) và tránh xung đột `exportController.js`. | Trước lượt Commit 4 / Ready; ETA chờ merge PR #103/#104. | Đã review `PR #104` (`8dde84e`) và xác nhận `exportController.js` chỉ thêm `downloadGrant: null`. | Nhờ Hùng xác nhận mô tả ZIP text trên `SessionExportPage.jsx` khớp quyết định cuối `w4-export-v2`. |
| `I-95-PR91` ([PR #91](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/91)) | Duy (`dev@e7e0088`) $\rightarrow$ Philip (`#95`) | Bảo toàn logic `#85` (candidate identity ở Review) và `#86` (outcome-unknown recovery ở Preview). | **Đã có sẵn trên `dev@e7e0088`**. | Đã đọc diff `9305de5` trên `Stage3ReviewPage.jsx` và `Stage3PreviewPage.jsx`. | Không thay đổi cơ chế kiểm soát; giữ nguyên + chạy lại đủ regression tests. |

- **Nơi tổng hợp input duy nhất:** Bảng mục 3 này và các comment trao đổi trực tiếp trên Draft PR của nhánh `feat/issue-95-stage3-redesign`.
- **Output giao lại:** Giao diện Stage 3 thống nhất với `ui-walkthrough` & `PR #100`, bộ frontend tests (`Review` / `Preview` / `Export`), ảnh/đo responsive Desktop & Mobile và báo cáo giới hạn (phân biệt `Local Ready` với `Live E2E`).

---

## 4. Kế hoạch tự kiểm

- **Automated checks (trên mỗi lượt và tổng kết lượt 5):**
  - `node --test` (toàn bộ frontend suite, kiểm riêng không skip test `#85` và `#86`).
  - `npm run lint` (`eslint . --max-warnings 0`).
  - `npm run build` (`vite build`).
  - `git diff --check`.
- **Kịch bản trọng tâm cho `#95`:**
  1. Review: chuyển mã đề, navigator câu 1..M, lọc câu, đối chiếu 2 cột gốc–biến thể, duyệt/tạo lại/khôi phục gốc, câu đang sinh lại, `partial_generated`, `read_only`, `409 ERR_SHUFFLE_REQUIRED`, `423`.
  2. Final Preview: không có checkbox `shuffle_options`; phiên mới OFF/OFF chọn `shuffle_questions` gửi `shuffle_options: false`; phiên cũ `shuffle_options: true` hiện thông báo chỉ đọc & bảo toàn `true` khi bật/tắt `shuffle_questions`; F5 không tự PATCH/POST; thiếu/không đọc được `shuffle_options` đáng tin cậy $\rightarrow$ chặn ghi & yêu cầu đối soát `GET`; recovery `#86`; chế độ Học sinh (ẩn đáp án/lời giải/matrix) vs Giáo viên; khóa `approved`/`exported`.
  3. Export: chỉ 1 thao tác tạo/tải gói ZIP, mô tả đúng `w4-export-v2`, link quay lại `stage3PreviewPath(sessionId)`, chống double-click, xử lý lỗi không lộ raw URL/dữ liệu người dùng khác.
  4. Responsive & Accessibility: Desktop `1440×900`, Mobile `375×812`, tràn công thức KaTeX cục bộ (`scrollWidth <= clientWidth`), focus bàn phím trong tablist và dialog.
- **Giới hạn dự kiến khai báo minh bạch:** Unit/component tests chạy với mock API & JSDOM; không chạy backend/Supabase/Docker live E2E trên nhánh thuần UI này trừ khi thực hiện smoke bổ sung sau khi ghép cùng `PR #103/#104` và `#94`.

---

## 5. Bàn giao *(cập nhật sau lượt Commit 5 — Local Ready)*

- **Trạng thái hiện tại:** Hoàn tất cả **5 lượt commit** trên nhánh `feat/issue-95-stage3-redesign` (rẽ từ `dev@e7e0088`). Toàn bộ giao diện Giai đoạn 3 (Review, Final Preview, Export) đã được đồng bộ với `docs/ui-walkthrough/` (`S06`/`S07`/`S08`) và hệ token `.paper-ui` (`index.css`), bảo toàn toàn bộ cơ chế an toàn `#85`, `#86`, `partial_generated`, `409`/`423` và không chạm các file ngoài phạm vi (`backend/**`, `exportController.js`, `exportService.js`, `stage3Service.js`, `App.jsx`, `sessionDestination.js`, `index.css`).

### 5.1. Danh sách commit trên nhánh
1. `809dc5e` — `docs(issue-95): add M2 redesign plan aligned with ui-walkthrough` (`docs/tasks/ISSUE-95.md`)
2. `313975e` — `feat(stage3-review): align review workspace UX with ui-walkthrough (#95)` (`Stage3ReviewPage.jsx`, `Stage3Review.test.js`)
3. `3b1df06` — `feat(stage3-preview): restrict shuffle to question order and align preview UX with ui-walkthrough (#95)` (`stage3PreviewService.js`, `stage3PreviewService.test.js`, `Stage3PreviewPage.jsx`, `Stage3PreviewPage.test.js`)
4. `97b64db` — `feat(export): align ZIP export screen with ui-walkthrough S08 and w4-export-v2 (#95)` (`SessionExportPage.jsx`, `SessionExportPage.test.js`)
5. *(commit này)* — `docs(issue-95): update handoff verification results and limitations (#95)` (`docs/tasks/ISSUE-95.md`)

### 5.2. Kết quả kiểm tra đã chạy sau Commit 4
- **Full frontend test suite (`npm test`):** `563/563 PASS` (`2` suites, `0` fail, `0` skipped, `0` cancelled, `0` todo).
- **Stage 3 & Export targeted suite (`node --test --test-concurrency=1` trên 6 file test Review / Preview / Export):** `129/129 PASS` (`0` fail, `0` skipped, `0` cancelled, `0` todo), bao gồm các ca `#85`, `#86`, guard `shuffle_options` bất đồng bộ/cũ, `stage3PreviewPath(sessionId)` URL-encoded, mô tả `w4-export-v2`, kích thước gói ZIP và retry `failed`.
- **Lint (`npm run lint` — `eslint . --max-warnings 0`):** Exit `0` (0 lỗi, 0 cảnh báo).
- **Production build (`npm run build` — `vite build`):** Exit `0`, transform `1920` modules thành công trong `22.98s` (`dist/` sạch).
- **Static audit Responsive & Keyboard/ARIA (trong mã nguồn JSX đã build):**
  - Đã kiểm lớp bố cục responsive (`sm:`, `lg:`, `max-w-*`, `grid-cols-1 sm:grid-cols-2`, `w-full sm:w-auto`) và cô lập tràn công thức KaTeX/ma trận đáp án bằng `min-w-0 overflow-x-auto`.
  - Đã kiểm cấu trúc ngữ nghĩa/bàn phím: `role="tablist"`, `onKeyDown={handleTabKeyDown}`, `role="tab"` (`aria-selected`), `role="tabpanel"` (`tabIndex={0}`), `role="dialog"` (`aria-modal="true"`), `role="status"`, `role="alert"`.

### 5.3. Giới hạn & phần chưa xác minh (Minh bạch trước khi Merge / Ready)
- **Live E2E & Backend tích hợp:** Toàn bộ test sử dụng JSDOM và adapter/API mock; chưa chạy E2E với Supabase Auth, Stage 2 (`#94`) hoặc worker đóng gói ZIP (`PR #103`/`PR #104`).
- **Ảnh chụp trình duyệt thật (`docs/ui-walkthrough/pr95-stage3/`):** Chưa tạo ảnh chụp màn hình `1440×900` và `375×812` trên browser thật do route `/session/:id/stage3/*` và `/session/:id/export` được bảo vệ bởi Supabase session trong `App.jsx` và phạm vi PR không sửa `App.jsx` hay dựng route bypass auth. Cần bổ sung kiểm tra visual desktop/mobile trực tiếp sau khi ghép môi trường staging có đăng nhập.
- **Bước tiếp:** Chuyển Draft PR sang **Ready for review** (tag `@htbaax`, `@AI-WFox`, `@benalexx007`, `@johannguyen015`), phối hợp smoke E2E sau khi `#94` và `PR #103/#104` sẵn sàng trên môi trường tích hợp.

---

## 6. Plan sửa S06 trên `fix/stage3-ui` — 23/11/2026

### 6.1. Phạm vi, nguồn và mức bằng chứng

- **Yêu cầu:** lấy UI walkthrough làm chuẩn, khôi phục việc so sánh một câu gốc ở cột trái với biến thể của câu đó ở cột phải; các mã đề chuyển bằng tab trong cột phải.
- **Thứ tự duyệt user chốt 23/11:** đi hết các mã của một câu rồi mới sang câu nguồn kế tiếp: **Câu 1/Mã 1 → Câu 1/Mã 2 → Câu 2/Mã 1 → Câu 2/Mã 2** (ví dụ hai mã). Với N mã, thứ tự là `(câu 1, mã 1..N)`, rồi `(câu 2, mã 1..N)`. Quyết định này thay hành vi duyệt hết câu trong một mã trước của walkthrough 02/11; bố cục/flow khác vẫn theo walkthrough.
- **Author / owner:** Philip (`philip-kkk`); reviewer chưa được chỉ định cho lượt sửa này. Đề xuất Bội Anh kiểm regression logic Review và Tâm đối chiếu thiết kế; chưa coi là đã nhận review. Workflow v0.1 + INPUT-20261109, tiếp task #95, không tạo tracker cạnh tranh.
- **Baseline đã kiểm:** working tree sạch trước thao tác; `dev` và `origin/fix/stage3-ui` cùng `efed79b`. Đã checkout local `fix/stage3-ui` theo remote. Không cần merge thêm `dev` ở baseline này. PR và ETA lượt sửa: chưa chốt.
- **Chuẩn:** [README walkthrough](../ui-walkthrough/README.md), [version](../ui-walkthrough/version.json), S06 trong `PREVIEW.html`; package `UI-WALKTHROUGH-20261102-TRANSPARENT-BRAND-HANDOFF-V2`, SHA256 `8f9d6ebca4ad42b3ebddc15cf2fb4119b9599b8eb175c1b2c4d749b5f779dfaa`. Hash artifact trong repo khớp bản portable tại workspace.
- **Nguồn cấu trúc đã đọc:** `project/ui-draft/redesign/src/features/workflow/pages/ReviewPage.tsx`, `styles/workflow.css`, `styles/fixed-viewport.css`, `styles/tokens.css`, `styles/review-popup-actions.css`, `styles/review-notifications.css`. Đây là đường dẫn từ workspace gốc, ngoài repo sản phẩm.
- **Nguồn hình đã xem:** `project/ui-draft/snapshots/20261027-design-source/current/S06.png`. Ảnh này có niên bản 27/10, chỉ làm bằng chứng bố cục; các delta popup, tạo lại, lỗi và approval lấy từ README/source/package 02/11. Chưa mở bản sản phẩm hoặc walkthrough trong browser thật ở lượt này, chưa đo kích thước/focus/scroll runtime.
- Quy chuẩn user ngày 21/11 áp dụng **bố cục đến màu sắc**. Các hướng nghiên cứu Hero ngày 23/11 chưa thay chuẩn triển khai S06 trong task này.
- **Trong scope:** Review S06, CSS cục bộ, trạng thái chọn cặp, inspection popup, thông báo và regression liên quan. S07/Export chỉ kiểm đường đi và bảo toàn nghiệp vụ; chưa redesign lại hai màn đó.
- **Ngoài scope:** backend/schema/API, auth/router, Stage 1/2, export/shuffle, đổi thư viện hoặc design system toàn ứng dụng. Không copy công cụ giả lập, timer hay account demo của walkthrough vào sản phẩm.

### 6.2. Đánh giá bố cục hiện tại

| Hạng mục | Code tại baseline | Hệ quả / hướng sửa |
|---|---|---|
| Bề mặt đọc chính | `Stage3ReviewPage.jsx` render `.map()` toàn bộ câu của mã đang chọn trong danh sách dọc; khung `min-h-screen`, `max-w-6xl`, `space-y-5`. | Câu gốc không thường trực; phải mở một câu rồi tìm vùng so sánh. Thay bằng workspace hiển thị đúng một cặp đang chọn. |
| Vị trí hai cột | `solution-columns` chỉ nằm trong vùng lời giải mở rộng, breakpoint `xl`; không phải bề mặt đọc chính. | Việc có class grid hai cột không đồng nghĩa đạt UX S06. Đưa hai panel lên vùng đọc chính, không nhân đôi cả đề trong danh sách. |
| Điều hướng | Chọn câu gắn với `selectedSolution`, mở lời giải và `scrollIntoView`; chuyển mã xóa selection. | Tách câu đang chọn khỏi trạng thái mở popup. Đổi mã giữ câu gốc; chọn câu không tự mở popup hoặc cuộn document. |
| Inspection | Node tên `solution-dialog` thực tế là `div role="region"` trong card; tạo lại câu đã duyệt dùng `window.confirm`. | Dùng một modal thật, confirmation trong cùng modal, có quản lý focus và đóng X/Esc/backdrop. |
| Không gian / CTA | Header, banners, tabs, navigator, filter và toàn bộ danh sách cùng kéo dài trang; footer chỉ `sticky bottom-0`. | Sticky footer không bảo đảm màn vừa viewport. Dùng các hàng cố định về vị trí và vùng đọc co giãn, cuộn cục bộ. |
| Màu đáp án | Option mang key ở biến thể đang dùng `approved-*` xanh lá và icon check. | Dễ hiểu nhầm là giáo viên đã duyệt. Dùng lam xám/navy + nhãn “Đáp án”; xanh lá chỉ cho approval. |
| Câu thiếu | Card thiếu gọi `handleRetryAllMissing`; không giữ được câu nguồn trong cùng khung so sánh. | Vẫn chọn được ô thiếu và đọc nguồn; bên phải là trạng thái thiếu/lỗi thật. Không mô tả retry cấp phiên thành tạo lại đúng một cặp. |
| Lời bàn giao cũ | Mục 5 ghi “đã đồng bộ”, nhưng chưa có browser visual QA; test cuối còn yêu cầu chọn câu tự mở đối chiếu. | Giữ kết quả lịch sử, sửa acceptance của lượt mới theo luồng thực tế. Unit xanh không phải chứng cứ đạt layout. |

### 6.3. Các yếu tố phải giữ ổn định từ walkthrough

“Cố định” ở đây là vị trí/ngữ nghĩa ổn định khi đổi câu hoặc mã; không bắt mọi phần tử dùng CSS `position: fixed`.

| Vùng | Quy tắc triển khai / nghiệm thu |
|---|---|
| Khung ứng dụng | Header thương hiệu/điều hướng thật, chỉ báo Bước 3/3, navigator, hàng hành động và footer không chạy theo chiều dài câu. Thu gọn metadata hiện có; không thêm menu/account demo. |
| Navigator nguồn | Nằm trên **cả hai cột**, chọn câu nguồn 1..M; có trạng thái bằng chữ/icon và active rõ. Nhiều câu cuộn ngang/thao tác tới câu, không làm navigator xuống nhiều hàng chiếm vùng đọc. |
| Cột trái | Một câu gốc chỉ đọc: đề + options, key đã có. Cùng nguồn khi chuyển tab mã; không cần mở lời giải mới thấy nguồn. |
| Cột phải | Tabs mã đề thuộc riêng panel biến thể. Chỉ hiển thị **một mã đang chọn**, cùng câu nguồn; không chia thành N cột mã đề. Hiện rõ Câu X / Mã Y và trạng thái. |
| Tỷ lệ / cuộn | Desktop từ 1024px: hai cột gần ngang nhau, tham chiếu `minmax(0,1fr) minmax(0,1.04fr)`, gap 16px; tiêu đề/tab cùng hàng cao. `min-height:0` xuyên chuỗi flex/grid, hai body panel cuộn độc lập. Không thêm đồng bộ cuộn vì hai nội dung có độ dài khác nhau. |
| Màn hẹp | Dưới 1024px theo walkthrough: nguồn trước, biến thể sau, cuộn trong vùng so sánh chung; header/navigator/hành động/footer giữ ngoài vùng đó. Không ép hai cột chữ quá nhỏ, không thu nhỏ cả trang để vừa. |
| Chữ / tokens | Inter cho nội dung, Plus Jakarta Sans cho heading; câu đọc tham chiếu 18px, control 14px. Tận dụng tokens đã khớp trong `index.css`, scoped CSS cho Stage 3; không đổi palette toàn app. |
| Màu ngữ nghĩa | Nền `#fafafa`, surface trắng, viền `#e4e4e7`, tab/CTA vàng `#f5ce58` với soft `#fef7dd`; đáp án lam xám `#edf1f7` / navy `#304c70`; approval xanh lá; lỗi `#a32b32`. Active tab và trạng thái approval là hai tín hiệu riêng. |
| Hành động chính | Trang chính có “Kiểm tra đáp án”; popup mới chứa “Tạo lại” và “Duyệt biến thể” cạnh nhau bên phải. Footer “Rà bộ đề” là thao tác chủ động, không tự đi S07 sau câu cuối. |
| Popup | Bên trái biến thể, bên phải key/lời giải; không lặp lại bố cục gốc–biến thể thay cho vùng evidence. Một dialog có body cuộn, header/footer còn truy cập được; X/Esc/backdrop, trap/restore focus. Confirmation tạo lại cùng dialog, không `window.confirm`/dialog lồng. |
| Thông báo | Toast dưới header, tối đa hai, tự ẩn khoảng 5s/dismiss/dedupe; không đẩy khung đọc. Lỗi cần phục hồi vẫn có badge/inline message sau khi toast mất. Lỗi thao tác trong modal giữ trong modal. |

### 6.4. Trạng thái chọn cặp và các guard phải giữ

1. Dùng `(sessionId, source_question_id hoặc question_no đã đối soát, version)` để chọn **vị trí**; candidate identity từ snapshot quyết định nội dung/approval của vị trí đó. `selectedQuestion` độc lập `inspectionOpen`; không dùng bản sao candidate trong modal làm nguồn sự thật lâu dài.
2. Mở mới chọn câu đầu/mã đầu; resume hợp lệ giữ câu/mã/filter. Đổi mã giữ câu, đổi câu cập nhật cả hai panel, không tự mở inspection. Lưu lựa chọn view trong sessionStorage, không lưu nội dung đề/keys/token. Bỏ phục hồi `window.scrollY`; reset cuộn cục bộ khi đổi cặp.
3. Giữ filter hiện có nhưng làm gọn. Khi filter loại câu đang chọn, chọn vị trí phù hợp theo thứ tự nguồn; filter rỗng có empty state, không hiển thị sai cặp. Mở popup không làm thay filter hoặc vô tình duyệt câu khác.
4. Câu chưa có kết quả: nguồn vẫn đọc được; panel phải hiển thị thiếu/chờ/lỗi theo dữ liệu thực. Skeleton cho tải/refetch/regenerate thật; không suy mọi `candidate:null` là “đang tạo” hoặc “tạo lỗi”, không tự tạo countdown/background scheduler.
5. Cặp tạo lỗi/thiếu hoặc nội dung có lỗi cấu trúc xác định được: nêu rõ Câu X/Mã Y, không cho accept; phải tạo lại/phục hồi rồi kiểm lại trước khi duyệt. Không bịa key/lời giải; không tự coi mọi warning/fallback là lỗi cứng hoặc báo đã xác minh tính đúng toán học.
6. Sau tạo lại thành công, giữ dialog, đọc candidate mới chưa duyệt; bỏ approval candidate cũ. Sau accept đúng candidate và đối soát snapshot, đóng popup rồi chọn cặp chưa duyệt tiếp theo theo **câu trước, mã sau**: giữ câu nguồn và chuyển sang mã kế tiếp; hết các mã của câu đó mới chuyển câu nguồn tiếp theo, bắt đầu từ mã đầu. Ví dụ hai mã: Câu 1/Mã 1 → Câu 1/Mã 2 → Câu 2/Mã 1 → Câu 2/Mã 2. Chỉ bỏ qua cặp đã duyệt đúng candidate hiện hành; không bỏ qua ô thiếu/lỗi, không tự bật popup cặp kế tiếp, không tự đi S07. Nếu snapshot thay candidate A bằng B thì B vẫn chưa duyệt (Issue #85).
7. Giữ idempotency key, operation/session/unmount guards, xác minh response lỗi `409` theo code, `423`, permanent lock và `read_only`. Busy không cho đổi cặp hoặc đóng dialog giữa mutation. Không nới quyền ghi để làm demo giống walkthrough.
8. “Rà bộ đề” chỉ bật khi đủ cặp, đủ approval hiện hành, không còn cặp lỗi xác định được và đáp ứng các guard/trạng thái backend hiện có. Không tự đặt một field readiness mới. Không đếm ID alias hoặc candidate lỗi thời thành nhiều approvals.
9. `revert` đang có trong phạm vi nghiệp vụ #95 nhưng không có trong walkthrough: giữ “Khôi phục đề gốc” như quiet/tertiary action bên trái popup; “Tạo lại” và “Duyệt biến thể” bên phải. [Duy đồng ý](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7104275075) và [Bội Anh xác nhận hướng UX/nghiệp vụ](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7121504561): fallback khi regenerate liên tục thất bại, không thay phục hồi ô thiếu, không auto-approve; hiển thị nội dung gốc ở cột biến thể và yêu cầu duyệt candidate hiện hành chủ động. Không tự đặt ngưỡng 2–3 lần, không đổi enum theo chữ “unapproved” mô tả nghiệp vụ trong comment. Đủ hướng cho C3 độc lập qua API/guard hiện hành.

### 6.5. Đầu vào đủ dùng và phần chưa được tự suy ra

| ID | Cung cấp → nhận | Bằng chứng / điều kiện đủ dùng | Trạng thái và bước tiếp |
|---|---|---|---|
| `I-95-FIX-LAYOUT` | User + walkthrough → Philip | Bố cục S06, palette, viewport, popup; nguồn mục 6.1. | Đủ lập plan và code phần giao diện độc lập. |
| `I-95-FIX-IDENTITY` | Code tích hợp #85/#91 → Philip | `stage3Service.js`, Review Page/tests: accept/regenerate/revert và current snapshot. | Đủ bảo toàn hành vi các cặp có candidate; regression bắt buộc. |
| `I-95-FIX-MISSING-RETRY` | Đạt (AI/recovery) + BE owner chưa xác nhận; Duy điều phối → Philip | [Duy đồng ý phương án A](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7104275075) và [htbaax đồng ý](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7121504561): đúng X/Y, giữ candidate/approval khác, validate/duyệt chủ động; tạm giữ retry cấp phiên ghi đúng phạm vi. PR #110 head `991b7e8` chỉ batching/resume. | **Accepted cho UX/nghiệp vụ và fallback hiện hành; chưa đủ API mới, chưa Integrated.** Endpoint/payload slot chưa có ID, idempotency/persistence/recovery, BE owner, mẫu/test và ETA chưa chốt. Không đổi retry cấp phiên thành cam kết một ô. |
| `I-95-FIX-PARTIAL-WRITE` | BE owner + Bội Anh; Duy xác nhận nghiệp vụ → Philip | Duy/htbaax đồng ý duyệt cặp khỏe. htbaax đã xác nhận `read_only` hiện hành là khóa FE cấp phiên; guard giữ `isFinalLocked || Boolean(session?.read_only)`. Đối chiếu docs/SQL ở mục 6.12: còn trạng thái `reviewed` trước shuffle, không chỉ `generated`. | **Accepted nghiệp vụ và cách đọc quyền hiện hành; contract mở partial-write chưa đủ, chưa Integrated.** Chờ BE định nghĩa state/permission mới và mẫu/test. `slot.can_accept` trong comment chỉ là ví dụ, chưa phải schema. Giữ guard và gate S07; ETA chưa chốt. |
| `I-95-FIX-REVERT` | Philip đề xuất; Duy + Bội Anh đồng ý → Philip | htbaax xác nhận quiet/tertiary bên trái popup; hai CTA chính bên phải. Sau revert là candidate mới chưa duyệt, giáo viên đọc và duyệt chủ động; không thay retry ô thiếu. | **Accepted cho UX/nghiệp vụ C3 qua API/guard hiện có.** Không chờ thêm phản hồi vị trí control; không tự đặt ngưỡng số lần retry hoặc enum mới. Chưa nhận đã triển khai popup/Integrated/visual passed. |
| `I-95-FIX-BROWSER` | Môi trường local có đăng nhập → Philip | Cần chạy bản đúng branch + dữ liệu hợp lệ và quyền browser để kiểm visual thật. | Lượt plan chưa có runtime capture. Fixture/mock để kiểm UI tách biệt Live FE–BE–DB; không thêm route bypass auth vào sản phẩm. |

Nơi tổng hợp input lượt sửa là bảng này; không suy câu trả lời của các input cũ ở mục 3 là đã giải quyết các giới hạn mới. Đã đọc comment Philip, Duy và htbaax trên PR #109 ngày 24/11; nguồn/giới hạn tại mục 6.11–6.12. Agent chưa gửi reply GitHub hoặc nhận ETA mới.

### 6.6. Thứ tự commit dự kiến và phạm vi file

Cập nhật sau phản hồi Duy + htbaax ngày 24/11: C1 đã commit `e3ec20b`; C2 đã commit `5d0e434` và được push lên PR #109. C2 có implementation/checks, vẫn thiếu native visual QA theo mục 6.10. C3–C5 dưới đây là phần còn lại, chưa code. Tách C4 thành C4a độc lập và C4b/C4c phụ thuộc BE; không gom cả ba vào một commit rồi nhận hoàn tất dù thiếu contract.

| Lượt / commit dự kiến | File dự kiến | Công việc và tiêu chí hoàn tất | Phụ thuộc / kiểm |
|---|---|---|---|
| **C3 — đủ input** `fix(stage3): inspect and regenerate in one accessible dialog` | Trong `frontend/src/features/stage3-review/`: `Stage3ReviewPage.jsx`, mới `Stage3InspectionDialog.jsx`, `stage3Review.css`, `Stage3Review.test.js` | Một modal thay inline region; biến thể bên trái, key/lời giải bên phải. Tạo lại/Duyệt bên phải, revert quiet bên trái. X/Esc/backdrop, trap/restore focus, body cuộn, busy khóa close/đổi cặp. Tạo lại xác nhận ngay trong modal, không dialog lồng/`window.confirm`; hủy không gọi API. Sau regenerate/revert, giữ nội dung mới chưa duyệt để đọc lại. Sau accept đúng candidate và reconcile, đóng modal rồi chọn cặp chưa duyệt tiếp theo theo câu trước/mã sau; không bỏ qua ô thiếu, không auto S07. | Dùng API/guard hiện hành cho cặp có candidate; không đợi hai API mới. Kiểm accept/reject/revert, idempotency, candidate A→B, refetch lỗi/chậm, chuyển phiên, khóa phiên và keyboard. Không tự đặt ngưỡng retry trước revert. |
| **C4a — đủ input sau C3** `fix(stage3): expose pair failures and preserve review guards` | `Stage3ReviewPage.jsx`, `Stage3Comparison.jsx`, `Stage3InspectionDialog.jsx`, `stage3Review.css`, `Stage3Review.test.js` | Toast/badge theo dữ liệu thật, không đẩy khung đọc; tối đa hai toast, dedupe/dismiss/~5s, lỗi cần phục hồi vẫn còn nhãn/inline. Ô thiếu còn nguồn đọc, không bịa nội dung. Chặn accept khi thiếu/lỗi cấu trúc xác định được; không coi mọi warning là hard failure. Giải thích gate Rà bộ đề, giữ filter/resume và retry cấp phiên đúng nhãn. `read_only`/lock và ma trận generated/reviewed trước shuffle giữ nguyên. | Chưa targeted retry, chưa mở partial-write. Kiểm pending/missing/invalid/warning/read-only, 409 phân loại/423, lỗi mạng, session switch/F5, toast hết hạn vẫn đọc được lỗi; lỗi modal không tự mất theo toast. |
| **C4b — chờ contract** `feat(stage3): recover a missing review slot` | Dự kiến `frontend/src/services/stage3Service.js`, `stage3Service.test.js`; `Stage3ReviewPage.jsx`, `Stage3InspectionDialog.jsx`, `Stage3Review.test.js` | Nối recovery đúng ô X/Y chưa có candidate qua contract được BE cung cấp; xác nhận đúng cặp, giữ candidate/approval cặp khác, đọc lại kết quả authoritative chưa duyệt. Không tái dùng session retry để giả per-slot; không sinh candidate ID client. | Chỉ code sau `I-95-FIX-MISSING-RETRY` đủ endpoint/payload định danh slot, idempotency/persistence/recovery, response/error và mẫu/test tại revision xác định. Kiểm một ô lỗi trong nhiều câu/mã, timeout/response loss/double-click, replay/conflict/lock, candidate mới và cặp khỏe không đổi. Tên endpoint/field vẫn chưa chốt. |
| **C4c — chờ contract** `feat(stage3): respect partial review permissions` | Dự kiến `frontend/src/services/stage3Service.js`, `stage3Service.test.js`; `Stage3ReviewPage.jsx`, `Stage3InspectionDialog.jsx`, `Stage3Review.test.js` | Đọc quyền từ contract mới để chỉ mở thao tác được phép cho cặp hợp lệ trong partial; ô lỗi vẫn khóa accept và gate Rà bộ đề vẫn khóa khi thiếu điều kiện. Mọi thay đổi guard phải căn cứ schema/state chính thức, thiếu/không hiểu quyền thì không tự mở ghi. | Chỉ code sau `I-95-FIX-PARTIAL-WRITE` đủ ma trận trạng thái/quyền, ý nghĩa read_only mới (nếu đổi), mẫu/test và revision. `slot.can_accept` chỉ là ví dụ, không đưa vào code trước. Kiểm read-only session/permanent lock, quyền khác nhau giữa các cặp, quyền đổi khi refetch, field thiếu và lỗi 409/423. |
| **C5 — nghiệm thu/bằng chứng** `docs(stage3): record visual and regression verification` | `docs/tasks/ISSUE-95.md`, `docs/change_log.md`; `docs/ui-walkthrough/stage3-fix/` chỉ chứa ảnh/báo cáo thực sự tạo được | Ghi đúng head, môi trường, viewport, mock/live, visual/keyboard/focus/scroll và giới hạn; full regression Review/Preview/Export, self-review/audit. Có thể thu bằng chứng C3/C4a sớm; không dùng kiểm đó để nhận C4b/C4c Done. | Đủ toàn bộ UX của task chỉ khi cả các nhánh recovery/partial-write đã có contract, code và kiểm tương ứng; nếu chưa có thì ghi từng phần pending, không tự bỏ scope. Chưa browser thì chưa visual passed, chưa live thì chưa Integrated thật. |

**Ranh giới file:** C3/C4a không sửa services, `index.css`, `App.jsx`, `sessionDestination.js`, backend/schema hoặc Export. Service scope dự kiến ở C4b/C4c là phần nối contract **có điều kiện**, chưa có quyền tự thiết kế API hoặc bỏ guard. Tài liệu contract API do BE owner cập nhật; FE dẫn revision đó trong bảng 6.5 trước triển khai. Nếu contract thật đòi file ngoài danh sách, cập nhật delta scope trước khi code. Docs task/changelog cập nhật cùng mỗi mốc, không tính thành một tính năng riêng. Handoff workspace không đưa vào commit sản phẩm.

**Thứ tự và điều kiện chuyển lượt:**

1. C3 → C4a có thể làm trước qua contract hiện hành khi user giao code. Mỗi commit độc lập, dùng được, không chứa placeholder gọi API chưa tồn tại.
2. C4b/C4c chỉ bắt đầu khi input tương ứng đủ dùng; thứ tự giữa hai lượt theo contract BE giao thực tế. Nếu chỉ một input sẵn, làm phần đó trước và giữ input kia pending; không coi hai input đã đủ chỉ vì có phản hồi đồng ý nghiệp vụ hoặc PR #110.
3. Trong C3/C4a, thiếu slot chỉ dùng fallback retry cấp phiên hiện hành với nhãn/phạm vi đúng. Không đặt control hoạt động “Tạo lại đúng cặp” trước C4b.
4. Chốt C5 trên code cuối của phần được nghiệm thu. Mỗi lượt chạy targeted tests và lint/build phù hợp; full frontend suite ở mốc tổng kết hoặc khi thay đổi có nguy cơ lan rộng. Sau code phải self-review/audit, xử lý lỗi và kiểm lại; không nhận test DOM là visual QA. Nếu phát hiện visual bug cần sửa source, tạo commit fix có scope cụ thể trước commit bằng chứng C5, không giấu code fix trong commit docs.
5. PR #109 tiếp tục Draft khi còn thiếu code/checks/input trong scope. Không tự chuyển Ready/thu hẹp nghiệm thu, tạo PR BE mới, merge #110 hoặc chỉnh Export từ việc lập plan này. ETA/reviewer nhận việc chưa xác nhận thì giữ TBD.

### 6.7. Ma trận nghiệm thu và verification

- **Hai cột:** desktop 1440×900, 1366×768, 1024×768; nguồn giữ khi chuyển mã 101→102, không render N mã cạnh nhau. Nguồn/biến thể dài khác nhau không làm mất header/tab/CTA.
- **Reflow:** 768×1024, 375×812 và bề rộng 320px; vùng đọc chung chứa hai panel xếp dọc, không horizontal overflow document. Zoom 200% hoặc cửa sổ thấp vẫn truy cập được mọi nội dung/CTA bằng scroll cục bộ; không giải bằng cắt nội dung.
- **Nhiều câu / mã:** fixture ít câu và nhiều câu để vượt chiều rộng navigator, các số mã thực tế, đề và option dài, công thức Đại số dài. Không dùng fixture chỉ một câu để kết luận viewport đạt.
- **Chọn cặp / filter / resume:** default, đổi nguồn, đổi mã, filter rỗng, F5/resume, route chuyển phiên; giữ identity và không lưu nội dung đề vào browser storage.
- **Popup:** mở chỉ khi bấm “Kiểm tra đáp án”; Tab/Shift+Tab, X/Esc/backdrop, focus trở nút mở; xác nhận/hủy tạo lại cùng popup, busy khóa close, thất bại giữ thông tin, thành công hiện candidate mới và chưa duyệt.
- **Approval:** missing/invalid không accept; warning không bị đánh đồng hard failure; accept đúng candidate thì chọn tiếp theo câu trước/mã sau. Test hai câu × hai mã phải đi Câu 1/Mã 1 → Câu 1/Mã 2 → Câu 2/Mã 1 → Câu 2/Mã 2; thêm ca N mã, cặp đã duyệt, ô thiếu/lỗi và candidate bị thay trong refetch. Giữ nguồn khi sang mã tiếp, chỉ đổi nguồn sau mã cuối của câu; replacement không thừa hưởng approval. Regenerate không làm mất approval cặp khác; đủ duyệt mới mở CTA theo guard backend.
- **Recovery:** partial có và không có read-only, failed, 409 shuffle-required khác review conflict/unknown, 423 locked, lỗi mạng/mutation outcome; retry phạm vi đúng với API. Không seed lỗi B=C giả vào dữ liệu sản phẩm.
- **Điều hướng S07/Export:** không auto navigate, không tự PATCH/POST do F5, giữ question-only shuffle/legacy option preference và khóa vĩnh viễn; regression #85/#86.
- **Commands từ `frontend/`:** `node --test --test-concurrency=1 src/features/stage3-review/Stage3Review.test.js src/services/stage3Service.test.js`; sau đó suite Preview/Export liên quan, full `node --test --test-concurrency=1`, `npm run lint`, `npm run build`. Từ repo root: `git diff --check`.

### 6.8. Kết quả thực tế ở lượt lập plan

- Đã đối chiếu source, README, package hash và ảnh S06 cũ theo giới hạn mục 6.1; đã checkout nhánh yêu cầu.
- **Baseline targeted tests đã chạy:** lệnh Review + service ở mục 6.7, **51/51 pass**, 0 fail/skip, khoảng 17.1s. Có cảnh báo KaTeX quirks mode trong test DOM và React Router future flags; không phải kết quả browser. Chưa chạy lại full suite/lint/build ở lượt chỉ sửa docs này.
- **Mốc chuẩn bị Draft:** user giao commit docs ngày 23/11; C1 gồm plan này và mục proposed trong `docs/change_log.md`. Chưa sửa source UI, push/tạo PR/gửi comment, visual runtime hoặc live FE–BE–DB. Các số 563/129 ở mục 5 là bằng chứng lịch sử, không được nhận là đã chạy lại ở baseline này.
- **Bước tiếp:** khi được giao code, bắt đầu C2; phần layout không bị chặn bởi các input backend. Chưa nhận hoàn tất parity phục hồi từng cặp nếu các input ở mục 6.5 còn mở.

### 6.9. Nội dung contract cần thống nhất trên Draft PR

**Đã chốt bởi user:** bố cục một câu nguồn trái/một biến thể phải; thứ tự Câu 1/Mã 1 → Câu 1/Mã 2 → Câu 2/Mã 1; cặp lỗi không được duyệt, phải tạo lại rồi kiểm và duyệt chủ động. Đây là yêu cầu UX, chưa phải xác nhận API đã đáp ứng.

**Đề xuất gửi owner phản hồi:**

| Input ở mục 6.5 | Hướng đề xuất | Nội dung cần owner xác nhận để consumer nhận đủ |
|---|---|---|
| `I-95-FIX-MISSING-RETRY` | Phục hồi đúng ô Câu X/Mã Y, giữ nội dung và approval hiện hành của các ô khác. | BE cung cấp contract chính thức để định danh ô chưa có candidate, request/response, idempotency, cách đọc kết quả mới và recovery khi timeout/conflict/khóa phiên. Endpoint và tên field **chưa chốt**; không tự suy từ API retry cấp phiên đang có. Cần mẫu response thành công/lỗi và commit hoặc PR cung cấp trước khi nối FE. |
| `I-95-FIX-PARTIAL-WRITE` | Cho đọc/duyệt cặp khỏe trong lúc các cặp khác thiếu/lỗi theo UX; cặp lỗi vẫn bị chặn, gate cả bộ giữ nguyên. | BE + Bội Anh xác nhận trạng thái nào được accept/regenerate, ý nghĩa `read_only` và cách báo quyền thao tác trong snapshot, kèm mẫu dữ liệu/ca lỗi. Nếu API hiện vẫn khóa toàn phiên thì ghi rõ phần backend cần sửa; FE tiếp tục giữ guard, không nhận đã hoàn thành UX này. |
| `I-95-FIX-REVERT` | Giữ “Khôi phục đề gốc” như hành động phụ trong inspection; hai CTA chính vẫn Tạo lại/Duyệt biến thể. | Philip chốt ngoại lệ so với walkthrough sau phản hồi nghiệp vụ của Bội Anh; không coi đây là phương án thay cho tạo lại câu lỗi. |

- Reply trên Draft PR dùng đúng ID input, ghi phần đồng ý/đề nghị sửa, link contract + phiên bản/mẫu và ETA người cung cấp xác nhận. Bảng mục 6.5 vẫn là nơi tổng hợp input duy nhất; mục này mô tả hướng đề xuất, không tự nâng input thành Accepted/Integrated.
- Tại mốc C1, Draft được chuẩn bị ở trạng thái **plan và thảo luận contract**, chưa yêu cầu nghiệm thu code UI hoặc chuyển Ready. C2 layout làm độc lập; checkpoint triển khai mới nhất tại mục 6.10. Chỉ nối hành vi phụ thuộc API sau khi có đầu vào tương ứng.

### 6.10. Checkpoint C2 — workspace đối chiếu thường trực, 24/11/2026

- **Baseline:** `fix/stage3-ui@e3ec20b`; user giao triển khai và commit C2. Các mục 6.8–6.9 ghi trạng thái lúc lập plan/thảo luận, không thay checkpoint này. Commit C2 chưa bao gồm push, GitHub reply hoặc xác nhận contract từ owner.
- **File code:** `Stage3ReviewPage.jsx`, `Stage3Review.test.js`, thêm `Stage3Comparison.jsx` và `stage3Review.css` tại `frontend/src/features/stage3-review/`. Dùng `BrandLogo`, MathRenderer và palette hiện hành, không thêm dependency.
- **Đã triển khai:** một câu nguồn trái/biến thể phải; tabs mã thuộc panel phải; chọn câu độc lập mở lời giải; đổi mã giữ nguồn, kể cả khi phải reset filter không còn khớp. Tabs hỗ trợ ArrowLeft/ArrowRight/Home/End và roving focus. Nguồn vẫn đọc được khi chọn ô thiếu.
- **Bố cục trong code:** khung 100dvh, hai body panel cuộn độc lập ở desktop; dưới 1024px nguồn/biến thể xếp dọc trong vùng đọc chung. Navigator cuộn ngang; CTA Kiểm tra đáp án ở ngoài vùng đọc cuộn. Header/metadata được thu gọn; footer có đường về Thư viện, Stage 2 và Rà bộ đề. Cửa sổ thấp có fallback cuộn trong workspace để không cắt mất nội dung. Key đáp án dùng lam xám/navy và nhãn riêng, không dùng màu approval xanh lá.
- **Thứ tự:** thao tác hiện có “Đến câu chưa duyệt tiếp theo” đi theo câu trước/mã sau và không bỏ qua ô thiếu. **Chưa thêm auto-select sau accept hoặc modal mới**; phần này thuộc C3. Vùng lời giải mở rộng hiện hành vẫn được giữ trong panel phải để các thao tác cũ tiếp tục dùng được ở commit C2.
- **Bảo toàn contract:** vùng handler regenerate/accept/revert/retry đối chiếu nguyên văn với baseline và không đổi. Cờ read-only/lock, identity/idempotency và recovery tiếp tục hiện hành. Bỏ nhãn ẩn “Sinh bù câu này” gây hiểu nhầm; thao tác vẫn ghi đúng sinh bổ sung các câu còn thiếu cấp phiên. Không nối API targeted retry chưa được cung cấp.

**Kiểm đã chạy trên candidate C2 trước commit:**

| Kiểm | Kết quả / mức bằng chứng |
|---|---|
| C2 focused `node --test --test-concurrency=1 --test-name-pattern="C2:" src/features/stage3-review/Stage3Review.test.js` | 5/5 pass ở lượt focused; cùng 5 ca cũng được chạy lại trong full suite trên source cuối. Kiểm một cặp, giữ nguồn, missing/key marker, filter khi đổi mã, bàn phím và next theo câu trước. |
| Full frontend `node --test --test-concurrency=1` | **612/612 pass**, 0 fail/skip/cancel, 2 suites, khoảng 100.4s; gồm các ca Review, Preview/Export và service. Test DOM/mock, chưa phải browser hay API/DB thật. |
| `npm run lint` | Exit 0, không lỗi/cảnh báo lint. |
| `npm run build` | Exit 0, 1930 modules, 19.43s; JS chunk 1158.81kB, có cảnh báo chunk >500kB. Không mở rộng task sang code splitting. |
| Self-review/audit | Kiểm correctness/readability/architecture/security/performance trong scope C2; handler mutation không đổi, CSS theo màn, không đổi auth/API/shared tokens. Phép thử mutation tạm reset câu về 1 khi đổi mã khiến test giữ nguồn fail đúng chỗ; đã phục hồi trước full suite/build. Không phải GitHub approval hoặc review độc lập. |
| Docs/diff | `git diff --check` và kiểm liên kết mới trước commit. |

- **Giới hạn:** chưa có công cụ browser điều khiển khả dụng trong lượt C2 để chụp/đo bản chạy. Chưa kiểm native desktop/mobile/zoom/focus/scroll, không nhận visual parity đạt từ class CSS hoặc test DOM. Chưa live FE–BE–DB/Docker smoke. Các cảnh báo KaTeX test DOM/React Router future flags vẫn xuất hiện.
- **Bước tiếp:** kiểm visual trên môi trường có đăng nhập khi khả dụng; tiếp C3 khi user giao. Giữ các input `I-95-FIX-MISSING-RETRY`, `I-95-FIX-PARTIAL-WRITE`, `I-95-FIX-REVERT` ở trạng thái chờ phản hồi, không tự nâng Accepted/Integrated. C2 là checkpoint implementation/checks, chưa phải nghiệm thu toàn bộ #95 hoặc Ready cho toàn nhánh.

### 6.11. Cập nhật phản hồi Duy / quy trình PR #110 — 24/11/2026

**Nguồn đã đọc trực tiếp:**

- [PR #109 / phản hồi Duy `7104275075`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7104275075), tạo ngày 23/11. Lượt đọc đầu có comment Philip và Duy; cập nhật htbaax ở mục 6.12. PR #109 đang Draft/open, head `5d0e434`, base `dev@efed79b` tại lượt đọc đầu.
- [PR #110](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/110), Draft/open, chưa merge; head `991b7e8719c2c745af23d5c8b6eef1c4b177b1f1`, base `dev@efed79b`, nhánh `feat/dat-question-batch-formats`.
- Đã đọc body, danh sách 19 file đổi, [plan của Đạt](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/991b7e8719c2c745af23d5c8b6eef1c4b177b1f1/docs/tasks/DAT-question-batch-formats.md), source generation/model/export route/service và các test liên quan tại đúng head #110. Đây là cập nhật đầu vào và đọc luồng, chưa phải review toàn PR hoặc xác minh runtime.

**Kết luận nhận input từ Duy:**

1. Retry riêng một ô X/Y (phương án A) được đồng ý về hướng nghiệp vụ. Đạt phụ trách AI generation/recovery; đầu mối BE cho API/persistence và ETA chưa được chỉ rõ. Chưa có endpoint/payload chính thức hoặc mẫu/test cho ô chưa có candidate ID.
2. Cho duyệt các cặp hợp lệ trong phiên partial được đồng ý về nghiệp vụ; vẫn cần state/permission và ý nghĩa `read_only` trong snapshot. Không dùng phản hồi này để xóa guard FE.
3. Revert được đồng ý giữ secondary, làm fallback khi regenerate liên tục thất bại, không auto-approve. Đủ hướng để tiếp phần C3 của các candidate hiện có; không tự đặt số lần retry bắt buộc trước revert.
4. Bảng 6.5 phân biệt **Accepted cho UX/nghiệp vụ**, **đủ contract để nối API** và **Integrated**. Phản hồi Duy thay trạng thái chưa có hướng ở các mục plan cũ; không có nghĩa hai input backend đã hoàn tất.

**Luồng generation đọc được ở head #110:**

| Bước | Hành vi trong source | Hệ quả với FE |
|---|---|---|
| Preflight | Kiểm source đã xác nhận/hash, đủ Blueprint, chính sách biến đổi theo câu, 1–4 mã; đối soát kết quả đã lưu bằng seed/fingerprint/source/config. | Không tự tạo candidate giả hoặc suy tất cả nguồn đều sẵn từ trạng thái UI. |
| Lập slot | Xếp câu nguồn trước, mã sau: Q1/V1, Q1/V2, Q2/V1… | Khớp thứ tự user đã chốt cho Review. Cặp được định danh rõ theo nguồn/mã, không suy vị trí từ thứ tự JSON provider. |
| Sinh ban đầu | Với hơn một mã còn thiếu của cùng nguồn, một structured request trả `variants` gồm `version_index` và candidate. Kiểm tập mã phải khớp chính xác, không trùng; map theo `version_index` dù provider trả đảo thứ tự. Chỉ còn một mã thì dùng nhánh một candidate; clone không gọi AI. | **Batching theo nguồn không phải API retry đúng một ô.** FE không đổi request chỉ vì thứ tự generation mới. |
| Validate/repair | Từng candidate qua validator/chống trùng, đối chiếu với nguồn và các mã. Repair/retry candidate có thể phát sinh thêm request. | Không diễn giải “một request ban đầu/câu” thành cam kết tổng đúng một AI call, hoặc nhãn chắc chắn toán học đã đúng. |
| Lưu / tiến độ | `on_result` được await tuần tự cho từng cặp trước khi tiến tiếp; lỗi persistence truyền lên, kết quả đã commit là đầu vào resume. Test integration mô phỏng save trước publish `question_done`. | Nhận tiến độ theo cặp; giữ selection và approvals theo identity. Chưa xác minh thứ tự/độ trễ SSE trên DB/network thật từ test này. |
| Resume | Giữ các kết quả đã commit hợp lệ và chỉ sinh phần còn thiếu; không tái sinh cặp đã lưu. Nếu còn nhiều ô thiếu của một nguồn, batch chúng theo luồng hiện có. | **Resume phần còn thiếu không thay contract manual retry một ô X/Y.** PR #110 tự ghi hai input #109 vẫn còn chờ. |
| Kết thúc | Tổng hợp `generated` / `partial_generated` / `failed` theo kết quả các slot. | Sinh xong không đồng nghĩa giáo viên đã duyệt. Gate Review/finalize và quyền ghi vẫn theo contract hiện hành. |

Source chính: [GenerationService](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/991b7e8719c2c745af23d5c8b6eef1c4b177b1f1/backend/app/services/generation/service.py), [test batch/thứ tự](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/991b7e8719c2c745af23d5c8b6eef1c4b177b1f1/backend/tests/ai/test_generation_pipeline.py), [test persistence/resume/SSE](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/991b7e8719c2c745af23d5c8b6eef1c4b177b1f1/backend/tests/generation/test_ai_batch_integration.py).

**Nhánh Export mới của #110, ngoài scope C3 hiện tại:**

- PR #110 còn đề xuất UI chọn PDF/LaTeX/Markdown và tải từng file. `GET /api/sessions/{session_id}/export/files?format=pdf|tex|md` trả danh sách `files` với `filename`/`size_bytes`; thêm query `filename` để lấy attachment tương ứng. Không đưa endpoint này vào luồng generation/retry.
- Backend lấy archive private có sẵn làm nguồn nội bộ: status/owner/snapshot gate trước đọc, chỉ khi ready; storage đọc/kiểm checksum rồi giới hạn giải nén, tên/path/filename trùng và format được phép. Mỗi request đọc archive lại, PR body yêu cầu đo độ trễ deployment.
- Đối chiếu [route](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/991b7e8719c2c745af23d5c8b6eef1c4b177b1f1/backend/app/api/routes/private_export.py), [private export service](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/991b7e8719c2c745af23d5c8b6eef1c4b177b1f1/backend/app/services/exporter/private_service.py) và [FE client](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/991b7e8719c2c745af23d5c8b6eef1c4b177b1f1/frontend/src/services/exportService.js).
- Điểm cần phối hợp khi ghép nhánh: scope #95 cũ ghi ZIP-only, còn #110 đổi lựa chọn tải file riêng và chạm `SessionExportPage.jsx`/`exportService.js`. Chưa tự sửa scope S06/Export hoặc nhận đây là contract đã merge; cần đồng bộ Đạt với owner Export và Philip khi tích hợp. Việc này không chặn C3 độc lập trên Review.

**Giới hạn kiểm chứng và bước tiếp:**

- Các số 487 passed/1 skipped (backend), 60 passed (security), 24 passed (FE Export), lint/mypy/build và mock browser là **tác giả #110 báo trong PR**, chưa được chạy lại ở lượt đọc này. PR #110 chưa live Gemini/DB/Storage; một compile test bị skip. Không dùng test 612 của C2 để chứng nhận code #110.
- Có thể tiếp C3 cho candidate hiện có: modal, inline confirmation, reread candidate mới, explicit approve, next theo câu trước/mã sau và revert secondary. Targeted missing retry/partial-write tiếp tục chờ API/state/permission/mẫu/test; chưa sửa service hoặc merge nhánh #110.
- PR #109 body vẫn ghi plan-only/head `e3ec20b`, trong khi head thực là `5d0e434` đã có C2: cần cập nhật mô tả khi user giao thao tác/body mới. Lượt này chỉ cập nhật docs/handoff local, chưa commit/push/GitHub reply hoặc chỉnh metadata PR.

### 6.12. Input htbaax và phạm vi đủ để chốt — 24/11/2026

- Đã đọc trực tiếp [comment htbaax `7121504561`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7121504561), tạo `2026-11-24T03:52:42Z`. Cập nhật bảng 6.5 và vị trí revert tại 6.4.9; không ghi đây là code/test mới hoặc GitHub Approve.
- **Đủ chốt UX và phần C3 qua API hiện hành:** modal inspection, Tạo lại/Duyệt bên phải, revert quiet/tertiary bên trái; candidate mới sau regenerate/revert phải được đọc và duyệt chủ động, không auto-approve. Thứ tự câu trước/mã sau và các guard giữ. Không có ngưỡng 2–3 lần bắt buộc; đó là ví dụ lý do nghiệp vụ trong comment.
- **Chưa đủ chốt toàn bộ contract tích hợp:** cả Duy và htbaax xác nhận API hiện chưa phục hồi một ô thiếu không có candidate ID. Chưa có endpoint/payload, idempotency/persistence/recovery, mẫu/test/ETA. Quyền duyệt cặp khỏe khi partial vẫn cần contract BE mới; không coi ví dụ `slot.can_accept` là field đã được chốt.
- `read_only` hiện tại đã rõ về cách FE dùng: khóa cụm actions/handler mutation theo `isFinalLocked || Boolean(session?.read_only)`; đây không thay authorization của Write API. Tạm giữ đường retry cấp phiên với nhãn đúng phạm vi, không mô tả là retry riêng một ô.
- **Điểm hiệu chỉnh trong phản hồi kỹ thuật:** htbaax viết điều kiện hiện tại chỉ `status === 'generated'`. [Contract snapshot hiện hành](../api/review-snapshot.md) còn cho `reviewed` **trước shuffle** với `read_only:false`; SQL `_review_assert_editable` tại `backend/migrations/006_stage3_review_and_shuffle.sql` cho `generated`/`reviewed`, còn snapshot guard ở `021_w4_confirmed_source_fallback.sql` chặn `reviewed` sau shuffle. FE giữ guard/ma trận hiện hành và quyền backend, không thêm điều kiện generated-only từ comment này. Đây là đối chiếu source/docs local head `5d0e434`, chưa xác minh DB đã deploy migration nào.
- **Kết luận consumer:** `I-95-FIX-REVERT` đủ dùng cho C3; `I-95-FIX-MISSING-RETRY` và `I-95-FIX-PARTIAL-WRITE` Accepted phần nghiệp vụ, chưa đủ API integration và chưa Integrated. Có thể gửi comment xác nhận/chốt phần C3 và liệt kê đúng hai dependency còn mở; không gửi tuyên bố “đã đủ toàn bộ contract”.
- Lượt này chỉ cập nhật docs/handoff và soạn nội dung để Philip paste; chưa commit/push/GitHub reply, chưa code C3 hoặc chạy lại product tests.

### 6.13. Replan các commit còn lại — 24/11/2026

- User giao cập nhật plan/scope sau khi nhận phản hồi Duy và htbaax. Baseline code vẫn `5d0e434` trên `fix/stage3-ui`; các cập nhật input 6.11–6.12 còn là docs local. Không sửa hoặc nhận lại kết quả C2 từ việc replan.
- Thứ tự mới tại mục 6.6: **C3 → C4a → C4b/C4c theo input BE → C5 tổng kết**. C4 cũ được tách, C5 không bị đổi sang làm tính năng. C3/C4a đủ input hiện hành; C4b/C4c chưa đủ API. Không có endpoint/schema/ETA mới được suy ra.
- C3 chốt đủ vị trí revert và flow candidate hiện có; acceptance gồm explicit reread/approve và auto-select đúng candidate theo câu trước/mã sau. C4a xử lý phản hồi lỗi/quyền hiện hành. C4b/c có scope FE service dự kiến và điều kiện mở riêng, không tự mở rộng sang backend/auth/router/export.
- Thu visual QA sớm cho C2/C3/C4a khi khả dụng; C5 ghi riêng implementation, automated checks, native visual và live integration. PR #110 Draft/batching không đóng hai dependency backend và không kéo phần tải file riêng vào scope sửa S06.
- Đã cập nhật scope/tiêu chí/checkpoint, giữ nguồn input duy nhất ở 6.5; reviewer/ETA chưa xác nhận tiếp tục TBD. Chỉ kiểm docs links/diff ở lượt này, chưa code/test product/commit/push hoặc cập nhật GitHub.

### 6.14. C3 — inspection modal qua API hiện hành, 24/11/2026

- Đã thay inline region bằng `Stage3InspectionDialog.jsx`: native dialog top layer, hai cột biến thể/evidence, xác nhận regenerate/revert trong cùng modal, quiet revert trái và CTA phải. Busy khóa đóng/đổi cặp; có Tab trap, Escape/backdrop/close và restore focus. Không còn `window.confirm` của Review.
- Sau regenerate/revert vẫn mở candidate mới chưa duyệt. Sau accept/refetch chỉ đóng và chọn tiếp nếu đúng candidate vừa duyệt; replacement A→B vẫn pending. Chọn tiếp theo câu trước/mã sau, kể cả ô thiếu, không tự vào S07. Refetch lỗi không kích hoạt auto-select.
- Code giới hạn Review Page/modal/CSS/test; không đổi service/backend/permission contract. Các cập nhật input/plan 6.11–6.13 được đưa cùng mốc này. C4a chưa triển khai tại checkpoint C3.
- Kiểm: Review + service **59/59 pass**; ba ca C3 mới cũng chạy focused sau khôi phục mutation; lint exit0; build exit0/1931 modules/17.76s, JS1156.66kB có cảnh báo chunk size. Mutation đảo điều kiện candidate identity khiến ca auto-select fail đúng assertion, đã khôi phục; self-review/audit guard, identity, state/focus và scope. Một build chạy lúc thử mutation bị lỗi đọc file, đã chạy lại tuần tự sau phục hồi và đạt; không dùng build lỗi làm bằng chứng.
- Tests cũ đổi từ region sang dialog, thêm bước xác nhận và cập nhật kỳ vọng sau accept; không xóa các ca idempotency/replacement/read-only/409/423. Chưa browser native/visual/mobile/zoom hoặc live FE–BE–DB; test focus là DOM harness. Chưa push/GitHub write/Ready; hai contract BE mới vẫn pending.

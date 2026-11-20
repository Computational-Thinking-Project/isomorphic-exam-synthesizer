# ISSUE-95 — Plan và bàn giao Redesign UI/UX Giai đoạn 3 (Review, Final Preview & Export)

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

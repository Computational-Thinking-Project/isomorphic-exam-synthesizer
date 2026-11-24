# ISSUE-95 — Plan và bàn giao Redesign UI/UX Giai đoạn 3 (Review, Final Preview & Export)

> **Lượt sửa `fix/stage3-ui`:** C2 tại mục 6.10; input Duy/htbaax và replan tại 6.11–6.13; checkpoint C3/C4a tại 6.14–6.15. Bàn giao mục 5 là lịch sử của lượt #95. Implementation/test DOM không thay native visual hoặc live integration; C4b/C4c và contract BE mới là follow-up ngoài PR109, không chặn merge phần FE khi đạt acceptance6.6.

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
- **Feedback UI user ngày24/11 (mục6.18) thay phần trình bày cũ:** logo gọn, bỏ metadata/legend/nhãn điều hướng phụ và bộ lọc trạng thái; panel cao hơn, tự nở theo nội dung và cuộn trang. Không còn yêu cầu khóa S06 vào đúng viewport/cuộn dọc riêng từng panel. Giữ hai cột/tabs, palette và flow duyệt đã chốt; đây là quyết định user, chưa nhận GV duyệt lại bản sửa.
- **Thứ tự duyệt user chốt 23/11:** đi hết các mã của một câu rồi mới sang câu nguồn kế tiếp: **Câu 1/Mã 1 → Câu 1/Mã 2 → Câu 2/Mã 1 → Câu 2/Mã 2** (ví dụ hai mã). Với N mã, thứ tự là `(câu 1, mã 1..N)`, rồi `(câu 2, mã 1..N)`. Quyết định này thay hành vi duyệt hết câu trong một mã trước của walkthrough 02/11; bố cục/flow khác vẫn theo walkthrough.
- **Author / owner:** Philip (`philip-kkk`); reviewer chưa được chỉ định cho lượt sửa này. Đề xuất Bội Anh kiểm regression logic Review và Tâm đối chiếu thiết kế; chưa coi là đã nhận review. Workflow v0.1 + INPUT-20261109, tiếp task #95, không tạo tracker cạnh tranh.
- **Baseline đã kiểm:** working tree sạch trước thao tác; `dev` và `origin/fix/stage3-ui` cùng `efed79b`. Đã checkout local `fix/stage3-ui` theo remote. Không cần merge thêm `dev` ở baseline này. PR và ETA lượt sửa: chưa chốt.
- **Chuẩn:** [README walkthrough](../ui-walkthrough/README.md), [version](../ui-walkthrough/version.json), S06 trong `PREVIEW.html`; package `UI-WALKTHROUGH-20261102-TRANSPARENT-BRAND-HANDOFF-V2`, SHA256 `8f9d6ebca4ad42b3ebddc15cf2fb4119b9599b8eb175c1b2c4d749b5f779dfaa`. Hash artifact trong repo khớp bản portable tại workspace.
- **Nguồn cấu trúc đã đọc:** `project/ui-draft/redesign/src/features/workflow/pages/ReviewPage.tsx`, `styles/workflow.css`, `styles/fixed-viewport.css`, `styles/tokens.css`, `styles/review-popup-actions.css`, `styles/review-notifications.css`. Đây là đường dẫn từ workspace gốc, ngoài repo sản phẩm.
- **Nguồn hình đã xem:** `project/ui-draft/snapshots/20261027-design-source/current/S06.png`. Ảnh này có niên bản 27/10, chỉ làm bằng chứng bố cục; các delta popup, tạo lại, lỗi và approval lấy từ README/source/package 02/11. Chưa mở bản sản phẩm hoặc walkthrough trong browser thật ở lượt này, chưa đo kích thước/focus/scroll runtime.
- Quy chuẩn user ngày 21/11 áp dụng **bố cục đến màu sắc**. Các hướng nghiên cứu Hero ngày 23/11 chưa thay chuẩn triển khai S06 trong task này.
- **Trong scope PR #109:** sửa FE Review S06 theo walkthrough (CSS, chọn cặp, popup, thông báo, responsive/accessibility) và giữ tương thích API hiện hành. S07/Export chỉ kiểm đường đi/regression. C4b/C4c là follow-up ngoài PR; không chặn nghiệm thu/merge phần FE này. Acceptance hiện hành ở 6.6 và quyết định scope ở 6.16.
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
| Khung ứng dụng | Header gọn với logo có chiều rộng riêng, chỉ báo Bước 3/3 và trạng thái; giữ navigator/hàng hành động/footer trong luồng trang. Theo feedback24/11, bỏ metadata số mã/câu/môn/khối, legend màu và nhãn điều hướng phụ; trang được cuộn theo câu dài. Không thêm menu/account demo. |
| Navigator nguồn | Nằm trên **cả hai cột**, chọn câu nguồn 1..M; có trạng thái bằng chữ/icon và active rõ. Nhiều câu cuộn ngang/thao tác tới câu, không làm navigator xuống nhiều hàng chiếm vùng đọc. |
| Cột trái | Một câu gốc chỉ đọc: đề + options, key đã có. Cùng nguồn khi chuyển tab mã; không cần mở lời giải mới thấy nguồn. |
| Cột phải | Tabs mã đề thuộc riêng panel biến thể. Chỉ hiển thị **một mã đang chọn**, cùng câu nguồn; không chia thành N cột mã đề. Hiện rõ Câu X / Mã Y và trạng thái. |
| Tỷ lệ / cuộn | Desktop từ1024px giữ hai cột `minmax(0,1fr) minmax(0,1.04fr)`, gap16px. Theo feedback24/11, comparison có min-height `max(420px, calc(100dvh - 260px))`; body không khóa chiều cao/cuộn dọc riêng, panel mở rộng theo nội dung dài và người dùng cuộn trang để đọc tiếp. Công thức quá rộng vẫn cuộn ngang cục bộ. |
| Màn hẹp | Dưới1024px nguồn trước/biến thể sau, hai panel nở theo nội dung và cuộn trang. Navigator/tabs vẫn cuộn ngang khi nhiều mục; không ép hai cột chữ nhỏ hoặc thu nhỏ toàn trang. |
| Chữ / tokens | Inter cho nội dung, Plus Jakarta Sans cho heading; câu đọc tham chiếu 18px, control 14px. Tận dụng tokens đã khớp trong `index.css`, scoped CSS cho Stage 3; không đổi palette toàn app. |
| Màu ngữ nghĩa | Nền `#fafafa`, surface trắng, viền `#e4e4e7`, tab/CTA vàng `#f5ce58` với soft `#fef7dd`; đáp án lam xám `#edf1f7` / navy `#304c70`; approval xanh lá; lỗi `#a32b32`. Active tab và trạng thái approval là hai tín hiệu riêng. |
| Hành động chính | Trang chính có “Kiểm tra đáp án”; popup mới chứa “Tạo lại” và “Duyệt biến thể” cạnh nhau bên phải. Footer “Rà bộ đề” là thao tác chủ động, không tự đi S07 sau câu cuối. |
| Popup | Bên trái biến thể, bên phải key/lời giải; không lặp lại bố cục gốc–biến thể thay cho vùng evidence. Một dialog có body cuộn, header/footer còn truy cập được; X/Esc/backdrop, trap/restore focus. Confirmation tạo lại cùng dialog, không `window.confirm`/dialog lồng. |
| Thông báo | Toast dưới header, tối đa hai, tự ẩn khoảng 5s/dismiss/dedupe; không đẩy khung đọc. Lỗi cần phục hồi vẫn có badge/inline message sau khi toast mất. Lỗi thao tác trong modal giữ trong modal. |

### 6.4. Trạng thái chọn cặp và các guard phải giữ

1. Dùng `(sessionId, source_question_id hoặc question_no đã đối soát, version)` để chọn **vị trí**; candidate identity từ snapshot quyết định nội dung/approval của vị trí đó. `selectedQuestion` độc lập `inspectionOpen`; không dùng bản sao candidate trong modal làm nguồn sự thật lâu dài.
2. Mở mới chọn câu đầu/mã đầu; resume hợp lệ giữ câu/mã. Đổi mã giữ câu, đổi câu cập nhật cả hai panel, không tự mở inspection. SessionStorage chỉ lưu số câu/mã, không lưu nội dung đề/keys/token hoặc filter. Không tự khôi phục `window.scrollY`; với page scroll mới không đặt lại giới hạn chiều cao panel khi đổi cặp.
3. Theo feedback24/11, bỏ bộ lọc Tất cả/Chưa duyệt/Đã duyệt/Có cảnh báo và logic filter tương ứng. Mọi vị trí nguồn luôn chọn được bằng navigator, kể cả cặp approved/missing; bỏ qua filter legacy còn lưu trong browser. Trạng thái vẫn có chữ/icon qua aria-label navigator và badge tại cặp, không chỉ dựa vào màu.
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
| `I-95-FIX-MISSING-RETRY` | Đạt (AI/recovery) + BE owner chưa xác nhận; Duy điều phối → Philip | [Duy đồng ý phương án A](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7104275075) và [htbaax đồng ý](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7121504561): đúng X/Y, giữ candidate/approval khác, validate/duyệt chủ động; tạm giữ retry cấp phiên ghi đúng phạm vi. PR #110 head `991b7e8` chỉ batching/resume. | **Accepted cho UX/nghiệp vụ và fallback hiện hành; chưa đủ API mới, chưa Integrated; follow-up ngoài PR109.** Endpoint/payload slot chưa có ID, idempotency/persistence/recovery, BE owner, mẫu/test và ETA chưa chốt. Không đổi retry cấp phiên thành cam kết một ô. |
| `I-95-FIX-PARTIAL-WRITE` | BE owner + Bội Anh; Duy xác nhận nghiệp vụ → Philip | Duy/htbaax đồng ý duyệt cặp khỏe. htbaax đã xác nhận `read_only` hiện hành là khóa FE cấp phiên; guard giữ `isFinalLocked || Boolean(session?.read_only)`. Đối chiếu docs/SQL ở mục 6.12: còn trạng thái `reviewed` trước shuffle, không chỉ `generated`. | **Accepted nghiệp vụ và cách đọc quyền hiện hành; contract mở partial-write chưa đủ, chưa Integrated; follow-up ngoài PR109.** Chờ BE định nghĩa state/permission mới và mẫu/test. `slot.can_accept` trong comment chỉ là ví dụ, chưa phải schema. Giữ guard và gate S07; ETA chưa chốt. |
| `I-95-FIX-REVERT` | Philip đề xuất; Duy + Bội Anh đồng ý → Philip | htbaax xác nhận quiet/tertiary bên trái popup; hai CTA chính bên phải. Sau revert là candidate mới chưa duyệt, giáo viên đọc và duyệt chủ động; không thay retry ô thiếu. | **Accepted cho UX/nghiệp vụ C3 qua API/guard hiện có.** Đã triển khai và kiểm DOM ở C3/C4a; không tự đặt ngưỡng số lần retry hoặc enum mới. Chưa native visual/live Integrated. |
| `I-95-FIX-BROWSER` | Môi trường local có đăng nhập → Philip | Cần chạy bản đúng branch + dữ liệu hợp lệ và quyền browser để kiểm visual thật. | Lượt plan chưa có runtime capture. Fixture/mock để kiểm UI tách biệt Live FE–BE–DB; không thêm route bypass auth vào sản phẩm. |

Nơi tổng hợp input lượt sửa là bảng này; không suy câu trả lời của các input cũ ở mục 3 là đã giải quyết các giới hạn mới. Đã đọc comment Philip, Duy và htbaax trên PR #109 ngày 24/11; nguồn/giới hạn tại mục 6.11–6.12. Agent chưa gửi reply GitHub hoặc nhận ETA mới.

### 6.6. Plan hiện hành cho PR #109 — scope FE

**Quyết định user ngày 24/11:** PR #109 sửa FE S06 theo UI walkthrough, dùng backend/API hiện hành. C4b/C4c chuyển sang follow-up ngoài PR; không phải điều kiện chờ để nghiệm thu/merge PR FE. Quyết định này thay các đoạn replan cũ yêu cầu hoàn tất hai API mới trước C5. Không nhận UI đã hỗ trợ mọi nghiệp vụ tương lai trong walkthrough.

| Mốc | Commit / file | Scope và kết quả | Phần còn kiểm trong PR này |
|---|---|---|---|
| C1 | `e3ec20b` / docs task + changelog | Plan và input. | Đồng bộ scope FE mới, giữ link follow-up. |
| C2 | `5d0e434` / Review Page, Comparison, CSS, test | Nguồn trái/biến thể phải, tabs mã, chọn cặp độc lập inspection, local scroll/reflow. | Visual desktop/mobile/zoom, nội dung dài và vùng cố định. |
| C3 | `ea41610` / Review Page, InspectionDialog, CSS, test + docs | Modal, inline confirmation, revert phụ trái/CTA phải, explicit approve, next theo câu trước/mã sau. | Native focus/Tab/Escape/backdrop, busy và phản hồi lỗi, hierarchy theo walkthrough. |
| C4a | `1b66140` / Review Page, Comparison, InspectionDialog, Notifications, CSS, test + docs | Toast/lỗi/gate, giữ read_only/lock, fallback retry cấp phiên đúng nhãn, reconcile khi snapshot thất lạc. Full frontend618/lint/build đã đạt theo checkpoint6.15. | Native toast không đẩy layout, lỗi vẫn truy cập được, current API behavior không bị regression. |
| C5 — kiểm tự động đã đạt, native QA còn mở | `5e890f9` — fix Tab; `docs(stage3): record FE scope and remaining visual acceptance` / task, changelog, [report C5](../ui-walkthrough/stage3-fix/README.md) | Sửa finding F109-C5-01 trước commit docs. Full frontend619/lint/build đạt trên code cuối; có checklist viewport/keyboard/scroll. Delta test support: selector nhóm trong `frontend/src/test-support/domHarness.js`, không đổi runtime sản phẩm. | Chưa native browser/visual/live; không nhận C5 hoàn tất hoặc PR Ready. Không chờ C4b/C4c hay PR110; CI/peer approval vẫn áp dụng. |

**Ranh giới PR:** chỉ FE feature `frontend/src/features/stage3-review/` và docs/bằng chứng liên quan; C5 có delta test-only ở `frontend/src/test-support/domHarness.js` để kiểm selector nhóm button/link (mục6.17). S07/Export chỉ kiểm đường đi/regression, không redesign hoặc đổi cơ chế export/shuffle. Không sửa services, backend/schema, auth/router, `index.css`, `App.jsx`, `sessionDestination.js` hoặc tích hợp Export tải lẻ của PR110 trong PR này. Nếu visual bug đòi file ngoài scope, nêu delta cụ thể trước khi triển khai, không tự đổi contract.

**Acceptance để hoàn tất PR FE:**

- [ ] Bản chạy S06 đạt bố cục/màu sắc/typography/phân cấp theo walkthrough trong scope đã chốt, gồm ngoại lệ revert đã thống nhất; một nguồn trái và một mã đang chọn phải, không render tất cả mã thành N cột.
- [ ] Đổi mã giữ nguồn; duyệt đúng candidate rồi chọn tiếp theo câu trước/mã sau; không tự approve candidate mới hoặc tự chuyển S07.
- [ ] Modal và main workspace dùng được bằng bàn phím; kiểm focus/close/busy, nội dung dài, desktop/mobile/zoom/cuộn trang theo ma trận6.7 đã cập nhật bởi feedback6.18. Modal vẫn cuộn body riêng. Không coi test DOM/class CSS là visual evidence.
- [ ] Hành vi API hiện có không regression: accept/regenerate/revert với candidate ID hợp lệ, identity/idempotency/stale response, read_only/lock, 409/423 và recovery/refetch. Không thêm guard generated-only, vẫn theo ma trận generated/reviewed trước shuffle.
- [ ] Các giới hạn backend hiển thị trung thực: ô thiếu chỉ có fallback retry cấp phiên; khi read_only thì mutation vẫn khóa; không có nút hoạt động hoặc thông báo hứa retry đúng một ô/duyệt sớm partial chưa được hỗ trợ.
- [ ] Tests/lint/build áp dụng trên code cuối; nếu chỉ docs sau checks thì ghi đúng baseline checks, không chạy lại rồi nhận kết quả mới khi chưa chạy. CI áp dụng trước merge và ít nhất một thành viên khác review/Approve theo CONTRIBUTING; không tự coi agent audit là approval.
- [ ] PR body phản ánh head/scope FE hiện tại, checks/giới hạn và link follow-up; không còn mô tả plan-only hoặc coi hai contract BE mới là blocker của PR này. Chưa chỉnh GitHub nếu user chưa giao.
- [ ] Tách rõ bằng chứng UI fixture/mock, native visual và live FE–BE–DB. Kiểm API hiện hành khi có môi trường phù hợp; không dùng mock để nhận live Integrated, không đặt thêm yêu cầu Gemini key/API mới cho PR thuần FE.

**Sau C5:** có thể đề nghị Ready/review và merge PR #109 khi scope FE/checks/CI/approval đạt dù C4b/C4c vẫn pending ngoài PR. Không cần đợi PR110; không tự Approve/merge hoặc đóng Issue #95 nếu issue còn chứa phần chưa nghiệm thu khác. Hai follow-up được giữ ở mục6.16, không xóa input hoặc đổi chúng thành Accepted API/Integrated.

### 6.7. Ma trận nghiệm thu và verification

- **Hai cột:** desktop1440×900,1366×768,1024×768; logo gọn, không có note/filter phụ; nguồn giữ khi đổi mã, chỉ một biến thể. Panel đủ cao và nở theo nội dung; header/tab/CTA vẫn truy cập bằng cuộn trang. Không bắt header/footer luôn đứng yên như kế hoạch cũ.
- **Reflow:**768×1024,375×812 và bề rộng320px; nguồn trước/biến thể sau, cuộn trang và không overflow ngang toàn trang. Zoom200% hoặc cửa sổ thấp vẫn đọc tới cuối và dùng CTA; không cắt nội dung hoặc khóa body panel thành khung thấp.
- **Nhiều câu / mã:** fixture ít câu và nhiều câu để vượt chiều rộng navigator, các số mã thực tế, đề và option dài, công thức Đại số dài. Không dùng fixture chỉ một câu để kết luận viewport đạt.
- **Chọn cặp / resume:** default, đổi nguồn/mã, F5/resume và route chuyển phiên; mọi trạng thái câu đều chọn được, bỏ qua filter legacy, giữ identity và không lưu nội dung đề vào browser storage.
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

### 6.13. Replan các commit còn lại — 24/11/2026 (lịch sử, scope đã được thay tại 6.16)

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

### 6.15. C4a — thông báo/lỗi và guard hiện hành, 24/11/2026

- Baseline C3 `ea41610`. Thêm `Stage3ReviewNotifications.jsx` trong feature để quản lý tối đa hai toast, dedupe, dismiss, tự ẩn 5s và cleanup timer khi unmount/StrictMode; tránh phình controller. Toast fixed không đẩy panel; lỗi cần phục hồi vẫn còn trong badge/inline/modal khi toast mất.
- `reviewPairIssue` ở `Stage3Comparison.jsx` dùng cho presentation, handler accept và gate Rà bộ đề: chặn report `is_valid:false`, options rỗng/trùng trong bộ 4 phương án, key thiếu/không khớp rõ ràng. Không biến mọi warning/unknown thành hard failure và không tạo validator toán mới. Regenerate response không tự gán approved cho candidate mới.
- Nếu accept được phản hồi nhưng snapshot refetch thất bại/rỗng: giữ modal, chặn ghi và Rà bộ đề, nêu cần Đọc lại trạng thái. Snapshot fresh thành công mới bỏ khóa đồng bộ cục bộ. Đây không phải thay đổi `read_only` backend hoặc cơ chế partial-write mới. Footer phân biệt chỉ xem, thiếu câu, lỗi và cần đồng bộ.
- Scope: Review Page/comparison/modal/notifications/CSS/test và docs; không service/backend/auth/router/Export. Vẫn retry cấp phiên đúng nhãn; không có endpoint targeted slot hoặc quyền slot mới.
- Ba ca C4a mới kiểm hard failure so với warning, refetch thất lạc/reload, queue/dedupe/dismiss/timeout trong StrictMode. Mutation đảo điều kiện duplicate bị test bắt đúng assertion; đã khôi phục trước checks cuối. Self-review/audit kiểm guard/candidate identity, timer lifecycle, scope CSS và không phát sinh dependencies.
- Kiểm cuối: **full frontend 618/618 pass**, 0 fail/skip/cancel, 2 suites, 128.57s, lệnh `node --test --test-concurrency=1`; gồm các ca C3/C4a và regression Preview/Export/service. Lint exit0; build exit0/26.57s, JS1159.03kB có cảnh báo chunk >500kB. Có cảnh báo test DOM KaTeX/React Router và MockTimers experimental. Diff/docs links được kiểm trước commit. Chưa native browser/visual/zoom/live FE–BE–DB; không nhận toàn task Done/Ready/Integrated.
- Bước tiếp: user push hai commit khi sẵn sàng, kiểm visual khi có công cụ/môi trường, tiếp C4b/C4c chỉ khi input đủ; C5 ghi bằng chứng trên head cuối. Chưa push/reply GitHub trong lượt này.

### 6.16. Scope PR109 được user chốt lại: FE theo walkthrough — 24/11/2026

- User xác nhận nhiệm vụ PR lần này là sửa FE đúng hướng UI walkthrough và yêu cầu cập nhật plan. Hai nghiệp vụ backend mở rộng không còn nằm trong acceptance của PR #109. Điều này thay mốc 6.13 từng gộp chúng làm điều kiện trước khi kết thúc C5; không biến API đang thiếu thành đã có và không bỏ lưu các dependency.
- Baseline code hiện tại `1b66140`, C3 `ea41610`, nhánh `fix/stage3-ui`; tracking local đã đồng bộ, working tree sạch trước lượt sửa docs. Bằng chứng 618tests/lint/build tại6.15 là lịch sử checks code, chưa được chạy lại ở lượt docs này. Còn C5 visual/browser/checks/review của FE; chưa nhận PR Ready/Approved/merged.
- **Hành vi còn khác walkthrough do API:** chưa manual retry một ô thiếu không candidate ID; chưa duyệt cặp khỏe khi session partial/read_only đang khóa. PR FE phải giữ fallback/guard và giải thích đúng. Không hứa đạt 100% mọi nghiệp vụ walkthrough; nghiệm thu đúng bố cục/thị giác/interaction và API hiện hành trong scope6.6.

**Follow-up ngoài PR #109, giữ ID input để truy vết:**

| Follow-up | Owner/input còn cần | Phạm vi triển khai sau, tách PR/task khi được giao | Tác động PR109 |
|---|---|---|---|
| C4b / `I-95-FIX-MISSING-RETRY` | Đạt AI/recovery + BE owner do Duy xác nhận; contract slot ID/request/response, idempotency/persistence/recovery, revision/mẫu/test/ETA | Khi đủ contract, nối recovery một ô X/Y qua FE service và Review/modal/tests; không giả ID hoặc dùng session retry thay targeted retry. Issue/PR follow-up chưa tạo, chưa tự phân công thêm. | Không block review/merge FE; tiếp tục ghi pending ngoài PR. |
| C4c / `I-95-FIX-PARTIAL-WRITE` | BE Review/snapshot owner do Duy xác nhận, phối hợp Bội Anh; state/permission/read_only contract mới, mẫu/test/ETA | Khi đủ contract, cập nhật adapter/guard/Review/tests để duyệt cặp hợp lệ khi partial; không coi ví dụ `slot.can_accept` là schema. Scope riêng khỏi PR FE hiện tại. | Không block review/merge FE; guard hiện hành vẫn là acceptance PR. |

- **Việc còn lại trong PR:** kiểm native browser theo6.7 (desktop1440/1366/1024, màn hẹp768/375/320, zoom200%, nội dung dài), sửa visual/interaction finding có căn cứ trong feature Stage3, chạy checks theo delta và lưu C5 evidence đúng head. Không code BE/đổi API hoặc ghép Export mới của PR110 từ việc này.
- Có thể chuyển Ready/merge khi acceptance FE, CI và review/approval hiện hành đạt; chưa browser evidence thì không ghi visual passed. PR109 có thể merge trong khi follow-up BE vẫn pending. Không tự đóng toàn Issue95 hoặc nhận tích hợp các follow-up hoàn tất.
- Đã cập nhật plan và changelog; handoff đồng bộ scope. Lượt này chỉ docs, kiểm links/diff; chưa code/commit/push/reply hoặc sửa metadata GitHub.

### 6.17. C5 — sửa finding và kiểm tự động cuối, native QA còn mở — 24/11/2026

- User giao các commit còn lại. Giữ quyết định scope FE tại6.16; không triển khai C4b/C4c hoặc đợi PR110/API key mới. Đọc lại PR109 và comments: remote head `1b66140`, base `efed79b`, vẫn Draft với title/body plan-only; chưa có input mới đổi contract. Chưa GitHub write.
- **Commit sửa `5e890f9` — `fix(stage3): keep solution links in dialog tab order`.** F109-C5-01: modal chỉ xem có nút đóng và link Markdown, nhưng trap chỉ tính button khiến không thể Tab tới link. Bổ sung link/tabindex không âm, giữ disabled/heading ngoài thứ tự Tab. Thêm regression readonly link, wrap hai chiều và Escape/restore focus; không đổi mutation/permission/API.
- Delta test-only ngoài feature: `frontend/src/test-support/domHarness.js` hỗ trợ selector nhóm đơn giản theo thứ tự DOM, phục vụ test button/link. Không thêm dependency hoặc đổi runtime sản phẩm. Full suite được chạy lại vì harness dùng chung.
- **Checks trên code cuối `5e890f9`:** Windows, Node22.20.0/npm10.9.3; full `node --test --test-concurrency=1` **619/619 pass**,2suites,0fail/skip/cancel,165.19s. Lint exit0/0warning; build exit0/55.22s, JS1159.09kB/gzip336.50kB còn chunk >500kB. Tests có warning KaTeX/Router/MockTimers và act ở Preview/MemoryRouter; không nhận không warning. Delta sau checks chỉ docs, không nhận đã rerun product tests trên commit docs.
- Focused C3/C5 2/2 pass trước mutation. Tạm đưa selector cũ về button-only làm ca C5 fail đúng assertion, đã restore trong `finally` trước full suite/lint/build. Author audit correctness/readability/architecture/security/performance; không tự nhận independent review/Approve.
- **[Gói C5 và ma trận nghiệm thu](../ui-walkthrough/stage3-fix/README.md):** nguồn walkthrough/hash đã kiểm lại; logs local; checklist desktop/mobile/zoom/nội dung dài/modal/toast/S07. Phiên này không có công cụ kết nối browser, nên không có native visual/keyboard/scroll/screenshot hoặc live FE–BE–DB mới. Không dùng DOM/build làm visual evidence; C5 chỉ hoàn tất phần tự động và bàn giao, chưa kết thúc native acceptance.
- Đã đưa cập nhật scope6.16 vào lượt docs này. Bước còn lại để chốt PR: push khi Philip thực hiện, cập nhật title/body khỏi plan-only, bổ sung native QA đúng head, CI áp dụng và peer approval. Hai follow-up BE không block PR FE. Chưa push/Ready/merge hoặc đóng toàn Issue95.

### 6.18. Feedback UI user — header gọn và vùng đọc tự nở — 24/11/2026

- User cung cấp ảnh bản chạy và yêu cầu bốn sửa đổi: giảm logo; bỏ note metadata/legend/nhãn điều hướng; bỏ bộ lọc trạng thái, giữ navigator câu; tăng chiều cao và cho câu dài mở rộng/cuộn trang. Quyết định này thay fixed-viewport/local vertical scroll và giữ filter của plan cũ. Ảnh user chứng minh vấn đề trước sửa, không phải visual pass sau sửa.
- Baseline `787b338` trên `fix/stage3-ui`, tree sạch/tracking local đồng bộ trước lượt này. Scope code: `Stage3ReviewPage.jsx`, `stage3Review.css`, `Stage3Review.test.js`; cập nhật plan/changelog/report cùng PR. Không đổi BrandLogo dùng chung, service/BE/API/guard hoặc flow duyệt.
- Logo có class riêng, `flex:0 0 auto`, rộng180px desktop/144px ở <=480px. Nguyên nhân giãn quá lớn là selector `.stage3-session-header > div` áp dụng `flex:1` cả lên div BrandLogo; chỉ khối chi tiết header còn flex-grow. Giữ artwork/tỷ lệ.
- Bỏ metadata số mã/câu/môn/khối, nhãn Điều hướng nhanh và legend màu. Bỏ hàng Tất cả/Chưa duyệt/Có cảnh báo/Đã duyệt, helper/state/render guard/filter persistence tương ứng; giữ navigator và trạng thái aria-label/icon/badge tại cặp. Resume chỉ câu/mã, bỏ qua field filter cũ; cặp pending/approved/missing đều luôn chọn được.
- Root/shell dùng min-height100dvh, không height viewport/overflow hidden. Comparison min-height `max(420px, calc(100dvh - 260px))`, body nở tự nhiên; hai cột desktop cao theo nội dung dài hơn, màn hẹp xếp dọc/cuộn trang. Không còn khung cuộn dọc cố định riêng từng body; công thức quá rộng vẫn cuộn ngang cục bộ. Modal vẫn giữ body cuộn riêng và focus/close guard hiện có.
- Tests cập nhật theo việc bỏ filter, giữ coverage phân loại cảnh báo/ô thiếu, đọc lại cặp approved, đổi mã giữ nguồn, chọn cặp và identity. Thêm ca sessionStorage legacy `filter:approved` không giấu câu pending và chỉ lưu câu/mã mới. Focused8/8 đạt; mutation đảo điều kiện chọn câu khiến ca resume fail đúng nguồn, đã restore trước checks cuối.
- Checks cuối trên delta code từ `787b338`: full `node --test --test-concurrency=1` **620/620 pass**,2suites,0fail/skip/cancel,142.77s; gồm Review/service/Preview/Export và legacy-storage. Lint exit0/0warning; build exit0/51.05s, JS1157.29kB/gzip335.87kB còn chunk >500kB. Tests còn warning DOM/Router/MockTimers/act như checkpoint trước. Delta sau checks chỉ docs. Native visual/zoom/scroll/keyboard sau sửa chưa kiểm do chưa có công cụ kết nối browser; không nhận visual passed/Ready.
- Author audit correctness/architecture/readability/security/performance: selection vẫn theo vị trí và candidate identity; không đổi mutation/permission; CSS chỉ scoped Stage3 và không còn filter dead code; không thêm dependency hoặc ghi nội dung đề vào storage. [Checklist C5](../ui-walkthrough/stage3-fix/README.md) đã đổi theo page scroll, cần user nghiệm thu lại đúng bản sau rebuild. Chưa push/GitHub write/Ready/merge.

### 6.19. Plan commit sửa review PR109 — 24/11/2026

**Baseline và bằng chứng mới:** local/remote head `854709d`, base `efed79b`, tree sạch trước lượt plan. PR đã Ready for review. Philip xác nhận manual test và duyệt trong conversation sau checkpoint6.18; không tự bổ sung kết quả từng viewport hoặc live backend từ xác nhận này. [Duy Request changes](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#pullrequestreview-6038442931) còn một blocker; [Tâm Commented](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#pullrequestreview-6040588696) xác nhận layout/6 viewport/long content/native focus bằng Chromium với API/auth mock, chưa Approve. Đây là kết quả reviewer báo, không phải agent chạy lại.

**Nguồn review và phân loại:**

| ID | Scope / trạng thái | Cách đưa vào lượt sửa |
|---|---|---|
| [F109-R1-03](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#discussion_r4679365695) | P2 bắt buộc, open; trong scope vì hard gate được thêm trong FE PR này. | R1 bỏ policy validation FE tự triển khai, tách cảnh báo khỏi quyền thao tác; giữ guard API hiện hành. Kết thúc phần quyết định blocked sau khi Q01 được làm rõ. |
| Tâm Q01 | **Accepted/đủ input cho R1**, theo phản hồi Duy7137928390, cập nhật25/11 tại6.21; chưa Integrated. | Không có permission hard-failure cấp candidate. Dùng guard hiện hành; BE loại hard failure trước persistence, warning/report là evidence. Không cần API mới. |
| Tâm Q02 | Giải trình navigator theo user6.18; chưa có bug wrap được tái hiện. | Giữ chips/nav đã được user duyệt. CSS hiện display:flex/overflow-x:auto/button flex-shrink:0, không đặt flex-wrap. R3 thu ca40câu để trả lời, không tự xây lại select/prev-next/equal-width tabs. |
| Tâm F01/F02/F03 | Trong scope, non-blocking; đề xuất tiếp thu. | R2 sửa khoảng cách divider, gom dot/label tiến độ và nhận diện link. |
| Tâm F04 | Trong scope, non-blocking; tiếp thu theo hướng giữ accessibility. | R2 đổi outline heading phù hợp theme, kiểm mouse/keyboard; không xóa focus ring toàn cục hoặc thay Tab trap. |

Các lo ngại approval transaction/thiếu options không còn được Duy giữ làm finding; không tạo task sửa mới cho chúng. C4b/C4c vẫn ngoài PR theo6.16; không đợi PR110 hoặc API key mới.

**Quyết định R1/Q01 cần làm rõ trước khi chốt thay đổi quyền:**

- Giữ yêu cầu user: cặp tạo lỗi phải có thông báo và không được duyệt trước khi xử lý. Plan này chưa tự thay yêu cầu đó bằng quyết định review.
- Tiếp thu vấn đề kiến trúc: `reviewPairIssue()` kiểm options/key/report rồi chặn handler Accept, nút dialog và Rà bộ đề; đây là policy mới ở FE. Không tiếp tục dùng phép so trùng/rỗng/key để quyết định quyền duyệt, không dời cùng validator sang helper khác.
- Contract snapshot hiện mô tả `has_warning`, `validation_report`, `validation_source` như evidence; chưa có định nghĩa chúng là permission per-candidate. Không tự coi `has_warning:true` hoặc `validation_report.is_valid:false` tương đương `can_accept:false`, không tự thêm field hoặc API.
- Đề xuất hỏi rõ: trong contract hiện có, BE ngăn candidate hard-failed xuất hiện như candidate có thể duyệt bằng invariant nào; nếu candidate vẫn xuất hiện, FE dựa vào trạng thái/quyền đã định nghĩa nào để chặn? Phân biệt ô thiếu/null/read_only với một candidate có warning. Cần dẫn contract/mẫu/test; không mặc định phải làm API mới.
- Nếu contract hiện chưa biểu đạt yêu cầu blocked, ghi nhận khoảng trống để owner/user chốt hướng trong phạm vi hiện hành hoặc follow-up riêng. Không lặng lẽ cho phép cặp lỗi để đóng finding, cũng không tự sửa BE. Khi chưa chốt, R1 chưa được đánh dấu ready-to-implement toàn bộ; R2 không phụ thuộc và có thể làm trước.

**Các commit dự kiến, chưa tạo ở lượt plan:**

| Commit | File dự kiến thay đổi | Scope và điều kiện đạt | Đầu vào / verification |
|---|---|---|---|
| **R1 — `fix(stage3): defer review validation decisions to backend`** | `Stage3Comparison.jsx`, `Stage3ReviewPage.jsx`, `Stage3InspectionDialog.jsx`, `Stage3Review.test.js` trong feature Stage3 | Bỏ quy tắc validation FE khỏi quyết định Accept/finalize; giữ presentation theo evidence BE. Chỉ dùng guard/permission đã có contract; giữ candidate identity, read_only/lock/busy, idempotency, receipt/refetch và thứ tự duyệt. Không sửa cơ chế approval đã được reviewer rút finding. | **Chốt Q01 trước khi hoàn tất hard-gate delta.** Review/service tests theo ma trận dưới, mutation kiểm guard liên quan và restore; lint/build theo delta. |
| **R2 — `fix(stage3): polish review spacing and keyboard focus`** | `Stage3ReviewPage.jsx`, `stage3Review.css` | F01 thêm khoảng cách giữa divider và nội dung biến thể; F02 gom dot + counter thành cùng cụm inline-flex không tách nhau; F03 link lời giải có underline/màu nhận biết trong popup; F04 focus heading dùng theme và giữ chỉ báo khi bàn phím. Không sửa MathRenderer/index.css/BrandLogo dùng chung, không đổi focus flow/modal/CTA hoặc navigator đã duyệt. | **Đủ input, độc lập R1, có thể làm trước.** Native375/320 và desktop, long content/warning, link/focus/Tab/Escape/restore; chạy existing focus regression. Không thêm tests chỉ kiểm tên class hoặc màu CSS. |
| **R3 — `docs(stage3): record review fixes and verification`** | `docs/tasks/ISSUE-95.md`, `docs/change_log.md`, `docs/ui-walkthrough/stage3-fix/README.md` | Gắn finding → commit → checks → trạng thái fix/reviewer xác minh; ghi câu trả lời Q01/Q02 đủ căn cứ. Giữ lịch sử manual approval tại854709d và yêu cầu kiểm lại delta trên head mới; cập nhật evidence đúng code cuối. | Sau R1/R2 và checks. Full frontend một lượt trên source cuối, lint/build; native fixture và API thật ghi tách. Docs links/diff. Chuẩn bị M5 cùng thread/ID cho Philip; chưa push hoặc gửi GitHub nếu chưa được giao. |

Đường dẫn bốn file R1/hai file R2 tính từ `frontend/src/features/stage3-review/`. Nếu có finding mới ngoài các file này, nêu delta trước khi mở scope. Kế hoạch/task list giữ tại mục này, không tạo tracker hoặc plan cạnh tranh.

**Checklist implementation và kiểm chứng dự kiến:**

- [ ] Làm rõ Q01 bằng contract/evidence hiện hành, ghi kết luận và giới hạn; không suy ra input mới.
- [ ] R1: warning/evidence không tự trở thành quyền cấm thao tác; RPC vẫn quyết định kết quả; UI phản ánh lỗi backend, không optimistic approve sai.
- [ ] R1: giữ coverage read_only/locked/missing-ID/busy,409/423, candidate bị thay, idempotency, refetch failure/reload, explicit approve và thứ tự câu trước/mã sau.
- [ ] R1: sửa ca C4a hiện đang coi fixture options trùng là luật quyền duyệt FE; thay bằng ca contract đã chốt, warning/unavailable evidence và phản hồi lỗi BE. Không xóa regression identity/recovery; case blocked chỉ thêm theo field/invariant đã được xác nhận.
- [ ] R2: source/variant spacing nhất quán; dot không rơi riêng khỏi nhãn375/320; link nhận biết trước focus; focus còn rõ khi bàn phím, không mất trap/Escape/restore. Không test CSS bằng assertions mirror implementation.
- [ ] R3/Q02: kiểm40câu tại desktop/mobile, giữ một hàng nav cuộn ngang và chọn được câu cuối; nếu không tái hiện wrap, phản hồi bằng code/ảnh đúng head thay vì tự redesign.
- [ ] Final checks từ `frontend/`: targeted Review/service `node --test --test-concurrency=1 src/features/stage3-review/Stage3Review.test.js src/services/stage3Service.test.js`; existing focus tests, rồi full `node --test --test-concurrency=1`, `npm run lint`, `npm run build` trên source cuối. Restore mutation trước build/checks cuối.
- [ ] Native QA sau fix: bộ6viewport theo6.7, nội dung dài, warning/missing theo contract; bổ sung zoom200% và các ca chưa được Tâm kiểm nếu môi trường cho phép. Không nhận Firefox/Safari/screen-reader/live DB đã đạt từ Chromium/mock. Nếu browser unavailable, ghi pending và nhờ nghiệm thu trên bản mới; không dùng DOM/build làm bằng chứng visual.
- [ ] Author audit đủ correctness/readability/architecture/security/performance và dead code; full suite/lint/build/docs checks; peer xác minh từng finding sau push và CI trên head cuối trước merge. Không tự mark resolved/Approve từ việc lên plan hoặc sửa local.

**Trạng thái lượt này:** chỉ lập plan/cập nhật docs và handoff. Chưa sửa source, chạy lại product tests, tạo commit, push hoặc reply GitHub. Kết quả620tests tại6.18 và trong review Tâm là bằng chứng854709d, không phải kết quả lượt plan hoặc head sửa tương lai.

### 6.20. R2 triển khai trước; R1/Q01 còn thiếu input — 24/11/2026

- User giao bắt đầu các commit. Đọc lại timeline PR109 trên854709d: không có reply mới sau review Tâm14:01:56Z giải quyết Q01. Triển khai R2 độc lập như6.19; chưa sửa `reviewPairIssue`, guard validation hoặc permission. Philip xác nhận trong conversation **chưa được cung cấp input Q01** và yêu cầu soạn comment để tự gửi. Chưa gửi comment GitHub hoặc tự gán field permission.
- **R2 commit `ebab331` — `fix(stage3): polish review spacing and keyboard focus`**, parent854709d. Scope đúng hai file: `Stage3ReviewPage.jsx`, `stage3Review.css`. F01 thêm margin-top16px cho nội dung biến thể sau header/warning; F02 wrap dot + counter trong một cụm inline-flex/nowrap, dot aria-hidden; F03 link Markdown trong inspection có màu highlight/underline/underline-offset và wrap URL dài; F04 heading focus dùng outline highlight2px, giữ rõ focus kể cả programmatic, không áp `outline:none` hoặc đổi Tab trap/restore.
- Không đổi text progress, candidate/state/handler/guard/CTA, luồng duyệt, source renderer hoặc global CSS. Không thêm dependency/test chỉ soi class CSS. R2 không thêm điều kiện logic mới để mutation-test; giữ nguyên các ca focus, counter/identity/read_only/refetch trong full suite.
- Checks trên code R2 `ebab331`: full `node --test --test-concurrency=1` **620/620 pass**,2suites,0fail/skip/cancel/118.23s, gồm regression focus/identity/progress/read_only/Preview/Export. Lint exit0/0warning; build exit0/32.30s, JS1157.37kB/gzip335.89kB còn chunk >500kB. Tests vẫn có warning DOM/Router/MockTimers/act. Logs workspace `tmp/stage3-r2-full-tests.log`, `tmp/stage3-r2-lint.log`, `tmp/stage3-r2-build.log`; source không đổi sau checks, các delta sau đó chỉ docs.
- Author audit correctness (progress/render/focus), readability (một cụm tiến độ), architecture (CSS scoped inspection/Stage3), security (không đổi renderer/raw HTML/quyền), performance (không thêm query/state/effect). Native375/320/desktop/link/focus sau sửa chưa kiểm do phiên không có công cụ browser; source fix không đồng nghĩa reviewer đã xác minh F01–F04.
- **R1 chưa triển khai:** thiếu kết luận Q01 như6.19, không tự nới/chặn thêm quyền để đóng F109-R1-03. R3 chỉ ghi evidence R2/phần còn mở ở lượt này; tổng kết cuối R1 và re-review sẽ cập nhật sau khi có contract và code tương ứng. Q02 có căn cứ CSS cuộn ngang, chưa chạy ca40câu trên native browser; không tự nhận đã tái hiện hoặc sửa wrap.

### 6.21. Input Q01 đã đủ theo phản hồi Duy — 25/11/2026

- Đọc trực tiếp [Duy7137928390](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7137928390), tạo24/11 lúc16:36:24Z (23:36 giờ Việt Nam). Phản hồi đối chiếu head9f5a04d/baseefed79b. Local/remote hiện9f5a04d, tree sạch trước docs; PR Ready/open/chưa merge. Mục này thay trạng thái thiếu input của6.19–6.20; không sửa lịch sử checks.
- **Accepted cho triển khai R1, chưa Integrated hoặc reviewer-verified:** hard-failed AI candidate bị loại tại generation service/AI mapping/persistence; manual regenerate có validator trước completion. Source reuse/fallback/revert dựa trên nguồn đã xác nhận, Stage1 kiểm options/key trước confirmation. Đã spot-check source local service/mapping/resolve_answer_key/duplicate checker và test known failures; migration026 gọi `_generation_persist_010`. Đây là static/source inspection, chưa chạy backend test/live DB ở lượt này; không nhận invariant mọi đường dữ liệu đã được chứng minh hoàn chỉnh.
- **Mapping FE Duy chốt:** candidate null không duyệt; candidate_id/status/read_only/session state và guard identity/busy/lock điều khiển actions; has_warning chỉ hiển thị warning; validation_report/validation_source/origin là evidence/provenance; progress là tiến độ/readiness. Unknown/unsupported/inconclusive/timeout không phải hard failure. Không mặc định cấm duyệt vì thiếu report/not_validated/math_verified:false; is_valid không phải field chung mọi origin. Không tạo can_accept hoặc API/migration/validator mới.
- **Giữ yêu cầu user theo đúng tầng:** B=C do AI được VAL-02 phát hiện, không persist successful candidate; sau retry có candidate hợp lệ/fallback hoặc slot thiếu. Duplicate source được chặn trước xác nhận. Nếu hard failure thực sự lọt snapshot, đây là bất nhất cần xác minh BE/follow-up riêng, không tự tái triển khai validator FE. Đây là căn cứ giải quyết Q01, không phải tự hạ yêu cầu UX hoặc xác nhận đầy đủ tính đúng toán học.
- **R1 đã đủ điều kiện bắt đầu:** bỏ reviewPairIssue và hard gate tự tính tại handler Accept/dialog/Rà bộ đề; giữ hiển thị evidence BE, missing-ID/read_only/busy/lock/identity/reconciliation/approval hiện hành. Sửa test C4a theo contract origin/warning/evidence khác nhau và phản hồi BE; giữ regression missing slot,409/423,candidate replacement,refetch failure,explicit approval và thứ tự câu trước/mã sau. Scope vẫn bốn file R1 tại6.19; không sửa BE/service/auth/router.
- **Chưa đủ đóng/merge PR:** R1 chưa code/commit; F109-R1-03 còn open và Duy Request changes chưa được thay bằng verification. Sau R1 chạy targeted/full frontend/lint/build trên source cuối, kiểm native delta R2/R1 và chuẩn bị M5 cùng thread; R3 tổng hợp evidence, CI và peer Approve trên head mới. Q02 có thể trả lời theo6.18/CSS và cần kiểm ca40câu nếu thu bằng chứng native. C4b/C4c tiếp tục ngoài PR.
- Lượt này cập nhật input/plan/changelog/report/handoff, chưa sửa source/chạy lại tests/commit/push hoặc gửi GitHub. Kết quả620tests ởebab331 là baseline trước R1, không phải verification cho bản sửa tương lai.

### 6.22. Plan các commit và checks cuối để hoàn thiện PR109 — 25/11/2026

**Baseline kiểm lại:** local/remote9f5a04d, baseefed79b; PR Ready/open, không có phản hồi mới sau Duy7137928390. Ba docs của lượt cập nhật Q01 còn uncommitted và được giữ lại. R2 sourceebab331/docs9f5a04d đã xong; không làm lại R2 hoặc chờ API mới. R1 đủ input theo6.21, thay dependency còn mở trong plan6.19. Lượt này chỉ plan/static checks, không nhận đã chạy lại product tests.

**Hai commit còn lại:**

| Mốc / commit | File dự kiến | Công việc và acceptance |
|---|---|---|
| **R1 — `fix(stage3): defer review validation decisions to backend`** | `Stage3Comparison.jsx`, `Stage3ReviewPage.jsx`, `Stage3InspectionDialog.jsx`, `Stage3Review.test.js` trong `frontend/src/features/stage3-review/` | Xóa `reviewPairIssue` cùng import/call site; bỏ gate tại handler Accept, disabled Approve và `hasInvalidVariants`/Rà bộ đề. Bỏ câu thông báo cấm duyệt tự suy từ validator. Giữ warning/evidence/provenance từ BE; không biến report thiếu/unknown/is_valid/math_verified thành permission hoặc tự nhận passed. Giữ mọi guard missing candidate/ID, status/session/read_only/busy/lock/identity/idempotency/reconciliation/explicit approval và thứ tự duyệt. Sửa C4a đúng contract Duy; không thêm validator hoặc field/API. |
| **R3b — `docs(stage3): finalize review fix evidence and handoff`** | `docs/tasks/ISSUE-95.md`, `docs/change_log.md`, `docs/ui-walkthrough/stage3-fix/README.md`; handoff workspace đồng bộ riêng | Đưa các cập nhật Q01 còn local cùng checkpoint R1/checks mới; map F109-R1-03/F01–F04/Q01/Q02 tới SHA/evidence/trạng thái. Chuẩn bị M5 cho Philip sau push, ghi rõ author fixed so với reviewer verified; không tự close finding, Approve, push hoặc merge. Native/API mock/live tách rõ. |

R1 commit source/test riêng trước, R3b chỉ docs sau checks; nếu phát hiện bug mới thì sửa source và kiểm lại trước R3b. Không thêm commit chỉ đổi tên class hoặc gom việc BE mới. Các docs pending hiện tại thuộc R3b, không bỏ/stash/reset thay đổi đã có.

**Ma trận regression cho R1, cần đạt trước commit source:**

- [ ] Candidate có warning, report thiếu/unavailable/not_validated hoặc report có shape khác theo origin vẫn hiển thị trung thực; quyền actions không do FE đánh giá nội dung/report. Dùng candidate snapshot đúng4options/key, không dùng fixture B=C giả để áp policy riêng.
- [ ] Candidate hợp lệ qua RPC Accept được đối soát đúng ID; cặp khác không mất approval. Candidate replacement không thừa hưởng approved; regenerate/revert yêu cầu duyệt chủ động; next theo câu trước/mã sau và không auto S07.
- [ ] Null/missing ID/read_only/locked/busy vẫn ngăn actions;409/423/lỗi mạng hiển thị đúng, không tự approve. ACK nhưng refetch thất bại vẫn pause ghi/finalize đến khi đọc snapshot fresh.
- [ ] Rà bộ đề vẫn chặn khi thiếu slot/chưa đủ approvals/partial/read_only/sync-required/busy; khi đủ điều kiện hiện hành không bị warning/report/fallback tự khóa thêm. Không coi progress ở FE là thay quyền Write API.
- [ ] Giữ tests focus/link/Tab/Escape/restore của R2/C5 và regression Preview/Export. Không xóa test identity/recovery để làm suite xanh. Tạm tái đưa gate warning vào đường đã sửa để chứng minh test bắt regression, khôi phục trước checks cuối; không mutation đồng thời với build.

**Checks và checkpoint thực hiện:**

1. Targeted từ `frontend/`: `node --test --test-concurrency=1 src/features/stage3-review/Stage3Review.test.js src/services/stage3Service.test.js`. Đọc failing assertion và sửa đúng contract; kiểm source không còn `reviewPairIssue`/`hasInvalidVariants` hoặc validator thay thế. Author audit correctness/readability/architecture/security/performance và dead code.
2. Sau khi source ổn định và mutation restored: full `node --test --test-concurrency=1`, `npm run lint`, `npm run build`. Ghi số tests thực tế, exit code/cảnh báo và SHA nguồn; không dùng620tests baseline làm kết quả R1. Không chạy lại full suite sau thay đổi chỉ docs.
3. Native UI trên head mới: desktop1440×900/1366×768/1024×768; màn hẹp768×1024/375×812/320×768; long content và zoom200%. Tập trung F01 spacing, F02 dot/counter, F03 link, F04 heading focus; missing/warning/fallback theo contract, guard/mutation flow khi có dữ liệu phù hợp. Môi trường mock phải ghi mock; không nhận live DB/Gemini hoặc mọi browser đã đạt.
4. Q02: navigator40câu trên desktop/mobile, giữ một hàng cuộn ngang và chọn được câu cuối. CSS hiện không wrap; nếu không có browser để kiểm thì ghi code evidence và native pending, không tự redesign hoặc báo đã tái hiện wrap.
5. R3b cập nhật docs/links/diff và handoff. Nếu browser chưa khả dụng, vẫn hoàn tất code/checks/commit đã được giao nhưng giữ native pending, chuẩn bị checklist để Philip/Tâm kiểm; không coi build/DOM là visual pass.

**Điều kiện kết thúc vòng sửa/merge:** R1 được sửa và checks trên source cuối đạt; delta native có kết quả được ghi nhận; M5 cùng ID/thread giải thích Q01 bằng [Duy7137928390](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7137928390), Q02 bằng6.18/CSS/case40câu. Sau Philip push, reviewer kiểm lại F109-R1-03 và UI F01–F04 trên đúng head, xử lý Request changes theo kết luận mới; CI áp dụng đạt và ít nhất một thành viên khác GitHub Approve theo CONTRIBUTING. Không đóng toàn Issue95 hoặc tích hợp C4b/C4c để merge PR FE.

**Trạng thái sau lượt plan:** chưa sửa source, chạy tests mới hoặc tạo commit. Input Q01 đã đủ, không còn blocker đầu vào cho R1; các ô checks phía trên là việc cần thực hiện, không phải kết quả đã đạt.

### 6.23. Kiểm trạng thái commit và chốt docs Windows — 25/11/2026

- User yêu cầu kiểm commits và commit docs. Kiểm thực tế tại repo Windows: nhánhfix/stage3-ui, HEAD/tracking local/remote PR đều9f5a04d, PR Ready/open/chưa merge. Ba file docs6.21/6.22 đang modified, chưa có source delta trong working tree. `git cat-file` không tìm được object c7044d6 hoặc a1b0ddb: chưa nhập các commit Linux vào repo Windows.
- Lượt trước ở checkout Linux riêng đã tạo **R1 c7044d6175e004e5a8678d7741f95d3df7956764** và **docs a1b0ddbbfa217a642efb210316ae72669fa25aa7**, chưa push. Bản Linux có targeted65/full621 tests, lint/build đạt, mutation warning-gate bị bắt rồi restore; native preview bị chặn kết nối/policy. Đây là bằng chứng lượt Linux đã báo, không phải checks chạy lại trên Windows hoặc remote9f5a04d.
- Commit docs Windows này giữ các cập nhật Q01/plan6.21/6.22 và bổ sung trạng thái hai checkout, không thay source hoặc giả nhận R1 đã Integrated trên PR. Không cherry-pick/import/overwrite docs Linux khi chưa có bundle tại repo này; không bỏ các docs Windows đã chuẩn bị.
- Bước tiếp: nhập/đối chiếu R1 và docs từ bundle hoặc nguồn Git có hai object, giữ cả plan Windows và evidence Linux; kiểm SHA/diff/source thực tế sau nhập, giải quyết phần docs có thay đổi khác nhau. Sau đó cập nhật head/checks, native/reviewer QA và CI/Approve sau push. F109-R1-03 chưa được reviewer xác minh trên PR; không tự resolve/merge.
- Lượt này chỉ docs: kiểm links/diff trước commit, không chạy product tests cho delta tài liệu và không nhận621tests là verification Windows. Không push hoặc gửi comment GitHub.

### 6.24. Áp hai delta Linux trên Windows, giữ docs local — 25/11/2026

- User giao ghi hai commit vào Windows. Repo bắt đầu tại c2b680a, tree sạch. Không tìm thấy bundle pr109 trong workspace hoặc Downloads; không có hai object Linux. Đã áp lại nội dung source R1 từ c7044d6 trên parent Windows c2b680a; commit mới có SHA khác, không nhận đã nhập nguyên object c7044d6/a1b0ddb.
- Bốn file source/test đúng scope: xóa reviewPairIssue và hard gate tự tính ở handler Accept/dialog/finalize; giữ warning/provenance theo BE và missing-ID/read_only/busy/lock/identity/idempotency/reconciliation/approval/next. Dialog hiển thị warning text từ BE, không dùng nó làm permission. C4a thay bằng matrix năm origins/reports và ca đủ approval với warning không tự khóa Rà bộ đề; không sửa BE/service/auth/global CSS.
- Targeted Windows Node22.20.0: Review/service65/65 pass/15.21s. Tạm tái thêm gate variant.has_warning vào disabled Approve khiến ca evidence fail exit1; restore trong finally trước full/lint/build. Checks cuối Windows được ghi dưới sau khi hoàn tất, không dùng kết quả Linux thay kiểm Windows.
- Docs tương ứng a1b0ddb được hợp nhất về mặt nội dung với plan/input6.21/6.22 và checkpoint Windows6.23, giữ nguyên lịch sử; không chép đè hai section trùng số từ checkout Linux. Báo cáo hiện phân biệt source Windows mới, source/checks Linux cũ và remote PR.
- Native delta R1/R2, navigator40câu và zoom200% còn pending; không có kết quả browser mới từ lượt ghi commit này. F109-R1-03 chỉ author-fixed sau kiểm source, chưa reviewer-verified/resolve. Sau push cần M5/CI/re-review/Approve trên head mới; C4b/C4c vẫn ngoài PR. Không push/comment/merge trong lượt này.
- **Source Windows 8a6f600ca4b95e8e18f9b28461937f791f0c04a5**, parentc2b680a, tương ứng delta c7044d6. Targeted65/65/15.21s, lint exit0/0warning, build exit0/28.07s JS1156.75kB/gzip335.50kB còn chunk warning. Mutation bắt disabled expectednull/actualempty rồi restore trước checks. Source không đổi sau checks. Author audit5trục, không có validator thay thế hoặc thay quyền.
- **Full suite Windows chưa xác nhận:** automatic approval review từ chối lần chờ kết quả vì HTTPS tới endpoint telemetry Visual Studio không đáng tin cậy, payload chưa rõ có thể lộ metadata repo/thực thi. Không rerun bằng workaround. Kết quả621Linux là evidence riêng của c7044d6, không phải Windows8a6f600. Cần xử lý hoặc user cho phép rủi ro external telemetry trước khi thử lại; CI/reviewer/native trên head mới còn cần đạt.
- Logs workspace: tmp/pr109-windows-r1-target.log, tmp/pr109-windows-r1-mutation.log, tmp/pr109-windows-r1-full.log (không dùng làm full-pass evidence), tmp/pr109-windows-r1-lint.log và tmp/pr109-windows-r1-build.log. Không commit raw logs/payload telemetry.

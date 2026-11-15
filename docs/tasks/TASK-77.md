# TASK-77 — Plan: Thiết kế lại Giao diện các Trang Khởi đầu (Login, Dashboard, Tạo Phiên & Stage 1)

- Nguồn giao việc: Issue #77, `docs/review/WORKFLOW.md`, `CONTRIBUTING.md`.
- Chế độ công việc: **Author** (chuẩn bị task plan, branch và Draft PR).
- Phụ trách: Frontend Engineer (Author); Reviewer đề xuất: Philip (`@philip-kkk` — FE Integration Owner) / Duy (`@nbduy2506` — Lead).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `feat/initial-pages-ui-redesign`.
- Base commit: `6e683c34399ff3b3a5689c121c5e62ef800c1909` (`origin/dev`).
- Trạng thái hiện tại: **PLANNING — CHƯA TRIỂN KHAI CODE UI**.

---

## 1. Mục tiêu và Tiêu chí Đạt

### 1.1. Mục tiêu
Chuẩn bị kế hoạch chi tiết, nhánh tính năng và Draft PR để tiến hành nâng cấp toàn diện giao diện người dùng (UI/UX) cho 4 màn hình khởi đầu của ứng dụng:
1. **Đăng nhập (Authentication / Login)**
2. **Bảng điều khiển (Dashboard / Danh sách phiên đề)**
3. **Khởi tạo phiên đề mới (Session Creation)**
4. **Giai đoạn 1: Tiếp nhận và xác nhận nguồn đề (Stage 1 / Source Ingestion & Review)**

### 1.2. Tiêu chí đạt (Acceptance Criteria)
- Giao diện đồng bộ, hiện đại theo bảng màu Dark Slate & Sky Blue của dự án, cải thiện kiểu chữ, khoảng cách và phân cấp thị giác.
- Tái sử dụng tối đa hạ tầng Tailwind CSS hiện có và thư viện biểu tượng `lucide-react` đã được cài đặt sẵn.
- Giữ nguyên 100% logic nghiệp vụ, các route, controller state, Supabase auth/session, và API contracts.
- Đảm bảo hiển thị đáp ứng (responsive) trên màn hình máy tính (desktop) và thiết bị di động (mobile).
- Đáp ứng các tiêu chuẩn trợ năng cơ bản (WCAG AA: độ tương phản màu, viền focus rõ ràng, gắn nhãn biểu mẫu, thuộc tính ARIA).
- Toàn bộ 420 frontend tests hiện có tiếp tục vượt qua (`npm --prefix frontend test`).
- Linter (`npm --prefix frontend run lint`) và build production (`npm --prefix frontend run build`) vượt qua không lỗi.
- Cung cấp hình ảnh so sánh Before / After khi triển khai thực tế.

### 1.3. Ngoài phạm vi (Out of Scope)
- Không chỉnh sửa backend, database migrations, hoặc Supabase RPC/schema.
- Không thay đổi thuật toán sinh đề AI hoặc bộ thẩm định SymPy.
- Không chỉnh sửa luồng Stage 2 (cấu hình biến thể), Stage 3 (duyệt biến thể/preview), hoặc Export (được quản lý theo các task riêng).
- Không đưa thêm các UI framework nặng (như Ant Design, MUI, Chakra) ngoài Tailwind CSS hiện hành.

---

## 2. Các Route và File Mã Nguồn Mục Tiêu

| Màn hình | Route URL | File mã nguồn chính | Thành phần / Vai trò |
|---|---|---|---|
| **1. Đăng nhập** | `/login` | `frontend/src/features/auth/LoginPage.jsx`<br>`frontend/src/features/auth/UserAvatar.jsx` | Thẻ đăng nhập Google OAuth, trạng thái loading/reauth, thông báo lỗi phiên. |
| **2. Dashboard** | `/dashboard` | `frontend/src/features/dashboard/DashboardRoute.jsx`<br>`frontend/src/features/dashboard/DashboardPage.jsx`<br>`frontend/src/features/dashboard/DashboardSessionCard.jsx`<br>`frontend/src/features/dashboard/CloneSessionModal.jsx` | Header người dùng, danh sách thẻ phiên đề, phân trang, hộp thoại nhân bản (clone), trạng thái rỗng và tải dữ liệu. |
| **3. Tạo phiên mới** | `/session/new/stage1` | `frontend/src/features/stage1-ingestion/Stage1Route.jsx`<br>`frontend/src/features/stage1-ingestion/sessionEntry.js` | Form nhập Tên phiên, Môn học, Khối lớp; nút hành động submit; breadcrumb quay về Dashboard. |
| **4. Stage 1 Nguồn đề** | `/session/:sessionId/stage1` | `frontend/src/features/stage1-ingestion/Stage1Route.jsx`<br>`frontend/src/features/stage1-ingestion/Stage1SourcePanel.jsx`<br>`frontend/src/features/stage1-ingestion/SourceQuestionPreview.jsx`<br>`frontend/src/features/stage1-ingestion/IncompleteContentDialog.jsx`<br>`frontend/src/components/MathRenderer.jsx` | Bộ chuyển đổi tab (nhập text / kéo thả file), thanh tiến độ upload, panel xem trước câu hỏi nguồn kèm KaTeX, banner trạng thái Blueprint & nút xác nhận đề nguồn. |

---

## 3. Hệ Thống Thiết Kế & Thành Phần Tái Sử Dụng

1. **Hạ tầng CSS & Token màu:**
   - **Tailwind CSS v3.4.11** cấu hình sẵn tại `frontend/tailwind.config.js`.
   - Nền tảng Dark Mode gốc: Background chính `slate-950` / `slate-900` (`#0f172a`), chữ chính `slate-50` (`#f8fafc`), viền thẻ `slate-800` / `slate-700`.
   - Màu nhấn chủ đạo (Primary Accent): Bảng màu `sky-400`, `sky-500`, `sky-600` cho CTA chính, viền focus ring, và liên kết.
   - Màu trạng thái: `rose-500`/`rose-400` (lỗi), `amber-500`/`amber-400` (cảnh báo/đang xử lý), `emerald-500`/`emerald-400` (thành công/đã duyệt).

2. **Thư viện Iconography:**
   - Sử dụng `lucide-react` v0.441.0 (đã có trong `package.json`).
   - Tận dụng các biểu tượng: `LogIn`, `LogOut`, `Plus`, `Copy`, `FileText`, `UploadCloud`, `CheckCircle2`, `Clock`, `AlertTriangle`, `ChevronLeft`, `ChevronRight`, `RefreshCw`, `Trash2`.

3. **Thành phần dùng chung:**
   - `MathRenderer.jsx`: Hiển thị công thức Toán LaTeX và Markdown, có sẵn cơ chế bắt lỗi an toàn (`MathErrorBoundary`).
   - `UserAvatar.jsx`: Hiển thị avatar người dùng hoặc chữ cái viết tắt.
   - Pattern Focus Trap & Accessibility từ `CloneSessionModal.jsx` và `IncompleteContentDialog.jsx`.

4. **Tài liệu tham chiếu UI:**
   - Walkthrough prototype: `docs/ui-walkthrough/PREVIEW.html` và `README.md` (các màn S00, S01, S02, S03 mô tả bố cục, tương tác và nhãn trạng thái).

---

## 4. Định Hướng Thị Giác Đề Xuất (Visual Direction)

1. **Phân cấp Nút Bấm (Button Hierarchy):**
   - **Primary CTA:** Nền `bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold px-4 py-2.5 rounded-lg shadow-sm transition-all focus-visible:ring-2 focus-visible:ring-sky-400`.
   - **Secondary / Ghost:** Viền `border border-slate-700 bg-slate-800/60 hover:bg-slate-800 text-slate-200 px-4 py-2.5 rounded-lg transition-all`.
   - **Danger / Destructive:** Viền `border border-rose-800/60 bg-rose-950/20 text-rose-300 hover:bg-rose-900/40 px-3 py-2 rounded-lg`.

2. **Form Controls & Inputs:**
   - Input/Textarea: `bg-slate-900/90 border border-slate-700 rounded-lg px-3.5 py-2.5 text-slate-100 placeholder-slate-500 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20 transition-all`.
   - Label rõ ràng, kèm helper text định hướng ngắn gọn và aria-describedby.

3. **Thẻ (Cards) & Bảng Trạng Thái (Status Badges):**
   - Khung thẻ bo tròn `rounded-xl`, viền mảnh `border-slate-800`, nền `bg-slate-900/80` có độ sâu thị giác.
   - Huy hiệu trạng thái (Status Pills) phân biệt bằng màu sắc ngữ nghĩa:
     - `draft`: Slate xám
     - `blueprinted`: Sky lam
     - `configured` / `generating`: Amber vàng hổ phách (kèm hiệu ứng pulse nhẹ khi đang sinh đề)
     - `approved` / `exported`: Emerald xanh lục
     - `failed`: Rose đỏ hồng

4. **Trạng thái Trống (Empty) & Tải (Loading):**
   - Thay thế các đoạn văn bản thô "Đang tải..." bằng Skeleton placeholder hoặc spinner mượt mà.
   - Màn hình rỗng ở Dashboard có biểu tượng minh họa nhẹ, lời chào thân thiện và nút CTA "Tạo đề mới" nổi bật.

---

## 5. Phạm Vi Triển Khai Chi Tiết Từng File

| File | Nội dung cải tiến dự kiến |
|---|---|
| `frontend/src/features/auth/LoginPage.jsx` | Căn giữa khung đăng nhập hiện đại, bổ sung biểu tượng Google chuẩn và icon bảo mật, thông báo trạng thái/lỗi hiển thị dạng banner nổi có icon, responsive cân đối trên mobile. |
| `frontend/src/features/dashboard/DashboardRoute.jsx` | Nâng cấp thanh Aside điều hướng trên cùng (User info + Avatar + Sign out), cải thiện thanh thông báo tiến trình mở phiên (opening session feedback) và phân trang. |
| `frontend/src/features/dashboard/DashboardPage.jsx` | Header có tiêu đề rõ ràng và nút "Tạo đề mới" nổi bật; grid thẻ responsive (`grid-cols-1 md:grid-cols-2 xl:grid-cols-3`); trạng thái loading dạng skeleton; trạng thái rỗng có minh họa; thông báo lỗi có icon cảnh báo và nút thử lại. |
| `frontend/src/features/dashboard/DashboardSessionCard.jsx` | Cấu trúc lại thẻ phiên: huy hiệu trạng thái góc trên, tiêu đề đậm rõ, danh sách metadata (môn, khối, ngày tạo) có icon tương ứng; nút hành động ("Tiếp tục" / "Xem đề", "Nhân bản") sắp xếp chỉn chu. |
| `frontend/src/features/dashboard/CloneSessionModal.jsx` | Hộp thoại modal bo góc hiện đại, backdrop mờ nhẹ (`backdrop-blur-sm`), input tên mới có focus rõ ràng, nút bấm căn lề chuẩn, giữ nguyên focus-trap và phím Esc. |
| `frontend/src/features/stage1-ingestion/Stage1Route.jsx` | Form tạo phiên mới (`sessionId === 'new'`): đóng gói thành card nổi bật, các trường Tên/Môn/Khối bố trí thoáng đãng, thông báo tạo đề mượt mà. Header phiên hiện hữu (`sessionId !== 'new'`): breadcrumb quay về Dashboard, thông tin phiên gọn gàng. |
| `frontend/src/features/stage1-ingestion/Stage1SourcePanel.jsx` | Cải tiến bộ chuyển chế độ nhập (Segmented control giữa Nhập trực tiếp và Tải tệp); khu vực kéo thả tệp (Dropzone) trực quan kèm icon và hướng dẫn định dạng (.docx, .tex, .md); banner trạng thái Blueprint hiện đại (tận dụng logic PR #65); nhóm nút hành động dưới đáy sắp xếp trực quan theo thứ tự quy trình. |
| `frontend/src/features/stage1-ingestion/SourceQuestionPreview.jsx` | Danh sách câu hỏi nguồn hiển thị dưới dạng thẻ độc lập; số thứ tự câu dạng badge; phương án trắc nghiệm A-D có viền nhẹ và làm nổi bật đáp án đúng; hiển thị công thức Toán chuẩn qua `MathRenderer`. |
| `frontend/src/features/stage1-ingestion/IncompleteContentDialog.jsx` | Hộp thoại cảnh báo lỗi nội dung nguồn hiển thị rõ các vị trí lỗi, có nút chuyển nhanh sang chế độ sửa phù hợp. |

---

## 6. Đánh Giá Xung Đột Tiềm Tàng với các PR Đang Mở

- **PR #76 (`fix/issue-75-w4-db-schema-sync`):** Tập trung vào DB migrations và RPC backend. Hoàn toàn không đụng vào mã frontend. **Không có xung đột.**
- **PR #71 (`feat/w4-mvp-06-finalize-preview-ui`):** Triển khai Stage 3 preview UI (`Stage3ReviewPage.jsx`). Không tác động vào Login, Dashboard hay Stage 1. **Không có xung đột.**
- **PR #69 (`feat/w4-mvp-09-export-download`):** Kế hoạch Export stage. **Không có xung đột.**
- **PR #66 (`feat/w4-mvp-10-resume-integration`):** Tài liệu phân tích resume. **Không có xung đột.**
- **PR #65 (`fix/issue-44-confirm-before-blueprint`):** Đã merge vào `dev`. Các thay đổi về `canonicalStatus`, `retrySourceArtifacts`, `isBlueprintReady` đã nằm đầy đủ trong `dev` và sẽ được giữ nguyên vẹn trong bản thiết kế lại.

---

## 7. Yêu Cầu Trợ Năng (Accessibility) & Responsive

- **Responsive Viewports:**
  - Desktop: 1440px, 1280px.
  - Laptop / Tablet: 1024px, 768px.
  - Mobile: 375px, 414px, 390px.
  - Tại màn hình hẹp (< 768px): Stage 1 chuyển thành bố cục 1 cột cuộn mượt hoặc tab chuyển đổi giữa Bộ nạp nguồn và Xem trước câu hỏi.
- **Trợ năng (a11y):**
  - Đảm bảo tỷ lệ tương phản tối thiểu 4.5:1 cho văn bản thông thường và 3:1 cho văn bản lớn theo chuẩn WCAG AA.
  - Mọi trường nhập liệu đều có `<label>` gắn với `id`, hỗ trợ `aria-describedby` liên kết thông báo lỗi và hướng dẫn.
  - Phím Tab di chuyển tuần tự hợp lý; viền focus outline/ring hiển thị rõ rệt trên tất cả các nút và liên kết.
  - Modal duy trì cơ chế bẫy focus (focus trap) và phím Esc để đóng.

---

## 8. Chiến Lược Kiểm Thử & Xác Minh

1. **Linter & Format:**
   ```bash
   npm --prefix frontend run lint
   ```
   *Yêu cầu: 0 lỗi, 0 cảnh báo.*

2. **Bộ Test Tự Động Frontend:**
   ```bash
   npm --prefix frontend test
   ```
   *Yêu cầu: 420/420 tests pass 100% (bao gồm các test suite về auth, dashboard, session cloning, stage1 ingestion, source confirmation).*

3. **Kiểm tra Đóng gói Production:**
   ```bash
   npm --prefix frontend run build
   ```
   *Yêu cầu: Vite build thành công không có cảnh báo nghiêm trọng.*

4. **Kiểm Tra Thực Tế (Visual & Functional Checklist):**
   - Luồng đăng nhập Google OAuth: chuyển hướng, hủy, lỗi và hiển thị avatar.
   - Luồng Dashboard: hiển thị danh sách, phân trang, lọc/mở phiên, nhân bản phiên.
   - Luồng tạo phiên mới: form nhập Tên, Môn, Khối; submit tạo phiên thành công và điều hướng sang `/session/:id/stage1`.
   - Luồng Stage 1: nhập văn bản thô, kéo thả file (.docx, .tex, .md), kiểm tra lỗi định dạng, xác nhận đề nguồn, theo dõi trạng thái Blueprint và nút chuyển tiếp sang Stage 2.
   - Chụp ảnh Before / After đối với từng màn hình để đính kèm vào PR khi chuyển sang trạng thái Ready for Review.

---

## 9. Các Quyết Định Thiết Kế Cần Tham Vấn Ý Kiến (Open Decisions)

1. **Bố cục Stage 1 trên Mobile/Tablet hẹp (< 768px):**
   - *Phương án A (Khuyến nghị):* Dùng Segmented Control chuyển đổi giữa tab "Nạp nguồn" và tab "Xem trước câu hỏi" trên mobile để tối ưu không gian hiển thị công thức Toán.
   - *Phương án B:* Xếp chồng 2 panel theo chiều dọc (cuộn trang liên tục).
2. **Thương hiệu & Tên sản phẩm hiển thị:**
   - *Phương án A (Khuyến nghị):* Giữ tên chính thức `Isomorphic Exam Synthesizer` kèm phụ đề "Biên soạn và sinh đề thi đẳng cấu".
   - *Phương án B:* Áp dụng thương hiệu ngắn gọn `Exam Mirror` như trong bản UI walkthrough prototype.
3. **Vị trí nút Tạo Phiên Đề Mới:**
   - *Phương án A (Khuyến nghị):* Giữ nguyên luồng hiện tại: bấm "Tạo đề mới" từ Dashboard sẽ điều hướng tới trang `/session/new/stage1`.
   - *Phương án B:* Mở một modal nhanh "Tạo phiên mới" ngay trên Dashboard tương tự như modal "Nhân bản đề".
4. **Phối màu Huy hiệu Trạng thái Phiên đề (Status Badges):**
   - Đề xuất bảng màu: `draft` (Slate xám), `blueprinted` (Sky lam), `configured`/`generating` (Amber vàng), `approved`/`exported` (Emerald xanh lá), `failed` (Rose đỏ). Cần xác nhận từ nhóm xem bảng màu này đã phù hợp với nhận diện chung chưa.

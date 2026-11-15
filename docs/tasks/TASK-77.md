# TASK-77 — Plan: Thiết kế lại Giao diện các Trang Khởi đầu (Login, Dashboard, Tạo Phiên & Stage 1)

- Nguồn giao việc: Issue #77, PR #78, `docs/ui-walkthrough/PREVIEW.html`, `docs/review/WORKFLOW.md`, `CONTRIBUTING.md`.
- Chế độ công việc: **Author** (chuẩn bị task plan, branch và Draft PR).
- Phụ trách: Frontend Engineer (Author); Reviewer đề xuất: Philip (`@philip-kkk` — FE Integration Owner) / Duy (`@nbduy2506` — Lead).
- Repo/nhánh: `isomorphic-exam-synthesizer` / `feat/initial-pages-ui-redesign`.
- Base commit: `6e683c34399ff3b3a5689c121c5e62ef800c1909` (`origin/dev`).
- Trạng thái hiện tại: **PLANNING — CHƯA TRIỂN KHAI CODE UI**.

---

## 1. Mục tiêu và Tiêu chí Đạt

### 1.1. Mục tiêu
Chuẩn bị kế hoạch chi tiết, nhánh tính năng và Draft PR để tiến hành nâng cấp toàn diện giao diện người dùng (UI/UX) cho 4 màn hình khởi đầu của ứng dụng:
1. **Đăng nhập (Authentication / Login)**: `/login`
2. **Bảng điều khiển / Thư viện đề (Dashboard / Session listing)**: `/dashboard`
3. **Khởi tạo phiên đề mới (Session Creation)**: `/session/new/stage1` & Modal tạo nhanh trên Dashboard
4. **Giai đoạn 1: Tiếp nhận và xác nhận nguồn đề (Stage 1 / Source Ingestion & Review)**: `/session/:sessionId/stage1`

Định hướng thiết kế chính thức: Chuyển đổi sang phong cách **Paper Canvas (Light Theme)** thanh lịch, chuyên nghiệp chuẩn theo nguyên mẫu `docs/ui-walkthrough/PREVIEW.html`.

### 1.2. Tiêu chí đạt (Acceptance Criteria)
- Giao diện đồng bộ theo bảng màu Paper Canvas của `PREVIEW.html`: Nền Canvas `#fafafa`, thẻ Surface `#ffffff`, viền Line `#e4e4e7`, màu thương hiệu Navy `#304c70`, điểm nhấn Gold `#f5ce58`, hỗ trợ Support blue-gray `#edf1f7`.
- Tái sử dụng tối đa hạ tầng Tailwind CSS hiện có và thư viện biểu tượng `lucide-react` đã được cài đặt sẵn.
- Giữ nguyên 100% logic nghiệp vụ, các route, controller state, Supabase auth/session, và API contracts.
- Đảm bảo hiển thị đáp ứng (responsive) trên màn hình máy tính (desktop) và thiết bị di động (mobile):
  - Stage 1 hiển thị 2 cột song song trên Desktop.
  - Stage 1 hiển thị Segmented Tab chuyển đổi giữa "Bộ nạp" và "Bản đọc" trên Mobile (< 768px). State được lưu tại parent để việc đổi tab không làm mất text đã nhập hoặc reset trạng thái upload/preview.
- Phương án mang đáp án đúng (`correct_key`) trong Bản đọc Stage 1 được làm nổi bật với nền `#edf1f7`, viền `#304c70` và gắn chip nhãn **"Đáp án"** chuẩn `PREVIEW.html`.
- Bọc container tối cục bộ cho Stage 2 và Stage 3 để các màn hình chưa thiết kế lại không bị vỡ bố cục hay xung đột màu (đây là giải pháp tương thích hiển thị - backward-compatibility wrapper, không phải redesign Stage 2/3).
- Modal tạo phiên nhanh trên Dashboard đóng vai trò lối vào UX tiện ích, tái sử dụng trực tiếp logic của `createSessionEntryController` nhằm bảo toàn kiểm tra xác thực và xử lý lỗi đồng nhất với route `/session/new/stage1`.
- Toàn bộ 420 frontend tests hiện có tiếp tục vượt qua (`npm --prefix frontend test`).
- Linter (`npm --prefix frontend run lint`) và build production (`npm --prefix frontend run build`) vượt qua không lỗi.
- Cung cấp hình ảnh so sánh Before / After khi triển khai thực tế.

### 1.3. Ngoài phạm vi (Out of Scope)
- Không chỉnh sửa backend, database migrations, hoặc Supabase RPC/schema.
- Không thay đổi thuật toán sinh đề AI hoặc bộ thẩm định SymPy.
- Không chỉnh sửa luồng nghiệp vụ Stage 2 (cấu hình biến thể), Stage 3 (duyệt biến thể/preview), hoặc Export (được quản lý theo các task riêng).
- Không đưa thêm các UI framework nặng (như Ant Design, MUI, Chakra) ngoài Tailwind CSS hiện hành.

---

## 2. Các Route và File Mã Nguồn Mục Tiêu

| Màn hình | Route URL | File mã nguồn chính | Thành phần / Vai trò |
|---|---|---|---|
| **1. Đăng nhập** | `/login` | `frontend/src/features/auth/LoginPage.jsx`<br>`frontend/src/features/auth/UserAvatar.jsx` | Thẻ đăng nhập Paper Card, thương hiệu Exam Mirror, nút Google OAuth chuẩn, thông báo trạng thái/lỗi. |
| **2. Dashboard** | `/dashboard` | `frontend/src/features/dashboard/DashboardRoute.jsx`<br>`frontend/src/features/dashboard/DashboardPage.jsx`<br>`frontend/src/features/dashboard/DashboardSessionCard.jsx`<br>`frontend/src/features/dashboard/CloneSessionModal.jsx`<br>`frontend/src/features/dashboard/CreateSessionModal.jsx` [NEW] | Header người dùng, danh sách thẻ phiên đề, phân trang, hộp thoại tạo nhanh (tái sử dụng controller), hộp thoại nhân bản, trạng thái rỗng và skeleton loading. |
| **3. Tạo phiên mới** | `/session/new/stage1` | `frontend/src/features/stage1-ingestion/Stage1Route.jsx`<br>`frontend/src/features/stage1-ingestion/sessionEntry.js` | Form Paper Card nhập Tên phiên, Môn học, Khối lớp; nút hành động submit; breadcrumb quay về Dashboard. |
| **4. Stage 1 Nguồn đề** | `/session/:sessionId/stage1` | `frontend/src/features/stage1-ingestion/Stage1Route.jsx`<br>`frontend/src/features/stage1-ingestion/Stage1SourcePanel.jsx`<br>`frontend/src/features/stage1-ingestion/SourceQuestionPreview.jsx`<br>`frontend/src/features/stage1-ingestion/IncompleteContentDialog.jsx`<br>`frontend/src/components/MathRenderer.jsx` | Bộ chuyển đổi tab (nhập text / kéo thả file), thanh tiến độ upload, panel xem trước câu hỏi nguồn kèm KaTeX và chip "Đáp án", banner trạng thái Blueprint & nút xác nhận đề nguồn. |
| **Cấu hình & Tương thích** | N/A | `frontend/tailwind.config.js`<br>`frontend/src/index.css`<br>`Stage2ConfigPage.jsx`<br>`Stage3ReviewPage.jsx` | Bổ sung design tokens Paper Canvas và bọc container tối cục bộ cho Stage 2/3 để chống xung đột màu. |

---

## 3. Hệ Thống Thiết Kế & Token Màu (Paper Canvas)

1. **Token màu chuẩn `PREVIEW.html`:**
   - `--canvas: #fafafa;` (Nền trang chính)
   - `--surface: #ffffff;` (Thẻ nội dung, card, modal)
   - `--rail: #f4f4f5;` (Thanh phụ, nền hover)
   - `--ink: #3f3f46;` (Chữ chuẩn)
   - `--strong: #27272a;` (Chữ tiêu đề, đậm)
   - `--muted: #6b6b74;` (Chữ phụ, nhãn mờ)
   - `--line: #e4e4e7;` (Đường kẻ, viền card)
   - `--highlight: #304c70;` (Màu thương hiệu Navy chính)
   - `--accent: #f5ce58;` (Màu vàng ấm điểm nhấn)
   - `--accent-soft: #fef7dd;` (Vàng nhạt)
   - `--support-bg: #edf1f7;` (Xanh lam xám nhạt hỗ trợ)
   - `--support-line: #d7e0ec;` (Viền hỗ trợ)
   - `--support-text: #52647b;` (Chữ hỗ trợ)
   - `--approved-bg: #eaf5ed;` / `--approved-ink: #255c3b;` (Thành công/đã duyệt)
   - `--danger-soft: #fff1f2;` / `--danger: #a32b32;` (Cảnh báo/lỗi)

2. **Thư viện Iconography:**
   - Sử dụng `lucide-react` v0.441.0 (đã có trong `package.json`).
   - Tận dụng các biểu tượng: `LogIn`, `LogOut`, `Plus`, `Copy`, `FileText`, `UploadCloud`, `CheckCircle2`, `Clock`, `AlertTriangle`, `ChevronLeft`, `ChevronRight`, `RefreshCw`, `BookOpen`, `GraduationCap`, `Calendar`.

---

## 4. Kế hoạch Kiểm Thử & Xác Minh

1. **Linter & Format:**
   ```bash
   npm --prefix frontend run lint
   ```
   *Yêu cầu: 0 lỗi, 0 cảnh báo.*

2. **Bộ Test Tự Động Frontend:**
   ```bash
   npm --prefix frontend test
   ```
   *Yêu cầu: 420/420 tests pass 100% (bảo toàn regression baseline).*

3. **Kiểm tra Đóng gói Production:**
   ```bash
   npm --prefix frontend run build
   ```
   *Yêu cầu: Vite build thành công không lỗi.*

4. **Kiểm tra Chức năng & Ca Cạnh biên (Edge cases):**
   - Luồng thất bại khi tạo phiên (lỗi mạng, validation rỗng).
   - Bảo toàn dữ liệu khi chuyển qua lại giữa các tab trên mobile ở Stage 1.
   - Redirect sau khi đăng nhập Google OAuth.
   - Trạng thái hiển thị ổn định của Stage 2 và Stage 3 qua container tối tương thích.
   - Chụp ảnh Before / After đối với từng màn hình để đính kèm vào PR khi chuyển sang trạng thái Ready for Review.

---

## 5. Kết Quả Triển Khai & Xác Minh (Implementation & Verification)

- **Trạng thái:** Đã hoàn thành triển khai giao diện Paper Canvas cho tất cả các trang mục tiêu.
- **Các trang đã nâng cấp:**
  1. **Đăng nhập (`/login`):** Thẻ Paper Card trung tâm, icon Google SVG chính thức, huy hiệu Exam Mirror, viền mảnh thanh nhã.
  2. **Dashboard (`/dashboard`):** Header mới kèm UserAvatar và Đăng xuất, lưới thẻ phiên Paper Canvas, huy hiệu trạng thái semantic, tích hợp `CreateSessionModal` (tái sử dụng 100% `createSessionEntryController`), phân trang Paper Canvas.
  3. **Tạo phiên mới (`/session/new/stage1`):** Form Paper Card trang nhã với bộ chọn nhanh môn học và khối lớp, breadcrumb điều hướng.
  4. **Stage 1 Nguồn đề (`/session/:sessionId/stage1`):** Tab chuyển đổi trên mobile, dropzone nét đứt, textarea font chuẩn, banner trạng thái Blueprint kèm 4 trạng thái, xem trước câu hỏi với chip "Đáp án" (`.answer-key-label`), math formula qua `MathRenderer`.
  5. **Cách ly Stage 2 & 3:** Bọc container tối cục bộ (`bg-[#0f172a] text-[#f8fafc] dark`) chống xung đột màu.
- **Kết quả kiểm thử tự động:**
  - `npm --prefix frontend test`: **427/427 pass** (100% pass, 0 fail, 0 skipped; bao gồm 4 regression tests cho F02/F03 trong `CreateSessionModal.test.js` và 3 regression tests cho F01 trong `DashboardRoutePagination.test.js`).
  - `npm --prefix frontend run lint`: **0 errors, 0 warnings** (`--max-warnings 0`).
  - `npm --prefix frontend run build`: **Vite production build thành công** (built in ~20s).

---

## 6. Xử Lý Các Findings Review (F01 - F04)

- **F01 (P1 — Phân trang Dashboard):** Nút "Sau" ở `DashboardRoute.jsx` trước đó bị nhầm `value - 1` thành `value + 1`. Đã sửa và bổ sung 3 regression tests trong `DashboardRoutePagination.test.js` kiểm tra biên trang 1/2 và 2/2.
- **F02 (P2 — Modal bị khóa sau lỗi tạo không xác định):** Cập nhật `CreateSessionModal.jsx` hiển thị nút "Kiểm tra danh sách phiên" khi `state.createUncertain` là true, đồng thời vô hiệu hóa nút submit để ngăn retry mù. Trong `DashboardRoute.jsx`, thêm `handleCheckCreatedSessions` tăng `refreshKey` giúp remount modal với controller mới sạch state. Đã kiểm thử qua `CreateSessionModal.test.js`.
- **F03 (P2 — Hủy request khi modal unmount):** Cập nhật cleanup effect trong `CreateSessionModal.jsx` để gọi `controller.cancel()` khi unmount hoặc đóng modal lúc đang pending, hủy bỏ AbortController signal và ngăn ngừa callback `onCreated` điều hướng muộn. Đã kiểm thử qua `CreateSessionModal.test.js`.
- **F04 (P3 — Thiếu token Tailwind):** Đã bổ sung các token `ink`, `strong`, `muted` vào `tailwind.config.js` đồng bộ với biến CSS trong `index.css`. Production build thành công và CSS generated đầy đủ.
- **Lưu ý Stage 2/3:** Giữ nguyên wrapper container tối (`bg-[#0f172a] text-[#f8fafc] dark`) để bảo toàn tính tương thích hiển thị cho đến khi có task redesign Stage 2/3 riêng biệt.

---

## 7. Xử Lý Phản Hồi Trải Nghiệm & Điểm Chưa Hợp Lý (UX Feedback & Aesthetic Polish)

Đã hoàn thành xử lý triệt để 3 điểm phản hồi UX và nâng cấp thẩm mỹ Paper Canvas cao cấp theo kế hoạch đã phê duyệt tại commit `3053cb6`:

1. **Bổ sung ảnh logo chính thức EXAM MIRROR:**
   - Trích xuất và tối ưu asset đồ họa gốc `frontend/public/brand-logo.png` từ bản thiết kế mẫu `PREVIEW.html`.
   - Tạo component chuẩn hóa `frontend/src/components/BrandLogo.jsx` với khả năng tự xử lý fallback và responsive.
   - Tích hợp vào thanh điều hướng Header (`DashboardRoute.jsx`), trang Đăng nhập (`LoginPage.jsx`) và đồng bộ thương hiệu.
2. **Khắc phục trùng lặp 2 nút Tạo bộ đề:**
   - Trong `DashboardPage.jsx`, tự động ẩn nút ở Header khi danh sách đề thi đang trống (`items.length === 0`), dồn toàn bộ sự chú ý của người dùng vào thẻ Empty State trung tâm với nút *"Tạo bộ đề ngay"* nổi bật.
   - Khi đã có đề thi (`items.length > 0`), nút *"Tạo bộ đề mới"* hiển thị cố định ở góc trên bên phải Header.
3. **Chuẩn hóa trường môn học trong CreateSessionModal:**
   - Thay thế ô nhập text tự do và các chip môn Vật lý, Hóa học, Sinh học, Tiếng Anh bằng huy hiệu cố định **“Môn học: Toán học”** (Read-only badge) kèm biểu tượng toán học ∑ và ghi chú *"Thẩm định đại số SymPy"*.
   - Giữ nguyên payload API `subject: 'Toán'` để tương thích 100% với backend và toàn bộ test suite.
4. **Kết quả kiểm định:**
   - `npm --prefix frontend test`: **427/427 PASS** (0 fail).
   - `npm --prefix frontend run lint`: **0 errors, 0 warnings**.
   - `npm --prefix frontend run build`: **Vite build production thành công** (~9.3s).

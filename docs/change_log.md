# Nhật Ký Quyết Định Công Nghệ & Thay Đổi Kiến Trúc (Architecture & Tech Change Log)

> **Mục đích:** Tài liệu này dùng để lưu trữ các **quyết định kỹ thuật (Architecture Decision Records - ADR)**, các thay đổi công nghệ hoặc điều chỉnh quy trình phát triển phát sinh trong quá trình triển khai dự án so với tài liệu thiết kế ban đầu.  
> Khi dự án triển khai, mọi thay đổi về stack, quy ước code, cấu trúc thư mục hoặc luồng phối hợp giữa các thành viên đều cần được ghi chép tại đây để đảm bảo tính minh bạch và thống nhất cho toàn đội.

---

## 📋 Mục lục các Quyết định

- [ADR-001: Chuẩn hóa Model AI `gemini-3.5-flash-lite`, Schema Repair Pass và Kiến Trúc Black-Box Generator](#adr-001-chuẩn-hóa-model-ai-gemini-35-flash-lite-schema-repair-pass-và-kiến-trúc-black-box-generator)
- [DEC-TV1-001: Chuẩn bị Login UI và kiểm tra frontend](#dec-tv1-001-chuẩn-bị-login-ui-và-kiểm-tra-frontend)
- [DEC-TV1-002: Tích hợp Google OAuth, profile và bootstrap Auth](#dec-tv1-002-tích-hợp-google-oauth-profile-và-bootstrap-auth)

---

## Chi tiết các Quyết định

### ADR-001: Chuẩn hóa Model AI `gemini-3.5-flash-lite`, Schema Repair Pass và Kiến Trúc Black-Box Generator
* **Ngày quyết định:** 16/10/2026
* **Người đề xuất:** TV5 (AI Integration & Generator)
* **Bối cảnh:**
  1. Tài liệu ban đầu ghi model `gemini-2.5-flash`. Tuy nhiên, Google đã cập nhật dòng model thế hệ mới `gemini-3.5-flash-lite` với độ trễ cực thấp (khoảng 3s) và độ chính xác toán học cao hơn trên SDK chính thức `google-genai`. Model này không hỗ trợ custom temperature/top-p; việc bỏ tham số sampling tùy chỉnh giúp request luôn ổn định.
  2. Các công thức toán LaTeX (như `\pm`, `\frac`, `\sqrt`) trong phản hồi JSON từ LLM thường gặp lỗi escape ký tự `\` trái với chuẩn JSON của RFC 8259, dễ gây `json.JSONDecodeError` hoặc `ValidationError`.
  3. Giảng viên chỉ có nhu cầu chọn số lượng $N$ đề thi (Stage 02) và bấm tái sinh câu hỏi không đạt yêu cầu (Stage 03) chứ không can thiệp sâu vào cấu trúc Blueprint.
* **Quyết định:**
  1. Cấu hình biến mặc định `GEMINI_MODEL=gemini-3.5-flash-lite` trong `backend/app/core/config.py`.
  2. Xây dựng module `backend/app/services/ai/schema_repair.py` theo kiến trúc bảo vệ 2 lớp:
     - *Lớp 1 (Heuristic):* Tự động làm sạch markdown fences và chuẩn hóa escape backslash LaTeX (`sanitize_latex_backslashes`).
     - *Lớp 2 (AI-Assisted Repair Loop):* Nếu heuristic không đủ, tự động gửi lại phản hồi lỗi cho Gemini kèm thông tin Pydantic error để AI tái cấu trúc (tối đa 2 lần retry).
  3. Xây dựng `VariantGenerator` (`generator.py`) như một hộp đen tự động:
     - Gán seed ngẫu nhiên độc lập cho từng biến thể ở từng phiên bản đề thi để bảo đảm tính tái lập (reproducibility).
     - Hỗ trợ `regenerate_single_variant` kèm cơ chế **Feedback-guided Regeneration**: tiếp nhận feedback lý do từ chối từ tầng Validation (TV7) hoặc giảng viên để AI tránh lặp lại lỗi cũ.
* **Hệ quả / Tác động:**
  - 100% các unit test (11/11 tests) chạy độc lập siêu nhanh (< 1s) với Mock Client.
  - Smoke test với Google Gemini API thật đạt độ trễ ~3.05s với 100% độ chính xác Pydantic schema.
  - Backend Router (TV3) và Frontend (TV1/TV2) có thể cắm trực tiếp mà không cần cấu hình phức tạp.

### DEC-TV1-001: Chuẩn bị Login UI và kiểm tra frontend

- Ngày/người thực hiện: 16/10/2026 — Trung Anh, TV1.
- Bối cảnh: TASK-101 cần màn đăng nhập; frontend có script lint nhưng chưa có công cụ và cấu hình ESLint.
- Quyết định: bổ sung ESLint cho JavaScript/JSX và React Hooks, lockfile, trang /login và router đầu vào.
- Phạm vi ảnh hưởng: frontend package/config, App.jsx và features/auth/LoginPage.jsx.
- Giới hạn: nút Google chỉ hiển thị thông báo; chưa kết nối Supabase hoặc xác thực người dùng.
- Kiểm tra: mở/bấm/reload trang login; npm run lint và npm run build thành công.
- Bổ sung: auth store dùng Zustand, ProtectedRoute và trang thử /auth-preview chỉ trong development.
- Kiểm thử bổ sung: ba unit test cho auth store bằng Node test runner; thêm script npm run test.
- Giới hạn: phiên mẫu không lưu sau reload; chưa kết nối Supabase, Google login hoặc API thật.

### DEC-TV1-002: Tích hợp Google OAuth, profile và bootstrap Auth

- Ngày/người thực hiện: 19–23/10/2026 — Trung Anh, TV1; nhánh `feat/task-101-google-login`, PR #7 → `dev`, chưa nghiệm thu.
- Bối cảnh: thay phiên đăng nhập mẫu bằng Supabase Google OAuth; cần ghép profile của Duy, không xác nhận đăng nhập sản phẩm chỉ bằng việc nhận token. Project chung chưa có các đối tượng profile khi kiểm ngày 23/10.
- Quyết định: giữ một Supabase client, một Zustand store và một Axios API client. Frontend `/login` nhận OAuth redirect, khôi phục/theo dõi phiên; `profile_pending` tải `GET /api/users/me` trước khi mở Dashboard. Đối chiếu user ID/version để bỏ kết quả cũ sau đổi tài khoản, giữ profile khi refresh cùng user. Lỗi 401 refresh/retry tối đa một lần; 403/lỗi tạm được phân biệt. Navbar hiển thị tên backend, ảnh metadata của đúng phiên, fallback chữ viết tắt và SDK sign-out local.
- API không đổi: dùng trực tiếp `id/email/name/created_at`, không thêm avatar vào schema hoặc tạo backend riêng. Endpoint Duy có fallback claims khi query không có dòng; việc xác nhận trigger được kiểm riêng trên Supabase.
- SQL đã áp: `backend/scripts/setup_auth_profiles.sql` lấy bảng/FK/RLS/policy/function/trigger từ schema nhóm, thêm SELECT cho `authenticated` và bổ sung profile Auth đã có. TV1 và Duy cùng quản lý Supabase; TV1 báo đã áp ngày 23/10. Script chỉ dành cho project chưa có các đối tượng Auth, không phải migration chạy lại; khi triển khai schema còn lại cần tránh tạo lại đối tượng/policy trùng tên.
- Cấu hình: host Vite đọc `frontend/.env.local`, Docker đọc `.env` gốc; backend dùng `SUPABASE_URL/SUPABASE_ANON_KEY`, frontend dùng `VITE_SUPABASE_URL/VITE_SUPABASE_PUBLISHABLE_KEY`. Không đổi stack, dependency hoặc đưa secret vào Git.
- Kiểm: TV1 báo login/profile200, reload, logout/route guard, avatar fallback, user B mới tự tạo profile đúng ID, đổi lại A, SELECT profile A/B chỉ trả dòng chính mình và refresh chủ động/profile/reload đều đạt. Agent ngày 22/10 kiểm 51 Node tests/lint/build và 17 browser cases riêng với fixtures; TV1 báo npm checks đạt sau avatar. Chi tiết/giới hạn tại [frontend README](../frontend/README.md#kiểm-tra).
- Giới hạn: expiry/refresh thất bại thật chưa kiểm trên cloud; 401/lỗi phiên đã có kiểm giả lập. Chưa CI head mới, static Nginx hoặc review/nghiệm thu. Dashboard list/clone/create/open vẫn mock, sẽ ghép TASK-103 ở nhánh riêng sau Auth review/merge; không suy SELECT profile chứng minh quyền ghi/sessions/storage.

### DEC-TV6-001: Shared Docker development workflow

- Date/author: 2026-10-19 — Khánh Tâm (TV6).
- Context: the original Compose stack serves a static frontend; host dependency
  installs, floating Python versions and fixed container/network names make team
  onboarding inconsistent.
- Decision: keep the static Nginx build, add a Compose Watch development overlay,
  a PowerShell setup/doctor/up/test/smoke/logs/down helper, Python dependency
  lock/hashes, pinned image digests, and container build/smoke CI.
- Node moves to the 22 line in Docker and existing CI to support the frontend's
  ESLint 10 engine requirements. Frontend packages and the build tool are unchanged.
- Frontend public Vite configuration is passed explicitly; backend secrets are not
  passed to frontend containers/builds. Vite's Docker proxy uses backend:8000.
- Impact/review: TV1 frontend startup/public env, TV3 backend startup/env/dependencies,
  TV4 CI. No API/schema, Gemini client, generator or validator implementation changes.
- Verification: see the Docker PR and docs/logbook.md for actual results; real cloud
  integration, another member's machine and ARM execution remain separate checks.

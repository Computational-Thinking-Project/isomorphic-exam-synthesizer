## 24/10/2026 — AI W2 (thay đổi cục bộ, chưa merge)

Gateway async dùng chung, xác nhận nguồn trước Blueprint, canonical core dùng chung CLI/backend, generator theo Blueprint kèm lời giải, bounded validation/retry, resume/callback và lifecycle. [Chi tiết và giới hạn nghiệm thu](ai-w2-integration.md). Chưa tích hợp routes/DB/SSE/UI W2; chưa nghiệm thu Docker/live API.

# Nhật Ký Quyết Định Công Nghệ & Thay Đổi Kiến Trúc (Architecture & Tech Change Log)

> Checkpoint tích hợp 26/10/2026: Auth PR #7 đã squash merge vào dev tại `bbb7c5e`. Nhánh TASK-103 đang ghép nền dev và giữ list/phân trang/Clone Modal thật; chưa lưu merge commit. Các mục DEC-TV1 bên dưới ghi đúng phạm vi lịch sử ở ngày thực hiện, không ghi đè bằng chứng hoặc nhận TASK-103 đã hoàn tất.

> **Mục đích:** Tài liệu này dùng để lưu trữ các **quyết định kỹ thuật (Architecture Decision Records - ADR)**, các thay đổi công nghệ hoặc điều chỉnh quy trình phát triển phát sinh trong quá trình triển khai dự án so với tài liệu thiết kế ban đầu.  
> Khi dự án triển khai, mọi thay đổi về stack, quy ước code, cấu trúc thư mục hoặc luồng phối hợp giữa các thành viên đều cần được ghi chép tại đây để đảm bảo tính minh bạch và thống nhất cho toàn đội.

---

## 📋 Mục lục các Quyết định

- [ADR-001: Chuẩn hóa Model AI `gemini-3.5-flash-lite`, Schema Repair Pass và Kiến Trúc Black-Box Generator](#adr-001-chuẩn-hóa-model-ai-gemini-35-flash-lite-schema-repair-pass-và-kiến-trúc-black-box-generator)
- [DEC-TV1-001: Chuẩn bị Login UI và kiểm tra frontend](#dec-tv1-001-chuẩn-bị-login-ui-và-kiểm-tra-frontend)
- [DEC-TV1-002: Tích hợp Google OAuth, profile và bootstrap Auth](#dec-tv1-002-tích-hợp-google-oauth-profile-và-bootstrap-auth)
- [DEC-TV1-003: Bổ sung DB cho Dashboard list/clone](#dec-tv1-003-bổ-sung-db-cho-dashboard-listclone)
- [DEC-TV6-001: Shared Docker development workflow](#dec-tv6-001-shared-docker-development-workflow)
- [ADR-002: In-Memory Pre-validation, Zero Cloud Mutation, và Atomic Ingestion Engine (TASK-202)](#adr-002-in-memory-pre-validation-zero-cloud-mutation-và-atomic-ingestion-engine-task-202)
- [DEC-BE1-003: Khắc phục Toàn Diện Phản Hồi Review PR #15 (Vòng 2)](#dec-be1-003-khắc-phục-toàn-diện-phản-hồi-review-pr-15-vòng-2)
- [DEC-BE1-004: Xử lý Triệt Để Ngoại Lệ Mạng và Khẳng Định Trạng Thái Commit CSDL (PR #15 Round 3)](#dec-be1-004-xử-lý-triệt-để-ngoại-lệ-mạng-và-khẳng-định-trạng-thái-commit-csdl-pr-15-round-3)
- [DEC-BE1-005: Chuẩn Hóa Bóc Tách Phương Án Bullet List Trong Parser Markdown & Text (PR #15)](#dec-be1-005-chuẩn-hóa-bóc-tách-phương-án-bullet-list-trong-parser-markdown--text-pr-15)
- [DEC-BE1-006: Khắc Phục Triệt Để Suy Luận Rollback CSDL & Ngoại Lệ Gateway (PR #15 Round 4)](#dec-be1-006-khắc-phục-triệt-để-suy-luận-rollback-csdl--ngoại-lệ-gateway-pr-15-round-4)
- [DEC-BE1-007: Bảo Toàn Ranh Giới Câu Hỏi Bảng Nhiều Cột và Nhận Diện Bảng Đáp Án Ô Riêng Biệt (PR #15 Round 5)](#dec-be1-007-bảo-toàn-ranh-giới-câu-hỏi-bảng-nhiều-cột-và-nhận-diện-bảng-đáp-án-ô-riêng-biệt-pr-15-round-5)

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

### DEC-TV1-003: Bổ sung DB cho Dashboard list/clone

- Ngày/người chuẩn bị và áp dụng: 24/10/2026 — Trung Anh/TV1 với hỗ trợ Codex; TV1 xác nhận đã chạy script trên Supabase chung. Nhánh `feat/task-103-dashboard-api` từ nền Auth `978003a`, được user cho tiếp tục trong lúc Auth chờ review. Sửa Auth vẫn ở nhánh Auth; trước merge Dashboard vào dev cần đối chiếu nền Auth đã được chấp nhận, đặc biệt khi squash.
- Bối cảnh: request list thật trả500/PGRST205 cho public.exam_sessions. TV1 kiểm SQL metadata: users có, ba bảng exam_sessions/source_questions/question_blueprints và hai enum session_status/question_status chưa có. Không chạy lại nguyên schema.sql vì Auth đã áp riêng.
- Quyết định: chuẩn bị `backend/scripts/setup_dashboard_sessions.sql` cho đúng trạng thái trên; lấy nguyên định nghĩa ba bảng/FK, session_status và ba policy sở hữu từ schema nhóm. Một transaction, chỉ tạo đối tượng chưa có, không thay thế users/Auth trigger/policy hoặc storage; xung đột đối tượng khiến transaction rollback.
- Quyền: đặt lại grants trên ba bảng mới rồi cấp authenticated SELECT/INSERT, thêm DELETE exam_sessions để backend dọn phiên clone lỗi; RLS vẫn kiểm sở hữu cha/con. Không cấp UPDATE, không cấp quyền bảng cho anon/PUBLIC. Các luồng Stage/editing cần thống nhất grants bổ sung với Duy; không đổi key hoặc dùng service-role để vòng qua quyền.
- Kiểm thật theo TV1: sau khi chạy SQL, request GET /api/sessions?page=1&page_size=20 bằng API client/phiên đăng nhập hiện hành trả200, items là mảng rỗng, total0/page1/page_size20. Chưa chạy clone thật hoặc kiểm RLS A/B cho sessions; list rỗng không chứng minh cách ly dữ liệu giữa hai tài khoản.
- Giới hạn: question_status không được ba bảng này dùng; API detail còn cần exam_versions, các bảng nghiệp vụ khác và storage chưa thiết lập bằng script này. Metadata kiểm cuối không thay kiểm bằng JWT user. Agent đối chiếu định nghĩa với schema, không trực tiếp chạy SQL hoặc gọi cloud thay TV1.
- Phạm vi code: chỉ setup SQL và tài liệu, chưa sessions service/UI/modal/navigation; chưa nghiệm thu TASK-103. Script không tạo dữ liệu thử. Khi Duy áp schema còn lại, tránh tạo lại các đối tượng/policy Auth và Dashboard đã có sau khi script được chạy.

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

### ADR-002: In-Memory Pre-validation, Zero Cloud Mutation, và Atomic Ingestion Engine (TASK-202)
* **Mã quyết định:** ADR-002 / DEC-BE1-002
* **Ngày quyết định:** 22/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Trong quá trình nạp đề thi nguồn (Stage 1 Ingestion), đề thi từ giảng viên có thể bị thiếu đáp án, sai cấu trúc hoặc chứa công thức Equation / MathType OMML không parse được sang LaTeX. Nếu ghi dữ liệu dở dang vào CSDL, hệ thống sẽ rơi vào trạng thái "ô nhiễm dữ liệu" (dirty state).
  2. Việc upload file lên Supabase Storage ngay khi nhận request dẫn đến rác bộ nhớ (orphaned files) khi file bị từ chối ở tầng validation, gây lãng phí dung lượng storage và tăng độ trễ HTTP.
  3. Thư viện `supabase-py` giao tiếp qua PostgREST HTTP REST API không hỗ trợ khối `async with db.transaction()` trực tiếp, có nguy cơ gây mất dữ liệu cũ nếu xóa xong nhưng insert câu mới bị lỗi giữa chừng.
* **Quyết định:**
  1. **100% In-Memory Pre-validation:** Bóc tách file DOCX/LaTeX/MD, quét bảng đáp án rời, và phát hiện OMML hoàn toàn trong bộ nhớ.
  2. **Zero Cloud Mutation (Phương án 1C):** Nếu phát hiện bất kỳ câu hỏi nào lỗi (thiếu đáp án, lỗi OMML, số câu không thuộc $[1, 20]$), backend **tuyệt đối không ghi đè CSDL và không upload Storage**. Trả về ngay **HTTP 422 Unprocessable Entity** kèm schema `errors: [{"question_no": X, "error_type": "..."}]` cho FE1 hiển thị modal hướng dẫn (`TASK-203b`).
  3. **Chỉ tải file lên Supabase Storage (Bucket `exam-sources`)** với prefix `{session_id}/{uuid}_{clean_name}` khi và chỉ khi 100% câu hỏi đã hợp lệ.
  4. **Atomic Replace qua PostgreSQL Stored Procedure (Phương án 2A):** Viết hàm SQL RPC `replace_source_questions(p_session_id, p_questions)` thực hiện xóa cũ (`question_blueprints`, `source_questions`) và bulk insert mới trong **1 Transaction ACID duy nhất** ở tầng CSDL (kèm fallback an toàn ở tầng ứng dụng nếu RPC chưa được migrate).
  5. **Bảo vệ File Upload (SEC-04):** Làm sạch filename chống Path Traversal (`re.sub` triệt tiêu `..`), chặn đuôi `.pdf` ngay từ vòng ngoài (HTTP 400), kiểm tra Magic Bytes `PK\x03\x04` và giới hạn giải nén $\le 50\text{MB}$ chống Zip Bomb.
* **Hệ quả / Tác động:**
  - Đảm bảo tính toàn vẹn dữ liệu đề thi: CSDL và Storage không bao giờ chứa dữ liệu rác hay trạng thái dở dang.
  - Tối ưu hiệu năng: Giảm số lượng network round-trips từ 3 xuống 1 khi cập nhật đề thi.
  - Phù hợp và ăn khớp 100% với hợp đồng API của Frontend (FE1) tại TASK-201, TASK-203b, và TASK-204.

### DEC-BE1-003: Khắc phục Toàn Diện Phản Hồi Review PR #15 (Vòng 2)
* **Mã quyết định:** DEC-BE1-003
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Parser DOCX bỏ qua các đoạn có text rỗng trước khi kiểm tra cờ OMML, khiến công thức hiển thị đứng riêng 1 dòng bị mất khỏi thân câu hoặc phương án mà không báo lỗi.
  2. Parser LaTeX trích xuất `\item[A.]` nhưng để sót môi trường bao ngoài danh sách (`\begin{enumerate}`, `\begin{tasks}`) ở cuối thân câu và phương án D.
  3. Stored Procedure `replace_source_questions` khai báo `SECURITY DEFINER` nhưng dùng `current_user` để nhận diện admin, khiến điều kiện luôn đúng vì `current_user` trong hàm này luôn là `postgres`.
  4. Ingestion Service trả về thông báo "Session state was not modified" cho mọi ngoại lệ còn lại, gây ngộ nhận khi gặp timeout mạng (máy chủ có thể đã commit thành công nhưng HTTP response bị timeout).
* **Quyết định:**
  1. **DOCX Parser:** Kiểm tra `content_omml_flags` ngay cả khi text đoạn rỗng; bật cờ `has_unparsed_omml = True` và chèn placeholder nhận diện, kích hoạt HTTP 422 `UNPARSED_OMML` từ chối đề thi thiếu nội dung công thức.
  2. **LaTeX Parser:** Xây dựng `clean_latex_list_wrappers` bóc tách sạch sẽ các thẻ mở/đóng môi trường danh sách (`enumerate`, `tasks`, `itemize`, `multicols`) khỏi thân câu và phương án, đồng thời bảo toàn 100% các môi trường toán học (`pmatrix`, `cases`, `aligned`).
  3. **SQL RPC:** Thay thế `current_user` bằng `session_user IN ('postgres', 'supabase_admin')` kết hợp `v_role = 'service_role'`, bảo đảm chỉ caller tin cậy mới được phân quyền quản trị.
  4. **Phân loại Ngoại lệ Ingestion:** Phân biệt lỗi timeout mạng (HTTP 504 Gateway Timeout với cảnh báo trạng thái chưa xác định, không cam kết dữ liệu chưa đổi) với lỗi SQL đã rollback (HTTP 500).
  5. **Tài liệu & Test:** Bổ sung script kiểm thử SQL 5 kịch bản phân quyền trên DB test; bổ sung unit tests cho OMML đứng riêng, LaTeX clean stem/options, và Timeout 504.

### DEC-BE1-004: Xử lý Triệt Để Ngoại Lệ Mạng và Khẳng Định Trạng Thái Commit CSDL (PR #15 Round 3)
* **Mã quyết định:** DEC-BE1-004
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Exception handler trước đây chỉ nhận diện lỗi mạng dựa trên từ khóa trong `str(exc)` (như "timeout", "connection reset").
  2. Các ngoại lệ HTTPX thực tế như `httpx.ReadTimeout("")`, `httpx.ReadError("")` có chuỗi thông báo rỗng, hoặc `RemoteProtocolError("Server disconnected without sending a response.")` khi mô phỏng rớt kết nối sau commit, dẫn đến việc lọt xuống nhánh mặc định HTTP 500 và khẳng định sai "was rolled back".
  3. Khi xảy ra lỗi mạng hoặc mất phản hồi, giao dịch có thể đã commit thành công trên PostgreSQL, việc khẳng định rollback hoặc chưa thay đổi là sai thực tế và nguy hiểm cho tính toàn vẹn dữ liệu.
* **Quyết định:**
  1. **Nhận diện theo Kiểu Ngoại lệ:** Sử dụng `isinstance(exc, ...)` để phân loại trực tiếp các lớp ngoại lệ `httpx.TimeoutException`, `httpx.TransportError`, `httpx.NetworkError`, `httpcore.ProtocolError`, `RemoteProtocolError` và các lớp con (kể cả khi chuỗi thông báo rỗng).
  2. **Trạng thái Chưa Xác Định (HTTP 504):** Mọi lỗi mạng và rớt kết nối trả về HTTP 504 Gateway Timeout với thông điệp rõ ràng: trạng thái chưa xác định, giao dịch có thể đã hoàn tất, và hướng dẫn frontend/người dùng kiểm tra lại phiên trước khi thử lại (`Please verify session state before retrying`).
  3. **Chỉ Khẳng định Rollback khi có Bằng chứng CSDL (HTTP 500):** Chỉ trả về thông báo "Database atomic replacement failed and was rolled back" khi nhận được ngoại lệ xác nhận từ CSDL (`postgrest.exceptions.APIError`). Các lỗi không xác định khác trả về HTTP 500 yêu cầu kiểm tra phiên và tuyệt đối không khẳng định đã rollback.
  4. **Kiểm thử Toàn Diện:** Bổ sung unit tests sử dụng trực tiếp các đối tượng ngoại lệ HTTPX thật gồm `httpx.ReadTimeout("")`, `httpx.ReadError("")`, `httpx.RemoteProtocolError("Server disconnected without sending a response.")`, `httpcore.RemoteProtocolError`, `APIError` có bằng chứng DB, và unconfirmed errors không khẳng định rollback.

### DEC-BE1-005: Chuẩn Hóa Bóc Tách Phương Án Bullet List Trong Parser Markdown & Text (PR #15)
* **Mã quyết định:** DEC-BE1-005
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Đề thi Markdown hoặc raw text từ giảng viên thường sử dụng danh sách gạch đầu dòng (`- A. ...`, `- B. ...`) hoặc dấu sao (`* A. ...`).
  2. Biểu thức chính quy `opt_pattern` trong `utils.py` trước đây chỉ nhận diện tiền tố phương án `[A-D][\.\)]`, khiến ký tự bullet đứng trước bị nuốt vào cuối thân câu hỏi (`stem`), đồng thời bullet của phương án kế tiếp bị dính vào đuôi nội dung phương án trước (ví dụ: `stem: 'Cho x = 1\n-'`, `options: {'A': '1\n-'}`).
  3. Tầng `markdown_parser.py` có khối fallback tìm bullet nhưng bị che khuất do `extract_options_from_text` vẫn nhận diện được 4 phương án dù bị dính ký tự bullet rác.
* **Quyết định:**
  1. **Nâng cấp `opt_pattern` tại nguồn `utils.py`:** Mở rộng pattern hỗ trợ `(?:[\-\*]\s*)?` trước nhãn phương án ở cả đoạn so khớp chính và lookahead kết thúc, bảo đảm điểm bắt đầu `first_opt_pos` bao gồm cả bullet của phương án A.
  2. **Làm sạch Thân câu và Phương án:** Cắt gọt triệt để ký tự bullet thừa, bảo đảm `stem` chỉ chứa nội dung câu hỏi và các giá trị trong `options` thuần khiết, không rò rỉ gạch đầu dòng hoặc dấu sao.
  3. **Bổ sung Unit Test Hồi quy:** Thêm test `test_markdown_parser_bullet_list_options` trong `test_parsers.py` kiểm chứng cho cả hai dạng bullet `-` và `*`.

### DEC-BE1-006: Khắc Phục Triệt Để Suy Luận Rollback CSDL & Ngoại Lệ Gateway (PR #15 Round 4)
* **Mã quyết định:** DEC-BE1-006
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. `is_database_rollback_evidence()` trước đây coi mọi instance của `postgrest.exceptions.APIError` hoặc exception có thuộc tính `code` là bằng chứng khẳng định PostgreSQL đã rollback transaction (`was rolled back`).
  2. Khi các reverse proxy / API Gateway trung gian (Cloudflare, Kong, Nginx) gặp sự cố, chúng trả về phản hồi HTML `502 Bad Gateway`, `503 Service Unavailable`, hoặc `504 Gateway Timeout`. PostgREST Python SDK khi nhận response HTML không parse được JSON sẽ đóng gói thành `APIError` với `code=502/504` và `message="JSON could not be generated"`.
  3. Lỗi gateway chỉ là sự cố lớp mạng chuyển tiếp; server CSDL phía sau có thể đã commit thành công transaction trước khi mất phản hồi. Việc khẳng định "was rolled back" là False Rollback Assertion nguy hiểm cho toàn vẹn dữ liệu.
* **Quyết định:**
  1. **Nhận diện chính xác SQLSTATE:** Chỉ coi là bằng chứng rollback từ CSDL khi `code` là mã PostgreSQL SQLSTATE hợp lệ gồm đúng 5 ký tự alnum (`^[0-9A-Z]{5}$`), đồng thời loại trừ triệt để các mã HTTP gateway (`500, 502, 503, 504`), loại trừ phản hồi không phải JSON (`message == "JSON could not be generated"`), và loại trừ nội dung HTML.
  2. **Thông điệp trung tính cho mọi trường hợp chưa xác định:** Mọi lỗi gateway, phản hồi không phải JSON, `APIError` có code không xác định, hoặc lỗi runtime chưa được chứng minh rollback đều trả về thông báo trung tính yêu cầu kiểm tra phiên (`"Database atomic replacement failed. Please verify session state before retrying."`) và tuyệt đối không khẳng định đã rollback hay dữ liệu chưa đổi.
  3. **Bảo toàn các ca timeout 504:** Giữ nguyên 100% hai hàm `is_network_timeout` và `is_network_transport`, không tự động gửi lại RPC mù quáng ở backend.
  4. **Kiểm thử mô phỏng Gateway chân thực:** Bổ sung 4 unit tests mới trong `test_ingest.py` kiểm chứng các ca Gateway HTML 502, Gateway HTML 504, non-JSON body và unknown code.

### DEC-BE1-007: Bảo Toàn Ranh Giới Câu Hỏi Bảng Nhiều Cột và Nhận Diện Bảng Đáp Án Ô Riêng Biệt (PR #15 Round 5)
* **Mã quyết định:** DEC-BE1-007
* **Ngày quyết định:** 27/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Khi đề thi DOCX sử dụng bảng nhiều cột để bố cục câu hỏi (ví dụ 1 hàng 2 ô, mỗi ô là một câu hỏi trọn vẹn), parser trước đây ghép các ô trên cùng hàng thành chuỗi duy nhất bằng `"  ".join()`. Việc này làm gộp các câu hỏi vào nhau, khiến câu đứng trước nuốt nhầm các phương án A, B, C, D của câu đứng sau và làm mất câu đứng sau trong khi API vẫn trả về 200.
  2. Bảng đáp án trong tệp DOCX thường được tách riêng biệt giữa ô số thứ tự và ô phương án chọn (ví dụ: ô 1 là "1", ô 2 là "A", ô 3 là "2", ô 4 là "B", hoặc bảng lưới 2 hàng). Khi ghép nối theo hàng, văn bản trở thành "1 A 2 B", không khớp với regex `KEY_PAIR_PATTERN` vốn yêu cầu dấu phân tách (như "1.A", "1: A"), dẫn đến lỗi từ chối sai 422 `MISSING_ANSWER`.
* **Quyết định:**
  1. **Bảo toàn ranh giới câu hỏi trong bảng nội dung:** Duyệt bảng câu hỏi theo từng ô riêng biệt (`cell-by-cell`) theo đúng thứ tự tài liệu thay vì gộp các ô trong hàng. Mọi đoạn văn và dòng ngắt (`\n`) trong từng ô được giữ nguyên thứ tự, bảo toàn tuyệt đối số lượng câu hỏi, thân câu và 4 phương án độc lập. Nếu bố cục ô bị sai lệch hoặc thiếu phương án, hệ thống từ chối ngay với HTTP 422 `INVALID_FORMAT`.
  2. **Chuẩn hóa nhận diện bảng đáp án dạng bảng ô riêng biệt:** Bổ sung hàm `try_parse_table_as_answer_key(tbl)` nhận diện tự động các kiểu bảng đáp án DOCX:
     - Dạng các cặp ô xen kẽ trong hàng (`1 | A | 2 | B` hoặc `Câu 1 | A`).
     - Dạng lưới 2 hàng (`Hàng 0: 1 2 3`, `Hàng 1: A B C`) có hoặc không có ô tiêu đề.
     - Dạng ô chứa sẵn cặp khóa (`1.A | 2.B`).
     - Bảng có tiêu đề "BẢNG ĐÁP ÁN" / "ĐÁP ÁN".
     Chuẩn hóa các cặp này thành chuỗi đáp án chuẩn `BẢNG ĐÁP ÁN: 1.A  2.B ...` ở cuối tài liệu để `parse_separate_answer_key` bóc tách đồng bộ và cô lập hoàn toàn khỏi thân câu hỏi.
  3. **Kiểm thử Toàn Diện:** Bổ sung 4 unit tests trong `test_parsers.py` và 2 API integration tests trong `test_ingest.py`, kiểm chứng chính xác số câu, thân câu, phương án và quy tắc Zero Cloud Mutation. Toàn bộ 270 backend tests đều đạt 100%.





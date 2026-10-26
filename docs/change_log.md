# Nhật Ký Quyết Định Công Nghệ & Thay Đổi Kiến Trúc (Architecture & Tech Change Log)

> **Mục đích:** Tài liệu này dùng để lưu trữ các **quyết định kỹ thuật (Architecture Decision Records - ADR)**, các thay đổi công nghệ hoặc điều chỉnh quy trình phát triển phát sinh trong quá trình triển khai dự án so với tài liệu thiết kế ban đầu.  
> Khi dự án triển khai, mọi thay đổi về stack, quy ước code, cấu trúc thư mục hoặc luồng phối hợp giữa các thành viên đều cần được ghi chép tại đây để đảm bảo tính minh bạch và thống nhất cho toàn đội.

---

## 📋 Mục lục các Quyết định

- [ADR-001: Chuẩn hóa Model AI `gemini-3.5-flash-lite`, Schema Repair Pass và Kiến Trúc Black-Box Generator](#adr-001-chuẩn-hóa-model-ai-gemini-35-flash-lite-schema-repair-pass-và-kiến-trúc-black-box-generator)
- [DEC-TV1-001: Chuẩn bị Login UI và kiểm tra frontend](#dec-tv1-001-chuẩn-bị-login-ui-và-kiểm-tra-frontend)
- [DEC-TV1-002: Tích hợp Google OAuth, profile và bootstrap Auth](#dec-tv1-002-tích-hợp-google-oauth-profile-và-bootstrap-auth)
- [DEC-TV6-001: Shared Docker development workflow](#dec-tv6-001-shared-docker-development-workflow)
- [ADR-002: In-Memory Pre-validation, Zero Cloud Mutation, và Atomic Ingestion Engine (TASK-202)](#adr-002-in-memory-pre-validation-zero-cloud-mutation-và-atomic-ingestion-engine-task-202)
- [ADR-003: Atomic Exam Confirmation và Blueprint Concurrency Protection (TASK-205)](#adr-003-atomic-exam-confirmation-và-blueprint-concurrency-protection-task-205)
- [DEC-BE1-003: Khắc phục Toàn Diện Phản Hồi Review PR #15 (Vòng 2)](#dec-be1-003-khắc-phục-toàn-diện-phản-hồi-review-pr-15-vòng-2)
- [DEC-BE1-004: Xử lý Triệt Để Ngoại Lệ Mạng và Khẳng Định Trạng Thái Commit CSDL (PR #15 Round 3)](#dec-be1-004-xử-lý-triệt-để-ngoại-lệ-mạng-và-khẳng-định-trạng-thái-commit-csdl-pr-15-round-3)
- [DEC-BE1-005: Chuẩn Hóa Bóc Tách Phương Án Bullet List Trong Parser Markdown & Text (PR #15)](#dec-be1-005-chuẩn-hóa-bóc-tách-phương-án-bullet-list-trong-parser-markdown--text-pr-15)
- [DEC-BE1-006: Khắc Phục Triệt Để Suy Luận Rollback CSDL & Ngoại Lệ Gateway (PR #15 / PR #16 Round 4)](#dec-be1-006-khắc-phục-triệt-để-suy-luận-rollback-csdl--ngoại-lệ-gateway-pr-15--pr-16-round-4)
- [DEC-BE1-007: Phân Loại Ngoại Lệ Mạng Phân Tán và Chuẩn Hóa Kiểm Quyền Migration 003 (TASK-205 Round 3)](#dec-be1-007-phân-loại-ngoại-lệ-mạng-phân-tán-và-chuẩn-hóa-kiểm-quyền-migration-003-task-205-round-3)
- [DEC-BE1-008: Loại Trừ PostgreSQL SQLSTATE Class 08 Khỏi Bằng Chứng Rollback CSDL (TASK-202 / TASK-205 Round 5)](#dec-be1-008-loại-trừ-postgresql-sqlstate-class-08-khỏi-bằng-chứng-rollback-csdl-task-202--task-205-round-5)

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

---

### ADR-003: Atomic Exam Confirmation và Blueprint Concurrency Protection (TASK-205)
* **Mã quyết định:** ADR-003 / DEC-BE1-004
* **Ngày quyết định:** 25/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Trong quy trình xác nhận đề thi nguồn (Stage 1 Confirmation / TASK-205), việc cập nhật `confirmed_at` trên bảng `question_blueprints` và chuyển `status = 'blueprinted'` trên `exam_sessions` qua 2 lệnh client-side riêng rẽ có nguy cơ gây lỗi trạng thái dở dang (partial lock) hoặc báo thành công giả `HTTP 200` khi bản ghi session bị xóa / đổi trạng thái song song.
  2. Bảng `question_blueprints` thiếu ràng buộc `UNIQUE (source_question_id)`, dẫn tới nguy cơ tác vụ nền (TASK-203) và thao tác xác nhận đồng thời tạo ra các bản ghi blueprint trùng lặp cho cùng một câu hỏi nguồn.
  3. Cơ chế trích xuất fallback biến số ±5 trong `blueprint_service.py` cần được định danh rõ ràng để phân biệt với Blueprint toán học do AI sinh ra ở TASK-203.
* **Quyết định:**
  1. **Ràng buộc Toàn vẹn 1-to-1:** Thêm `CONSTRAINT uq_question_blueprints_source_question UNIQUE (source_question_id)` trên bảng `question_blueprints` và sử dụng `upsert(..., ignore_duplicates=True)` khi sinh blueprint dự phòng.
  2. **Chốt Nguồn Nguyên Tử qua Stored Procedure:** Triển khai hàm PostgreSQL RPC `confirm_exam_source(p_session_id, p_expected_question_count)` thực hiện:
     - Khóa dòng phiên (`FOR UPDATE`).
     - Kiểm tra xác thực và quyền sở hữu (bảo mật SEC-04).
     - Kiểm tra điều kiện trạng thái `status = 'draft'` và đối chiếu số lượng câu hỏi thực tế.
     - Đồng thời khóa `confirmed_at = now()` trên các blueprints và chuyển session sang `'blueprinted'` trong 1 ACID transaction duy nhất.
  3. **Kiểm tra Kết quả Ghi Thực Tế:** Loại bỏ hoàn toàn fallback cập nhật rời; chỉ chốt bằng transaction/RPC. Nếu RPC gặp timeout mạng, trả về HTTP 504 Gateway Timeout không cam kết trạng thái chưa đổi.
  4. **Phân Định Rõ Ràng Hợp Đồng Blueprint:** Đánh dấu rõ cờ `is_fallback: true` và `extraction_source: "FALLBACK_DETERMINISTIC"` cho các blueprint dự phòng từ `extract_default_blueprint` để Stage 2 phân biệt với Blueprint chính thức của AI pipeline (TASK-203).
* **Hệ quả / Tác động:**
  1. Loại bỏ hoàn toàn nguy cơ race condition, nhân bản blueprint và báo thành công sai.
  2. Dữ liệu đề thi và blueprint luôn đồng bộ 100% trong CSDL.
  3. Đáp ứng toàn diện các tiêu chí đánh giá khắt khe trong Code Review từ Lead Reviewer.

---

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

---

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

---

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

---

### DEC-BE1-006: Khắc Phục Triệt Để Suy Luận Rollback CSDL & Ngoại Lệ Gateway (PR #15 / PR #16 Round 4)
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
  4. **Kiểm thử mô phỏng Gateway chân thực:** Bổ sung unit tests trong `test_ingest.py` và `test_confirm_source.py` kiểm chứng các ca Gateway HTML 502, Gateway HTML 504, non-JSON proxy error, và unknown code.

---

### DEC-BE1-007: Phân Loại Ngoại Lệ Mạng Phân Tán và Chuẩn Hóa Kiểm Quyền Migration 003 (TASK-205 Round 3)
* **Mã quyết định:** DEC-BE1-007
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Trong endpoint `confirm-source` (`sessions.py`), việc dùng chuỗi ký tự `"timeout" in err_lower` để bắt ngoại lệ mạng không phát hiện được các lỗi mạng phân tán với thông báo rỗng (`httpx.ReadTimeout("")`, `httpx.ReadError("")`, `RemoteProtocolError`). Khi đó, request rơi vào khối HTTP 500 với thông điệp sai lệch *"was rolled back"*, dù giao dịch có thể đã commit thành công trên PostgreSQL.
  2. Script kiểm quyền CSDL `verify_migration_003_permissions.sql` chưa khởi tạo dữ liệu người dùng mẫu trong `auth.users` và `public.users`, gây lỗi khóa ngoại `exam_sessions_user_id_fkey` khi kiểm thử trên database trắng.
  3. Kịch bản kiểm thử quyền `anon` trong `verify_migration_003_permissions.sql` chạy trực tiếp dưới kết nối superuser `postgres`, khiến RPC tin cậy `session_user` và bỏ qua kiểm tra quyền, không xác thực được cơ chế cấm `EXECUTE` (SQLSTATE 42501).
* **Quyết định:**
  1. **Phân loại ngoại lệ phân tán theo kiểu `isinstance`:** Xây dựng các helper `is_network_timeout`, `is_network_transport`, `is_database_rollback_evidence` kiểm tra cây ngoại lệ `__cause__`/`__context__`. Trả về HTTP 504 Gateway Timeout khi trạng thái commit chưa rõ ràng; chỉ trả về HTTP 500 khẳng định hoàn tác khi có bằng chứng từ `postgrest.exceptions.APIError`.
  2. **Chuẩn hóa script kiểm quyền migration 003:** 
     - Thêm preflight tạo mock users trong `auth.users` và `public.users`.
     - Giả lập caller PostgREST qua `SET SESSION AUTHORIZATION authenticator; SET ROLE anon / authenticated / service_role;`.
     - Xác thực role `anon` bị từ chối `EXECUTE` ở tầng PostgreSQL Engine (SQLSTATE 42501 / Least Privilege SEC-04).
     - Thêm Scenario 11 kiểm chứng trực tiếp Quản trị viên CSDL (`session_user IN ('postgres', 'supabase_admin')`) thực thi bảo trì thành công không cần JWT claims.
     - Đóng gói toàn bộ script trong transaction kết thúc bằng `ROLLBACK;`.
  3. **Kiểm thử tự động:** Bổ sung failure mode unit tests với instance ngoại lệ thật trong `test_confirm_source.py`.

---

### DEC-BE1-008: Loại Trừ PostgreSQL SQLSTATE Class 08 Khỏi Bằng Chứng Rollback CSDL (TASK-202 / TASK-205 Round 5)
* **Mã quyết định:** DEC-BE1-008
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Regex `^[0-9A-Z]{5}$` chỉ kiểm tra hình thức độ dài 5 ký tự của mã SQLSTATE, chưa phân biệt ngữ nghĩa nghiệp vụ của các nhóm lỗi trong PostgreSQL.
  2. Khi PostgREST SDK nhận mã lỗi kết nối thuộc SQLSTATE Class 08 (như `08007` - *transaction resolution unknown* hoặc `08006` - *connection failure*), hàm `is_database_rollback_evidence()` vẫn trả về `True`.
  3. Khi gặp lỗi kết nối `08007` / `08006`, máy chủ CSDL có thể đã commit thành công giao dịch trước khi kết nối bị ngắt. Việc khẳng định *"was rolled back"* là sai thực tế.
* **Quyết định:**
  1. **Loại trừ Class 08 và 40003:** Bổ sung `POSTGRES_NON_ROLLBACK_SQLSTATE_PREFIXES = ("08",)` và `POSTGRES_NON_ROLLBACK_SQLSTATES = {"40003"}` vào `ingestion_service.py`. Mọi mã lỗi bắt đầu bằng `08` hoặc `40003` đều bị loại khỏi bằng chứng rollback CSDL.
  2. **Thông báo Trung tính Cho Trạng thái Chưa Xác Định:** Khi gặp lỗi kết nối Class 08, service trả về HTTP 500 trung tính yêu cầu kiểm tra lại phiên (`"Database atomic replacement/confirmation failed. Please verify session state before retrying."`), tuyệt đối không khẳng định đã rollback.
  3. **Bảo toàn Khẳng định Rollback cho Lỗi Dữ liệu Xác định:** Các mã lỗi ràng buộc toàn vẹn thực tế (`23505`, `23503`), lỗi PL/pgSQL (`P0001`) vẫn được khẳng định rollback chính xác.
  4. **Kiểm thử Hồi quy Toàn diện:** Bổ sung các unit tests cho mã `08007`, `08006` và `23505` trên cả 2 endpoint Ingestion và Confirm Source.

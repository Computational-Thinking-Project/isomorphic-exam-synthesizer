# Team logbook

## 2026-10-19 — Khánh Tâm (TV6), Docker development setup

- Branch: chore/dev-docker-setup; PR base: dev.
- Added shared development Compose Watch configuration, setup/doctor/up/test/smoke/
  logs/down helper, Python lock/hashes, image digest pins, setup documentation and
  container CI. Preserved static Nginx build verification.
- Verified on Windows amd64 / WSL 2 with Docker Desktop 4.95.0, Engine 29.8.2,
  Compose 5.6.0. Checked Desktop relaunch and hello-world after local install repair.
- Existing .env preserved by repeated setup; configuration and Linux engine doctor pass.
- Dev startup: both services healthy; backend HTTP, frontend HTTP and frontend API
  proxy pass.
- Windows PowerShell 5.1 helper test command: 12 Python mock tests, SymPy LaTeX
  parser, 3 frontend tests, ESLint and Vite build pass.
- Ruff and Mypy in the pinned backend image pass (19 source files).
- Compose Watch: temporary frontend module served after sync; backend Python file
  mirrored; Uvicorn reload logs and post-reload health confirmed. Probes removed.
- Static stack: image build, health checks, root page, /login SPA fallback and
  frontend-to-backend proxy pass.
- Remote CI status belongs to the PR checks; do not infer a result from local tests.
- Pending: TV1/TV3/TV4 review, another member's machine, real Google/Supabase/Gemini
  integration and ARM execution. Existing frontend audit findings remain covered
  by the separate dependency work.
- TASK-107a and TASK-107b are not implemented by this Docker change.

## 2026-10-22 — Bá Duy (BE1 / johannguyen015), TASK-202 Ingestion Parsers & Endpoints

- Branch: `feat/be1-task-202-ingestion-parsers`; Base: `dev`.
- Implemented secure exam ingestion endpoints:
  - `POST /api/sessions/{session_id}/ingest-file` (multipart/form-data for .docx, .tex, .md)
  - `POST /api/sessions/{session_id}/ingest-text` (application/json for raw text, <= 100k chars)
- Implemented SEC-04 file security:
  - Filename sanitization against path traversal (collapsing `..` and non-alphanumeric symbols).
  - Explicit extension filtering (rejecting .pdf with HTTP 400).
  - DOCX magic bytes `PK\x03\x04` and structure verification (`[Content_Types].xml`, `word/document.xml`).
  - Anti-Zip Bomb decompression limit check (<= 50MB uncompressed).
  - Upload to Supabase Storage bucket `exam-sources` with prefix `{session_id}/{uuid}_{clean_name}`.
- Implemented 3 independent parsers with Unicode NFC normalization & Prompt Injection detection (SEC-02):
  - `docx_parser.py`: extracts questions, 4 options A/B/C/D, detects OMML/MathType tags (`w:oMath`, `m:oMath`, `w:object`).
  - `latex_parser.py`: parses enumerate environments, preserving 100% LaTeX math formulas.
  - `markdown_parser.py`: parses Markdown headers, lists, and inline math.
  - Separate trailing answer key parser matching formats like `1.A 2.B`, `1-A`, or tables.
- Implemented ADR-002 In-Memory Pre-validation & Zero Cloud Mutation:
  - Validates question count [1, 20], complete options, correct keys, and OMML formulas in-memory.
  - Database and Storage remain untouched on validation failure; returns structured HTTP 422 for frontend incomplete loop (TASK-203b).
- Implemented Atomic Idempotent Replace (Method 2A):
  - Created PostgreSQL Stored Procedure `replace_source_questions` in `backend/scripts/schema.sql` for single-transaction ACID execution.
  - Resilient application-level fallback for dev environments.
  - Non-blocking background Blueprint extraction hook (`trigger_blueprint_pipeline` with `asyncio.Semaphore(3)`).
- Quality Verification:
  - 13/13 parser tests passed (`pytest tests/test_parsers.py`).
  - 7/7 API ingestion tests passed (`pytest tests/api/test_ingest.py`).
  - 17/17 session regression tests passed (`pytest tests/api/test_sessions.py`).
  - Total: 37/37 tests passed (100%).
  - Mypy static type checking: 0 errors in 34 source files.
  - Ruff linter & formatter: all checks passed.

---

## 2026-10-22 — Bá Duy (BE1 / johannguyen015), TASK-205 Source Confirmation & Blueprint Activation (BE-03)

- Branch: `feat/be1-task-205-confirm-source`; Base: `dev`.
- Implemented Source Confirmation Endpoint:
  - `POST /api/sessions/{session_id}/confirm-source`
- Implemented Multi-Layer Guards & State Transitions:
  - Guard 1 (Ownership): `assert_ownership` synchronous verification (HTTP 403 / 404).
  - Guard 2 (State Precondition): Ensures session is in `'draft'` status (rejects with HTTP 409 Conflict if `'blueprinted'` or `'generating'`).
  - Guard 3 (Data Integrity): Ensures session contains at least 1 source question and zero missing answers (`has_missing_answer == False`, HTTP 422).
  - Guard 4 (Security SEC-02): Enforces explicit acknowledgment via `acknowledged_security_warnings: True` if any source question contains prompt injection / suspicious patterns (HTTP 422).
  - Guard 5 (Blueprint Engine): `ensure_blueprints_for_session` guarantees 100% of source questions have active mathematical blueprints (auto-generates deterministic fallback blueprints if background pipeline was incomplete).
  - Guard 6 (Atomic State Transition): Atomically updates blueprints `confirmed_at` and session status to `'blueprinted'`.
- Implemented Blueprint Engine Service:
  - `backend/app/services/parser/blueprint_service.py` with `extract_default_blueprint` and `ensure_blueprints_for_session`.
  - Connected `trigger_blueprint_pipeline` in `ingestion_service.py` to `ensure_blueprints_for_session`.
- Quality Verification:
  - 12/12 new confirm-source tests passed (`pytest tests/api/test_confirm_source.py`).
  - 49/49 total backend tests passed (100% pass rate).
  - Mypy static type checking: 0 issues in 35 source files.
  - Ruff linter: All checks passed on scoped files.
- Documentation:
  - Created API specification in `docs/api/confirm-source-endpoint.md`.

---

## 2026-10-24 — Bá Duy (BE1 / johannguyen015), TASK-202 Review Remediation (PR #15)

- Branch: `feat/be1-task-202-ingestion-parsers`; PR #15; Base: `dev`.
- Remediation fixes addressing code review comments from Philip (`philip-kkk`):
  - [P1] Database Security Hardening:
    - Updated `replace_source_questions` in `backend/scripts/schema.sql` and created standalone migration `backend/migrations/002_replace_source_questions_rpc.sql`.
    - Added atomic row lock (`FOR UPDATE`), strict caller identity validation (rejecting unauthenticated callers while permitting authenticated owner or `service_role`), and enforced session `status = 'draft'`.
    - Enforced least privilege: `REVOKE EXECUTE ... FROM PUBLIC, anon` and `GRANT EXECUTE ... TO authenticated, service_role`.
  - [P1] Strict Zero Cloud Mutation:
    - Removed non-transactional client-side fallback in `ingestion_service.py`. When RPC fails, operation fails fast with HTTP 500 without deleting or inserting records.
  - [P2] Complete OMML Equation Detection:
    - Updated `docx_parser.py` to flag all unconverted OMML math structures (including superscript `m:sSup`, subscript, radicals, etc.) as `is_unparsed_omml = True`.
  - [P2] Trailing Answer Key Separation in DOCX:
    - Truncated trailing answer key paragraphs prior to question segmentation in `docx_parser.py`, preventing answer keys from leaking into Option D.
  - [P2] LaTeX Enumerate & Nested Items Handling:
    - Replaced naive `re.split` with environment-aware parsing and lookahead in `latex_parser.py`. Distinguishes question `\item` from option `\item[A.]` and nested `enumerate` blocks.
  - [Q1 & Q2] Architecture Documentation:
    - Provided standalone idempotent migration `002_replace_source_questions_rpc.sql`.
    - Clarified that `trigger_blueprint_pipeline` is currently an asynchronous hook / logging placeholder pending full integration in TASK-203.
- Quality Verification:
  - Total tests increased from 37 to 42 tests (`pytest tests/test_parsers.py tests/api/test_ingest.py tests/api/test_sessions.py -v` -> 42/42 passed 100%).
  - Static type checking: `mypy` passed with 0 errors.
  - Linter & Formatting: `ruff check` and `ruff format --check` passed 100%.

---

## 2026-10-25 — Bá Duy (BE1 / johannguyen015), TASK-205 Review Remediation (PR #16)

- Branch: `feat/be1-task-205-confirm-source`; PR #16; Base: `dev`.
- Remediation fixes addressing code review comments from Philip (`philip-kkk`):
  - [P1] Synchronized Base Branch Fixes:
    - Merged `origin/feat/be1-task-202-ingestion-parsers` (PR #15) into `feat/be1-task-205-confirm-source`.
    - Inherited security hardening of `replace_source_questions` RPC (SEC-04 least privilege, FOR UPDATE lock, draft guard).
    - Inherited strict Zero Cloud Mutation in `ingestion_service.py`.
  - [P1] Atomic Confirm Source RPC (`confirm_exam_source`):
    - Created `confirm_exam_source` PostgreSQL RPC with row lock (`FOR UPDATE`), owner authorization, draft state check, question count integrity check, and simultaneous update of `confirmed_at` and session `status = 'blueprinted'` in 1 ACID transaction.
    - Added standalone idempotent migration `backend/migrations/003_confirm_exam_source_rpc.sql` and updated `backend/scripts/schema.sql`.
    - Enforced least privilege: `REVOKE EXECUTE ... FROM PUBLIC, anon` and `GRANT EXECUTE ... TO authenticated, service_role`.
  - [P1] Defense-in-Depth & Chống Báo Thành Công Sai (False 200):
    - In `sessions.py`: Added row match validation on session update. If 0 rows matched (concurrent deletion or state change), returns `HTTP 409 Conflict`.
    - Added automatic rollback of session state back to `draft` if blueprint confirmation fails during fallback execution.
  - [P2] Blueprint Deduplication & Concurrency Protection:
    - Added `CONSTRAINT uq_question_blueprints_source_question UNIQUE (source_question_id)` in `schema.sql` and migration `003`.
    - Updated `ensure_blueprints_for_session` in `blueprint_service.py` to use `upsert(..., ignore_duplicates=True, on_conflict="source_question_id")`, preserving existing and confirmed blueprints without duplication.
  - [Q1] Clarified Fallback Heuristic vs AI Contract:
    - In `extract_default_blueprint`: Added metadata tags `is_fallback: True` and `extraction_source: "FALLBACK_DETERMINISTIC"`.
    - Documented architectural contract with TASK-203 AI pipeline in `docs/api/confirm-source-endpoint.md` and `docs/change_log.md` (ADR-003).
- Quality Verification:
  - 18/18 tests in `backend/tests/api/test_confirm_source.py` passed (including 6 new remediation edge-case tests).
  - 252/252 tests passed in complete backend test suite (100% pass rate).
  - `mypy backend/app` passed with 0 errors across 40 source files.
  - `ruff check` passed on all scoped files.

---

## 2026-10-26 — Bá Duy (BE1 / johannguyen015), TASK-205 Review Remediation Round 3

- Branch: `feat/be1-task-205-confirm-source`; PR #16; Base: `dev`.
- Remediation fixes addressing Reviewer Philip's (`philip-kkk`) Round 3 feedback:
  - [P1] Phân Loại Ngoại Lệ Mạng Phân Tán Bằng `isinstance`:
    - Loại bỏ hoàn toàn chuỗi so khớp `"timeout" in err_lower` trong `backend/app/api/routes/sessions.py` và `backend/app/services/parser/ingestion_service.py`.
    - Định nghĩa các hàm kiểm tra ngoại lệ `is_network_timeout`, `is_network_transport`, và `is_database_rollback_evidence` duyệt toàn bộ chuỗi cây nguyên nhân (`__cause__` / `__context__`).
    - Phân biệt minh bạch: ngoại lệ mạng chưa rõ trạng thái commit (`httpx.TimeoutException`, `httpx.TransportError`, `httpcore.RemoteProtocolError`) trả về **HTTP 504 Gateway Timeout** kèm khuyến nghị kiểm tra trạng thái phiên trước khi thử lại, tuyệt đối không khẳng định đã rollback.
    - Chỉ trả về **HTTP 500 kèm khẳng định rollback** khi có bằng chứng từ chối từ `postgrest.exceptions.APIError`. Lỗi runtime không rõ nguyên nhân trả về HTTP 500 trung lập.
  - [P1] Chuẩn Hóa Script Kiểm Quyền SQL (`backend/tests/verify_migration_003_permissions.sql`):
    - Khởi tạo preflight user fixture trong `auth.users` và `public.users` (`v_owner_id`, `v_attacker_id`), loại bỏ triệt để lỗi khóa ngoại `exam_sessions_user_id_fkey` trên DB trắng.
    - Giả lập đúng cơ chế caller PostgREST thông qua `SET SESSION AUTHORIZATION authenticator; SET ROLE anon / authenticated / service_role;` cho 10 kịch bản PostgREST.
    - Kiểm tra `anon` bị từ chối `EXECUTE` ở tầng PostgreSQL Engine với SQLSTATE `42501` và `has_function_privilege` trả về `FALSE` (SEC-04 Least Privilege).
    - Bổ sung Scenario 11 kiểm chứng trực tiếp Quản trị viên CSDL (`session_user IN ('postgres', 'supabase_admin')`) thực thi bảo trì thành công không cần JWT claims.
    - Toàn bộ script nằm trong một transaction kết thúc bằng `ROLLBACK;` (zero dirty test data).
  - [P1] Đồng Bộ Các Cải Tiến Từ TASK-202:
    - Kế thừa script `backend/tests/verify_migration_002_permissions.sql` đã nghiệm thu từ nhánh TASK-202.
    - Đồng bộ `ingestion_service.py` với chuẩn type annotation `tuple[type[BaseException], ...]`.
  - [P2] Mở Rộng Bộ Kiểm Thử Ngoại Lệ Mạng:
    - Bổ sung 6 unit tests với instance ngoại lệ thật trong `backend/tests/api/test_confirm_source.py`: `httpx.ReadTimeout("")`, `httpx.ReadError("")`, `httpx.RemoteProtocolError`, `httpcore.RemoteProtocolError`, `APIError`, unconfirmed runtime error.
- Quality Verification:
  - 26/26 tests passed trong `backend/tests/api/test_confirm_source.py` (100%).
  - 266/266 tests passed trong toàn bộ test suite backend (100% pass rate, thời gian chạy ~50s).
  - `ruff check app/` đạt 0 errors (all checks passed).
  - `mypy app/ --ignore-missing-imports` đạt 0 errors trên 40 source files.
  - SymPy LaTeX smoke test: parse thành công `x**2 + 1`.

---

## 2026-10-26 — Bá Duy (BE1 / johannguyen015), TASK-205 Review Remediation Round 4

- Branch: `feat/be1-task-205-confirm-source`; PR #16; Base: `dev`.
- Remediation fixes addressing Reviewer Philip's (`philip-kkk`) Round 4 feedback:
  - [P2] Chuẩn Hóa Bằng Chứng Rollback CSDL & Loại Bỏ Suy Luận Rollback Sai Khi Nhận Lỗi Gateway:
    - Đồng bộ `is_database_rollback_evidence()` từ commit `4f227be` của PR #15 vào `backend/app/services/parser/ingestion_service.py`.
    - Dùng regex `POSTGRES_SQLSTATE_PATTERN = re.compile(r"^[0-9A-Z]{5}$")` để chỉ công nhận mã SQLSTATE chuẩn 5 ký tự alnum của PostgreSQL (ví dụ `P0001`, `23505`, `40P01`).
    - Loại trừ hoàn toàn các mã HTTP Gateway (`500, 502, 503, 504`), thông báo non-JSON (`message == "JSON could not be generated"` do SDK PostgREST sinh ra khi gặp HTML/text từ reverse proxy), và nội dung chứa HTML trong `details`.
    - Cập nhật endpoint `confirm_source` tại `backend/app/api/routes/sessions.py`: Mọi lỗi Gateway 502/503/504 hoặc ngoại lệ chưa xác minh đều trả về thông điệp trung tính an toàn: `"Database atomic confirmation failed. Please verify session state before retrying."` (HTTP 500, không khẳng định rollback).
    - Giữ nguyên các nhánh xử lý `is_network_timeout` và `is_network_transport` (`HTTP 504 Gateway Timeout`) và tuân thủ nghiêm ngặt nguyên tắc Zero RPC Auto-Retry.
  - [P2] Mở Rộng Unit Tests (Fault Injection Tầng Gateway):
    - Bổ sung 4 unit tests mới trong `backend/tests/api/test_confirm_source.py`: Gateway 502 HTML, Gateway 504 HTML, APIError mã lạ không phải JSON, APIError với code=None.
    - Đồng bộ 4 unit tests tương ứng trong `backend/tests/api/test_ingest.py` và cập nhật test RPC failure dùng SQLSTATE `P0001` chuẩn.
  - [Non-blocking] Cập Nhật PR Description:
    - Chuẩn bị nội dung cập nhật PR #16 description phản ánh chính xác số lượng test (274+ tests pass 100%) và phân tách rõ ràng code TASK-205 so với phần kế thừa PR #15.
- Quality Verification:
  - 30/30 tests passed trong `backend/tests/api/test_confirm_source.py` (100%).
  - 13/13 tests passed trong `backend/tests/api/test_ingest.py` (100%).
  - Toàn bộ backend test suite đạt 100% pass rate.
  - `ruff check app/` và `mypy app/ --ignore-missing-imports` đạt 0 errors.





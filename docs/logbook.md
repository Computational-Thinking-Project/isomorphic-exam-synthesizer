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

## 2026-10-26 — Bá Duy (BE1 / johannguyen015), TASK-202 Review Remediation Round 3 (PR #15)

- Branch: `feat/be1-task-202-ingestion-parsers`; PR #15; Base: `dev`.
- Remediation fixes addressing code review comments from Philip (`philip-kkk`):
  - [P2] Markdown Bullet List Option Parsing (DEC-BE1-005):
    - Upgraded `opt_pattern` regex in `backend/app/services/parser/utils.py` to recognize optional bullet markers (`-` or `*`) preceding option letters `[A-D]`.
    - Sanitized question stem and option contents to eliminate trailing dashes and asterisks from leaking into rendered KaTeX elements.
    - Added regression test `test_markdown_parser_bullet_list_options` in `backend/tests/test_parsers.py`.
  - [P2] Distributed Network Exception Handling (DEC-BE1-004):
    - Replaced naive string-based error message matching (`"timeout"`, `"connection reset"`) with explicit exception type matching (`httpx.TimeoutException`, `httpx.TransportError`, `httpcore.RemoteProtocolError`, `httpcore.NetworkError`).
    - Differentiated unconfirmed network dropouts (HTTP 504 Gateway Timeout, transaction state indeterminate, instructing client to verify session state) from verified database rejects with automatic rollback (`postgrest.exceptions.APIError` -> HTTP 500).
    - Expanded test suite with real exception instances (`ReadTimeout("")`, `ReadError("")`, `RemoteProtocolError(...)`).
  - [P2] Database Verification Test Script Hardening (`verify_migration_002_permissions.sql`):
    - Added preflight fixture setup creating prerequisite mock users in `auth.users` and `public.users` prior to session insertion, resolving foreign key violations on empty databases.
    - Implemented authentic caller context emulation using `SET SESSION AUTHORIZATION authenticator;` followed by `SET ROLE anon / authenticated / service_role;` and matching JWT claims.
    - Verified Least Privilege (SEC-04): `anon` caller is denied at the PostgreSQL function execute level (SQLSTATE 42501) and metadata privilege check.
    - Added dedicated Scenario 7 for direct database administrator callers (`session_user IN ('postgres', 'supabase_admin')`) succeeding without JWT claims.
    - Ensured full test execution wrapped in a transaction with trailing `ROLLBACK;`.
- Quality Verification:
  - Scoped TASK-202 tests: **54 tests passed** (23 parser tests + 14 ingest API tests + 17 session tests).
  - Full backend test suite: **246 passed** (100%).
  - Linter: `ruff check` passed 100% clean.
  - Static type checking: `mypy` passed with 0 errors.




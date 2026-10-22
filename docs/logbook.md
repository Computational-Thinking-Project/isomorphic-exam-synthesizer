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


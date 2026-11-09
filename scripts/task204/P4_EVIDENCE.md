# TASK-204 P4 — local integration evidence, 09/11/2026

Author self-verification on `feat/task-204-source-confirm`, product HEAD
`7d72dca58118a9d2dd9c8fd343933c931494ce49` plus uncommitted P4 harness/docs.
No production frontend/backend logic changed. This is not reviewer approval,
GitHub CI verification, cloud deployment or proof of AI content quality.

## Runtime

- Docker Engine 29.9.2, Compose 5.6.1; app built from repository base + dev Compose.
- Supabase CLI **2.54.11**. CLI 3.0.0 failed with Windows `uv_spawn`.
- Dedicated project `task204-supabase-local`, config in workspace
  `tmp/task204-supabase-cli2`, API 55421 / PostgreSQL 55422.
- PostgreSQL `17.6.1.029`; real GoTrue, JWT verification, PostgREST and RLS.
- Kong **2.8.1 Ubuntu**, digest
  `sha256:32747a08135f546ab817a9d883b3245492940906833c8bbac123dd72fff4bf07`.
  The original Alpine image failed to execute; copied busybox had zero bytes.
  Ubuntu passed a shell probe and was locally tagged to the CLI's expected Kong
  tag. This runtime deviation must be retained when reproducing the evidence.
- 16 schema/migration entries applied (schema + 002–016, empty 010 included).
  Database history queried; all 16 source SHA-256 values match the checkout.
- App project `exam-tv1-local`, frontend 3000 / backend 8000, both healthy.
  Backend attached **only** to Docker internal network `exam-tv1-p4-isolated`;
  frontend and local Kong bridge that network. External TCP probe was rejected.
  Backend AI keys empty; Python acceptance/fake worker has a loopback TCP guard.

## Results

| Check | Result / evidence scope |
|---|---|
| Two local accounts | PASS, real GoTrue admin creation and password login |
| JWT | PASS, backend missing token rejected; invalid token rejected by Auth |
| Ownership | PASS, foreign account cannot read/confirm source; RLS UPDATE returns no rows; replace-source RPC denied |
| Preview/revision | PASS, real GET UUID revision; missing key/revision 422; mismatched UUID revision 409 |
| Confirmation/replay | PASS, real confirm and same UUID key replay return same confirmation ID |
| Receipt cardinality | PASS, SQL query found zero sessions with more than one confirmation receipt |
| Private ledger | Direct service-role table read denied, ACL preserved; SQL audit used local administrator |
| Legacy RPC | PASS, correct RPC signature denied; SQL EXECUTE=false for anon/authenticated/service_role |
| CORS | PASS, preflight returns 200 and explicitly allows Idempotency-Key |
| Readiness | PASS, real worker claim/fail and HTTP pending/running/failed |
| Ready | PASS, schema-validated deterministic algebra producer publishes through real RPC; GET detail ready with nonempty modes and with [] |
| Browser | PASS, Chrome headless separate profile, actual app/Auth/PostgREST; keyboard confirm; response dropped after HTTP200; F5 enters same Stage2 with one POST |
| Stage2 | PASS in browser, locked pending; fake worker produces ready with []; F5 opens form |
| AI outbound | No provider keys; backend external TCP blocked by internal network; Python guard reports zero external attempts. No Gemini invocation |

The backend API suite uses FastAPI TestClient **without dependency overrides**;
Auth and Supabase clients make real HTTP requests to local GoTrue/PostgREST.
Browser checks use the actual HTTP frontend proxy and backend container.
Canonical readiness is controlled explicitly by the test driver, not an AI job.
Polling/failed retry UX remains FE2 W4-MVP-04; Q02 accepts F5 for this PR.

## Local artifacts / secrets boundary

Workspace `tmp/task204-supabase-local/` contains sanitized `auth-result.json`,
`browser-real-result.json`, `migration-history.txt`, migration manifests and logs.
`status.private.local.json`, `browser.private.local.json`, generated app override
and Chrome profiles are **private local artifacts**. Do not upload them.
Accounts are synthetic; credentials/JWT are never in this document or context.

API re-run uses `scripts/task204/check_local_auth.py` from a backend-image runner
sharing the local Kong network namespace, with a private status JSON and
`--api-url http://127.0.0.1:8000`. It writes a fresh draft browser session privately.
The committed-source browser driver `scripts/task204/browser-p4.mjs` consumes that
private file and must run after the API suite; each browser run consumes the draft
confirmation. `run_existing_p4.ps1` runs both in order. The relocated repo-source
wrapper, API suite and browser driver all passed a fresh rerun during final review.

## Review status

Local P4 evidence is now available for review. PR #42 remains Draft until author
publishes the reviewed harness/evidence and current-head checks/review are handled.
No commit, push, PR write, review request, approval or merge performed here.
Existing 355 FE / 170 API regression results remain historical at `3e3dff1`;
they were not rerun merely to add P4 tooling. New harness paths ran live above.

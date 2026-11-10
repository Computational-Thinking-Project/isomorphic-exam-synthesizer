# TASK-204 — P4 Supabase Local

## Reviewer rerun

Run from the repository root on Windows with Docker Linux containers, Node 22,
Chrome at `C:/Program Files/Google/Chrome/Application/chrome.exe`, and the local
stack described in [P4_EVIDENCE.md](P4_EVIDENCE.md). No cloud project is used.

```powershell
# Existing healthy P4 stack: generate a private local status file, never publish it.
npx.cmd --yes supabase@2.54.11 status --workdir ../../tmp/task204-supabase-cli2 -o json > ../../tmp/task204-supabase-local/status.private.local.json
.\scripts\task204\run_existing_p4.ps1 -EvidenceDirectory ../../tmp/task204-supabase-local
```

The runner creates two new synthetic accounts and disposable sessions, verifies
the API, then drives Chrome against the actual app. Browser confirmation consumes
the fresh draft session, so always run API setup before repeating the browser.
Private account/JWT/profile files stay in the evidence directory. Only sanitized
`auth-result.json` and `browser-real-result.json` may accompany a review.

For a fresh machine, initialize an **unlinked** CLI2 workspace with
`npx.cmd --yes supabase@2.54.11 init --workdir <workdir>`. In its generated
`supabase/config.toml` set project_id to `task204-supabase-local`, API port 55421,
DB port 55422, shadow port 55420; reserve other enabled service ports in 554xx.
Run `python scripts/task204/prepare_local.py <workdir>` once, then:

```powershell
npx.cmd --yes supabase@2.54.11 start --workdir <workdir> --exclude studio,imgproxy,edge-runtime,logflare,vector,supavisor,realtime,mailpit,postgres-meta
```

On this host the original Kong Alpine tag did not execute. Reproduction uses
`docker pull --platform linux/amd64 kong:2.8.1-ubuntu` followed by
`docker tag kong:2.8.1-ubuntu public.ecr.aws/supabase/kong:2.8.1` **before** startup.
Keep this local tag substitution explicit; it is not the original image.

Build the app using repository Compose base+dev plus
`scripts/task204/app-safe.override.yml` (env_file cleared, keys empty), project
`exam-tv1-local`. Redirect CLI status to the private file above. Then run
`python scripts/task204/prepare_app.py <evidence-directory>` to generate the
private app override without printing keys. Create Docker network
`exam-tv1-p4-isolated` with `docker network create --internal`, attach the local
Kong container using `docker network connect --alias supabase-local`, then add
the generated `app-p4.private.local.json` as the final Compose overlay and run
`up -d --wait`. Backend must have only that internal network; frontend has both
the app default and P4 network. Do not reuse or reset shared project IDs/volumes.

The checked runtime/deviations and historical startup notes follow. This runbook
does not create, link or push a cloud Supabase project.

## Latest checkpoint — P4 local passed 09/11/2026

See [P4_EVIDENCE.md](P4_EVIDENCE.md) for the current matrix, runtime deviations,
secret boundaries and review status. Earlier startup failures below are history.
The final API and real-browser rerun both passed. Auth/JWT/PostgREST/RLS are real;
canonical production uses a deterministic schema-validated algebra fake.
Browser response loss is injected after actual backend HTTP200, followed by F5.

CLI2-compatible runtime lives in workspace `tmp/task204-supabase-cli2`; sanitized
reports and private runtime files live separately in `tmp/task204-supabase-local`.
The current app is connected to local Supabase through the private P4 override,
and backend egress is blocked by Docker internal networking. The old app wrapper
loads the disconnected safe override; do not use it to infer the current P4 wiring.

## Application Docker recovery after reinstall — 09/11/2026

Docker 29.9.2 / Compose 5.6.1 rebuilt both application images successfully using
the repository base + dev Compose files. Dedicated project `exam-tv1-local` has
healthy frontend (3000) and backend (8000). HTTP frontend, backend `/health`, and
frontend `/api/health/metrics` proxy all returned 200. Runtime settings confirmed
empty AI keys and disconnected cloud Supabase. This is not P4 acceptance.

Local-only override and wrapper are outside the repo in workspace
`tmp/task204-supabase-local/app-safe.override.yml` and `app-local.ps1`.
The wrapper accepts up/down/ps/logs; `app-smoke.ps1` repeats the three HTTP probes.
Compose runs detached without Watch; rebuild to apply source changes. Do not use
the default helper against an existing cloud `.env` for the no-quota P4 run.

## Local checkpoint 09/11/2026

User authorized a Docker Desktop restart after daemon API 1.56 and 1.47 both
returned 500. Restart completed and daemon reported 29.9.2. Dedicated stack retry
downloaded more images but repeatedly reported `unexpected EOF`, then exited
with Windows process code -1073740791. Host shells also failed with insufficient
memory / pipeline creation errors. No healthy Supabase stack was established.

Independent checks passed: migration preparer produced 16 files with exactly one
empty migration; `LoopbackGuard` rejected an external test IP without connecting;
new Python scripts compiled and `git diff --check` passed before the host failure.
`check_local_auth.py` is ready to execute against a private status JSON, but has
not run against GoTrue/PostgREST. It creates synthetic local users and a session;
it checks real login, invalid JWT and cross-owner table visibility only. It does
not claim backend, RPC, fake-production or browser acceptance.

After local stack is healthy, redirect `supabase status --workdir <workdir> -o json`
to a private file in the workspace tmp directory, then run:

```text
<repo>/.venv/Scripts/python.exe scripts/task204/check_local_auth.py <private-status.json> <sanitized-result.json>
```

Do not print or publish the private status file. The runner enforces loopback URLs
and TCP connections, does not replace Auth/DB dependencies and publishes no JWT.

## Local checkpoint 08/11/2026

Supabase CLI 3.0.0 initialized `tmp/task204-supabase-local` in the workspace.
Ports were changed to 554xx. The preparation script executed successfully and
created 16 migration files plus a SHA-256 manifest (schema + 002–016, empty 010).
This is preparation evidence only, not applied migration history.

Startup failed while pulling images: Docker credential helper and Go runtime
reported Windows paging-file exhaustion / out-of-memory. A reduced-service retry
also exhausted resources and was interrupted. Even a follow-up verification shell
could not load System.Management.Automation.dll due to the same paging-file error.
No Supabase integration assertions or browser acceptance ran. Fake-provider wiring
and HTTP acceptance runner are still pending. No cloud mutation or AI call made.

Resume after host resources are available: inspect only containers carrying the
dedicated project ID, finish startup, inspect migration history, then implement and
run the fake-provider/HTTP checks. Do not reset or stop unrelated Docker resources.

Author scope: PR #42, baseline `7d72dca`. Q02 accepted by FE2 on 08/11:
F5 updates readiness; polling and failed/retry UX remain W4-MVP-04.
This harness must not link, push, reset or deploy a cloud project.

## Execution plan

1. Initialize a dedicated CLI workspace named `task204-supabase-local` outside
   the product checkout; reserve ports 55420–55429. Do not reuse shared containers.
2. Run `prepare_local.py <workdir>` with Python 3.11+ before first startup.
   It copies the current schema and migrations in filename order, recording hashes.
   Migration 010 is intentionally empty in this baseline. No migration is inferred
   from the previously published PostgreSQL fixture results.
3. Start Supabase Local, inspect applied history, and create two synthetic Auth
   users. Keep generated keys/passwords/JWTs in ignored local files only.
4. Run the backend against that local Auth/PostgREST with a fake producer and
   enforce outbound isolation. Do not load the product `.env` or cloud credentials.
5. Verify HTTP and browser behavior below; record the tested SHA, commands,
   assertions and limitations in M3. A prepared workspace is not a passing P4.

## Acceptance matrix

- Real Auth login A/B, invalid/missing JWT rejection.
- A creates/reads source; B cannot read, mutate or confirm A's session.
- Preview GET returns UUID revision; stale revision POST returns 409.
- Missing revision/key returns 422; valid POST confirms exactly once.
- Drop the response after commit; GET recovers and same-key replay has one receipt.
- Direct PostgREST/RPC requests enforce RLS and deny legacy confirmation RPC.
- CORS preflight accepts Idempotency-Key for the intended frontend origin.
- Fake producer controls pending/running/failed/ready; no external AI connection.
- Ready with supported_modes=[] opens Stage 2 after F5.
- Browser preview → confirm → same session Stage 2, keyboard, refresh and recovery.

## Evidence boundaries

SQL transport fixtures and DOM tests remain separate from this run. Do not mark
Auth/PostgREST/RLS or browser acceptance passed until their assertions execute.
Use `supabase status -o json` redirected to an ignored file; never attach that
file or raw Auth responses to GitHub. Publish only sanitized assertions.

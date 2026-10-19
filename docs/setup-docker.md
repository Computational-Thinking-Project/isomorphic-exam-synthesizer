# Team Docker setup (TV6)

Application and tests run in Linux containers. Install Git and Docker Desktop;
no host Python, Node or venv is needed. The helper uses Windows PowerShell 5.1+
or PowerShell 7 (pwsh on macOS/Linux).

## First run

Install Docker Desktop from https://docs.docker.com/desktop/setup/install/.
On Windows choose Linux containers with WSL 2. Reopen the terminal after installing.
The development configuration requires Compose 2.32.0 or later.
Clone the repository, check out dev, and run from its root:

~~~powershell
.\scripts\dev.ps1 setup
.\scripts\dev.ps1 doctor
.\scripts\dev.ps1 up
~~~

Setup creates the root .env only if absent and validates Compose without printing
secrets. Doctor bounds its engine probe at 20 seconds. Up builds both images, waits
for health checks, tests HTTP and the API proxy, then watches source changes.
The first build requires internet and can take minutes.
Ctrl+C stops watching; use down to stop the services.

Default URLs: frontend http://localhost:3000, backend docs http://localhost:8000/docs.
The helper prints the actual addresses if ports change.
On macOS/Linux use pwsh ./scripts/dev.ps1 followed by the same action.

## Daily commands

| Action after .\scripts\dev.ps1 | Behavior |
| --- | --- |
| up | Build/start, health/HTTP checks, watch source changes |
| up -NoWatch | Start in background; use for CI or demonstrations |
| test | Python mock unit tests, SymPy parser, frontend tests/lint/build in containers |
| smoke | Check running backend, browser entry page and frontend API proxy |
| logs | Last 100 log lines for both services |
| down | Stop/remove this project's containers/network; no volume deletion |

Without the helper:

~~~sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --watch
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --build --rm --no-deps backend python -m pytest tests -q
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
~~~

For the static Nginx build, use docker compose up --build --detach --wait.
Stop dev before switching: both configurations use the same project and ports.
The static stack is for build verification/demo, not a complete production deployment:
TLS and production secret management are not configured.

## Configuration

The root .env supplies both configurations. Empty cloud credentials allow the
current mock UI, health checks and mock tests. This does not verify real Google
login, persistence or Gemini generation.

- Backend only: GEMINI_API_KEY, GEMINI_MODEL, SUPABASE_URL, SUPABASE_ANON_KEY,
  SUPABASE_SERVICE_ROLE_KEY.
- Public browser configuration: VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY,
  aligned with TV1's auth PR.
- Never place Gemini/service-role keys in VITE_* variables or commit real env files.
- Browser requests use relative /api/... URLs. Vite proxies to backend:8000 inside
  Docker; API_PROXY_TARGET affects only the Vite server. Host Vite defaults to
  localhost:8000. Nginx proxies the same prefix.
- OAuth callbacks must use the browser-visible host/port. Confirm callbacks and CORS
  with TV1/TV3/TV4 when enabling real authentication.

Run up again after changing .env. Restart alone does not apply new environment values.
The static Vite bundle requires rebuilding after changes to public configuration.
Do not paste docker compose config output: it expands secrets. Use config --quiet.

## Source and dependency changes

Compose Watch syncs source; dependencies remain in images. Windows node_modules
and .venv are excluded. Vite/Uvicorn reload source edits; manifests trigger rebuilds.
Tests use run --build to include the current checkout without requiring a watcher.

- Frontend uses npm ci with the existing package-lock.json.
- backend/requirements.txt declares dependencies; backend/requirements.lock records
  the complete Python 3.11 Linux resolution and hashes.
- Change requirements and regenerate the lock together. From the repository root:

~~~powershell
docker run --rm --mount "type=bind,source=$PWD/backend,target=/work" -w /work python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89 sh -c "python -m pip install pip-tools==7.5.2 && python -m piptools compile -q --generate-hashes --resolver=backtracking --strip-extras --output-file requirements.lock requirements.txt"
~~~

Then rebuild and test. Do not edit generated versions/hashes manually.
Base images are pinned by multi-platform digest; update deliberately with a tested PR.
System packages and Typst still require network access: this is not an offline or
bit-for-bit reproducible OS build. Typst selects amd64/arm64 archives; ARM execution
requires separate verification.

## Troubleshooting

- Engine unavailable: open Desktop, use Linux containers, then run doctor.
- CLI/credential helper missing after installation: reopen the terminal/IDE.
  The helper also checks Docker's standard Windows installation locations.
- Port busy: change FRONTEND_PORT/BACKEND_PORT in .env, update CORS/OAuth callback
  if the frontend port changes, and run up again.
- Two checkouts: choose different COMPOSE_PROJECT_NAME values AND different ports.
  There are no fixed shared container/network names.
- Code does not update: keep the watcher open and check ignored paths.
  NoWatch starts containers but does not sync later edits; run up to rebuild.
- Missing dependency: regenerate its lockfile, then run up.
- Test needs only Docker and mock credentials; smoke needs an already running stack.
- Shell/Compose/PowerShell/lock files use LF through .gitattributes.

## Verification and handoff

Docker environment CI builds/tests the dev stack on a clean Ubuntu runner and
checks the static Nginx build and SPA deep links. It saves scoped logs on failure,
always cleans up containers, uses no real cloud keys and publishes no images.

TV1 reviews frontend startup/public env; TV3 reviews backend startup/env; TV4 reviews
CI and tries onboarding on another machine when available. CI does not replace a
Windows/WSL onboarding test or real Google/Supabase/Gemini tests. Record tested and
unverified cases in the Docker PR.

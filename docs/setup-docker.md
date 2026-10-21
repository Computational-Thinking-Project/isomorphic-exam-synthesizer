# Team Docker setup (TV6)

Application and tests run in Linux containers. Install Git and Docker Desktop;
no host Python, Node or venv is needed. The helper uses Windows PowerShell 5.1+
or PowerShell 7 (pwsh on macOS/Linux).


## Choose the correct branch

Before this Docker PR is merged, use its branch to try the setup:

~~~powershell
git clone --branch chore/dev-docker-setup https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer.git
cd isomorphic-exam-synthesizer
~~~

For an existing checkout, save or commit your work before switching branches:

~~~powershell
git fetch origin
git switch chore/dev-docker-setup
git pull --ff-only
~~~

After the PR is merged, use dev as the base for your own feature branch. Do not
put feature work on the shared Docker branch. If Git reports local changes or
diverged history, resolve them before continuing; do not discard work to run Docker.

## Windows prerequisites and script permissions

1. Install Git and [Docker Desktop](https://docs.docker.com/desktop/setup/install/).
2. Enable the WSL 2 backend and use Linux containers in Docker Desktop.
3. Open Docker Desktop and wait until the engine is running.
4. Reopen PowerShell or your IDE terminal after installation.
5. Run the setup commands below from the repository root.

The helper supports Windows PowerShell 5.1 or PowerShell 7. If Windows reports
that running scripts is disabled, allow scripts only in the current terminal:

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
~~~

Then rerun the helper. This setting ends when you close that terminal. If your
organization enforces a policy, use the approved terminal/policy instead.

On macOS/Linux, install Docker with Compose and PowerShell 7, then replace
each Windows helper invocation with, for example:

~~~sh
pwsh ./scripts/dev.ps1 setup
pwsh ./scripts/dev.ps1 doctor
pwsh ./scripts/dev.ps1 up
~~~

## First run

Install Docker Desktop from https://docs.docker.com/desktop/setup/install/.
On Windows choose Linux containers with WSL 2. Reopen the terminal after installing.
The development configuration requires Compose 2.24.4 or later.
Choose the branch using the instructions above, then run from the repository root:

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

## How this avoids environment conflicts

| Concern | Project convention |
| --- | --- |
| Python, Node and OS libraries | Installed inside images; no host Python, Node, npm or venv required |
| Frontend packages | Installed with npm ci from package-lock.json |
| Backend packages | Installed from the generated Python lockfile with hashes |
| Host dependency folders | Excluded from image build/source sync; do not copy node_modules or .venv into containers |
| Local configuration | Root .env belongs to each checkout and is ignored by Git |
| Service names | Use Compose service names inside Docker; use localhost from your browser |
| Multiple running copies | Give each copy a unique Compose project name and host ports |
| Source updates | Compose Watch syncs source; dependency manifest changes rebuild images |

Use the helper for everyday development. Running npm run dev or uvicorn on the
host at the same time can occupy the same ports and bypass the shared environment.
Docker isolates application dependencies; host ports and external cloud resources
still need coordination.

## Daily development and updating code

Start a work session:

~~~powershell
.\scripts\dev.ps1 up
~~~

Keep that terminal open for Watch. Edit source files on your machine with your
usual editor; Vite and Uvicorn reload supported source changes. Do not edit files
inside a container: those changes can disappear when it is recreated.

To run without Watch:

~~~powershell
.\scripts\dev.ps1 up -NoWatch
~~~

With NoWatch, later source edits are not synchronized. Run up again to rebuild
the checkout. To apply a Git branch switch, stop Watch with Ctrl+C, run down,
switch/update your branch, and run up again. This prevents stale files left by
the previous branch from remaining in a running container.

After changing .env, run up again. Setup never replaces an existing .env;
compare it with .env.example when pulling changes and add new settings manually.

When finished, press Ctrl+C to stop Watch and then run:

~~~powershell
.\scripts\dev.ps1 down
~~~

Ctrl+C alone leaves the application containers running.

## Multiple checkouts and occupied ports

The default frontend/backend ports are 3000/8000. For a second running checkout,
edit its root .env before starting it:

~~~dotenv
COMPOSE_PROJECT_NAME=exam-tam-feature
FRONTEND_PORT=3001
BACKEND_PORT=8001
CORS_ORIGINS=http://localhost:3001,http://127.0.0.1:3001
~~~

Use a lowercase project name with letters, digits and hyphens, starting with a
letter or digit. Each simultaneously running checkout must have a different
project name AND different host ports. Another person's separate computer can
use the same defaults.

If this checkout is already running, run down BEFORE changing the project name
or ports so the helper can find the original containers. Then run up and use
http://localhost:3001 and http://localhost:8001/docs for this example.

Changing host ports does not change the internal service ports. Keep the Vite
proxy destination http://backend:8000. For real OAuth, also register the selected
browser URL/callback in your provider's allowed URLs.

Shell environment variables can override Compose interpolation values in .env.
If a port or project name does not match your file, check whether the current
terminal inherited FRONTEND_PORT, BACKEND_PORT or COMPOSE_PROJECT_NAME. Correct
the relevant terminal variable or open a terminal without that override.

## Optional checks and reporting a problem

Routine startup already checks container health, frontend HTTP and the API proxy.
To repeat those checks on a running development stack:

~~~powershell
.\scripts\dev.ps1 smoke
~~~

To run the automated checks inside containers:

~~~powershell
.\scripts\dev.ps1 test
~~~

Test runs the existing Python mock tests, the SymPy LaTeX parser check, frontend
tests, ESLint and a Vite build. It does not exercise real cloud credentials.

For a failure, collect the relevant error and recent service logs:

~~~powershell
.\scripts\dev.ps1 logs
docker version
docker compose version
git rev-parse --short HEAD
~~~

Include your OS, commit, failing command and relevant error when opening a GitHub
issue. Remove secrets from logs. Do not upload .env or expanded Compose config.

### Common fixes

| Symptom | Next step |
| --- | --- |
| Docker command missing | Reopen the terminal after installing Desktop; run doctor |
| Engine unavailable or Windows container mode | Open Desktop, wait for startup, select Linux containers and rerun doctor |
| Unsupported !override / Compose schema | Update Docker Compose to at least 2.24.4 |
| Address already in use | Stop the conflicting application or configure distinct host ports as described above |
| Source changes do not appear | Keep Watch open; after NoWatch or a branch switch, rerun up |
| New environment value has no effect | Check terminal overrides and rerun up to recreate/rebuild services |
| Login or AI generation fails with blank keys | Configure the corresponding cloud credentials; startup/mock checks do not provide cloud access |
| Image download fails | Check network/proxy access in Docker Desktop and retry up; keep committed image pins |
| Dependency missing after an update | Update the manifest and lockfile together, then rebuild; do not install ad hoc inside a running container |

For a fresh project restart, use down followed by up. Do not use a global Docker
prune, factory reset or delete unrelated containers to fix this project's setup.


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

The up command builds the current source before starting Watch; it does not rely
on newer initial_sync schema support. Compose Watch then syncs edits while running.
Dependencies remain in images. Windows node_modules
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

Review responsibilities: TV1 covers frontend startup and public configuration;
TV3 covers backend startup, environment and dependencies; TV4 covers CI changes.
Use the daily commands above to run the application and the optional checks when
needed. This guide is the shared reference for team setup.

## Official Docker references

- [Compose Watch](https://docs.docker.com/compose/how-tos/file-watch/)
- [Compose project names](https://docs.docker.com/compose/how-tos/project-name/)
- [Compose variable interpolation and precedence](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)

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

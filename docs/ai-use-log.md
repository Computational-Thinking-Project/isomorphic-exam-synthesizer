# AI assistance log

## 2026-10-19 — TV6 Docker setup

- Tool: OpenAI Codex.
- Assistance: compared the Week 1 guide with the repository, prepared Dockerfiles,
  Compose configuration, PowerShell helper, documentation, dependency locking and
  GitHub Actions changes; diagnosed local Docker installation issues.
- Verification: real Docker builds, Linux container tests, Windows PowerShell 5.1,
  HTTP/proxy health checks, source-sync/reload checks, Ruff/Mypy and static SPA checks.
  See logbook and the Docker PR for commands, results and remaining limitations.
- Scope excludes the mathematical validators (TASK-107a / TASK-107b).
- Cloud AI tests used the existing mock clients; no Gemini API calls were required.

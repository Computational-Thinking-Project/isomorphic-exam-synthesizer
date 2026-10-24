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

## 2026-10-24 — AI W2 confirmed-source pipeline

- Tool: OpenAI Codex, under Trương Thành Đạt’s direction.
- Assistance: reused the merged Blueprint extractor as a shared backend/CLI core; implemented async Gemini key pool, confirmation fingerprints, Blueprint-based candidate/answer/solution generation, bounded validation/repair, resume and lifecycle; updated dependency locking, Docker resources and integration documentation.
- Human decisions: source confirmation precedes Blueprint; string options map to A–D; no teacher freeform prompt; unsupported math remains unknown and needs teacher review; Hùng reviews and Đạt owns Docker merge.
- Verification: 304 host tests passed, one live opt-in test skipped; Ruff/Mypy passed. Live Gemini generated two quadratic variants; fixed a provider schema incompatibility found by live testing and rechecked string/key/solution consistency. Docker evidence is collected by PR CI because the host has no usable Docker engine.
- Scope: AI services/contracts; no shared database migrations, W2 HTTP/UI orchestration, or automatic teacher approval.

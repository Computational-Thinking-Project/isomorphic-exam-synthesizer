# Isomorphic Exam Synthesizer 📐

> **Hệ thống sinh đề thi trắc nghiệm Toán học THPT đẳng cấu (Isomorphic Math Exam Synthesis)**  
> Ứng dụng mô hình AI (Gemini Structured Outputs), bộ thẩm định toán học 4 tầng (Syntax, Logic, SymPy CAS, Rule Fallback), xáo trộn ngẫu nhiên xác định (Deterministic Shuffling) và xuất bản đa định dạng (Typst PDF, LaTeX, Markdown ZIP).

---

## Quick start (Docker)

Install Git and Docker Desktop (Linux containers / WSL 2 on Windows), then reopen
your terminal. No host Python or Node installation is needed.

From the repository root, on Windows:

~~~powershell
.\scripts\dev.ps1 setup
.\scripts\dev.ps1 doctor
.\scripts\dev.ps1 up
~~~

Frontend: http://localhost:3000. API docs: http://localhost:8000/docs.
The up command waits for health checks and starts watching source changes.
Ctrl+C stops watching; use the down command to stop the containers.

~~~powershell
.\scripts\dev.ps1 test
.\scripts\dev.ps1 logs
.\scripts\dev.ps1 down
~~~

Setup preserves an existing .env. Empty cloud keys support local health checks
and mock tests. Google login and the profile API require the existing Supabase
configuration; see the [frontend Auth setup and verification](frontend/README.md).
Dashboard session data/actions still use mocks. Real Gemini requires backend
credentials and integration work. Never commit real secrets.

For macOS/Linux use PowerShell 7: pwsh ./scripts/dev.ps1 setup (and the same actions).
For static Nginx build verification, stop dev and use docker compose up --build --detach --wait.

See [team setup, credentials, dependency updates and troubleshooting](docs/setup-docker.md).

---

## 📁 Cấu trúc Thư mục Dự án

```text
isomorphic-exam-synthesizer/
├── frontend/                  # React + Vite + JavaScript / JSX (Single Page Application)
│   ├── src/
│   │   ├── components/        # KaTeX MathRenderer, WarningBadges, UI dùng chung
│   │   ├── features/          # Auth, Dashboard, Stage 1 (Ingest), Stage 2, Stage 3
│   │   ├── hooks/             # Custom hooks (useAuth, useSSE, ...)
│   │   ├── services/          # API client (api.js), Supabase client, mocks
│   │   └── models/            # JavaScript data contracts / helpers / JSON fixtures
│   ├── Dockerfile             # Multi-stage build + Nginx static serving
│   ├── nginx.conf             # Reverse proxy /api/* -> backend container
│   ├── package.json           # Frontend dependencies & scripts
│   └── vite.config.js         # Cấu hình Vite & alias path
├── backend/                   # Python 3.11 / FastAPI async engine
│   ├── app/
│   │   ├── api/               # API endpoints & dependencies (Auth, JWT, Ownership)
│   │   ├── core/              # Config, rate limit, CORS, error handlers
│   │   ├── models/            # Pydantic schemas khớp contracts & DB models
│   │   └── services/          # Parsers, AI Gemini, 4-tier Validator, Exporter
│   ├── scripts/               # Scripts kiểm thử độc lập (smoke tests API, AI, CAS)
│   ├── Dockerfile             # Python 3.11-slim + Typst binary
│   └── requirements.txt       # Backend dependencies
├── agents/                    # Thư mục cấu hình workspace theo thành viên nhóm
├── docs/                      # Tài liệu kiến trúc, đặc tả, kế hoạch & change log
├── .github/workflows/ci.yml   # CI Pipeline: Linting, Backend TypeCheck, SymPy smoke test
└── docker-compose.yml         # Container orchestration (Frontend + Backend)
```

---

## 🛠 Tech Stack
- **Frontend:** React 18, Vite, JavaScript (JSX), TailwindCSS, KaTeX, Zustand.
- **Backend:** FastAPI, Python 3.11, Pydantic v2, SymPy (CAS), Typst (PDF).
- **AI Service:** Google Gemini API (Structured Outputs).
- **Database & Auth:** Supabase (PostgreSQL với Row-Level Security, Google OAuth).
- **CI/CD & DevOps:** Docker, Docker Compose, GitHub Actions.

---

## 👥 Đóng góp Dự án
Xem chi tiết tại [CONTRIBUTING.md](CONTRIBUTING.md).

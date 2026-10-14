# Isomorphic Exam Synthesizer 📐

> **Hệ thống sinh đề thi trắc nghiệm Toán học THPT đẳng cấu (Isomorphic Math Exam Synthesis)**  
> Ứng dụng mô hình AI (Gemini Structured Outputs), bộ thẩm định toán học 4 tầng (Syntax, Logic, SymPy CAS, Rule Fallback), xáo trộn ngẫu nhiên xác định (Deterministic Shuffling) và xuất bản đa định dạng (Typst PDF, LaTeX, Markdown ZIP).

---

## 🚀 Hướng dẫn Chạy Nhanh (Quick Start)

### 1. Yêu cầu Tiên quyết (Prerequisites)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Hỗ trợ WSL 2 trên Windows / macOS / Linux).
- Git.

### 2. Thiết lập Biến Môi trường
Tạo file `.env` từ file mẫu `.env.example`:
```bash
cp .env.example .env
```
Điền các giá trị cần thiết vào `.env`:
- `GEMINI_API_KEY`: API key lấy từ [Google AI Studio](https://aistudio.google.com/).
- `SUPABASE_URL` & `SUPABASE_ANON_KEY`: Lấy từ dự án Supabase.

### 3. Khởi chạy với Docker Compose
Chạy toàn bộ hệ thống (Frontend + Backend) chỉ bằng 1 câu lệnh duy nhất:
```bash
docker compose up --build
```

Sau khi khởi chạy thành công:
- **Frontend SPA:** [http://localhost:3000](http://localhost:3000)
- **Backend API Docs (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

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

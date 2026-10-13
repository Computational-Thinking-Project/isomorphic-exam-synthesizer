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
├── frontend/                  # React + Vite + TypeScript (Single Page Application)
│   ├── src/
│   │   ├── components/        # KaTeX MathRenderer, ProgressTracker, WarningBadges
│   │   ├── features/          # Auth, Dashboard, Stage 1 (Ingest), Stage 2 (Config), Stage 3 (Review), Approval, Export
│   │   └── types/             # TypeScript data contracts
│   └── nginx.conf             # Reverse proxy /api/* -> backend container
├── backend/                   # Python 3.11 / FastAPI async engine
│   ├── app/
│   │   ├── api/               # API endpoints
│   │   ├── core/              # Config, security, database pool
│   │   ├── models/            # Pydantic schemas khớp contracts
│   │   └── services/          # Parsers, AI Pipelines, 4-tier Validator, Exporter (Typst)
│   └── Dockerfile             # Python 3.11-slim + Typst binary
├── docs/                      # Tài liệu kiến trúc, đặc tả & hợp đồng API
├── .github/workflows/ci.yml   # CI Pipeline: Linting, Typecheck, SymPy smoke test
└── docker-compose.yml         # Container orchestration
```

---

## 🛠 Tech Stack
- **Frontend:** React 18, Vite, TypeScript, TailwindCSS, KaTeX, Zustand.
- **Backend:** FastAPI, Python 3.11, Pydantic v2, SymPy (CAS), Typst (PDF).
- **AI Service:** Google Gemini API (Structured Outputs).
- **Database & Auth:** Supabase (PostgreSQL với Row-Level Security, Google OAuth).
- **CI/CD & DevOps:** Docker, Docker Compose, GitHub Actions.

---

## 👥 Đóng góp Dự án
Xem chi tiết tại [CONTRIBUTING.md](CONTRIBUTING.md).

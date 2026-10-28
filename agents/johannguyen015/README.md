# AI Agent Workspace — BE1 (`johannguyen015` / Nguyễn Bá Duy)

Thư mục này chứa toàn bộ tài nguyên cấu hình cá nhân dành cho AI Assistant (Antigravity) phục vụ vai trò **BE1 (Backend Lead & Core)** trong dự án **Isomorphic Exam Synthesizer**.

---

## 1. Cấu trúc Thư mục

```text
agents/johannguyen015/
├── AGENTS.md                  # Quy tắc cốt lõi (In-Memory Pre-validation, Atomic Transaction, SEC-04)
├── README.md                  # Tài liệu hướng dẫn sử dụng thư mục này
└── skills/                    # Bộ Custom Skills cá nhân của BE1
    ├── parser-evaluator/      # Skill bóc tách DOCX/LaTeX/MD, OMML & bảng đáp án rời (TASK-202)
    │   └── SKILL.md
    ├── session-endpoints/     # Skill triển khai API Ingestion, Confirm & Preconditions (TASK-202, 205)
    │   └── SKILL.md
    └── backend-code-quality/  # Skill chạy ruff, mypy, pytest 1 chạm
        └── SKILL.md
```

---

## 2. Cách Kích hoạt cho Antigravity trên Máy Cá nhân

Để Antigravity tự động nhận diện các Skill và Rule trong thư mục này khi bạn đang làm việc trong `backend/`:

### Cách 1: Đăng ký Skill vào cấu hình Global của Antigravity
Tạo hoặc cập nhật file: `C:\Users\ASUS Vivobook\.gemini\config\skills.json`:
```json
{
  "entries": [
    { "path": "agents/johannguyen015/skills" }
  ]
}
```

### Cách 2: Gọi trực tiếp trong phiên chat
Khi bắt đầu một tác vụ mới, bạn có thể tham chiếu trực tiếp:
- `@agents/johannguyen015/AGENTS.md`: Nhắc AI tuân thủ nguyên tắc kiến trúc backend.
- Yêu cầu AI kích hoạt skill tương ứng: *"Hãy kiểm tra parser theo skill parser-evaluator"*.

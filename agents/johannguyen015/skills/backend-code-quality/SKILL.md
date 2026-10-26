---
name: backend-code-quality
description: >-
  Use this skill before committing or pushing backend code. It provides instructions and command sequences
  for running Ruff linter and formatter, Mypy type checker, Pytest test runner under Windows PowerShell,
  and enforces realistic exception mocking standards.
---

# Backend Code Quality Checklist & Runner

Before committing any code on branch `feat/be1-task-202-ingestion-parsers` or submitting a PR, execute this quality suite to maintain repository standards.

---

## 1. Quick One-Line Verification (PowerShell)

Run from `backend/` directory:

```powershell
# Chạy toàn bộ bộ kiểm tra chất lượng
ruff check app/ tests/ ; mypy app/ ; pytest
```

---

## 2. Step-by-Step Commands & Fixes

### A. Scoped Ruff Linter & Formatter (Chỉ chạy trên file thuộc task)
The project enforces Python 3.11 with line length 100.
**CẢNH BÁO:** TUYỆT ĐỐI KHÔNG chạy `ruff format app/ tests/` trên toàn bộ dự án vì sẽ làm thay đổi format file của các thành viên khác gây conflict trên nhánh `dev`.

Chỉ chạy trên các file/thư mục thuộc task của BE1:

```powershell
# Ví dụ cho TASK-202:
# 1. Kiểm tra lint scoped
ruff check app/services/parser/ app/models/schemas.py app/api/routes/sessions.py tests/test_parsers.py tests/api/test_ingest.py

# 2. Format scoped (chỉ format đúng file thuộc task)
ruff format app/services/parser/ app/models/schemas.py tests/test_parsers.py tests/api/test_ingest.py
```

### B. Mypy Static Type Checking
All FastAPI routes, dependency functions, and parsing logic must be fully typed:

```powershell
mypy app/
```

*Common Mypy issues:*
- Use `list[str]` instead of `List[str]` for Python 3.11+ built-in generics, or stick to models defined in `app/models/schemas.py`.
- Use `typing.Any` (in hoa chữ A), không dùng `builtins.any` làm type hint.
- Handle `Optional` return types explicitly with `None` checks.

### C. Pytest Test Suite
Run scoped tests first, then regression tests:

```powershell
# Chạy test của task
pytest tests/test_parsers.py tests/api/test_ingest.py -v

# Chạy kiểm tra không làm hỏng tính năng sessions cũ
pytest tests/api/test_sessions.py -v
```

### D. Kỷ Luật Mock Ngoại Lệ Thực Tế (Realistic Mocking & Fault Injection)
> [!CAUTION]
> **Quy tắc vàng chống False Mocking:** Không bao giờ mock ngoại lệ mạng hoặc CSDL bằng `RuntimeError("tên_lỗi")`. Lỗi giả mồi chuỗi sẽ đánh lừa unit test nhưng làm sập hệ thống trên môi trường thật.

Khi viết test mô phỏng sự cố:
* **Mô phỏng Timeout Mạng:** Dùng `side_effect = httpx.ReadTimeout("")` (bắt buộc kiểm tra cả thông báo rỗng).
* **Mô phỏng Mất Kết Nối / Ngắt Socket:** Dùng `side_effect = httpx.ReadError("")` hoặc `side_effect = httpx.RemoteProtocolError("Server disconnected without sending a response.")`.
* **Mô phỏng Lỗi CSDL Có Xác Nhận Rollback:** Dùng `side_effect = APIError({"code": "P0001", "message": "Constraint violation"})`.
* **Mô phỏng Lỗi Nội Bộ Bất Định:** Dùng `side_effect = RuntimeError("Memory failure")` và xác nhận API **không khẳng định** giao dịch đã rollback.

---

## 3. Pre-Commit Sanity Checklist & Scope Protection

- [ ] **Rà soát `git status`:** Không có file nào của thành viên khác bị sửa đổi hoặc reformat ngoài ý muốn.
- [ ] Nếu có file ngoài scope bị modified, chạy `git restore <file>` ngay lập tức.
- [ ] Không có file `.tmp`, file log, `.pytest_cache`, hoặc file đề bài sprint (như `w2_21_10.md`) bị thêm vào git stage.
- [ ] Mọi endpoint mới đều có unit test trong `backend/tests/`.
- [ ] **Không bắt ngoại lệ bằng dò chuỗi:** Mọi handler lỗi mạng và CSDL đều kiểm tra bằng `isinstance`.
- [ ] **Không mock giả mồi chuỗi:** Mọi test lỗi mạng/DB đều dùng instance thật của `httpx`, `httpcore`, `postgrest.exceptions.APIError`.
- [ ] Không có `print()` statements thừa; sử dụng `logging` chuẩn của FastAPI / Uvicorn.
- [ ] Tuân thủ Conventional Commits (ví dụ: `feat(api): implement docx ingestion parser [TASK-202]`).

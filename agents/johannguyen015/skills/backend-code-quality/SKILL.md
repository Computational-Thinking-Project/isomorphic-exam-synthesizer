---
name: backend-code-quality
description: >-
  Use this skill before committing or pushing backend code. It provides instructions and command sequences
  for running Ruff linter and formatter, Mypy type checker, and Pytest test runner under Windows PowerShell.
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

### A. Ruff Linter & Auto-fix
The project enforces Python 3.11 with line length 100:

```powershell
# Kiểm tra lỗi lint
ruff check app/ tests/

# Tự động sửa các lỗi safe-fixes (import sort, unused imports, format)
ruff check app/ tests/ --fix
ruff format app/ tests/
```

### B. Mypy Static Type Checking
All FastAPI routes, dependency functions, and parsing logic must be fully typed:

```powershell
mypy app/
```

*Common Mypy issues:*
- Use `list[str]` instead of `List[str]` for Python 3.11+ built-in generics, or stick to models defined in `app/models/schemas.py`.
- Handle `Optional` return types explicitly with `None` checks.

### C. Pytest Test Suite
Run tests with coverage and verbose output:

```powershell
# Chạy tất cả test
pytest

# Chạy có in log output chi tiết
pytest -s -v

# Dừng ngay tại ca test đầu tiên bị fail
pytest -x
```

---

## 3. Pre-Commit Sanity Checklist

- [ ] Không có file `.tmp`, file log hoặc `.pytest_cache` bị thêm vào git stage.
- [ ] Mọi endpoint mới đều có unit test trong `backend/tests/`.
- [ ] Không có `print()` statements thừa; sử dụng `logging` chuẩn của FastAPI / Uvicorn.
- [ ] Tuân thủ Conventional Commits (ví dụ: `feat(api): implement docx ingestion parser [TASK-202]`).

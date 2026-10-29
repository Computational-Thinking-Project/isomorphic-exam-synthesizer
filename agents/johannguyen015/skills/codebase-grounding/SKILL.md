---
name: codebase-grounding
description: >-
  Use this skill BEFORE creating any implementation plan or writing any backend code for a new task.
  It provides a mandatory verification checklist to ground every technical decision in the actual
  codebase state — preventing assumption-driven errors (wrong column names, async/sync confusion,
  wrong SDK patterns, incorrect foreign-key relationships).
---

# Codebase Grounding — Mandatory Fact-Checking Before Planning or Coding

> **Quy tắc bất biến:** Mọi kế hoạch sai lệch đều xuất phát từ việc suy diễn thay vì đọc mã nguồn thực tế.
> Skill này bắt buộc thực hiện **trước** khi viết bất kỳ dòng logic kế hoạch hoặc dòng code nào.

---

## 0. Khi nào phải dùng Skill này?

Kích hoạt **bắt buộc** trước khi:
- Bắt đầu lập kế hoạch (implementation plan) cho bất kỳ task mới nào.
- Viết bất kỳ endpoint, service, hoặc database query mới nào.
- Mở rộng hoặc tích hợp với một module/service chưa làm việc trực tiếp gần đây.

---

## 1. Checklist 3 Điểm Chốt (Bắt Buộc Đối Chiếu)

### 1.A. Database Schema — `schema.sql`

**File cần đọc:** `backend/scripts/schema.sql`

Trước khi viết bất kỳ câu query hay conditional logic liên quan đến bảng X:

```
□ Mở schema.sql, tìm và đọc định nghĩa CREATE TABLE X
□ Liệt kê chính xác tên cột và kiểu dữ liệu (BOOLEAN, TEXT, UUID, TIMESTAMPTZ...)
□ Xác định các cột NULLABLE và cột có DEFAULT value
□ Liệt kê tất cả FOREIGN KEY — bảng nào trỏ sang bảng nào
□ Kiểm tra có RPC/Function PostgreSQL nào liên quan không (search bằng CREATE OR REPLACE FUNCTION)
```

**Các cột dễ bị ngộ nhận nhất (đã xác nhận):**

| Bảng | Tồn tại trong DB | KHÔNG tồn tại trong DB (chỉ là DTO in-memory) |
|---|---|---|
| `source_questions` | `has_missing_answer`, `has_security_warning` | `has_unparsed_omml` ← cờ in-memory, bị chặn trước khi ghi DB |
| `question_blueprints` | `source_question_id`, `confirmed_at` | `session_id` ← không tồn tại, phải join qua `source_questions` |
| `exam_sessions` | `status`, `user_id`, `updated_at` | (đầy đủ, không suy diễn thêm) |

---

### 1.B. Chữ ký Hàm Phụ Trợ — Sync hay Async?

**File cần đọc:** `backend/app/api/dependencies.py`

```
□ Tìm hàm assert_ownership → def (SYNC) hay async def (ASYNC)?
□ Tìm get_current_user → def hay async def?
□ Kiểm tra các dependency function khác sẽ dùng trong endpoint mới
```

**Đã xác nhận:**

```python
# dependencies.py — CÁC HÀM SYNC (KHÔNG dùng await):
def assert_ownership(table, resource_id, user_id, db=None) -> None: ...

# CÁCH GỌI ĐÚNG trong endpoint async:
assert_ownership("exam_sessions", session_id, current_user.id, db=db)  # ✅
await assert_ownership(...)  # ❌ TypeError: object NoneType can't be used in 'await' expression
```

---

### 1.C. Pattern Gọi SDK Thực Tế — Đối chiếu với Endpoint đang chạy

**File cần đọc:** `backend/app/api/routes/sessions.py` (xem các endpoint ingest-file / ingest-text đã được implement và đã pass test)

Mỗi khi dùng Supabase PostgREST SDK, đối chiếu pattern sau:

#### ✅ Cách đúng — Timestamp (không dùng "now()" string)
```python
from datetime import datetime, timezone

# ĐÚNG: Python sinh timestamp, truyền string ISO-8601
db.table("exam_sessions").update({
    "status": "blueprinted",
    "updated_at": datetime.now(timezone.utc).isoformat()
}).eq("id", session_id).execute()

# SAI: "now()" là text literal, không phải SQL function call
db.table("exam_sessions").update({"updated_at": "now()"}).eq("id", session_id).execute()  # ❌
```

#### ✅ Cách đúng — `.in_()` với danh sách có thể rỗng
```python
# PHẢI kiểm tra rỗng trước khi gọi .in_()
if not id_list:
    return 0  # hoặc xử lý early return phù hợp
result = db.table("question_blueprints").select("source_question_id") \
    .in_("source_question_id", id_list).execute()
```

#### ✅ Cách đúng — `.insert()` với cast(Any, ...)
```python
from typing import Any, cast

# PHẢI wrap bằng cast(Any, ...) để pass Mypy type check
db.table("question_blueprints").insert(cast(Any, list_of_dicts)).execute()
```

#### ✅ Cách đúng — Rate Limit Decorator
```python
# PHẢI có request: Request và response: Response trong signature
# nếu endpoint dùng @crud_rate_limit
@router.post("/{session_id}/confirm-source", ...)
@crud_rate_limit
async def confirm_source(
    session_id: str,
    payload: ConfirmSourceRequest,
    request: Request,       # ← BẮT BUỘC cho SlowAPI
    response: Response,     # ← BẮT BUỘC cho SlowAPI
    current_user: UserOut = Depends(get_current_user),
    db: Client = Depends(get_db),
):
```

---

## 2. Verification Checklist (Copy & Fill trước khi viết plan)

Điền vào bảng này trước khi bắt đầu viết kế hoạch chi tiết:

```markdown
### Grounding Verification — [TASK-XXX]

**DB Tables dùng trong task này:**
- [ ] Bảng `___`: Các cột cần dùng: ___, ___, ___. ĐÃ ĐỌC schema.sql ✅
- [ ] Bảng `___`: Foreign Key đến bảng `___` qua cột `___`. ĐÃ ĐỌC schema.sql ✅

**Hàm/Dependency sẽ gọi:**
- [ ] `assert_ownership` → SYNC (def) → Gọi trực tiếp, KHÔNG await
- [ ] `get_current_user` → ASYNC (async def) → Dùng như FastAPI Depends, không await thủ công

**Endpoint tương tự đã đọc để tham khảo pattern:**
- [ ] `ingest_file` (dòng ___-___) → Đã đọc cách dùng rate limit, assert_ownership, DB update

**Cột/Field đáng ngờ đã kiểm tra:**
- [ ] Cột `___` có trong DB? → Có / Không (chỉ là DTO in-memory)
- [ ] Bảng `___` có cột `session_id`? → Có / Không (phải join gián tiếp qua `___`)
```

---

## 3. Quy trình Đọc Mã Nguồn Hiệu Quả

### Bước 1 — Tìm nhanh bằng grep/search
```powershell
# Kiểm tra cột trong schema
Select-String -Path "backend/scripts/schema.sql" -Pattern "has_unparsed_omml"

# Kiểm tra hàm là sync hay async
Select-String -Path "backend/app/api/dependencies.py" -Pattern "def assert_ownership"

# Tìm pattern gọi Supabase trong toàn bộ services
Select-String -Path "backend/app/services/" -Pattern "\.update\(" -Recurse
```

### Bước 2 — Đọc định nghĩa cụ thể
- Luôn đọc ít nhất **5 dòng trước** và **5 dòng sau** chữ ký hàm để hiểu context đầy đủ.
- Kiểm tra cả `return type` của hàm — hàm trả `None` không thể `await`.

### Bước 3 — Tìm "usage example" đang chạy trong dự án
- Tìm ít nhất 1 chỗ hàm/pattern đó được gọi thành công trong codebase hiện tại.
- Copy pattern đó làm baseline, chỉ thay đổi phần cần thiết.

---

## 4. Những Suy Diễn Phổ Biến Cần Tránh (Anti-Patterns)

| Suy diễn thường gặp | Thực tế | Cách kiểm tra |
|---|---|---|
| "Pydantic model có field X → DB cũng có cột X" | ❌ Sai. DTO và DB schema độc lập. | Đọc `schema.sql` trực tiếp. |
| "Endpoint là async nên mọi hàm phụ đều async" | ❌ Sai. `assert_ownership` là sync. | Tìm `def ` vs `async def ` trong file định nghĩa. |
| "`update({'col': 'now()'})` = SQL `SET col = now()`" | ❌ Sai. SDK gửi string literal. | Dùng `datetime.now(timezone.utc).isoformat()`. |
| "Bảng con chắc có `session_id` như bảng cha" | ❌ Sai. `question_blueprints` không có `session_id`. | Kiểm tra FOREIGN KEY trong `schema.sql`. |
| "`.in_(col, list)` hoạt động với `list = []`" | ❌ Sai. Sinh SQL lỗi. | Guard `if not list: return early`. |

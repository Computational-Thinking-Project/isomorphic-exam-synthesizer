---
name: backend-code-quality
description: >-
  Use for BE1 backend tasks (feat/be1-*) from planning through implementation, testing, and before
  committing or pushing. Requires a root-cause-first task plan, scoped Ruff formatting, Mypy, full
  Pytest suite, realistic fault injection, and strict pre-push CI pipeline verification.
---

# BE1 Backend Task Playbook for AI Agents

Dùng checklist này cùng `AGENTS.md`. `AGENTS.md` là quy tắc kiến trúc bắt buộc; file này là quy trình thực hiện task. Các đường dẫn trong lệnh bên dưới là ví dụ; phải thay bằng file/test thực tế của task, không copy mù quáng.

## 1. Cổng bắt buộc trước khi code: khảo sát và lập kế hoạch

### 1.1. Kiểm tra hiện trạng

- [ ] Đọc yêu cầu, tiêu chí nghiệm thu và `AGENTS.md`.
- [ ] Từ thư mục repo, chạy `git status --short` và `git diff --stat`; ghi nhận thay đổi đã có trước khi làm.
- [ ] Tìm route/entry point; truy vết `route → dependency/auth → service → parser/AI/DB adapter → response`.
- [ ] Đọc schema/model, migration hoặc SQL function, exception handler và test liên quan.
- [ ] Xác minh các giới hạn và quy ước thực tế trong `backend/pyproject.toml`, không tự đoán config.
- [ ] Phân loại điều đã xác minh, giả thuyết và điểm chưa biết.

### 1.2. Xuất kế hoạch cụ thể trước khi chỉnh sửa

Kế hoạch phải được trình bày cho người dùng trước khi sửa code, tối thiểu theo mẫu:

```markdown
## Kế hoạch task: <mã/tên task>

### 1. Mục tiêu và ngoài phạm vi
- Mục tiêu:
- Không thay đổi:

### 2. Luồng hiện tại và bằng chứng
- Entry point:
- Luồng dữ liệu/side effect:
- File, schema, function và test liên quan:
- Đã xác minh / giả thuyết / chưa biết:

### 3. Nhiệm vụ theo thứ tự
| # | File/module dự kiến | Việc cần làm | Phụ thuộc | Rủi ro/lỗi thường gặp | Cách xử lý tại nguyên nhân gốc | Test chứng minh |
|---|---|---|---|---|---|---|

### 4. Ma trận kiểm thử
- Happy path:
- Boundary/validation:
- Auth/ownership/state:
- DB/network/AI failure và side effect:
- Regression:

### 5. API/DB/Storage impact
- HTTP status/response schema:
- Mutation hoặc migration:
- Tương thích frontend:

### 6. Tiêu chí nghiệm thu
- [ ] ...

### 7. Giả định và rủi ro còn mở
- ...
```

Không chấp nhận nhiệm vụ mơ hồ như “sửa parser” mà không chỉ rõ định dạng/input, failure mode và test. Khi yêu cầu đủ rõ, hãy nêu kế hoạch rồi tiếp tục triển khai trong cùng lượt, không dừng chỉ để chờ xác nhận.

## 2. Quy trình sửa bug: root cause first

Khi gặp bug, test fail, lỗi môi trường hoặc lỗi tích hợp:

1. **Tái hiện:** lưu input tối thiểu, lệnh chạy, stack trace/status và hành vi thực tế.
2. **Xác định invariant:** hành vi hoặc trạng thái nào đáng lẽ phải đúng nhưng đã bị phá vỡ?
3. **Truy vết:** tìm tầng đầu tiên tạo ra dữ liệu sai, side effect sai hoặc phân loại lỗi sai; đừng chỉ vá nơi lỗi lộ ra.
4. **Kiểm chứng giả thuyết:** đối chiếu code, call chain, test, DB response và cấu hình thật.
5. **Sửa nguyên nhân:** thay đổi nhỏ nhất ở đúng tầng chịu trách nhiệm.
6. **Test hồi quy:** thêm test thất bại trước khi sửa và pass sau khi sửa; test cả hành vi không được phép xảy ra.
7. **Kiểm tra lan truyền:** chạy test liên quan và xem diff để phát hiện regression.

### Không được dùng các cách vá triệu chứng sau

| Cách làm sai | Vì sao sai | Phương án đúng |
|---|---|---|
| Bắt mọi exception rồi trả response mặc định | Che mất loại lỗi, có thể báo sai trạng thái mutation | Phân loại lỗi bằng kiểu/bằng chứng, giữ nguyên cause và trả đúng contract |
| Dò `str(exc)` để nhận diện timeout | Message có thể rỗng hoặc thay đổi theo version | Dùng `isinstance` với exception của thư viện thực tế và duyệt `__cause__`/`__context__` |
| Retry ghi DB ngay khi timeout | Request đầu có thể đã commit; retry có thể tạo dữ liệu trùng/xung đột | Báo trạng thái chưa xác định, yêu cầu kiểm tra session; chỉ retry tự động khi có idempotency được thiết kế/test |
| Tăng timeout để che test chậm | Chưa chứng minh bottleneck là timeout cấu hình | Đo/trace query, I/O và thuật toán; tìm thao tác chậm thực sự trước khi đổi timeout |
| Bỏ test hoặc hạ assertion để CI xanh | Xóa bằng chứng về bug thay vì giải quyết nó | Sửa implementation hoặc cập nhật contract chỉ khi yêu cầu chính thức thay đổi |
| `except: pass`, trả `[]`/`None` khi lỗi | Biến lỗi thực thành thành công giả | Trả lỗi có ngữ nghĩa, log phù hợp và test failure path |
| Format/sửa lint toàn repo | Tạo diff lớn và conflict với đồng đội | Giới hạn formatter/linter sửa code vào file task |

Nếu chưa đủ bằng chứng để xác định nguyên nhân gốc, hãy nói rõ điều gì đã được kiểm chứng và làm bước chẩn đoán an toàn tiếp theo. Không khẳng định đã sửa dứt điểm khi mới có workaround.

## 3. Hướng dẫn theo loại nhiệm vụ

### A. Parser và ingestion `.docx`, `.tex`, `.md`

**Nhiệm vụ cần liệt kê trong plan**
- [ ] Xác định parser/entry point và schema output hiện dùng.
- [ ] Kiểm tra kích thước tối đa 10 MB, magic bytes (`PK\x03\x04`), kiểu archive, zip bomb và giới hạn tài nguyên giải nén (<= 50 MB).
- [ ] Parse toàn bộ input trong memory; phân tách parse khỏi ghi DB/Storage.
- [ ] Kiểm tra trích xuất câu hỏi, bảng đáp án và OMML; xác định hành vi với nội dung không hỗ trợ.
- [ ] Chuẩn hóa text Unicode NFC tại ranh giới nhập thích hợp.
- [ ] Kiểm tra quy tắc nghiệp vụ: đáp án bắt buộc, số câu trong `[1, 20]`, security warning nếu có.
- [ ] Chỉ cho phép bước persist sau khi toàn bộ pre-validation thành công.

| Dấu hiệu | Nguyên nhân bản chất có thể có | Cách giải quyết |
|---|---|---|
| File có đuôi `.docx` nhưng parser lỗi khó hiểu | Chỉ tin extension; bytes không phải DOCX hợp lệ hoặc ZIP bị hỏng | Kiểm tra magic bytes/container và trả `400` trước parsing sâu |
| Một phần câu hỏi bị mất | Cấu trúc XML/OMML chưa hỗ trợ; parser bỏ qua node | Tái hiện với fixture nhỏ; parse đúng hoặc báo validation rõ ràng, không âm thầm bỏ nội dung bắt buộc |
| Lỗi tiếng Việt không nhất quán | Các dạng Unicode tổ hợp/dựng sẵn không được chuẩn hóa | Thêm NFC tại tầng chuẩn hóa text và test với hai biểu diễn tương đương |
| Validation báo lỗi nhưng DB vẫn đổi | Ghi dữ liệu xảy ra trước khi hoàn thành validation | Tách pure parsing/validation khỏi persistence; assert mutation calls == 0 |

### B. Atomic replacement và ghi DB

**Nhiệm vụ cần liệt kê trong plan**
- [ ] Đặt phần thay thế dữ liệu phụ thuộc trong một PostgreSQL Stored Procedure/Function call theo Method 2A.
- [ ] Xác minh transaction boundary và điều kiện nào chứng minh rollback.
- [ ] Kiểm tra chức năng SQL dưới quyền DB thực tế (`SET SESSION AUTHORIZATION authenticator; SET ROLE ...`); nếu dùng `SECURITY DEFINER`, cố định `search_path`, giới hạn `EXECUTE`, xác minh ownership ở phía DB và tránh SQL động không an toàn.
- [ ] Xử lý Storage bên ngoài như một hệ thống riêng; không giả định transaction DB bao trùm được Storage.

| Dấu hiệu | Nguyên nhân bản chất có thể có | Cách giải quyết |
|---|---|---|
| Client timeout nhưng DB đã đổi | Mất response sau commit; timeout không cho biết kết quả transaction | Trả `504` uncertain commit, hướng dẫn kiểm tra session trước khi retry; không nói rollback |
| Function chạy với quyền quá rộng | Dùng `SECURITY DEFINER` mà không khóa search path/quyền gọi | Cố định search_path, revoke từ public/anon, grant authenticated/service_role |
| Test DB lọt lỗi do connection superuser | Connection test chạy dưới quyền postgres bỏ qua kiểm tra auth | Dùng kết nối authenticator rồi chuyển role anon/authenticated để kiểm thử |

### C. API route, auth, ownership và toàn bộ State Machine

**Nhiệm vụ cần liệt kê trong plan**
- [ ] Dùng auth dependency hiện có và principal đã xác thực (`current_user.id`).
- [ ] Kiểm tra session tồn tại và ownership qua `assert_ownership("exam_sessions", session_id, current_user.id)`.
- [ ] Kiểm tra vòng đời 10 trạng thái (`draft → blueprinted → configured → generating → partial_generated → generated → reviewed → approved → exported`). Thao tác sai trạng thái trả `HTTP 409 Conflict`.
- [ ] Nếu `has_security_warning == true`, yêu cầu `acknowledged_security_warnings: true`.
- [ ] Bảo vệ race condition: dùng `FOR UPDATE` trong transaction/RPC khi kiểm tra và ghi trạng thái.

### D. Exception handler và lỗi mạng/DB

**Nhiệm vụ cần liệt kê trong plan**
- [ ] Dùng `isinstance` với exception của `httpx`/`httpcore` và lỗi DB chính thức.
- [ ] Duyệt `__cause__`/`__context__` khi exception được bọc; chống vòng lặp.
- [ ] Phân biệt timeout/disconnect (kết quả mutation chưa xác định $\rightarrow$ HTTP 504), lỗi DB có bằng chứng (`APIError` $\rightarrow$ HTTP 500 kèm khẳng định rollback) và lỗi nội bộ không xác định (HTTP 500 trung lập).

| Failure mode | Test double phải dùng | Assertion quan trọng |
|---|---|---|
| Timeout có message rỗng | `httpx.ReadTimeout("")`, `httpx.ConnectTimeout("")` | Handler nhận diện đúng loại lỗi; trả `504` |
| Read/disconnect | `httpx.ReadError("")`, `httpx.RemoteProtocolError(...)`, kiểu `httpcore` | `504` theo contract; nêu uncertain commit; yêu cầu kiểm tra session |
| Database trả lỗi chính thức | `postgrest.exceptions.APIError({"code": "P0001", "message": "Constraint violation"})` | Trả `500`; khẳng định rollback khi transaction bảo đảm |
| Internal fault không có bằng chứng DB | `RuntimeError("Memory failure")` | `500` trung lập; không khẳng định rollback |

### E. Tích hợp AI Gemini, Structured Output & Schema Repair (TASK-203, TASK-204)

**Nhiệm vụ cần liệt kê trong plan**
- [ ] Sử dụng wrapper chuẩn `app/services/ai/` với thư viện `google-genai`.
- [ ] Cấu hình Structured Outputs bằng JSON Schema / Pydantic model cho mọi prompt trích xuất Blueprint hoặc sinh Variant.
- [ ] Quản lý Quota & Rate Limit: Bọc lời gọi API trong cơ chế exponential backoff khi gặp `HTTP 429`.
- [ ] Schema Repair Pipeline: Nếu LLM trả về JSON khuyết trường hoặc sai cú pháp, chuyển qua bộ lọc sửa chữa cú pháp (`test_schema_repair.py`) trước khi quyết định retry hoặc fail.
- [ ] Giám sát: Cập nhật `gemini_call_count` và `retry_count` trên `exam_sessions`. Zero mutation nếu toàn bộ quá trình sinh đề thất bại.
- [ ] Bảo mật: Cấm log API Key hoặc nội dung prompt nhạy cảm.

### F. Validation toán học, SymPy Evaluator & Logic Checker (TASK-205)

**Nhiệm vụ cần liệt kê trong plan**
- [ ] CẤM TUYỆT ĐỐI dùng `eval()` hoặc `exec()` trên chuỗi biểu thức toán từ người dùng hoặc AI.
- [ ] Phân tích công thức toán qua `sympy.parsing.latex.parse_latex` hoặc AST an toàn.
- [ ] Timeout Guard: Bọc mọi phép biến đổi đại số tượng trưng phức tạp (đạo hàm, tích phân, giải hệ) trong timeout để tránh DoS/treo CPU.
- [ ] Đảm bảo ANTLR runtime (`antlr4-python3-runtime`) hoạt động chính xác trước khi chạy test/deploy.

### G. Export Engine, SSE Progress Streaming & Dọn dẹp File tạm (TASK-206)

**Nhiệm vụ cần liệt kê trong plan**
- [ ] Streaming tiến độ: Dùng Server-Sent Events (SSE) với định dạng chuẩn `event: progress\ndata: {...}\n\n`.
- [ ] Xử lý file tạm: Mọi thao tác sinh PDF (Typst) hoặc đóng gói ZIP phải dùng `tempfile.TemporaryDirectory()` với context manager (`with ...`) để đảm bảo luôn dọn dẹp file rác kể cả khi có ngoại lệ.
- [ ] Stream response: Trả file tải về dưới dạng streaming response với headers `Content-Disposition` và `Content-Type` chuẩn xác.

### H. Schema, type hint và response contract

- [ ] Dùng Pydantic v2 theo pattern đang có; không tạo schema trùng lặp nếu model dùng chung đã tồn tại.
- [ ] Type annotate mọi hàm route, dependency, parser và service; kiểm tra `Optional`/`None` rõ ràng.
- [ ] Không dùng `Any` hoặc ép kiểu để che type error nếu có thể mô hình hóa dữ liệu chính xác.

### I. Viết test và kiểm tra tác động

- [ ] Test hành vi thành công và đầu ra chính xác.
- [ ] Test validation/boundary và zero mutation khi có lỗi.
- [ ] Test auth/ownership/state guard cho endpoint liên quan.
- [ ] Test exception thực tế bằng instance thật của thư viện; cấm fake mocking.
- [ ] Test regression ở các module liên quan.

## 4. Chạy chất lượng code: Windows PowerShell

Chạy từ thư mục `backend/`. Trên Windows PowerShell, ưu tiên dùng đường dẫn Python virtualenv trực tiếp để tránh lỗi CommandNotFound:

```powershell
# Đường dẫn Python virtualenv trên Windows
$PYTHON = ".\.venv\Scripts\python.exe"
```

### 4.1. Ruff — kiểm tra scoped trước, không format toàn repo

```powershell
# Kiểm tra lint trên file/module thuộc task
.\.venv\Scripts\python.exe -m ruff check app/services/parser/ tests/test_parsers.py

# Format CHỈ những file thuộc task (CẤM format toàn repo)
.\.venv\Scripts\python.exe -m ruff format app/services/parser/ tests/test_parsers.py

# Kiểm tra lại sau format
.\.venv\Scripts\python.exe -m ruff check app/services/parser/ tests/test_parsers.py
```

### 4.2. Mypy — Static Type Checking

```powershell
.\.venv\Scripts\python.exe -m mypy app/ --ignore-missing-imports
```

### 4.3. Pytest — Test scoped rồi regression

```powershell
# Chạy test phạm vi hẹp thuộc task
.\.venv\Scripts\python.exe -m pytest tests/test_parsers.py tests/api/test_ingest.py -v

# Chạy regression liên quan
.\.venv\Scripts\python.exe -m pytest tests/api/test_sessions.py -v
```

### 4.4. Bộ kiểm tra CI Pre-push Pipeline (Mô phỏng 100% GitHub Actions `.github/workflows/ci.yml`)

> [!IMPORTANT]
> **BẮT BUỘC TRƯỚC KHI PUSH CODE:** Chạy toàn bộ 4 bước dưới đây để đảm bảo GitHub Actions CI chắc chắn xanh 100%:

```powershell
# Bước 1: Linting toàn bộ backend app
.\.venv\Scripts\python.exe -m ruff check app/

# Bước 2: Type checking với Mypy
.\.venv\Scripts\python.exe -m mypy app/ --ignore-missing-imports

# Bước 3: SymPy LaTeX Parser Smoke Test (ANTLR Runtime Verification)
.\.venv\Scripts\python.exe -c "import sympy; from sympy.parsing.latex import parse_latex; res = parse_latex('x^2 + 1'); assert res is not None; print('SymPy LaTeX parser verified:', res)"

# Bước 4: Chạy toàn bộ 245+ Pytest với Mock Environment Variables giống hệt CI
$env:ENVIRONMENT="test"
$env:SUPABASE_URL="https://mock.supabase.co"
$env:SUPABASE_ANON_KEY="mock-anon-key"
$env:SUPABASE_SERVICE_ROLE_KEY="mock-service-role-key"
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

Chạy riêng từng lệnh. Không dùng chuỗi lệnh có dấu `;` rồi báo pass nếu có lệnh fail ngầm.

## 5. Kiểm tra Git và phạm vi trước khi hoàn tất

Chạy từ repo root:

```powershell
git status --short
git diff --stat
git diff --check
git diff
```

Checklist:
- [ ] Chỉ có file liên quan task bị thay đổi.
- [ ] Không có file của thành viên khác bị reformat ngoài ý muốn.
- [ ] Không có `.tmp`, log, cache, `.pytest_cache`, file nháp hoặc file sprint chung như `w2_21_10.md` bị thêm vào diff/stage.
- [ ] Không có secret, token, nội dung đề thi nhạy cảm hoặc `print()` debug.
- [ ] Không dùng `git restore` làm mất thay đổi có sẵn của người khác. Chỉ phục hồi phần thay đổi ngoài ý muốn do chính agent tạo ra.
- [ ] Dùng Conventional Commits: `feat(api): implement docx ingestion parser [TASK-202]`.

## 6. Definition of Done và báo cáo cuối

Task chỉ được đánh dấu hoàn thành khi các mục áp dụng đều đạt:
- [ ] Tiêu chí nghiệp vụ và API contract đáp ứng.
- [ ] Nguyên nhân gốc (nếu sửa bug) đã được chứng minh.
- [ ] Có test hồi quy và test cho các failure mode quan trọng.
- [ ] Validation/auth/state failure không gây mutation trái phép.
- [ ] Toàn bộ 4 bước CI Pre-push Pipeline đã chạy và pass 100%.
- [ ] `git diff` đã rà soát sạch sẽ.

Báo cáo cuối theo cấu trúc:
```markdown
## Kết quả
- Hành vi đã hoàn thành:
- Nguyên nhân gốc (nếu sửa bug):
- File/module thay đổi và lý do:
- API/DB/Storage side effect:

## Kiểm chứng CI & Test
- `ruff check app/`: PASS
- `mypy app/`: PASS
- `SymPy Smoke Test`: PASS
- `pytest toàn bộ suite`: PASS (x/x passed)

## Còn lại
- Rủi ro/giới hạn chưa xử lý:
- Giả định hoặc blocker:
- Git scope/diff:
```

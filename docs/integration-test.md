# TASK-005 — Rate limit/CORS: kiểm thử và bàn giao

Owner: Quỳnh (TV4). Reviewer/owner nhận điểm nối auth và sessions: Duy (TV3).
Mốc kiểm chứng: 19/10/2026; Python 3.11, SlowAPI 0.1.10 trong Docker backend.

## Phạm vi PR

- Hai chính sách quota dùng chung theo verified user hoặc remote IP:
  - CRUD: tổng 60 requests/phút qua các route/method/session gắn `crud_rate_limit`.
  - Generate: tổng 10 requests/phút qua các session gắn `generation_rate_limit`.
  - Hai ngân sách độc lập; hai user chung IP không chia sẻ quota.
- Response vượt quota: HTTP 429, body `{"detail": "Rate limit exceeded"}`, `Retry-After` là số giây dương.
- `main.py` đăng ký limiter/handler và đúng một CORS middleware từ `core/cors.py`; hai health endpoints được đánh dấu exempt.
- CORS đọc `settings.CORS_ORIGINS`, loại origin trùng/rỗng, từ chối wildcard origin. Credentials bật; methods GET/POST/PATCH/DELETE; request headers Authorization/Content-Type cùng các header CORS tiêu chuẩn. Response expose `Retry-After`.
- Backend CI hiện có thêm bước `python -m pytest backend/tests -q`; không thêm Docker workflow mới.

Ứng dụng tại baseline này mới có health/metrics. Đăng ký limiter không tự áp quota lên mọi route: routes nghiệp vụ phải dùng decorator. Auth/session CRUD/generate HTTP thật chưa được ghép trong PR này. Không thêm route giả vào production để chứng minh quota.

## Contract cho PR tiếp theo của Duy

### 1. Identity sau xác thực

Giữ logic xác minh Supabase JWT của TASK-102. Sau khi xác minh thành công, dependency auth đặt ID vào request state trước khi trả CurrentUser:

```python
# Chỉ thực hiện sau khi token đã được xác minh thành công.
request.state.authenticated_user_id = current_user.id
return current_user
```

`get_user_or_ip_key()` chỉ tin chuỗi user ID không rỗng ở state này. Nếu state thiếu/không hợp lệ thì dùng remote IP, không lấy user ID từ JWT chưa xác minh, request body hoặc header do client tự khai.

Header `X-Test-User` chỉ là shortcut của fixture security tests; không triển khai nó thành auth production. Module cũng không trực tiếp tin `X-Forwarded-For`/`X-Real-IP`; việc trust proxy phải cấu hình theo topology thực tế với Tâm. Dependency auth vẫn chịu trách nhiệm trả 401/403; limiter không thay thế auth hoặc ownership.

### 2. Decorator trên routes

Ví dụ minh họa cho route CRUD sau khi Duy ghép (không phải route mới trong PR này):

```python
from fastapi import Depends, Request, Response

from app.core.rate_limit import crud_rate_limit


@router.get("")
@crud_rate_limit
async def list_sessions(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
):
    # Giữ logic truy vấn và response model của TASK-104 tại đây.
    ...
```

- Router decorator nằm ngoài/trên decorator rate limit. FastAPI chạy auth dependencies trước khi gọi endpoint đã bọc.
- Với generate, dùng `generation_rate_limit` trên route tương ứng. Shared scope giúp đổi session ID không tạo thêm quota.
- Endpoint luôn cần `request: Request`. Khi trả dict/Pydantic/None, nhận thêm `response: Response` để SlowAPI chèn headers. Nếu trả một Response trực tiếp, SlowAPI chèn headers lên Response đó.
- Với DELETE trả 204, giữ đúng status và body rỗng; kiểm tra lại headers trên route thật. Đổi tên kết quả truy vấn DB thành `db_result` nếu tên `response` đang trùng tham số Response.
- Khi dùng `limiter_instance` tùy chọn cho app/test riêng, truyền cùng instance đó cho decorator và `register_rate_limiter`; không trộn bộ đếm singleton với bộ đếm khác.

### 3. Giữ wiring khi cập nhật dev

```python
from app.core.cors import register_cors
from app.core.rate_limit import register_rate_limiter

register_rate_limiter(app)
register_cors(app)
```

Giữ các lời gọi trên khi đưa routers vào main.py; không khôi phục block CORS inline cũ hoặc đăng ký CORS thêm lần nữa. Không thêm blanket rate-limit middleware chạy trước auth để thay cho decorators, vì có thể làm request đăng nhập vẫn bị đếm theo IP.

Hai health routes `/health` và `/api/health/metrics` tiếp tục exempt. Preflight OPTIONS do CORS xử lý, không sử dụng ngân sách route nghiệp vụ. `RATE_LIMIT_EXEMPT_PATHS` là danh sách chính sách dùng để đối chiếu, không tự động áp whitelist cho mọi route mới.

Nếu frontend thêm method/header cross-origin, cập nhật policy và test có chủ đích thay vì mở wildcard. HTTP 429 application limiter không đồng nghĩa quota Gemini đã hết hoặc user hết phiên.

## Chạy kiểm tra local

Từ root repository, với backend đã build và chạy theo README:

```powershell
docker compose exec -T backend python -m pytest tests/security -q
docker compose exec -T backend python -m pytest tests -q
docker compose exec -T backend ruff check app tests/security
docker compose exec -T backend mypy app tests/security --ignore-missing-imports
docker compose exec -T backend ruff format --check app/core/rate_limit.py app/core/cors.py app/main.py tests/security
```

Baseline Compose hiện mount backend vào container nhưng không bật reload. Sau khi sửa main.py, dùng `docker compose restart backend` để tiến trình HTTP nạp code mới. Nếu Docker setup mới của Tâm đã merge, dùng hướng dẫn sync/watch/rebuild trong README mới; không mặc định container đang chạy đã thấy source mới.

Smoke HTTP từ PowerShell:

```powershell
curl.exe -i http://localhost:8000/health
curl.exe -i http://localhost:8000/api/health/metrics

curl.exe -i -X OPTIONS http://localhost:8000/health `
  -H "Origin: http://localhost:3000" `
  -H "Access-Control-Request-Method: POST" `
  -H "Access-Control-Request-Headers: Authorization,Content-Type"
```

Hai GET và preflight hợp lệ phải trả 200. Đổi requested method thành PUT phải nhận 400. Đổi Origin thành origin ngoài danh sách phải nhận 400 cho preflight và không có `Access-Control-Allow-Origin` cho origin đó. Đây là kiểm tra CORS; nó không tạo POST route cho `/health`.

Không dùng health để thử nhận 429, vì health được miễn rate limit. Quota được kiểm tra bằng app fixture qua decorators sản phẩm cho đến khi có routes thật.

## Bằng chứng kiểm thử

| Kiểm tra | Phạm vi | Kết quả |
|---|---|---|
| Regression generate trước fix | Helper thật, một user qua 11 session ID | FAIL: request 11 nhận 200 thay vì 429 |
| Security suite sau fix | Decorators thật, nhiều route/method/session; verified identity giả trong fixture | 40 passed |
| Backend regression | Toàn bộ tests hiện có; không gọi AI/DB thật | 52 passed |
| Ruff | app + tests/security | All checks passed |
| Mypy | app + tests/security | Success, 25 source files |
| Format check | main.py, hai core modules, tests/security | 7 files already formatted |
| HTTP trên backend đã restart | health/metrics; preflight POST, PUT, origin lạ | 200/200; 200/400/400 |

Security suite còn kiểm tra identity/IP riêng, không tin unverified headers, DELETE 204 body rỗng, reset cửa sổ, Retry-After tại biên và fallback, 429 có CORS/expose header, preflight không hao quota và health vẫn hoạt động sau khi ngân sách nghiệp vụ hết. Test app/storage được cô lập; test reset chỉ expire storage của fixture, không ngủ hoặc đổi clock của server thật.

GitHub Actions đã được cấu hình bước pytest nhưng chưa chạy trên GitHub ở mốc này vì chưa push/tạo PR. Bảng trên là kết quả local Docker, không phải chứng nhận CI remote đã pass.

## Giới hạn và checklist sau khi Duy ghép

- JWT thật, CRUD/clone thật và hai tài khoản Supabase thật chưa được kiểm thử trong TASK-005 độc lập; Duy nối verified state và decorators rồi chạy API/auth/ownership/security tests cùng nhau.
- Smoke frontend thật: login/profile, CRUD/clone, 401/403 không bị đổi thành lỗi khác; 429 đọc được body/Retry-After từ origin hợp lệ.
- Smoke nhiều session vẫn dùng chung quota generate, nhiều CRUD methods dùng chung quota CRUD; user B còn lượt sau khi user A hết lượt.
- In-memory limiter chỉ dùng cho MVP một worker/một instance, reset khi restart. Nhiều worker/instance cần shared storage; không triển khai Redis trong PR này.
- Limiter dùng SlowAPI `_inject_headers` trong một handler riêng; kiểm tra lại khi nâng phiên bản SlowAPI. Phiên bản đã thử: 0.1.10.
- Chống flood trước bước gọi Supabase Auth và trust forwarded IP cần thiết kế cùng auth/proxy thực tế, chưa nằm trong implementation này.
- Cảnh báo Compose `version` obsolete và TestClient/httpx deprecation vẫn còn; không đổi môi trường/dependencies của Tâm trong PR này.

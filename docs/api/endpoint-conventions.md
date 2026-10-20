# Quy chuẩn Endpoint & Rate Limit

Tài liệu quy định chuẩn chữ ký hàm cho API endpoint khi gắn **Rate Limiting (TASK-005)** và **Auth (TASK-102)** để tránh lỗi runtime SlowAPI 500.

---

## 1. Chuẩn Chữ Ký Hàm (Bắt buộc `request: Request`)

> **Cảnh báo:** Bất kỳ endpoint nào gắn `@crud_rate_limit` hoặc `@generation_rate_limit` **bắt buộc phải có `request: Request`**. Nếu thiếu, server vẫn khởi động được nhưng sẽ **crash HTTP 500** ngay khi nhận request.

### Mẫu chuẩn:
```python
@router.get("/sessions")
@crud_rate_limit
async def list_sessions(
    request: Request,                                       # Bắt buộc: để SlowAPI định danh user/IP
    response: Response,                                      # Khuyên dùng: để SlowAPI chèn header X-RateLimit-*
    current_user: CurrentUser = Depends(get_current_user),  # Gán request.state.authenticated_user_id
):
    return {"ok": True}
```

---

## 2. Thứ tự Decorator

```python
@router.post("/sessions/{id}/generate")  # 1. Router nằm TRÊN CÙNG
@generation_rate_limit                   # 2. Rate limit nằm TRONG
async def generate(request: Request, response: Response, ...):
    ...
```
*FastAPI chạy dependency `get_current_user` trước $\to$ lưu User ID vào `request.state` $\to$ SlowAPI trừ quota theo User thay vì fallback về IP.*

---

## 3. Các lưu ý quan trọng

1. **Không ghi đè biến `response`:** Khi hàm có tham số `response: Response`, kết quả truy vấn database phải đặt tên là `db_res` hoặc `result` (tránh `response = db.execute()`).
2. **Endpoint DELETE (HTTP 204):** Trả trực tiếp `Response(status_code=204)`, không cần thêm tham số `response: Response` thứ hai:
   ```python
   @router.delete("/sessions/{id}", status_code=204)
   @crud_rate_limit
   async def delete_session(session_id: str, request: Request, ...):
       ...
       return Response(status_code=204)
   ```

---

## 4. Bảng Hạn Ngạch (Quota Matrix)

| Decorator | Quota | Scope | Áp dụng |
|---|:---:|---|---|
| `@crud_rate_limit` | **60 req/phút/user** | `session-crud` | Các route CRUD thông thường |
| `@generation_rate_limit` | **10 req/phút/user** | `session-generation` | Route sinh đề, sinh bù |
| `@limiter.exempt` | **Không giới hạn** | None | `/health`, `/api/health/metrics` |

---

## 5. Checklist trước khi tạo Route mới
- [ ] Đã khai báo tham số `request: Request`.
- [ ] Đã thêm `response: Response` (nếu trả dict/Pydantic).
- [ ] Không trùng tên biến `response = ...` trong thân hàm.
- [ ] Thứ tự decorator: `@router` ở trên, `@rate_limit` ở dưới.

# KẾ HOẠCH CHI TIẾT TÍCH HỢP ATTEMPT PERMIT (TASK-304 / ĐẠT) VÀO REVIEW ORCHESTRATOR (TASK-301 / DUY)

**Tài liệu tham chiếu:**
- Branch Đạt: `feat/dat-task-304-targeted-regeneration` tại commit `a8f61d5` (PR #26).
- Handoff doc: `docs/ai-w3-targeted-regeneration.md`.
- Implementation: `backend/app/models/targeted.py`, `backend/app/services/generation/attempts.py`, `backend/app/services/generation/targeted_service.py`.
- Unit tests của Đạt: `backend/tests/ai/test_attempt_permits.py`.

---

## I. RÀ SOÁT CẤU TRÚC VÀ CÁC THÀNH PHẦN TỪ PHÍA ĐẠT (PR #26)

### 1. Data Model & Types (`app.services.generation.attempts`)

```python
class AttemptPermit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    attempt_id: UUID
    dispatch_permitted: StrictBool  # True: cho phép gửi Gemini; False: từ chối (hết quota)
    calls_used: Annotated[StrictInt, Field(ge=0, le=30)]      # Số lượt đã dùng toàn session (0-30)
    remaining_calls: Annotated[StrictInt, Field(ge=0, le=30)] # Số lượt còn lại toàn session (0-30)
    replayed: StrictBool           # True: request bị lặp lại, KHÔNG được dispatch lần 2
```

- **Type alias callback:**
  `AcquireAttempt = Callable[[UUID, UUID], Awaitable[AttemptPermit]]`
  Nhận vào: `(operation_id: UUID, attempt_id: UUID)`.
  Trả về: `AttemptPermit` bất biến, kiểu dữ liệu strict (không chấp nhận ép kiểu chuỗi như `"false"` hoặc số nguyên cho boolean).

- **Budget quản lý bên trong Adapter (`DurableAttemptBudget`):**
  - Giới hạn: `1 <= limit <= 4` (mặc định 4).
  - Trước mỗi lượt gửi Gemini (kể cả repair, math retry), budget tự sinh `attempt_id = uuid4()` và gọi `acquire_attempt(self.operation_id, attempt_id)`.
  - Nếu `dispatch_permitted == False` $\rightarrow$ ném `GatewayError("REVIEW_QUOTA_EXHAUSTED")`.
  - Nếu `replayed == True` $\rightarrow$ ném `GatewayError("REVIEW_ATTEMPT_REPLAYED")`.
  - Nếu ID không khớp hoặc `calls_used < used + 1` $\rightarrow$ ném `GatewayError("REVIEW_PERMIT_INVALID")`.
  - Nếu callback văng exception / timeout / network drop $\rightarrow$ ném `GatewayError("REVIEW_PERMIT_UNCERTAIN")`.
  - Không bao giờ tự xin ID mới để retry một permit bị uncertain; dừng ngay lập tức (fail-closed).

### 2. Callable Interface (`app.services.generation.targeted_service.TargetedRegenerator`)

```python
async def regenerate_question_variant(
    self,
    session_id: UUID | str,
    question_id: UUID | str,
    source_snapshot: dict[str, Any],
    blueprint: dict[str, Any],
    current_variant: dict[str, Any],
    peer_variants: list[dict[str, Any]],
    *,
    operation_id: UUID | str | None = None,
    acquire_attempt: AcquireAttempt | None = None,
) -> RegeneratedVariantResult:
```

- **Yêu cầu đầu vào bắt buộc:**
  1. `operation_id`: UUID của đợt reject này (phải truyền, không được `None`).
  2. `acquire_attempt`: Async callable thỏa mãn `AcquireAttempt` (phải truyền, không được `None`). Nếu thiếu một trong hai $\rightarrow$ ném `TargetedGenerationError("REVIEW_PERMIT_REQUIRED")`.
  3. `source_snapshot`: Phải chứa `id`, `options`, `content_hash` (khớp với fingerprint confirmed source), `question_text`/`raw_content`, `correct_answer`/`correct_key`, `solution`/`solution_md`.
  4. `current_variant`: Phải chứa `id` khớp `question_id`, `source_question_id` khớp `source.id`, `content`/`stem_latex`, `options` (4 phương án, có thể có tiền tố `A. `).
  5. `peer_variants`: Danh sách các câu hiện hành cùng `source_question_id` trong cùng phiên ở các mã đề khác.

- **Kết quả trả về (`RegeneratedVariantResult` / `to_review_payload()`):**
  - `stem_latex`: Chuỗi LaTeX đề bài mới (1 - 12000 ký tự).
  - `content`: Alias của `stem_latex` do `to_review_payload()` sinh ra (phù hợp với ReviewRepository).
  - `options`: List đúng 4 phương án **không tiền tố** A/B/C/D, nội dung phân biệt sau khi chuẩn hóa.
  - `correct_key`: 'A', 'B', 'C', hoặc 'D'.
  - `solution_md`: Lời giải chi tiết.
  - `validation_report`: Chứa `is_valid: bool`, `math_verified: bool`, `warnings`, `checks`.
  - `api_calls_count`: Số permit đã được cấp thành công (0 đến 4).

- **Exception ném ra:**
  `TargetedGenerationError(code: str, api_calls_count: int)`
  Bao gồm các mã lỗi:
  - `"REVIEW_PERMIT_REQUIRED"`
  - `"REVIEW_QUOTA_EXHAUSTED"`
  - `"REVIEW_ATTEMPT_REPLAYED"`
  - `"REVIEW_PERMIT_INVALID"`
  - `"REVIEW_PERMIT_UNCERTAIN"`
  - `"PREVIOUS_VARIANT_MISMATCH"`
  - `"REGENERATION_INPUT_INVALID"`
  - `"MATH_VALIDATION_FAILED"`
  - `"GENERATION_INTERNAL"`

---

## II. RÀ SOÁT CÁC MỤC CẦN UPDATE TRONG TASK-301 (DUY)

| STT | File cần sửa | Thành phần hiện tại | Thay đổi cần thực hiện | Lưu ý tránh nhầm lẫn |
|---|---|---|---|---|
| 1 | `backend/app/services/review/repository.py` | Chưa có hàm `acquire_attempt`. Đang tự cộng `+4` vào `gemini_review_calls` trong TX1 và hoàn trừ trong TX2/Rollback. | Bổ sung method `async def acquire_attempt(self, operation_id: UUID, attempt_id: UUID) -> AttemptPermit`.<br>Quản lý atomic attempt ledger (cả cho Stateful Mock DB lẫn chuẩn bị RPC TASK-302). | - Không tự hoàn trừ quota 4 cố định.<br>- `calls_used` và `remaining_calls` phải là integer strictly trong khoảng 0-30.<br>- Mỗi `attempt_id` trong cùng `operation_id` chỉ được cấp 1 lần; nếu gọi lại cùng ID thì `replayed=True`, `dispatch_permitted=False`. |
| 2 | `backend/app/services/review/service.py` | `reject_question()` khởi tạo `regeneration_id = uuid4()`, nhưng truyền vào `generator` không có `operation_id` và `acquire_attempt`. Bắt lỗi chung `Exception` và đọc `getattr(exc, 'dispatched_calls', 1)`. | 1. Dùng `operation_id = uuid4()` (đồng nhất với `regeneration_id`).<br>2. Truyền `operation_id=operation_id` và `acquire_attempt=self.repo.acquire_attempt` vào `self.ai_generator`.<br>3. Bắt trực tiếp `TargetedGenerationError` / `GatewayError`.<br>4. Lấy số `api_calls_count` thực tế đã cấp để reconcile trong rollback.<br>5. Map đúng HTTP status: 429 nếu `REVIEW_QUOTA_EXHAUSTED`, 502 nếu permit uncertain/invalid. | - Không bao giờ refund nếu không chắc permit đã gửi hay chưa.<br>- Xử lý `asyncio.CancelledError` nguyên vẹn (propagate), không nuốt lỗi làm sai lệch ledger. |
| 3 | `backend/app/services/review/service.py` | `_default_ai_generator` mock cũ chỉ nhận kwargs cũ, trả `api_calls_count=1` giả định. | Cập nhật `_default_ai_generator` nhận `operation_id`, `acquire_attempt` và trả payload chuẩn khớp `TargetedRegenerator.to_review_payload()`. | Mock mặc định chỉ dùng cho unit test nội bộ khi không inject mock tường minh. |
| 4 | `backend/tests/services/test_review_lifecycle.py` | Các fixture `_mock_ai` trong test file chỉ nhận snapshot cũ, không nhận `operation_id` và `acquire_attempt`. | Cập nhật `_mock_ai(**kw: Any)` nhận linh hoạt `*args, **kwargs` và tương thích cả chữ ký mới của Đạt. | Tránh làm hỏng 32 test case regression hiện có. |
| 5 | `backend/tests/services/test_review_lifecycle.py` | Chưa có test case kiểm thử việc cấp permit, từ chối permit khi hết quota, và xử lý uncertain permit. | Bổ sung 4 unit tests mới:<br>1. `test_reject_passes_operation_id_and_acquires_permit`<br>2. `test_reject_denied_permit_raises_429`<br>3. `test_reject_uncertain_permit_retains_charge_and_fails_502`<br>4. `test_mock_targeted_adapter_compatibility` | Kiểm thử cả trường hợp mock và tương thích với `TargetedRegenerator` / `mock_regenerate_question_variant`. |

---

## III. CẤU TRÚC CODE CHI TIẾT SẼ TRIỂN KHAI

### 1. `backend/app/services/review/repository.py`
```python
# Bổ sung phương thức acquire_attempt trên ReviewRepository
async def acquire_attempt(self, operation_id: UUID, attempt_id: UUID) -> AttemptPermit:
    """Acquires a durable permit for a single AI provider dispatch attempt.
    
    Conforms strictly to TASK-304 AttemptPermit schema and TASK-302 RPC contract.
    Enforces session ceiling (30) and operation ceiling (4).
    """
    # 1. Tìm session_id sở hữu operation_id hoặc lấy từ active reservation
    # 2. Kiểm tra attempt_id đã từng được cấp cho operation_id chưa (Idempotency / Replay check)
    #    Nếu đã tồn tại: trả AttemptPermit(..., dispatch_permitted=False, replayed=True)
    # 3. Kiểm tra quota session (calls_used + 1 <= 30) và operation (op_calls + 1 <= 4)
    #    Nếu vượt: trả AttemptPermit(..., dispatch_permitted=False, replayed=False)
    # 4. Ghi nhận permit vào ledger, tăng calls_used
    # 5. Trả AttemptPermit(dispatch_permitted=True, replayed=False, calls_used=..., remaining_calls=...)
```

### 2. `backend/app/services/review/service.py`
```python
# Trong ReviewService.reject_question:
operation_id = uuid4()
# ... TX1 Reserve ...

# Phase 2: AI Execution
try:
    ai_result = await asyncio.wait_for(
        generator(
            session_id=session_id,
            question_id=question_id,
            source_snapshot=snapshot["source"],
            blueprint=snapshot["blueprint"],
            current_variant=snapshot["variant"],
            peer_variants=snapshot["peers"],
            operation_id=operation_id,
            acquire_attempt=self.repo.acquire_attempt,
        ),
        timeout=45.0,
    )
except Exception as exc:
    # Trích xuất số permit đã acknowledged thực tế từ exception của Đạt
    dispatched = getattr(exc, "api_calls_count", 0)
    # Rollback trạng thái câu hỏi và reconcile ledger (không hoàn quá số đã cấp)
    await self.repo.emergency_rollback_tx(
        session_id=session_id,
        old_question_id=question_id,
        regeneration_id=operation_id,
        error_msg=str(exc),
        user_id=user_id,
        actual_calls_dispatched=dispatched,
    )
    # Map đúng error code
    err_str = str(exc)
    if "REVIEW_QUOTA_EXHAUSTED" in err_str:
        raise ReviewDomainException(429, "ERR_REVIEW_QUOTA_EXHAUSTED", "Đã dùng hết 30 lượt AI của buổi review")
    if "REVIEW_PERMIT_UNCERTAIN" in err_str or "REVIEW_PERMIT_INVALID" in err_str:
        raise ReviewDomainException(502, "ERR_AI_GATEWAY_PERMIT_FAILURE", "Không thể xác thực giấy phép gọi AI với CSDL")
    # ... các mã lỗi khác ...
```

---

## IV. TRÌNH TỰ THỰC HIỆN VÀ VERIFICATION

1. **Bước 1:** Bổ sung mock model `AttemptPermit` tương thích trong `app.models.schemas` hoặc import an toàn từ `app.services.generation.attempts` nếu module có sẵn.
2. **Bước 2:** Cập nhật `ReviewRepository.acquire_attempt` để hỗ trợ cấp permit in-memory/stateful fake cho test suite và chuẩn bị interface RPC cho Hùng.
3. **Bước 3:** Cập nhật `ReviewService.reject_question` tích hợp `operation_id` và `acquire_attempt`.
4. **Bước 4:** Cập nhật test suites và bổ sung các test cases mới.
5. **Bước 5:** Chạy toàn bộ regression test suites:
   `& "C:\Users\ASUS Vivobook\AppData\Local\Python\bin\python.exe" -m pytest backend/tests/services/test_review_lifecycle.py backend/tests/api/test_review_api.py -v`
6. **Bước 6:** Chạy linter & typecheck:
   `ruff check backend/app/services/review backend/tests/services`
   `mypy backend/app/services/review`


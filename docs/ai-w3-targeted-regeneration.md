# TASK-304 — Handoff cho Review API

Owner AI: Đạt. Quyết định đầu vào: [Duy trên PR #26](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/26#issuecomment-6485507631). Không có trường reason/prompt giáo viên.

## Callable và schema

```python
from app.models.targeted import RegeneratedVariantResult
from app.services.generation.service import GenerationService
from app.services.generation.targeted_service import TargetedRegenerator

# Gateway có lifecycle do ứng dụng quản lý, dùng lại key pool/concurrency hiện có.
regenerator = TargetedRegenerator(GenerationService(gateway), max_api_calls=4)
result: RegeneratedVariantResult = await regenerator.regenerate_question_variant(
    session_id=session_id, question_id=question_id,
    source_snapshot=source, blueprint=canonical_blueprint,
    current_variant=current, peer_variants=peers,
    operation_id=operation_id, acquire_attempt=review_repository.acquire_attempt,
)
# ReviewService PR #28 cần dict .get(), truyền regenerator làm ai_generator.
payload = result.to_review_payload()  # thêm content = stem_latex
```

`source_snapshot`: `id`, `question_text` hoặc `raw_content`/`raw_text`, `options`, `correct_answer` hoặc `correct_key`, `solution` hoặc `solution_md`, **content_hash**. Hash là `source_fingerprint(prepare_sources([source]))` của đúng nguồn đã confirm; không tự tính lại hash tại thời điểm reject để bỏ qua xác nhận. Nếu DB dùng một hash khác, owner cần map từ snapshot đã confirm thay vì truyền hash không tương thích.

`blueprint`: JSON canonical 0.4.0, khớp toàn bộ source. Không nhận fallback variables/domains thay canonical.

`current_variant`: `id` khớp question_id, `source_question_id`, `content` (hoặc `stem_latex`/`question_text`), `options`. Mỗi peer cũng có source_question_id/content/options; BE chỉ truyền peers hiện hành cùng nguồn và phiên. Options đầu ra là bốn string **không tiền tố**, A tương ứng index 0. Adapter bỏ đúng tiền tố A./B./C./D. ở các options persisted để so sánh identity.

Kết quả: stem_latex/options/correct_key/solution_md/validation_report/api_calls_count. `is_valid` nghĩa không có lỗi chắc chắn trong các check đã chạy; **không chứng nhận mọi bài toán đúng**. math_verified chỉ true khi answer_verified có status verified và confidence sympy_verified; reasoning/đẳng cấu tổng quát luôn cần giáo viên duyệt. Report giữ checks và warnings đầy đủ.

## Quota, lỗi và timeout

- Tối đa 4 provider attempts; tối đa 2 math retries nằm trong trần đó. Gateway reserve từng lần dispatch; schema repair/network errors cũng tính.
- `max_api_calls` là trần cục bộ 1–4, không phải giữ chỗ/trừ trước bốn lượt. Mỗi dispatch cần permit bền vững từ DB. Cách reserve 3/4 rồi hoàn chênh lệch trong bản PR #28 cũ không còn là contract tích hợp mới.
- `TargetedGenerationError` có `code` và `api_calls_count`, kể cả thất bại. Count là số permit mới đã được adapter nhận xác nhận, có thể gồm grant rồi timeout trước transport; không chứng nhận chính xác request đã tới Gemini. Ledger DB là nguồn quyết toán chính thức, nhất là khi mất response/cancel/crash. Không tự hoàn chênh lệch bằng count này. Không log payload/secrets từ provider.
- Deadline adapter tối đa 40s, nhỏ hơn timeout 45s của review API. CancelledError truyền lên; durable reservation/recovery do BE quản lý. Không hoàn quota bằng giả định cố định rằng lỗi luôn dùng 1 call.
- Quota 30 attempts/session, bảo vệ nhiều worker, crash/revision/uniqueness phải ở BE/DB. Local ceiling không thay durable ledger.

## Callback permit — cập nhật 01/11/2026

[Đề xuất Đạt trên #36](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551270882), [Duy xác nhận policy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6546291626). RPC contract chính do Hùng quản lý tại PR #36; shape adapter dưới đây đã triển khai để bàn giao, chưa coi Hùng đã cập nhật/chấp nhận toàn bộ chữ ký.

`operation_id` và `acquire_attempt` là keyword-only bắt buộc cho real adapter; thiếu dependency trả `REVIEW_PERMIT_REQUIRED` trước dispatch. Không có local-only fallback production.

```python
from uuid import UUID
from app.services.generation.attempts import AttemptPermit

async def acquire_attempt(operation_id: UUID, attempt_id: UUID) -> AttemptPermit:
    # TASK-301 wrapper: service-role RPC do TASK-302 cung cấp.
    row = await repository_call(operation_id, attempt_id)
    return AttemptPermit(**{name: row[name] for name in AttemptPermit.model_fields})
```

Ví dụ chỉ mô tả wrapper; `repository_call` chưa được cung cấp trong TASK-304. Model frozen, booleans/counts strict; UUID được parse từ RPC string. Fields: operation_id, attempt_id, dispatch_permitted, calls_used (session), remaining_calls, replayed. Duy map domain/HTTP ở service, không đưa DB credentials vào adapter. SDK automatic retry đang tắt; mọi retry/repair do GenerationService gọi lại đều đi qua RequestContext.reserve_request tại gateway ngay trước transport, sau khi đợi key/concurrency.

- Mỗi provider attempt mới có UUID riêng. RPC transport retry/reconciliation giữ nguyên UUID; wrapper không được đổi ID khi chưa biết permit đã commit chưa.
- Chỉ dispatch với initial grant true, replayed=false, IDs khớp và deadline còn hiệu lực. Denial/replay/malformed/error dừng thao tác; không tự xin ID khác để vượt kết quả chưa rõ. Replay không phải quyền gửi lần nữa.
- REVIEW_QUOTA_EXHAUSTED, REVIEW_ATTEMPT_REPLAYED, REVIEW_PERMIT_INVALID, REVIEW_PERMIT_UNCERTAIN đều không retry provider. Callback transport exception được sanitize thành uncertain; cancellation truyền nguyên trạng lên.
- Permit đã cấp vẫn tính khi provider lỗi hoặc deadline/cancel xảy ra trước dispatch. Nếu mất response, adapter có thể báo 0 acknowledged nhưng DB đã trừ 1; caller phải reconcile ledger, không yêu cầu giả định count=0 hay tự refund. Không có transaction DB giữ mở trong lúc gọi AI.
- Mock tường minh chấp nhận các keyword mới nhưng không gọi callback/provider, vẫn 0 calls và math_verified=false.

Handoff test tách rõ: offline callback/gateway/adapter tests không chứng minh RPC atomicity, quota đa worker hoặc recovery thật. Những phần đó chờ Hùng/Duy. `calls_used`/remaining_calls không được dùng thay quyền dispatch của RPC.

## Mock và tình trạng tích hợp

`mock_regenerate_question_variant` có cùng keyword inputs và trả dict tương thích PR #28; chỉ dùng khi **inject tường minh** vào tests. MOCK hiện rõ trong stem/solution, math_verified=false, api_calls_count=0. Không dùng mock như fallback production và không bật tự động khi API lỗi.

Đối chiếu lịch sử PR #28 tại `510b765` (không phải trạng thái hiện tại):

1. `get_question_snapshot` chưa select content_hash/canonical JSON; peers thiếu source_question_id. Owner Duy/Hùng cần hoàn thiện mapper trước live integration.
2. Constant reservation là 3, trong khi phản hồi contract cho trần 4.
3. Nhánh lỗi BE chưa quyết toán `TargetedGenerationError.api_calls_count`; mock mặc định của BE đang báo math_verified=true. Owner thay bằng injection thật và xử lý lỗi theo số calls thực tế.

Unit tests độc lập không chứng nhận các transaction/rollback/quota SQL hoặc endpoint hiện tại đã nối AI thật. Chưa chạy live Gemini W3 hoặc DB E2E.

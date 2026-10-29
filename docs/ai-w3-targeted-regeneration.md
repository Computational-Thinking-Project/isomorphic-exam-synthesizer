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
- `max_api_calls` phải bằng số lượt BE đã giữ chỗ nguyên tử. Nếu BE mới reserve 3 như PR #28, cấu hình 3; **không chạy mặc định 4 trên reservation 3**. BE cần đồng bộ constant trước khi dùng đủ trần contract.
- `TargetedGenerationError` có `code` và `api_calls_count`, kể cả thất bại sau khi đã gọi AI. BE phải quyết toán số thực tế cả success lẫn failure, giữ nguyên câu cũ. Không log payload/secrets từ provider.
- Deadline adapter tối đa 40s, nhỏ hơn timeout 45s của review API. CancelledError truyền lên; durable reservation/recovery do BE quản lý. Không hoàn quota bằng giả định cố định rằng lỗi luôn dùng 1 call.
- Quota 30 calls, bảo vệ nhiều worker, crash/revision/uniqueness phải ở BE/DB. Budget cục bộ không thay durable reservation.

## Mock và tình trạng tích hợp

`mock_regenerate_question_variant` có cùng keyword inputs và trả dict tương thích PR #28; chỉ dùng khi **inject tường minh** vào tests. MOCK hiện rõ trong stem/solution, math_verified=false, api_calls_count=0. Không dùng mock như fallback production và không bật tự động khi API lỗi.

Đối chiếu PR #28 tại `510b765`:

1. `get_question_snapshot` chưa select content_hash/canonical JSON; peers thiếu source_question_id. Owner Duy/Hùng cần hoàn thiện mapper trước live integration.
2. Constant reservation là 3, trong khi phản hồi contract cho trần 4.
3. Nhánh lỗi BE chưa quyết toán `TargetedGenerationError.api_calls_count`; mock mặc định của BE đang báo math_verified=true. Owner thay bằng injection thật và xử lý lỗi theo số calls thực tế.

Unit tests độc lập không chứng nhận các transaction/rollback/quota SQL hoặc endpoint hiện tại đã nối AI thật. Chưa chạy live Gemini W3 hoặc DB E2E.

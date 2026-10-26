# AI W2 — triển khai và hợp đồng tích hợp

Cập nhật 24/10/2026. Chủ trì: Trương Thành Đạt. Hùng review; Đạt tự cập nhật và tự merge Docker cho task của mình theo quy trình nhóm. Phần AI được đóng gói để review vào dev; chưa merge.

## Flow đã chốt

Nạp tài liệu → parser trích đề nguồn → giáo viên xác nhận nguồn → sinh Blueprint từng câu → đủ Blueprint mới chọn N=1–4 → sinh candidate kèm đáp án và lời giải trong một request → kiểm tra → giáo viên duyệt hoặc bấm **Sinh lại** → chốt/xuất.

Không gọi Blueprint khi mới ingest. Giáo viên không nhập prompt hoặc sửa Blueprint. Cùng một bộ Blueprint phục vụ N mã và sinh lại. Chưa xây routes, migration DB, SSE, UI hay export W2 trong thay đổi AI này; các bước đó là đầu việc tích hợp của BE/FE.

## Code đã có

| Thành phần | Entry point | Trách nhiệm |
|---|---|---|
| App lifecycle | `app.state.ai_services` (`AIRuntime`) | Khởi tạo lazy, dùng chung gateway, đóng SDK khi shutdown; startup không gọi Gemini |
| Gemini async | `services/ai/gateway.py` | Chọn ngẫu nhiên key khả dụng mỗi attempt, 429 cooldown, 401/403 vô hiệu hóa key và cho retry qua key khác nếu còn, concurrency tối đa 3, deadline và quota hook |
| Blueprint | `BlueprintService.extract_sources` | Kiểm nguồn xác nhận, chuyển schema app sang canonical 0.4.0, extractor của Hùng dùng chung CLI, cache có fingerprint, retry phần thiếu, callback từng câu |
| Sinh đề | `GenerationService.generate_exam_drafts` | N=1–4, 1–20 câu, một request cho candidate+answer+solution mỗi vị trí, tiếp tục từ phần đã lưu, chống trùng giữa mã |
| Sinh lại | `GenerationService.regenerate_question` | Giữ Blueprint, seed mới, chống trùng nguồn/câu cũ; không nhận prompt giáo viên; trả candidate mới để BE thay thế nguyên tử sau thành công |
| Kiểm tra | `CandidateValidator` | Tái sử dụng syntax, logic options, SymPy hiện có; solution key/final answer nhất quán; process timeout cho CAS |
| Output | `models/generation.py` | Nội dung model tách metadata server, solution từng bước và Markdown, kết quả từng vị trí, báo cáo check và batch status |

Client/generator đồng bộ cũ giữ tương thích cho demo/test W1; **không dùng cho routes W2** vì không yêu cầu nguồn xác nhận hoặc Blueprint, không tham gia semaphore/budget async chung. Các import W2 phải dùng runtime/service mới. Không gọi solver legacy riêng sau khi sinh candidate mới.

## BE gọi thế nào

```python
import time
from app.services.ai.gateway import RequestContext
from app.services.blueprint.adapters import prepare_sources
from app.services.blueprint.service import source_fingerprint

# Tại transaction xác nhận nguồn: kiểm ownership/state/security warning trước,
# snapshot các SourceQuestion theo thứ tự cố định, lưu hash và confirmed_at vào DB.
confirmed_hash = source_fingerprint(prepare_sources(sources))

# DB phải cấp budget NGUYÊN TỬ: nếu đã hết, raise GatewayError
# ("REQUEST_BUDGET_EXHAUSTED"). Hook này tính chung extraction/generation/retry.
context = RequestContext(deadline=time.monotonic() + 600,
                         reserve_request=reserve_session_request_in_db)
services = request.app.state.ai_services
results, metadata = await services.blueprints.extract_sources(
    sources, confirmed_source_hash=stored_confirmed_hash, context=context,
    ready=stored_ready_blueprint_results, on_result=persist_blueprint_and_progress)
# on_result(result_dict, metadata_dict): await DB commit từng câu.
# Chỉ mở N khi mọi result['blueprint'] có dữ liệu và result['error'] là None.

# Job generate có deadline riêng; dùng lại CÙNG bộ đếm session bền vững.
context = RequestContext(time.monotonic() + 600, reserve_session_request_in_db)
drafts = await services.generation.generate_exam_drafts(
    sources, stored_blueprints_by_source_id,
    confirmed_source_hash=stored_confirmed_hash, n_versions=2, context=context,
    completed=stored_successful_question_results, on_result=persist_candidate_and_progress)
# on_result(QuestionResult): được gọi cho cả lỗi và thành công mới, không gọi lại cache.
```

`stored_confirmed_hash` phải đọc từ bản xác nhận của server. Hash tự client gửi không chứng minh giáo viên đã xác nhận. `SourceQuestion` chỉ mang text/options/answer/solution; mapping giữ nguyên nội dung, dùng ID có prefix phù hợp schema và từ chối đáp án mơ hồ. Hình ảnh hoặc nội dung ngoài profile Toán trắc nghiệm 4 options không được âm thầm suy đoán từ adapter này.

Lưu **nguyên result record** của Blueprint có `input_fingerprint`, source ID và canonical JSON; ghi model, schema/prompt version và metadata trích xuất cho truy vết. Cache Blueprint gắn source/context/model/schema/prompt; cache candidate gắn source/Blueprint/config/seed/model/prompt. Chỉ đưa những result không lỗi vào `ready`/`completed`; sai fingerprint sẽ bị từ chối trước khi gọi API. Giữ nguyên `base_seed` khi resume. Seed không bảo đảm Gemini tái lập tuyệt đối.

Callback phải commit DB rồi mới trả về; lỗi callback được ném ra và TaskGroup hủy task cùng job. Kết quả đã commit được giữ. MVP cần một worker, khóa/idempotency job trong BE để tránh hai request cùng sinh một session; bộ nhớ Python không thay thế DB sau restart. Phải lưu/reconcile job bị ngắt, không tự đánh dấu hoàn tất. Chống trùng dùng stem/options chuẩn hóa, chưa phát hiện mọi diễn đạt tương đương ngữ nghĩa.

Sinh lại gọi `regenerate_question` với source, Blueprint và candidate **đã lưu**. Với nhiều câu, hash batch được dùng ở `extract_sources`/`generate_exam_drafts`; hash từng câu `source_fingerprint([source_to_item(source)])` được lấy từ cùng snapshot xác nhận khi gọi `generate_question`/`regenerate_question`. BE kiểm candidate thuộc session/version và ownership, lưu candidate mới rồi mới đổi con trỏ; thất bại giữ câu cũ. Không truyền feedback từ UI vào service.

## Kiểm tra được gì

| Check | Ý nghĩa |
|---|---|
| Cấu trúc | Đúng kiểu dữ liệu, bốn options không rỗng, key A–D, LaTeX cân bằng |
| Options | Phát hiện phương án trùng qua chuẩn hóa/CAS trong giới hạn checker |
| Solution consistency | Key lời giải trùng key câu, final answer trùng nội dung option được chọn; không chứng minh các bước giải |
| Answer math | Chỉ xác minh các dạng phương trình mà checker hiện có hỗ trợ; đề tổng quát trả unsupported/unknown |
| Solution reasoning / Blueprint equivalence | Chưa có checker tổng quát; luôn yêu cầu giáo viên review |

Lỗi xác định kích hoạt retry với feedback máy. `unknown/unsupported/inconclusive/timeout` không biến thành pass và không làm retry vô hạn; candidate mang `has_warning=true`, `requires_teacher_review=true`. Không dùng nhãn “đã chứng minh đúng/đạt chuẩn” cho toàn câu chỉ vì một check pass. Kể cả mọi check hỗ trợ pass, vẫn phải giáo viên duyệt trước khi chốt.

Blueprint được code kiểm schema, nguồn bất biến, references, chính sách, profile và mâu thuẫn option ID giữa computed answer/đáp án nguồn đã khai báo; không thêm API “AI kiểm AI” mặc định. Blueprint hợp lệ schema vẫn có thể sai chuyên môn. Nếu hết retry, trả lỗi để giáo viên xem lại nguồn/tạo phiên mới; UI không tự gọi lại vòng lặp. Cần sửa Blueprint nội bộ thì tái tạo có chủ đích và hủy cache các candidate phụ thuộc, không đổi ngầm trong job.

## Quota và lỗi

- Đường thành công: Q request Blueprint + Q×N request candidate kèm solution. Q=20,N=4 là **100 calls**, chưa tính retry; async giúp chờ đồng thời, không giảm số calls. Key pool không đảm bảo tăng quota nếu key chung project/provider limit.
- Mỗi câu candidate tối đa 4 attempts tổng, kể cả transient retry, schema repair và solution repair. Schema lỗi tối đa 2 repair; chỉ sửa solution riêng tối đa 1 lần khi xác định lỗi consistency/LaTeX. Không gọi solution riêng ở đường thành công.
- `RequestBudget` chỉ là counter cục bộ cho test/demo. Production dùng hook DB cho trần batch 250/session, review 30 riêng theo phase sau. Reservation trước dispatch có thể tính một lượt nếu task bị hủy ngay sau cấp lượt; không hoàn tiền tự động gây vượt trần.
- Deadline tuyệt đối dùng chung các lần thử của job; request không vượt phần thời gian còn lại. Process kiểm toán có timeout riêng; khi caller hủy, thread/process đang chạy có thể cần hết timeout ngắn để dọn tài nguyên.
- Các mã đáng xử lý: `SOURCE_NOT_CONFIRMED`, `BLUEPRINT_INVALID`, `BLUEPRINT_PROFILE_INVALID`, `BLUEPRINT_SOURCE_ANSWER_CONFLICT`, `BLUEPRINTS_NOT_READY`, `ERR_CONFIG_CONFLICT`, `RESUME_MISMATCH`, `DUPLICATE_CANDIDATE`, `VALIDATION_FAILED`, `REQUEST_BUDGET_EXHAUSTED`, `JOB_DEADLINE`. Không đưa raw provider error hoặc key vào response/log.
- Batch `generated` nghĩa là đủ candidate để review; `partial_generated` còn thiếu; `failed` chưa có candidate. Đều không có nghĩa giáo viên đã duyệt. Không xuất khi thiếu câu.

## Chạy và nghiệm thu

```powershell
# Từ root repo; dùng Python của môi trường đã cài requirements
python -m pytest backend/tests scripts/blueprint/tests -q
python -m ruff check backend/app scripts/blueprint
python -m mypy backend/app --ignore-missing-imports
cd backend
python scripts/demo_ai_pipeline.py
```

Demo replay nguồn → Blueprint → hai mã → sinh lại một câu, dùng validator thật, xuất `outputs/blueprint/ai-pipeline-demo.json` (ignored); không gọi mạng hoặc tiêu quota Gemini. Fixture chỉ minh họa đổi ngữ cảnh trong variation policy, chưa đánh giá chất lượng nhiều chủ đề từ API thật. Tests có các tình huống đề tổng quát unsupported, đáp án phương trình sai, schema sai, trùng câu, budget/deadline/cancellation, resume và lỗi persistence.

Manifest/lock đã thêm jsonschema/referencing cùng dependencies; backend chứa đủ schema/prompts/contracts. CLI standalone dùng chính lõi này; Docker build context/root ignore và CI có kiểm tra cả hai. Máy hiện không có Docker nên chưa nghiệm thu image/container, và chưa chạy live Gemini. Cần Docker CI xanh cùng live smoke có kiểm soát quota trước khi Đạt tự merge.

### Kết quả host ngày 24/10/2026

- Toàn bộ backend + standalone Blueprint: **300 passed, 1 skipped** (live API opt-in), 78.97 giây. Có một deprecation warning từ Starlette/httpx hiện có.
- Ruff đạt; Mypy đạt **52 source files**; `pip check` đạt; `git diff --check` không có lỗi whitespace.
- Demo offline đạt: một Blueprint, hai candidate và một lần sinh lại, tổng 4 replay requests; xuất JSON đầy đủ báo cáo kiểm tra. YAML CI/Compose parse được; đây không phải bằng chứng container chạy.
- Chưa chạy Docker hoặc Gemini thật; chưa commit/push/merge, chưa áp DB migration.

### Live smoke ngày 24/10/2026 — sau nghiệm thu host

Đạt cho phép gọi Gemini thật khi kiểm thử. Đã chạy `python backend/scripts/demo_ai_live.py --live`, sau đó `--live --resume` để dùng lại Blueprint. Nguồn `x^2-5x+6=0` sinh thành công hai mã `x^2-7x+10=0` và `x^2-7x+12=0`, kèm bốn options, đáp án và solution steps. Bản thành công cần hai request generation từ Blueprint đã lưu; các lượt thử/chẩn đoán trước đó tính riêng. Không thay đổi DB/UI/session thật.

Live test phát hiện endpoint không nhận `additional_properties` khi SDK chuyển Pydantic qua `response_schema`. Đã sửa generator và targeted solution repair sang `response_json_schema=model_json_schema()`; vẫn giữ strict Pydantic validation ở backend, không bỏ extra=forbid. Thêm assertion regression cho cả hai đường schema. Sau sửa: 31 tests generation pipeline đạt, Ruff/Mypy đạt và demo offline vẫn đạt.

Các đáp án dạng tiếng Việt như “2 và 5” khiến checker hiện trả unsupported/inconclusive; không tuyên bố đã chứng minh toán học. Kết quả chi tiết ở `outputs/blueprint/ai-live-demo.md` và JSON cạnh đó (ignored). Script mặc định không chạy API nếu thiếu `--live`; CI/unit tests tiếp tục offline. Docker và flow routes/DB/SSE/UI vẫn chưa nghiệm thu.

### Contract option string với frontend

Options là mảng bốn string theo thứ tự A/B/C/D, frontend gắn nhãn theo index. Văn bản tự nhiên như “2 và 5” hợp lệ, không bắt buộc viết tập nghiệm/CAS. `correct_key` là duy nhất một trong A/B/C/D; frontend dùng key để chọn option, không phân tích ngôn ngữ đáp án. `solution.correct_key` phải bằng `correct_key`, `solution.final_answer` phải khớp nội dung option được trỏ tới sau chuẩn hóa khoảng trắng/LaTeX đã hỗ trợ. Không khớp thì validation failed và retry/repair có giới hạn trước khi bàn giao candidate. Checker không hiểu ý nghĩa toán học của string thì unknown/unsupported, khác với lỗi ánh xạ hoặc cấu trúc. Prompt generation 2.0.1 quy định mapping này; schema cũng có mô tả cho options/key/final_answer. Không tự sửa option chỉ để CAS đọc được.

### Chuẩn bị PR trên dev mới

Baseline đã đồng bộ PR #7 Google login (`bbb7c5e`). Nghiệm thu host trước đóng gói: **304 passed, 1 live opt-in skipped**, Ruff đạt, Mypy 52 files đạt. Các key thật và output demo ở file ignored, không đưa vào Git. Docker engine/CLI không có trên host này; dùng workflow Docker environment của PR để nghiệm thu backend và standalone Blueprint. Chờ Hùng (`benalexx007`) review trước khi merge; các routes/DB/SSE/UI W2 vẫn là phần tích hợp với BE/FE.

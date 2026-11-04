# AI W2 — triển khai và hợp đồng tích hợp

## Bàn giao contract W2 ngày 04/11/2026 — I-B-AI / I-B-POLICY

Đạt phụ trách boundary AI; Quỳnh giữ worker/preflight/persistence adapter,
Duy giữ SQL/RPC/detail, Hùng giữ canonical schema/migration, FE2 giữ API/UI.
Phản hồi đang phối hợp tại [PR30](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6629611144),
theo [yêu cầu của Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6629393300).
Phần dưới là hiện trạng AI và yêu cầu dữ liệu của consumer. Bảng public modes và
clone ghi rõ **proposed**, chưa có bằng chứng các owner đã cùng chấp nhận.
[Plan/bàn giao](tasks/TASK-AI-W2-CONTRACT.md) giữ scope và phần còn chờ.

### 1. Snapshot nguồn và các loại hash

Chỉ dùng nguồn đã xác nhận cùng canonical Blueprint0.4.0 đã publish, không dùng
legacy row/summary làm Blueprint. `get_source_artifacts` của W3 có revision/hash
từng câu; nó chưa phải storage contract cho ordered W2 batch hoặc full results.
W2 cần snapshot bền vững của **toàn bộ** nguồn theo thứ tự xác nhận, đủ Blueprint,
config/job identity và provenance. Không ghép heads ở các revision khác nhau.

Một manifest W2 cần giữ `source_order` (IDs theo question_no duy nhất tăng dần
tại lúc xác nhận), source snapshot đã validate, source/Blueprint revision IDs,
per-question fingerprints, ordered batch confirmation hash, canonical documents
và fingerprint của chúng. Đây là dữ liệu cần persist, **không phải tên cột/RPC mới
đã được SQL owner chốt**. Nếu DB lưu options dạng object A–D, adapter phải tạo list
đúng A/B/C/D; null solution ánh xạ thành chuỗi rỗng theo SourceQuestion.

```python
items = prepare_sources(confirmed_sources_in_saved_order)
batch_hash = source_fingerprint(items)
question_hashes = {
    source.id: source_fingerprint([item])
    for source, item in zip(confirmed_sources_in_saved_order, items, strict=True)
}
```

`source_fingerprint` = SHA256 của UTF-8 `canonical(items)`. `canonical` dùng JSON
`ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False`.
Object keys được sort; **thứ tự array không được sort**. Một item chứa canonical
source cùng extraction context subject/language do `source_to_item` tạo.
Question ID là `q_` +24 ký tự hex đầu của SHA256 UTF-8 SourceQuestion.id; option IDs
giữ A–D, đáp án được resolve bằng helper hiện có. Không tự viết phiên bản hash SQL
từ `jsonb::text` hoặc hash văn bản nguồn đơn lẻ.

Batch1 câu có thể bằng hash câu đó; batch nhiều câu **không** bằng hash bất kỳ câu
nào và không phải hash nối các per-question hashes. Đổi source order làm đổi batch
hash và slot seed. Không dựa vào thứ tự query thiếu ORDER BY khi restart.
Source hash không bao gồm topic/security flag/DB updated_at; revision và policy
readiness vẫn phải được kiểm riêng. Hash không phải chữ ký hoặc bằng chứng người
dùng đã xác nhận. Chỉ so với hash/snapshot persist từ trusted confirmation, không
tính lại hash nguồn vừa sửa rồi coi đó là bản xác nhận cũ.

Fixture hai câu với ordered/reversed batch hash và từng question hash:
[`w2_ai_contract.json`](../backend/tests/fixtures/w2_ai_contract.json), mục `source_hashes`.

### 2. Blueprint cache và provenance

`BlueprintService.input_fingerprint(item)` hash object gồm `item`, `model`, full
`schema` và `prompts` hash; khác source confirmation hash và khác Blueprint body
fingerprint `generation.service.fingerprint(blueprint)`.
`ready[source_id]` phải giữ full extraction result: index, source_question_id,
input_fingerprint, blueprint/error. Cache tái kiểm fingerprint và full canonical
validation trước dùng. Cùng source nhưng model/schema/prompt khác có thể làm cache
không hợp lệ; không chép fingerprint mới lên document cũ để ép cache hit.

Lưu riêng metadata gốc (model, schema_version, prompt_version, prompt_hash và các
trường extractor cung cấp), result và confirmed revision. Callback cache-hit chỉ
có index/source ID/requests0/cachedtrue; merge phần invocation này, không xóa hay
thay thế provenance gốc bằng record rút gọn. `requests` của metadata cache-hit
không có nghĩa extraction gốc chưa từng tiêu quota.

### 3. Variation modes — hiện trạng và đề xuất cần chốt

AI callable **hiện có** nhận canonical dimension IDs, so case-sensitive với
`requirement.variation_policy.allowed_transformations[].dimension` của từng câu.
Schema0.4.0 có `wording`, `names`, `context`, `values`, `representation`,
`option_order`; không có `structural`/`variable_inversion`.
Mode không hỗ trợ trả `ERR_CONFIG_CONFLICT` trước provider.

| Public ID | Canonical dimension / hành vi đề xuất | Trạng thái |
|---|---|---|
| `NUMERICAL`, `parameter_variation` | `values`, chỉ khi mọi Blueprint cho phép values | Proposed alias, chưa nối adapter |
| `context_swap` | `context`, chỉ khi mọi Blueprint cho phép context | Proposed alias, chưa nối adapter |
| Canonical IDs đúng case | Giữ nguyên nếu API công bố và mọi câu cho phép | Callable hiện hỗ trợ; public exposure cần owner xác nhận |
| `STRUCTURAL`, `variable_inversion` | Chưa có mapping an toàn; không đoán thành representation/names | Chờ định nghĩa/fixture hoặc loại khỏi supported modes |
| `[]` / `["NONE"]` | Clone xác định ở orchestration, zero Gemini | Proposed, chưa implement nhánh clone |

Quỳnh/Duy/FE2 cần chốt alias, cách chuẩn hóa NONE và supported_modes; danh sách
khả dụng phải theo giao của các mode được hỗ trợ trên **toàn bộ** nguồn. Lưu public
IDs nguyên trong config và resolved canonical dimensions/mapping version trong
job snapshot; generator nhận dimensions đã resolve. Không lower-case tùy ý,
không biến unsupported ID thành `[]`, không coi thiếu modes là none-only.
`option_order` là dimension hợp lệ nhưng chỉ đảo options vẫn bị anti-duplicate
của generator từ chối; không dùng nó thay đường shuffle xác định.

AI hiện hiểu `[]` là không thêm constraint mode và vẫn sinh câu khác nguồn;
`NONE` chưa có nhánh đặc biệt. Nếu chọn clone theo đề xuất, worker phải tách trước
generator, bảo toàn source text/options/key/solution, shuffle theo ordering và
remap key đồng bộ; không dựng solution steps hay validation proof giả khi nguồn
không có lời giải. `NONE` trộn mode biến thể nên bị từ chối. Clone phải có result
/resume contract riêng do owner orchestration phối hợp chốt; không gọi nó là
QuestionResult do AI sinh. Không bỏ anti-duplicate của generation để làm clone.

### 4. Full QuestionResult và acceptance

Persist nguyên `QuestionResult.model_dump(mode="json")` bên cạnh display projection:

| Cấp | Trường cần giữ |
|---|---|
| Result | version_index (1–4), source_question_id, request_fingerprint, candidate, validation, error_code, attempts |
| Candidate | variant_id, source_question_id, blueprint_fingerprint, seed, question_text, bốn options A–D theo index, correct_key, solution, solution_md, has_warning, requires_teacher_review |
| Solution | correct_key, final_answer là nội dung option được chọn, steps gồm explanation/latex |
| Validation AI | checks đầy đủ và requires_teacher_review; mỗi CheckResult giữ check_name/passed/detail/errors/status/confidence |

Không dùng `to_legacy()` hoặc `variant_text` làm resume record; không thay checks
bằng `CheckResult.to_dict()` (đổi tên field thành `check`) hoặc report aggregator
`passed/status/confidence` mà chưa có adapter do Tâm/AI cùng xác nhận.

- Có candidate, không error, validation tồn tại và không hard failure: có thể lưu
  draft. `unknown/unsupported/inconclusive/timeout` là warning cần giáo viên duyệt,
  không tự biến thành mathematical pass. Kể cả các check hỗ trợ pass vẫn cần review.
- Candidate null, error hoặc hard failure: lưu lỗi/progress/audit, không dựng draft
  từ None và không đưa record vào `completed`. Report còn lại có thể là lần thử
  trước, không đại diện candidate được chấp nhận.
- `attempts` là vòng generation, không phải outbound/quota counter. Repair/extraction
  và commit không chắc chắn cần ledger/hook thực tế; W2 budget250 khác W3 budget30.

Fixture `cases.success` là một generation thành công **có teacher-review warning**,
`warning_timeout` giữ nguyên timeout evidence, `hard_failure` không có draft sau4
attempts, `provider_failure` có validationnull. Chúng dùng provider/check outcomes
được inject và validate_solution thật, không phải chứng cứ CAS hay chất lượng AI.

### 5. Resume và invalidation

Seed slot = `base_seed + version_index * 1000 + source_index`, version bắt đầu1,
source_index bắt đầu0 theo saved order. Request fingerprint hiện hash:

```text
{source: canonical_item, blueprint: full_canonical_document, seed: slot_seed,
 variation_modes: sorted(set(resolved_dimensions)), model: gateway.model,
 prompt_version: generation.prompts.PROMPT_VERSION}
```

Fingerprint này không tự bao gồm job/session/revision ID, n_versions, ordering,
mapping version hoặc validator version. Store phải giữ và đối chiếu các trường
đó trong immutable job config/snapshot; không coi request fingerprint là chữ ký
bảo vệ nội dung result. Cần trusted persisted results, không nhận completed từ FE.

`completed` phải có unique `(version_index, source_question_id)` trong job targets,
candidate source/Blueprint fingerprint/seed khớp expected slot, request fingerprint
khớp model/prompt/modes/source/Blueprint, validation không hard failure, không error
và không trùng candidate cùng source giữa các mã. Generator nay kiểm cả persisted
candidate.seed; Quỳnh đã có check seed ở adapter, hai boundary cùng fail-closed.

Đổi nguồn/order/Blueprint/seed/resolved modes/model/prompt thì phải kiểm lại cache;
không sửa fingerprint record cũ để tái dùng. Đổi public config, N, ordering, mapping
hoặc validator policy cần orchestration chốt snapshot/invalidation tương ứng;
generator không chứng nhận config khác là cùng job chỉ vì vài slot hash vẫn khớp.

Sau restart, load đúng snapshot và full records đã commit, chỉ truyền successful
slots vào completed; retry phần thiếu/thất bại. Cached slots không gọi provider,
không gọi lại on_result. Với slot mới, await callback commit full result + display
projection cùng job fencing trước khi báo progress/SSE. Callback lỗi phải dừng job;
khi mất response commit, reconcile DB trước retry, không tự suy luận chưa lưu.

**Acceptance bàn giao:** các ca hash/order, full result roundtrip, zero-dispatch
completed resume, mismatch model/seed/modes/Blueprint/source, hard failure và public
mode chưa map nằm trong [`test_w2_contract.py`](../backend/tests/ai/test_w2_contract.py).
Các ca partial resume/callback failure/cross-version uniqueness đã có tại
[`test_generation_pipeline.py`](../backend/tests/ai/test_generation_pipeline.py).
Đây là kiểm AI offline, chưa thay W2 SQL/worker/FE/SSE E2E. Handoff gateway outcome
observer vẫn thuộc Quỳnh như comment6601308632; patch này không sửa gateway.

## Lịch sử triển khai và kiểm tra nền (24–26/10/2026)

Cập nhật 26/10/2026. Chủ trì: Trương Thành Đạt. Hùng review; Đạt tự cập nhật và tự merge Docker cho task của mình theo quy trình nhóm. PR #18 đã được Hùng approve và merge vào dev tại 0307b1c; CI và Docker environment đều đạt. Bổ sung chống trùng khi sinh lại trong nhánh tiếp theo; xem biên bản ai-w2-handoff.md.

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
| Sinh lại | `GenerationService.regenerate_question` | Giữ Blueprint, seed mới, chống trùng nguồn/câu cũ và các candidate cùng nguồn được BE truyền qua current_candidates; không nhận prompt giáo viên; trả candidate mới để BE thay thế nguyên tử sau thành công |
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


## Sinh lại không trùng mã đề khác (bổ sung sau review PR #18)

```python
replacement = await services.generation.regenerate_question(
    source, stored_blueprint, previous_candidate,
    confirmed_source_hash=stored_single_source_hash,
    context=review_context, version_index=version_index,
    current_candidates=other_current_candidates_for_same_source,
)
```

BE phải đọc candidate hiện tại của cùng câu nguồn ở tất cả mã đề còn lại trong cùng session; truyền qua `current_candidates`. Service snapshot dữ liệu, kiểm source ID/Blueprint fingerprint trước API, loại trùng theo stem và options chuẩn hóa (không phụ thuộc thứ tự options), retry trong tối đa 4 attempts. Tham số mặc định rỗng giữ tương thích caller cũ, nhưng caller review nhiều mã bắt buộc truyền đủ danh sách. Không phát hiện mọi trùng lặp ngữ nghĩa.

Nếu thất bại, giữ nguyên câu cũ. Khi thành công, BE khóa session hoặc dùng revision/CAS trong transaction, đọc lại các candidate hiện hành và dùng `candidate_identity` kiểm trùng trước khi đổi con trỏ. Nếu revision đã đổi hoặc xuất hiện trùng, rollback và trả conflict; không tự lặp gọi AI vô hạn. Giữ quota reservation bền vững riêng cho review. Service không chứng minh ownership/session membership; route phải kiểm trước khi gọi.

Revert to Source là thao tác riêng, không gọi Gemini và không đi qua regenerate. Chưa triển khai endpoint này; khi triển khai phải ghi provenance và cho phép ngoại lệ câu nguồn có chủ đích, vẫn yêu cầu giáo viên duyệt. Không tự thêm nút này trong phạm vi AI.

Các kết quả kiểm thử 24/10 ở trên là lịch sử. Trạng thái hiện tại: PR #18 đã merge, live smoke đã đạt và Docker CI đã đạt; flow HTTP/DB/SSE/UI W2 vẫn chưa nghiệm thu vì các điểm nối chưa được triển khai trong baseline.

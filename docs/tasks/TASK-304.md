# TASK-304 — Plan và bàn giao: Targeted Regeneration

- Trạng thái: **Draft — plan/input**, ngày 29/10/2026; chưa triển khai code W3.
- Nguồn: W3_ASSIGNMENT.md v2.1 (28/10/2026) và w3.md do Đạt cung cấp ngoài repo. Bản v2.1 chưa có đường dẫn GitHub được xác minh; chờ Duy cung cấp nguồn chung. Không dùng bản W3 cũ làm assignment v2.1.
- Owner: Trương Thành Đạt (`Thanhdat3010`); reviewer: Tâm (`AI-WFox`), **đề xuất**, chưa coi đã nhận review.
- Nhánh: `feat/dat-task-304-targeted-regeneration`, target `dev`; baseline `dc62d3c1d8616316771f8c1dc5a8a1ab56a2ff8c`.
- Workflow v0.1 — proposed; docs commit `506384b`. Xem [WORKFLOW](../review/WORKFLOW.md) và [TEMPLATES](../review/TEMPLATES.md).
- Hạn: tối thứ 3 03/11/2026. Theo assignment: giao schema/mock trưa thứ 6 30/10, hoàn thiện AI thứ 7 31/10. Các ETA cần xác nhận lại trên Conversation.

## Mình cần làm gì?

- Sinh lại duy nhất câu bị reject, giữ source snapshot đã xác nhận và Blueprint canonical 0.4.0; trả candidate, đáp án và lời giải mới trong cùng request ở đường thành công.
- Tái sử dụng `GenerationService.regenerate_question`, gateway async/key pool, schema repair, validator và `candidate_identity`; không tạo generator/gateway song song.
- Nhận source, Blueprint, previous candidate, current same-source peers, context quota/deadline và reason theo contract thống nhất với Duy. IDs/ownership và truy vấn dữ liệu do API Duy quản lý.
- Xử lý AI hoàn toàn ngoài DB transaction; trả object Pydantic để Duy lưu trong transaction ngắn thứ hai. Thất bại giữ câu cũ; BE kiểm revision/uniqueness nguyên tử trước persist.
- Giữ mapping bốn string options theo A–D, correct_key, structured solution, solution_md, validation report và warning/teacher-review flags. Unknown không được coi là chứng minh toán học hoặc đẳng cấu sư phạm.
- Ngoài phạm vi: sinh lại cả đề, sửa Blueprint ngầm, endpoint/DB review lifecycle, stale recovery, migration, UI và export.

## Hiện đã có và dependencies

- Baseline có [generation/service.py](../../backend/app/services/generation/service.py), [prompts.py](../../backend/app/services/generation/prompts.py), [generation models](../../backend/app/models/generation.py), [validator pipeline](../../backend/app/services/validator/pipeline.py) và [contract W2](../ai-w2-integration.md).
- Regeneration hiện loại trùng source/previous/peer; caller phải truyền đủ peers cùng nguồn. Duy vẫn cần kiểm uniqueness lúc commit.
- [PR #19](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/19) (`1308a59`) bổ sung rule fallback; [PR #20](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/20) (`53ec64f`) bổ sung aggregator. Tại lần đọc 29/10, #20 bị GitHub báo conflict với dev; đây là việc owner xử lý trước tích hợp.
- #20 có `ValidationReport` khác report AI hiện tại và API validator đồng bộ. Cần thống nhất adapter và semantics, không import cùng tên rồi coi tương đương; không chặn event loop.
- API confirm trên dev còn lưu fallback Blueprint ±5 khác canonical của generator; tích hợp DB cần Duy/Hùng chốt nơi lưu Blueprint canonical và confirmed hash. Fixture hợp lệ không thay bằng chứng luồng DB thật.
- Các tests đã chạy trên baseline ở lượt trước không chứng nhận implementation W3 chưa viết hoặc các nhánh PR chưa merge.

## File và thứ tự triển khai từ thứ 6

| Lượt / file dự kiến | Mục đích / output | Input / cách kiểm |
|---|---|---|
| 1. Contract trong tài liệu owner thống nhất + fixture/mock | Chốt input/output và lỗi cho Duy | Source snapshot, reason, retry/quota và report mapping |
| 2. `generation/targeted_service.py` nếu cần adapter | Wrapper mỏng dùng GenerationService, không DB connection | Test input/output, preserve input, không nhân logic orchestration |
| 3. `generation/service.py`, `generation/prompts.py` | Reason theo contract trong giới hạn Blueprint; giữ bounded retry/repair và peer exclusion | Test prompt injection, reason trái Blueprint, schema, duplicate |
| 4. Adapter validator trong targeted service hoặc `validator/pipeline.py` | Tích hợp aggregator sau #19/#20; giữ solution consistency và unknown | Tâm xác nhận contract; bounded execution/deadline, không blocking event loop |
| 5. `backend/tests/ai/` + fixture tích hợp Duy | Regression schema/retry/quota/lỗi và success | Provider mock mặc định; live Gemini riêng |
| 6. Contract AI và change_log nếu đổi contract | Ghi quyết định thật và giới hạn | Không tạo contract cạnh tranh hoặc sửa schema owner khác |

## Đầu vào và câu hỏi — giải đáp trên Draft Conversation

| Người/task | Cần xác nhận | Mốc cần / ETA | Phần làm ngay hoặc chờ |
|---|---|---|---|
| Duy / TASK-301 | W2 chỉ button sinh lại, W3 có reason: enum/nội bộ hay text giáo viên? JSON thành công/lỗi, IDs và dữ liệu domain do ai load? | Trước schema/mock trưa 30/10; ETA trả lời TBD | Soạn contract đề xuất; chưa bật prompt giáo viên |
| Duy + Tâm | W3 tối đa 2 retry lỗi toán, W2 trần 4 attempts tổng. Đề xuất giữ trần tổng 4 và tối đa 2 math retries; mọi network/schema/repair tính trong trần và quota review 30 calls. Có đồng ý không? | Trước code retry; TBD | Chưa coi đề xuất là quyết định đã chốt |
| Tâm / #19/#20 | Report/API chuẩn, mapping failed/unknown, thời điểm resolve conflict và merge | Trước tích hợp validator; TBD | Design/test adapter với fixture, chưa nhận đã tích hợp bốn tầng |
| Duy + Hùng / TASK-302 | Blueprint canonical, hash xác nhận, peers/revision và quota reservation hook đọc từ đâu? | Trước API/DB integration; TBD | Dùng source/Blueprint fixture hợp lệ |
| Duy | Nguồn assignment v2.1 trên GitHub và xác nhận ETA schema/full AI | Trong thứ 5; TBD | Giữ nguồn do owner cung cấp, không tự xuất bản assignment thay leader |

Quyết định đã thống nhất: chỉ scope/ownership theo assignment được người dùng cung cấp; các câu hỏi trên **chưa được giải đáp**. Không tự đổi flow reason/retry vì tài liệu mới nhắc đến nó.

## Lịch và bàn giao

- 29/10: Draft chứa plan, trao đổi input/contract, chưa code sản phẩm.
- 30/10: giao schema + mock cho Duy trước trưa theo assignment; code phần đã rõ.
- 31/10: module AI và regression, phối hợp Duy kiểm reject ngoài transaction.
- 01–03/11: sửa theo review, tích hợp validator/DB đúng head và ghi kết quả thực tế. Báo dependency trễ tại PR để Duy điều phối; không tự lùi hạn.
- Output cho Duy: callable/schema/fixture, lỗi an toàn, report và instructions tích hợp; không giao object gần giống mà thiếu mapping.

## Kế hoạch tự kiểm

- Schema/options/key/solution mapping; reason không vượt Blueprint; không mutate source/Blueprint/previous/peers.
- Duplicate source/previous/peer, đảo options, bounded exhaustion; retry/repair và reservation tính từng provider attempt.
- Deadline, quota hết, provider lỗi, cancellation; failed/unknown/unsupported đúng semantics; không biến rule-only thành math proof.
- Regression AI/validator/Blueprint, Ruff/Mypy; CI/Docker trên head cuối. Live smoke tách khỏi unit tests, ghi model/prompt/calls, không log key.
- Integration với Duy: không giữ DB connection lúc gọi Gemini; timeout/cancel/failure giữ câu cũ; revision race/uniqueness và durable quota thuộc kiểm thử BE, không nhận đã kiểm bằng unit AI.

## Bàn giao — trạng thái thực tế

- Đã làm: đọc assignment v2.1, baseline, PR #19/#20 và lập plan M2.
- Đã kiểm: đối chiếu file/interface và dependency qua đọc tĩnh; diff/docs checks của commit plan sẽ ghi ở PR body.
- Chưa làm: implementation W3, test sản phẩm cho task này, live API W3 hoặc DB E2E.
- Chưa có review/chấp nhận. Bước tiếp: chốt các câu hỏi trên Conversation rồi code phần đủ rõ từ 30/10 trên cùng nhánh/PR.

# TASK-302 — Plan và bàn giao

- Phụ trách: Hùng (`benalexx007`); reviewer: Duy (`johannguyen015`, đã được phân công).
- Chế độ: author. Workflow v0.1 **proposed**, docs commit `506384bb312058d8ad2bec759fed8957b19940b3`.
- Nền: `dev` tại `32d7644d0c2d0e6fc8c99234096ee9cc550fbea3`; nhánh `feat/task-302-schema-foundation`.
- Nguồn: [W3 assignment v2.1 trên nhánh TASK-301](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/4db0869f14b455a20a0355d8ffb1070355b45fb5/docs/tasks/W3_ASSIGNMENT.md).
- Contract đầu vào: [review #28](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#pullrequestreview-5720765457), [Duy bàn giao migration/RPC](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#issuecomment-6540968075), [phản hồi cần chốt](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#issuecomment-6544415727).
- Bản code tham chiếu TASK-301: `4db0869f14b455a20a0355d8ffb1070355b45fb5`; chưa merge vào dev.
- Hạn chung: tối 03/11/2026 theo file tuần; mốc TASK-302 cũ là 30/10, không tự coi đã đạt hoặc tự thay ETA. ETA phần còn chờ: cần thống nhất với Duy.

## Phạm vi thực hiện trước

Triển khai nền schema, nâng cấp có transaction và kiểm thử PostgreSQL. Tái sử dụng tên/index tương thích hiện có. Không sao chép repository chưa merge thành một implementation cạnh tranh.

| Thứ tự / file | Mục đích / output | Phụ thuộc | Cách kiểm |
|---|---|---|---|
| 1. `backend/migrations/006_stage3_review_and_shuffle.sql` | Bổ sung các cột đã rõ; backfill không đoán; giữ lịch sử và dữ liệu canonical đã có | Schema dev; 004/005 của PR #32 vẫn chưa merge | Nâng cấp database cũ, chạy lại, rollback khi dữ liệu không hợp lệ |
| 2. `backend/scripts/schema.sql` | Đồng bộ cấu trúc khởi tạo; ghi rõ cần áp dụng migration để có trigger/index bảo vệ | Cùng contract schema | Khởi tạo mới rồi chạy migration |
| 3. `backend/tests/migrations/` | Fixture PostgreSQL biệt lập và kiểm dữ liệu/thao tác thật | Docker PostgreSQL 15; không dùng cloud/secret | Chống canonical overwrite, duplicate current, alias sai, FK/upgrade/rollback |
| 4. `docs/api/review-rpc-contract.md` | Đề xuất chữ ký, input/output, quyền gọi và bảo đảm để owner chốt trước khi code | F02/F06/F07, C01/C02/C03 đang chờ | Đối chiếu từng quyết định trong review |
| 5. `docs/change_log.md` | Ghi phạm vi schema và ngoại lệ/giới hạn đúng trạng thái | Kết quả thực tế | Kiểm diff/link, không ghi đã chấp nhận nếu chưa có |

Tên migration 006 được Duy đề xuất, Hùng chấp nhận có điều kiện kiểm thứ tự; PR #32 đang dùng 004/005. Migration nền không phụ thuộc các RPC generation của #32. Không tự đổi/xóa migration của PR khác.

## Quy tắc dữ liệu

- Canonical bất biến **trong một candidate**. INSERT candidate mới có snapshot riêng; UPDATE display fields khi shuffle không được sửa canonical. Không sửa canonical lịch sử để che lỗi sinh trước đó.
- Nếu canonical lịch sử thiếu thì dừng, không backfill từ display kể cả `is_finalized=false`: dữ liệu có thể từng được shuffle rồi invalidated. Snapshot đã đủ nhưng solution NULL vẫn được giữ nguyên.
- Giữ index `idx_single_current_version_question`: chỉ bảo đảm **tối đa một** current/slot. Bảo đảm còn đúng một sau replacement cần RPC, chưa được tuyên bố ở phase này.
- Giữ các cột `answer_keys.question_no/correct_option` để tương thích; thêm `display_no/display_correct_key` cùng nghĩa và đồng bộ hai cách ghi. Không đổi nội dung hoặc chọn một phía khi hai giá trị xung đột.
- Backfill canonical slot của answer key chỉ khi ánh xạ `(version_id, display_no)` tới đúng một current candidate và đã có canonical slot. Không suy ra từ vị trí hiển thị nếu thiếu ánh xạ.
- Không tự deduplicate, xóa lịch sử, suy đoán actor, đổi khóa ngoại xóa lịch sử hoặc sửa dữ liệu đã shuffle. Dữ liệu mâu thuẫn phải làm migration dừng và rollback, báo cách điều tra.
- `review_logs.session_id` có thể suy ra qua candidate → version → session. Actor lịch sử theo quyết định đã chốt bên dưới; không tự điền owner thành người đã thao tác.
- Không đổi policy RLS/ACL hiện có trong phase nền; cần kiểm riêng khi chốt RPC và dạng log có/không có candidate. Không tuyên bố đã kiểm Supabase thật.

## Contract RPC đề xuất — chưa phải interface đã chốt

Nguồn interface đề xuất: [review-rpc-contract.md](../api/review-rpc-contract.md).
File này giữ tên/chữ ký RPC, kiểu dữ liệu, payload TASK-304, quyền JWT/worker,
idempotency, hiệu ứng nguyên tử và mã lỗi để owner đối chiếu trên Draft PR.
Plan chỉ giữ phạm vi, phụ thuộc và trạng thái quyết định; không tạo bản contract thứ hai.

Chưa triển khai RPC hoặc ledger operation/attempt. Không giữ transaction DB trong
lúc gọi AI. Không code các policy phụ thuộc trước khi chốt; wrapper sẽ tích hợp
trên ReviewRepository hiện có của Duy, không tạo repository cạnh tranh.

## Input còn chờ và người xác nhận

| ID / cần ai | Lựa chọn Hùng đề xuất | Trạng thái |
|---|---|---|
| F02/C03 — Duy | TASK-302 làm toàn bộ mutation DB nguyên tử; Duy giữ service/API, cùng chốt RPC signatures | Duy đồng ý hướng RPC; phạm vi đầy đủ và signatures chưa xác nhận |
| F07 — Duy + Đạt | 30 attempts kể cả fail, tối đa 4/operation, permit bền vững trước mỗi dispatch; giữ charge khi crash chưa biết có dispatch hay không | Chưa xác nhận contract đầy đủ; cách đếm bảo thủ khi crash là lựa chọn đề xuất, không nhận đo chính xác provider calls |
| C01 — Duy | DB recalculation readiness; lifecycle gọi; đủ toàn bộ slot mới `reviewed` | Phản hồi trước dùng sai ID, chưa coi là chốt |
| C02 — Duy | Revert candidate đầu; reject binary; một regeneration/session | Chưa xác nhận; không tự chọn Model A/B |
| Canonical/display — Duy + Tâm | list 4 strings A/B/C/D; canonical slot ổn định, display mapping tách biệt | Cơ sở từ W3/#24; tích hợp shuffle thật còn chờ |
| Actor lịch sử — Hùng | Giữ NULL cho lịch sử không biết actor; bắt buộc actor cho log mới | Người phụ trách xác nhận phương án 1 ngày 31/10/2026 trong phiên làm việc này; chưa đồng nghĩa Duy đã đọc hoặc GitHub approve |

## Quyết định actor lịch sử — đã chốt ngày 31/10/2026

Người phụ trách chọn: **giữ `user_id=NULL` cho log lịch sử không biết actor; log mới bắt buộc có `user_id` hợp lệ**. Đây là ngoại lệ có chủ đích so với `user_id NOT NULL` cho toàn bộ dữ liệu trong đặc tả W3, nhằm giữ đúng lịch sử thay vì gán nhầm người thao tác.

- NULL chỉ có nghĩa **không biết actor của dòng đã tồn tại trước khi áp constraint**. Không có nghĩa owner session, actor hệ thống, user hiện tại hoặc UUID mặc định. Không tự backfill actor từ các giá trị đó.
- Migration thêm `ck_review_logs_actor_required CHECK (user_id IS NOT NULL) NOT VALID`. PostgreSQL không quét lại để loại lịch sử NULL, nhưng kiểm mọi INSERT và UPDATE sau đó. Không dùng mốc `created_at` hoặc cờ do client gửi để nhận diện lịch sử.
- INSERT thiếu actor bị từ chối, kể cả gửi `created_at` rất cũ. Actor không tồn tại bị FK từ chối. RPC/service sau này vẫn phải lấy actor từ caller đã xác thực; constraint này không chứng minh actor là người đang gọi.
- UPDATE một log lịch sử vẫn NULL cũng bị từ chối, kể cả chỉ sửa reason. Giữ nguyên dòng đó nếu không có bằng chứng actor; chỉ bổ sung actor khi đã xác minh được người thao tác thật. Không lấy actor của người bảo trì làm actor lịch sử.
- Cột vẫn nullable trong metadata. Trên database nâng cấp có lịch sử NULL, constraint sẽ ở trạng thái `convalidated=false` theo thiết kế, không phải lỗi migration. Chạy lại migration không được tự VALIDATE hoặc SET NOT NULL.
- Schema khởi tạo mới tạo CHECK bình thường vì chưa có lịch sử. Fresh init và upgrade cùng bắt buộc actor cho các thao tác ghi mới.
- Chỉ có thể VALIDATE/đổi sang NOT NULL sau một đợt backfill có bằng chứng đã xử lý hết lịch sử NULL. Quyết định hiện tại không cho phép tự làm bước đó, xóa lịch sử hoặc bịa actor để đạt constraint.
- SQL có cả comment cạnh implementation và `COMMENT ON` để người kiểm tra database thấy được ý nghĩa ngoại lệ. Thay đổi này cần được thông báo trong gói bàn giao TASK-302, không coi quyết định nội bộ đã tự đồng bộ với đồng nghiệp.

## Kiểm tra và bàn giao

- Dùng PostgreSQL container tạm, không publish port, không mount `.env`, không gọi Gemini/Supabase, dọn container khi xong.
- Kiểm upgrade có dữ liệu, fresh init, replay; giữ IDs/count/history/quota/canonical; các trường hợp ambiguity/duplicate phải rollback toàn bộ.
- Kiểm transaction replacement/concurrency/recovery/quota chỉ sau khi RPC được triển khai. Không dùng kết quả schema tests để nhận các bảo đảm lifecycle này.
- Output nền cho Duy/Tâm: migration, cấu trúc canonical/answer keys và test tái lập. Không tuyên bố TASK-302 Done khi repository/RPC còn chờ.
- Bàn giao qua Draft PR vào dev; giữ Draft khi contract/RPC còn chờ, không chỉnh description PR/issue đã có.
- Kết quả đã chạy và giới hạn nằm bên dưới; trạng thái push/CI/review thực tế được ghi trên PR.

## Kết quả triển khai cục bộ — 31/10/2026

- Đã viết migration nền 006, cập nhật schema khởi tạo, giữ nguyên index current, thêm index regeneration và stale lookup, backfill audit session, thêm FK audit thiếu trên database chuẩn bị dở.
- Đã thêm trigger bảo vệ canonical và bridge `question_no/correct_option` ↔ `display_no/display_correct_key`. Giữ nguyên dữ liệu/lịch sử cũ; actor đã có constraint theo quyết định ngoại lệ lịch sử ở trên.
- PostgreSQL 15: **15/15 pass, 0 skip** sau cập nhật policy actor, bằng `RUN_POSTGRES_MIGRATION_TESTS=1`, `DOCKER_BIN=<Docker CLI>`, `python -m unittest discover -s backend/tests/migrations -v`. Runner dùng Python stdlib có sẵn trên máy để điều khiển container, không cài package host.
- Docker backend: `ruff check --no-cache backend/app scripts/blueprint backend/tests/migrations/test_stage3_schema.py` **pass**; `mypy backend/app --ignore-missing-imports --cache-dir /tmp/mypy-cache` **pass, 62 source files**.
- Các ca có bằng chứng: upgrade/replay dữ liệu cũ, fresh full schema + migration, display shuffle không sửa canonical, candidate mới snapshot riêng, chống hai current/slot, hai kiểu ghi answer key, rollback khi duplicate/alias mâu thuẫn/thiếu hoặc mơ hồ mapping, từ chối canonical thiếu và actor FK sai.
- Policy actor đã kiểm: giữ NULL lịch sử qua replay; fresh schema chặn log thiếu actor ngay cả trước migration; log mới thiếu actor/giả ngày cũ bị chặn; actor hợp lệ được ghi nhưng không thể xóa thành NULL; UPDATE lịch sử NULL cần actor đã xác minh. Ruff cho test runner sau thay đổi cũng pass.
- Container PostgreSQL tạm đã được dọn. Không test cloud/Gemini, không deploy migration, không chạy full product suite, không nhận các RPC pending đã hoạt động.
- **TASK-302 chưa hoàn tất.** Quyết định actor lịch sử đã chốt; contract RPC/C01/C02/F07 vẫn chờ trước khi triển khai phần phụ thuộc. File SQL hiện là nền để review, chưa là gói deploy hoàn thiện.
- Gói bàn giao gồm schema, migration, tests và contract RPC đề xuất. Cần Duy xác nhận lifecycle/interface, Duy–Đạt xác nhận budget, Duy–Tâm xác nhận mapping/invalidation trước khi làm phần phụ thuộc. Quyết định sẽ được hỏi tại đúng mục trên Conversation của Draft PR.

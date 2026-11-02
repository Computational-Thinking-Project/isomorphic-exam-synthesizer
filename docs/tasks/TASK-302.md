# TASK-302 — Plan và bàn giao

- Phụ trách: Hùng (`benalexx007`); reviewer: Duy (`johannguyen015`, đã được phân công).
- Chế độ: author. Workflow v0.1 **proposed**, docs commit `506384bb312058d8ad2bec759fed8957b19940b3`.
- Nền ban đầu: `dev` tại `32d7644d0c2d0e6fc8c99234096ee9cc550fbea3`; nhánh `feat/task-302-schema-foundation`. Đã đồng bộ dev `ada2963` ngày 02/11, không có conflict Git.
- Nguồn: [W3 assignment v2.1 trên nhánh TASK-301](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/4db0869f14b455a20a0355d8ffb1070355b45fb5/docs/tasks/W3_ASSIGNMENT.md).
- Contract đầu vào: [review #28](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#pullrequestreview-5720765457), [Duy bàn giao migration/RPC](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#issuecomment-6540968075), [phản hồi cần chốt](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#issuecomment-6544415727).
- Bản code đối chiếu cập nhật 02/11: TASK-301 `a4dd03bb24d8122256fcc687940b29d78ae0861a`, TASK-305 `8e04613d481891bca25bba0d0ab50187788fafb4`, TASK-304 `a8f61d57976181472eae355d869362b2c80261d4`, dev `ada29633b721765a3e0eaae5f8accfb908e48bd8` (đã nhận TASK-303/306). Đây là đối chiếu interface, chưa phải tích hợp caller/AI/shuffle E2E.
- Hạn chung: tối 03/11/2026 theo file tuần; mốc TASK-302 cũ là 30/10, không tự coi đã đạt hoặc tự thay ETA. ETA phần còn chờ: cần thống nhất với Duy.

## Phạm vi triển khai và bàn giao

Triển khai schema, ledger và các RPC review nguyên tử, kiểm trên PostgreSQL thật rồi bàn giao cho ReviewRepository hiện có của Duy. Giữ cùng PR #36 và migration 006; không tạo repository cạnh tranh, không sửa nhánh tác giả khác, không deploy cloud hoặc sửa description PR/issue đã có.

| Thứ tự / file | Mục đích / output | Phụ thuộc | Cách kiểm |
|---|---|---|---|
| 1. `backend/migrations/006_stage3_review_and_shuffle.sql` | Schema; ledger operation/attempt/action; RPC reserve/acquire/complete/fail/recover/accept/revert/progress | Quyết định Duy và interface Đạt bên dưới; 004/005 của #32 vẫn riêng | Upgrade/replay, rollback, ACL, hai connection tranh permit/current/recovery |
| 2. `backend/scripts/schema.sql` | Đồng bộ cấu trúc khởi tạo; ghi rõ cần áp dụng migration để có trigger/index bảo vệ | Cùng contract schema | Khởi tạo mới rồi chạy migration |
| 3. `backend/tests/migrations/` | Giữ 15 ca schema; thêm suite ledger/RPC trên connection DB độc lập | Docker PostgreSQL 15; không dùng cloud/secret | Concurrency, replay, lost response, expiry/recovery, audit/invalidation failure, ACL và actor |
| 4. `docs/api/review-rpc-contract.md` | Interface thực tế, callback strict và accounting khi mất response; policy đã chốt/caller pending | F02/F06/F07, C01/C02/C03 và phản hồi owner | Đối chiếu code/test và link quyết định, không nhận đã tích hợp chỉ vì interface khớp |
| 5. `docs/change_log.md` | Ghi phạm vi schema và ngoại lệ/giới hạn đúng trạng thái | Kết quả thực tế | Kiểm diff/link, không ghi đã chấp nhận nếu chưa có |

Quyết định owner migration ngày 02/11: giữ `006_stage3_review_and_shuffle.sql`, không tạo thêm 006 dưới tên khác. Thứ tự tích hợp 004/005 (#32) → 006 (#36) → 007 (#33). TASK-302 là nguồn duy nhất cho ledger/tám RPC review; Duy xử lý phần trùng trong 008 ở #28. Nếu 008 đã áp dụng vào DB dùng chung, phải báo trạng thái để Hùng cung cấp chuyển đổi an toàn; không tự xóa lịch sử/quota hoặc sửa migration đã áp dụng. Migration nền không phụ thuộc các RPC generation của #32; không sửa nhánh tác giả khác.

## Plan tiếp tục — 02/11/2026

Nguồn phối hợp: [comment tiếng Anh đã đăng trên #36](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6568374582). Đây là quyết định migration và yêu cầu đầu vào; chưa phải bàn giao code đã kiểm.

| Thứ tự | Việc thực hiện / file | Output / cách kiểm | Phụ thuộc |
|---|---|---|---|
| 1 | Cập nhật plan/contract/change log theo head mới và phản hồi owner | Ghi nhận xác nhận Tâm, actor/thứ tự của Duy; tách SQL trùng 008 khỏi interface chuẩn | Đã có căn cứ và quyền quyết định migration |
| 2 | Hoàn thiện 006 và test RPC | Giữ khóa session trước mutation; serialize global receipt IDs, giữ snapshot source khi acquire/complete; từ chối ledger không tương thích bằng lỗi rõ ràng và rollback | Không cần chờ mapper AI |
| 3 | Kiểm PostgreSQL thật và static checks trên code cuối, đối chiếu dev mới | Upgrade/replay, multi-connection quota/global-ID races, recovery/late worker, approval interleaving, rollback và ACL; Ruff/mypy theo CI | Docker PostgreSQL 15, không secret/cloud |
| 4 | Commit/push cùng #36 và comment M3 bàn giao | Commit, lệnh/kết quả thực tế, contract và pending owners; giữ Draft | Checks phần TASK-302 đạt; caller/E2E chưa tự coi Done |
| 5 | Tích hợp caller/AI/shuffle sau phản hồi | Duy nối wrappers; Duy/Đạt chốt canonical blueprint/hash; Đạt/Tâm phối hợp kiểm các điểm nối | Chờ input được tag ở comment, không tự code thay owner |

Chưa có xác nhận 008 đã áp dụng vào database nào; không xây dựng script chuyển đổi dữ liệu theo giả định. Guard trong 006 chỉ dừng an toàn nếu gặp ledger không tương thích và yêu cầu điều tra.

## Quy tắc dữ liệu

- Canonical bất biến **trong một candidate**. INSERT candidate mới có snapshot riêng; UPDATE display fields khi shuffle không được sửa canonical. Không sửa canonical lịch sử để che lỗi sinh trước đó.
- Nếu canonical lịch sử thiếu thì dừng, không backfill từ display kể cả `is_finalized=false`: dữ liệu có thể từng được shuffle rồi invalidated. Snapshot đã đủ nhưng solution NULL vẫn được giữ nguyên.
- Giữ index `idx_single_current_version_question`: bản thân index chỉ bảo đảm **tối đa một** current/slot. RPC complete/revert bảo toàn current bằng transaction; lỗi demote/insert/audit/invalidation rollback chung.
- Giữ các cột `answer_keys.question_no/correct_option` để tương thích; thêm `display_no/display_correct_key` cùng nghĩa và đồng bộ hai cách ghi. Không đổi nội dung hoặc chọn một phía khi hai giá trị xung đột.
- Backfill canonical slot của answer key chỉ khi ánh xạ `(version_id, display_no)` tới đúng một current candidate và đã có canonical slot. Không suy ra từ vị trí hiển thị nếu thiếu ánh xạ.
- Không tự deduplicate, xóa lịch sử, suy đoán actor, đổi khóa ngoại xóa lịch sử hoặc sửa dữ liệu đã shuffle. Dữ liệu mâu thuẫn phải làm migration dừng và rollback, báo cách điều tra.
- `review_logs.session_id` có thể suy ra qua candidate → version → session. Actor lịch sử theo quyết định đã chốt bên dưới; không tự điền owner thành người đã thao tác.
- Không thay policy RLS của bảng sản phẩm cũ; thêm private ledger có RLS/ACL và quyền EXECUTE riêng JWT/worker cho RPC. Đã kiểm role PostgreSQL cục bộ; không nhận đã kiểm JWT/RLS Supabase thật.

## Contract RPC và nguồn quyết định

Nguồn interface: [review-rpc-contract.md](../api/review-rpc-contract.md). Đã triển khai ledger và tám entry point trong migration 006; plan chỉ giữ scope, trạng thái và bàn giao, không sao chép interface.

- [Duy xác nhận ranh giới/auth/quota/lifecycle/invalidation](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6546291626).
- [Đạt xác nhận callback và phân biệt acknowledged count/ledger](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551270882), [bàn giao adapter tại a8f61d5](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551386372).
- TASK-301 `a4dd03b` đã gọi acquire RPC, nhưng parser vẫn coercion và complete vẫn ghi nhiều request riêng; SQL 008 trùng/incompatible với 006. [Review mới của Đạt](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#pullrequestreview-5731619370) còn Request changes. Không nhận caller đã hoàn tất lifecycle atomic chỉ vì đã có acquire wrapper.

Mất response sau khi DB commit vẫn giữ charge. Complete thành công đối chiếu count với ledger; fail/recover không nhận count adapter và không từ chối recovery chỉ vì adapter nhận 0 acknowledged trong khi DB đã grant 1. Không hoàn cố định 4 lượt.

## Trạng thái đầu vào và người nhận bàn giao

| ID / cần ai | Contract / cách thực hiện | Trạng thái |
|---|---|---|
| F02/C03 — Duy | TASK-302 làm mutation DB; Duy dùng JWT/worker clients gọi RPC trên repository hiện có | Boundary/auth đã xác nhận; RPC đã code, caller chuyển từ direct writes sang RPC còn chờ. Duy ước lượng wrapper trong 24h sau khi nhận RPC, chưa là bằng chứng đã giao/tích hợp |
| F07 — Duy + Đạt | 30/session, 4/operation, grant trước mỗi dispatch; ledger quyết toán, giữ uncertain charge | Policy đã chốt; callback Đạt đã giao. RPC đã code; wrapper/adapter E2E còn chờ |
| C01 — Duy | Recalculate trong mutation; đủ expected slots và không active operation mới reviewed; progress chỉ đọc | Đã xác nhận và triển khai DB; SQL 007 đã khóa session, còn đồng bộ operation/readiness, fail-closed khi config thiếu/mơ hồ và kiểm tích hợp |
| C02 — Duy | Revert candidate đầu; reject binary; Model A một regeneration/session | Đã xác nhận và triển khai RPC; không tự đổi Model B |
| Canonical/display — Duy + Tâm (`AI-WFox`) | Giữ mapping/alias #24, canonical bất biến; invalidation toàn phiên khi replacement | [Tâm đã xác nhận](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6555305930), TASK-303/306 đã merge; còn shuffle persistence/E2E |
| Source-to-AI snapshot — Duy (`johannguyen015`) + Đạt (`Thanhdat3010`) | RPC freeze raw DB rows; Duy xác định storage/mapper canonical/hash, Đạt xác nhận input/fail-closed | Baseline chưa lưu canonical document/hash đúng TASK-304. Không dựng hash ở reject hoặc tự mở rộng source-storage; input đang chờ trên comment 02/11 |
| Thứ tự migration — Hùng quyết định, Duy tích hợp | Giữ 006 của PR này, sau 004/005 và trước 007; loại implementation 008 trùng | [Duy đã xác nhận thứ tự](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6567937686); owner giữ tên file hiện có. Chờ Duy báo 008 đã được áp dụng ở đâu chưa |
| Actor lịch sử — Hùng + Duy | Giữ NULL cho lịch sử không biết actor; bắt buộc actor cho log mới | Owner chốt 31/10, [Duy đã đồng thuận](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6567937686); chưa phải GitHub approve |

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
- Kiểm RPC bằng các connection psql độc lập. Approval interleaving chứng minh RPC đợi/recheck khóa session; không chứng minh writer TASK-305 đã có transaction tương ứng.
- Output cho Duy/Đạt/Tâm: migration/RPC, contract, tests tái lập. Duy hoàn thiện RPC wrappers và bỏ local refund/direct lifecycle writes; Đạt giữ callback/fail-closed; Tâm phối hợp kiểm persistence/shuffle theo policy đã xác nhận. Không tự sửa nhánh các owner này.
- Bàn giao qua Draft PR vào dev; giữ Draft khi contract/RPC còn chờ, không chỉnh description PR/issue đã có.
- Kết quả đã chạy và giới hạn nằm bên dưới; trạng thái push/CI/review thực tế được ghi trên PR.

## Mốc nền schema đã kiểm — 31/10/2026

- Đã viết migration nền 006, cập nhật schema khởi tạo, giữ nguyên index current, thêm index regeneration và stale lookup, backfill audit session, thêm FK audit thiếu trên database chuẩn bị dở.
- Đã thêm trigger bảo vệ canonical và bridge `question_no/correct_option` ↔ `display_no/display_correct_key`. Giữ nguyên dữ liệu/lịch sử cũ; actor đã có constraint theo quyết định ngoại lệ lịch sử ở trên.
- PostgreSQL 15: **15/15 pass, 0 skip** sau cập nhật policy actor, bằng `RUN_POSTGRES_MIGRATION_TESTS=1`, `DOCKER_BIN=<Docker CLI>`, `python -m unittest discover -s backend/tests/migrations -v`. Runner dùng Python stdlib có sẵn trên máy để điều khiển container, không cài package host.
- Docker backend: `ruff check --no-cache backend/app scripts/blueprint backend/tests/migrations/test_stage3_schema.py` **pass**; `mypy backend/app --ignore-missing-imports --cache-dir /tmp/mypy-cache` **pass, 62 source files**.
- Các ca có bằng chứng: upgrade/replay dữ liệu cũ, fresh full schema + migration, display shuffle không sửa canonical, candidate mới snapshot riêng, chống hai current/slot, hai kiểu ghi answer key, rollback khi duplicate/alias mâu thuẫn/thiếu hoặc mơ hồ mapping, từ chối canonical thiếu và actor FK sai.
- Policy actor đã kiểm: giữ NULL lịch sử qua replay; fresh schema chặn log thiếu actor ngay cả trước migration; log mới thiếu actor/giả ngày cũ bị chặn; actor hợp lệ được ghi nhưng không thể xóa thành NULL; UPDATE lịch sử NULL cần actor đã xác minh. Ruff cho test runner sau thay đổi cũng pass.
- Container PostgreSQL tạm đã được dọn. Không test cloud/Gemini, không deploy migration, không chạy full product suite, không nhận các RPC pending đã hoạt động.
- Đây là bằng chứng phase nền tại thời điểm đó; không gán 15 schema tests thành kiểm RPC.

## Gói ledger/RPC — 01/11/2026

- Đã triển khai private operation/attempt/action ledger, ACL/RLS của ledger và tám RPC; actor worker lấy từ operation creator, không nhận user_id do caller gửi. Replay không reset quota, receipts hoặc lịch sử.
- Reserve không trừ quota; grant/replay/denial bền vững qua connection mới; complete/audit/invalidation và fail/recover/revert có transaction. Recovery dùng lease 180s, không refund; worker cũ không được thay operation mới.
- Tests PostgreSQL và static checks cuối được ghi theo kết quả thực tế trong PR handoff; runner phải bật opt-in. Pytest mặc định skip DB tests, không nhận đó là PostgreSQL pass.
- **Chưa nhận TASK-302 Done/Ready toàn luồng.** Còn caller RPC thực tế, confirmed canonical/hash mapper, TASK-305 approval compatibility, xử lý 008 trùng và tích hợp Supabase/AI/shuffle E2E. Policy Tâm/thứ tự migration đã có phản hồi; PR giữ Draft, không deploy/approve/merge hoặc đóng finding #28 thay người kiểm.

## Kiểm bản cuối — 02/11/2026

- PostgreSQL 15 thật: `RUN_POSTGRES_MIGRATION_TESTS=1`, `DOCKER_BIN=<Docker CLI>`, `python -m unittest discover -s backend/tests/migrations -v` → **45/45 pass, 0 skip, 109.656s** (16 schema + 29 RPC). Hai suite dùng container tạm riêng; đã kiểm chúng được dọn sau khi chạy.
- Đã kiểm thêm global operation/attempt/action ID race giữa hai session trả domain conflict, source/blueprint row lock khi reserve/acquire/complete, và guard ledger 008 không tương thích giữ nguyên receipts/quota. Các ca rollback fault, replay sau connection mới, conservative lost-response accounting, recovery/late worker và approval-first interleaving đều pass.
- Sau đồng bộ dev: `ruff check --no-cache backend/app scripts/blueprint backend/tests/migrations` → **pass** với pyproject của repo; `mypy backend/app --ignore-missing-imports --cache-dir /tmp/mypy-cache` → **pass, 68 source files**. `git diff --check` không có lỗi khoảng trắng.
- Image kiểm thử riêng `task302-backend-check:20261102` build từ Dockerfile hiện tại với `pip --require-hashes` theo lockfile; `pip check` pass. Trong image mới, Ruff/mypy tiếp tục pass với kết quả trên.
- `python -m pytest backend/tests scripts/blueprint/tests -q -p no:cacheprovider` → **685 passed, 46 skipped, 21 warnings, 63.04s**. 46 skip gồm 45 PostgreSQL opt-in đã chạy riêng và 1 live API opt-in; không gọi Gemini. Dùng network none, mock Supabase env và chỉ mount code/config/test/schema, không mount `.env`.
- CI của commit bàn giao phải đọc theo head mới sau push; không dùng CI xanh của head schema cũ để đại diện cho ledger/RPC mới.
- Giới hạn: PostgreSQL roles/JWT claims là bootstrap cục bộ; chưa kiểm Supabase thật, mapper/adapter/caller/shuffle E2E, live Gemini hoặc triển khai SQL 007/008 trên DB dùng chung. Chưa có GitHub approve/nghiệm thu của Duy cho gói này.

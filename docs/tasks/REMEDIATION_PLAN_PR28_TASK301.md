# TASK-301 / PR #28 — kế hoạch hoàn thiện hiện hành

Ngày cập nhật:04/11/2026. Author: Duy. Workflow v0.1 **proposed**, tài liệu quy
trình tham chiếu506384b. Xuất phát68b375f; bản tích hợp8b0a20f, base dev8bdc3b1.
Kế hoạch8 bước đã được Duy yêu cầu triển khai. Producer thuộc301, xử lý nền.
Chỉ sửa nhánh feat/duy-task-301-review-lifecycle-api. Được kiểm/commit/push và
bàn giao review; không tự sửa nhánh người khác, deploy cloud, Approve hay merge.

Interface duy nhất: [review-rpc-contract](../api/review-rpc-contract.md). Các
plan cũ là lịch sử trong Git, không phải contract song song. Không còn chờ giao
owner producer hoặc hỏi lại lựa chọn background. PR giữ non-Draft theo Duy;
trạng thái này không đồng nghĩa đã đủ điều kiện merge.

## Thứ tự phụ thuộc và trạng thái

| Bước | Việc thực hiện | Trạng thái / điều kiện khép lại |
|---|---|---|
|1|Một plan hiện hành, một authority, giữ nguyên finding IDs|Đã cập nhật; cần owner #36 đối chiếu/adopt interface, không suy đồng ý từ im lặng|
|2|F11: owner lookup thuần đọc trước adapter; replay completed/active/failed/recovered; fresh thiếu adapter không mutation|Đã publish674d3aa; tiếp tục hồi quy trên head cuối và Đạt xác minh|
|3|Bootstrap source confirmation độc lập legacy Blueprint/003; exact source, actor/time/revision/hash/audit nguyên tử|Đã publish4bc71e4; không tạo fallback canonical, giữ Stage1 với canonical pending|
|4|Nối public confirm-source, producer nền, claim/lease/status/retry/resume|Đã publish8b0a20f; lease lớn hơn extraction deadline, giữ publication thành công; restart cần trigger retry xác thực|
|5|C03: SQL frozen-v1 từ persisted heads; canonical current/peers; acquire/complete kiểm revision đã reserve|Đã publish8b0a20f; không nới validator legacy, cần kiểm hồi quy SQL/CI cuối|
|6|Lookup/replay → adapter → session guards → recovery → reserve; settlement/readiness cùng snapshot|Đã publish8b0a20f; source invalidation làm ready=false nhưng không chặn fail/recovery; #33 dùng cùng parent lock|
|7|HTTP→producer→PostgreSQL→frozen→adapter thật/provider giả→permit→complete; chạy ma trận lỗi/CI|Luồng tích hợp đã thực thi đạt; final-head full SQL, Pipeline và Docker phải được ghi kết quả thật vào PR|
|8|M5 C03/F11, owner #36 adopt, Đạt xác minh, handoff #33|Chưa được xem là reviewer verified/Approve. Applicable checks và ít nhất1 GitHub Approve theo CONTRIBUTING trước merge|

## Phân loại nguyên nhân và bản sửa

Các A/B dưới đây giữ liên hệ với phân tích cũ; đây là trạng thái triển khai hiện
hành, không phải danh sách yêu cầu sửa lại những ca đã verified.

| Mã / nguyên nhân | Cách xử lý và bằng chứng cần giữ | Trạng thái |
|---|---|---|
|F11 — guard adapter trước durable replay|Owner-only lookup kiểm session/question/operation/actor; không reserve/recover/audit/quota. Completed đọc candidate, active/failed/recovered không gọi AI|Author claimed_fixed, chờ Đạt|
|Bootstrap — confirmation gọi003 đòi Blueprint sẵn có|Worker confirmation mới trên cùng public endpoint; không cần legacy row/003; rollback audit+revision+status cùng TX|Đã triển khai/kiểm SQL|
|C03/A01/A02/B01/B02 — legacy rows không phải canonical frozen input|Producer301 lưu validated input/fingerprint/revision; BlueprintService tạo full canonical; SQL reserve xuất v1 từ heads; strict validator trước permit|Author claimed_fixed, reviewer pending_verification (Đồng bộ authority d94f138, 111/111 PostgreSQL passed)|
|A03/A05/A06 — lỗi sau reserve/mất response để operation treo hoặc settle sai ID|Giữ operation ID gốc, bounded same-ID reconciliation, sanitized fail codes, shield cancellation, postcommit read không rollback|Caller và SQL fault/race tests; giữ hồi quy|
|A04 — replay bị xem như action mới|Phân nhánh typed receipt, không dùng worker clock để hết hạn historical outcome; active replay luôn không dispatch|Đã triển khai; hồi quy F11|
|A07/F10 — dựng report/solution/count thay dữ liệu thiếu|Strict candidate/report/checks/count validation; giữ evidence thật, không clamp/default validation|Đạt đã verified tại68b375f; không sửa lại|
|A08/F02/F07/F09 — fallback mutation và lẫn owner/worker|RPC-only lifecycle, typed AttemptPermit, worker thiếu503; không GRANT ledger để né ACL|Đã triển khai; giữ test ACL/permit|
|F06 — discovery đoán operation ID/SELECT private ledger|Dùng worker review_recover_session, DB lease và cùng parent lock|Đạt đã verified discovery cũ; race/settlement hồi quy riêng|
|A09/B03/C01 — progress IDs khác snapshot counts|SQL cùng snapshot trả IDs/counts/readiness; thiếu canonical thì ready=false; không đoán mẫu số từ remaining rows|Đã triển khai; owner #36 adopt|
|A10 — Accept/Revert retry thiếu key|Optional UUID Idempotency-Key truyền xuyên suốt receipt; replay trước edit guard|Đã triển khai và test|
|A11 — docs mô tả checkpoint khác code|Một plan này và một authority, PR body/M5 ghi exact commit và phân biệt author/reviewer/Approve|Cập nhật cùng bản bàn giao|
|A12 — dependency đọc cấu hình AI sai field|Dùng Settings.get_gemini_api_keys() thực tế, kể cả numbered keys|Đã sửa trước8b0a20f; giữ4 ca hồi quy|
|Producer — hai trigger/lỗi từng câu/process chết|Durable claim trước extraction; publication check job/revision/lease; từng câu thành công giữ lại, resume bỏ qua ready|SQL race/partial failure/cancellation/restart tests|

## Ma trận kiểm và vị trí thực hiện

| Nhóm | Ca bắt buộc / nơi kiểm |
|---|---|
|F11|Completed offline, active/failed/recovered replay, fresh offline không mutation, sai binding; test_review_flow/receipts, test_review_rpc_http và SQL lookup|
|Bootstrap|Không legacy row/003, exact source, missing answers, stale timestamp, concurrent edit/confirm, revision/audit rollback; test_source_artifacts|
|Background|Hai claim/trigger, lỗi1 câu giữ câu đã publish, cancellation/restart/resume, lease expired và stale worker publication/fail; test_source_artifacts|
|Frozen-v1|JSON RPC qua validator/adapter thật; pending/absent heads, revision mismatch, source edit+revert, canonical options/key/solution không lẫn display; test_review_rpcs + integration|
|Settlement|Timeout/cancel, reserve/complete/fail response mất, postcommit read, recovery trước/sau complete, same-question retry; caller tests + SQL race/fault tests|
|DB invariants|Một current/slot,30/session,4/operation, ACL, audit/invalidation atomic, không refund; test_stage3_schema/test_review_rpcs|
|Approval/#33|Ghim d7a3d3f; thật004/005→006→007 trên legacy/fresh, approval/recovery cùng parent lock; test_review_migration_chain|
|Public API|Auth/ownership, error mapping, pending/ready/retry; test_confirm_source, test_review_rpc_http; HTTP→actual BlueprintService/GenerationService/TargetedRegenerator→SQL trong test_source_artifacts|
|Final|Ruff, mypy, backend/Blueprint full execution ở CI Pipeline, Docker job; SQL opt-in phải chạy riêng, không dùng skipped/collect làm pass|

Lệnh SQL: RUN_POSTGRES_MIGRATION_TESTS=1, RUN_UPSTREAM_MIGRATION_TESTS=1,
python -m unittest discover -s backend/tests/migrations -v. Container PostgreSQL15
cô lập, không ports/mounts/cloud, dọn sau test. Chi tiết [SQL README](../../backend/tests/migrations/README.md).
Full async/API suite dùng CI Linux; không nhận broad local async pass khi chưa chạy.

## Gate bên ngoài còn lại và giới hạn

1. Hùng đối chiếu/adopt extension cùng006/authority trên #36: source storage,
   lease/status RPCs, frozen-v1, lookup/progress IDs và R1. Không có blocker thiếu
   owner triển khai; đây là acceptance của phần dùng chung.
2. Đạt kiểm đúng head cuối C03/F11/bootstrap, giữ F10/F06 discovery verified;
   author self-check không đóng thay finding hoặc GitHub Approve.
3. #33 phải nhận cùng phiên bản review/contract/migration, không đưa caller cũ
   trở lại. Không tự sửa nhánh305 trong task này; conflict #33 là công việc tích hợp
   của nhánh đó. PR28 kiểm mergeable và CI trên head cuối của chính nó.
4. Test fake gateway đủ cho phạm vi này. JWT verification/Supabase deployed RLS/
   PostgREST pool/live Gemini và cloud rollout chưa được chứng nhận bởi container
   SQL hoặc injected-auth HTTP. Không tuyên bố đã deploy hay hết mọi bug.

Background ở đây là tác vụ trong process với claim/status bền vững. Sau restart,
nguồn vẫn confirmed và tiến độ vẫn trong DB; người dùng gọi retry sau lease hết
hạn để tiếp tục. Không hứa tự chạy lại nếu không có trigger. GET giữ thuần đọc.

Kết quả thực thi và exact final commit được ghi ở PR body/M5, không lấy số test
tại checkpoint cũ làm bằng chứng cho code mới. Hoàn thành code/author checks
không thay acceptance #36, review hoặc điều kiện merge.

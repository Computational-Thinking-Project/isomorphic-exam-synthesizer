# W4-MVP-08 — Private export: plan và bàn giao

## Publication checkpoint 15/11/2026

- Đồng bộ `dev@c2ee9fd` (PR59, migration021/PR68) qua dependency07 tại
  `d84263d` đã push. Merge local08 tại `60bd5f0`; khôi phục nguyên các bản sửa
  Q09/HTTP đã được review14/11, conflict chỉ là dòng README liệt kê migrations.
- PostgreSQL15 disposable + exporter/HTTP: **276 passed, 2 skipped, 21 subtests**
  trên snapshot có021. Kiểm cả fresh chain019→020→021 và populated upgrade
  đã có021 rồi bổ sung020. Blob fake/SQL transport; không chứng minh shared DB
  đã apply hoặc công cụ migration môi trường đích chấp nhận backfill theo số.
- Trên cùng snapshot code: Ruff app/scripts và các tests thay đổi pass; mypy
  pass127 files; API+exporter **676 passed, 1 skipped**, sáu warning deprecated
  API như lượt trước. Các skip/giới hạn live vẫn giữ nguyên. Diff check pass.
- Giữ020 là migration export do Hùng bàn giao; không sửa/đổi số021 hoặc migration
  Q01 tiếp theo của BE2. Duy/Đạt cần đối chiếu approved/applied manifest và cách
  triển khai đúng môi trường, không tự suy trạng thái DB từ Git merge.
- Kết quả CI, head đã push, phản hồi Q09 và đầu vào OPS được công bố qua M3/M5
  tại PR63. PR vẫn Draft, runtime mặc định tắt; không sửa PR/issue descriptions.
  Gói14/11 bên dưới là bằng chứng lịch sử; review agent không thay Duy xác minh.

## Checkpoint 14/11/2026 — phần đã chốt

- Đồng bộ local với `dev@4c2d424` qua nhánh07 tại `2976c07`; merge local vào08
  tại `3f67706`. Không push/merge GitHub trong lượt này. Duy/Tâm đã Approve07
  tại `8e2941a`, không tự coi approval đó xác minh bản đồng bộ mới.
- [Philip đã xác nhận Q10](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6825618302):
  synchronous POST trong worker thread,200 ready/202 live claim; GET read-only;
  POST download-url, TTL3600/no-store; reconcile GET trước retry khi mất response.
  Không còn chờ lựa chọn sync/async. Bảng input bên dưới giữ trạng thái hiện hành.
- Sửa hai finding trong [Q09 re-review của Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6831140214):
  chỉ structured `NoSuchKey`/404 chứng minh object mất; bucket/access/generic404
  giữ checkpoint. RPC020 checkpoint trả persisted receipt cùng token; adapter
  yêu cầu exact token/receipt trước upload, fail closed khi ack sai/mất.
- Đã code ba routes/worker runtime theo Q10. Mặc định
  `PRIVATE_EXPORT_ENABLED=false`; không tạo privileged client khi thiếu cấu hình
  timeout/bucket/credentials. Client privileged sống/đóng trong worker; không
  đóng theo request disconnect. Không tự apply migration, đổi ACL hay cấp access.
- OPS đã bàn giao [inventory một phần](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6840314999):
  chưa có actual private flag/ACL, MIME/size limits, applied manifest và tổng
  runtime/proxy/stop-grace budget. Timeout từng IO không chứng minh lease900s đủ.
  Các mục đó còn chặn bật luồng thật/nghiệm thu, không chặn code độc lập.
- Những mục evidence dưới đây có ngày12/11 là lịch sử, không thay kết quả của
  bản14/11. Kết quả và review độc lập mới sẽ được ghi riêng sau kiểm thực tế.

### Author checks 14/11

- Docker local image `export07-backend-check:20261112`, Python3.11; network-none
  cho unit/API, internal network PostgreSQL15 disposable cho SQL, không secrets,
  cloud hoặc Docker socket. Runtime enable chỉ được giả lập trong tests.
- `ruff check backend/app scripts/blueprint` và các test Python thay đổi: pass;
  `mypy backend/app --ignore-missing-imports`: pass127 source files. Ruff format
  cho các file Python mới/sửa: pass; `git diff --check`: pass ở diff riêng08.
- `pytest backend/tests/api backend/tests/exporter -q --tb=short`:
  **676 passed, 1 skipped**. Một skip XeLaTeX; sáu warning Starlette/FastAPI
  deprecated API hiện có. Có tests vòng đời/tách client và timeout7/11 giả lập.
- SQL transport harness trên chain002–019→020, chạy exporter và
  `test_export_snapshot_pg.py`, `test_private_export_pg.py`:
  **274 passed, 2 skipped, 21 subtests**. Snapshot lượt này trước hai unit tests
  vòng đời client cuối cùng (hai tests đó thuộc lượt676 trên). Skip XeLaTeX và
  PR49 parity chưa tích hợp; warning anyio harness + Starlette TestClient.
- Regression mới: bucket404 giữ checkpoint/build count; durable checkpoint sai
  ack dừng trước upload và recover sau expiry; HTTP→service→SQL owner/foreign,
  repeated POST, GET không build/sign; request body không được giả owner/revision;
  upload mất response không complete/double upload, download trước ready409.
- Đây là **author checks**. Hai Q09 findings hiện **author claimed_fixed**,
  chưa được Duy xác minh lại. Chưa GitHub Approve,
  chưa push code mới, chưa live DB/Storage/JWT/PostgREST hay Golden E2E.

### Review độc lập 14/11 — gpt-6.1-sol high

Đúng một subagent review read-only toàn bộ08 và tích hợp07 tại local `3f67706`
cộng working-tree/untracked code mới; không sửa source hoặc đăng GitHub.
**Không có finding mới đủ bằng chứng**; hai bản sửa Q09 đạt các combined-service
probes, chưa thay xác minh của Duy/GitHub Approve.

- Tự chạy fresh PostgreSQL15 harness: **276 passed, 2 skipped, 21 subtests**,
  bao gồm hai unit tests vòng đời client cuối cùng. Skip/warning như author run.
- **29 independent unexpected probes passed**:12 body variants;5 method guards;
  query không giả owner/revision; actual SDK service headers, rpc7s/storage11s,
  immutable multipart ZIP upload và signerTTL3600; cancellation giữ client tới
  worker kết thúc;5 lỗi Storage qua SDK thật giữ checkpoint;4 malformed RPC acks
  qua SDK thật trả outcome-unknown và không upload/mutation tiếp.
- SDK hiện cài có thể bỏ JSON `code` mới và giữ legacy `error` trong exception.
  Khi không có object-specific code đáng tin, recovery giữ checkpoint thay vì
  tự restart; không nhận đã nhận diện object mất trong trường hợp đó. Giới hạn
  này cần đối chiếu trên Storage đích, không dùng free-text404 để đoán missing.
- Report/probes/logs local tại `scratch/review-w408-http-unexpected/`; không
  commit raw artifacts. Chỉ module docstring private_service sửa trong lúc review
  để ghi Q10 đã accepted; reviewer đã đối chiếu, không đổi hành vi sau tests.
- Shared applied manifest, private ACL/limits, live JWT/PostgREST/Storage, expiry
  và production budget vẫn UNRUN; không có quyền deploy phát sinh từ review.

- Author: Hùng; Duy review DB/RPC theo [phân công W4](W4_TASK_DETAIL.md).
- Workflow v0.1 proposed + INPUT-20261109; baseline tài liệu `dev@21887c1`.
- Nhánh: `feat/w4-mvp-08-private-export`; [Draft PR #63](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63); kế thừa `dev` và dependency 07 tại
  `305f38d` (PR #58 chưa merge). Diff riêng 08 tính từ commit này; PR về `dev`
  phải ghi rõ phần 07 đi kèm cho đến khi #58 merge. Không sửa description PR cũ.
- Hạn trong phân công: 11/11 18:00, đã qua; không tự tạo hạn thay thế.

## Scope và thứ tự

1. Plan/nhánh riêng; giữ nguyên contract snapshot đã được Duy chốt trên #58.
2. Code phần độc lập: snapshot đã duyệt → compiler/bundler → manifest/checksums;
   orchestration qua interface ledger/Storage, kiểm checksum sau upload,
   không complete/exported khi compile/upload/verification thất bại.
3. Sau khi code phần đủ đầu vào: gửi lựa chọn cụ thể cho Duy, Đạt, Philip.
  Q09/Q10 đã có quyết định; OPS bàn giao một phần. Interface hiện hành theo bảng dưới.
4. Nối RPC, HTTP và Storage thật sau khi nhận/đối chiếu input; kiểm retry,
   concurrent requests, recovery, owner auth, private ACL, signed URL 3600s.
   Sau phần thực hiện được, gọi reviewer `gpt-6.1-sol high`, sửa finding có căn cứ.

Không thay producer/shuffle, không viết UI, không tự cấp quyền cloud, không merge.
Không đưa implementation ledger RAM vào production; không giả kết quả Storage/DB thật.

## Đầu vào — nguồn tổng hợp duy nhất

| ID / yêu cầu | Cung cấp → nhận | Mục đích / điều kiện đủ dùng | Trạng thái / bằng chứng | Còn thiếu / bước tiếp |
|---|---|---|---|---|
| I08-07 | Hùng/07 → Hùng/08 | ApprovedExportSnapshot từ user RLS, revision SHA256, immutable approved data | Accepted/Integrated local; Duy/Tâm Approve07 tại `8e2941a`; đồng bộ dev local `2976c07`, chưa merge GitHub | Kiểm lại bản đồng bộ và integrated parity khi PR49 merge; synchronous reader+builder đã nối trong worker |
| I08-COMPILER | Compiler/bundler hiện có → 08 | build_compiled_bundle, BundleArtifact; đầy đủ 2N+1 PDF và TeX/MD | Accepted/Integrated cục bộ tại `45b2e5b`: snapshot 07 → Typst thật → ZIP/manifest, 5 PDF cho 2 mã; không phải deployed proof | Thêm manifest tại lớp 08; không đổi output contract của bundler W3 |
| I08-Q09 | Hùng đề xuất; Duy review/đồng bộ DB → 08 | Claim/fencing/complete atomic, metadata, recovery; migration slot và RPC contract | Decided/Delivered/Accepted theo [quyết định Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6819045971); Integrated cục bộ: RPC020 + recovery, PostgreSQL15 thực. Không phải shared DB applied hay PR approval | 020 chưa thấy dùng ở PR mở khi kiểm; 019 thuộc PR61. Lease900s còn provisional chờ OPS budget; final manifest/live proof và review implementation vẫn cần |
| I08-11S | Đạt (`Thanhdat3010`), Duy điều phối → 08 | Private bucket interface/limits, safe secret channel, authorized environment | Duy yêu cầu backend-only export writes: 020 đã code targeted policy và kiểm trên PostgreSQL giả lập Storage schema. Bucket/access/limits/timeout chưa được OPS giao; [Issue #53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53) vẫn thiếu access | Đạt review policy/approved applied manifest và giao bucket private, MIME/size limits, test access/IO budget. Không tự áp DDL hay sửa cloud; ETA chưa xác nhận |
| I08-Q10 | Hùng đề xuất; Philip (`philip-kkk`) → 09/08 | POST export, GET status, POST download URL, bounded polling/errors | Decided/Delivered/Accepted theo [Philip](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6825618302); routes/runtime Integrated local theo contract | Không hỏi lại sync/async; OPS budget/live validation còn riêng. Mặc định tắt runtime |

Input Delivered không tự là Accepted/Integrated. Không lặp lại quyết định đã có:
export thiếu solution fail-closed; snapshot revision SHA256, không dùng updated_at.

## Kế hoạch tự kiểm

- Compiler thật + ZIP đọc được; manifest đúng SHA256/size của từng entry,
  giữ nguyên display questions/options/keys/solutions từ snapshot 07.
- Upload lỗi hoặc checksum sai không gọi complete; compile lỗi không upload;
  hoàn tất DB mất response không xóa object hay đánh failed mù.
- Retry ready không compile/upload lại; pending không chiếm claim của worker khác;
  signer chỉ chạy sau owner authorization và ready metadata, TTL đúng 3600.
- Fake ports kiểm orchestration, không thay proof DB locking/RPC/PostgREST/Storage ACL.
- Real RPC concurrency/recovery và real Storage/URL TTL sẽ ghi UNRUN nếu thiếu input.
- Ruff, mypy, pytest exporter trong Docker local; không chạy Gemini cho export.

## Bàn giao

Đã code pipeline độc lập trong `private_service.py`, port trong `private_models.py`,
SDK adapter `private_storage.py`, manifest wrapper `manifest_bundle.py`;
[contract đề xuất](../api/private-export-contract.md). Có checkpoint expected
path/hash/size trước upload; mất response không đánh failed/xóa object mù.

Đã kiểm Docker local image `export07-backend-check:20261112`, network none,
dummy env, không mount `.env` thật: `ruff check backend/app scripts/blueprint`
PASS; `mypy backend/app --ignore-missing-imports` PASS 101 files;
`pytest backend/tests/exporter -q --tb=short` **206 passed, 1 skipped** (XeLaTeX
chưa có). Có Typst thật cho snapshot 07 3 câu × 2 mã, PDF magic và manifest
checksum; fake ledger/Storage cho concurrent requests, retry, lỗi và lost response;
SDK fake kiểm upsert=false và TTL argument 3600. Không phải RPC/ACL/TTL live proof.

Đợt tiếp theo sau quyết định Duy: đã thêm `020_private_export_ledger.sql`,
`SupabaseExportLedger`, recovery outcome/port `restart` và kiểm PostgreSQL thực.
Explicit POST/service export tiếp quản token mới nhưng giữ path/hash/size object
cũ; chỉ restart khi SDK404 hoặc checksum mismatch. Unknown transport không giải
phóng claim/xóa object/build lại mù. GET/status vẫn read-only.

Kiểm Docker PostgreSQL15 qua SQL transport độc lập (thay HTTP, không thay engine):
`pytest backend/tests/exporter backend/tests/migrations/test_export_snapshot_pg.py
backend/tests/migrations/test_private_export_pg.py -q --tb=short` đạt
**244 passed, 2 skipped, 21 subtests**. Hai skip: XeLaTeX chưa có và parity với
repository PR49 chưa nằm ở dev; warning anyio do harness import trước pytest.
Các tests mới kiểm populated upgrade018→020/fresh chain, concurrent claims,
expiry/takeover, stale mutation, checkpoint/upload/complete/restart response loss,
old-object recovery không rebuild, receipt/identity rejection, lifecycle rollback,
ready-object loss không tự đổi artifact, actual-role ACL/RLS và Storage policy có
thêm permissive policy. Blob store vẫn fake, không coi là live Supabase proof.
Lệnh chuẩn backend dependencies + Docker và giới hạn ở
[migration tests README](../../backend/tests/migrations/README.md).
Ruff `backend/app scripts/blueprint` PASS; mypy `backend/app --ignore-missing-imports`
PASS 102 files. Probe riêng tại `d255663` với candidate019 từ PR61@`9fda6fd568a992ca64172cbcb1047c0ac41f6f31`
đặt trước020 đạt **17 passed, 9 subtests** trên PostgreSQL15 thật, cho historical
approved fixture/fresh DDL. Không commit candidate019 vào nhánh08; không phải
W4 producer/config→generate E2E hay final approved migration manifest.

Chưa có HTTP adapter, chưa nối Storage thật, chưa áp migration dùng chung. Chưa
GitHub Approve hay task Done. Bước 4 còn cần I08-11S/I08-Q10 và final migration
manifest. Output giao Philip/09, Hùng/12, Quỳnh/13, Đạt/21s; ETA tích hợp thật phụ
thuộc input Requested. Không coi thời gian chờ là owner đồng ý. Review độc lập
tiếp theo phải kiểm cả unexpected behavior trên toàn bộ08, bao gồm code đã có.

Đã đăng [yêu cầu đầu vào trên PR #63](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6814634477)
sau khi push phần code độc lập `45b2e5b`, tag Duy cho I08-Q09, Đạt + Duy cho
I08-11S, Philip + Duy/Đạt cho I08-Q10. Q09 đã có quyết định như bảng; hai mục
I08-11S/Q10 vẫn Requested. Đã kiểm sự hiện diện cấu hình Supabase local mà không
in giá trị: chỉ placeholder, chưa có môi trường để chạy bước 4 thật.

Review độc lập **đợt đầu**: `gpt-6.1-sol`, reasoning `high`, đọc code 08 tại
`45b2e5b` so với dependency `305f38d`, không sửa code/đăng GitHub. Reviewer tự chạy
Docker network-none và xác nhận **206 passed, 1 skipped**; không có actionable
finding trong scope đã triển khai. Đây không phải GitHub Approve hay xác minh
RPC/HTTP/recovery/Storage ACL/URL expiry thật. Bản report chi tiết giữ local tại
`scratch/review08-independent/review.md`, không commit artifact review/test thô.

Review độc lập **đợt recovery/unexpected behavior**, đúng model `gpt-6.1-sol high`:
review toàn bộ08 tại `d255663`, tự chạy lại full suite **244 passed, 2 skipped,
21 subtests** và thêm **4 unexpected probes PASS**: stale worker upload muộn;
lease hết lúc verify với worker khác complete; GET expired checkpoint không đổi
ledger; malformed receipts/ready replay sau expiry. Không actionable finding.

Một tác động policy được thu hẹp trước push: giữ owner SELECT như quyền cũ,
chỉ chặn mutation đúng Q09. SQL/regression/contract sửa tại `3221ea4`; reviewer
kiểm riêng delta và tự chạy lại **244 passed, 2 skipped, 21 subtests**, thêm
**1 policy probe PASS** cho owner/foreign/anon, move raw↔export, restrictive
guards dưới extra permissive policy, raw/source UPDATE/DELETE vẫn hoạt động.
Không actionable finding trên final code. Báo cáo/lệnh/log chi tiết local:
`scratch/review08-recovery-independent/review.md`. Không coi review agent là
GitHub Approve hoặc proof Storage/HTTP/JWT/deployment thật.

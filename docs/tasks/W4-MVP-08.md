# W4-MVP-08 — Private export: plan và bàn giao

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
   Q09 đã có quyết định; Q10/OPS vẫn chờ. Interface hiện hành theo bảng dưới.
4. Nối RPC, HTTP và Storage thật sau khi nhận/đối chiếu input; kiểm retry,
   concurrent requests, recovery, owner auth, private ACL, signed URL 3600s.
   Sau phần thực hiện được, gọi reviewer `gpt-6.1-sol high`, sửa finding có căn cứ.

Không thay producer/shuffle, không viết UI, không tự cấp quyền cloud, không merge.
Không đưa implementation ledger RAM vào production; không giả kết quả Storage/DB thật.

## Đầu vào — nguồn tổng hợp duy nhất

| ID / yêu cầu | Cung cấp → nhận | Mục đích / điều kiện đủ dùng | Trạng thái / bằng chứng | Còn thiếu / bước tiếp |
|---|---|---|---|---|
| I08-07 | Hùng/07 → Hùng/08 | ApprovedExportSnapshot từ user RLS, revision SHA256, immutable approved data | Delivered tại `305f38d`, [#58](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/58); Duy đã chốt read/revision, chưa GitHub Approve/merge | Nối synchronous reader+builder trong worker thread, không truyền coroutine vào to_thread |
| I08-COMPILER | Compiler/bundler hiện có → 08 | build_compiled_bundle, BundleArtifact; đầy đủ 2N+1 PDF và TeX/MD | Accepted/Integrated cục bộ tại `45b2e5b`: snapshot 07 → Typst thật → ZIP/manifest, 5 PDF cho 2 mã; không phải deployed proof | Thêm manifest tại lớp 08; không đổi output contract của bundler W3 |
| I08-Q09 | Hùng đề xuất; Duy review/đồng bộ DB → 08 | Claim/fencing/complete atomic, metadata, recovery; migration slot và RPC contract | Decided/Delivered/Accepted theo [quyết định Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6819045971); Integrated cục bộ: RPC020 + recovery, PostgreSQL15 thực. Không phải shared DB applied hay PR approval | 020 chưa thấy dùng ở PR mở khi kiểm; 019 thuộc PR61. Lease900s còn provisional chờ OPS budget; final manifest/live proof và review implementation vẫn cần |
| I08-11S | Đạt (`Thanhdat3010`), Duy điều phối → 08 | Private bucket interface/limits, safe secret channel, authorized environment | Duy yêu cầu backend-only export writes: 020 đã code targeted policy và kiểm trên PostgreSQL giả lập Storage schema. Bucket/access/limits/timeout chưa được OPS giao; [Issue #53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53) vẫn thiếu access | Đạt review policy/approved applied manifest và giao bucket private, MIME/size limits, test access/IO budget. Không tự áp DDL hay sửa cloud; ETA chưa xác nhận |
| I08-Q10 | Hùng đề xuất; Philip (`philip-kkk`) → 09/08 | POST export, GET status, POST download URL, bounded polling/errors | Requested theo Q10; [#60](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/60) xác nhận chưa có contract export hoàn chỉnh | Đề xuất cụ thể sau code độc lập; không bật public routes chưa chốt |

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

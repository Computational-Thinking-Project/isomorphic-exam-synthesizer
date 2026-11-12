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
3. Sau khi code phần đủ đầu vào: gửi lựa chọn cụ thể cho Duy, Đạt, Philip để
   chốt Q09/Q10. Các interface thử nghiệm không phải contract đã được họ nhận.
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
| I08-Q09 | Hùng đề xuất; Duy review/đồng bộ DB → 08 | Claim/fencing/complete atomic, metadata, recovery; migration slot và RPC contract | Requested theo W4 Q09, chưa có quyết định bổ sung trong trao đổi đã đọc | Code orchestration qua port trước; sau đó gửi lựa chọn lease/token + immutable object, upload thành công/DB mất response cần read-back; ETA provider chưa xác nhận |
| I08-11S | Đạt (`Thanhdat3010`), Duy điều phối → 08 | Private bucket interface/limits, safe secret channel, authorized environment | Schema có bucket exam-export-bundles và session-first path policy; không là applied/live proof. [Issue #53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53) vẫn thiếu access | Không tự đổi ACL hay dùng service-role để bỏ owner check. Đạt xác nhận bucket/path/limits + test access; ETA chưa xác nhận |
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

Chưa có concrete ledger/RPC/migration/HTTP adapter; chưa nối Storage thật. Chưa
GitHub Approve/acceptance hay task Done. Bước 4 còn cần I08-Q09/I08-11S/I08-Q10;
không tự thay lựa chọn hoặc cấu hình cloud khi các owner chưa trả lời. Output giao
Philip/09, Hùng/12, Quỳnh/13, Đạt/21s; ETA tích hợp thật phụ thuộc input Requested.
Không coi hạn đã qua hoặc hết thời gian chờ là owner đồng ý. Reviewer độc lập sẽ
kiểm scope code đã có, không được diễn giải các input thiếu thành proof đã hoàn tất.

Đã đăng [yêu cầu đầu vào trên PR #63](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6814634477)
sau khi push phần code độc lập `45b2e5b`, tag Duy cho I08-Q09, Đạt + Duy cho
I08-11S, Philip + Duy/Đạt cho I08-Q10. Các mục vẫn Requested, chưa có câu trả lời
được consumer chấp nhận. Đã kiểm sự hiện diện cấu hình Supabase local mà không
in giá trị: chỉ placeholder, chưa có môi trường để chạy bước 4 thật.

Review độc lập theo yêu cầu: `gpt-6.1-sol`, reasoning `high`, đọc code 08 tại
`45b2e5b` so với dependency `305f38d`, không sửa code/đăng GitHub. Reviewer tự chạy
Docker network-none và xác nhận **206 passed, 1 skipped**; không có actionable
finding trong scope đã triển khai. Đây không phải GitHub Approve hay xác minh
RPC/HTTP/recovery/Storage ACL/URL expiry thật. Bản report chi tiết giữ local tại
`scratch/review08-independent/review.md`, không commit artifact review/test thô.

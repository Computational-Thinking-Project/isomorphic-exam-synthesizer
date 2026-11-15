# W4-MVP-12 — Security/negative baseline và regression tích hợp

## Phạm vi và kế hoạch (M2)

- Owner: Hùng. Chế độ author; workflow v0.1 proposed + INPUT-20261109.
- Nguồn: [phân công W4](W4_ASSIGNMENT.md), [chi tiết task 12](W4_TASK_DETAIL.md#w4-mvp-12--securitynegative-smoke--frozen-head-regression).
- Baseline code: `f74e34c74cfbc2b24f7fb28da02fad02458f896e` + các thay đổi test TASK-12 trong working tree; ngày kiểm 15/11/2026 (UTC+7).
- Nhánh `test/w4-mvp-12-security-baseline` tách từ head task08 trên, **có dependency PR58/PR63 chưa merge**. Draft PR tạm base vào `feat/w4-mvp-08-private-export` để diff chỉ chứa TASK-12; chuyển base về `dev` sau khi dependency merge và kiểm lại phạm vi ảnh hưởng. Không trình bày kết quả này như kiểm `dev` hay deployed head.
- Được làm: thêm test, chạy local/DB tạm, lập bằng chứng và danh sách đầu vào. Không thay product contract, migration, cloud hoặc description PR/issue.
- Thứ tự: đối chiếu coverage → bổ sung khoảng trống HTTP/DB đã có contract → chạy baseline → khi có môi trường, chạy integrated smoke → rerun trên frozen head và giao task13/21.
- Các mốc 12/11 baseline và 14/11 regression trong phân công đã qua; bản này không tự đổi deadline hoặc nhận G0/G1 đã đạt.

## Đầu vào và bàn giao

Bảng này là nơi tổng hợp input TASK-12. Các ID dưới đây là ID theo dõi local mới, **chưa phải yêu cầu đã gửi/được người cung cấp nhận**. ETA chưa được xác nhận.

| ID | Người cung cấp / nhận | Điều kiện đủ dùng | Hiện có / còn thiếu |
|---|---|---|---|
| I-W412-01 | Duy + Đạt → Hùng | Candidate/frozen deployed SHA, manifest migrations thực áp, config/runtime export và môi trường được phép test | Có code local; chưa xác nhận deployment cho baseline này. ETA TBD. Cần trước integrated run. |
| I-W412-02 | Đạt hỗ trợ OPS, Duy auth/RPC → Hùng | Hai tài khoản kiểm soát được, session riêng của A/B; approved/unapproved/partial fixtures; private bucket và cách gây lỗi an toàn | Local có synthetic identities và DB tạm; chưa có bộ input live được xác nhận cho run này. ETA TBD. |
| I-W412-03 | Quỳnh SSE, Hùng consumer | Đường SSE triển khai, fixture reconnect/retry/fallback và kết quả kỳ vọng theo contract | Có tests SSE local; kiểm qua proxy/browser và producer thật còn thiếu. ETA TBD. |
| Q13 / Q20 (ID gốc W4_TASK_DETAIL) | Hùng + Duy + Đạt; người nghiệm thu theo phân công | Chốt nơi lưu, quyền xem, retention/consent và hình thức evidence sanitized | Đề xuất của Hùng: commit matrix/tóm tắt và testcase synthetic; raw log/video chỉ ở nơi hạn chế quyền do OPS xác nhận; không lưu token/link còn hạn. Chưa coi đề xuất là quyết định chung. |

Đầu ra: matrix + kết quả/giới hạn cho Quỳnh (13) và Đạt (21); Duy review auth/RPC. Baseline cần reviewer độc lập ký theo DoD; tự kiểm của author chưa thay xác minh/Approve.

## Ma trận baseline

`PASS local` chỉ áp dụng cho lớp được ghi. `BLOCKED live` là thiếu đầu vào để chạy tích hợp, không phải lỗi product đã tái hiện. Mỗi dòng vẫn phải rerun trên frozen head trước nghiệm thu. Test HTTP dùng TestClient/fixture; các ca PostgreSQL dùng SQL thật nhưng thay JWT/PostgREST bằng SQL transport. Không dùng số lượng test để suy ra coverage live.

| Case ID | Action / expected HTTP và invariant | Bằng chứng local | Kết quả local / phần tích hợp |
|---|---|---|---|
| SEC12-01 | Các route session/user thiếu/sai Bearer: 401 + challenge, không gọi DB | `security/test_w4_negative_baseline.py::test_w4_registered_routes_fail_closed_before_database` (30 route-method × 6 input) | PASS local; BLOCKED live JWT hết hạn/sai chữ ký |
| SEC12-02 | Ticket SSE không tồn tại: 401, không mở stream/lookup owner | Cùng module, `test_w4_unknown_sse_ticket_cannot_reach_owner_lookup` | PASS local; BLOCKED proxy/browser |
| SEC12-03 | User B không đọc session/content của A, không export hoặc xin link tải | `migrations/test_export_snapshot_pg.py::test_real_rls_hides_session_and_every_content_table_from_foreign_owner`; `test_private_export_pg.py::test_http_sql_owner_and_replay_boundary` | PASS SQL/RLS + HTTP/SQL; BLOCKED live identities |
| SEC12-04 | Ownership guard từ chối: 403 khi thấy foreign row; RLS che row: 404; không lộ artifact | `api/test_ownership.py`, `api/test_review_snapshot.py` (403/404); `exporter/test_snapshot_reader.py`; SEC12-03 | PASS local; giữ status theo contract endpoint, không ép mọi endpoint 403 |
| SEC12-05 | Confirm-source revision/key xung đột: 409, không ghi lại hoặc chạy worker trái phép | `api/test_confirm_source.py` (mismatched revision, changed source, idempotent replay) | PASS fixture; BLOCKED deployed RPC/worker |
| SEC12-06 | Generate trùng lúc active: 409, không schedule job mới | `api/test_generation_jobs.py::test_duplicate_state_conflict_does_not_schedule_job` | PASS fixture; BLOCKED producer live |
| SEC12-07 | Sau approval, mutation mới: 423; replay cùng action đã commit trả receipt, không ghi action mới | `api/test_review_rpc_http.py::test_http_action_key_replays_after_lock_but_new_action_is_locked`; PG locked writers / generation fencing | PASS HTTP fixture + SQL locks; BLOCKED toàn chuỗi live |
| SEC12-08 | Trước approval, export/status/download-url: 409; không claim/build/upload/sign, session không đổi | `migrations/test_export_snapshot_pg.py::test_task12_unapproved_http_export_never_claims_uploads_or_signs` | PASS HTTP/SQL; BLOCKED live |
| SEC12-09 | Input sai bị từ chối theo endpoint; không mutation | `api/test_ingest.py` zero-mutation 422; private HTTP body injection 400 | PASS local; không đồng nhất mọi input thành 422 |
| SEC12-10 | Duplicate export/claim race: một build authority, replay ready dùng cùng artifact | `migrations/test_private_export_pg.py` concurrent claims, complete replay, HTTP replay; `exporter/test_private_export.py` parallel request | PASS SQL/service; BLOCKED nhiều worker triển khai thật |
| SEC12-11 | Mất response upload/complete: giữ unknown checkpoint, reconcile; không báo rollback giả hoặc upload mù | `test_private_export_pg.py` response-loss/recovery tests; `exporter/test_private_http.py::test_lost_upload_response_requires_status_reconciliation` | PASS SQL/fake Storage; BLOCKED Storage thật |
| SEC12-12 | Upload lỗi/Storage 404 mơ hồ: không publish ready hay rebuild sai; RPC hoàn tất lỗi rollback ledger | `test_private_export_pg.py` ambiguous404, recovery network, lifecycle rollback; `test_private_export.py` upload failure | PASS SQL/fake Storage; BLOCKED SDK/Storage deployment |
| SEC12-13 | Thiếu config export/service key: fail closed, không mở HTTP client hay tạo privileged client | `security/test_w4_negative_baseline.py::test_w4_incomplete_export_config_never_opens_privileged_transport` (6 cấu hình: disabled, thiếu từng timeout, sai bucket, thiếu URL/key) | PASS local; thiếu service-role trên target chưa kiểm |
| SEC12-14 | Client không gọi privileged RPC/ghi ledger/ghi đè object export được | `test_private_export_pg.py` RPC ACL/forged-role/ledger RLS + restrictive Storage mutation policy | PASS PG policy fixture; BLOCKED Supabase/PostgREST/Storage ACL thật |
| SEC12-15 | Mỗi lần cấp link đều kiểm owner; TTL 3600, no-store; bucket private và URL hết hạn bị từ chối | Private service/HTTP tests kiểm reauthorize/TTL/header; SEC12-03 kiểm B không xin link | PASS local issuance; BLOCKED direct-object/TTL enforcement thật. URL đã cấp là bearer, không kiểm lại user khi mở |
| SEC12-16 | SSE ticket single-use, owner thay đổi 403, stale/future cursor 409/resync, reconnect không leak stream | `api/test_generation_stream.py` | PASS fixture; BLOCKED proxy/browser/Supabase live |
| SEC12-17 | Fallback/revert warning, provenance/flags và thiếu solution phải hiện đúng, không xuất đề sai | `api/test_review_snapshot.py` partial/regenerated/clone là coverage cục bộ; snapshot/export validator có guard dữ liệu | PARTIAL; chưa chứng minh fallback producer → review → preview → export. Cần input Quỳnh/Duy và oracle, không nhận PASS toàn case |

## Cách chạy lại

Tại root, dùng môi trường backend đã cài dependencies; chỉ dùng test values, không cần API key thật:

```powershell
$env:PYTHONPATH = "$PWD/backend;$PWD/backend/tests/migrations"
$env:SUPABASE_URL = 'https://mock.supabase.co'
$env:SUPABASE_ANON_KEY = 'mock-key'
$env:SUPABASE_SERVICE_ROLE_KEY = 'mock-key'
python -m ruff check backend/tests/security/test_w4_negative_baseline.py backend/tests/migrations/test_export_snapshot_pg.py
python -m pytest backend/tests/security backend/tests/api backend/tests/services backend/tests/exporter -q -rs
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
python -m pytest backend/tests/migrations/test_export_snapshot_pg.py backend/tests/migrations/test_private_export_pg.py -q -rs
```

Hai module PostgreSQL yêu cầu Docker CLI (`DOCKER_BIN` nếu ngoài PATH) và image `postgres:15-alpine`; tự tạo container/DB tạm, không nhận URL DB chung. Xem [harness PostgreSQL](../../backend/tests/migrations/README.md). Các suite `services/*real_db*` có opt-in riêng; skip của chúng không phải PASS. Typst/XeLaTeX có thể skip nếu thiếu compiler. Chỉ chạy trên môi trường kiểm soát, không đưa key thật vào command/output.

Trên máy Hùng, baseline dùng Docker image local `export07-backend-check:20261112`, backend mount read-only, network none, fake Supabase settings; PG dùng `postgres:15-alpine` trên mạng Docker internal, SQL transport thay HTTP, không gọi cloud. Harness SQL transport nằm ở scratch local, không phải công cụ bàn giao; lệnh chuẩn ở trên dùng Docker CLI của suite. Image local này không được coi là manifest deployment.

## Kết quả author và việc còn lại (15/11/2026)

- Security suite cuối: **248 passed**, 3 cảnh báo deprecation; gồm **188 checks mới** (180 auth variants + inventory + SSE + 6 missing-config). Log cục bộ ignored `scratch/task12-security-final.log`.
- Security + API + services + exporter trước 6 ca missing-config cuối: **1.173 passed, 3 skipped**, 8 cảnh báo deprecation; log cục bộ ignored `scratch/task12-local-baseline.log`. Sáu ca mới được kiểm trong security run cuối ở trên; không cộng thành một lần run tổng giả định. Các skip không được tính là bằng chứng DB/renderer.
- PostgreSQL + exporter sau khi thêm SEC12-08: **277 passed, 2 skipped, 21 subtests passed**; 2 cảnh báo harness/TestClient, log cục bộ ignored `scratch/w4-08-pg-harness/results.log`. Hai skip là XeLaTeX và preview repository chưa tích hợp; không nhận coverage cho chúng. Ca SEC12-08 mới đạt, không thay RPC/product code.
- Ruff check hai file test đạt. Code sản phẩm không thay đổi nên không chạy lại mypy của app cho thay đổi chỉ test/docs.
- Không commit raw log, signed URL, token, PII hoặc ZIP thật. Chưa có deployment test, Gemini thật, Golden E2E hoặc frozen-head sign-off.
- Chưa có reviewer độc lập ký baseline. TASK-12 **chưa Done**, chưa đủ điều kiện xác nhận G0/G1.

Khi nhận đủ input: ghi SHA frontend/backend, manifest migration/config không chứa secret, thời điểm UTC+7 và case-id/request-id sanitized; chạy A positive trước B negative, so state/DB trước-sau. Ghi expected/actual/status cho từng case, lỗi có PR/owner và retest. Request-id dùng giá trị server thực cấp nếu có; không giả định header chưa có trong contract. Evidence có link tải phải xóa toàn bộ URL/query/token còn hiệu lực. Duy/Đạt xác nhận frozen candidate rồi rerun phạm vi liên quan trên đúng head; thay đổi sau đó phải kiểm lại.

# W4 OPS handoff — lifecycle đề xuất và baseline triển khai

Đạt chuẩn bị 07/11/2026 cho [plan11/21](tasks/TASK-W4-OPS.md), [runbook](w4-production private beta-runbook.md), tiếp nhận yêu cầu Quỳnh [I-OPS-LIFE/I-OPS-DB](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6690592440). **Baseline được Duy chấp nhận08/11 tại PR51 comment6718841843; triển khai PR30@b1f0999 chưa merge/live**, không phải runtime đã triển khai. Không cấp quyền cloud/availability từ tài liệu này.

## 1. Phương án lifecycle để Duy/Quỳnh quyết định

| Nội dung | Đề xuất cụ thể | Căn cứ / người thực thi |
|---|---|---|
| Processes | Một backend Uvicorn worker, một app registry/broker/ticket store, một AIRuntime; không dùng reload trên production private beta | Dockerfile hiện workers1; Duy main integration, Quỳnh lifecycle |
| Scanner | Một loop lifespan độc lập request; quét ngay khi startup rồi mỗi30s; không overlap; mỗi lượt tối đa100 sessions theo generation_last_activity_at,id (017), có phân trang không bỏ đói job cũ | Duy xác nhận query/RPC quyền service-role + index; Quỳnh Python orchestration, timeout/logging |
| Stale cutoff | Giữ720s hiện hành; DB dùng server time và kiểm lại status/token/timestamp dưới lock; scan chỉ phát hiện, không quyết định bằng timestamp client | Job deadline600s + cleanup finish10s, cutoff có margin; 017 dùng generation_last_activity_at độc lập metadata |
| Clock/race | DB re-check chặn scanner kết luận từ query cũ; worker hợp lệ dưới600s không bị thu token sớm; không scale nhiều replica trước khi có claim scanner/DB coordination | Duy SQL author/reviewer Hùng; Quỳnh tests |
| Recovery | fail_stale_generation_job giữ committed results/quota/snapshot; clear old token, failed; retry explicit giữ nguyên targets đã commit | RPC005 hiện có. Không tự chuyển lại generating hay tự sinh lại khi startup |
| Interrupted code | Persist ERR_GENERATION_INTERRUPTED theo contract017 do Duy sở hữu; Quỳnh đã nối read-back, chưa có DB-applied proof | Chốt persist tại PR52@5b3f433; DB-applied/real proof pending |
| Terminal retention | Giữ buffer terminal tối thiểu15phút từ terminal event cuối; quét cleanup mỗi60s; chỉ forget khi terminal, subscribers=0, reservations=0, không còn job claim | Quỳnh broker cần timestamp/atomic conditional cleanup; broker hiện50events/session, capacity1024 |
| Active subscribers | Không evict stream/lease còn hoạt động để đạt retention; hết capacity báo lỗi rõ và resync từ durable DB, không tự xóa session generating | Quỳnh theo semantics broker; không coi15phút là hard limit khi đang xem |
| Epoch/replay | Restart tạo epoch mới; cursor/history mất trả recovery contract; FE lấy durable snapshot rồi subscribe theo epoch/cursor mới; không giữ counters/cursor RAM như dữ liệu bền | Quỳnh + Philip/FE2; pending live proof |
| Shutdown | Ngừng nhận claim mới trước teardown; cancel/await scanner và cleanup loops, bound wait10s; giải phóng handles; đóng AIRuntime sau tác vụ dùng gateway; in-flight chưa kết luận không tự ghi success | Duy/Quỳnh chốt shutdown wiring; không reset quota hoặc clear fencing mù |
| Metrics | Observer ở shared transport, không bọc batch lần nữa; main inject observer đúng registry, protected metrics và smoke đổi trong cùng đợt | Wiring implemented PR30@b1f0999, chưa merged/live; Quỳnh author; Đạt phối hợp dev.ps1/docker-ci |

Baseline đã được Duy chốt08/11, không phải capacity evidence hoặc deployment acceptance. PR30@b1f0999 triển khai scanner/retention/ticket protection/shutdown/metrics; F02 validator resource bounds còn OPEN. PR52@5b3f433 giao listing/fencing/durable errors, chưa merge/real-DB proof. Không yêu cầu owner giao lại contract đã có. ENV0/roster/access chốt ở [Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53).

## 2. Ma trận kiểm có thể chuẩn bị trước, chưa có kết quả live

| Case | Môi trường trước | Kỳ vọng cần đo |
|---|---|---|
| Idle restart | Isolated DB có partial committed + quota | Không cần request mới để scanner chuyển stale failed; old worker token bị fenced; retry chỉ slot thiếu |
| Scan race | Query trả job cũ rồi worker finish/retry mới | RPC recheck không sửa token/job hiện tại; không làm mất committed rows |
| Young job | Runtime dưới cutoff720s | Không recover trước hạn; DB clock không phụ thuộc client clock |
| Full backlog | Hơn100 stale rows | Batch bounded, phân trang xử lý toàn bộ, loop không overlap; không in content/secret |
| Terminal TTL | Fake clock15phút, có/không subscriber và lease | Chỉ xóa khi đủ cảTTL+terminal+zero-users/leases; fresh job cùng session không bị xóa |
| Broker capacity | Capacity1024 đầy | Error/recovery explicit, không evict live stream; durable snapshot vẫn đọc được |
| Shutdown/cancel | Scanner/stream/gateway đang await | Handles không âm/rò; scanner dừng; quota không reset; cancel không tăng successful outcome |
| Proxy/auth | Staging cùng SHA sau protected route | /health200, metrics anonymous401+Bearer, nonadmin403 ngoài development; no-store và safe503 |

Reviewer kiểm đơn vị không thay restart/PostgREST/RLS/proxy live; các cột kết quả vẫn UNRUN cho đến có evidence.

## 3. Baseline version/config cần freeze

Inventory static từ dev `73583d775243245cd2479e29d943c329b0b2debb`, không phải deployed head:

| Thành phần | Baseline đã đọc | Bàn giao còn cần |
|---|---|---|
| AI generation | prompts.py PROMPT_VERSION2.0.1 | Quỳnh ghi runtime model/config/prompt hash thực trong job/evidence |
| Blueprint | prompt_builder.py PROMPT_VERSION1.0.1 | Hùng/AI ghi canonical schema/prompt hash của artifact thực |
| Typst | backend image TYPST_VERSION v0.11.1 | Operator ghi typst --version trong container build thật |
| Backend Python | Dockerfile Python3.11 base image pinned; requirements.lock hashed | CI/build image digest và dependency changes từng owner |
| Frontend | npm ci từ package-lock.json, static Nginx target | Philip giao route/API-compatible SHA, rebuild public auth config |
| W2 integration | PR30@b1f0999; F01 verified, F02 OPEN; Draft/chưa merge/live | Duy bàn giao integrated head sau merge, không deploy PR head như dev đã có |
| W4 product policy | Issues45/46; docs PR50 còn review | Duy chốt modes/toggles/fallback; không dùng W2 fixture chứng minh W4 |

Freeze record cho mỗi candidate phải có git SHA, dirty=false, image digests, migration ledger/checksums thực, prompt versions+hashes, model ID, nonsecret config revision, oracle/input checksum. Không lưu key/JWT/prompt chứa đề riêng tư vào report public. Không đổi model/prompt để chữa live demo rồi giữ kết quả kiểm của head cũ.

## 4. Migration inventory và acceptance gate

[Static inventory](w4-migration-inventory.md) chỉ liệt kê byte hashes từ Git, không là execution manifest. Repo có schema bootstrap `backend/scripts/schema.sql` và migrations002–016; có file010/012 tên cùng supported_modes nên Duy/Hùng phải giải thích lịch sử thay thế trước khi ký fresh/upgrade ledger. Không tự skip/rename hoặc chạy lại migration dựa trên basename.

| Đường kiểm | Input Duy cần giao | Proof operator cần lưu |
|---|---|---|
| Fresh | Bootstrap đúng version, prerequisite auth/roles/extensions và approved ordered manifest | Empty isolated DB→fullchain; constraints, functions signatures/grants, source-confirm/config/job/clone/review/finalize smoke |
| Upgrade | Ledger/checksums hiện có và source version; forward changes từ version đó | Không apply lạiDDL đã có; giữ dữ liệu/job/quota; schema/grants diff; same acceptance như fresh |
| Failure | Migration atomicity, backup/restore authority, roll-forward plan | Failed step+transaction status; không tiếp tục mù; không dùng app rollback thay DB repair |
| Final receipt | Backend/API-compatible SHA, admin JWT test method, storage policy | URL/time/SHA/migration hashes, A/B and admin/nonadmin auth checks; chỉ sanitized logs |

Đạt chuẩn bị static inventory và checklist; Duy/Hùng xác nhận authority và DB proof. Chưa có quyền/test project nên chưa chạy SQL hay cloud setup.

# W4-MVP-11 / 21 — Plan OPS và bàn giao demo của Đạt

## Checkpoint hiện hành — 17/11/2026 (UTC+7)

Checkpoint này thay các nhận định trạng thái cũ bên dưới; các mốc 07–15/11 giữ làm lịch sử. Owner OPS11/21: Đạt; workflow v0.1 proposed + INPUT-20261109. Không đổi người phụ trách module hoặc tiêu chí nghiệm thu.

- **Runtime local:** đã pull `dev@1ff345cc4d1ca04d81abc75b6ca14db0f192c9db`, build lại Docker Compose; frontend/backend healthy, smoke **8/8 PASS**. Frontend ở `http://localhost:3000`, backend ở `http://localhost:8000`, chỉ bind loopback. Có #49 Preview, #58 snapshot adapter và #66 route/resume; App đã mount Preview và Export. Không còn chờ merge #58/#66.
- **Cloud connectivity:** MCP/CLI đã truy cập được project nhóm; backend container thực tế gọi Supabase REST trả **HTTP 200**. Credentials chỉ lưu local, không đưa vào Git. Kết quả này chưa chứng nhận Auth A/B, RLS hoặc toàn bộ pipeline.
- **DB0 / I08-11S:** đọc catalog shared DB ngày 17/11: chưa có `public.private_export_ledger`, RPC `public.private_export_ledger_command` và bucket `exam-export-bundles`. Không có bảng ledger chuẩn `supabase_migrations.schema_migrations`; chưa thể xác nhận applied manifest toàn bộ. Bốn thân hàm được sửa trong migration024 khớp bản repo sau chuẩn hóa whitespace; đây không phải xác nhận đầy đủ ACL/postconditions của024. Không replay024 chỉ vì thiếu ledger.
- **An toàn triển khai:** chưa apply DDL, tạo bucket, seed/cleanup hoặc bật private export trên DB nhóm. #63 còn mở; #82 renderer cũng chưa merge tại checkpoint. Cần Duy/Hùng/DB owner chốt manifest upgrade có020, backup/restore và GO trước thay đổi shared DB; sau đó kiểm private bucket/ACL, size/MIME và quyền test A/B. Local/disposable DB vẫn là phương án Golden theo điều phối #74, không cần biến shared DB NO-GO thành blocker của mọi kiểm thử local.
- **Timeout/lifecycle:** Nginx read timeout600s, backend một worker; Compose chưa đặt stop grace riêng (Docker mặc định10s). Chưa chứng minh tổng thời gian export và shutdown an toàn khi có job đang chạy. Không coi lease900s là timeout end-to-end đã đủ.
- **ENV0/Q14/Q20:** lựa chọn local trên máy thuyết trình đã đủ cho chuẩn bị local; không yêu cầu lại host online như điều kiện của bước này. Q14/oracle theo handoff của #74, chỉ yêu cầu phần còn thiếu ở đúng revision. Q20 đủ dùng cho summary/synthetic evidence; raw evidence lưu local ignored, kho chung/retention/consent vẫn cần người giữ kho xác nhận. Không đăng token, signed URL hoặc dữ liệu thật.
- **Bàn giao tiếp:** OPS cung cấp runtime/DB facts cho #73/#74; khi candidate tích hợp + DB/Storage/test scope đủ, chạy G0 trên đúng FE/BE SHA rồi giao Quỳnh Golden OFF/OFF N=2 (6 slots), ON/ON riêng, G2 và demo21. **G0/G1/G2: NOT_VERIFIED**; smoke8/8 và REST200 không thay nghiệm thu này. ETA phần phụ thuộc vẫn TBD, không cam kết thay owner.

Evidence local ignored: `.artifacts/w4/ops-20261117-1ff345c-smoke.json`. Build từ checkout local có file demo untracked được giữ lại; chưa gọi đây là frozen release từ archive sạch. Chỉ bàn giao summary đã khử nhạy cảm qua Git.

## Checkpoint lịch sử — 15/11/2026

Đã build và kiểm Docker local từ `dev@c2ee9fd`: hai containers healthy,4 smoke checks và4 anonymous auth checks PASS, Typst0.11.1; không dùng cloud credentials. Xem [kết quả và giới hạn](../w4-ops-local-c2ee9fd.md). Runtime này chưa chứa PR63/67; các checkpoint cũ bên dưới giữ làm lịch sử. Integrated smoke/G0 live/G1/G2 vẫn chưa được nghiệm thu.

Đã bổ sung4 kiểm auth vào smoke dùng chung (tổng8), kiểm trên Docker trước/sau restart backend không có job;9 tests/14 subtests và Ruff PASS. Runbook có lệnh xuất JSON evidence; không cần chạy tay các auth probes nữa. Đây là phần tooling OPS hoàn thiện được độc lập với input cloud.

## Checkpoint lịch sử — 13/11/2026 (UTC+7)

- Author OPS11/21: Đạt; workflow v0.1 proposed. Nhánh tiếp nối `docs/w4-ops-integration-checkpoint`, base ban đầu `dev@294c69a1a085ac6487d65b633e06a2f1112e2046`; đã sync devb47e4fa, gồm #54/018 và #60; đây là sync source/docs, không nhận đã build runtime mới, giữ nguyên SHA294c69a của runtime đã kiểm; không mở lại PR51 đã merge. Các checkpoint có ngày cũ phía dưới là lịch sử.
- PR51 preparation đã merge. PR52 đã merge thành `294c69a`; Đạt Approve sau 23/23 test PostgreSQL17 thật. Không còn chờ F01–F04 của PR52; **chưa có applied ledger trên DB ứng dụng**.
- PR54 đã merge vào dev21887c1; Git blob018 giữ nguyên. Evidence tại `7c7200f`: Đạt [Approve](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/54#pullrequestreview-5857922227), 23/23 PostgreSQL15 + 198 API/review tests pass. PR56@`586604b`: [Approve docs](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/56#pullrequestreview-5857894388); không xác nhận policy adoption.
- PR61 đã merged vào devb47e4fa; evidence tại `9fda6fd`: [Approve](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/61#pullrequestreview-5884187896), F01/F02 verified; 345pass/1optional worker-skip, CI5/5. PR30@`66ad00c`: [Approve W2](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#pullrequestreview-5884226438), final API93pass/CI5/5. W4 adapter tách [issue64](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/64); chưa ghép #30+#61 làm W4 release.
- Build từ Git archive sạch của base `294c69a`, project Docker cô lập `dat-w4-checkpoint`, Windows/Linux engine, static Compose, env từ `.env.example` rỗng; chỉ đổi ports thành frontend13000/backend18000. Không đọc/copy env thật, không gọi cloud. Backend/frontend healthy; preflight + 4 HTTP probes PASS; anonymous `/api/sessions` trả401 trực tiếp và qua proxy; Typst0.11.1. Stack test đã down đúng project, không xóa volumes/stack khác.
- Image IDs: backend `sha256:1116996153c3db881dcf20b605a313170c2d25d909b1e447080fdddb1f8c4037`; frontend `sha256:81e93c31b81eb3a9a00523113967b262e0b19725b864ae40ab9c446ba39c0a85`. Evidence local ignored: `.artifacts/w4-ops-294c69a/{build.txt,preflight.json,smoke.json,anonymous.json}`; các đường dẫn này không phải artifact nhóm đã nhận.
- **Chỉ LOCAL build/health/smoke verified**. Chưa OAuth/ownership A-B, PostgREST, Gemini, worker/SSE/restart, Storage/ZIP, private beta hay G0/G1/G2. Không dùng review SQL hoặc health200 thay DB deployment.
- Tiếp tục trong scope: runbook/script8 bước đã có; chờ DB0/I-OPS-DB, Q09/Q10, Q14 và Q20 theo bảng input duy nhất bên dưới. Task20 prompt optimization vẫn deferred. ETA của các owner chưa xác nhận giữ TBD.

- Owner phần OPS theo phân công W4 và yêu cầu tiếp tục của Đạt: Trương Thành Đạt (`Thanhdat3010`), bắt đầu 07/11/2026 theo yêu cầu trực tiếp. Quyền cloud, người thay thế và availability cuối tuần chưa được xác nhận; không suy từ quyền sửa repo.
- Nguồn: [W4 assignment v2.0](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_ASSIGNMENT%20%281%29.md), [task detail](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_TASK_DETAIL.md). Bản nguồn còn ghi chờ owner xác nhận; lời Duy ưu tiên khép PR cũ trước W4.
- Workflow v0.1 proposed, docs baseline `506384b`; author mode, M2/M3. Nhánh `docs/w4-ops-runbook`, rẽ từ dev `73583d7`. Reviewer đề xuất Duy (BE/OPS), Hùng (Storage), Quỳnh nhận môi trường; chưa có approval.
- Deadline dưới đây theo W4, UTC+7; là mốc cần giao, chưa phải ETA đã xác nhận. Không thay bằng lịch tuần thông thường.
- Runbook: [W4 private beta](../w4-staging-runbook.md).
- Bổ sung trước khi có server: [lifecycle proposal và freeze/migration gates](../w4-ops-handoff.md), [static migration inventory](../w4-migration-inventory.md). Đã review PR50 theo yêu cầu GitHub; các contract F01–F03 chờ Duy sửa, không tự sửa nhánh author.

## Phạm vi và hiện trạng

Chuẩn bị môi trường, inventory tên biến, deploy/runbook, smoke và evidence cùng head. Không viết trùng SQL/worker/exporter; không tối ưu prompt (task20 deferred). Mỗi thành viên vẫn chịu trách nhiệm Docker/dependency của module mình; Đạt điều phối integration và chỉ đề xuất sửa cấu hình chung qua PR.

Đã kiểm tĩnh trên base: Compose bind loopback; backend một Uvicorn worker; Typst v0.11.1 trong image; Nginx SPA fallback và SSE no-buffer/600s. Chưa có TLS/production private beta deployment. Trên base script dev/CI còn metrics200; PR30@b1f0999 đã triển khai anonymous401/Bearer cùng protected route, chưa merge. Không sửa trùng trong PR51. `ADMIN_EMAILS` có trong backend Settings nhưng chưa có trong `.env.example`.

Máy reviewer không có `docker` trong PATH ở lượt kiểm 07/11; chưa chứng nhận engine/image/cloud. Không đọc `.env`, không nhận việc có secret đồng nghĩa có quyền cloud. PR41 đã merge; PR30 F01 được reviewer xác minh tại `8fb6387`, còn Draft và thiếu integration inputs. Không dùng kết quả kiểm PR30 thay kiểm deploy branch này.

## Trình tự thực hiện

| Lượt / file | Đầu ra | Input cần | Kiểm / mốc cần giao |
|---|---|---|---|
| 1: plan này + runbook | Inventory, blockers, smoke/evidence template | Code hiện có; đã đủ | Links/diff, Draft PR ngay |
| 2: production private beta topology/config đề xuất | Host/URL/TLS termination, single worker, origin/callback | Duy xác nhận ENV0/Q12 và quyền; Hùng Storage requirements | Docker config quiet/build/health trên máy có Docker; skeleton08/11 |
| 3: deploy pinned SHA | Fresh/upgrade ledger, Auth, DB, Gemini, Typst, Storage thật | BE-H1 từ Duy, Hùng export/bucket contract, Quỳnh worker | Live10/11 12:00; chưa đủ thì BLOCKED |
| 4: scripts/dev.ps1 + docker-ci.yml khi phối hợp xong | Anonymous metrics401/Bearer, health200, proxy regression | Quỳnh protected route/contract + Duy main integration | Cùng patch/head tương thích; không nới auth để giữ smoke xanh |
| 5: runbook/evidence | Script8 bước, G0/G1/G2 reports cùng SHA | Philip UI; Quỳnh Golden; Tâm oracle; Hùng ZIP/security | Script12/11; G0 12/11 18:00; G1 14/11; demo15/11 |

<a id="input-handoff"></a>

## Input handoff — bảng lịch sử và checkpoint hiện hành

**Cập nhật trạng thái 17/11:** đọc checkpoint đầu file trước; bảng dưới giữ nguồn yêu cầu và trạng thái tại 13/11, không mở lại các input đã Accepted sau đó. Không dùng các dòng “chưa merge” cũ thay trạng thái hiện hành.

Áp dụng cách ghi đề xuất INPUT-20261109 tại [PR57@ef941be](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/57): không thay workflow/owner/gate hiện hành. Giữ ID cũ; ENV0 và quyết định quyền/roster vẫn có nguồn chuẩn Issue53, bảng này chỉ dẫn link và ghi phần đủ dùng cho task11/21. Mốc là need-by từ W4, ETA chưa có xác nhận ghi TBD.

| ID / yêu cầu gốc | Cung cấp → Đạt / mục đích đủ dùng | Mức và phần đã nhận | Còn thiếu / bước tiếp / need-by / ETA |
|---|---|---|---|
| [ENV0/Q12](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53) | Duy + người giữ quyền → OPS11; môi trường và authority để triển khai | Decided topology08/11; local Windows Docker build/health smoke đã chạy. Đủ dùng chuẩn bị local, chưa Accepted cho deployment online. | Host online/quyền/access gate/backup/roster theo Issue53; đề xuất máy Đạt chưa được duyệt làm host online. Duy điều phối; trước deploy; ETA TBD. |
| [DB0/Q08](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/51#issuecomment-6718841843) | Duy + Hùng → OPS11; manifest và candidate SHA để áp DB an toàn | Đã nhận quyết định017 sau016 và candidate inventory; chưa đủ để chạy migration trên shared DB. | Approved fresh+upgrade manifest, ledger/checksum, backup/restore/forward-fix, quyền và SHA tương thích; Duy/Hùng; need-by09/11 18:00; ETA TBD. |
| [I-OPS-LIFE](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6690592440) | Duy + Quỳnh → OPS11; policy để chuẩn bị cấu hình/ma trận smoke | Consumer Accepted cho chuẩn bị runbook: baseline1worker, startup+30s scan, batch100, cutoff720s, terminal15phút, cleanup60s, shutdown bounded đã chốt08/11. Code PR30@66ad00c Approve W2, chưa merged/Integrated; W4 adapter theo issue64. | F02 reviewer verified tại b6b6422 (705pass/1skip, Ruff PASS); còn merge/pinned SHA rồi kiểm restart/SSE/proxy thật; Quỳnh module owner; trước integrated smoke; ETA TBD. Không xin lại policy đã giao. |
| [I-B-STALE](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/52) | Duy → OPS11; durable interruption/SQL contract | Consumer Accepted contract017; code merged vào dev294c69a. Đạt verified F01–F04 tại3d05949, PostgreSQL17:23pass/0skip và Approve. | Không chờ sửa/review52 nữa. Chờ DB0 applied ledger/checksum, quyền/backup và compatible #30 SHA để kiểm recovery thực. Trước lifecycle acceptance; ETA TBD. |
| [I-OPS-DB](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6690592440) | Duy + người giữ quyền → OPS11; identities A/B/admin/non-admin và phạm vi test | Requested; chưa có handoff đủ dùng để Auth/ownership smoke. | Cấp quyền qua kênh an toàn, seed/cleanup/quota và ADMIN_EMAILS owner/revoke; trước integration; ETA TBD. Không đăng JWT/secret. |
| [Q09/Q10](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_TASK_DETAIL.md) | Hùng + Duy → OPS11/21; private Storage/export config và API | Nhận một phần: PR63@8bb2931, SQL020/ACL reviewed, 17PGpass +29private-unit-pass/1skip. Philip đã chốt Q10 sync POST; chưa có runtime route/live proof. | Hùng sửa existing Q09 findings; Duy/Hùng giao applied manifest/private bucket/size-MIME/SDK timeout và quyền. OPS đối chiếu bảng cấu hình bên dưới; ETA TBD, chưa nhận900s đủ an toàn. |
| [Q14](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_TASK_DETAIL.md) | Quỳnh + Tâm + Duy → demo21; Golden3 câu N=2 và oracle | Requested; script/phiếu trống chuẩn bị được, chưa có Golden đã duyệt để chạy nghiệm thu. | Artifact/revision, permission, key/solution oracle, config/model/prompt; trước E2E; ETA TBD. |
| [Q20](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_TASK_DETAIL.md) | Duy + Hùng + Đạt → demo21; nơi lưu proof và quyền recording | Requested; không tự tạo cloud folder/chia sẻ dữ liệu. | Nơi lưu ZIP/video/log, quyền/retention/consent và người ký; trước pack12–15/11; ETA TBD. |

Đạt nhận chuẩn bị plan/runbook ngay. Duy điều phối input còn thiếu; không gán cam kết quyền hoặc ca trực thay người dùng. Phần Docker/CI thay đổi cụ thể sẽ phối hợp Quỳnh khi protected route sẵn; không cần Quỳnh chờ OPS để code unit/guard độc lập.

## Storage/timeout handoff — I08-11S, kiểm repo ngày13/11

Nguồn input duy nhất vẫn là Q09/Q10 trong bảng trên; bảng này là inventory kỹ thuật, không tạo trạng thái/owner mới. [Review OPS63](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#pullrequestreview-5884323942); [Q09 finding gốc](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6831140214).

| Hạng mục | Đã kiểm từ source | Còn cần trước live wiring/smoke |
|---|---|---|
| Bucket/interface | PR63 dùng `exam-export-bundles`, immutable upload `upsert=false`, MIME `application/zip`, owner-authorized signing TTL3600s | Hùng/Duy giao project alias + private flag/ACL applied và test scope; không gửi key/JWT/signed URL |
| Policy020 | PostgreSQL15: chặn owner export mutation, owner SELECT/foreign RLS và raw/source behavior có test; chưa áp DB nhóm | Approved manifest/hash/order019→020 và actual applied receipt; bucket privacy vẫn phải kiểm riêng |
| Size/MIME | PR63 app ceiling100MiB/ZIP,20MiB/PDF; đây không phải quota Storage | Actual global/per-bucket limit và allowed MIME từ operator; nếu thấp hơn thì chốt giới hạn trước wiring |
| SDK IO | Repo chưa có cấu hình export upload/read-back timeout được bàn giao | Hùng cấu hình bounded SDK timeout/retry và báo total budget; không dựa default SDK chưa pin |
| Proxy/runtime | `frontend/nginx.conf` API `proxy_read_timeout 600s` là idle-read timeout, không phải hard end-to-end deadline; Compose chưa cấu hình stop_grace_period riêng | Operator đối chiếu browser/proxy/worker shutdown thực; Philip sync POST decision không tự đổi timeout |
| Lease/build | RPC020 lease900s provisional; Typst per-call30s, chưa bound rendering + mọi IO + scheduling end-to-end | Chốt worst-case total budget/margin với Hùng/Duy trước bật route; không suy900s đủ từ9×30s |
| Failure semantics | Timeout/disconnect là outcome unknown; read/status trước manual retry; không blind rebuild/delete | Sửa404/checkpoint ack theo Q09, kiểm trên exact candidate + private Storage thật |
| Secret inventory | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` có tên trong `.env.example`; không thêm export secret mới từ docs này | Xác nhận người giữ/cấp/thu hồi qua kênh an toàn; không đọc hoặc ghi giá trị vào report |

Chưa có approved live settings thì ghi BLOCKED đúng mục; không sửa SDK/Nginx/Docker của module khác để tự chốt contract. Sau handoff, OPS kiểm sanitized config + owner A/B + upload/read-back/checksum/signing và ghi exact SHA/DB alias/ledger; không ghi URL có token vào evidence.

## Bàn giao và kiểm

- Đã làm: kiểm cấu hình tracked, inventory, plan/runbook và smoke checklist. Không đổi production config/API/schema/dependency nên chưa phát sinh ADR mới.
- Kiểm docs: link local tồn tại, UTF-8, git diff --check. Không chạy product tests cho thay đổi thuần docs; vẫn yêu cầu CI trước merge.
- Ghi nhận lịch sử 07/11 (đã có Docker local smoke trong checkpoint mới ở đầu file): chưa kiểm Docker build/run tại thời điểm đó. Chưa kiểm TLS/OAuth thật, DB/RLS, Gemini, Storage, restart/FE/proxy live. ENV0 và integrated acceptance: BLOCKED chờ handoff, không phải LOCAL_READY cho toàn production private beta.
- Output cho Duy/Hùng/Quỳnh/Philip: Draft PR này và runbook; URL/deployed SHA/test identities sẽ bàn giao sau quyền/môi trường được xác nhận. ETA thực tế TBD.
- Mọi kết quả demo ghi PASS/FAIL/BLOCKED đúng từng gate, cùng SHA/config/migrations/prompt. G1 không thay demo ngày15/11; thay head sau freeze phải rerun phạm vi ảnh hưởng.

## Cập nhật triển khai 07/11 — phạm vi 11/21

- Có `scripts/w4_ops.py`: preflight read-only, smoke HTTP có timeout và JSON evidence; dùng Python standard library, không thêm dependency/Docker.
- Preflight kiểm Docker CLI, Linux engine, Compose >=2.24.4, sự tồn tại env (không đọc giá trị), static Compose config quiet. Smoke kiểm health, HTML, /login và /docs qua proxy; không đổi metrics route/dev helper/CI đang chờ Quỳnh.
- Báo cáo tách checkout SHA với deployed SHA do operator cung cấp, không overwrite; checksum ZIP không chứng nhận nội dung/6 slots. G0/G1/G2 vẫn cần manual evidence và acceptance.
- Quỳnh nhận Python lifecycle/route/tests tại [comment6703279898](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6703279898); bảo vệ ticket chưa mở stream thuộc Quỳnh. Không nhận thêm phần triển khai này cho Đạt.
- Kiểm Windows/.venv: 5 unittest isolated PASS, Ruff PASS. Docker/live smoke chưa chạy thành công; môi trường/migration/cloud inputs vẫn BLOCKED.

## Quyết định 08/11 — production private beta, merge preparation độc lập

Nguồn chuẩn ENV0: [Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53); [Duy quyết định](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/51#issuecomment-6719017111). Không cần staging server riêng. Một production HTTPS deployment, beta **chỉ thành viên nhóm được duyệt**, ngân sách mặc định 0đ; trả phí chỉ sau phương án và phê duyệt chi phí. Chưa chọn nhà cung cấp/domain hoặc cam kết availability.

- Topology DECIDED: static Compose, 1 worker/replica, không reload/autoscale; giữ loopback/internal, backend8000 không public. Operator xác nhận ingress/TLS/origin/OAuth. Gate private beta phải thực thi access control; CORS/ẩn URL không đủ.
- PR30@b1f0999: lifecycle/metrics/smoke implemented, chưa merged/live; review F02 timeout/resource bounds còn OPEN. Không tự sửa worker/validator.
- PR52@5b3f433: SQL017/contract delivered, chưa merged/approved/DB-applied; Duy/Hùng review ACL, real PostgreSQL fresh+upgrade, approved manifest/ledger/backup+restore. [Candidate inventory](../w4-migration-candidate.md) không thay historical inventory.
- ENV0=BLOCKED: host/access/provider, team principals/count, primary+backup/slots và safe secret channel chưa giao. Đạt đã nhận preparation11/21, **operator deployment và lịch cá nhân chưa được xác nhận**. Duy điều phối tại Issue53; không đăng secret/email roster vào repo.
- Q09/Q10 Storage, Golden/oracle và live identities vẫn cần owners giao. Destructive tests chỉ local/isolated DB; không chạy trên production DB.
- PR51 preparation có thể Ready/merge sau review độc lập + final CI; **không cần deployment/G0/G1/G2 PASS**. W4-MVP11/21 Integrated Done vẫn cần proof thật.
- Trạng thái tách biệt: LOCAL_READY (local Docker/tests) → DEPLOYED_PRIVATE_BETA (HTTPS/access gate/real services/exactSHA/ledger/owner) → G0 integrated → G1 Golden6/6 → G2 demo; PUBLIC_GO/NO_GO là quyết định riêng sau proof P0. Hiện chỉ tooling isolated verified, chưa LOCAL_READY toàn stack.

## Bàn giao tiếp 08/11 — review và ENV0-1

Đạt tiếp tục phần OPS11/21 theo phân công và yêu cầu thực hiện; không cần giao lại task. Quyền truy cập host/cloud, backup và lịch cá nhân vẫn cần dữ liệu thực tế. [So sánh hosting0đ](../w4-hosting-options.md) đã chuẩn bị, chưa chọn provider/chạy cloud. PR51 đã request Duy/Hùng review chính thức.

PR50@a5a31e2: reviewer verified F01–F03 và GitHub Approve; F05 mapping canonical persistence là non-blocking. PR52@9e9d6f3: SQL embedded probe xác nhận lifecycle/ACL, nhưng test F01 chờ sai message guard009; đã Request Changes, real PostgreSQL/races chưa verified. Không dùng kết quả PGlite thay live DB. PR30 F02 tiếp tục chờ owner. [Candidate017](../w4-migration-candidate.md) cập nhật riêng; historical inventory giữ nguyên.

## ENV0 host — Đạt xác nhận 08/11

Đạt chọn tạm máy cá nhân hiện tại làm host beta. Đây là lựa chọn host, chưa là Docker-ready/deployed hoặc cam kết uptime/ca trực. Kiểm local: không thấy docker trong PATH hoặc executable Docker Desktop ở đường dẫn cài chuẩn; có wsl.exe/winget.exe nhưng chưa xác minh WSL2/virtualization/engine. Dung lượng trống quan sát khoảng46GB ổC,193GB ổD. Truy vấn OS/RAM qua CIM bị từ chối quyền nên chưa đánh giá đủ tài nguyên.

Bước tiếp: cài/xác minh Docker Desktop Linux engine + WSL2, khởi động/restart nếu installer yêu cầu; chạy preflight/build/health theo runbook. Chưa mở port/public ingress, chọn tailnet/provider, thay OAuth hoặc chạy migration cloud. Host/access/roster/backup và compatible backend/migration handoff còn các gate riêng.

Cập nhật cài host08/11: đã tải bộ cài chính thức desktop.docker.com, Authenticode Valid/Docker Inc; Docker Desktop per-user WSL2 install log báo Installation succeeded. Đã cài Virtual Machine Platform và WSL, wsl --version trả3.0.3.0. Windows báo cần reboot để thay đổi có hiệu lực; chưa tự restart, chưa chạy engine/build/health. Nhận định Docker chưa cài ở đoạn kiểm ban đầu phía trên là lịch sử trước bước cài này.

## Local host smoke09/11 — sau reboot

Docker Desktop Linux/WSL2 engine đã chạy; doctor và preflight PASS. Đã build/chạy static docker-compose.yml (không dev overlay/reload), checkout092b0a9 với local docs chưa commit và script demo_generator.py có sẵn không sửa. Hai services running/healthy, chỉ bind127.0.0.1: frontend3000, backend8000. Smoke backend health/frontend HTML/login deep-link/proxy docs PASS; evidence localignored `.artifacts/w4/preflight-20261109-host.json`, `.artifacts/w4/smoke-20261109-host.json`. Typst trong container0.11.1. Không ghi đây là clean frozen deployment hoặc G0/G1 acceptance.

Giữ nguyên env; không áp migration/cloud, không gọi Gemini, chưa kiểm OAuth/ownership/SSE/restart/Storage/Golden. Chưa mở mạng riêng/HTTPS/public. Frontend npm ci báo14 dependency advisories (2high); chưa audit/review scope tác động, không tự npm audit fix/đổi lockfile. Containers đang chạy để Đạt truy cập local.

## PR51 review fixes 09/11 — claimed_fixed, chờ reviewer xác minh

- Proxy smoke chuyển từ HTML `/docs` sang JSON `/openapi.json`, kiểm OpenAPI3.x và GET `/health`, `/api/sessions`; regression từ chối SPA HTML, JSON lỗi/không đúng schema/thiếu routes.
- CI backend thêm OPS unittest và Ruff cho hai scripts, không thay product runtime/Docker/dependency.
- Đã kiểm local: 6 unittest PASS; Ruff PASS; HTTP smoke mới trên stack local hiện có PASS, integrated acceptance vẫn NOT_VERIFIED. Evidence ignored `.artifacts/w4/smoke-pr51-openapi-20261109.json`; stack build từ092b0a9 trước patch scripts, không nhận clean deployment mới.
- Phân biệt theo comment Duy09/11 và PR56: mỗi developer tự cài/chạy Docker local. Máy Đạt đã local-ready về build/health; đề xuất dùng tạm máy cá nhân trước đây chưa là host online được nhóm phê duyệt, không thay ENV0/Q12 hay xác nhận uptime/quyền cloud.
- PR52@598b959 reviewer chạy PostgreSQL17 thật:15pass/5fail; F01 verified, F02–F04 test fixes còn chờ Duy. PR30@b6b6422 có patch mới, Đạt chưa xác minh lại F02. Không dùng smoke này thay G0/G1/G2.

## Preparation W4-MVP-21 — 09/11

Đã soạn [script diễn tập và phiếu evidence](../w4-demo-rehearsal.md): prerequisites clean checkout,8 bước với expected/evidence, tách ca phụ,6-slot key/solution mapping và xử lý FAIL/BLOCKED/restore. Đầu ra đủ dùng đọc thử/tập thao tác khi owner cung cấp input; chưa chạy Golden/Auth/SSE/Storage và chưa ký G0/G1/G2. Reviewer Duy đã được đề nghị ở PR51; không tự nhận acceptance. Bảng input phía trên thay bản cũ, không tạo tracker song song.

## Khép preparation và review 09/11

Đã sync dev ed81acd (PR42/50), giữ cả OPS/W4 decision logs khi xử lý conflict changelog. PR30@b6b6422 F02 reviewer verified trong thread gốc:705pass/1skip, Ruff PASS; phần AI/OPS đã kiểm không còn finding bắt buộc, chưa integrated/live acceptance toàn Draft. PR51 còn chờ independent review/CI; các input còn thiếu giữ ở bảng input-handoff, không yêu cầu lại phần đã nhận.


## Gói chuẩn bị Golden local — 17/11/2026

OPS author Đạt, tiếp nối PR83; không sửa module DB/export của owner khác. Candidate dưới đây là **nguồn SQL để rehearsal**, chưa phải manifest được DB owner phê duyệt cho shared DB. Không tự ghép hai PR chưa merge thành release.

### Catalog có thể chạy lại

Chạy `scripts/w4_export_catalog.sql` bằng operator trên đúng DB alias. Query chỉ đọc metadata bảng/RPC/bucket, không đọc câu hỏi, identities, token hay object URL. Kết quả ngày17/11 trên DB nhóm: export ledger=false, history chuẩn=false, RPC=[], bucket=[]. Không có history chuẩn không có nghĩa mọi migration đều chưa áp; cần catalog/postconditions và ledger được owner đối chiếu.

### Cấu hình cần xác nhận trước activation

| Input | Giá trị/giới hạn từ source | Trạng thái |
|---|---|---|
| Flag | `PRIVATE_EXPORT_ENABLED=false` cho tới khi đủ gate | Giữ disabled |
| Bucket | `exam-export-bundles`, private; upload `application/zip`, upsert=false | Chưa tồn tại trên shared DB; limits/ACL chưa nghiệm thu |
| RPC timeout | `PRIVATE_EXPORT_RPC_TIMEOUT_SECONDS`, bắt buộc khi bật, 1–120s | Chưa chọn budget cuối |
| Storage timeout | `PRIVATE_EXPORT_STORAGE_TIMEOUT_SECONDS`, bắt buộc khi bật, 1–300s | Chưa chọn budget cuối |
| Proxy/process | Nginx600s; Docker stop grace mặc định10s | Cần thử in-flight export/shutdown, không suy tổng bound từ từng IO timeout |
| Principals/seed | A/B qua kênh an toàn, nguồn synthetic, quyền seed/cleanup và quota test | Chưa có handoff đủ để chạy ownership + full Golden |

### Git-byte inventory cho rehearsal

Nguồn `ad87643b6ac26d6a05bd4935edd7b27014610741` (#63), gồm producer024 nhưng chưa chứa #82 renderer hoặc route integration #66. Thứ tự lexical dưới đây giống fixture migration hiện có; dùng bootstrap riêng của fixture khi test PostgreSQL, không chạy mù trên shared DB. `schema.sql` của fixture không phải bootstrap Supabase production. File010 rỗng giữ làm lịch sử.

| File | SHA256 Git blob |
|---|---|
| `002_replace_source_questions_rpc.sql` | `8dae5f4d5b5cd05d098faa5cfa8b13ff34e40d31b60de2f545b6407eabf6d0d0` |
| `003_confirm_exam_source_rpc.sql` | `9d410a002820d8b5b49bca02f0e9882fa3182f553a295a57a8d1f003dbb34093` |
| `003b_reconcile_baseline.sql` | `b8d9497ee4683708be121738e9103bf87039272382d6f882b27f52ace8932b44` |
| `004_save_generation_config_rpc.sql` | `c66a1416b875ee407f0663301d841120cf9b5b5c16480ea07aea4435583aba25` |
| `005_generation_job_operations_rpc.sql` | `55d3d51d1608ad4ec6c57d542428af728d6cdec28373846d0752018da4f1ea65` |
| `006_stage3_review_and_shuffle.sql` | `c6a50d885f0382c791db2ad7dcd1450c4f766e58d2884dbae615a8028daa27c5` |
| `007_finalize_approve_session_rpc.sql` | `bd2ccc61b9ce14e1661c50c5671fc2e4da2baf4a681b52a4c5d13cf60acca78e` |
| `008_finalize_persist_shuffle_rpc.sql` | `f32935cbf48a27d2c8c988ba8dfc1accefdb48300b9e273c094710b63d18d63f` |
| `009_finalize_security_boundary.sql` | `b4516597de80f8678381968678b46748ff92a4d7c7b4ad581fc3378cb6ac4bef` |
| `010_source_artifact_supported_modes.sql` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `011_source_confirmation_revision.sql` | `e450637bac39ff47c3677de497d84bc42aba948dac656f6c4009f67135a8f0cf` |
| `012_source_artifact_supported_modes.sql` | `dd58de9603cf36fefd794dcbd5904c52c9216d10014fdd13edc63691218ef54d` |
| `013_source_freeze_guard.sql` | `1a04b5ff975a68605cd8eed9b1fc579a33f1b3f5897b738863a41989413e39ff` |
| `014_disable_legacy_source_confirmation.sql` | `9f408a274739b82ae94803aff1bee594ab4a0111273bdfb08410366ea59a4113` |
| `015_stage2_canonical_w2_integration.sql` | `63b18dc6b541ec48c55ee3e4d5371cb8f84bc96c429b85f052feeb260521dc1b` |
| `016_stage2_original_clone.sql` | `539f929112eb1803fb0f4d1e5464155a07808e6640ecd6ce2bf42dca1a823427` |
| `017_generation_lifecycle_recovery.sql` | `76544a154a9230529cbb385958784e32dcfb93bcc17f358622f5b82ef721fdff` |
| `018_review_current_snapshot.sql` | `4e36271d5254343c228132f22e765dfe76b09a518e06a8f898d36701ea14012d` |
| `019_w4_source_readiness_config.sql` | `5ca0464ddaac534caa0f85c615cc31dee187bee32e5ee7a19609b976dd2ce6ba` |
| `020_private_export_ledger.sql` | `39884715f67eacd07468d909ff17cbc9871ca1a724f84e7d87890e2a40fadf82` |
| `021_w4_confirmed_source_fallback.sql` | `6730db5f18be9e18463f8ffcc08ede4ec6af7552810aa7412f8a924981665c67` |
| `022_w4_generation_solution_guard.sql` | `ef9c8ce310ad1a7c60576df80d3ce08e5c41a8f643e747d3a2b2fef5cdab682e` |
| `023_users_client_acl_hardening.sql` | `cac6973da49c9b5f5ca611b9eab2e794cb8c595b47bec812e88d2881b57c33a3` |
| `024_source_reuse_optional_solutions.sql` | `f1de510f8ad2bbcfd5f2e1a711b934995001c7b981c523de75d7541e71f68c9e` |

### Thứ tự khép task

1. Duy/Hùng khép #63 và renderer #82; lấy một dev SHA chung đã merge. Tính lại inventory từ SHA đó, không gọi inventory này là frozen candidate.
2. Dựng DB/Storage test local hoặc môi trường được phép; ghi DB alias, thực tế bootstrap/applied manifest/checksum, private bucket limits/ACL và test scope. Duy/DB owner xác nhận trước thao tác shared DB.
3. Kiểm catalog, PostgREST/ownership A-B và quota; chỉ bật export sau khi cấu hình/timeout đủ. Không tạo broad Storage policy để vượt test.
4. Build đúng FE/BE SHA; OPS chạy G0 UI→API→DB→Gemini→Typst→private Storage, ghi từng PASS/FAIL/BLOCKED, rồi giao Quỳnh Golden6slots và demo21. API/SQL fixture, hash hoặc smoke200 không thay E2E.

Evidence SQL/checksum được xác minh17/11; không có DDL, seed, bucket write hoặc export activation trong bước chuẩn bị này.

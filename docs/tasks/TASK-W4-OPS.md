# W4-MVP-11 / 21 — Plan OPS và bàn giao demo của Đạt

## Checkpoint hiện hành — 11/11/2026 (UTC+7)

- Author OPS11/21: Đạt; workflow v0.1 proposed. Nhánh tiếp nối `docs/w4-ops-integration-checkpoint`, base ban đầu `dev@294c69a1a085ac6487d65b633e06a2f1112e2046`; đã sync dev7601d67 sau khi #56 merge (chỉ docs), giữ nguyên SHA294c69a của runtime đã kiểm; không mở lại PR51 đã merge. Các checkpoint có ngày cũ phía dưới là lịch sử.
- PR51 preparation đã merge. PR52 đã merge thành `294c69a`; Đạt Approve sau 23/23 test PostgreSQL17 thật. Không còn chờ F01–F04 của PR52; **chưa có applied ledger trên DB ứng dụng**.
- PR54@`7c7200f`: Đạt [Approve](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/54#pullrequestreview-5857922227), 23/23 PostgreSQL15 + 198 API/review tests pass. PR56@`586604b`: [Approve docs](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/56#pullrequestreview-5857894388); không xác nhận policy adoption.
- PR61@`b327899`: [Request changes](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/61#pullrequestreview-5857931153). 230 passed/1 optional worker-probe skipped; F01 HTTP boolean coercion và F02 success khi receipt RPC thiếu/sai đã tái hiện, chờ Duy sửa. Không sửa nhánh author.
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

## Input cần trả lời trên Draft PR — nơi tổng hợp duy nhất

Áp dụng cách ghi đề xuất INPUT-20261109 tại [PR57@ef941be](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/57): không thay workflow/owner/gate hiện hành. Giữ ID cũ; ENV0 và quyết định quyền/roster vẫn có nguồn chuẩn Issue53, bảng này chỉ dẫn link và ghi phần đủ dùng cho task11/21. Mốc là need-by từ W4, ETA chưa có xác nhận ghi TBD.

| ID / yêu cầu gốc | Cung cấp → Đạt / mục đích đủ dùng | Mức và phần đã nhận | Còn thiếu / bước tiếp / need-by / ETA |
|---|---|---|---|
| [ENV0/Q12](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53) | Duy + người giữ quyền → OPS11; môi trường và authority để triển khai | Decided topology08/11; local Windows Docker build/health smoke đã chạy. Đủ dùng chuẩn bị local, chưa Accepted cho deployment online. | Host online/quyền/access gate/backup/roster theo Issue53; đề xuất máy Đạt chưa được duyệt làm host online. Duy điều phối; trước deploy; ETA TBD. |
| [DB0/Q08](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/51#issuecomment-6718841843) | Duy + Hùng → OPS11; manifest và candidate SHA để áp DB an toàn | Đã nhận quyết định017 sau016 và candidate inventory; chưa đủ để chạy migration trên shared DB. | Approved fresh+upgrade manifest, ledger/checksum, backup/restore/forward-fix, quyền và SHA tương thích; Duy/Hùng; need-by09/11 18:00; ETA TBD. |
| [I-OPS-LIFE](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6690592440) | Duy + Quỳnh → OPS11; policy để chuẩn bị cấu hình/ma trận smoke | Consumer Accepted cho chuẩn bị runbook: baseline1worker, startup+30s scan, batch100, cutoff720s, terminal15phút, cleanup60s, shutdown bounded đã chốt08/11. Code PR30@b6b6422 Delivered để review, chưa Integrated. | F02 reviewer verified tại b6b6422 (705pass/1skip, Ruff PASS); còn merge/pinned SHA rồi kiểm restart/SSE/proxy thật; Quỳnh module owner; trước integrated smoke; ETA TBD. Không xin lại policy đã giao. |
| [I-B-STALE](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/52) | Duy → OPS11; durable interruption/SQL contract | Consumer Accepted contract017; code merged vào dev294c69a. Đạt verified F01–F04 tại3d05949, PostgreSQL17:23pass/0skip và Approve. | Không chờ sửa/review52 nữa. Chờ DB0 applied ledger/checksum, quyền/backup và compatible #30 SHA để kiểm recovery thực. Trước lifecycle acceptance; ETA TBD. |
| [I-OPS-DB](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6690592440) | Duy + người giữ quyền → OPS11; identities A/B/admin/non-admin và phạm vi test | Requested; chưa có handoff đủ dùng để Auth/ownership smoke. | Cấp quyền qua kênh an toàn, seed/cleanup/quota và ADMIN_EMAILS owner/revoke; trước integration; ETA TBD. Không đăng JWT/secret. |
| [Q09/Q10](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_TASK_DETAIL.md) | Hùng + Duy → OPS11/21; private Storage/export config và API | Requested cho handoff OPS; chưa đủ dùng export live. | Contract/env names/upload-status-reissue/exported transition và quyền; Hùng/Duy; trước live export11/11; ETA TBD. |
| [Q14](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_TASK_DETAIL.md) | Quỳnh + Tâm + Duy → demo21; Golden3 câu N=2 và oracle | Requested; script/phiếu trống chuẩn bị được, chưa có Golden đã duyệt để chạy nghiệm thu. | Artifact/revision, permission, key/solution oracle, config/model/prompt; trước E2E; ETA TBD. |
| [Q20](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_TASK_DETAIL.md) | Duy + Hùng + Đạt → demo21; nơi lưu proof và quyền recording | Requested; không tự tạo cloud folder/chia sẻ dữ liệu. | Nơi lưu ZIP/video/log, quyền/retention/consent và người ký; trước pack12–15/11; ETA TBD. |

Đạt nhận chuẩn bị plan/runbook ngay. Duy điều phối input còn thiếu; không gán cam kết quyền hoặc ca trực thay người dùng. Phần Docker/CI thay đổi cụ thể sẽ phối hợp Quỳnh khi protected route sẵn; không cần Quỳnh chờ OPS để code unit/guard độc lập.

## Bàn giao và kiểm

- Đã làm: kiểm cấu hình tracked, inventory, plan/runbook và smoke checklist. Không đổi production config/API/schema/dependency nên chưa phát sinh ADR mới.
- Kiểm docs: link local tồn tại, UTF-8, git diff --check. Không chạy product tests cho thay đổi thuần docs; vẫn yêu cầu CI trước merge.
- Chưa kiểm: Docker build/run, TLS/OAuth thật, DB/RLS, Gemini, Storage, restart/FE/proxy live. ENV0 và integrated acceptance: BLOCKED chờ handoff, không phải LOCAL_READY cho toàn production private beta.
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

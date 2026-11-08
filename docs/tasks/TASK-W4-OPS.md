# W4-MVP-11 / 21 — Plan OPS và bàn giao demo của Đạt

- Owner phần chuẩn bị trong repo: Trương Thành Đạt (`Thanhdat3010`), bắt đầu 07/11/2026 theo yêu cầu trực tiếp. Quyền cloud, người thay thế và availability cuối tuần chưa được xác nhận; không suy từ quyền sửa repo.
- Nguồn: [W4 assignment v2.0](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_ASSIGNMENT%20%281%29.md), [task detail](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/51a919861089f0475a7a5f8ec16acfb0c41a3cd2/docs/tasks/W4_TASK_DETAIL.md). Bản nguồn còn ghi chờ owner xác nhận; lời Duy ưu tiên khép PR cũ trước W4.
- Workflow v0.1 proposed, docs baseline `506384b`; author mode, M2/M3. Nhánh `docs/w4-ops-runbook`, rẽ từ dev `73583d7`. Reviewer đề xuất Duy (BE/OPS), Hùng (Storage), Quỳnh nhận môi trường; chưa có approval.
- Deadline dưới đây theo W4, UTC+7; là mốc cần giao, chưa phải ETA đã xác nhận. Không thay bằng lịch tuần thông thường.
- Runbook: [W4 private beta](../w4-production private beta-runbook.md).
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

## Input cần trả lời trên Draft PR

| ID / owner cung cấp | Input cụ thể | Trạng thái / cần trước / ETA |
|---|---|---|
| ENV0/Q12 — Duy + Đạt | Máy/host/domain test dùng gì, ai cấp quyền deploy/OAuth/Supabase; backup và lịch phối hợp07–08/14–15 | Chưa nhận; trước deploy; ETA TBD. Mốc06/11 đã qua, không tự nhận gate PASS |
| DB0/Q08 — Duy + Hùng | Ledger migrations fresh+upgrade, isolated project, pinned compatible backend SHA, rollback/forward-fix và người thực thi | Chưa nhận handoff môi trường; cần09/11 18:00; ETA TBD |
| I-OPS-LIFE — Duy + Quỳnh | Chốt1worker, source/query quét stale, interval, terminal retention và active subscriber policy | Đề xuất giữ1worker theo Dockerfile hiện có; Quỳnh đã nhận baseline để triển khai/test cô lập tại comment6703279898: startup+30s, batch100 có pagination, cutoff720s DB lock, terminal15phút/cleanup60s, shutdown10s. SQL/RPC017 đã giao tại PR52@5b3f433, Quỳnh đã nối tại PR30@b1f0999; chưa merge/applied/live; chưa nghiệm thu production private beta. Cần trước lifecycle wiring; TBD |
| I-B-STALE — Duy | Persist ERR_GENERATION_INTERRUPTED theo migration017 | Đã chốt bởi Duy; PR52 open, independent SQL/ACL + real-DB proof và DB-applied ledger còn thiếu |
| I-OPS-DB — Duy + OPS | Accounts A/B/admin/non-admin, quyền seed/cleanup, JWT qua kênh an toàn, phạm vi/quota live, ADMIN_EMAILS owner/revoke | Chưa nhận; trước integration smoke; TBD |
| Q09/Q10 — Hùng + Duy | Bucket private, tên biến chính thức, upload/status/reissue contract và exported transition | Không tự đặt env Storage khi chưa có contract; cần trước live export; TBD |
| Q14 — Quỳnh + Tâm + Duy | Golden Markdown3 câu có quyền dùng, oracle đáp án/lời giải, N=2, prompt/config version | Chưa nhận artifact đã duyệt; trước E2E; TBD |
| Q20 — Duy + Hùng + Đạt | Nơi lưu ZIP/video/log, quyền xem/retention, người ký | Trước evidence pack12–15/11; TBD |

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

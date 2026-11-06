# TASK-207c — Plan và bàn giao W2: Runtime metrics có Auth

## Kiểm lại input ngày 06/11/2026 — nhánh Quỳnh, Draft PR #30

- Local `feat/task-207-w2-backend@dc8e0d4` theo dõi remote
  `feat/task-207c-runtime-metrics`; base PR `e82b8ed`,
  `origin/dev@73583d7` sau fetch. Dev mới thêm AI contract PR #41;
  chưa merge commit này vào nhánh Quỳnh và chưa kiểm lại regression trên bản
  tích hợp.
  C2 và tài liệu liên quan còn WIP chưa commit. Giữ các thay đổi local và
  file untracked khác; Quỳnh tự commit/push, PR #30 vẫn Draft.
- **C2 đủ input code:** Đạt/Hùng đã giao ranh giới observer ở actual Gemini
  dispatch. Gateway/runtime/bridge và test fixture đã có trong WIP; cần kiểm
  lại trên đúng head rồi nhờ AI owner review shared gateway diff. PR #41 đã
  merge vào dev sau head của nhánh này; cần đối chiếu khi đồng bộ nhưng không
  đổi ranh giới observer đã được Đạt đồng ý.
- **C1 chờ Duy:** `get_current_admin_user` đã có ở
  `backend/app/api/dependencies.py`; nguồn hiện tại là server `ADMIN_EMAILS`,
  chỉ development cho phép mọi user đã xác thực, môi trường khác kiểm email
  trong allowlist. Cần Duy xác nhận policy nghiệm thu và test identities trước
  khi dùng helper để bảo vệ metrics route. Không tạo role field/helper thứ hai.
- **C3/C4 chờ OPS/Duy:** 207b đã mount runner/job/SSE với cùng registry và
  AIRuntime trong `main.py`, nhưng observer/collector chưa inject; metrics
  handler vẫn public. Cần chốt lifecycle một worker, ownership sửa
  `scripts/dev.ps1` và Docker CI, smoke 401 qua proxy. Thay route và hai smoke
  cùng lượt sau khi input đủ.
- **C5 live chờ OPS/Duy:** chưa có môi trường cô lập, JWT admin/non-admin,
  quyền DB/Gemini/proxy và phạm vi smoke. Fixture không chứng nhận live
  PostgREST/RLS, Gemini, FE hoặc proxy. Assignment W2/reviewer/ETA vẫn cần
  Duy xác nhận.
- **Kiểm WIP trên nền `dc8e0d4` trong lượt này:** Python 3.12.10 Windows,
  venv tạm ngoài repo cài từ `backend/requirements.txt` (không phải lockfile
  Linux của CI). Nhóm gateway, AI pipeline, batch integration, observability:
  **245 pass, 1 skip**. Ruff lint app/Blueprint và ba file test WIP đạt;
  Mypy app đạt **113 source files**; Ruff format đạt cho bốn file Python vừa
  sửa/kiểm riêng, còn format cũ ở ba đoạn đầu `test_gateway.py` ngoài WIP.
  `python -m compileall -q` và `git diff --check` đạt. Windows sandbox chặn
  socketpair của asyncio nên pytest chạy ngoài sandbox; Docker daemon chưa
  khởi động được. Chưa có Docker Python 3.11/lockfile, DB/RLS, Gemini thật
  hoặc proxy acceptance trên WIP này.

## Cập nhật M2 ngày 04/11/2026 — PR #30

- **C0 đã đồng bộ** ở `1a2e05a`, chứa `dev@ac18e72` và PR #30
  `5cd570b`. [Baseline](TASK-207a.md#cập-nhật-m2-ngày-04112026--pr-30)
- **C2 đã triển khai để inject.** Đạt đã xác nhận phạm vi hook ở gateway.
  `AIRuntime` nhận observer tùy chọn và truyền cho gateway dùng chung.
  `make_gemini_attempt_observer` nối SDK dispatch với registry đã start.
  Provider success, error, timeout và cancel có kết quả riêng; local
  validation giữ nguyên trạng thái transport. Xem
  [contract và ranh giới dispatch](../api/runtime-metrics-endpoint.md#gemini-attempts-and-errors).
  [Bàn giao AI của Đạt](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6601308632)
- **C1 và C3–C5 còn chờ.** Duy đã bàn giao nguồn admin một phần, còn cần
  xác nhận policy môi trường `test` và cách ghép Auth. Registry, collector
  và observer chờ wiring cùng lifespan, producer job/SSE thật và điều kiện
  smoke Auth/proxy của OPS. C2 có kiểm offline độc lập trong lượt này.
  [Bàn giao Auth của Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6503019229)
  · [TASK-207b](TASK-207b.md#cập-nhật-m2-ngày-04112026--pr-30)
- **C6.** Đã cập nhật phần contract observer. M3 ghi theo head và checks thực
  tế khi Quỳnh cập nhật Draft PR. Mốc cần input và ETA vẫn TBD.
- **Đã kiểm local.** Ruff lint đạt cho app, Blueprint và ba file test đã sửa.
  Mypy đạt trên 92 file app. Ruff format đạt cho năm file Python và vùng hai
  test đã sửa trong `test_generation_pipeline.py`; phần còn lại của file
  có chênh lệch format từ baseline. `git diff --check` đạt.
  [Kết quả test offline](TASK-207b.md#kết-quả-kiểm-local-trên-bản-tổ-hợp)

## Snapshot M2 trước đồng bộ

- Trạng thái: **Draft — plan/input**, 29/10/2026 (Asia/Saigon); không triển khai code trong lượt này.
- Assignment: `w2_21_10.md` mục TASK-207c do Quỳnh cung cấp; file untracked, link/version chung chờ Duy. Giữ đủ 6 metrics W2, không chuyển sang bản demo rút gọn hay TASK-401.
- Owner: Quỳnh / `nhatquynh1107`; reviewer đề xuất Duy (Auth), Đạt/Hùng (AI hooks), OPS (lifecycle/CI), chưa được xác nhận.
- Checkout `dev@813f4976ac95a336eed8f71ec77b3426eef6edf5`; modules 207 đọc từ nhánh local `feat/task-207c-runtime-metrics@97546d8a94c6eff719bc150b49866ac7b7a3c302`, chưa nằm trong dev.
- Nhánh/PR gửi do Quỳnh xác nhận; lượt này không checkout/merge/commit/push/tạo PR. Plan cần có trên nhánh task trước khi dùng làm M2 chung.
- Workflow PR23 v0.1 — proposed, docs head `7a6ffc2bab0fedf8e5e66b2485370ae8daab0f01`, merge `506384b`; [WORKFLOW](../review/WORKFLOW.md), [M2–M5](../review/TEMPLATES.md).
- Hạn W2/ETA: cần Duy xác nhận khác biệt file W2 21–31/10 và TASK-206 ghi28/10; không dùng hạn W3. Ngày cần input/ETA giao/ETA hoàn tất task bên giao và Quỳnh: TBD.

## Mình cần làm gì?

- `GET /api/health/metrics` qua `get_current_user`: user đã xác thực trong server development được phép; ngoài development cần admin từ nguồn đáng tin. Không cho anonymous ở dev.
- Trả uptime_seconds, active_sse_connections, gemini_call_count, gemini_error_rate, background_jobs_running, process_memory_mb; giữ status/gemini_model; no-store.
- Một registry mỗi worker/lifespan, metrics runtime khác quota session250 và quota review30. Theo dõi actual provider attempts, không coi validation fail là Gemini transport error.
- RSS tiến trình Linux Docker, không phải RAM cả máy/peak RSS. Collector lỗi trả503 an toàn; không bù số0 để che nguồn chưa nối.
- `/health` vẫn public cho liveness. Ngoài scope: metrics sư phạm401, hệ thống distributed monitoring, UI dashboard mới, tự cấp admin/schema Auth hay sửa Docker/dependencies khi chưa có phạm vi phối hợp.

## Hiện đã có và giới hạn

| Nguồn | Có gì | Phần còn lại |
| --- | --- | --- |
| Nhánh Quỳnh `models/runtime_metrics.py`, `services/observability/runtime_registry.py` | Model strict, monotonic uptime, handles idempotent cho SSE/job/provider; completed/failed ratio | Chưa start/wire trong main thật |
| Nhánh Quỳnh `process_memory.py`, `collector.py` +4tests observability | Linux RSS, snapshot mới, safe failure | Chưa endpoint/guard/instrumentation thật |
| Nhánh Quỳnh207b | Broker/runner nhận cùng registry; ProviderCalls dành raw outbound | Runner hiện chưa nối batch/gateway; bọc nguyên generate_exam_drafts sẽ đếm sai và double quota |
| dev `main.py`, `services/ai/runtime.py`, `ai/gateway.py` | AIRuntime app-scoped/lazy, reserve hook trước mỗi outbound, SDK attempts=1 | RequestContext chỉ deadline/reserve_request; không có outcome hook success/failure/cancel |
| dev `api/dependencies.py`, `models/schemas.py` | Verified CurrentUser: id/email/name/access_token; user DB và service_role helper | Chưa business admin source/helper. Không suy admin từ user_metadata/service_role |
| dev `api/routes/health.py` | Public metrics chỉ status/gemini_model | Cần thay handler cùng smoke; hiện chưa đạt207c |
| dev `scripts/dev.ps1`, `.github/workflows/docker-ci.yml` | Smoke mong unauthenticated metrics200 | Phải phối hợp đổi thành kiểm401 qua proxy khi bảo vệ route; không thêm auth bypass |

## File và thứ tự triển khai

| Lượt / file dự kiến | Mục đích sửa | Output | Input cần trước | Cách kiểm |
| --- | --- | --- | --- | --- |
| C0 — nhánh task/plan | Tiếp nối modules sẵn có sau đồng bộ có quyền | Baseline tổ hợp chính xác | Quỳnh chọn nhánh/thao tác như [207a A0](TASK-207a.md) | Git diff; không nhận tests cũ là checks mới |
| C1 — file mới dự kiến `backend/app/api/metrics_access.py`; `api/dependencies.py`/`models/schemas.py` chỉ nếu owner giao | Guard dùng verified user và trusted admin helper | Dev authenticated allow, production admin allow, non-admin/missing deny; lookup fail rõ | I-C-ADMIN | Isolated API tests401/403/200, forgedmetadata, unknownenv, lookupfailure; không dựng fieldadmin tùy ý |
| C2 — file mới dự kiến `backend/app/services/observability/ai_instrumentation.py`; phối hợp `services/ai/gateway.py` và `runtime.py` | Hook đúng transport boundary, một lần/attempt | Success/failure/cancel metrics cho Blueprint/variant/repair; quota giữ nguyên | I-C-ATTEMPTS, ownerAI đồng ý shared files | Spy transport, timeout, 429/5xx/network/cancel; validation fail sau response không tăng error rate; khôngdouble count |
| C3 — `backend/app/main.py`, `api/routes/health.py` hoặc route metrics riêng owner thống nhất; collector khi cần | Start registry/collector một lần; thay đúng1handler; giữ AIRuntime hiện có | Protected response đủ metrics/no-store, lỗi503; /health200 public | C1/C2; I-OPS-LIFE và hooks207b | App lifecycle, restartreset, currentRSS, không gọi AI khi poll, no duplicate route |
| C4 — `scripts/dev.ps1`, `.github/workflows/docker-ci.yml` | Cập nhật smoke theo auth contract, cùng đợt tích hợp C3 | Anonymous metrics 401 + auth challenge qua proxy; /health200 | OPS/Duy xác nhận owner và phạm vi | PowerShell5.1/7 phù hợp; Docker/proxy smoke; khôngcommit JWT |
| C5 — `backend/tests/observability/test_*.py`, file mới dự kiến `backend/tests/api/test_runtime_metrics.py`; tests AI/207b liên quan | Kiểm counters và Auth thật ở adapter hợp lệ | Bằng chứng currenthead, gauges trả 0 sau cleanup, memoryfail503 | C1–4, test accounts I-OPS-DB | Concurrenthandles/failure/cancel; isolated tests trước, live smoke theo môi trường được cấp |
| C6 — `docs/api/runtime-metrics-endpoint.md`, `generation-integration-inputs.md`, plan | Contract/coverage thật và M3 bàn giao | Phân biệt gauges/quotas, snapshot readiness và giới hạn | Checks/replies hiện hành | Docs/link/diff; change_log nếu đổi contract theo CONTRIBUTING |

Không cần chờ mọi phần207a/b mới phát triển metrics độc lập; nhưng không nghiệm thu gauge job/SSE thật khi producer207b chưa mount. Việc sửa shared files AI/Auth/CI cần owner xác nhận, không yêu cầu họ viết thay toàn bộ code Quỳnh.

## Đầu vào và câu hỏi — Conversation của Draft PR Quỳnh

Mỗi dòng ghi task/nguồn của bên cung cấp và task nhận input ngay tại mục đó. Các PR/contract được dẫn là nguồn liên quan đã đọc, không chứng nhận input mới đã được triển khai. Task hỗ trợ chưa được giao riêng phải nhờ Duy xác nhận; không tự mở rộng scope task cũ.

| ID / người giao → nhận | Input cụ thể cần bàn giao | Cần trước / ETA input / ETA xong task bên giao | Làm ngay/chờ; bằng chứng |
| --- | --- | --- | --- |
| I-C-ADMIN — Duy → Quỳnh | Nguồn business admin đáng tin ở đâu (verified app_metadata hay bảng quản lý role)? Helper tên/signature/return/error, chính sách missing/unknown role/DB failure và test users admin/non-admin. Ai cấp/revoke và source có trong commit nào? Giữ development chỉ user đã xác thực, không dùng service_role database như role người dùng<br>**Task/nguồn liên quan:** Duy — TASK-102 (Auth, tuần 1), [helper hiện có](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/813f4976ac95a336eed8f71ec77b3426eef6edf5/backend/app/api/dependencies.py); [API conventions](../api/endpoint-conventions.md). Trusted admin là hỗ trợ TASK-207c, chưa có task Auth riêng mới được xác nhận.<br>**Task nhận input:** Quỳnh — [TASK-207c](TASK-207c.md). | Trước C1; ngày TBD / TBD / TBD | Model/collector đã có; guardproduction chờ. CurrentUser trên dev chưa có role/helper |
| I-C-ATTEMPTS — Đạt/Hùng + Quỳnh | Chốt hook/API success/failure/cancel tại `GeminiGateway.generate_content`, phạm vi Blueprint/candidate/repair, owner shared file. Đề xuất callback observer không đụng durable reserve; xác nhận cách xử lý timeout/cancel/in-flight và observer lỗi. Xin fixture/result các ca; không yêu cầu viết lại gateway<br>**Task/nguồn liên quan:** Đạt/Hùng — TASK-203/402, [PR #18](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/18), [PR #21](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/21) và [contract AI W2](../ai-w2-integration.md); Quỳnh — [TASK-207b](TASK-207b.md) và [TASK-207c](TASK-207c.md) phối hợp viết instrumentation.<br>**Task nhận input:** Quỳnh — [TASK-207c](TASK-207c.md). | Trước C2 / TBD / TBD | Reservehook đã có nhưng không báo outcome; mappingmetrics thuộc Quỳnh |
| I-OPS-LIFE — Duy + OPS (xác nhận đầu mối) + Quỳnh207b | Một app registry/worker và AIRuntime; startup/shutdown, job/SSE handles, cleanup/recovery; ai phối hợp sửa main/CI? RSS Linux là target, không tự thêmdependency<br>**Task/nguồn liên quan:** OPS — TASK-004 (môi trường tuần 1, đầu mối chưa chốt), [Docker setup](../setup-docker.md); Duy điều phối; Quỳnh — [TASK-207b](TASK-207b.md).<br>**Task nhận input:** Quỳnh — [TASK-207c](TASK-207c.md). | Trước C3/C4 / TBD / TBD | Single worker/proxy đã có; còn wiring/lifecycle thật |
| I-OPS-DB — Duy + OPS → Quỳnh | Môi trường test, identities admin/non-admin, cách lấy test JWT an toàn, acceptance Auth/DB/AI/proxy smoke và quota thử<br>**Task/nguồn liên quan:** OPS — TASK-004 (môi trường tuần 1, đầu mối chưa chốt), [Docker setup](../setup-docker.md); Duy điều phối; Duy hỗ trợ DB theo [schema DB hiện có](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/813f4976ac95a336eed8f71ec77b3426eef6edf5/backend/scripts/schema.sql).<br>**Task nhận input:** Quỳnh — [TASK-207c](TASK-207c.md). | Trước C5 live / TBD / TBD | Isolated tests dùngfixture; chưa nhận credentials hay quyền chạyshared DB |
| I-W2-PLAN — Duy + Quỳnh | Xác nhận link assignment/hạn W2/reviewer và mốc giao output phù hợp chuỗi 207<br>**Task/nguồn liên quan:** Duy — leader/M1, [WORKFLOW §3](../review/WORKFLOW.md); link assignment W2 chung còn thiếu.<br>**Task nhận input:** Quỳnh — [TASK-207c](TASK-207c.md). | Trước chốt lịch / TBD / TBD | Không lấy lịch W3 của PR26/27 |

Xin mỗi owner trả tại Conversation kèm link contract/commit, JSON/helper mẫu, checks thật, pending, người xác nhận/thời điểm; tách ETA input với ETA xong task. Thiếu input chỉ dừng phần phụ thuộc; nhờ Duy điều phối nếu không còn thời gian kiểm/review. Quyết định mới được chấp nhận trong lượt này: chưa có.

## Kế hoạch tự kiểm

- Model/registry/collector/RSS regressions; fake clock không ảnh hưởng wall clock; thread/async cleanup không âm/đếm đôi, in-flight khỏi mẫu số error rate.
- API: anonymous mọi env 401; development authenticated 200; production admin 200, non-admin/missing role 403; upstream Auth lỗi giữ mã phù hợp; role lookup fail đóng quyền theo contract; no-store và safe 503.
- Raw calls: request queued không tính; mỗi actual dispatch tính 1; timeout/API error tính failed; cancel unknown không giả thành success; schema/math fail sau successful response không phải transport error.
- Tích hợp job/SSE thật cùng registry: accepted job chưa executing không tính, failed handshake không tính, disconnect/ASGI failed send/cancel giải phóng; poll metrics không gọi Gemini.
- Ruff/Mypy/backend tests/format/diff và CI áp dụng; smoke Docker/proxy không bypass Auth; live dùngtest account theo phạm vi đã giao.

## Bàn giao và M5

- Output cho OPS/Duy: response/access/error contract, smoke instructions và kết quả thật; choAI/207b: lifecycle/observer contract và cases. ETA chưa xác nhận.
- Đã làm: đọc code dev +207 riêng, rules/assignment và plan/Conversation tham khảo PR26/27; lập M2. Chưa chạy product tests/live trong lượt này.
- Chưa hoàn thành protected endpoint/admin/raw AI hooks/main/OPS smoke; không nhận Done vì model tests từng đạt. Chưa córeview/approval cho plan này.
- M3 Draft khai scope/input/pending; Ready/re-review cập nhật head sau push và checks. M5 chỉ khi có finding M4 thật: cùng ID/thread, author claimed_fixed có commit/cách kiểm/giới hạn, reviewer xác minh độc lập thành verified/open/disputed/inconclusive. Không tạo finding giả hoặc dùng M5 thay bàn giao input.


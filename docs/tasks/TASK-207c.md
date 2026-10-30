# TASK-207c — Plan và bàn giao W2: Runtime metrics có Auth

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


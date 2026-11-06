# TASK-207a — Plan và bàn giao W2: API cấu hình sinh đề

## Triển khai local 06/11/2026 — chưa push PR #30

- **Đã làm trên working tree sau `0424059`:** request giữ mode ID chính xác;
  response nhận đủ receipt SQL. Preflight dùng
  `get_generation_source_snapshot` làm nguồn canonical, chỉ đọc
  `question_blueprints` khi RPC trả đúng `NO_CONFIRMATION`; kiểm approved/status,
  giao mode theo profile 1.0, chuẩn hóa đúng `["NONE"]` thành `[]`. Repository
  gọi một lần `save_generation_config` với manifest gốc ở
  `p_expected_snapshot`, xác thực receipt và không tự retry kết quả ghi không
  chắc chắn. Router config đã mount vào app thật bằng authenticated user client.
- **HTTP do BE2 chốt với Quỳnh:** mode xung đột `400 ERR_CONFIG_CONFLICT`,
  source chưa ready `422 ERR_SOURCE_NOT_READY`; snapshot/state đổi khi save
  `409 ERR_CONFIG_CONFLICT`. Bảng HTTP trong contract PR #32 đang ghi 422/409
  cho hai trường hợp đầu, cần Duy chỉnh theo scope PR #30. Tên migration trong
  contract 010/011 cũng cần đối chiếu lại với file dev 015/016.
- **Đã kiểm local:** 301 tests passed (bốn file test 207a, `test_sessions.py`,
  `test_gateway.py`) trong container Python 3.11 tạm từ image backend cũ, có
  cài `jsonschema==4.26.0` riêng cho lượt test; Ruff đạt cho file sửa, Mypy
  đạt trên 111 source files. `python -m compileall` và `git diff --check HEAD`
  đạt. Đây là fixture/mock-RPC và code thật, chưa chứng minh PostgREST/RLS thật.
- **Chưa kiểm/chưa chấp nhận:** DB cô lập áp migrations và owner/non-owner qua
  Supabase/PostgREST, FE GET detail → POST config → reload, CI trên head PR #30
  mới. Remote PR vẫn ở head cũ; không coi CI cũ là bằng chứng cho local diff.
  User sẽ tự đăng comment/push theo quyền; không có GitHub Approve hay merge.

## Thứ tự tích hợp cập nhật 06/11/2026 — PR #30

- **Đã đồng bộ Git, chưa nối code sản phẩm.** Nhánh local
  `feat/task-207c-runtime-metrics@0424059` đã merge `origin/dev@e82b8ed`,
  còn trước remote PR #30 `5cd570b` 20 commit. Thay đổi đang làm đã được
  phục hồi: 10 file tracked chưa stage và 3 file untracked; hai stash vẫn
  được giữ. Conflict của `docs/api/generation-config-endpoint.md` đã giải
  theo contract dev, và conflict import trong `test_gateway.py` đã gộp cả
  hai phía. PR #30 vẫn Draft, head remote cũ; CI của PR không kiểm bản
  local chưa push. `git diff --check HEAD` và py_compile file test đạt;
  chưa chạy pytest vì Python hiện tại thiếu pytest và Docker daemon chưa chạy.
  `origin/dev` đã nhận PR #40 (FE2), #43 (canonical readiness) và #32
  (SQL/RPC, gồm Original Clone).
- **Input.** Contract SQL/RPC đã merge vào dev ở migrations 015/016;
  [PR #32](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/32)
  là nguồn bàn giao. PR #41 AI contract/seed guard còn open và conflict;
  PR #36 TASK-302 còn open, cần owner đối chiếu dev trước khi merge.
  Không gọi fixture/CI độc lập là nghiệm thu worker, SSE hoặc Supabase.

| Thứ tự | Phần Quỳnh thực hiện | Điều kiện và cách kiểm |
| --- | --- | --- |
| 0 — đã làm local | Bảo toàn thay đổi local và ghép `origin/dev` vào nhánh PR #30; lấy contract dev cho `docs/api/generation-config-endpoint.md`, giữ bản HTTP cũ trong Git history để cập nhật theo policy mới. | Backup `.artifacts/branch-sync-20261106-154602`, hai stash và worktree đã phục hồi; chưa push. Đối chiếu migrations 015/016 trên dev thay vì số cũ trong tài liệu. |
| 1 — 207a | Đổi preflight canonical sang `get_generation_source_snapshot`, truyền nguyên manifest bằng `p_expected_snapshot` khi save, dùng public mode profile và mã lỗi nghiệp vụ. Mount route sau khi inject store thật. | Canonical ready không có legacy Blueprint vẫn cấu hình được; revision đổi, mode sai và owner sai bị chặn. |
| 2 — 207b | Nối claim/quota/full-result persist/load/finish/fail-stale. Tách `AI_RESULT` và `ORIGINAL_CLONE` trước resume; clone record riêng, zero Gemini, lưu trước shuffle. | PostgreSQL cô lập: slot đã commit không sinh lại, retry phần thiếu, quota/fencing/finish đúng; dùng AI fingerprint thật, không dùng synthetic hash của SQL receipt. |
| 3 — 207b FE | Bổ sung durable generation snapshot, cursor/epoch và ticket/history-loss contract cho FE2 đã merge; mount job/stream routes. | Reload partial, buffer overflow, restart, đổi phiên và SSE reconnect qua app thật. |
| 4 — 207c | Hoàn tất admin guard, gateway observer, registry/lifespan, metrics route và smoke Auth/proxy. | Đạt review shared gateway; job/SSE gauges chỉ nghiệm thu khi producer được mount. |
| 5 — bàn giao | Chạy tests theo phần sửa, DB integration, sau đó FE/SSE E2E; cập nhật M2/M3 theo head và checks thực tế trước khi đưa PR #30 đi review. | PR #41 cần owner xử lý conflict/review; môi trường Supabase/proxy cần Duy/OPS cung cấp cho nghiệm thu triển khai. |

Mục 04/11 bên dưới là lịch sử M2 tại head cũ; các trạng thái “chờ PR #32”
không còn mô tả input hiện tại sau khi PR #32 đã merge.

## Cập nhật M2 ngày 04/11/2026 — PR #30

- **A0 đã đồng bộ.** Baseline nhánh `feat/task-207c-runtime-metrics` là
  `1a2e05a`, chứa cả `dev@ac18e72` và đầu nhánh Draft PR `5cd570b`.
  Cả hai phép kiểm `git rev-list --count HEAD..<ref>` đều trả `0`.
  [Draft PR #30](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30)
- **A1–A3 chờ DB và contract.** Duy đã bàn giao chữ ký RPC để đối chiếu với
  adapter. Tại lần đọc gần nhất, PR #32 ở `31ed3bc` còn F01–F06 cần tác giả
  xử lý và reviewer xác minh. Khi đủ input, kiểm lưu nguyên tử và chọn cấu
  hình hiện hành trước khi inject store thật hoặc mount router. Quyết định
  readiness, mode IDs và `[]`/`NONE` vẫn cần Duy, Đạt/Hùng và Bội Anh chốt
  cùng canonical Blueprint và confirmed source hash.
  [Bàn giao Duy cho TASK-207a/b/c](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6503019229)
  · [PR #32](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/32)
  · [Bàn giao AI](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6601308632)
  · [TASK-206/208](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6597584297)
- **Tiếp theo.** Sau khi xác minh DB, ghép A1 → A2 nếu contract cần →
  A3 → kiểm A4 trước khi ghép job thật. Kết quả kiểm offline của bản tổ hợp
  ghi trong [TASK-207b](TASK-207b.md#cập-nhật-m2-ngày-04112026--pr-30).
  Mốc cần input, ETA người giao và ETA hoàn thành W2 vẫn TBD.

## Snapshot M2 trước đồng bộ

- Trạng thái: **Draft — plan/input**, cập nhật 29/10/2026 (Asia/Saigon); lượt này chỉ lập tài liệu.
- Nguồn giao việc: `w2_21_10.md` do Quỳnh cung cấp, mục TASK-207a; file đang untracked, chưa có link assignment chung được xác minh. Nhờ Duy cung cấp link/version W2; không xuất bản assignment thay leader.
- Owner: Quỳnh / `nhatquynh1107` (BE2). Reviewer đề xuất: Duy (DB/Auth), Bội Anh (consumer FE); chưa xác nhận nhận review.
- Checkout lúc đọc: `dev@813f4976ac95a336eed8f71ec77b3426eef6edf5`. Code Quỳnh được đọc bằng Git từ `feat/task-207c-runtime-metrics@97546d8a94c6eff719bc150b49866ac7b7a3c302`, chứa cả 207a/b/c, chưa nằm trong dev. Nhánh 207a cũ ở `5f9efc0` không phải bản tổng hợp mới nhất.
- PR/nhánh dùng để gửi: Quỳnh xác nhận khi chuẩn bị PR; chưa tạo/chuyển nhánh, commit hoặc push từ lượt này. Đưa plan lên nhánh task trước khi dùng làm M2 chung.
- Workflow: v0.1 — proposed theo PR23, docs head `7a6ffc2bab0fedf8e5e66b2485370ae8daab0f01`, merge `506384b`. [WORKFLOW](../review/WORKFLOW.md), [M2–M5](../review/TEMPLATES.md).
- Hạn/ETA: W2 nguồn ghi 21–31/10, TASK-206 ghi hết W2 28/10; nhờ Duy xác nhận hạn phần W2 tồn đọng. Không tự chuyển sang hạn W3 03/11. ETA task và các mốc giao nhận: **TBD, chờ người phụ trách xác nhận**.

## Mình cần làm gì?

- `POST /api/sessions/{session_id}/config`: Auth/ownership; N nguyên từ 1–4; modes thuộc giao các Blueprint đủ và đã xác nhận; mode không hỗ trợ trả 400 `ERR_CONFIG_CONFLICT`.
- Lưu cấu hình và chuyển `configured` nguyên tử; không thay bằng hai lần ghi riêng. Tái kiểm trạng thái/Blueprint trong transaction để chống thay đổi sau preflight.
- Giữ IDs phân biệt hoa/thường; nhận hai cờ ordering độc lập. Lưu lựa chọn không đồng nghĩa thực thi shuffle ở bước này.
- Ngoài phạm vi: SQL/RPC của Duy, AI extraction, generator/validator mới, UI, shuffle/finalize/export W3. Python adapter lưu config thuộc Quỳnh sau khi có contract.

### Hiện đã có — bằng chứng đọc source, chưa phải E2E

| Nguồn | Có gì | Chưa nối/điểm cần chốt |
| --- | --- | --- |
| Nhánh Quỳnh: `backend/app/models/generation_config.py`, `services/generation/config_service.py` | Models strict; N; modes; trạng thái blueprinted/configured; 1–20 sources và đủ confirmed Blueprint | Cho phép modes rỗng; ý nghĩa khi gọi AI phải chốt, không suy là giữ nguyên đề |
| Nhánh Quỳnh: `config_repository.py`, `api/routes/generation_config.py` | Read adapter, `GenerationConfigStore.save_config` Protocol và router factory; tests model/policy/repository/API | Read adapter chưa implement save; main chưa mount router |
| dev: migrations 002/003 | RPC replace-source và `confirm_exam_source`; confirm có khóa phiên/confirmed_at | Không phải RPC lưu config. Schema generation_configs chưa có UNIQUE session_id hoặc chính sách chọn current config |
| dev: TASK-205, AI, ADR0001 | Confirm API + AI canonical services cùng có source | Confirm vẫn tạo fallback ±5; chưa bàn giao canonical JSON/hash mà AI cần; ADR yêu cầu confirm trước extraction |
| dev: FE PR22 | Gửi đúng n_versions/active_variation_modes; phân biệt hoa/thường; gửi shuffle_options rõ ràng | FE mặc định gửi shuffle_options=false, BE mặc định thiếu field là true; không tự đổi default. Session detail chưa trả saved config/Blueprint summary |

Nguồn nhóm: [confirm contract](../api/confirm-source-endpoint.md), [ADR0001](../adr/0001-confirm-before-blueprint.md), [AI integration](../ai-w2-integration.md), [TASK-206](TASK-206.md).
Các file Quỳnh nêu trên tồn tại ở commit local 97546d8, không giả định đã có trong checkout dev hoặc trên GitHub.

## File và thứ tự triển khai — tiếp nối W2, không làm lại phần đã có

| Lượt / file dự kiến | Mục đích sửa | Output mong muốn | Input cần trước | Cách kiểm |
| --- | --- | --- | --- | --- |
| A0 — nhánh task và ba plan W2 | Quỳnh chọn nhánh; đồng bộ dev vào nhánh task theo thao tác được giao sau | Code 207 hiện có cùng baseline nhóm, giữ mọi thay đổi | Quỳnh chỉ định nhánh/hành động Git; không checkout/merge trong lượt plan | Kiểm branch/head/diff; không dùng kết quả tests cũ chứng nhận bản tổ hợp |
| A1 — `backend/app/services/generation/config_repository.py` | Bổ sung adapter thực hiện `save_config`, mapping lỗi/response đúng RPC | Config + trạng thái được lưu nguyên tử | I-A-SAVE; dữ liệu confirmed/modes từ I-B-AI/I-B-POLICY trong 207b | Fake RPC kiểm call/response/error; DB thật kiểm lock/race/rollback |
| A2 — `backend/app/services/generation/config_service.py`, `backend/app/models/generation_config.py` (chỉ nếu contract đã chốt cần đổi) | Đồng bộ readiness/modes với canonical và FE | Không coi fallback đủ điều kiện AI; không dịch mode tùy ý | Duy + AI + Bội Anh chốt mapping và []/NONE | Modes giao, case-sensitive, thiếu BP, fallback, nguồn thay đổi, request không mutate |
| A3 — `backend/app/api/routes/generation_config.py`, `backend/app/main.py` | Inject store thật, mount một route | API thật giữ Auth/ownership/rate limit và lỗi an toàn | A1/A2 đủ; phối hợp owner main, không tạo client quyền cao để né RLS | API success/401/403/404/400/409/422/storage failure; kiểm route không trùng |
| A4 — `backend/tests/generation/test_config_*.py`, `backend/tests/api/test_generation_config.py` | Cập nhật regression và thêm DB integration theo môi trường đã chốt | Bằng chứng đúng revision, tách fixture/DB thật | I-OPS-DB và RPC deploy test | Concurrent saves, source/config race, non-owner, commit response bị mất không ghi lại mù |
| A5 — `docs/api/generation-config-endpoint.md`, `docs/api/generation-integration-inputs.md` và plan này | Ghi contract thực tế và output cho FE/207b | Một nguồn contract; M3 cùng head sau push | Replies/commit owner + kết quả thực chạy | Đối chiếu payload/links, docs diff; change_log nếu thay contract theo CONTRIBUTING |

`sessions.py`/`models/schemas.py` để trả detail do Duy sở hữu: nhờ Duy cập nhật hoặc xác nhận giao Quỳnh sửa phần cụ thể; chưa mặc định nằm trong code scope Quỳnh.

## Đầu vào và câu hỏi — đăng tại Conversation của Draft PR Quỳnh

Mỗi dòng ghi task/nguồn của bên cung cấp và task nhận input ngay tại mục đó. Các PR/contract được dẫn là nguồn liên quan đã đọc, không chứng nhận input mới đã được triển khai. Task hỗ trợ chưa được giao riêng phải nhờ Duy xác nhận; không tự mở rộng scope task cũ.

| ID / người cung cấp → nhận | Input/câu hỏi cụ thể và bằng chứng còn thiếu | Cần trước / ETA input / ETA xong task cung cấp | Làm ngay/chờ / nguồn |
| --- | --- | --- | --- |
| I-A-SAVE — Duy → Quỳnh | Nhờ bàn giao RPC lưu config: tên/signature/params/result, JSON thành công+lỗi và SQLSTATE/code; owner check, khóa phiên, tái kiểm N/modes/BP/status, chính sách insert/update một config hiện hành, cập nhật configured+updated_at trong cùng transaction. Kèm migration, quyền gọi authenticated/worker và test permissions. 002/003 hiện không cung cấp chức năng này<br>**Task/nguồn liên quan:** Duy — [TASK-205 / PR #16](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/16) và [contract confirm](../api/confirm-source-endpoint.md); nền DB: [schema DB hiện có](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/813f4976ac95a336eed8f71ec77b3426eef6edf5/backend/scripts/schema.sql). RPC config là hỗ trợ TASK-207a, chưa có task DB riêng được xác nhận.<br>**Task nhận input:** Quỳnh — [TASK-207a](TASK-207a.md). | Trước A1; ngày cần nhận TBD / TBD / TBD | Chốt mapping/fixture trước; ghi DB thật chờ contract+migration. Chưa có reply cho PR này |
| I-B-AI, I-B-POLICY — Duy + Đạt/Hùng + Bội Anh → Quỳnh | Dẫn [207b](TASK-207b.md): khi nào canonical BP đủ để config, mode public nào map sang allowed_transformations.dimension, []/NONE nghĩa gì? Nhờ mẫu 2 nguồn giao modes và trường hợp không có mode chung; không dùng fallback ±5 thay canonical<br>**Task/nguồn liên quan:** Duy — [TASK-205 / PR #16](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/16) và [contract confirm](../api/confirm-source-endpoint.md); Đạt/Hùng — TASK-203/402, [PR #18](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/18), [PR #21](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/21) và [contract AI W2](../ai-w2-integration.md); Bội Anh — [TASK-206/208 / PR #22](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/22) và [plan TASK-206](TASK-206.md).<br>**Task nhận input:** Quỳnh — [TASK-207a](TASK-207a.md). | Trước A2 / TBD / TBD | Policy khung có sẵn; không tự chốt semantics |
| I-B-FE-REST — Duy + Bội Anh → Quỳnh/FE | Nhờ chốt JSON GET session: saved generation_config, nguồn+BP hoặc summary sẵn sàng, số câu/modes/status và lỗi. Hiện SessionDetailResponse chỉ có source_questions/exam_versions, chưa query config/BP. Ai sửa route/schema và ETA? Xác nhận UI false so với BE default true là chủ đích, không cần sửa nếu được chốt<br>**Task/nguồn liên quan:** Duy — TASK-104 (session detail, tuần 1), [route hiện có](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/813f4976ac95a336eed8f71ec77b3426eef6edf5/backend/app/api/routes/sessions.py); Bội Anh — [TASK-206/208 / PR #22](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/22) và [plan TASK-206](TASK-206.md).<br>**Task nhận input:** Quỳnh — [TASK-207a](TASK-207a.md); Bội Anh — TASK-206/208. | Trước A3 và FE smoke / TBD / TBD | FE save payload/case-sensitive đã có; không yêu cầu viết lại |
| I-OPS-DB — Duy + OPS (đầu mối cần xác nhận) → Quỳnh | DB test cô lập, migrations đã áp, identities A/B, quyền seed/cleanup và phạm vi chạy transaction/RLS tests; trao credentials bằng kênh phù hợp, không dán vào PR<br>**Task/nguồn liên quan:** OPS — TASK-004 (môi trường tuần 1, đầu mối chưa chốt), [Docker setup](../setup-docker.md); Duy điều phối; Duy hỗ trợ DB theo [schema DB hiện có](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/813f4976ac95a336eed8f71ec77b3426eef6edf5/backend/scripts/schema.sql).<br>**Task nhận input:** Quỳnh — [TASK-207a](TASK-207a.md). | Trước A4 DB tests / TBD / TBD | Fixture tests làm độc lập; chưa nhận DB thật |
| I-W2-PLAN — Duy + Quỳnh | Link/version assignment chung W2, hạn phần tồn đọng và owner/reviewer/ETA; không lấy lịch PR26/27 W3 áp vào 207<br>**Task/nguồn liên quan:** Duy — leader/M1, [WORKFLOW §3](../review/WORKFLOW.md); link assignment W2 chung còn thiếu.<br>**Task nhận input:** Quỳnh — [TASK-207a](TASK-207a.md). | Trước nhận lịch hoàn thiện / TBD / TBD | Giữ W2; không tạo assignment mới |

Mốc “cần trước” là điều kiện kỹ thuật, **chưa là ngày cam kết**. Nhờ bên giao trả lời cùng Conversation: output/contract/commit, phần đủ dùng ngay, phần pending, ETA giao input và ETA xong task riêng. Duy điều phối nếu ETA không còn đủ thời gian tích hợp/kiểm/review; không coi im lặng là đồng ý.

- Output Quỳnh giao: config request/response/errors + callable adapter/route + fixture/tests cho Bội Anh và 207b; ETA sau khi xác nhận input.
- Quyết định mới đã thống nhất trong lượt này: chưa có. Đây là plan/questions, không phải chấp thuận thay contract.

## Kế hoạch tự kiểm

- Models/policy/read adapter/router; N biên, modes giao/hoa-thường/rỗng, malformed DB, confirmed readiness, Auth/rate-limit.
- DB thật: atomic config+state, concurrent save/generate/source change, permissions/RLS, uncertain response.
- FE thật: load detail → chọn config → lưu → reload khôi phục; phối hợp Bội Anh.
- Backend regression, Ruff/Mypy, format phần đổi, CI áp dụng và git diff --check trên bản cuối. Chưa chạy các kiểm tra sản phẩm trong lượt lập plan.

## Bàn giao và M5

- Đã làm: đọc dev và nhánh Quỳnh riêng, assignment W2, PR23 và mẫu PR26/27; lập M2 này. PR26/27 chỉ tham khảo cách trình bày, không giao việc W3 cho Quỳnh.
- Chưa làm: đồng bộ nhánh task, triển khai save RPC/adapter, mount route, DB/AI/FE E2E; chưa có approval cho plan này.
- M3 Draft dùng scope/input trên; khi Ready cập nhật head sau push và checks thật. Local SHA không phải PR head mới.
- Khi có finding: M4 giữ F-ID/thread; author tái hiện → sửa → kiểm → trả M5 claimed_fixed có commit/checks/giới hạn; reviewer kiểm ca cũ+vùng ảnh hưởng rồi ghi verified/open/disputed/inconclusive. **Hiện chưa có finding cho plan này, không tạo F01 hoặc claimed_fixed giả.**


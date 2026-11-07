# TASK-204 — Xem trước và xác nhận đề nguồn (M2)

- **Phụ trách:** Trung Anh / `philip-kkk` / TV1 / FE1. Duy (`johannguyen015`) review chính và phụ trách API xác nhận. Bội Anh (`htbaax`) kiểm điểm bàn giao Stage 2. Dự phòng và ETA review riêng TBD.
- **Nguồn giao việc:** TASK-204 trong `w2_21_10.md` của Duy, bản workspace `project/W2_ASSIGNMENT_20261026.md`. Link phân công chung TBD.
- **Nhánh:** `feat/task-204-source-confirm` → `dev`. [Draft PR #42](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/42). Nền `dev` đã đồng bộ: `73583d7`.
- **Workflow:** [v0.1 proposed](../review/WORKFLOW.md) (`506384b`), dùng [M2/M3](../review/TEMPLATES.md). Mốc W2 tối 03/11/2026 theo [xác nhận của Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499240459) đã qua. ETA TASK-204 và ETA giao đầu vào chưa được xác nhận.
- **Trạng thái:** P1–P3 đã triển khai. Bản ghép dev đã kiểm canonical summary và Stage 2 với dữ liệu từ SQL. Còn chốt cập nhật readiness/failed ở FE2 và runtime Auth/PostgREST cho Q03. Checkpoint chờ #32 và adapter modes riêng bên dưới là lịch sử.

## Mình cần làm gì?

Giảng viên xem lại đề nguồn đã lưu, chủ động xác nhận đề và tiếp tục sang Stage 2 trong cùng phiên. Tái sử dụng preview chỉ đọc để hiển thị câu hỏi, bốn phương án A–D và đáp án đúng bằng `MathRenderer`. Dữ liệu mẫu dùng Toán Đại số không cần hình vẽ.

- Cho xác nhận nguồn đã lưu khi phiên còn `draft`, nguồn có câu và trạng thái tải/ghi đã rõ. Giải thích rõ thao tác áp dụng cho preview đang hiển thị nếu còn file hoặc nháp văn bản chưa nạp. Khóa thao tác trong lúc nạp, đọc lại, xác nhận hoặc đối soát ghi chưa rõ kết quả.
- Gửi confirm bằng hành động rõ ràng. Nạp và xác nhận loại trừ nhau ở cả nút và handler để click liên tiếp không tạo hai thao tác ghi. Khi confirm thất bại, giữ preview và nháp. Phân biệt lỗi thiếu dữ liệu, xung đột trạng thái, mất quyền và kết quả chưa rõ.
- Xác nhận thành công khóa đề đã lưu. Sau khi tải lại hoặc mở lại phiên đã xác nhận, đọc trạng thái và tiếp tục đúng phiên theo contract, không tự gửi confirm. Bỏ phản hồi cũ khi đổi phiên, tài khoản hoặc rời màn.
- Theo dõi readiness riêng. Khi còn `pending`/`running` hoặc `failed`, hiển thị trạng thái chuẩn bị dữ liệu phù hợp ở màn đã thống nhất. Chỉ mở cấu hình/sinh theo điều kiện backend và FE2 chốt. Blueprint, hash và cảnh báo an ninh xử lý nội bộ theo [ADR 0001](../adr/0001-confirm-before-blueprint.md) và silent audit hiện hành.

Ngoài phạm vi: làm lại tạo/mở phiên, ingestion hay dialog 203b, sửa câu đã trích xuất trên UI, autosave, card/biên tập Blueprint, checkbox xác nhận an ninh, thiết kế lại màn, xây form Stage 2/SSE hoặc sửa backend/migration. Nếu cần thay đổi contract chung, phối hợp owner trước khi đưa vào phạm vi PR.

## Nền hiện có và các điều kiện chuyển bước

- [TASK-201](TASK-201.md) / [PR #29](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29) đã merge. [SourceQuestionPreview](../../frontend/src/features/stage1-ingestion/SourceQuestionPreview.jsx) đã render câu nguồn, phương án và đáp án. [TASK-203b](TASK-203b.md) / [PR #31](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/31) đã merge và cung cấp vòng sửa đầu vào khi incomplete 422.
- [Stage1Route](../../frontend/src/features/stage1-ingestion/Stage1Route.jsx) đã có key theo tài khoản và phiên. Panel hiện đọc nguồn đã lưu từ [controller ingestion](../../frontend/src/features/stage1-ingestion/sourceIngestion.js). Route chưa có đường tiếp tục cho lần mở lại phiên đã xác nhận.
- **Confirm và snapshot.** [Contract BE1 `5b711d2`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/5b711d250774446e8e61511174ac738c0a924d71/docs/api/confirm-source-endpoint.md) trả `source_revision` UUID cùng câu nguồn từ GET detail. POST gửi revision đã xem và UUID `Idempotency-Key` bắt buộc. Sau nạp thành công, lấy lại snapshot bằng GET trước khi bật confirm. Key lưu theo tài khoản và phiên qua F5. Đối soát bằng GET trước khi retry cùng key; xung đột revision đòi hỏi xem và xác nhận lại bản mới.
- **Blueprint readiness.** [Contract canonical](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/5b711d250774446e8e61511174ac738c0a924d71/docs/api/source-artifacts-contract.md) tách xác nhận nguồn khỏi `ready`. Stage 2 đọc `ready`/`supported_modes`; `ready=true` và `[]` hợp lệ. Adapter thuộc FE2.
- **Bàn giao Stage 2.** Dùng route `/session/:sessionId/stage2` và quy tắc mở lại phiên của [Dashboard](../../frontend/src/features/dashboard/sessionDestination.js). Sau confirm hợp lệ hoặc GET cho biết phiên đã xác nhận, chuyển cùng ID. FE1 không chờ Blueprint và không tự POST khi F5.

## File và thứ tự triển khai

Tên file mới là dự kiến. Chốt phạm vi từng lượt theo code và contract đã thống nhất trước khi sửa.

| Lượt / file dự kiến | Mục đích và đầu ra | Điều kiện bắt đầu | Cách kiểm |
|---|---|---|---|
| P0 — `docs/tasks/TASK-204.md`, M3 trong Draft | Lưu plan, base, câu hỏi Q01–Q03 và thứ tự bàn giao. | Nhánh task có nền dev đã kiểm. | So nguồn giao việc, đường dẫn, diff tài liệu và câu hỏi chưa chốt. |
| P1 — `frontend/src/services/sourceConfirmation.js` và kiểm liên quan | Dùng `api.js` cho confirm/read readiness, truyền key và signal theo contract, kiểm ID và response trước khi trả trạng thái cho UI. Tách confirm 422 khỏi incomplete 422. | Duy chốt Q01. Có thể chuẩn bị fixture rõ nhãn sau khi mẫu payload được chốt. | Kiểm request path/body/header, response sai phiên, 409/422, lỗi mạng và đối soát cùng key. |
| P2 — `Stage1SourcePanel.jsx`, controller Stage 1 liên quan và kiểm component | Ghép CTA vào preview nguồn đã lưu. Khóa ghi đồng thời, xử lý trạng thái pending/lỗi/đọc lại, giữ nguồn và nháp. Tái dùng cơ chế cô lập tài khoản/phiên của 201. | P1 đạt, thống nhất cách trình bày nguồn đã lưu và điều kiện xác nhận snapshot ở Q01. | Bấm đôi, nạp rồi confirm và chiều ngược lại, lỗi giữ preview, logout/đổi route khi đang chờ. |
| P3 — `Stage1Route.jsx`, readiness và điểm nối Stage 2 đã thống nhất | Đọc lại phiên đã xác nhận, điều hướng cùng ID, phục hồi trạng thái khi F5 và phối hợp kiểm luồng vào trực tiếp từ Dashboard. | P2 đạt, Q02 chốt màn chờ và nguồn dữ liệu readiness/modes. Phạm vi sửa file FE2 cần được phối hợp trước. | Pending/running/failed, ready và F5. Xác nhận không có POST ngoài thao tác người dùng và không mở cấu hình sớm. |
| P4 — audit và bàn giao M3 | Kiểm hồi quy frontend, kiểm môi trường tích hợp được giao và ghi kết quả theo commit. | Q03 có môi trường hoặc ghi rõ phần fixture và blocker kiểm thật. | Test/lint/build, kiểm thao tác người dùng và ghi nhận riêng mock/API thật. |

Các mốc commit dự kiến sau P0, theo từng phần đã tự review và kiểm: `feat(stage1): add source confirmation client`, `feat(stage1): connect source confirmation to preview`, `feat(stage1): hand off confirmed sessions to Stage 2`. Gộp test liên quan cùng phần triển khai để mỗi commit có thể review độc lập.

## Đầu vào và câu hỏi trên Draft PR

| ID / owner | Cần xác nhận | Cần trước | ETA / phần có thể làm |
|---|---|---|---|
| Q01 — Duy / TASK-205 | Đã chốt `source_revision` và key UUID. Thiếu key/revision trả 422, xung đột trả 409. Sau timeout/F5 đọc phiên và artifact trước khi retry; giữ key cho cùng thao tác. | P1/P2 | Có thể kiểm với fixture theo [PR BE1 #43](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/43). |
| Q02 — Duy và Bội Anh | Đã chốt chuyển Stage 2 cùng ID sau confirm và dùng readiness/modes từ `source-artifacts`. | P3 | Có thể kiểm route với fixture. Adapter FE2 là điều kiện tích hợp thật. |
| Q03 — Duy và Trung Anh | Xác nhận runtime đã ghép BE1/BE2, gồm migration và Auth/JWT/RLS; chạy với provider tắt hoặc giả lập. Kiểm preflight `Idempotency-Key` nếu FE/API khác origin. | P4 | Chờ runtime được giao. BE1 đã báo kiểm PostgreSQL với AI giả lập, tách khỏi nghiệm thu FE và runtime đã triển khai. |

Silent audit đã chốt, không mở lại câu hỏi checkbox của assignment cũ. [ADR 0001](../adr/0001-confirm-before-blueprint.md) và [change log](../change_log.md#dec-be1-018-task-301-background-canonical-production-and-frozen-v1) giữ quyết định backend. Q01–Q03 hỏi phần tích hợp và hành vi giao diện còn thiếu.

## Kế hoạch tự kiểm

- **Fixture FE:** preview đúng câu và key, nguồn rỗng/chưa tải, input chưa nạp, xung đột nạp/confirm, lỗi 409/422, timeout sau ghi, response sai phiên, đổi account/route và F5. Xác minh confirm 422 không bật dialog incomplete của 203b.
- **Readiness và handoff:** kiểm confirmed nhưng chưa ready, failed, ready, vào trực tiếp từ Dashboard và tải lại. Kiểm route đúng ID và dữ liệu cấu hình đúng nguồn. Không lấy kết quả fixture làm bằng chứng backend.
- **Kiểm trước Ready:** chạy `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build` trong `frontend/` sau khi có code. Kiểm thao tác keyboard/CTA và luồng nạp → xem → confirm → Stage 2 theo điều kiện Q03. Dùng fixture hoặc phiên có artifact sẵn nếu cần kiểm trạng thái `ready` mà không gọi AI. Ghi head, môi trường, phép kiểm thật và phần chưa chạy. Việc ghi cloud cần phạm vi được giao riêng.

## Bàn giao

- **Output cho FE2:** cùng `sessionId`, đường vào Stage 2 và quy tắc khi đang chuẩn bị/đã sẵn sàng theo Q02. Mốc giao TBD.
- **Mốc triển khai:** P1 `d5e8823`, P2 `5e511fd`, P3 `f48ed60`. Bản P4 trong commit chứa mục này giữ intent đến khi đọc lại thành công sau 409 và có [fixture Chrome tái chạy](../../frontend/test-support/stage1-native/README.md#task-204--xác-nhận-nguồn-và-f5).
- **Bước tiếp:** Duy review contract, Bội Anh kiểm điểm bàn giao cùng phiên trên runtime tích hợp. Giữ Draft trong lúc chờ xác minh phần đó.

## M3 — Kết quả kiểm local cho PR #42

- Baseline sau đồng bộ `dev`: 86 ca Stage 1/ingestion đã có đạt. Sau P1–P4: `npm.cmd test -- --test-concurrency=2` **328 đạt**, `npm.cmd run lint` đạt, `npm.cmd run build` đạt với `GOMAXPROCS=2` và cảnh báo bundle `968.62 kB`. Lượt chạy song song trước đó hết tài nguyên Windows; chạy lại tuần tự đạt. `git diff --check` đạt.
- **Chrome, Auth/HTTP giả lập:** bàn phím nạp đề B, GET cập nhật preview, confirm mất response. F5 trên phiên nháp giữ số POST ở 1, đọc phiên và artifact trước khi cho retry. Retry chủ động gửi lần 2 cùng key và mở đúng phiên trên Stage 2 fixture. Với ca server giả lập đã commit, F5 đọc `blueprinted`, mở Stage 2 fixture và số POST vẫn là 1. Bằng chứng local tại `tmp/task204-chrome-fixture.json` trong workspace.
- **Phạm vi bằng chứng:** kiểm FE1, snapshot, khôi phục key và route. Stage 2 trong fixture chỉ kiểm ID bàn giao. Kiểm thật với adapter FE2, migration BE1/BE2, Supabase/PostgREST/JWT/RLS và CORS khác origin vẫn chờ runtime được giao. Chưa gọi API/provider thật cho lượt này.

## M3 — P4 sau đồng bộ dev ngày 06/11/2026

Checkpoint lịch sử tại nền `295342f`; xem kết quả ngày 07/11/2026 bên dưới.

- **Bản kiểm:** merge local `e42e6d3` của PR #42 `4cef37e` với `dev` `295342f`. Nền đã có FE2 [PR #40](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/40) và BE1 [PR #43](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/43).
- **Frontend:** `npm.cmd test -- --test-concurrency=2 --test-reporter=dot`, `npm.cmd run lint`, `npm.cmd run build` và `git diff --check` đạt. Build cảnh báo bundle `982.67 kB`.
- **Chrome 156 qua DevTools Protocol:** hai ca fixture Auth/HTTP đạt. Đã dùng bàn phím nạp đề và xác nhận. F5 khi phiên còn nháp đọc lại artifact rồi cho retry cùng key. F5 khi server giả lập đã commit mở đúng phiên ở Stage 2 fixture và giữ đúng một POST. Bằng chứng local tại `tmp/task204-p4-e42e6d3/chrome-result.json` trong workspace.
- **Backend:** FastAPI TestClient chạy với PostgreSQL 15 cô lập, migration BE1 đến `014`, Auth/transport DB test và provider giả lập. Đã kiểm xung đột revision, mất response sau commit, replay cùng key với một receipt, và artifact chuyển pending/running/failed/ready. Ca PostgreSQL riêng cũng xác nhận `ready=true, supported_modes=[]`. Lượt này chưa có Supabase/PostgREST hoặc xác minh JWT/RLS trên runtime tích hợp.
- **Điểm chặn FE2:** Probe gọi `fetchSessionDetail` theo dữ liệu của contract. Với cả artifact `ready=true, supported_modes=[]` và `ready=true` có một mode, service chỉ gọi GET phiên. `blueprint_summary` vẫn là `null` và form Stage 2 khóa submit. PR #40 đã merge, adapter canonical cho [`source-artifacts`](../api/source-artifacts-contract.md) vẫn cần FE2 nối.
- **Điểm chặn BE2:** Migration `010` trên `dev` là file rỗng của BE1. Migration generation-config và API tương ứng còn ở [PR #32](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/32). Cần thứ tự migration được BE2 xác nhận và runtime có đầy đủ các thành phần trước khi chạy P4 tích hợp.
- **Kết luận:** Có bằng chứng riêng cho FE1 và BE1 trên nền mới. Giữ PR #42 Draft và chạy lại luồng browser với Stage 2 thật sau khi có adapter FE2 và runtime BE2 đã ghép.

## M3 — Kiểm lại bản ghép ngày 07/11/2026

- **Bản kiểm:** merge local `3e3dff1` với `dev` `73583d7`, gồm #32/#36/#41. Merge không conflict. API GET phiên đã đọc `get_generation_source_snapshot` và cung cấp canonical `blueprint_summary`.
- **Regression:** 355 frontend tests, lint/build và diff-check đạt. Bundle cảnh báo `982.67 kB`. Backend API confirm/detail/ingestion/CORS và mode mapper đạt 170 ca, dùng transport/provider giả lập.
- **SQL/API bản ghép:** hai ca PostgreSQL 15 dùng một lần đạt với migrations BE1 đến 014 cùng 004/005/015/016 của BE2. Kiểm confirm, revision conflict, mất response sau commit/replay cùng key và pending/running/failed/ready. GET phiên trả `is_ready=true` cùng modes đầy đủ hoặc `[]` hợp lệ. Provider là fake, Auth được inject và transport PostgREST được thay bằng SQL fixture. Harness bổ sung IN-filter của GET detail mới trước lượt đạt.
- **Component Stage 2 thật:** Node DOM/MemoryRouter dùng JSON GET lấy từ ca SQL trên. Form khóa với pending/failed, mở với ready có modes hoặc ready với `[]`. Điểm chặn cũ “thiếu adapter modes” đã hết trên nền này. Khi server fixture đổi pending sang ready sau mount, màn không đọc lại và vẫn khóa; failed hiện cùng cảnh báo chưa sẵn sàng, không hiện mã lỗi production. Cần Bội Anh chốt hành vi refresh/readiness và retry canonical theo Q02, không yêu cầu xây luồng generation/SSE trong TASK-204.
- **Q03:** Duy là đầu mối xác nhận runtime kiểm có migration đúng bản, Auth/JWT/RLS/PostgREST và provider tắt/fake hoặc artifact sẵn. Chưa kiểm các thành phần này trên Supabase/PostgREST. Không đưa toàn bộ PR30 hoặc OPS W4 thành gate mới.
- **Bằng chứng local:** `tmp/task204-merged-3e3dff1/` trong workspace có harness SQL, JSON pending/failed/none/ready và `stage2-result.json`. Đây là SQL/API và DOM integration, chưa phải browser qua Auth/PostgREST thật. Chrome/F5 fixture tại checkpoint trước giữ phạm vi bằng chứng riêng.

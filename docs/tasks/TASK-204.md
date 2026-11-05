# TASK-204 — Xem trước và xác nhận đề nguồn (M2)

- **Phụ trách:** Trung Anh / `philip-kkk` / TV1 / FE1. Duy (`johannguyen015`) review chính và phụ trách API xác nhận. Bội Anh (`htbaax`) kiểm điểm bàn giao Stage 2. Dự phòng và ETA review riêng TBD.
- **Nguồn giao việc:** TASK-204 trong `w2_21_10.md` của Duy, bản workspace `project/W2_ASSIGNMENT_20261026.md`. Link phân công chung TBD.
- **Nhánh:** `feat/task-204-source-confirm` → `dev`. Nền code đã đọc: `99dc8d307cb22b489cb17553d487f0ce5f7573e7`. Link Draft PR bổ sung khi có.
- **Workflow:** [v0.1 proposed](../review/WORKFLOW.md) (`506384b`), dùng [M2/M3](../review/TEMPLATES.md). Mốc W2 tối 03/11/2026 theo [xác nhận của Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499240459) đã qua. ETA TASK-204 và ETA giao đầu vào chưa được xác nhận.
- **Trạng thái 05/11/2026:** plan/input. Đã đọc code và tài liệu tại nền trên. Chưa triển khai TASK-204 hoặc kiểm API trên môi trường tích hợp.

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
- **Confirm và hash.** [Route confirm](../../backend/app/api/routes/sessions.py) gọi [source artifacts flow](../../backend/app/api/routes/source_artifacts.py). Backend xác nhận snapshot/fingerprint và trả `confirmation_id`, `status: blueprinted`, `canonical_status`. `Idempotency-Key` là UUID. [Test backend](../../backend/tests/api/test_confirm_source.py) có ca lỗi đọc sau commit rồi gửi lại cùng key. Giữ một key cho cùng thao tác chưa rõ kết quả nếu contract cho phép gửi lại. FE dùng kết quả từ server và không tự tính hash xác nhận. Cần làm rõ việc gắn confirm với đúng snapshot đã xem nếu nguồn đổi ở tab khác trước khi bấm xác nhận.
- **Blueprint readiness.** `GET /api/sessions/{id}/source-artifacts` tại base là đường đọc `ready`, `canonical_status` và tiến độ chuẩn bị. `blueprinted`, HTTP 200 và số Blueprint trong response confirm chỉ mô tả kết quả xác nhận hoặc số đã hoàn thành tại thời điểm đó. Điều kiện sẵn sàng cần kiểm riêng. [Tài liệu confirm v1.0](../api/confirm-source-endpoint.md) còn mô tả fallback đồng bộ. Dùng code hiện hành và phản hồi từ BE1 để chốt mẫu payload triển khai.
- **Bàn giao Stage 2.** Route `/session/:sessionId/stage2` đã có trong [App](../../frontend/src/App.jsx). [Dashboard](../../frontend/src/features/dashboard/sessionDestination.js) đã mở phiên `blueprinted` tại Stage 2. [Adapter Stage 2](../../frontend/src/services/stage2Service.js) hiện đọc `blueprint_summary` hoặc suy từ dữ liệu Blueprint lồng trong câu nguồn, còn GET detail ở base lấy câu nguồn và mã đề. Bội Anh và Duy cần chốt cách cấp readiness và dữ liệu chế độ biến thể trước khi nhận tích hợp. Không tạo summary/mode giả trong 204.

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
| Q01 — Duy / TASK-205 | Chốt mẫu confirm/readiness và lỗi trên bản tích hợp. Xác nhận quy tắc gửi lại cùng UUID khi mất response, cách đối soát sau tải lại và cơ chế phát hiện snapshot đã xem bị đổi ở tab khác. Route tại base dùng `updated_at` đọc phía server, request hiện chưa thấy trường revision do client gửi. | P1/P2, trước khi chốt hành vi ghi. | TBD. Preview hiện có có thể rà độc lập. Dùng [source artifacts flow](../../backend/app/api/routes/source_artifacts.py) làm căn cứ trao đổi. |
| Q02 — Duy và Bội Anh | Chốt màn chịu trách nhiệm hiển thị chờ/thất bại, lúc điều hướng và nguồn readiness/modes cho Stage 2. Xác nhận hành vi khi vào từ Dashboard hoặc F5. Nếu có retry chuẩn bị Blueprint, chốt owner, màn và phạm vi trước khi ghép. | P3, trước khi công bố luồng Stage 2 tích hợp. | TBD. Rà route và adapter trước. Đề xuất Stage 2 nhận phiên đang chuẩn bị chỉ khi FE2 có thể chặn cấu hình ở mọi đường vào. |
| Q03 — Duy và Trung Anh | Xác nhận runtime có migration/RPC source artifacts và môi trường được phép kiểm. Các POST nạp/xác nhận có thể lên lịch worker khi runtime có cấu hình AI. Chốt môi trường dùng fixture hoặc tắt provider trước khi kiểm các POST này. | P4, trước khi ghi đã kiểm API thật. | TBD. Dùng fixture đã thống nhất cho các ca tự động và ghi rõ phần còn chờ môi trường. |

Silent audit đã chốt, không mở lại câu hỏi checkbox của assignment cũ. [ADR 0001](../adr/0001-confirm-before-blueprint.md) và [change log](../change_log.md#dec-be1-018-task-301-background-canonical-production-and-frozen-v1) giữ quyết định backend. Q01–Q03 hỏi phần tích hợp và hành vi giao diện còn thiếu.

## Kế hoạch tự kiểm

- **Fixture FE:** preview đúng câu và key, nguồn rỗng/chưa tải, input chưa nạp, xung đột nạp/confirm, lỗi 409/422, timeout sau ghi, response sai phiên, đổi account/route và F5. Xác minh confirm 422 không bật dialog incomplete của 203b.
- **Readiness và handoff:** kiểm confirmed nhưng chưa ready, failed, ready, vào trực tiếp từ Dashboard và tải lại. Kiểm route đúng ID và dữ liệu cấu hình đúng nguồn. Không lấy kết quả fixture làm bằng chứng backend.
- **Kiểm trước Ready:** chạy `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build` trong `frontend/` sau khi có code. Kiểm thao tác keyboard/CTA và luồng nạp → xem → confirm → Stage 2 theo điều kiện Q03. Dùng fixture hoặc phiên có artifact sẵn nếu cần kiểm trạng thái `ready` mà không gọi AI. Ghi head, môi trường, phép kiểm thật và phần chưa chạy. Việc ghi cloud cần phạm vi được giao riêng.

## Bàn giao

- **Output cho FE2:** cùng `sessionId`, đường vào Stage 2 và quy tắc khi đang chuẩn bị/đã sẵn sàng theo Q02. Mốc giao TBD.
- **Đã làm:** lập M2 từ assignment, code tại base và checkpoint của 201/203b. Kết quả đọc tĩnh dùng để khoanh điểm cần chốt, chưa có kết quả kiểm triển khai 204.
- **Bước tiếp:** mở Draft với M2 và M3 theo quyền, giải đáp Q01–Q03, rồi bắt đầu P1 khi đã đủ đầu vào.

# TASK-201 / TASK-203b / TASK-204 — M2 Stage1 nguồn đề

- Trạng thái: Draft — plan/input. Checkpoint local 30/10/2026: nhánh TASK-201 mới có commit kế hoạch, chưa có implementation upload/text ingestion hoặc preview/confirm nguồn.
- Nguồn giao việc: `w2_21_10.md` do Duy giao, bản workspace `project/W2_ASSIGNMENT_20261026.md` khớp nội dung. Link assignment chung do leader quản lý: TBD; chưa có file tuần này trong repo, không tạo M1 cạnh tranh.
- Phụ trách: Trung Anh / philip-kkk / TV1 / FE1. User chọn Duy review chính, Bội Anh kiểm nối frontend/Stage2; Duy đã nhận review chính tại comment29/10 bên dưới. Bội Anh chưa xác nhận nhận việc/ETA; dự phòng và ETA review TBD.
- Workflow: [v0.1 proposed](../review/WORKFLOW.md), docs commit506384b; dùng [M2/M3](../review/TEMPLATES.md). Merge docs không chứng minh pilot/rollout đã đạt.
- Nền hiện tại đã đọc: dev `813f497` ngày29/10, có PR17/15/18/23/16/22. Nhánh `feat/task-201-stage1-source`, [Draft PR29](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29) đã có; commit plan khởi đầu50b81b5. TASK203b có [Draft riêng PR31](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/31), không triển khai cùng phần203b ở hai PR.
- Tổ chức sau khi tách: PR29 giữ kế hoạch Stage1/TASK-201 và điểm nối TASK-204; TASK-203b quản lý riêng tại PR31. Phần203b bên dưới là tiêu chí phối hợp, không triển khai lại ở cả hai PR. Chưa chốt PR riêng cho204; không tạo hai bản preview/hook cạnh tranh.
- Hạn nguồn W2:21–31/10/2026 (lịch sử). Duy đã xác nhận hạn chuyển tiếp tối thứ3,03/11/2026 và dự kiến code từ thứ6,30/10, tại comment29/10 bên dưới; đây là xác nhận leader, không phải agent tự gia hạn. ETA input/task/review cụ thể vẫn chưa có. Gate toànW1 do user chốt chưa được user thay đổi.

## Mình cần làm gì?

- 201: trong phiên draft có ID, nạp DOCX/TeX/MD hoặc text; chặn PDF/file quá10MB; phân biệt tiến trình upload và đang phân tích. Không POST khi mount/F5/đổi tab.
- Điểm nối203b/PR31: nhận incomplete422 có `detail.errors`; chỉ rõ lỗi toàn đề/câu và hướng sửa đầu vào, chọn lại file/chuyển text. Nguồn A phải còn sau khi B bị422 theo dữ liệu server; FE không tự restore DB.
- Điểm nối204: preview nguồn/options/key bằng MathRenderer, chỉ đọc, Blueprint ẩn; confirm và bàn giao FE2 theo contract/readiness. Rule silent audit đã có quyết địnhBE, không checkbox/modal ack; success-state còn phụ thuộcQ02/Q04/Q05.
- Ngoài phạm vi: làm lại Auth/Dashboard/create/detail; sửa parser/DB/Storage/AI; editor kết quả/xóa câu/autosave/Blueprint UI; config/SSE/Stage2/export; đổi stack/dependency.
- Nội dung ví dụ: Đại số không cần hình; giữ điều kiện, công thức, A–D và key đúng. UI không chứng minh parser/generator phủ toàn bộ Đại số.

Hiện đã có [Stage1Route](../../frontend/src/features/stage1-ingestion/Stage1Route.jsx), sessionEntry, services/sessions cho new→POST→ID/detail; client Auth chung và [MathRenderer](../../frontend/src/components/MathRenderer.jsx). Giữ các phần này, chỉ mở rộng nguồn tại phiên draft đã có ID.

Checkpoint code local30/10: feature stage1-ingestion chỉ có Stage1Route/sessionEntry và README/tests entry. Chưa có ingestion service, Stage1Page, useStage1Source, input file/text hoặc SourceQuestionPreview. Mở được route/đọc metadata không phải TASK-201 Done. Không đưa gói audit Evidence cho Presenter vào implementation hoặc kết quả kiểm của TASK-201.

Ingestion và confirm đã có source. PR22 đã vào nền813f497: App có `/session/:sessionId/stage2` nhận bởi `Stage2ConfigPage`; Dashboard cũng đã map blueprinted/configured/generating tới Stage2. Không thêm lại route hoặc làm màn thay FE2. Chưa kiểm runtime/cloud/migration hay luồng Stage1→Stage2 thật trong lượt này. Gate toàn W1 vẫn cần xác minh trước code: lần REST29/10 trước ghi PR19/TASK107c và PR20/TASK107d Open/unmerged, chưa audit lại vòng này. Plan/Draft không tự mở khóa code W2.

## File và thứ tự triển khai từ mốc code được xác nhận

Tên file mới là đề xuất; lượt này chưa tạo component/service/test hoặc thay runtime.

| Lượt / file dự kiến | Mục đích sửa | Output mong muốn | Input cần trước | Cách kiểm |
|---|---|---|---|---|
|2: `docs/tasks/TASK-201.md` — đã có|Cập nhật M2 sau trả lời owner và tách203b|Plan trên PR29, liên kết PR31; trạng thái đủ/thiếu rõ|Snapshot câu trả lời đã nhận; chưa code sản phẩm|Link, Markdown, diff; không nhận Draft là Done|
|3: `frontend/src/services/ingestion.js` và tests|Dùng `services/api.js`; request text/file, signal/progress; không client mới|Text `{raw_text}`, multipart trường `file`; response đúng phiên|Contract ingestion; gate W1 và user giao code|HTTP/adapter fixtures theo hạ tầng repo, không tự retry POST|
|3: `features/stage1-ingestion/useStage1Source.js`, `Stage1Page.jsx`; mở rộng ID draft trong `Stage1Route.jsx`|Quản lý input/nguồn đã lưu/request; giữ form new và tạo phiên|Text→gửi rõ ràng→kết quả; F5 GET nguồn; không giữ dữ liệu account/ID cũ|Current detail và response ingestion|Pending/cancel/stale/account/ID; nguồn đúng sau GET|
|3: `SourceQuestionPreview.jsx`|Preview tối thiểu dùng chung qua MathRenderer|Stem/A–D/key chỉ đọc, không ép format tích phân; chưa nhận204Done|Source shape đã đọc|Key/công thức/điều kiện/dữ liệu dài; không editor/Blueprint|
|4: PR31 — `stage1Errors.js`, `IncompleteContentDialog.jsx` và tests|203b cung cấp model lỗi/dialog;201 ghép callbacks/input|Lỗi toàn đề không “Câu0”; chọn lại file hoặc tabtext|ParserErrorItem/detail.errors; chốt props và thứ tự ghép với201|A→B422→A còn; unknown/FastAPI422/confirm422 không bị nhận nhầm|
|5: panel input/file trong `Stage1Page.jsx`|Chọn/kéo thả ba đuôi;10MB; progress riêng analysis|Chọn lại cùng file, giữ input khi lỗi; hủy/khóa gửi chồng|Giới hạn BE/settings và môi trường xác nhận|Picker/drop/boundaries/progress/focus trên browser; không gọi Storage trực tiếp|
|6: `services/confirmation.js`, panel confirm và callback điều hướng Stage1|Hoàn thiện204 theo contract, dùng route Stage2 đã có, không thêm App route trùng|Confirm→nhận/đọc lại trạng thái→Stage2ConfigPage đúng ID|Q02–Q05; không suy200/blueprinted/fallback là AI-ready|409/422/pending/double-click/readiness; tách fixture và API thật|
|7: Stage1/frontend README, change_log khi cần, M3|Bàn giao đúng head/checks/giới hạn|Ready khi phần được giao thực sự đạt; không che blocker|Input thật/màn FE2/CI/reviewer|Checks phù hợp và evidence, không nhận toàn W2 đã xong|

## Đầu vào và câu hỏi — giải đáp trên Draft PR trong thứ 5

User đã hỏi trên PR29 và Duy đã [trả lời Q01–Q05](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499240459) ngày29/10. Trạng thái dưới đây phân biệt quyết định BE với đủ bằng chứng tích hợp; không đánh dấu tất cả Resolved chỉ theo lời đề nghị trong comment. Quyết định cập nhật vào contract của owner, không tạo schema cạnh tranh.

Các trạng thái GitHub/Conversation trong mục này là snapshot đầu vào đã lưu29/10, không phải kết quả kiểm remote mới của lượt cập nhật local30/10. Trước code/tích hợp cần đối chiếu lại head/contract và gate phù hợp; không tự nhận branch pending đã merge.

User đã [đăng câu hỏi bổ sung](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499904653) ngày29/10. Đã tìm và đọc [TASK-201_ANSWERS.md tại5cd570b](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/5cd570b2fbd51a7f847c230b67f2ae4803faa325/docs/tasks/TASK-201_ANSWERS.md), Duy commit29/10 21:58:57 GMT+7 trên feat/task-207c-runtime-metrics thuộc PR30 củaQuỳnh, chưa vào dev/PR29. Commit chỉ thêm117dòng tài liệu, không sửa payloadAPI. Conversation vẫn3comment, Duy chưa trả lời mới/edits. Phần tìm/linkanswers đã giải quyết, không hỏi lại; GETpayload/ADR/runtime còn thiếu như bảng. Câu hỏi bổ sung đã có, không gửi comment trùng/ackrỗng.

| Cần ai/task nào | Câu hỏi/input cụ thể | Cần trước | ETA bên cung cấp xác nhận | Phần làm ngay/chờ | Link trả lời/contract |
|---|---|---|---|---|---|
|Q01 — Duy/leader, Tâm/PR19–20 và user|Partial: Duy nhận review chính/chốt03/11; answers có lịch30/10services,31/10–01/11error-confirm,02/11checks-review. Duy ghi rõ19/20 không chặnFE1 theo phụ thuộc; snapshot29/10 vẫnOpen, user chưa đổi gate toànW1. Link assignment/backup/ETA input còn thiếu.|Trước code|Hạn leader03/11, có lịch theo ngày; ETA input TBD|Plan/Draft; chờ gateuser, không nhận W1 đã merge hết|[Answers5cd570b](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/5cd570b2fbd51a7f847c230b67f2ae4803faa325/docs/tasks/TASK-201_ANSWERS.md)|
|Q02 — Duy + AI + FE2|Partial: BE chốt confirm đồng bộ/ensure fallback, không polling;200 blueprinted,409 GET lại. Source khớp cơ chế đó; chưa đối chiếu xong ADR0001 confirm/hash trước extraction và Blueprint canonical. Fallback không là bằng chứng Gemini/chất lượng/Stage2 tích hợp.|Trước ghép confirm success|Chưa có ETA đồng bộcontract|Không tự thêm polling hoặc coi200 là đủ dữ liệu Stage2|[Duy trả lời](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499240459)|
|Q03 — Duy/owner contract và user|Resolved rule an ninh: ADR004 silent audit, không checkbox/modal ack/security-warning gate. Answers làm rõ badge/tooltip nếu có chỉ thông tin, không chặn. Confirm khi cócâu/không missing-answer/không submitting; giữ guards status/account khác.|Trước code rule204|Đã trả lời29/10|Không làm checkbox/modal ack hoặc tự redesign badge. Chưa code/kiểm204|[Answers5cd570b](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/5cd570b2fbd51a7f847c230b67f2ae4803faa325/docs/tasks/TASK-201_ANSWERS.md)|
|Q04 — Bội Anh/FE2 và Duy|Blocked tích hợp: đích Stage2 đã chốt; GETdetail dev813f497 chỉ source_questions.select(*)/exam_versions, không blueprint_summary/joinBlueprint. Probe actual stage2Service với shape này trả summarynull; hai control có BP/summary đều ready. Cần JSON/contract và sửa ởowner tương ứng.|Trước navigate/kiểm204 xuyên suốt|TBD|Không giả dữ liệu/épready/sửa thayFE2/BE; probe là mô phỏng|[Duy trả lời](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499240459)|
|Q05 — Duy/OPS|Partial: đã nhận answers đúngcommit, SQL/migrations/tests và ví dụHTTP200/409/422confirm. Tài liệu hướng dẫn local/Docker/Storage/JWT, chưa xácnhậnDB/migration002–003/Storage áp ởruntime nào hoặc cóJSONliveJWT. Linkanswers đãresolved, không hỏi tìmfile nữa.|Trước API/cloud thật|ETA môi trường/input TBD|Đủ tham khảo source/fixture, chưa nghiệm thu API/cloud; giữ Docker/client hiện có, không rerunschema|[Answers5cd570b](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/5cd570b2fbd51a7f847c230b67f2ae4803faa325/docs/tasks/TASK-201_ANSWERS.md)|

- Output giao FE2: session ID, nguồn đã xác nhận và trạng thái/readiness đúng Q02/Q04. Giao BE1 payload/lỗi có thể tái hiện, không token/nội dung mật. Mốc cần nhận, ETA giao/nhận và hoàn tất: TBD.
- Tính khả thi theo đầu vào đã lưu: Duy chốt hạn03/11 nhưng gateuser chưa được khép, Q04 thiếu điểm nối trên nền nhánh này và Q02/Q05 chưa đủ chứng cứ; chưa đủ căn cứ cam kết204/xuyên suốt. Q03 đã có quyết địnhBE, không hỏi lại cùng nội dung. Các phụ thuộc204 không được coi là phần201 đã triển khai hoặc làm thay backend/FE2.
- Quyết định đã rõ: source read-only, Blueprint ẩn, Đại số không hình; dùng client/renderer có sẵn. Các mục TBD chưa được nhận là đã chốt.

## Contract đã đọc, không phải kiểm tích hợp

- [Ingestion](../api/ingestion-endpoints.md): POST `ingest-text` body `{raw_text}`; `ingest-file` multipart `file`;200 `{session_id,total_questions,questions}`. Detail GET dùng `source_questions`; adapter FE kiểm đúng phiên và phân biệt hai tên trường.
- [schemas.py](../../backend/app/models/schemas.py): text strip không rỗng, tối đa100.000 Unicode codepoints. FE cần khớp cách đếm, không mặc định JS.length cho ký tự surrogate. ParserErrorItem còn có UNPARSED_IMAGE/AMBIGUOUS_FORMAT/EMPTY_STEM/CONFLICTING_ANSWER_KEY/SURPLUS_ANSWER_KEY/DUPLICATE_QUESTION_NO/INVALID_QUESTION_NO; không hardcode chỉ ba mã cũ.
- [validator.py](../../backend/app/services/parser/validator.py) trả422 `{detail:{message,errors:[...]}}`; question_no0 là lỗi toàn đề. Request validation422 có detail array và confirm422 có detail string xử lý khác. File sai/quá giới hạn có thể400;429/409/network không phải incomplete.
- [Confirm](../api/confirm-source-endpoint.md) đã merge PR16:200 có session_id/statusblueprinted/confirmed_at/total_questions/total_blueprints; ack deprecated/ignored; có fallback Blueprint mặc định. Không tự dùng count/status để chứng minh AI-ready.
- [ADR0001](../adr/0001-confirm-before-blueprint.md) và [AI integration](../ai-w2-integration.md) cần BE/AI/FE2 đối chiếu; không tự sửa BE để ghép hợp đồng. Rule silent audit là ADR004 trong [change_log](../change_log.md), đã ởdev, không còn chỉ nằm trên PR pending.
- [Stage2 guide](../../frontend/src/features/stage2-config/STAGE2_GUIDE.md) và [Stage2ConfigPage](../../frontend/src/features/stage2-config/Stage2ConfigPage.jsx) đã có trên nền813f497. Dùng làm đầu vào Q04, không lấy deadline/coverage trong tài liệu task khác thay hạn W2 của TV1 hoặc nhận API/SSE đã kiểm thật.

## Kế hoạch tự kiểm

- Unit/service/controller: input/response/session consistency; phân loại lỗi; hủy và bỏ reply cũ; không tự retry POST. Timeout/mất phản hồi hướng GET kiểm lại phiên, không hứa rollback.
- Luồng: mount/F5/đổi tab không gửi nguồn; A hợp lệ→B422→A còn→sửa đầu vào→gửi lại. GET sau reload hiện nguồn thật, không fallback fixture vào runtime.
- Browser khi được giao: picker/drop, progress/analysis, keyboard/focus/dialog, responsive/zoom; PDF/quá10MB và sát giới hạn; read-only/ẩn Blueprint, không lộ account cũ.
- Confirm: rỗng/loading/ingesting/pending/double-click không gửi;409 đọc lại nguồn/status; rule đúng Q03; không nhận callback fixture là Stage2 thật.
- Nội dung minh họa, chưa tạo fixture/chưa chạy parser: `3x-5=10`, A:x=3/B:x=4/C:x=5/D:x=6, keyC; `(x²-9)/(x-3)` với x≠3, đáp án x+3. Dùng thêm hệ/tập nghiệm có điều kiện theo handoff Đại số, không ảnh.
- Trước Ready, từ frontend: `npm.cmd run test` hoặc suite liên quan, `npm.cmd run lint`, `npm.cmd run build`, ghi head/kết quả. CI/Approve/merge theo CONTRIBUTING. Plan-only kiểm Markdown/link/diff; không bịa tests sản phẩm pass.

## Bàn giao — điền theo kết quả thực tế

- Đã có M2, Draft PR29 và phản hồi/answers củaDuy có permalink. Bản cập nhật30/10 đối chiếu code nhánh hiện tại và giữ mức bằng chứng từng câu hỏi; chưa có code TASK-201 hoặc kiểm UI/API/cloud W2 từ nhánh này.
- Nhánh: `feat/task-201-stage1-source`; commit plan khởi đầu50b81b5, PR29 vào dev. TASK203b có plan riêng trên PR31. Không ghi SHA của chính bản cập nhật vào file để tránh vòng commit tài liệu.
- Duy đã nhận review chính và chấp thuận kế hoạch trong answers; không coi đó là GitHub Approve hoặc nghiệm thu code mới. Chưa có code TASK-201 để xác minh findings; chưa Done/Ready chỉ vì plan đã lưu.
- Kiểm phù hợp cho cập nhật chỉ tài liệu: Markdown, liên kết tương đối, tính nhất quán snapshot/scope và git diff. Chưa chạy product tests cho bản cập nhật này; CI trước merge vẫn theo CONTRIBUTING.
- Bước tiếp: đối chiếu gate/head/input trước lượt3, triển khai service/input/controller201 theo từng mốc khi được giao; nhận model lỗi/dialog từ203b và giữ phần confirm/Stage2 theo owner204. User đã hỏi phần thiếu trênPR29, không tạo phản hồi trùng hoặc tự ghi tất cảResolved.

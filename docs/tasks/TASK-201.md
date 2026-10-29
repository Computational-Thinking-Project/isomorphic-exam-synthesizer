# TASK-201 / TASK-203b / TASK-204 — M2 Stage1 nguồn đề

- Trạng thái: Draft — plan/input; chưa code W2 trong lượt này.
- Nguồn giao việc: `w2_21_10.md` do Duy giao, bản workspace `project/W2_ASSIGNMENT_20261026.md` khớp nội dung. Link assignment chung do leader quản lý: TBD; chưa có file tuần này trong repo, không tạo M1 cạnh tranh.
- Phụ trách: Trung Anh / philip-kkk / TV1 / FE1. Reviewer, dự phòng và ETA: TBD; chưa tự giao cho người từng review W1.
- Workflow: [v0.1 proposed](../review/WORKFLOW.md), docs commit506384b; dùng [M2/M3](../review/TEMPLATES.md). Merge docs không chứng minh pilot/rollout đã đạt.
- Nền hiện tại đã đọc: dev `813f497` ngày29/10, có PR17/15/18/23/16/22. User đã tạo nhánh `feat/task-201-stage1-source`, cùng SHA với local dev/origin/dev lúc kiểm. PR URL/head plan sau commit: TBD, chưa có bằng chứng Draft đã tạo.
- Tổ chức đề xuất: một Draft chung cho Stage1, phân rõ ba task và code từng lượt nhỏ. Nếu diff lớn hoặc confirm tiếp tục phụ thuộc, cân nhắc tách204 trước khi thực hiện nó; không tạo hai bản preview/hook cạnh tranh.
- Hạn nguồn W2:21–31/10/2026. Hạn chuyển tiếp, mốc code cho đợt cũ, ETA input/task: TBD, Duy/owner xác nhận. Không tự đổi thành03/11. Nhịp mới thường code từ thứ6, không mặc định thay lịch W2 cũ.

## Mình cần làm gì?

- 201: trong phiên draft có ID, nạp DOCX/TeX/MD hoặc text; chặn PDF/file quá10MB; phân biệt tiến trình upload và đang phân tích. Không POST khi mount/F5/đổi tab.
- 203b: nhận incomplete422 có `detail.errors`; chỉ rõ lỗi toàn đề/câu và hướng sửa đầu vào, chọn lại file/chuyển text. Nguồn A phải còn sau khi B bị422 theo dữ liệu server; FE không tự restore DB.
- 204: preview nguồn/options/key bằng MathRenderer, chỉ đọc, Blueprint ẩn; confirm và bàn giao FE2 theo contract/readiness/security được chốt. Chưa tự khóa success-state hoặc rule an ninh còn xung đột.
- Ngoài phạm vi: làm lại Auth/Dashboard/create/detail; sửa parser/DB/Storage/AI; editor kết quả/xóa câu/autosave/Blueprint UI; config/SSE/Stage2/export; đổi stack/dependency.
- Nội dung ví dụ: Đại số không cần hình; giữ điều kiện, công thức, A–D và key đúng. UI không chứng minh parser/generator phủ toàn bộ Đại số.

Hiện đã có [Stage1Route](../../frontend/src/features/stage1-ingestion/Stage1Route.jsx), sessionEntry, services/sessions cho new→POST→ID/detail; client Auth chung và [MathRenderer](../../frontend/src/components/MathRenderer.jsx). Giữ các phần này, chỉ mở rộng nguồn tại phiên draft đã có ID.

Ingestion và confirm đã có source. PR22 đã vào nền813f497: App có `/session/:sessionId/stage2` nhận bởi `Stage2ConfigPage`; Dashboard cũng đã map blueprinted/configured/generating tới Stage2. Không thêm lại route hoặc làm màn thay FE2. Chưa kiểm runtime/cloud/migration hay luồng Stage1→Stage2 thật trong lượt này. Gate toàn W1 vẫn cần xác minh trước code: lần REST29/10 trước ghi PR19/TASK107c và PR20/TASK107d Open/unmerged, chưa audit lại vòng này. Plan/Draft không tự mở khóa code W2.

## File và thứ tự triển khai từ mốc code được xác nhận

Tên file mới là đề xuất; lượt này chưa tạo component/service/test hoặc thay runtime.

| Lượt / file dự kiến | Mục đích sửa | Output mong muốn | Input cần trước | Cách kiểm |
|---|---|---|---|---|
|2: `docs/tasks/TASK-201.md`|Lưu M2 này trên nhánh task đã tạo|Một nguồn plan ba task và Draft trước code|User commit/push/PR theo quyền; chưa code sản phẩm|Link, Markdown, diff, body Draft đúng head|
|3: `frontend/src/services/ingestion.js` và tests|Dùng `services/api.js`; request text/file, signal/progress; không client mới|Text `{raw_text}`, multipart trường `file`; response đúng phiên|Contract ingestion; gate W1 và user giao code|HTTP/adapter fixtures theo hạ tầng repo, không tự retry POST|
|3: `features/stage1-ingestion/useStage1Source.js`, `Stage1Page.jsx`; mở rộng ID draft trong `Stage1Route.jsx`|Quản lý input/nguồn đã lưu/request; giữ form new và tạo phiên|Text→gửi rõ ràng→kết quả; F5 GET nguồn; không giữ dữ liệu account/ID cũ|Current detail và response ingestion|Pending/cancel/stale/account/ID; nguồn đúng sau GET|
|3: `SourceQuestionPreview.jsx`|Preview tối thiểu dùng chung qua MathRenderer|Stem/A–D/key chỉ đọc, không ép format tích phân; chưa nhận204Done|Source shape đã đọc|Key/công thức/điều kiện/dữ liệu dài; không editor/Blueprint|
|4: `stage1Errors.js`, `IncompleteContentDialog.jsx` và tests|Phân biệt incomplete422 và lỗi khác; hướng sửa đầu vào|Lỗi toàn đề không “Câu0”; chọn lại file hoặc tabtext|ParserErrorItem và detail.errors|A→B422→A còn; unknown/FastAPI422/confirm422 không bị nhận nhầm|
|5: panel input/file trong `Stage1Page.jsx`|Chọn/kéo thả ba đuôi;10MB; progress riêng analysis|Chọn lại cùng file, giữ input khi lỗi; hủy/khóa gửi chồng|Giới hạn BE/settings và môi trường xác nhận|Picker/drop/boundaries/progress/focus trên browser; không gọi Storage trực tiếp|
|6: `services/confirmation.js`, panel confirm và callback điều hướng Stage1|Hoàn thiện204 theo contract, dùng route Stage2 đã có, không thêm App route trùng|Confirm→nhận/đọc lại trạng thái→Stage2ConfigPage đúng ID|Q02–Q05; không suy200/blueprinted/fallback là AI-ready|409/422/pending/double-click/readiness; tách fixture và API thật|
|7: Stage1/frontend README, change_log khi cần, M3|Bàn giao đúng head/checks/giới hạn|Ready khi phần được giao thực sự đạt; không che blocker|Input thật/màn FE2/CI/reviewer|Checks phù hợp và evidence, không nhận toàn W2 đã xong|

## Đầu vào và câu hỏi — giải đáp trên Draft PR trong thứ 5

Các câu hỏi chưa gửi. Quyết định cập nhật vào contract của owner và dẫn link lại; M2 không định nghĩa API/schema cạnh tranh.

| Cần ai/task nào | Câu hỏi/input cụ thể | Cần trước | ETA bên cung cấp xác nhận | Phần làm ngay/chờ | Link trả lời/contract |
|---|---|---|---|---|---|
|Q01 — Duy/leader và user|Gate toàn W1 merge; link assignment chung; reviewer/dự phòng; hạn W2 cũ và need-by/ETA input/task theo lịch chuyển tiếp?|Trước code; lịch trước cam kết|TBD|Plan/Draft, chưa code khi gate còn thiếu|TBD|
|Q02 — Duy + AI + FE2|ADR0001 yêu cầu confirm/hash trước Blueprint; endpoint hiện ensure/fallback rồi chốt blueprinted. Bản nào là chuẩn tích hợp, JSON success/pending/error/readiness/retry nào FE dùng?|Trước ghép confirm success|TBD|Ingest/dialog/preview độc lập; chưa thêm polling/enum/API|TBD|
|Q03 — Duy/owner contract và user|Assignment204 đòi badge/ack; ADR004/contract đã merge silent audit và bỏ qua ack. Xác nhận yêu cầu FE có badge/ack hay không, cập nhật nguồn phân công?|Trước code rule an ninh204|TBD|Preview; không tự thêm/bỏ policy theo ảnh/file cũ|TBD|
|Q04 — Bội Anh/FE2 và Duy|Route `/session/:sessionId/stage2`/Stage2ConfigPage đã có từ PR22. Chốt status/mode và GET detail/JSON readiness dùng thật: stage2Service đọc blueprint_summary hoặc Blueprint gắn câu nguồn; response confirm/current detail có đủ không?|Trước navigate/kiểm204 xuyên suốt|TBD|Dùng màn có sẵn, không placeholder; chưa nhận route tồn tại là tích hợp đạt|TBD|
|Q05 — Duy/OPS|Runtime commit, migration002/003, Storage/DB grants đã áp ở môi trường nào, kiểm với user JWT ra sao? JSON thực200/422/409 cho text/file?|Trước kiểm API/cloud thật|TBD|Fixture ghi nguồn/SHA; không SQL/cloud/AI ngoài quyền|TBD|

- Output giao FE2: session ID, nguồn đã xác nhận và trạng thái/readiness đúng Q02/Q04. Giao BE1 payload/lỗi có thể tái hiện, không token/nội dung mật. Mốc cần nhận, ETA giao/nhận và hoàn tất: TBD.
- Tính khả thi: gate W1 chưa xác minh đủ (lần trước PR19/20 còn mở), Q02–Q05 chưa đủ, hạn nguồn31/10 gần. Chưa đủ căn cứ cam kết hoàn tất204/xuyên suốt; cần Duy điều phối input/hạn, không tự đổi deadline hoặc coi hết ngày là đồng ý.
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

- Đã đọc source/contracts và chuẩn bị M2/M3. User đã tạo đúng nhánh; M2 đã được đưa vào repo trong lượt2, chưa triển khai201/203b/204, chạy kiểm sản phẩm hoặc tích hợp cloud.
- Nhánh: `feat/task-201-stage1-source`. Commit plan/PR URL/head sau push: TBD, user thực hiện theo quyền. Không nhận Draft đã tạo nếu chưa có URL/metadata.
- Chưa có review/finding/approval cho code mới. Không nhận Done vì có plan hoặc nhập được fixture.
- Bước tiếp: kiểm/stage M2, user commit plan/push/mở Draft vào dev và giải đáp Conversation. Chỉ chuyển lượt code sau gateW1, Draft và user giao việc; chưa khóa confirm khi Q02–Q05 còn thiếu.

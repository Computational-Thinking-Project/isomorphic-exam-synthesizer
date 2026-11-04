# TASK-201 — Nhập nguồn Stage1 và bàn giao cho203b/204

- **Checkpoint04/11/2026:** tự kiểm chức năng frontend đã có kết quả. P1/P2 đã công bố tại24cfe3c; P3 đã commit local241a1ae, sửa zoom08f0cb2; tài liệu nghiệm thu lưu ở mốc riêng. Chưa push các mốc mới hoặc có CI tương ứng. Không nhận Ready/Done hoặc reviewer Approve từ việc tự kiểm.
- Author: Trung Anh / philip-kkk / TV1 / FE1. Nhánh `feat/task-201-stage1-source`, [PR29](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29), targetdev. Nền đã ghép `ada29633b721765a3e0eaae5f8accfb908e48bd8`; không cần tạo lại luồng Auth/Dashboard/new/detail.
- Workflow [v0.1 proposed](../review/WORKFLOW.md), docs506384b; dùng [M2/M3](../review/TEMPLATES.md). Reviewer chính Duy đã nhận theo answers29/10; Bội Anh do user chọn phối hợp FE/Stage2, chưa có xác nhận/ETA riêng. Không tự request review hoặc đăng Conversation.
- Assignment: `w2_21_10.md` của Duy, bản workspace `project/W2_ASSIGNMENT_20261026.md`; link assignment chung còn TBD, không tạo M1 cạnh tranh. Hạn chuyển tiếp tối03/11/2026 do Duy xác nhận giữ nguyên; kiểm tiếp04/11 không tự dời hạn. GateW1 đã khép theo mergePR19/20 của Tâm/AI-WFox vào nềnada2963.

## Hành vi và phạm vi

Trong phiên draft có ID, giáo viên nhập text hoặc chọn/kéo thả một DOCX/TeX/MD rồi chủ động bấm Nạp nguồn. Chọn file, sửa text, đổi cách nhập, mount/F5 không tự nạp. Text được kiểm1–100.000 Unicode codepoints sau Python-compatible strip; file1byte–10MiB, whitelist ba đuôi, PDF bị chặn trước gửi. Backend tiếp tục kiểm nội dung/bytes/parser.

Nguồn đã lưu tách khỏi input chưa gửi. Response hợp lệ mới thay nguồn/count cùng snapshot. Preview stem/options/key bằng MathRenderer, chỉ đọc, Blueprint ẩn. Nguồn cũ và input được giữ khi incomplete422; raw HTTPcause giữ để ghép model/dialog từ [TASK203b/PR31](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/31).

Upload có total mới tính phần trăm;100% chỉ là tải lên xong, vẫn chờ xử lý/response. Khóa gửi/mode trong pending; AbortController/revision/account/route guard cả progress và response.409 yêu cầu GET, non-draft chỉ đọc. Timeout/cancel/5xx/invalid200 là kết quả chưa rõ: giữ nguồn cuối đã biết, khóa gửi lại và cho GET đối chiếu. GET không chứng minh rollback hoặc POST cũ đã dừng; khóa này không bền qua F5. Không thêm retry POST ngoài refresh401 chung của client.

Đại số không cần hình là nội dung mẫu, không phải coverage đã đạt. Ngoài scope: backend/parser/Storage/schema/AI, editor/autosave/xóa câu/Blueprint UI, dialog203b, confirm204/readiness/Stage2/SSE/export, đổi stack/dependency. Preview tối thiểu không thay nghiệm thu toàn204.

## File và mốc triển khai

| Mốc | File chính | Output / kiểm |
|---|---|---|
|P1, đã công bố|[ingestion.js](../../frontend/src/services/ingestion.js), [tests](../../frontend/src/services/ingestion.test.js)|ingestText/ingestFile, validate input/response, signal/progress qua client chung;22tests service|
|P2, đã công bố|[controller](../../frontend/src/features/stage1-ingestion/sourceIngestion.js), [tests](../../frontend/src/features/stage1-ingestion/sourceIngestion.test.js), [panel](../../frontend/src/features/stage1-ingestion/Stage1SourcePanel.jsx), [preview](../../frontend/src/features/stage1-ingestion/SourceQuestionPreview.jsx)|Text/pending/saved/error/uncertain, count/source cùng snapshot; giữ new/create/detail của [Stage1Route](../../frontend/src/features/stage1-ingestion/Stage1Route.jsx)|
|P3, commit local241a1ae|Panel/controller và [component tests](../../frontend/src/features/stage1-ingestion/Stage1SourcePanel.test.js)|Picker/drop, reset để chọn lại cùng file, tên/dung lượng, input giữ qua đổi mode, tiến độ upload và lifecycle guard|
|P4, zoom commit local08f0cb2; docs mốc riêng|Stage1Route, M2 và README|Native200% phát hiện source bị ép dù CTA còn hiện; thêm min-height40rem cho existingID workspace để trang cuộn dọc khi thấp. New form/logic API không đổi.285tests/lint/build và Docker/frontend/browser kiểm sau sửa|

Shared test harness chỉ bổ sung chuẩnDOM Text/Comment.nodeValue phục vụ React cập nhật count; không mock React internals trong tests mới. Không đổi Auth/store/api client, timeout15s, backend, Stage2/Stage3, package/lockfile. Không có quyết định schema/stack/contract mới cần ADR từ code frontend này.

## Input và contract — kết luận hiện hành

Duy đã [trả lời Q01–Q05](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499240459), [answers nguồn](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/5cd570b2fbd51a7f847c230b67f2ae4803faa325/docs/tasks/TASK-201_ANSWERS.md). Không hỏi tìm answers lại hoặc nhận tất cả resolved từ lời đề nghị trong comment.

| Mục | Kết luận / phạm vi còn lại |
|---|---|
|Q01|Duy nhận reviewer chính; hạn03/11 đã chốt. Assignment link chung, backup, ETA phối hợp/review còn TBD. Không coi nhận plan là Approve code.|
|Q02|Partial, phần204: [ADR0001](../adr/0001-confirm-before-blueprint.md) yêu cầu confirm/hash trước canonicalBlueprint; code nền có ensure fallback trướcRPC. Không nhận fallback/count/statusblueprinted/confirm200 là AI-ready hoặc toàn pipeline atomic.|
|Q03|Silent audit đã chốt theo [change_log](../change_log.md): không checkbox/modal ack, không chặn flow vì badge. Không làm UI bảo mật riêng trong201.|
|Q04|Phần204/FE2: summary/modes/readiness cần contract và tích hợp đúng bản. PR29 không ghép các nhánh runtime hoặc dựng màn thay FE2; route [Stage2](../../frontend/src/features/stage2-config/Stage2ConfigPage.jsx) đã có.|
|Q05|L01 ban đầu500/PGRST202 vì RPC không resolve. User SELECT báo0rows, đã chạy nguyên [migration002](../../backend/migrations/002_replace_source_questions_rpc.sql) bọc transaction và gửi ảnh signature/args/authenticated=true/anon=false. Sau đó user kiểm live text/file/F5 thành công. Chưa audit mọi Storage object/runtime/grant hoặc direct non-ownerPOST/RPC; không chạy lại fullschema/003 hay nhận môi trường toàn phần đã đạt.|

[Ingestion v1.0](../api/ingestion-endpoints.md): JSON raw_text hoặc FormData fieldfile, response200 session_id/total_questions/questions. [Schemas](../../backend/app/models/schemas.py) và [validator](../../backend/app/services/parser/validator.py) là nguồn kiểm structure/parser. GET dùngsource_questions, không nhầm với questions của response ingest. [Confirm contract](../api/confirm-source-endpoint.md) thuộc điểm nối204, không triển khai confirm service từ201.

## Kiểm đã thực hiện

### Tự động / mô phỏng

- Candidate sau sửa zoom04/11: từfrontend `npm.cmd test` **285/285passed,0skip**; `npm.cmd run lint` và `npm.cmd run build` đạt. Bundle956.34kB còn warning>500kB. Cuối lượt chỉ đổi docs; đối chiếu hash để xác nhận runtime/tests vẫn đúng bản đã kiểm, không nhận đã rerun nếu không chạy.
- Trong tổng285 có22service,29controller và14component/route/SSR cases cho ingestion; không cộng các suite riêng lần nữa. Auth/HTTP thay thế, service/store/controller/ReactDOM thật. Kiểm request/response/Unicode/size/count/permission errors/cancel/stale progress/401 chung, sourceA giữ khiB422 và new/F5 khôngPOST bằng harness.
- Mốc100% vẫn pending và thiếu total dùng indeterminate đã kiểm service/controller/component; native chỉ ghi nhận pending/cancel, chưa quan sát riêng mốc100%.
- Docker backend/frontend build/Healthy, health/frontendHTTP/APIproxy đạt. Parser/security/validator in-memory đọc bộ Đại số tự soạn MD/TeX/DOCX trả2câu/keyC,A/0errors; bản thiếu key phát hiệnMISSING_ANSWER. Không dùng phép kiểm này thay HTTP/DB/Storage/AI.

### Docker/Google/API thật và native UI

Bộ mẫu: câu1 giải3x−5=10, optionsx=3/4/5/6, keyC; câu2 rút gọn(x²−9)/(x−3),x≠3, optionsx+3/x−3/x²−3/1, keyA. Nguồn tự soạn, không teacher/AIbenchmark. Kết quả sau do user kiểm theo từng ca, trừ khi ghi agent.

| Ca | Kết quả / nguồn bằng chứng |
|---|---|
|Text/MD/TeX/DOCX trong cùng draft|User báo2câu/keyC,A, công thức/điều kiện đúng;F5giữURL/nội dung. Không tạo/clone phiên mới.|
|Nạp bản thiếu key|User báo lỗi đúng và giữ file; logbackendPOSTfile422; agentGET/reload xác nhận nguồn2câuC/Agiữ.|
|Empty/10MiB+1/nhiều file/.txt/PDF thật|User xác nhận lỗi tại chỗ trướcNạp; agent đọc source2câuC/A sau nhómvalidation. PDF native được user kiểm riêng, không dùng.txt thay thế. Không có networktrace riêng từng lượt.|
|Chọn lại cùng file / đổi text-file|User bỏ chọn/chọn lại cùngMD đạt; agent kiểm mode switch giữ cả input/file và khôi phục input ban đầu, không bấmNạp.|
|Đang gửi/hủy|User3G/file64KiB/khóa gửi-mode/Dừngchờ→uncertain/submitkhóa đạt; mạng vềNoThrottling. AgentGET thànhcông vẫngiữalert/khóagửi/source2C,A/file đãchọn. Không suy serverrollback hoặc POST đãdừng.|
|Tài khoản|User cùngtabA→B: BkhôngmởA/khôngsource/formA; trởA:nguồn2C,Agiữ,text/filetransientrỗng. Chưa directBPOST/RPC live-test.|
|Zoom/mobile|Agent sửa/kiểm200%CSS741×339/DPR2.5, cócuộndọc/key/CTA/fileinputđọcđược;usertrả100%báobìnhthường. Agent kiểm lại candidate ở375×812CSS thật,2modes/nguồn/cuộn/CTA đạt, khôngtrànngang; đã reset viewport.|

## Giới hạn cần reviewer đánh giá

- Một input1MiB gồm bộ mẫu cộng đệm khoảng trắng chạm giới hạn20s của phép kiểm parser in-memory, exit124/khôngoutput. Chưa profiling/rootcause hoặc sửa backend. Mẫu64KiB có preamble qua parser và dùng cho ca pending/cancel. Không nhận mọi file≤10MiB xử lý ổn trong timeout15s; Duy cần đánh giá quan sát này khi review trước khi chốt giới hạn tích hợp.
- Không có AI/Gemini run, confirm/Stage2/SSE/PDF export, coverage Đại số, direct non-owner mutation test hoặc Storage object audit mới. BịchặnPDFinput không phải chức năng xuấtPDF.
- LỗiPGRST202 ban đầu và lỗizoom giữ trong log lịch sử; migration002 do user chạy, không phải agent deploy cloud. File test/ảnh/log nằm ngoàirepo trên máyowner; trước review có thể attach/share theo quyền. Bảng nghiệm thu này là phần được đưa cùngPR, không nhận reviewer đã nhận localfiles.

## Bàn giao / bước trước merge

Output cho203b: lỗi gốc/cause và thao tác sửa/chọn lại nguồn; cho204:sessionID/source snapshot/preview chỉ đọc, không readiness/confirmed-state. M3 theo [template](../../.github/pull_request_template.md), khai báo sharedfiles và các giới hạn trên. Theo quyền user04/11, đã lưu local241a1ae `feat(stage1): add source file upload` và08f0cb2 `fix(stage1): keep source readable on short viewports`; tài liệu nghiệm thu lưu ở mốc docs riêng, không ghi SHA của chính file vào file.

PR29 hiện công bố24cfe3c với5CIchecks success, chưa phải CI cho các commit local mới. Chưa có formal review/inline findings ở lần đọcGitHub04/11. Bước tiếp khi user giao push/cập nhật PR: công bố đúng head/body, chờCIheadcuối và ít nhất1Approve thật theoCONTRIBUTING trướcmerge. Quyền lượt04/11 chỉ lưu commit local; chưa push/đăngPRbody/Ready/requestreview/merge hoặc nhận201/203b/204Done từ gói tự kiểm.

# TASK-203b — Stage1 Incomplete Loop — M2

- **Checkpoint 04/11/2026: P1–P4 đã hoàn tất implementation và nghiệm thu local trong phạm vi dưới đây.** Full frontend308/308tests/lint/build đạt; sáu file runtime/test giữ nguyên hash của bản đã kiểm. Chưa commit/push phần code mới hoặc xác minh CI/review tương ứng; PR31 chưa được chuyển Ready từ lượt này.
- Author: Trung Anh / philip-kkk / TV1 / FE1; BE1 Duy phối hợp contract ingestion. User chọn Duy (`johannguyen015`) review chính, Bội Anh (`htbaax`) phối hợp FE khi liên quan. Duy đã nhận review chính tại PR29; ETA review riêng PR31 và dự phòng chưa chốt, không chờ chọn lại reviewer để code.
- Nhánh `feat/task-203b-incomplete-loop`, [PR31](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/31), target `dev`. Đã ghép dev chứa squash PR29 **ac18e724be377f10a3fecf2e46c2b72074410bed** bằng merge commit **6ca5b25**; không ghép lại nhánh201. Đây là nền đã kiểm, không phải SHA của chính bản cập nhật M2 này.
- Workflow [v0.1 proposed](../review/WORKFLOW.md), docs506384b; dùng [M2/M3](../review/TEMPLATES.md). Assignment: mục TASK-203b trong w2_21_10.md của Duy, bản workspace W2_ASSIGNMENT_20261026.md; link assignment chung còn TBD, không tạo M1 cạnh tranh.
- Hạn W2 chuyển tiếp **tối03/11/2026** theo [xác nhận của Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499240459). Checkpoint04/11 đã qua hạn; implementation và nghiệm thu local203b đã đạt, còn công bố code/CI/review/merge. ETA review/merge mới chưa chốt. Không tự gia hạn hoặc dùng việc đủ đầu vào để cam kết ngày hoàn tất.

## Hành vi và phạm vi

Khi một lần nạp file/text trả incomplete422 có danh sách lỗi, hiển thị dialog lỗi toàn đề/theo câu và hướng sửa đầu vào. Cho chọn file đã sửa, kể cả cùng file, hoặc chuyển Nhập trực tiếp. Người dùng chủ động bấm Nạp nguồn sau khi sửa; mở/đóng dialog, chọn file, đổi mode không tự POST.

Nguồn A đã lưu và input B bị lỗi là hai phần riêng. B422 không thay preview/count của A; không xóa input B khi đóng dialog. Đổi session/account/logout/rời trang phải bỏ dialog/lỗi và phản hồi cũ theo cơ chế201. Timeout/cancel/kết quả chưa rõ tiếp tục dùng cảnh báo và khóa của201; GET không chứng minh POST trước đã dừng hoặc rollback.

Ngoài scope: viết lại service/controller/upload/progress201, editor cho câu đã trích xuất, autosave/backup/restore DB từ FE, parser/schema/Storage/AI, confirm/readiness204, Stage2/SSE/export hoặc đổi stack/UI. Source vẫn chỉ đọc, Blueprint ẩn. Nội dung mẫu là Đại số không cần hình; không coi bộ mẫu là coverage đã đạt.

## Đầu vào đã có

- [PR29/TASK-201](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29) đã merge dev; [service](../../frontend/src/services/ingestion.js), [controller](../../frontend/src/features/stage1-ingestion/sourceIngestion.js) và [panel](../../frontend/src/features/stage1-ingestion/Stage1SourcePanel.jsx) đã có trên nhánh này. Controller giữ raw `cause`, tách input/nguồn, khóa pending và bỏ response/progress cũ; picker đã reset để chọn lại cùng file. Dùng nguyên client/Auth/store và các guard đó.
- [Ingestion contract](../api/ingestion-endpoints.md), [schemas.py](../../backend/app/models/schemas.py), [validator.py](../../backend/app/services/parser/validator.py) là nguồn chuẩn. Lỗi ingestion có dạng `{detail:{message,errors:[{question_no,error_type,message}]}}` trong `cause.response.data`; cần đồng thời kiểm HTTP422. FastAPI422/detail array, confirm422/detail string,400/409/429/network/timeout không phải cùng loại lỗi.
- `question_no=0` biểu thị lỗi toàn đề; số nguyên dương hiển thị CâuN. Số/vị trí không hợp lệ dùng nhãn dự phòng, không hiển thị Câu0 hoặc tự đoán câu liên quan. Unknown error_type vẫn có thông báo/hướng sửa chung. Payload rỗng hoặc sai shape không gây crash hay mở dialog rỗng, giữ thông báo lỗi chung.
-10mã hiện hành: `MISSING_ANSWER`, `UNPARSED_OMML`, `UNPARSED_IMAGE`, `AMBIGUOUS_FORMAT`, `EMPTY_STEM`, `CONFLICTING_ANSWER_KEY`, `SURPLUS_ANSWER_KEY`, `DUPLICATE_QUESTION_NO`, `INVALID_QUESTION_NO`, `INVALID_FORMAT`. Hướng sửa bám mã: bổ sung/chốt key, sửa cấu trúc/câu/số thứ tự hoặc chuyển công thức sang text/LaTeX phù hợp. Với ảnh/hình bắt buộc, báo giới hạn đầu vào; không hứa tự chuyển ảnh/OCR hoặc bỏ qua lỗi để nạp. Message chỉ render như text, không HTML.
- [Nghiệm thu201](TASK-201.md): user kiểm B thiếu key bị lỗi và giữ fileB; log POSTfile422, agent GET/F5 xác nhận A vẫn2câu/keyC,A. Đây là bằng chứng từng phần cho giữ nguồn, chưa phải dialog203b, mọi mã lỗi hoặc Storage audit. Không hỏi lại như chưa có bằng chứng nào.
- Gate toàn W1 đã đạt: [PR19](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/19) và [PR20](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/20) của Tâm/AI-WFox đã merge31/10. Phụ thuộc201 đã nhập qua dev; không còn hai blocker này.

## File và thứ tự triển khai P1–P4

Các file203b mới nằm trong `frontend/src/features/stage1-ingestion/`. P1–P3 đã có implementation local; P4 đã khép kiểm tự động, browser fixture và các ca Docker/API thật do user báo. Code mới chưa được công bố.

| Lượt / file | Mục đích và output | Đầu vào đủ dùng | Kiểm trước bàn giao |
|---|---|---|---|
|P1 — stage1Errors.js và stage1Errors.test.js, local|Hàm thuần đọc rawcause, nhận dạng incomplete và tạo nhãn lỗi/hướng sửa, giữ unknown fallback|Contract/schema/validator hiện hành; không gọi API|9tests/lint đạt: phân loại, vị trí,10mã/unknown/malformed, giữ input và text an toàn|
|P2 — IncompleteContentDialog.jsx và tests, local|Danh sách lỗi, close/Escape/Tab/focus và hai hành động file/text, theo UI hiện có|Error model P1 và props bên dưới|7tests/lint đạt: đóng/focus/callback/markup và danh sách dài; native kiểm thêm ở P4|
|P3 — Stage1SourcePanel.jsx và tests, local|Ghép cause/dialog/picker/focus, không đổi controller/service201|Code201 và P1/P2 đã đạt|7integration mới;72ca liên quan đạt, gồm gửi lại cùng error object, không tự POST, lỗi GET/timeout/route/logout|
|P4 — README/M2/M3 và evidence, đã tự kiểm|Kiểm hồi quy/UI/API, bàn giao đúng bản và giới hạn|P1–P3 đã đạt, frontendDocker mới Healthy|308tests/lint/build đạt; nativefixture374/376CSS; userPASS L01/L02/L03a/L03b/L04a/L04b gồm Chrome200% vàF5. Chờ công bố/CI/review|

## Interface và hành vi ghép đã chốt cho plan

- P1: `readIncompleteError(cause)` trả `null` khi không có incomplete envelope đủ dùng; với lỗi hợp lệ trả `{message,errors}`, item gồm `location/title/detail/guidance` là string. Không sửa rawcause/source/input/state hoặc gọi mạng/DOM. Unknown code có fallback; danh sách trộn malformed giữ fallback từng item, tất cả item không hữu ích thì dùng thông báo chung. Giữ thứ tự và nhiều lỗi cùng câu, không tự gộp/xóa.
- P2: props `open`, `errors`, `onClose`, `onChooseFile`, `onSwitchToText`. Component chỉ hiển thị và phát hành động; không tự ingest, GET, sửa nguồn hoặc mở khóa uncertain. Theo cấu trúc/style và cách keyboard của [CloneSessionModal](../../frontend/src/features/dashboard/CloneSessionModal.jsx), không tạo thư viện dialog mới hoặc sửa modal Dashboard.
- P3: panel tạo model từ cause bằng useMemo, chỉ mở khi `controller.canSubmit()` và cause chưa được đóng. Một `dismissedCause` ghi lỗi đã đóng; reset trước submit được phép để cùng error object ở lần nạp mới vẫn mở được. Controller201 không đổi. Không mở lại từ rerender/mode change hoặc lỗi GET có requiresReload; không lưu dialog vào localStorage hay thêm request state.
- `onChooseFile`: đóng dialog, giữ source/text/file cho tới khi chọn mới, setModefile và gọi một picker luôn mounted ngay trong click của user; filepanel bị ẩn khỏi hiển thị/tab order ở mode text. Không dùng timer/retry để mở picker hoặc tự upload. `onSwitchToText`: đóng dialog, setMode hiện có và focus textarea sau mount, giữ text chưa gửi. Pending focus chỉ dùng ref và effect ở panel.
- `onClose`: chỉ đóng dialog, không xóa source/input/cause hoặc tự POST. Focus về control đã mở nếu còn hợp lệ; hành động đổi mode focus input đích. Khi account/route đã rời hoặc control disabled/unmount, không cố focus DOM cũ. Có nhãn dialog, aria-modal, Tab/Shift+Tab trong dialog, Escape và focus return.
- Giữ guard201: submit bắt đầu thì lỗi cũ không tiếp tục mở; đổi session/account/logout/unmount bỏ dialog, response/progress cũ bị bỏ. Không đổi timeout15s/401-refresh chung, không phân loại timeout/5xx/invalid200 thành lỗi có thể gửi lại an toàn.

Đây là interface nội bộ FE để triển khai; không thay contract API/schema và không cần owner backend quyết định thêm trước P1. Có thể điều chỉnh chi tiết cài đặt khi code nếu giữ các hành vi và cập nhật plan tương ứng.

## Câu hỏi và phụ thuộc — trạng thái04/11

| ID / người liên quan | Kết luận đủ để bắt đầu | Phần còn lại |
|---|---|---|
|203b-Q01 — Trung Anh/TASK201|Resolved về đầu vào:201 đã merge, nhánh203b đã syncdev6ca5b25; interface/callbacks đã ghép local|P1–P4 tự kiểm/nghiệm thu local đã đạt; còn commit/push, CI và review đúng head trước merge|
|203b-Q02 — Duy/BE1|Đã có contract/schema/validator và bằng chứng giữ nguồn201 từng phần, đủ code classifier/dialog|Dialog/envelope và vòng sửa→nạp đã kiểm trong phạm vi dưới đây; chưa Storage audit/direct non-owner mutation|
|203b-Q03 — Duy + Trung Anh|Hạn03/11 và reviewer đã rõ; không chờ quyết định kỹ thuật mới|Assignment link chung, ETA hoàn tất/review/dự phòng còn TBD; không tự gia hạn, không coi là blocker P1|
|203b-Q04 — Tâm; Duy điều phối|Resolved: PR19/20 merge31/10, gateW1 đạt|Không tiếp tục lấy W1 làm blocker|

Confirm/hash/Blueprint và readiness Stage2 còn ở TASK-204, không phải blocker code203b. Silent audit đã chốt, không thêm checkbox/modal an ninh. Không cần lấy PR30/32 hoặc generation/runtime support để làm classifier/dialog; trạng thái những PR đó không được xác minh lại chỉ từ việc sửa M2 này.

## Kế hoạch kiểm và mốc lưu

- Mỗi lượt theo plan→code→review→audit: chốt hành vi/điểm sửa; code đúng phạm vi; tự đọc diff/M2 và đường lỗi; chạy checks phù hợp và ghi giới hạn. P1/P2/P3 chỉ chuyển tiếp sau khi đạt. Đây là author tự kiểm, không thay reviewer độc lập/Approve; không mở thêm agent hoặc bắt review ngoài sau từng sửa nhỏ.
- P1 dùng Node runner hiện có, không thêm dependency: ca phân biệt envelope/status, toàn đề/câu, nhiều lỗi, mã hiện hành/unknown, message thiếu, cấu trúc sai/rỗng. Kiểm output hữu ích và không làm thay đổi input; không chỉ sao chép switch implementation vào tests.
- P2/P3 dùng harness/component hiện có cho hành vi; kiểm keyboard/focus thật ở P4. Không nhận DOM giả là native browser. Mốc file chọn lại/mode switch phải qua input của201, không tạo endpoint hoặc flow retry thứhai.
- Hồi quy: file/text,422giữ A/inputB, pending/duplicate/cancel/uncertain/GET, route/account/logout/late reply và new/F5 không tự nạp. Sau mỗi mốc code chạy suite liên quan; trước gói review chạy `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build` từfrontend và ghi head/kết quả.
- P4 native/API: A hợp lệ→B thiếu key422→dialog đúng/còn inputB→đóng/GET/F5A còn→sửa nguồn→chủ động nạp thành công; thêm toàn đề/câu, same-file, switchtext, Escape/Tab/focus return và mobile/zoom. Ca unknown/malformed dùng mô phỏng có nhãn nếu backend không tạo được thật; không sửa backend/cloud hoặc gọi AI chỉ để lấp ca.
- Giữ giới hạn201: chưa live-test riêng direct non-ownerPOST/RPC, Storage object audit hoặc native upload100%; parser1MiB trailing spaces chạm timeout20s còn cần đánh giá riêng. Không biến các điểm này thành kết quả203b hoặc mở rộng sang sửa backend trong PR31.
- Mốc commit dự kiến theo quyền user, sau checks: `feat(stage1): classify incomplete ingestion errors`; `feat(stage1): add incomplete content dialog`; `feat(stage1): connect incomplete source recovery`; docs/evidence theo mốc phù hợp. Không tự commit/push từ việc cập nhật M2; không bắt chia commit chỉ theo số file.

## Bàn giao thực tế và phần còn lại

- Đã syncdev6ca5b25 trước lượt này: merged tree so devac18e72 chỉ thêm plan203b, không đổi runtime. Baseline mới sau merge đã **285/285frontend tests,0fail/skip, lint/build đạt**, Node22.20/npm10.9.3; bundle956.34kB warning giữ. Full diff từ nhánh cũ có11whitespace entries trong docs upstream; scoped diff-check so dev đạt, không sửa ngoài scope.
- Sau user giao thực hiện plan, P1/P2/P3 đã code local và qua từng vòng; full **308/308tests,0fail/skip, lint/build** đạt trên candidate hiện tại, bundle961.68kB warning. Các suite9/7/72 đã nằm trong tổng308, không cộng lại. Không đổi service/controller/API/Auth/store/harness/backend hoặc dependencies, không chạy backend/cloud/AI mới.
- Browser native dùng Auth/HTTP fixture: dialog whole/câu/unknown, markup hiển thị text/khôngimg; Shift+Tab/Tab vòng, Escape trảfocus vềNạp, input giữ và POSTkhông tăng khi đóng.20lỗi dài cuộn tớiCâu20, CTA còn hiện ở374/376×812CSS, không tràn ngang. Windows scaling khiến request375 thành300, hiệu chỉnh được374/376; không nhận đúng375 từ fixture; zoom200% thật được user kiểm riêng tạiL04b. Viewport đã reset. Fixture không phải API thật.
- Frontend Docker đã rebuild riêng và Healthy, backend/env giữ nguyên. Agent GET phiên test có sẵn xác nhận2câu/keyC,A; không agentPOST. **L01 PASS theo user04/11:** nạp missing-keyMD một lần, dialog đúng lỗi/hướng bổ sung keyCâu1/Câu2; Đóng vẫn giữ nguồn2C,A/filename và không tự mở lại. Đây là kết quả user kiểm đúng ca đã hỏi, không phải agent HTTP/DB/Storage audit hoặc toànP4 đã đạt chỉ từ riêngL01.
- **L02 PASS theo user04/11:** từ dialog mởpicker/chọnvalidMD, dialogđóng/filenameđổi và chưa tựnạp; chủđộngNạp1lầnbáo2câu, F5giữURL/nguồn2C,A. Đây là quan sát user trong ca đã hỏi, không networktrace hoặc DB/Storageaudit mới.
- **L03a PASS theo user04/11:** từ file incomplete dialog chuyển sang Nhập trực tiếp, dialogđóng/textdraft giữ/focustựvềtextarea/source2C,Agiữ/khôngtựnạp. Không suy pickerfromtext hoặc same-file đã kiểm từ ca này.
- **L03b PASS theo user04/11:** dialog từtextdraft mởpicker ngay qua Chọn tệp đã sửa; chọnlạicùngmissing-keyMD, dialogđóng/filenamehiện/chưatựnạp; chủđộngNạpfile1lần mởđúngdialogthiếukeyCâu1/2. Không coi đây là networktrace/DBaudit mới.
- **L04a PASS theo user04/11:** Tab/ShiftTab trongdialog/boundaryĐóng↔actiontext và clicktiêuđề rồiEscape đóng, focusNạp/khôngtựgửi. Đây là kết quả nativeUI user báo, không thay bằng agenttrace hoặc kiểmzoom.
- **L04b PASS theo user04/11:** Chromezoom200%, đọc/cuộn tới lỗi cuối và tiếp cận Đóng/2hành động không bị che; Đóng/Ctrl0 về100%/F5 giữ URL/nguồn2C,A. Cả sáu ca P4 đã đạt trong phạm vi user được hỏi. Bản ghi local là tài liệu dẫn xuất từ câu trả lời, không phải network/DB/Storage trace.
- **Kết luận author:** đủ chuẩn bị commit và gói M3; chưa GitHub Ready/Approve/merge hoặc Done toàn task. Chưa có CI/review độc lập cho code chưa commit. Gói M3 cần gắn SHA sau khi công bố; bằng chứng local/ảnh/log phải chia sẻ được cho reviewer, không dùng đường dẫn ổ đĩa riêng làm nguồn chung duy nhất. Không tự commit/push/đổiPR/đăng tin hoặc bắt đầu204. ETA review/merge vẫn TBD; không tự dời hạn03/11.

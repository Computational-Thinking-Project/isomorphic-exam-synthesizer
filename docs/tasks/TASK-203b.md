# TASK-203b — Stage1 Incomplete Loop — M2

- **Checkpoint review 04/11/2026:** bản công bố **1fc501c** đã push, PR31 đã **Ready**, 5/5 checks success; chưa merge/Approve. [Review của Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/31#issuecomment-6627687175) nêu F01/F02 blocking, F03/F04 non-blocking. Đây là đề nghị REQUEST_CHANGES trong Conversation, chưa phải review submission trên GitHub.
- **Bản sửa sau review:** F01 ở commit **5233322**, F03 ở **38c3553**; F02/F04 cập nhật trong tài liệu này. Full frontend **311/311 tests,0fail/skip, lint/build đạt**; bundle961.94kB warning, code/tests khớp bản đã kiểm. Native Chrome fixture đã tái hiện baseline thoát focus và xác nhận candidate chặn focus nền/cleanup/Tab/Escape; picker từ dialog text của panel thật mở được trong fixture. Bản sửa chưa push, chưa có CI hoặc reviewer xác minh tương ứng; không dùng CI1fc501c để nhận bản sửa đã đạt CI. FrontendDocker đã rebuild Healthy, GET phiên test vẫn2câu/keyC,A. Ca user kiểm lại picker/zoom/F5 sau sửa còn chờ phản hồi; không dùng các ca trước review để nhận bản sửa mới đã nghiệm thu thật đầy đủ.
- Author: Trung Anh / philip-kkk / TV1 / FE1; BE1 Duy phối hợp contract ingestion. User chọn Duy (`johannguyen015`) review chính, Bội Anh (`htbaax`) phối hợp FE khi liên quan. Duy đã nhận review chính tại PR29; ETA review riêng PR31 và dự phòng chưa chốt, không chờ chọn lại reviewer để code.
- Nhánh `feat/task-203b-incomplete-loop`, [PR31](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/31), target `dev`. Đã ghép dev chứa squash PR29 **ac18e724be377f10a3fecf2e46c2b72074410bed** bằng merge commit **6ca5b25**; không ghép lại nhánh201. Đây là nền đã kiểm, không phải SHA của chính bản cập nhật M2 này.
- Workflow [v0.1 proposed](../review/WORKFLOW.md), docs506384b; dùng [M2/M3](../review/TEMPLATES.md). Assignment: mục TASK-203b trong w2_21_10.md của Duy, bản workspace W2_ASSIGNMENT_20261026.md; link assignment chung còn TBD, không tạo M1 cạnh tranh.
- Hạn W2 chuyển tiếp **tối03/11/2026** theo [xác nhận của Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29#issuecomment-6499240459). Checkpoint04/11 đã qua hạn; bản gốc đã công bố/nghiệm thu, bản sửa review còn kiểm lại UI thật/công bố/CI/review/merge. ETA review/merge mới chưa chốt. Không tự gia hạn hoặc dùng việc đủ đầu vào để cam kết ngày hoàn tất.

## Hành vi và phạm vi

Khi một lần nạp file/text trả incomplete422 có danh sách lỗi, hiển thị dialog lỗi toàn đề/theo câu và hướng sửa đầu vào. Cho chọn file đã sửa, kể cả cùng file, hoặc chuyển Nhập trực tiếp. Người dùng chủ động bấm Nạp nguồn sau khi sửa; mở/đóng dialog, chọn file, đổi mode không tự POST.

Nguồn A đã lưu và input B bị lỗi là hai phần riêng. B422 không thay preview/count của A; không xóa input B khi đóng dialog. Đổi session/account/logout/rời trang phải bỏ dialog/lỗi và phản hồi cũ theo cơ chế201. Timeout/cancel/kết quả chưa rõ tiếp tục dùng cảnh báo và khóa của201; GET không chứng minh POST trước đã dừng hoặc rollback.

Ngoài scope: viết lại service/controller/upload/progress201, editor cho câu đã trích xuất, autosave/backup/restore DB từ FE, parser/schema/Storage/AI, confirm/readiness204, Stage2/SSE/export hoặc đổi stack/UI. Source vẫn chỉ đọc, Blueprint ẩn. Nội dung mẫu là Đại số không cần hình; không coi bộ mẫu là coverage đã đạt.

## Xử lý review F01–F04

| ID | Thay đổi và bằng chứng author | Trạng thái bàn giao |
|---|---|---|
| F01 | `IncompleteContentDialog` mở bằng `showModal()`, đóng bằng `close()` để trình duyệt cô lập nền. Cleanup khi đóng/unmount; nativecancel/Đóng/Escape không gọi trùng callback. Đóng modal trước callback mở picker/chuyểntext, giữ user gesture. Lifecycle/integration tests và native Chrome fixture kiểm riêng. | Đã sửa và tự kiểm local; chưa reviewer verified. Native API stub trong tests không giả lập inert hoặc thay bằng chứng browser. |
| F02 | M2 và2README có checkpoint bản công bố/Ready/CI1fc501c, bản sửa và review riêng; phần trước công bố được đánh nhãn lịch sử. | Đã cập nhật local; không tự chuyển author reported thành reviewer Approve. |
| F03 | Hướng sửa `MISSING_ANSWER` yêu cầu xác định **đáp án đúng (A/B/C/D)** hoặc bổ sung đáp án tương ứng vào bảng cuối đề; tests kiểm ý nghĩa này. | Đã sửa local; không thay contract/parser. |
| F04 | Native picker đã có bằng chứng Chrome trên Windows; Safari/iOS chưa kiểm. Browsermatrix sản phẩm chưa được chốt từ lượt này. | Ghi nhận giới hạn, không suy Safari có bug hoặc sản phẩm chỉ hỗ trợ Chrome. |

Khi công bố bản sửa, cập nhật M3/CI đúng head mới và phản hồi cùng F-ID/comment. Author chỉ báo claimed_fixed; Duy kiểm lại trước Approve. Không tự resolve review hoặc nhận task đã merge/Done. Hạn03/11 đã qua, không tự gia hạn.

## Đầu vào đã có

- [PR29/TASK-201](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29) đã merge dev; [service](../../frontend/src/services/ingestion.js), [controller](../../frontend/src/features/stage1-ingestion/sourceIngestion.js) và [panel](../../frontend/src/features/stage1-ingestion/Stage1SourcePanel.jsx) đã có trên nhánh này. Controller giữ raw `cause`, tách input/nguồn, khóa pending và bỏ response/progress cũ; picker đã reset để chọn lại cùng file. Dùng nguyên client/Auth/store và các guard đó.
- [Ingestion contract](../api/ingestion-endpoints.md), [schemas.py](../../backend/app/models/schemas.py), [validator.py](../../backend/app/services/parser/validator.py) là nguồn chuẩn. Lỗi ingestion có dạng `{detail:{message,errors:[{question_no,error_type,message}]}}` trong `cause.response.data`; cần đồng thời kiểm HTTP422. FastAPI422/detail array, confirm422/detail string,400/409/429/network/timeout không phải cùng loại lỗi.
- `question_no=0` biểu thị lỗi toàn đề; số nguyên dương hiển thị CâuN. Số/vị trí không hợp lệ dùng nhãn dự phòng, không hiển thị Câu0 hoặc tự đoán câu liên quan. Unknown error_type vẫn có thông báo/hướng sửa chung. Payload rỗng hoặc sai shape không gây crash hay mở dialog rỗng, giữ thông báo lỗi chung.
-10mã hiện hành: `MISSING_ANSWER`, `UNPARSED_OMML`, `UNPARSED_IMAGE`, `AMBIGUOUS_FORMAT`, `EMPTY_STEM`, `CONFLICTING_ANSWER_KEY`, `SURPLUS_ANSWER_KEY`, `DUPLICATE_QUESTION_NO`, `INVALID_QUESTION_NO`, `INVALID_FORMAT`. Hướng sửa bám mã: bổ sung/chốt key, sửa cấu trúc/câu/số thứ tự hoặc chuyển công thức sang text/LaTeX phù hợp. Với ảnh/hình bắt buộc, báo giới hạn đầu vào; không hứa tự chuyển ảnh/OCR hoặc bỏ qua lỗi để nạp. Message chỉ render như text, không HTML.
- [Nghiệm thu201](TASK-201.md): user kiểm B thiếu key bị lỗi và giữ fileB; log POSTfile422, agent GET/F5 xác nhận A vẫn2câu/keyC,A. Đây là bằng chứng từng phần cho giữ nguồn, chưa phải dialog203b, mọi mã lỗi hoặc Storage audit. Không hỏi lại như chưa có bằng chứng nào.
- Gate toàn W1 đã đạt: [PR19](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/19) và [PR20](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/20) của Tâm/AI-WFox đã merge31/10. Phụ thuộc201 đã nhập qua dev; không còn hai blocker này.

## File và thứ tự triển khai P1–P4

Các file203b nằm trong `frontend/src/features/stage1-ingestion/`. Bảng dưới ghi các vòng ban đầu trước review, đã công bố ở1fc501c. Trạng thái bản sửa sau review nằm ở checkpoint và bảng F01–F04 bên trên.

| Lượt / file | Mục đích và output | Đầu vào đủ dùng | Kiểm trước bàn giao |
|---|---|---|---|
|P1 — stage1Errors.js và stage1Errors.test.js, local|Hàm thuần đọc rawcause, nhận dạng incomplete và tạo nhãn lỗi/hướng sửa, giữ unknown fallback|Contract/schema/validator hiện hành; không gọi API|9tests/lint đạt: phân loại, vị trí,10mã/unknown/malformed, giữ input và text an toàn|
|P2 — IncompleteContentDialog.jsx và tests, local|Danh sách lỗi, close/Escape/Tab/focus và hai hành động file/text, theo UI hiện có|Error model P1 và props bên dưới|7tests/lint đạt: đóng/focus/callback/markup và danh sách dài; native kiểm thêm ở P4|
|P3 — Stage1SourcePanel.jsx và tests, local|Ghép cause/dialog/picker/focus, không đổi controller/service201|Code201 và P1/P2 đã đạt|7integration mới;72ca liên quan đạt, gồm gửi lại cùng error object, không tự POST, lỗi GET/timeout/route/logout|
|P4 — README/M2/M3 và evidence trước review|Kiểm hồi quy/UI/API, bàn giao đúng bản và giới hạn|P1–P3 đã đạt, frontendDocker Healthy|308tests/lint/build; userPASS L01–L04b. Đã công bố1fc501c/Ready/CI5xanh; còn F01/F02 từ review sau đó|

## Interface và hành vi ghép đã chốt cho plan

- P1: `readIncompleteError(cause)` trả `null` khi không có incomplete envelope đủ dùng; với lỗi hợp lệ trả `{message,errors}`, item gồm `location/title/detail/guidance` là string. Không sửa rawcause/source/input/state hoặc gọi mạng/DOM. Unknown code có fallback; danh sách trộn malformed giữ fallback từng item, tất cả item không hữu ích thì dùng thông báo chung. Giữ thứ tự và nhiều lỗi cùng câu, không tự gộp/xóa.
- P2: props `open`, `errors`, `onClose`, `onChooseFile`, `onSwitchToText`. Component không tự ingest, GET, sửa nguồn hoặc mở khóa uncertain. Giữ bố cục hiện có, dùng native `dialog.showModal()/close()` để cô lập nền; nativecancel và các hành động đóng đi qua cùng đường callback có guard. Không tạo thư viện dialog hoặc sửa modal Dashboard. Helper `test-support/dialog.stub.js` chỉ theo dõi lifecycleAPI trong Node tests, không giả lập nativeinert.
- P3: panel tạo model từ cause bằng useMemo, chỉ mở khi `controller.canSubmit()` và cause chưa được đóng. Một `dismissedCause` ghi lỗi đã đóng; reset trước submit được phép để cùng error object ở lần nạp mới vẫn mở được. Controller201 không đổi. Không mở lại từ rerender/mode change hoặc lỗi GET có requiresReload; không lưu dialog vào localStorage hay thêm request state.
- `onChooseFile`: gọi native`close()` trước callback để input nền hết inert, giữ source/text/file cho tới khi chọn mới, setModefile và gọi một picker luôn mounted ngay trong click của user; filepanel bị ẩn ở mode text. Không dùng timer/retry để mở picker hoặc tự upload. `onSwitchToText`: close trước callback, setMode hiện có và focus textarea sau mount, giữ text chưa gửi. Pending focus vẫn chỉ dùng ref/effect ở panel. ChromeWindows là môi trường native đã kiểm; Safari/iOS chưa kiểm, không tự cam kết browsermatrix.
- `onClose`: chỉ đóng dialog, không xóa source/input/cause hoặc tự POST. Focus về control đã mở nếu còn hợp lệ; hành động đổi mode focus input đích. Khi account/route đã rời hoặc control disabled/unmount, không cố focus DOM cũ. Có nhãn dialog, aria-modal, Tab/Shift+Tab trong dialog, Escape và focus return.
- Giữ guard201: submit bắt đầu thì lỗi cũ không tiếp tục mở; đổi session/account/logout/unmount bỏ dialog, response/progress cũ bị bỏ. Không đổi timeout15s/401-refresh chung, không phân loại timeout/5xx/invalid200 thành lỗi có thể gửi lại an toàn.

Đây là interface nội bộ FE để triển khai; không thay contract API/schema và không cần owner backend quyết định thêm trước P1. Có thể điều chỉnh chi tiết cài đặt khi code nếu giữ các hành vi và cập nhật plan tương ứng.

## Câu hỏi và phụ thuộc — trạng thái04/11

| ID / người liên quan | Kết luận đủ để bắt đầu | Phần còn lại |
|---|---|---|
|203b-Q01 — Trung Anh/TASK201|Resolved:201 đã merge;203b đã công bố1fc501c/Ready/CI5xanh|Còn công bố bản sửa review và CI/reviewer xác minh đúng head mới trước merge|
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

## Lịch sử tự kiểm trước khi công bố1fc501c

Các ghi nhận bên dưới phản ánh thời điểm trước push/Ready và trước review F01–F04, không phải trạng thái hiện hành. Bằng chứng baseline308 và user L01–L04b không thay kiểm lại phần modal sau sửa; xem checkpoint hiện hành ở đầu file.

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

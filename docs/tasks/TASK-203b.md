# TASK-203b — Stage 1 Incomplete Loop — M2

- Status: Draft — plan/input, chưa code sản phẩm.
- Author: Trung Anh / philip-kkk / TV1 / FE1; BE1 Duy phối hợp contract ingestion.
- Reviewer user chọn: Duy review chính; Bội Anh kiểm điểm nối frontend khi liên quan. Chưa có xác nhận nhận việc/ETA; dự phòng TBD.
- Assignment: W2 do Duy giao, bản workspace project/W2_ASSIGNMENT_20261026.md / w2_21_10.md, mục TASK-203b; link chung do leader quản lý TBD. Không tạo M1 thay leader.
- Workflow: [v0.1 proposed](../review/WORKFLOW.md), docs commit506384b; [M2/M3](../review/TEMPLATES.md).
- Nhánh: feat/task-203b-incomplete-loop, Draft vào dev từ nền813f497. Chỉ thêm plan riêng; [PR29](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/29) giữ tham chiếu plan tổng Stage1. Theo yêu cầu user, phần triển khai203b dự kiến quản lý ở PR riêng này, cần đồng bộ phạm vi khi cập nhật PR29.
- Hạn nguồn:21–31/10/2026; hạn chuyển tiếp, ETA input/task/review TBD. Không tự đổi thành03/11.

## Mình cần làm gì?

- Nhận lỗi incomplete từ ingest-text/ingest-file, hiển thị danh sách lỗi và hướng sửa file/văn bản nguồn bằng hộp thoại phù hợp UI đã bàn giao.
- Cho chọn file khác hoặc chuyển tab Nhập trực tiếp; chỉ gửi lại khi user xác nhận thao tác. Chọn lại cùng file vẫn hoạt động.
- Không sửa trực tiếp câu/options/key đã parse, không thêm editor/autosave. Giữ source read-only và Blueprint ẩn.
- Khi nạp nguồn A thành công rồi B bị422, A vẫn là nguồn đã lưu; input B và lỗi hiển thị riêng. Không tự ghi/restore DB hoặc coi B đã thay A.
- Không lấy lỗi/câu của session hoặc tài khoản trước; bỏ phản hồi cũ khi đổi ID/account/rời trang, dùng cơ chế hiện có của TASK201 và API client chung.
- Ngoài phạm vi: sửa parser/transaction/schema/Storage; upload/progress của201; preview/confirm/security/readiness của204; AI/Stage2/SSE/export; đổi stack hoặc thiết kế UI.
- Nội dung mẫu: Đại số không cần hình, ví dụ phương trình3x-5=10 với A:x=3/B:x=4/C:x=5/D:x=6, keyC. Thiếu key hoặc option là fixture lỗi đề xuất, chưa chạy parser.

## Hiện đã có / contract đã đọc

- [Ingestion contract](../api/ingestion-endpoints.md) từ PR15 đã merge; [schemas.py](../../backend/app/models/schemas.py) và [validator.py](../../backend/app/services/parser/validator.py) là đầu vào đối chiếu. Chưa kiểm API/cloud thật trong lượt plan.
- Incomplete422 thực tế: `{detail:{message,errors:[{question_no,error_type,message}]}}`. Phân biệt FastAPI422 có detail array, confirm422 có detail string và400/409/429/network/timeout. Không nhận mọi422 là incomplete.
- question_no0 biểu thị lỗi toàn đề theo validator; không hiển thị Câu0. Hiển thị an toàn message như text, không chèn HTML.
- 10mã hiện có: MISSING_ANSWER, UNPARSED_OMML, UNPARSED_IMAGE, AMBIGUOUS_FORMAT, EMPTY_STEM, CONFLICTING_ANSWER_KEY, SURPLUS_ANSWER_KEY, DUPLICATE_QUESTION_NO, INVALID_QUESTION_NO, INVALID_FORMAT. Mã mới/không biết có thông báo chung và hướng sửa đầu vào; không làm crash hoặc âm thầm bỏ lỗi.
- [Stage1 entry](../../frontend/src/features/stage1-ingestion/README.md) và [API client](../../frontend/src/services/api.js) đã có. TASK201 text/file/controller chưa có ở nền đã đọc; không coi DraftPR29 là input implementation đã giao.
- Backend chịu trách nhiệm422 không mutation. FE giữ nguồn được GET xác nhận; timeout/mất phản hồi không chắc kết quả khác với422, cần kiểm lại trạng thái trước thao tác ghi tiếp, không tự retry POST.

## File và thứ tự triển khai khi được mở khóa code

Tên/props sau là đề xuất FE, chốt với TASK201 trước ghép; không tạo contract API cạnh tranh.

|File / thứ tự|Mục đích|Output|Input cần|Cách kiểm|
|---|---|---|---|---|
|docs/tasks/TASK-203b.md|Plan riêng và bàn giao|Draft trước code, liên kết rõPR29|User đã giao tạo Draft|Markdown/link/diff|
|frontend/src/features/stage1-ingestion/stage1Errors.js và test|Phân loại incomplete, ánh xạ nhãn/hướng sửa|Mô hình lỗi toàn đề/câu, unknown fallback|HTTP envelope và10mã parser|Bảng ca hợp lệ/malformed/non-incomplete; không test chỉ lặp implementation|
|IncompleteContentDialog.jsx và test trong cùng feature|Hiện lỗi, close/Escape, file khác/nhập trực tiếp|Dialog dùng UI hiện có, focus hợp lý và nội dung dễ hiểu|Props open/errors/onClose/onSelectOtherFile/onSwitchToText do201/203b chốt|Keyboard/focus, danh sách dài, plain text, không POST từ dialog|
|Hook/page Stage1 do TASK201 cung cấp|Ghép lỗi/callback, reset đúng phiên, giữ nguồn A|Retry do user, lỗi B không thay A, đổi tab không gửi|Service/controller/input file-text từ201; cơ chế account/ID/cancel hiện có|A→B422→A còn→sửa đầu vào→gửi lại; stale/account/navigation|
|Stage1 README và M3|Ghi bàn giao/checks/giới hạn đúng head|Reviewer tái kiểm được, tách fixture/API thật|Các phần thực sự đã đạt|Rà diff và evidence; không nhận toàn201/204 Done|

## Đầu vào và câu hỏi trên Draft Conversation

|ID / người cần trả lời|Input cụ thể|Cần trước / ETA|Làm được / còn chờ|
|---|---|---|---|
|203b-Q01 — Trung Anh/TASK201|Service/controller/input tabs, nơi bắt lỗi và reset picker; chốt props/callback, thứ tự merge vớiPR29|Trước ghép, ETA TBD|Plan/model/dialog độc lập sau gate; chưa nhân đôi service/hook201|
|203b-Q02 — Duy/BE1|JSON thực422 toàn đề/câu, các mã hiện có/unknown; xác nhận A→B422 giữ A trên runtime nào|Trước tích hợp thật, ETA TBD|Source đã đọc; fixture không thay bằng chứng API thật|
|203b-Q03 — Duy + Trung Anh|Link assignment chung, hạn chuyển tiếp/need-by, ETA input/task/review; reviewer đã chọn nhưng cần xác nhận khả năng nhận|Trước cam kết lịch, ETA TBD|Giữ hạn nguồn21–31/10; không tự gia hạn|
|203b-Q04 — Tâm/AI-WFox; Duy điều phối|PR19/20 của Tâm còn open ở danh sách GitHub khi lập Draft; toàn W1 merge dev theo gate user đã chốt|Trước code, ETA TBD|Lập Draft được; không bắt đầu code W2 chỉ vì có plan|

- Output giao TASK201: model lỗi/dialog/callback và bằng chứng regression; giao BE1 payload tái hiện đã bỏ token/nội dung mật. Mốc cần nhận/ETA giao/hoàn tất TBD, chưa là cam kết.
- Confirm/Blueprint, badge/ack an ninh và readiness Stage2 vẫn giữ câu hỏi ởPR29/TASK204. Chúng không phải lý do tự thêm policy đó vào203b.
- Tính khả thi: chưa có input201 hoặc xác nhận môi trường/ETA, gateW1 chưa đạt; chỉ đủ căn cứ lập plan, chưa cam kết ngày hoàn tất.

## Kế hoạch tự kiểm

- Phân loại đúng incomplete422; FastAPI422/confirm422/400/409/429/mất mạng không hiện sai dialog. Payload thiếu/rỗng/malformed không làm crash; giữ fallback thông báo an toàn.
- Toàn đề/câu,10mã và unknown; nhiều lỗi/câu, nội dung dài, công thức và chuỗi có markup hiển thị an toàn.
- UI/browser: close/Escape/Tab/focus return, file khác/cùng file, chuyển text giữ input hợp lý; mở/đóng dialog/đổi tab không POST. Số lần gửi phụ thuộc thao tác user rõ ràng.
- A hợp lệ→B422→GET vẫn A→sửa input→gửi thành công; đổi ID/account/logout/rời trang không lộ hoặc dùng lại lỗi cũ. Kiểm fixture và API thật ghi riêng.
- Lượt plan chỉ kiểm Markdown, liên kết và diff. Sau code chạy suite liên quan, npm.cmd run lint và npm.cmd run build từ frontend; CI áp dụng và1GitHubApprove từ người khác trước merge theo CONTRIBUTING.

## Bàn giao thực tế

- Lượt này chỉ đọc assignment/code/contract và lập M2/M3, chưa tạo source/test/fixture, chưa kiểm UI/API/cloud hoặc nghiệm thu203b.
- Draft riêng theo user giao; commit/head/PR URL được ghi trên PR và checkpoint sau tạo, không ghi SHA của chính file vào file.
- Bước tiếp: hỏi input/ETA trên Conversation theo quyền gửi riêng, cập nhật kết luận vào plan/contract owner. Chỉ code khi gateW1/đầu vào/phân công đủ; chưa Ready hoặc request review code đã hoàn tất.

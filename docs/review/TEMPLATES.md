# Mẫu giao việc, plan và review

Đi cùng [WORKFLOW v0.1 — proposed](WORKFLOW.md). Bản mẫu giữ nguyên; sao chép phần cần dùng vào **file tuần, file task hoặc PR** như hướng dẫn dưới đây. `<...>` là chỗ điền, không phải dữ liệu thật. Bỏ hoặc ghi không áp dụng cho trường không phù hợp; không tick/bịa kết quả để đủ mẫu.

| Mẫu | Người điền | Đọc trước | Bản điền nằm ở đâu? |
|---|---|---|---|
| [M1](#m1) | Duy — leader | WORKFLOW, kết quả tuần trước, scope và khả năng/ước lượng của người nhận | Một file giao việc tuần do leader quản lý |
| [M2](#m2) | Thành viên nhận task và agent | Rules, M1 đúng bản, code/contract liên quan | Một file plan task trên nhánh task |
| [M3](#m3) | Author và agent | M2, diff/head, contract và checks thực tế | PR description hoặc một comment tổng hợp được link từ body |
| [M4](#m4) | Reviewer và agent | Rules, PR/head, plan trên nhánh PR, M3/code/tests và review cũ | Review thread; vấn đề xuyên file dùng comment tổng hợp có link |
| [M5](#m5) | Author trả lời, reviewer xác minh | Finding, bản code/commit sửa và bằng chứng | Reply trong cùng thread/ID |

<a id="m1"></a>

## M1. Leader giao việc theo tuần

Duy chuẩn bị thứ 4, phát trong thứ 4 hoặc sáng thứ 5. Ví dụ nơi điền: `docs/tasks/W<NN>_ASSIGNMENT.md`; nếu nhóm đã có một đường dẫn chung thì dùng đường dẫn đó. Không tạo bản phân công song song.

```markdown
# Phân công tuần <NN> — <ngày bắt đầu> đến <ngày hạn>

- Leader: Duy.
- Phiên bản/cập nhật: <bản hoặc commit; ngày cập nhật>.
- Mục tiêu tuần và nguồn yêu cầu: <...>.
- Hạn chung: tối thứ 3 <ngày của tuần sau>; không tự thêm giờ.
- Thứ 5: thành viên/agent đọc, lập plan, tạo Draft PR và giải đáp.
- Từ thứ 6: bắt đầu code theo phần đã làm rõ.
- Nguồn tiến độ chính: <tracker/kênh nhóm đang dùng>.

## Task và thứ tự thực hiện

| Thứ tự / nhóm song song | Task / mục tiêu | Phụ trách / dự phòng | Input cần từ task/người nào | Output giao cho task nào | ETA xong task | Tiêu chí đạt / ngoài phạm vi | Reviewer đã chốt hoặc đề xuất |
|---|---|---|---|---|---|---|---|
| <1, 2 hoặc cùng nhóm> | <ID, hành vi> | <tên hoặc TBD> | <ID/người, input cụ thể> | <output + ID/người nhận> | <ước lượng + người xác nhận, kể cả task độc lập> | <đạt khi...; không làm...> | <tên + trạng thái> |

## Mốc giao-nhận đầu vào và ước lượng

| Quan hệ | Input/điều kiện đủ dùng | Người giao → người nhận | Bên nhận cần trước | ETA giao input | ETA xong task cung cấp | Thời gian phần sau: code/tích hợp/review/sửa | Người xác nhận / cập nhật |
|---|---|---|---|---|---|---|---|
| <B → A> | <contract/JSON/fixture/code đã merge...> | <...> | <ngày/buổi> | <ước lượng hoặc TBD> | <ước lượng riêng> | <ước lượng từng phần hoặc tổng có cơ sở> | <tên, thời điểm> |

## Điều cần làm rõ trong thứ 5

- <Câu hỏi cụ thể → người cần trả lời → task bị ảnh hưởng>.
- <Vòng phụ thuộc/ETA muộn/quá tải → đề xuất điều chỉnh → người quyết định>.
- Link Draft PR/plan của từng task: <điền khi có>.
```

**Cách xếp:** nếu A cần B, đặt phần cung cấp input của B trước A; task độc lập cùng nhóm song song. Tính ngược từ tối thứ 3 để A còn thời gian code/tích hợp/kiểm/sửa. So ETA giao với mốc cần nhận; nếu muộn thì điều phối lại trước khi nhận lịch khả thi. Input đủ dùng có thể được giao trước khi xong toàn B, nhưng contract/mock không thay code thật nếu A cần tích hợp. Không buộc leader liệt kê mọi file code hoặc biến ETA chưa xác nhận thành cam kết.

<a id="m2"></a>

## M2. Plan và bàn giao của thành viên

Trong thứ 5, agent đọc đúng task/code rồi nháp; owner kiểm và lưu theo quyền. Ví dụ nơi điền: `docs/tasks/TASK-<ID>.md` trên nhánh task. Draft PR chứa commit plan, link file tuần và file task; reviewer phải đọc bản trong PR, không chỉ dev.

```markdown
# TASK-<ID> — Plan và bàn giao

- Nguồn giao việc: <link file tuần + phiên bản/commit>.
- Phụ trách: <...>; reviewer: <đã chốt / đề xuất / TBD>.
- Repo/nhánh: <...>; PR: <điền link khi tạo>.
- Hạn đợt: tối thứ 3 <ngày>; ETA task: <ước lượng, người xác nhận>.

## Mình cần làm gì?

- Hành vi/tiêu chí đạt: <...>.
- Ngoài phạm vi: <...>.
- Hiện đã có: <file/commit và bằng chứng; phân biệt đã kiểm/chỉ được báo>.

## File và thứ tự triển khai từ thứ 6

| Lượt / file dự kiến | Mục đích sửa | Output mong muốn | Cần input gì trước | Cách kiểm |
|---|---|---|---|---|
| <...> | <...> | <...> | <task/contract hoặc không có> | <...> |

## Đầu vào và câu hỏi — giải đáp trên Draft PR trong thứ 5

| Cần ai/task nào | Câu hỏi/input cụ thể | Cần trước | ETA bên cung cấp xác nhận | Phần làm ngay/chờ | Link trả lời/contract |
|---|---|---|---|---|---|
| <...> | <xin một JSON thành công và một JSON lỗi...> | <...> | <...> | <...> | <...> |

- Output mình cần giao cho task sau: <cho ai, dạng gì, ETA đã xác nhận>.
- Lịch có khả thi không? <input trễ/vòng phụ thuộc/quá tải; đề nghị Duy điều phối>.
- Quyết định đã thống nhất: <kết luận + link; không tự đoán contract>.

## Kế hoạch tự kiểm

- <Tình huống thành công, lỗi và thao tác liên quan cần thử>.
- <Môi trường; mock/fixture/API thật; phần chưa thể kiểm>.

## Bàn giao — điền theo kết quả thực tế

- PR/commit/output: <link và người nhận>.
- Đã làm / đã kiểm: <bằng chứng và giới hạn>.
- Đã chấp nhận: <review/nghiệm thu thực tế, hoặc chưa có>.
- Còn chờ/bước tiếp: <...>.
```

File task giữ plan/quyết định/bàn giao, không thay tracker hoặc chép mọi finding. Không commit SHA của chính file vào file để tạo vòng cập nhật. Không mở lại nhánh đã merge chỉ để ghi Done; bổ sung kết quả cuối trên PR/tracker khi phù hợp.

<a id="m3"></a>

## M3. Gói yêu cầu review

Trong Draft thứ 5, dùng phần scope/plan/input để hỏi và ghi chưa có code/checks nếu đúng. Khi Ready hoặc yêu cầu kiểm lại sau push, cập nhật đúng head và kết quả. [PR template](../../.github/pull_request_template.md) đã có các mục để điền; không cần dán thêm một body trùng toàn bộ.

```markdown
- Task / file tuần / plan: <link đúng bản>.
- Workflow: v0.1, docs commit <nếu biết; không nhầm với code head>.
- Base/head cần review: <SHA>/<SHA sau push>.
- Scope/tiêu chí đạt; ngoài phạm vi: <...>.
- Contract/phụ thuộc: <link phiên bản; đã sẵn hay pending>.
- Input cần/ETA: <link file tuần, câu hỏi và người cần trả lời>.
- Checks thực tế: <lệnh hoặc thao tác; môi trường; head; kết quả>.
- Phần chưa kiểm: <mock/API thật/browser/cloud...; lý do>.
- Reviewer/phạm vi kiểm và quyền được giao: <...>.
- Findings còn mở / link thread: <ID và link, hoặc chưa có review>.
```

<a id="m4"></a>

## M4. Finding và review

Giữ ID ổn định trong PR. Reviewer chỉ nhận đã chạy kiểm khi có kết quả; đọc tĩnh thì ghi rõ mức bằng chứng. Kết luận Approve/Request changes/Comment của agent là đề xuất cho đến khi được submit theo quyền.

```markdown
Praise:
- <Điểm tốt có bằng chứng; bỏ nếu không có>.

Question:
- <Điều còn cần làm rõ; không giấu bug đã biết dưới câu hỏi>.

Suggestion:
- **F01 — [Bắt buộc sửa / Không chặn merge] <tên vấn đề>**
  - Head/vị trí: <SHA; file:dòng hoặc hàm>.
  - Loại: <lỗi mới / lỗi cũ còn tồn tại / hồi quy>.
  - Cách tái hiện/điều kiện: <dữ liệu, thao tác/lệnh>.
  - Mong đợi / thực tế: <...> / <...>.
  - Tác động và căn cứ scope: <...>.
  - Tiêu chí sửa đạt: <hành vi kiểm được; không ép cách cài đặt vô cớ>.
  - Bằng chứng/giới hạn: <output/link hoặc chỉ đọc tĩnh/chưa chạy>.
  - Trạng thái: open.
```

Mỗi finding ở thread phù hợp, review tổng hợp dẫn link khi cần. Nếu contract chưa thống nhất hoặc ca chưa tái hiện được, dùng disputed/inconclusive và nêu input còn thiếu; không coi thiếu quyền chạy là tests đã pass. Không bắt nội dung đủ cả ba phần khi không áp dụng.

<a id="m5"></a>

## M5. Phản hồi sửa và xác minh

Author trả ở cùng thread; reviewer trả ngay bên dưới sau kiểm, không tạo file/PR mới cho mỗi vòng.

```markdown
F01 — Author: claimed_fixed
- Commit sửa: <SHA>.
- Đã sửa nguyên nhân/phạm vi: <...>.
- Đã kiểm: <ca cũ; test hồi quy khi phù hợp; lệnh/thao tác, môi trường, kết quả>.
- Chưa kiểm/giới hạn: <...>.

F01 — Reviewer: <verified / open / disputed / inconclusive>
- Head đã kiểm: <SHA>.
- Kiểm lại ca cũ + diff/vùng ảnh hưởng: <cách kiểm và kết quả thật>.
- Kết luận/cần tiếp: <đạt; còn tái hiện; hoặc thiếu gì/người cần quyết định>.
```

## Ví dụ xuyên suốt — hoàn toàn giả định

Không phải phân công thật, finding thật hoặc kết quả test đã chạy. Các mốc dưới đây chỉ minh họa cách ước lượng; Duy/người phụ trách phải xác nhận khi giao việc thật.

| Task | Thứ tự / input-output | Mốc minh họa |
|---|---|---|
| B — API upload | Nhóm 1, giao contract/JSON cho A; API thật bàn giao riêng | Thứ 5 chốt contract; dự kiến thứ 6 giao API kiểm được, toàn B có thể xong sau |
| A — UI upload | Nhóm 2 theo input của B; phần UI độc lập làm song song từ thứ 6 | Cần API kiểm được trước khi tích hợp thứ 7; chừa thời gian review/sửa trước tối thứ 3 |

1. Duy dùng M1 ghi `B → A`, người giao/nhận, ETA riêng và thời gian A cần. Nếu B chỉ có thể giao API thứ 3 thì phải điều phối, không coi lịch trên vẫn khả thi.
2. Thứ 5 A/agent dùng M2 và mở Draft: “Upload thành công trả session ID ở trường nào? Nhờ owner B cho một JSON thành công và một JSON lỗi; API thật có kịp trước phần tích hợp thứ 7 không?”
3. B trả lời trong Conversation, link contract chuẩn và xác nhận/điều chỉnh ETA; A cập nhật plan. Từ thứ 6 A code theo contract, phần thử với fixture ghi mock, chờ API thật để kiểm tích hợp.
4. A push code rồi điền M3: `<head cần review>`, scope, checks thực tế và phần chưa kiểm. Reviewer đọc đúng plan/head.
5. Nếu reviewer phát hiện nhấn Gửi hai lần tạo hai request, ghi F01 theo M4 với thao tác tái hiện và mong đợi một request; không chỉ nói “xử lý loading”.
6. Sau khi sửa, A trả M5 với `<commit sửa>` và kết quả kiểm thực tế; reviewer thử lại ca cũ/các đường liên quan rồi mới ghi verified. Nếu chưa kiểm được, ghi inconclusive; verified F01 chưa là Approve cả PR.

## Prompt khởi động ngắn

Author trong thứ 5:

```text
Đọc AGENTS.md, CONTRIBUTING.md, WORKFLOW và M2 trong docs/review/TEMPLATES.md.
Task của mình là <ID> theo <file tuần + phiên bản>. Đọc code/contract liên quan,
lập plan file/input/output/cách kiểm và đối chiếu thứ tự, mốc cần input, ETA.
Lưu plan và tạo Draft PR trong thứ 5 theo quyền mình đã giao, hỏi rõ trên PR
để thứ 6 code. Ghi blocker còn lại; chưa tự code phần thiếu input hoặc nhắn
đồng đội ngoài quyền đã được giao. Nếu thiếu quyền thao tác, soạn nội dung để mình dùng.
```

Reviewer:

```text
Đọc AGENTS.md, CONTRIBUTING.md, WORKFLOW, M4/M5 và <PR, head cần review>.
Đọc plan trên nhánh PR, gói review, contract/code/tests và các finding trước.
Kiểm độc lập trong phạm vi/quyền đã giao, ghi ca tái hiện và giới hạn thật.
Không tự sửa nhánh author khi chỉ được giao review; soạn hoặc đăng kết quả
theo quyền. Phân biệt claimed_fixed, verified và GitHub Approve.
```

## What
<Task ID + hành vi/đầu ra, 1–2 câu. Ghi rõ plan-only nếu chưa code.>

- Status: <Draft — plan/input / Draft — coding / Ready for review>.
- Task / assignment / plan: <link đúng file và phiên bản; không cần tạo Issue>.
- Workflow: <version; docs commit nếu biết>.
- Base/head cần review: <SHA>/<SHA sau push; cập nhật khi request review lại>.

## Why
<Vấn đề, mục tiêu hoặc link use case/quyết định. Chỉ ghi Closes #... khi có Issue thật.>

## Acceptance / Scope

- [ ] <Hành vi hoặc đầu ra cần đạt, kiểm được>.
- Ngoài phạm vi: <...>.

## Handoff / Dependencies

- Thứ tự/task phụ thuộc: <link file phân công tuần — nguồn lịch chuẩn>.
- Input: <ID + link nơi tổng hợp duy nhất trong M2/comment; người cung cấp → nhận/task; mức đủ dùng cho phạm vi PR; không áp dụng nếu độc lập>.
- Phần input còn thiếu: <ID; thiếu gì; mốc cần nhận theo file tuần; ETA + người/ngày xác nhận hoặc TBD; không chép lại bảng M2>.
- Output giao cho task sau: <cho ai, dạng gì, mốc theo file tuần>.
- Contract / PR liên quan: <link đúng bản; đã sẵn hoặc pending>.
- File chung ảnh hưởng / reviewer: <người đã chốt hoặc mới đề xuất>.

## Status / Questions

<Câu hỏi scope/API/ETA trong Draft thứ 5: ID + link yêu cầu gốc và người cần trả lời.
Reply theo đúng ID bằng mẫu M2; giữ nơi tổng hợp đã chọn. Khi Ready, dẫn xác nhận
của consumer đủ dùng cho bước nào và phần còn chờ; Delivered chưa tự là Accepted/Integrated.>

- Finding còn mở: <ID + link thread, hoặc chưa có review>.

## How tested
- [ ] automated checks: <lệnh, môi trường, head và kết quả thực tế>.
- [ ] manual check: <bước thử, môi trường, kết quả; mock/fixture hay API thật>.
- Chưa kiểm / không áp dụng: <phần nào, lý do; không tick nếu chưa chạy>.

Plan-only/docs: nêu kiểm tài liệu thực tế; chưa có code không đồng nghĩa code checks pass.
CI trước merge vẫn theo CONTRIBUTING. Gói review M3 nằm trong TEMPLATES bên dưới.

## AI use
<tool, what it produced, what you changed, how you verified — or "None">

## Checklist
- [ ] small and focused (< ~300 lines; nếu lớn hơn, giải thích phạm vi, không tick sai)
- [ ] no secrets or personal data
- [ ] docs / README updated if needed
- [ ] contract/dependencies và file chung đã khai báo; checks/giới hạn đúng thực tế
- [ ] finding/fix/verification giữ cùng thread/ID; hoặc chưa có review

Review và mẫu: [WORKFLOW](../docs/review/WORKFLOW.md), [TEMPLATES](../docs/review/TEMPLATES.md).
Khi điền PR, thay link tương đối bằng link GitHub tới đúng nhánh/commit;
không mặc định plan chưa merge đã có trên dev.

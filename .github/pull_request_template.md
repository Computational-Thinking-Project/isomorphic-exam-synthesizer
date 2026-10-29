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
- Input cần từ ai/task nào: <đầu vào cụ thể; mốc cần nhận; ETA đã xác nhận hoặc TBD>.
- Output giao cho task sau: <cho ai, dạng gì, mốc theo file tuần>.
- Contract / PR liên quan: <link đúng bản; đã sẵn hoặc pending>.
- File chung ảnh hưởng / reviewer: <người đã chốt hoặc mới đề xuất>.

## Status / Questions

<Câu hỏi scope/API/ETA trong Draft thứ 5, ai cần trả lời; hoặc kết luận khi Ready.>

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

# Bàn giao và nghiệm thu AI W2 — Trương Thành Đạt

Cập nhật 26/10/2026. Hùng (`benalexx007`) đã APPROVE PR #18 trên `0b75d21`; PR đã merge vào `dev` tại `0307b1c`.

## Phần đã nghiệm thu

- Nguồn xác nhận → Blueprint → N=1–4 mã → candidate kèm đáp án/lời giải → validator → sinh lại giữ Blueprint.
- Gateway async dùng chung key pool, concurrency, deadline, reservation hook; lưu từng kết quả và resume qua callback.
- Gemini thật đã sinh hai câu mẫu thành công; đây là smoke module, không phải phiên giáo viên trên DB/UI.
- CI và Docker của PR #18 đạt: [CI Pipeline](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/actions/runs/40086064656), [Docker environment](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/actions/runs/40086064681).
- Bổ sung sau review: `regenerate_question(..., current_candidates=...)` loại trùng với các mã khác của cùng câu nguồn; nhận diện không phụ thuộc thứ tự options. Đã có test retry, hết budget attempts và từ chối candidate khác nguồn trước API.

## Điểm nối cần hoàn thiện cùng nhóm

Đây là checklist bàn giao, chưa gửi tin nhắn cho thành viên hoặc sửa task tracker bên ngoài.

| Người phụ trách | Việc cần nối | Điều kiện nghiệm thu |
|---|---|---|
| Duy | Ingest/parser, ownership, xác nhận nguồn bất biến, hash snapshot, scheduling và lưu Blueprint | Ingest không gọi AI; confirm lặp không nhân job; nguồn đổi bị từ chối; retry chỉ phần thiếu |
| Quỳnh | Job generate, quota DB nguyên tử theo phase, lưu callback, resume/reconcile và SSE | N chỉ nhận khi đủ Blueprint; restart giữ kết quả; counter không vượt trần; progress khớp dữ liệu commit |
| BE phần review | Truyền các candidate hiện tại cùng nguồn vào sinh lại; kiểm revision và uniqueness trong transaction trước khi thay câu | Sinh lại không trùng mã khác; conflict/failure giữ câu cũ; hai yêu cầu đồng thời không ghi đè âm thầm |
| FE | Xem/xác nhận nguồn; chờ Blueprint; chọn N; tiến độ; review và nút Sinh lại | Không nhận prompt giáo viên; ánh xạ options index A–D với correct_key; hiển thị warning chưa kiểm chứng |
| Đạt | Hỗ trợ điểm nối service, chạy acceptance cùng nhóm và lưu bằng chứng | Các dòng checklist bên dưới có kết quả thật, không dùng replay thay bằng chứng HTTP/DB/UI |

Contract gọi service và lỗi ở [ai-w2-integration.md](ai-w2-integration.md). Không tạo route giả hoặc migration dự đoán để thay implementation của BE.

## Kịch bản nghiệm thu chung

| Bước | Thao tác | Kết quả cần ghi nhận | Hiện tại |
|---|---|---|---|
| 1 | Đăng nhập; tải tài liệu có hai câu trắc nghiệm | Đề nguồn đúng text/options/key; chưa gọi Blueprint | Chờ API/UI ingest W2 |
| 2 | Thử generate trước confirm | Server từ chối; counter Gemini không tăng | Service guard đã test; HTTP chờ tích hợp |
| 3 | Xác nhận nguồn hai lần | Một snapshot và một job; không nhân request | Chờ transaction/job BE |
| 4 | Một Blueprint lỗi rồi retry | Giữ câu thành công; chỉ gọi lại câu thiếu; chưa mở N | Module đã test; DB/UI chờ tích hợp |
| 5 | Chọn N=2 sau khi đủ Blueprint | Bốn candidate, mỗi câu kèm solution; lưu/progress từng vị trí | Demo module đạt; HTTP/DB/SSE chờ tích hợp |
| 6 | Sinh lại một câu, AI trả trùng mã khác | Retry có giới hạn; thành công thay đúng vị trí, giữ Blueprint | Service test đạt; transaction/UI chờ tích hợp |
| 7 | Hết quota hoặc hết attempts khi sinh lại | Giữ câu cũ, báo lỗi; UI không tự lặp | Service test đạt; DB/UI chờ tích hợp |
| 8 | Hai request sinh lại đồng thời hoặc worker restart | Revision conflict không ghi đè; resume không gọi lại phần commit | Chờ BE lock/reconcile |
| 9 | Duyệt câu có unknown/unsupported | Hiển thị phạm vi kiểm tra; giáo viên quyết định | Report module có; UI chờ tích hợp |

Lưu session ID, commit, người chạy, thời điểm, request counter theo phase, log đã che secret và ảnh/video UI vào biên bản khi chạy thật. Không đưa key hoặc dữ liệu nhạy cảm vào Git.

## Trạng thái đóng task

Kiểm thử bổ sung ngày 26/10: backend + standalone Blueprint **307 passed, 1 live opt-in skipped**; generation pipeline **38 passed**; Ruff đạt; Mypy đạt 52 source files. Không dùng quota Gemini trong lần kiểm thử này. Demo replay dùng validator thật, không thay bằng chứng HTTP/DB/UI.

PR AI/Docker #18 đã merge. Bổ sung chống trùng sau review được kiểm thử riêng và phải đi qua PR/checks trước khi vào dev. Không dùng kết quả CI của PR #18 để chứng nhận thay đổi mới.

Luồng tích hợp W2 chưa đủ bằng chứng để đánh dấu Done: baseline mới có routes users/sessions CRUD/clone/health, chưa có endpoints xác nhận nguồn, Blueprint, generate hay review W2. Duy/Quỳnh/FE nối theo contract rồi Đạt chạy kịch bản trên. Finalize/export thuộc giai đoạn tiếp theo, không tính là đã có.

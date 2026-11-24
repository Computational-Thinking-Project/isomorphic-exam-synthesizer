# Đạt — sinh theo câu và tải tài liệu theo định dạng

Nguồn giao việc là yêu cầu trực tiếp của Đạt ngày 24/11/2026 và phản hồi Duy tại PR #109, comment 7104275075. Author Đạt, base dev efed79b. Workflow v0.1 proposed + INPUT-20261109. Reviewer dự kiến Duy và các owner tích hợp, chưa xác nhận lịch.

## Thay đổi

- Pipeline async chính xử lý câu nguồn theo thứ tự. Một request structured JSON sinh đủ các mã còn thiếu của cùng câu, tối đa bốn mã. Kết quả được ánh xạ bằng version_index và kiểm tập mã chính xác trước khi dùng.
- Validator hiện có kiểm từng candidate, chống trùng nguồn và giữa các mã. Candidate lỗi được sửa riêng bằng luồng hiện có. Một request ban đầu không bảo đảm mọi lượt chạy chỉ tốn đúng một request khi có lỗi.
- Callback lưu được await lần lượt Câu 1/Mã 1, Câu 1/Mã 2, rồi Câu 2. Lỗi persistence được truyền lên ngay. Resume giữ candidate đã commit, seed và fingerprint logic của từng ô. Clone không gọi AI.
- UI chọn PDF, LaTeX hoặc Markdown và tải từng file. API GET /api/sessions/{session_id}/export/files?format=pdf|tex|md liệt kê filename/size_bytes. Thêm filename để trả attachment tương ứng.
- API giữ xác thực/RLS và gate export hiện có, đọc lại artifact có checksum, giới hạn dung lượng giải nén, chặn tên trùng/path không hợp lệ và trả no-store. Archive nội bộ được tái sử dụng làm nguồn file đã đóng băng. UI tải file riêng.
- UI Stage 3 của Trung Anh ở PR #109 được tích hợp qua thứ tự nguồn/mã hiện có, thay đổi này nằm trên nhánh riêng.

## Phối hợp tiếp

Khôi phục ô chưa có candidate ID và quyền ghi khi partial vẫn cần API/persistence contract theo I-95-FIX-MISSING-RETRY và I-95-FIX-PARTIAL-WRITE. Thay đổi batching này chưa cung cấp endpoint mới cho hai nghiệp vụ đó. Regenerate của candidate hiện có vẫn dùng luồng một candidate.

## Kiểm chứng

Có regression cho một request/bốn mã, đảo thứ tự response, thứ tự nhiều câu, duplicate, quota và resume sau lỗi lưu. Có kiểm tra tải đúng bytes, định dạng, từ chối path và quyền owner. Visual preview dùng dữ liệu giả đã mở bằng browser, kiểm PDF và chuyển LaTeX. Live Gemini/DB/Storage chưa được nghiệm thu trên nhánh này. Kết quả lệnh cuối được ghi trong PR khi bàn giao.

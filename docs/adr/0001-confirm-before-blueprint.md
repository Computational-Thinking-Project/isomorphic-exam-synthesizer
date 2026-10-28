# ADR 0001 — Xác nhận nguồn trước khi sinh Blueprint

Ngày: 24/10/2026. Quyết định của Trương Thành Đạt cho AI W2.

Flow cũ sinh Blueprint ngay sau ingest làm tốn quota và tạo mẫu từ đề mà giáo viên chưa kiểm tra. Flow chính thức: ingest/parser → giáo viên xác nhận nguồn → Blueprint từng câu → đủ Blueprint mới chọn N → sinh candidate, đáp án, lời giải cùng request → validator → teacher review/regenerate → chốt/xuất.

BE ghi source confirmation/hash bền vững trước extraction. Retry giữ nguyên xác nhận và các Blueprint thành công; nguồn thay đổi phải xác nhận lại trong phiên mới theo W2. Schema canonical là 0.4.0 của PR #9, không sử dụng model Blueprint legacy để tạo một cấu trúc song song.

Không có prompt tự do của giáo viên. Sinh lại giữ Blueprint và chỉ nhận feedback nội bộ từ checker. Không thêm API kiểm định AI mặc định; code kiểm contract, checker chỉ kiểm toán trong phạm vi đã hỗ trợ. Unknown cần giáo viên duyệt, không tự coi là đạt chuẩn hoặc tương đương sư phạm.

Quyết định này thay các đoạn cũ trong planning/description/architecture nói đến Blueprint editor, extraction trước confirmation hoặc gọi solver riêng mặc định. Hợp đồng triển khai và giới hạn: [AI W2](../ai-w2-integration.md). Thay đổi service không tự tạo routes/DB/UI của thành viên khác.

# Phân công tuần 3 — 28/10/2026 đến 03/11/2026

- Leader: Duy.
- Phiên bản/cập nhật: v2.1; 28/10/2026.
- Mục tiêu tuần và nguồn yêu cầu: Hoàn thành trọn vẹn phần lõi Backend, AI Engine, Shuffler và Dual Export của Giai đoạn 3 (Stage 3). Tạm thời hoãn toàn bộ các task Frontend ra sau, tập trung 100% tài nguyên cho 4 thành viên (Duy, Đạt, Tâm, Hùng) xây dựng hệ thống nền tảng vững chắc. Nguồn tài liệu kỹ thuật: [w3.md](../../w3.md), [docs/planning_new.md](../planning_new.md) và [docs/architecture.md](../architecture.md).
- Hạn chung: tối thứ 3 03/11/2026; không tự thêm giờ.
- Thứ 5 (29/10): thành viên/agent đọc, lập plan, tạo Draft PR và giải đáp.
- Từ thứ 6 (30/10): bắt đầu code theo phần đã làm rõ.
- Nguồn tiến độ chính: GitHub PR threads và Project board.

## Task và thứ tự thực hiện

| Thứ tự / nhóm song song | Task / mục tiêu | Phụ trách / dự phòng | Input cần từ task/người nào | Output giao cho task nào | ETA xong task | Tiêu chí đạt / ngoài phạm vi | Reviewer đã chốt hoặc đề xuất |
|---|---|---|---|---|---|---|---|
| Nhóm 1 (song song) | TASK-301: API Thẩm định 1-1, Vòng đời is_current, Revert nguyên tử & Stale Guard | Duy / Hùng | TASK-302 (DB Schema & Model từ Hùng) | Bộ endpoints /accept, /reject, /revert, /progress | Thứ 7 31/10 (Duy xác nhận) | Đạt: 2 short transactions chống cạn pool; tự động mở khóa sau 3 phút crash; reset is_finalized nếu sửa sau shuffle; chặn trần 30 calls quota review. Ngoài phạm vi: Giữ DB connection trong lúc chờ AI; không code Frontend. | Hùng (đã chốt) |
| Nhóm 1 (song song) | TASK-302: Database Schema Migration, Canonical Invariant & Repository Layer | Hùng / Duy | Schema CSDL hiện tại từ dev | Migration SQL (cột canonical_*, is_current, Partial Unique Index, review_logs, answer_keys, gemini_review_calls) | Thứ 6 30/10 (Hùng xác nhận) | Đạt: Migration sạch, Partial Unique Index (version_id, source_question_id) WHERE is_current = TRUE hoạt động chính xác; repository layer đọc/ghi an toàn. Ngoài phạm vi: Không sửa các bảng không liên quan. | Duy (đã chốt) |
| Nhóm 1 (song song) | TASK-303: Thuật toán Hoán vị xác định (Deterministic Fisher-Yates Shuffler) & Đồng bộ Lời giải | Tâm / Duy | Dữ liệu canonical_* từ TASK-302 | Service Fisher-Yates và endpoint POST /finalize/shuffle | Chủ Nhật 01/11 (Tâm xác nhận) | Đạt: Seed cố định theo mã đề; đảo câu & đảo đáp án; đồng bộ bảng answer_keys; cập nhật chữ cái đáp án trong solution_md. Ngoài phạm vi: Không shuffle đè lên dữ liệu đã đảo (phải đọc từ canonical). | Duy (đề xuất) |
| Nhóm 1 (song song) | TASK-304: AI Targeted Regeneration Service cho nhánh Reject (On-the-fly Variant) | Đạt / Duy | Lý do từ chối từ API reject của Duy | Module sinh lại biến thể câu hỏi đạt chuẩn toán học & lời giải chi tiết mới | Thứ 7 31/10 (Đạt xác nhận) | Đạt: Gọi Gemini sinh biến thể duy nhất câu bị từ chối; chạy kiểm định toán học on-the-fly; sinh lời giải chi tiết mới ngoài DB transaction. Ngoài phạm vi: Không sinh lại cả đề thi. | Tâm (đề xuất) |
| Nhóm 2 | TASK-305: API Phê duyệt Cuối cùng, Bảng Ma trận Đáp án & Khóa Nội dung Bất biến (HTTP 423) | Duy / Tâm | TASK-301 (100% câu approved) & TASK-303 (shuffle done) | Endpoint POST /finalize/approve và GET /finalize/matrix | Thứ 2 02/11 (Duy xác nhận) | Đạt: Kiểm tra điều kiện nghiêm ngặt; cập nhật status = approved, approved_at = now(); chặn mọi thao tác sửa đổi sau đó với HTTP 423 Locked; trả ma trận đáp án đối soát. Ngoài phạm vi: Không phê duyệt khi chưa duyệt đủ câu. | Đạt (đề xuất) |
| Nhóm 2 | TASK-306: Export Engine Pipeline 1 — Biên dịch PDF In Ấn Typst Subprocess An Toàn | Tâm / Đạt | Dữ liệu phiên đề đã khóa từ TASK-305 (test mock trước từ T6) | Module typst_compiler.py xuất exam_{code}.pdf, answers_matrix.pdf, solutions_{code}.pdf | Thứ 2 02/11 (Tâm xác nhận) | Đạt: Template Typst chuẩn A4 Việt Nam; Subprocess an toàn không shell=True; timeout cứng 30s/file; kiểm tra Magic Bytes %PDF-; dọn sạch tempfile. Ngoài phạm vi: Không dùng thư viện PDF nặng khác. | Duy (đề xuất) |
| Nhóm 3 | TASK-307: Export Engine Pipeline 2 — XeLaTeX Clean Template, Markdown Bundler & ZIP Packaging | Đạt / Tâm | Files PDF từ TASK-306 của Tâm | Module bundle_builder.py đóng gói ZIP hoàn chỉnh | Thứ 3 03/11 (Đạt xác nhận) | Đạt: Jinja2 XeLaTeX UTF-8 không BOM (fontspec); file Markdown KaTeX; đóng gói ZIP cấu trúc thư mục chuẩn (pdf/, latex/, markdown/). Ngoài phạm vi: Không hardcode path máy cá nhân. | Tâm (đề xuất) |
| Nhóm 3 | TASK-308: Export Service API Idempotent, Supabase Storage Integration & Signed URL 1h | Hùng / Duy | Gói ZIP hoàn chỉnh từ TASK-307 của Đạt | Endpoint POST /export, GET /export-status và tải file | Thứ 3 03/11 (Hùng xác nhận) | Đạt: Đẩy ZIP lên Supabase Storage bucket exam-export-bundles; ký Signed URL TTL 3600s; cơ chế idempotent tái cấp URL trong 100ms nếu file đã tồn tại. Ngoài phạm vi: Không compile lại nếu file đã có. | Duy (đề xuất) |

## Mốc giao-nhận đầu vào và ước lượng

| Quan hệ | Input/điều kiện đủ dùng | Người giao → người nhận | Bên nhận cần trước | ETA giao input | ETA xong task cung cấp | Thời gian phần sau: code/tích hợp/review/sửa | Người xác nhận / cập nhật |
|---|---|---|---|---|---|---|---|
| TASK-302 → TASK-301/303 | Migration SQL và model canonical_*, is_current | Hùng → Duy + Tâm | Chiều thứ 6 30/10 | Trưa thứ 6 30/10 | Thứ 6 30/10 | Duy viết API Review; Tâm dựng Shuffler trong 1 ngày | Hùng, 28/10 |
| TASK-304 → TASK-301 | Pydantic Schema & Mock hàm regenerate_question(reason) | Đạt → Duy | Chiều thứ 6 30/10 | Trưa thứ 6 30/10 | Thứ 7 31/10 (full AI) | Duy ráp vào Short Transaction 2 của endpoint /reject trong 0.5 ngày | Đạt, 28/10 |
| TASK-301 + TASK-304 → TASK-303 | Toàn bộ câu hỏi biến thể được thẩm định đạt approved | Duy + Đạt → Tâm | Sáng Chủ Nhật 01/11 | Tối thứ 7 31/10 | Thứ 7 31/10 | Tâm chạy Fisher-Yates xáo trộn câu và đáp án trong 1 ngày | Duy, 28/10 |
| TASK-303 → TASK-305 | API POST /finalize/shuffle trả ma trận hoán vị và answer_keys | Tâm → Duy | Sáng thứ 2 02/11 | Tối Chủ Nhật 01/11 | Chủ Nhật 01/11 | Duy hoàn thiện API Phê duyệt và chốt khóa bất biến HTTP 423 trong 0.5 ngày | Tâm, 28/10 |
| TASK-305 → TASK-306/307 | Trạng thái session approved thật và dữ liệu đã khóa cứng E2E | Duy → Tâm + Đạt | Tối thứ 2 02/11 | Chiều thứ 2 02/11 | Thứ 2 02/11 | Tâm kiểm thử xuất PDF; Đạt sinh TeX/Markdown từ dữ liệu thật trong 0.5 ngày | Duy, 28/10 |
| TASK-306 → TASK-307 | Các file exam_{code}.pdf, answers_matrix.pdf, solutions_{code}.pdf | Tâm → Đạt | Sáng thứ 3 03/11 | Tối thứ 2 02/11 | Thứ 2 02/11 | Đạt đóng gói vào ZIP bundle hoàn chỉnh trong 0.5 ngày | Tâm, 28/10 |
| TASK-307 → TASK-308 | Gói file ZIP exam_bundle_{session_id}.zip hoàn chỉnh | Đạt → Hùng | Trưa thứ 3 03/11 | Sáng thứ 3 03/11 | Thứ 3 03/11 | Hùng tải lên Supabase Storage và cấp Signed URL 1h trong 0.5 ngày | Đạt, 28/10 |

## Điều cần làm rõ trong thứ 5

- Schema PostgreSQL migration cho các trường canonical_*, Partial Unique Index, review_logs, answer_keys và cột `gemini_review_calls` giữa Hùng và Duy → Duy cần Hùng chốt cấu trúc SQL trước thứ 6 → ảnh hưởng TASK-301, TASK-302.
- Interface hàm regenerate_question(reason) giữa Đạt và Duy → Duy cần Đạt xác nhận Pydantic contract (stem, options, correct_key, solution_md, validation_report) và mock function trước trưa thứ 6 → ảnh hưởng TASK-301, TASK-304.
- Cài đặt Typst CLI binary trong môi trường dev / Docker container giữa Tâm và Duy → Tâm cần xác nhận lệnh gọi typst subprocess → ảnh hưởng TASK-306.
- Quy ước đặt tên file thống nhất giữa Typst (Tâm) và ZIP Bundler (Đạt): `exam_{code}.pdf`, `answers_matrix.pdf`, `solutions_{code}.pdf` → ảnh hưởng TASK-306, TASK-307.
- Supabase Storage bucket exam-export-bundles và service role key giữa Hùng và Duy → Hùng cần Duy xác nhận quyền bucket và TTL 3600s → ảnh hưởng TASK-308.
- Vòng phụ thuộc / ETA muộn / quá tải: Nếu có nguy cơ trễ mốc, báo ngay trên Draft PR và kênh nhóm để Duy điều phối; không tự ý lùi hạn chốt tối thứ 3.
- Link Draft PR/plan của từng task:
  - `feat/duy-task-301-review-lifecycle-api`: https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/new/feat/duy-task-301-review-lifecycle-api
  - `feat/hung-task-302-canonical-schema-migration`: <sẽ điền khi tạo trong thứ 5>
  - `feat/tam-task-303-fisher-yates-shuffler`: https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/24
  - `feat/dat-task-304-targeted-regeneration`: https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/tree/feat/dat-task-304-targeted-regeneration
  - `feat/duy-task-305-approval-lock-api`: <sẽ điền khi tạo trong thứ 5>
  - `feat/tam-task-306-typst-compiler-engine`: https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/tree/feat/tam-task-306-typst-compiler-engine
  - `feat/dat-task-307-dual-export-bundler`: https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/tree/feat/dat-task-307-dual-export-bundler
  - `feat/hung-task-308-export-storage-signed-url`: <sẽ điền khi tạo trong thứ 5>

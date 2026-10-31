# TASK-307 — Plan và bàn giao: XeLaTeX, Markdown và ZIP Bundler

- Trạng thái: **Draft — bundler đã triển khai bằng fixture**, ngày 29/10/2026; Đạt yêu cầu triển khai ngay trong phiên này, chưa nghiệm thu E2E.
- Nguồn: W3_ASSIGNMENT.md v2.1 (28/10/2026) và w3.md do Đạt cung cấp ngoài repo. Chưa có đường dẫn GitHub được xác minh cho bản v2.1; chờ Duy cung cấp nguồn chung. Không lấy bản W3 cũ làm assignment mới.
- Owner: Trương Thành Đạt (`Thanhdat3010`); reviewer: Tâm (`AI-WFox`), **đề xuất**, chưa coi đã nhận review.
- Nhánh: `feat/dat-task-307-dual-export-bundler`, target `dev`; baseline `dc62d3c1d8616316771f8c1dc5a8a1ab56a2ff8c`.
- Workflow v0.1 — proposed, docs commit `506384b`; [WORKFLOW](../review/WORKFLOW.md), [TEMPLATES](../review/TEMPLATES.md).
- Hạn chung: tối thứ 3 03/11/2026. Theo assignment: nhận approved snapshot chiều 02/11, PDF tối 02/11, giao ZIP sáng 03/11 trước mốc Hùng cần trưa 03/11; ETA cần xác nhận lại trên Conversation.

## Mình cần làm gì?

- Pipeline 2: render XeLaTeX và Markdown từ snapshot phiên đã approved/khóa; nhận PDF của Tâm rồi đóng gói ZIP hoàn chỉnh cho Hùng.
- Dữ liệu phải là câu hiện hành theo display order/options/key/solution sau shuffle. Không xuất canonical chưa đảo rồi gắn key đã đảo.
- Jinja2 XeLaTeX UTF-8 không BOM, fontspec, amsmath, amssymb, geometry, enumitem; tiếng Việt và math đúng. Tách escape text khỏi math hỗ trợ, không biến nội dung đề thành mã tùy ý.
- Markdown mỗi mã đề giữ nguyên nội dung toán và mapping A–D; không gọi Gemini để định dạng export.
- ZIP root `exam_bundle_{session_id}/`, chứa pdf/, latex/, markdown/, README và hướng dẫn compile. PDF theo assignment: `exam_{code}.pdf`, `answers_matrix.pdf`, `solutions_{code}.pdf`; TeX/MD theo mã đề tương ứng.
- Kiểm tên file, không path tuyệt đối/../ hoặc collision; giới hạn dữ liệu cần được thống nhất; thiếu/hỏng PDF trả lỗi rõ, không nhận gói thiếu là hoàn tất.
- Ngoài phạm vi: Typst/compiler/PDF converter (Tâm TASK-306), shuffle (Tâm TASK-303), approval/ownership/state lock (Duy TASK-305), Storage/Signed URL/API export/idempotency (Hùng TASK-308), UI và code regeneration TASK-304.

## Hiện đã có và dependencies

- Baseline chỉ có package `backend/app/services/exporter/__init__.py`, chưa có bundler. Task này có thể phát triển TeX/MD/ZIP từ fixture sớm, không đợi PDF thật mới bắt đầu.
- [PR #24](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/24) (`5d97b9d`) chỉ có plan shuffler; cần interface display order/options/key/solution và answer_keys.
- [PR #25](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/25) (`06c261c`) chỉ có plan Typst; cần PDF artifacts và lifetime. Plan/body còn nhắc TASK-306b hoặc Export Center/UI theo bản cũ; assignment v2.1 giao Đạt bundler 307, không làm UI.
- Chưa có PR mở TASK-305/308 trong snapshot GitHub đã đọc; không suy rằng owner chưa làm. Cần chốt contract trực tiếp ở Conversation trước integration.
- Không có code bundler ở PR đang mở tại thời điểm đọc. Cùng thư mục exporter không tự là conflict Git; tránh sửa chung __init__, requirements/Docker khi chưa thống nhất ownership.

## File và thứ tự triển khai từ thứ 6

| Lượt / file dự kiến | Mục đích / output | Input cần / cách kiểm |
|---|---|---|
| 1. Snapshot/artifact interface trong contract owner thống nhất | JSON mẫu approved snapshot + filename/bytes manifest + lỗi | Duy/Hùng/Tâm chốt; không tự đoán schema DB |
| 2. `exporter/bundle_builder.py` | Render TeX/Markdown và tạo ZIP từ object/PDF thuần | Unit tests fixtures; không đọc DB hay upload cloud |
| 3. `exporter/templates/exam.tex` và template hỗ trợ cần thiết | Đề, đáp án, lời giải theo dữ liệu display | Jinja2; compile XeLaTeX thật và xem layout tiếng Việt/math |
| 4. `backend/tests/exporter/test_bundle_builder.py` | Regression encoding/escape/file names/ZIP/mapping | Test ZIP nội dung và thiếu/hỏng PDF, không dùng mock thay chứng nhận render |
| 5. requirements/lock/Docker nếu cần | Chỉ dependency còn thiếu và resources được đóng image | Chốt file chung với Tâm; import/resource test và CI Docker |
| 6. Contract owner + change_log nếu đổi contract | Hướng dẫn Hùng gọi hàm, lỗi, cleanup và metadata | Theo interface đã thống nhất, không tạo contract cạnh tranh |

## Đầu vào và câu hỏi — giải đáp trên Draft Conversation

| Người/task | Cần xác nhận | Mốc cần / ETA | Phần làm ngay hoặc chờ |
|---|---|---|---|
| Duy + Tâm / TASK-303/305 | JSON snapshot thành công/lỗi, display vs canonical, solution sau shuffle; snapshot/revision bất biến khi export | Contract trước implementation liên quan; snapshot thật chiều 02/11 theo assignment; ETA xác nhận TBD | Fixture proposal và template; chưa nhận đã nối DB |
| Tâm / TASK-306, #25 | PDF là bytes, stream hay Path? Lifetime tempfile và owner cleanup? File manifest đủ cho mọi mã? | Chốt interface trong thứ 5; PDF tối 02/11 theo assignment; ETA xác nhận TBD | Fixture PDF; không giữ Path đã bị xóa sau compiler return |
| Tâm | Đề xuất giữ tên assignment: exam_{code}.pdf, answers_matrix.pdf, solutions_{code}.pdf. Chốt ai sửa exporter/__init__, dependency/Docker | Trước code file chung; TBD | Đạt chỉ sở hữu .tex/bundler/tests riêng; Tâm sở hữu .typ/compiler/converter |
| Hùng / TASK-308 | Bundler trả bytes hay Path/stream, ownership cleanup, metadata filename/size, error codes và giới hạn dung lượng | Trước ghép Storage; ZIP sáng 03/11 theo assignment; TBD | Test ZIP in-memory; chưa upload cloud |
| Duy | Link assignment v2.1 trên GitHub và xác nhận lịch cuối chuỗi | Trong thứ 5; TBD | Ghi nguồn do owner cung cấp, không tự xuất bản assignment thay leader |

Các đề xuất chưa là quyết định đã chốt. Reviewer Tâm mới ở trạng thái đề xuất theo assignment. Không tự nhận phân công UI do plan cũ nhắc đến.

## Lịch và bàn giao

- 29/10: Draft plan-only, chốt contract và câu hỏi đầu vào.
- 30–31/10: ưu tiên TASK-304; song song chốt interface export và fixture dùng được.
- 01/11: TeX/Markdown/ZIP bằng fixture; kiểm render và encoding sớm.
- 02/11: nhận approved snapshot thật của Duy và PDF thật của Tâm; đối soát đồng bộ key/order/solution trên PDF/TeX/MD.
- Sáng 03/11: giao ZIP + interface/metadata/lỗi cho Hùng; phần còn lại trong ngày dành cho review/sửa và E2E download.
- Lịch chuỗi cuối sát nhau: nếu input trễ, báo dependency tại PR để Duy điều phối; không tự lùi hạn hoặc dùng fixture thay nghiệm thu thật.

## Kế hoạch tự kiểm

- UTF-8 không BOM, tiếng Việt, text chứa ký tự đặc biệt, math inline/display và công thức dài.
- ZIP có đủ đúng filenames/root, không traversal/collision; kiểm thiếu/hỏng PDF; `%PDF-` chỉ kiểm dạng, không chứng nhận PDF layout đúng.
- Shuffle fixture đối soát câu/options/key/solution giữa TeX/MD/PDF đầu vào; không mutate snapshot/canonical.
- Compile XeLaTeX thật, mở kết quả xem tràn trang/vỡ công thức; ghi rõ nếu compiler chưa có thay vì tick mock như render thật.
- Pytest exporter và backend/Blueprint regression, Ruff/Mypy; requirements/resources và Docker CI trên head cuối nếu thay dependency/image.
- E2E với Duy/Tâm/Hùng: approved snapshot → PDF → ZIP → Storage → Signed URL → tải/giải nén/mở file; unit ZIP không thay nghiệm thu chain.

## Quyết định sau phản hồi Duy

Duy đã chốt ZIP/filenames và input approved thật chiều 02/11 tại [PR #27](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/27#issuecomment-6485753431). Xem [handoff bundler](../export-w3-bundler.md) cho typed boundary/bytes/lỗi/giới hạn. Các câu hỏi phía trên giữ lịch sử plan; chưa coi schema snapshot/PDF/Storage đã được mọi owner chấp nhận.

## Bàn giao — trạng thái thực tế

- Đã làm: boundary models, Jinja2 XeLaTeX template, Markdown, ZIP in-memory và metadata; Jinja2/MarkupSafe trong requirements/lock. Không đổi Dockerfile/package __init__ chung.
- Đã kiểm: 24 exporter tests đạt; 1 compile test skip vì thiếu XeLaTeX. Ruff/Mypy/pip check đạt. Kết quả full regression/head trong PR body.
- Chưa kiểm: XeLaTeX compile/layout, dữ liệu approved/PDF thật, mapper DB, E2E Storage/Signed URL. PDF fixture không chứng nhận renderer của Tâm.
- Chưa có reviewer xác minh/GitHub Approve; giữ Draft cho phần phụ thuộc thiếu.

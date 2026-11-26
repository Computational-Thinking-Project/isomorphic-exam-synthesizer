# Đạt — sinh theo câu và tải tài liệu theo định dạng

Nguồn giao việc là yêu cầu trực tiếp của Đạt ngày 24/11/2026 và phản hồi Duy tại PR #109, comment 7104275075. Author Đạt, base dev efed79b. Workflow v0.1 proposed + INPUT-20261109. Reviewer dự kiến Duy và các owner tích hợp, chưa xác nhận lịch.

## Thay đổi

- Pipeline async chính xử lý câu nguồn theo thứ tự. Một request structured JSON sinh đủ các mã còn thiếu của cùng câu, tối đa bốn mã. Kết quả được ánh xạ bằng version_index và kiểm tập mã chính xác trước khi dùng.
- Validator hiện có kiểm từng candidate, chống trùng nguồn và giữa các mã. Candidate lỗi được sửa riêng bằng luồng hiện có. Một request ban đầu không bảo đảm mọi lượt chạy chỉ tốn đúng một request khi có lỗi.
- Callback AI được await lần lượt Câu 1/Mã 1, Câu 1/Mã 2, rồi câu AI tiếp theo. Lỗi persistence được truyền lên ngay. Resume giữ candidate đã commit, seed và fingerprint logic của từng ô. Clone không gọi AI. Worker hiện lưu và phát SSE cho các ô Clone trước khi chạy batch AI, nên không cam kết thứ tự sự kiện toàn cục giữa Clone và AI. Thứ tự hiển thị phải dựa trên source/question number và version_index, không dựa trên lúc nhận sự kiện. Điểm này trả lời F110-03 để Duy xác nhận phạm vi, chưa là contract mới đã chấp nhận.
- UI chọn PDF, LaTeX hoặc Markdown và tải từng file. API GET /api/sessions/{session_id}/export/files?format=pdf|tex|md liệt kê filename/size_bytes. Thêm filename để trả attachment tương ứng.
- API giữ xác thực/RLS và gate export hiện có, đọc lại artifact có checksum, giới hạn dung lượng giải nén, chặn tên trùng/path không hợp lệ và trả no-store. Archive nội bộ được tái sử dụng làm nguồn file đã đóng băng. UI tải file riêng.
- UI Stage 3 của Trung Anh ở PR #109 được tích hợp qua thứ tự nguồn/mã hiện có, thay đổi này nằm trên nhánh riêng.

## Phối hợp tiếp

Khôi phục ô chưa có candidate ID và quyền ghi khi partial vẫn cần API/persistence contract theo I-95-FIX-MISSING-RETRY và I-95-FIX-PARTIAL-WRITE. Thay đổi batching này chưa cung cấp endpoint mới cho hai nghiệp vụ đó. Regenerate của candidate hiện có vẫn dùng luồng một candidate.

## Bổ sung producer handoff sau review 25/11/2026

Trạng thái proposed, cần Duy xác nhận rồi Hùng cập nhật canonical contract. Giữ private archive, packaging version và API ZIP hiện có. Endpoint files đọc artifact đã đóng băng, không rebuild hay gọi Gemini.

| Request/kết quả | Hành vi |
|---|---|
| GET `/api/sessions/{id}/export/files?format=pdf` | 200 JSON `{"files":[{"filename":"exam_101.pdf","size_bytes":123}]}`, tên tăng dần; không có file cùng định dạng trả danh sách rỗng |
| Thêm `filename=exam_101.pdf` | 200 bytes đúng artifact, Content-Disposition attachment; MIME PDF `application/pdf`, TeX `application/x-tex`, Markdown `text/markdown` |
| filename không tồn tại hoặc khác format | 404 `ERR_EXPORT_FILE_NOT_FOUND` |
| format thiếu/ngoài pdf, tex, md | 422 theo validation FastAPI |
| export chưa ready | 409 `ERR_EXPORT_NOT_READY` |
| phiên/quyền/snapshot không hợp lệ | Giữ gate auth/RLS và mã lỗi domain hiện có; không cấp quyền từ filename |
| metadata/storage/runtime lỗi | Mã lỗi export hiện có, lỗi bất ngờ trả 503 `ERR_EXPORT_UNAVAILABLE`, không lộ nội dung lỗi nội bộ |

Response do handler trả có Cache-Control no-store. Auth dependency và request validation vẫn dùng error response chung của ứng dụng. UI truyền AbortSignal cho cả listing và download, hủy khi cleanup/chuyển phiên; kiểm account guard và lifetime trước khi tạo URL, click tải hay cập nhật state. Request cũ không được tải file sau khi rời trang, kể cả transport hoàn tất muộn.

Batch retry lỗi gateway/provider có retryable=true, backoff 1/2/4 giây trong deadline chung, tối đa bốn lần. Mỗi outbound được reserve vào budget chung. Lỗi auth/quota/deadline không retry khi nonretryable; cancellation truyền lên. Sau F110-04, JSON/schema/tập version không hợp lệ được gửi lại bằng prompt đầy đủ cùng output_schema feedback; dừng khi có ba lỗi schema như luồng một candidate, hoặc chạm tổng bốn attempts. Không lấy hoặc lưu candidate từ batch chưa qua toàn bộ schema/tập version. Nếu dừng vì quota/deadline hay ba schema failures ở attempt 3 thì không đánh dấu exhaustion; chỉ đánh dấu khi thực sự dùng hết attempt 4 theo chính sách hiện có. Khi batch thành công ở lần k, candidate được validate ở attempt k, còn tối đa 4-k lượt sửa riêng cho mỗi ô. Bốn lỗi retryable liên tiếp trả attempts=4 và exhausted_attempts nội bộ để worker dùng confirmed-source fallback hiện có; không tự approve câu nguồn.

## Kiểm chứng

Có regression cho một request/bốn mã, đảo thứ tự response, thứ tự nhiều câu, duplicate, quota và resume sau lỗi lưu. Có kiểm tra tải đúng bytes, định dạng, từ chối path và quyền owner. Visual preview dùng dữ liệu giả đã mở bằng browser, kiểm PDF và chuyển LaTeX. Live Gemini/DB/Storage chưa được nghiệm thu trên nhánh này. Kết quả lệnh cuối được ghi trong PR khi bàn giao.

Regression review bổ sung timeout/429/transport rồi batch thành công, bốn lỗi liên tiếp, giới hạn tổng batch+repair, quota/deadline/auth/cancel và worker fallback; frontend kiểm tải bình thường và response muộn sau unmount/chuyển phiên/đổi tài khoản trong StrictMode.

Kết quả author ngày 25/11 trên Windows, Python .venv và Node 24.14.1

- `python -m pytest backend/tests/ai backend/tests/generation backend/tests/api/test_direct_export_files.py backend/tests/exporter -q -p no:cacheprovider` — 795 passed, 16 skipped do thiếu Typst/XeLaTeX trên host.
- `npm test -- --test-reporter=dot` — toàn bộ frontend pass. Tám test ExportFiles/SessionExportPage chạy riêng đều pass, gồm bốn ca lifetime mới.
- Ruff, mypy 128 source files, frontend lint/build và git diff --check pass. Build còn cảnh báo chunk size hiện có.
- Chưa chạy live Gemini, DB, Storage hoặc compile thật cho lần sửa này. Các mock worker không chứng minh RLS/SQL atomicity.

Sau finding F110-04 ngày 25/11, `python -m pytest backend/tests/ai backend/tests/generation -q -p no:cacheprovider` đạt 483 passed trên Windows/Python .venv; Ruff, mypy 128 source files và diff --check pass. Regression gồm batch bốn mã với JSON hỏng/thiếu solution/trùng hoặc thiếu version rồi recovery thành công, lặp lỗi schema dừng ở ba lần, lỗi schema xen transport không vượt bốn attempts, quota/deadline dừng không giả exhaustion. Không có thay đổi frontend/API/persistence trong lượt sửa này; chưa chạy live provider/DB.

## Đồng bộ sau #109 — 26/11/2026

- Nhập `dev@b292443` (Stage 3 #109) vào cùng nhánh #110. Conflict duy nhất ở changelog được giải quyết bằng cách giữ cả hai lịch sử; không sửa source của Stage 3 hay batching/export.
- Windows: AI/generation/direct-files/exporter **803 passed, 16 skipped** (host thiếu Typst/XeLaTeX); toàn bộ frontend tests, lint và build pass. Ruff và mypy **128 files** pass. Build vẫn có cảnh báo chunk size hiện hữu.
- Đây là regression local sau tích hợp source, chưa là kiểm browser/live Gemini/DB/Storage hoặc reviewer acceptance. Approval của Duy ở `9d86a17` thuộc head trước đồng bộ; cần CI/review trên head mới. F110-01/02 vẫn chờ Hùng xác minh; F110-03 và files extension còn cần xác nhận contract rõ ràng.
- EXT-02 #112 chạm `generation/service.py`: Đạt giữ batching/retry/budget/seed-resume; Tâm phụ trách frozen mode/quota/clone. Đề xuất ghép trên dev có #110 hoặc chốt hunk trước sửa song song; chưa nhận đề xuất này đã được Tâm chấp nhận. Trao đổi input ở #111/#112, không sửa nhánh người khác.

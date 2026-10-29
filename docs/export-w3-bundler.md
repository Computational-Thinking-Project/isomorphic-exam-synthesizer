# TASK-307 — XeLaTeX / Markdown / ZIP handoff

Owner: Đạt. [Duy đã chốt tên file và lịch input](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/27#issuecomment-6485753431). Phần độc lập hiện làm bằng fixture; dữ liệu approved thật hẹn chiều 02/11.

## Gọi hàm

    from app.services.exporter.bundle_models import ApprovedExportSnapshot
    from app.services.exporter.bundle_builder import build_bundle

    snapshot = ApprovedExportSnapshot.model_validate(locked_display_snapshot)
    artifact = build_bundle(snapshot, pdf_artifacts)
    # Hùng upload artifact.data; metadata filename/content_type/size_bytes/sha256.

Hàm đồng bộ, API có thể gọi qua asyncio.to_thread để ZIP không chiếm event loop. Không đọc DB, không gọi Gemini, không upload, không tạo tempfile. Input bytes do caller sở hữu; output bytes bất biến, không có cleanup ngầm. Không thay đổi exporter/__init__.py hoặc API/migration của thành viên khác.

## Boundary snapshot — chờ ghép mapper của owner

Đây là boundary của bundler, **chưa phải xác nhận schema DB/API của Duy/Hùng đã ghép xong**:

    {
      "session_id": "b12e3456-e89b-12d3-a456-426614174000",
      "revision": "approved-revision-7",
      "title": "Đề Toán lớp 10",
      "status": "approved",
      "versions": [{
        "code": "101",
        "questions": [{
          "id": "c56a4180-65aa-42ec-a945-5fd21dec0538",
          "question_no": 1,
          "content": "Giải phương trình $x+2=7$.",
          "options": ["3", "4", "5", "6"],
          "correct_key": "C",
          "solution_md": "$x=7-2=5$. Đáp án C.",
          "status": "approved"
        }]
      }]
    }

- 1–4 mã đề, 1–20 câu/mã, cùng số câu; code không trùng tên file; question_no theo thứ tự hiển thị 1..M.
- Owner chỉ map câu is_current=true, đã approved, dùng display options/key/solution **sau shuffle**. Options không kèm nhãn A./B./C./D.; renderer thêm nhãn. Không trộn canonical fields với key đã đảo.
- Solution đã cập nhật key sau shuffle là trách nhiệm mapper; bundler giữ nguyên, không suy luận/sửa đáp án bằng AI. Chưa đối chiếu PDF thật với source; fixtures chỉ chứng minh preservation dữ liệu truyền vào.
- Session approved/exported và revision phải lấy từ snapshot đã khóa. Model validation không thay kiểm ownership/revision/locking/idempotency trong DB của TASK-305/308.

## Gói xuất và giới hạn

Root exam_bundle_{session_id}/, ZIP có:

- pdf/exam_{code}.pdf, pdf/solutions_{code}.pdf từng mã, pdf/answers_matrix.pdf.
- latex/exam_{code}.tex và latex/README_huong_dan_bien_dich.txt.
- markdown/exam_{code}.md.
- README.txt chứa session/revision.

TeX dùng Jinja2 template tĩnh, fontspec, TeX Gyre Termes, amsmath/amssymb/geometry/enumitem. Mỗi file nguồn chứa đề, rồi đáp án/lời giải ở phần sau. UTF-8 không BOM. Markdown dùng bullet labels A–D và math gốc. Solution Markdown được giữ dạng văn bản trong TeX; chưa có renderer Markdown đầy đủ/HTML/images.

Math hỗ trợ $, $$, \(...\), \[...\]. Prose escape ký tự TeX; math chỉ nhận command/environment liệt kê trong source_renderer.py. Macro chưa hỗ trợ báo lỗi rõ, không tự loại công thức. Cần bổ sung profile bằng ca kiểm thật khi tài liệu dùng macro khác. Template không evaluate Jinja trong nội dung câu.

Giới hạn implementation: mỗi PDF 20 MiB, tổng input + nguồn sinh ra 100 MiB, ZIP tối đa 100 MiB. Giới hạn chưa được owner Storage xác nhận; cần thống nhất trước integration. PDF cần header %PDF- và marker %%EOF ở cuối; **không chứng nhận cú pháp đầy đủ/layout/nội dung toán**.

Lỗi BundleBuildError.code: EXPORT_PDF_MANIFEST_MISMATCH, EXPORT_PDF_INVALID, EXPORT_PDF_TOO_LARGE, EXPORT_BUNDLE_TOO_LARGE, EXPORT_UNBALANCED_MATH, EXPORT_UNSUPPORTED_MATH_COMMAND, EXPORT_UNSUPPORTED_MATH_ENVIRONMENT, EXPORT_CONTROL_CHARACTER. Schema sai trả Pydantic ValidationError; caller map sang response API theo contract của mình.

## Trạng thái kiểm

- Pytest kiểm manifest, shuffle mapping, PDF bytes, UTF-8, escape/math, schema, filenames, giới hạn, archive deterministic.
- Jinja2/MarkupSafe khóa trong requirements.lock cho Docker Python 3.11/Linux. Template trong backend/ nên Docker COPY hiện hành đưa vào image, không cần đổi Dockerfile.
- Local thiếu XeLaTeX: compile test skip. Chưa chứng nhận layout tiếng Việt/công thức dài; cần compile và xem PDF trước nghiệm thu.
- Chưa có approved snapshot/PDF thật/Storage Signed URL. E2E chờ TASK-305/306/308 và review.

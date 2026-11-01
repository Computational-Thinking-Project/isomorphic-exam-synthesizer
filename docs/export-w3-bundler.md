# TASK-307 — XeLaTeX / Markdown / ZIP handoff

Owner: Đạt. [Duy đã chốt tên file và lịch input](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/27#issuecomment-6485753431). Phần độc lập hiện làm bằng fixture; dữ liệu approved thật hẹn chiều 02/11.

## Gọi hàm

Luồng tích hợp compiler đã merge từ TASK-306:

    import asyncio
    from app.services.exporter.bundle_models import ApprovedExportSnapshot
    from app.services.exporter.export_pipeline import build_compiled_bundle

    snapshot = ApprovedExportSnapshot.model_validate(locked_display_snapshot)
    artifact = await asyncio.to_thread(build_compiled_bundle, snapshot)
    # Upload artifact.data sau khi hàm thành công.

`build_compiled_bundle(snapshot, *, compiler=None)` là hàm đồng bộ, trả `BundleArtifact`.
Có thể truyền `TypstCompiler(binary_path=...)` qua keyword `compiler`. Hàm xác thực
snapshot trước khi compile, dựng exam/solutions theo từng mã và một answers_matrix
từ chính options/key/solution hiển thị đó, rồi gọi bundler hiện có. Typst CLI phải
có trên PATH hoặc cấu hình binary_path; timeout hiện có là 30 giây/file. Với N mã
đề có 2*N+1 lượt compile tuần tự; API cần chạy ngoài event loop và cấu hình job
timeout tương ứng, không coi timeout 30 giây là giới hạn của toàn ZIP.

Không trả ZIP thiếu khi compiler lỗi. `TypstNotFoundError`, `TypstCompilationError`,
`TypstTimeoutError`, `BundleBuildError` và `ValidationError` truyền về caller;
TASK-308 quyết định response/job status, cleanup và retry/idempotency theo contract
của owner. Tempfile do compiler tự dọn; pipeline chỉ giữ PDF/ZIP bytes trong bộ nhớ.
Giữ nguyên `build_bundle` cho caller đã có PDF:

    from app.services.exporter.bundle_models import ApprovedExportSnapshot
    from app.services.exporter.bundle_builder import build_bundle

    snapshot = ApprovedExportSnapshot.model_validate(locked_display_snapshot)
    artifact = build_bundle(snapshot, pdf_artifacts)
    # Hùng upload artifact.data; metadata filename/content_type/size_bytes/sha256.

`build_bundle` đồng bộ, API có thể gọi qua asyncio.to_thread để ZIP không chiếm event loop. Không đọc DB, không gọi Gemini, không upload, không tạo tempfile. Input bytes do caller sở hữu; output bytes bất biến, không có cleanup ngầm. Không thay đổi exporter/__init__.py hoặc API/migration của thành viên khác.

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

Cập nhật 01/11: đã merge `dev` tại `a57079c` vào nhánh TASK-307, gồm PR #24/#25.
Pipeline compiler → bundler hiện dùng cùng validated snapshot cho PDF/TeX/MD và
ma trận đa mã; có regression hai mã khác thứ tự options/key/solution, lỗi compiler,
snapshot chưa approved và PDF không hợp lệ, cùng test compile Typst thật.
Đây là tích hợp module với fixture, chưa phải snapshot từ DB thật. PR #33 còn
race approval/mutation F01; dữ liệu thật theo ETA Duy chiều 02/11 vẫn là dependency.
Storage/download và size limits còn cần owner Hùng xác nhận.

- Pytest kiểm manifest, shuffle mapping, PDF bytes, UTF-8, escape/math, schema, filenames, giới hạn, archive deterministic.
- Jinja2/MarkupSafe khóa trong requirements.lock cho Docker Python 3.11/Linux. Template trong backend/ nên Docker COPY hiện hành đưa vào image, không cần đổi Dockerfile.
- Kiểm bổ sung ngày 31/10/2026 trên code PR #27 `03cb057`: dùng TinyTeX portable v2026.10 / XeTeX 0.999998. Toàn bộ suite exporter đạt **25 passed**, bao gồm compile XeLaTeX thật, không skip. Bản demo 4 câu (2 fixture và 2 kết quả Gemini thật của TASK-304) biên dịch thành PDF 3 trang; đã render PNG và xem cả 3 trang, không thấy thiếu ký tự tiếng Việt/công thức hoặc tràn lề. Đây là snapshot fixture ở boundary, không phải session đã được duyệt qua API thật.
- Thiết lập kiểm trên Windows: TinyTeX portable cần cấu hình fontconfig trỏ đúng thư mục font sau khi giải nén; đường dẫn workspace có dấu cần alias ASCII tạm thời. Không đổi PATH toàn máy, Dockerfile hoặc dependency của ứng dụng. Binary/compiler chỉ nằm trong thư mục artifact local, không phải dependency runtime của bundler.
- Chưa có approved snapshot/PDF thật/Storage Signed URL. E2E chờ TASK-305/306/308 và review.

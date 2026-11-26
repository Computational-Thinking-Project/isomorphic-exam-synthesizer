# Phân công phát triển tính năng mở rộng — EXT v3.1

**Isomorphic Exam Synthesizer · Nhóm 04 · 25/11/2026**

Mục tiêu: giáo viên nhập hoặc dùng lại đề, sinh đề tương tự hoặc chỉ xáo trộn, kiểm tra, duyệt lưu vào ngân hàng và xuất tài liệu ngay hoặc vào lần truy cập sau. Ngoài phạm vi: chấm bài trên web, gộp nhiều lượt xuất, PDF riêng cho đề gốc, trang lịch sử file.

## 1. Phân công và bàn giao

| Task | Phụ trách | Trách nhiệm | Bàn giao |
|---|---|---|---|
| **EXT-01 · Review** | Duy | Duyệt từng câu, sinh lại theo lý do, hoàn nguyên và phục hồi phiên. | Trạng thái câu, readiness Preview, ví dụ accept/revert kèm đáp án và lời giải. |
| **EXT-02 · Reuse và shuffle** | Tâm | Chọn/xác minh nguồn, tạo lượt idempotent, khóa chế độ, Stage 2 và Shuffler. | Kết quả tạo lượt, trạng thái điều hướng, tùy chọn shuffle và dữ liệu sau hoán vị. |
| **EXT-03 · Export và OMR** | Đạt (backend); Bội Anh (giao diện, tài liệu) | Đạt: snapshot, định danh gói, ledger, đáp án và contract OMR. Bội Anh: mẫu, poll/download sau reload và đối soát bản in. | Định dạng đáp án, miền mã OMR, tải đáp án riêng và mở Export theo lượt. |
| **EXT-04 · Bank và Finalize** | Quỳnh (backend/DB); Hùng (frontend/tích hợp) | Quỳnh: ownership, Settings, tên bộ, mã, migration và transaction duyệt/lưu. Hùng: Dashboard, Bank, Settings, Preview và màn hình sau duyệt. | Quy tắc nguồn/đích, sức chứa, snapshot đã duyệt, metadata, mã và ID lượt. |

Duy điều phối M1. Lịch đợt: M2/Draft PR thứ Năm 26/11, code từ thứ Sáu 27/11, báo kết quả tối thứ Ba 01/12/2026. Reviewer, dự phòng, link PR/tracker và ETA từng EXT ghi trên M1/Draft PR; tính thời gian tích hợp và độ phức tạp EXT-02/04 trước khi cam kết ETA. Hạn báo kết quả không thay cho ETA hoàn tất từng task.

| ID input | Bên giao → nhận | Cần trước tích hợp | Kiểm khi tích hợp |
|---|---|---|---|
| I-EXT-01 | Duy → Tâm, Đạt, Quỳnh | Accept/revert, nguồn thiếu lời giải, điều kiện readiness toàn phiên. | Đọc snapshot sau duyệt, sinh lại, hoàn nguyên và reload. |
| I-EXT-02 | Quỳnh → Tâm, Đạt | Mẫu nguồn/đích, metadata null, receipt, snapshot, miền/sức chứa mã sản phẩm và cặp ID/mã của hai lượt. | Ownership đúng; snapshot do transaction thật tạo. |
| I-EXT-03 | Tâm → Quỳnh, Đạt | Nguồn canonical, trạng thái mở lại, projection hậu shuffle có đáp án. | Chạy nguồn đến reviewed, shuffle và đọc đúng dữ liệu từ DB. |
| I-EXT-04 | Đạt → Quỳnh | Tập con mã/số câu OMR đã xác minh; miền mã sản phẩm do Quỳnh giao qua I-EXT-02. | Chỉ mở OMR sau khi in và chấm thử tổ hợp mã/số câu. |
| I-EXT-05 | Đạt, Bội Anh ↔ Hùng, Quỳnh | ID lượt, tải đáp án riêng, contract gói cũ/mới, phục hồi sau reload. | Đi Bank → Export với lượt cũ và lượt mới. |

Ghi ETA giao input, ETA hoàn tất task cung cấp và thời gian tích hợp/kiểm/sửa theo từng ID trên Draft PR. Chốt contract/fixture sớm; thứ tự tích hợp EXT-01/02 → EXT-04 → EXT-03. Nếu input trễ, báo Duy phần nghiệm thu được và phần còn chờ. M1/M2 theo [WORKFLOW](docs/review/WORKFLOW.md) (v0.1 proposed, `7b7387f`) và [mẫu M1](docs/review/TEMPLATES.md#m1); CI/review theo [CONTRIBUTING](CONTRIBUTING.md). M2 ghi base/head, contract, phạm vi thay đổi, fixture, ETA và kế hoạch kiểm thử.

## 2. Nguồn, bộ đề và metadata

Bản nháp trên Dashboard là lượt chưa duyệt; một `exam_session` là một lượt; mỗi lượt tạo 1–4 mã. Bộ đề trong Bank gồm đề gốc và các lượt đã duyệt. Bank chỉ hiện bộ/lượt `approved` hoặc `exported`. Reuse tạo lượt độc lập và giữ nguyên đề gốc, các mã cũ.

| Nguồn | Mặc định Preview | Lựa chọn giáo viên |
|---|---|---|
| Nhập đề mới | Tạo bộ mới. | Xác nhận tên và metadata, kể cả khi trống hoặc trùng bộ khác. |
| Reuse, metadata trùng nguồn sau chuẩn hóa | Bổ sung vào bộ nguồn. | Lưu thành bộ mới, kể cả khi metadata đều trống. |
| Reuse, metadata khác nguồn | Tạo bộ mới. | Khôi phục metadata nguồn để chọn bổ sung. |
| Bộ nguồn không đủ sức chứa | Báo sức chứa khi biết đích. | Giảm số mã hoặc chọn bộ mới trước xử lý; sau khi sinh giữ đủ mã và cho đổi đích tại Preview. |

Đích bổ sung chỉ là bộ nguồn trực tiếp, xác định server. Hiển thị đích, tên và mã dự kiến; giữ lựa chọn chủ động tạo bộ mới khi reload hoặc sửa trường còn tương thích. Nếu metadata khiến lựa chọn bổ sung mất hiệu lực, nêu lý do và yêu cầu xác nhận đích mới. Đổi tên, tag và mẫu xuất không đổi đích.

- Tên quản lý bắt buộc, tối đa 255 ký tự sau NFC/trim; được trùng. Phân biệt bằng ngày tạo, metadata, trạng thái; chọn, sửa, bổ sung và tải theo ID.
- Trước duyệt, Dashboard cho sửa tên nháp và mở lại đúng tiến độ sau khi đóng tab. Tạo bộ mới dùng tên/tag đã xác nhận trong cùng transaction; bổ sung giữ tên/tag nguồn.
- Chủ sở hữu được xóa lượt chưa duyệt khi không có tác vụ chạy/chờ. `DELETE /sessions/{id}` và Dashboard cùng kiểm job, `approved_at` và trạng thái dưới khóa với nhận job/duyệt. Khi bận báo thử lại; khi xóa dọn dữ liệu con, giữ nguồn và lượt khác.
- `title` là tiêu đề in, sửa được trước duyệt. Nhập mới lấy tiêu đề nhập; reuse kế thừa title khóa của lượt chứa mã hoặc lượt đầu khi chọn đề gốc. Đổi tên quản lý chỉ sửa `display_name`; sau duyệt phải tạo lượt mới để đổi title/metadata (có thể reuse một mã, tắt cả hai cờ shuffle và lưu thành bộ mới).

| Dữ liệu | Ghi | Dùng |
|---|---|---|
| `default_exam_metadata` | `GET/PATCH /users/me/settings` theo user; GET trả đủ tám trường, PATCH thiếu giữ nguyên, null xóa. | Chép một lần khi nhập mới; reuse kế thừa nguồn, kể cả null. Áp dụng Settings cho xem thay đổi trước khi xác nhận. |
| Metadata nháp/chính thức | Preview gửi đủ tám trường kể cả null; Finalize khóa giá trị. | Bank lọc, Export in. Settings thay đổi không tác động lượt cũ; số mã mặc định giữ cơ chế localStorage theo user của MVP. |
| `exam_sessions.subject`, `grade` | Giữ contract hiện tại (`Toán`, `12` mặc định); Tâm kiểm consumer Stage 2. | Nếu ảnh hưởng AI, hiển thị giá trị hiệu lực để xác nhận. Giới hạn theo môn/lớp pipeline hỗ trợ; nhãn Preview chỉ phân loại/in, tham số vận hành không tự điền metadata null. |
| `tags` | EXT-04 lưu theo bộ; mặc định `[]`, trim, bỏ rỗng/trùng. Append giữ tag; bộ mới có thể sao chép. | Bank tìm/sửa; tag không đổi đích, title, snapshot hoặc file. |

Metadata gồm tám trường nullable: `school`, `subject`, `exam_type` (chuỗi); `grade` (số nguyên 1–12); `semester` (1 hoặc 2); `academic_year` (hai năm liên tiếp, YYYY-YYYY); `exam_date` (ISO); `duration_minutes` (số nguyên dương). Chuẩn hóa NFC/trim, chuỗi trắng thành null, từ chối ngày/số sai. So sánh đủ tám trường sau chuẩn hóa, phân biệt dấu và hoa/thường; tên, title, tag và cấu hình xuất nằm ngoài phép so sánh.

EXT-04 quản lý `bank_item` gồm ID, owner, tên, ngày, metadata, tag và lượt đầu đã duyệt. Reuse lưu bộ nguồn, loại nguồn và ID phiên bản nguồn. Mỗi lượt đã duyệt thuộc đúng một bộ. Đề gốc là nguồn canonical của lượt đầu, kể cả khi lượt đó dùng mã đã trộn. Bank đọc dữ liệu cấu trúc; file thuộc Private Export.

## 3. Hợp đồng theo EXT

Route/trường mới là contract đề xuất tương đối với API prefix hiện hành; owner cập nhật contract chuẩn trong PR. Tên kỹ thuật, cách lưu vật lý, chia component thuộc M2, không được đổi hành vi đã thống nhất.

### EXT-01 · Review

Hiện đáp án, lời giải và nút duyệt dưới từng câu; thiếu lời giải thì hiện “Chưa có lời giải”. Chỉ auto-advance sau accept thành công nếu giáo viên vẫn ở đúng phiên/mã/câu và chưa tự điều hướng trong lúc chờ. Ưu tiên câu chưa duyệt tiếp theo cùng mã, rồi mã khác, kể cả câu đã bỏ qua. Cho quay lại câu đã duyệt. Lỗi hoặc reload thì đọc trạng thái server. Chỉ mở Preview khi toàn phiên đủ điều kiện.

`POST /sessions/{session_id}/questions/{version_question_id}/reject` nhận `reasons` tùy chọn dạng mảng, hỗ trợ rỗng/nhiều mã. Duy chốt mã hợp lệ, gồm nhiều/không có đáp án đúng, phương án tương đương, sai đề hoặc sai mức tương đương; backend từ chối mã lạ. Lưu lý do và đưa vào targeted regeneration cùng blueprint/validator hiện có. Chuẩn hóa tập reasons trong fingerprint của receipt/reservation: cùng key/tập lý do trả kết quả cũ, khác tập trả 409; receipt cũ thiếu reasons tương đương rỗng. Giữ ứng viên hiện tại, hạn mức/quota, revert khi đủ điều kiện và bắt buộc duyệt lại câu mới.

### EXT-02 · Reuse và shuffle

Nhập mới chọn **Sinh đề tương tự** hoặc **Chỉ xáo trộn** tại Stage 2 sau xác minh nguồn. Từ Bank, chọn đề gốc/mã và chế độ khi bắt đầu reuse. Endpoint đề xuất `POST /exam-bank/{bank_item_id}/reuse` nhận `source_type` (`original`/`version`), `source_version_id` bắt buộc với version, `generation_mode` và `Idempotency-Key`. Kiểm owner, mã thuộc đúng bộ và lượt nguồn đã duyệt; trả session ID, trạng thái thật và bước tiếp theo; Dashboard mở đúng bước xác nhận/phân tích nếu nguồn chưa sẵn sàng.

Giữ tương thích `POST /sessions` và `POST /sessions/{id}/clone`: tạo draft độc lập, giữ payload/response/ngữ nghĩa Dashboard hiện có, gồm `new_title` của clone. Create khởi tạo tên/metadata theo nhập mới; clone được cả phiên chưa duyệt và không append vào bộ nguồn. Cả hai chỉ tạo draft, liên kết bộ/mã công khai qua Finalize. Chỉ đường reuse của Bank mới chọn mã đã duyệt để bổ sung. Không kế thừa job token, quota, lịch sử export hoặc trạng thái khóa.

| Nguồn | Dữ liệu canonical |
|---|---|
| Đề gốc | Nguồn bất biến của lượt đầu; dùng blueprint nếu khớp nội dung và chế độ. |
| Mã đã duyệt | Projection hậu shuffle gồm thứ tự câu, phương án, đáp án và lời giải. Tạo source ID mới; seed cũ không áp dụng. Với AI, blueprint phải khớp mã được chọn. |

Nguồn phải có provenance, confirmation và revision hợp lệ với source ID mới. Backend dùng cơ chế readiness mà Stage 2 tin cậy; thiếu bằng chứng thì trở về bước xác minh cần thiết. Nguồn thiếu lời giải chỉ tiếp tục khi provenance giải thích trường thiếu theo contract Preview/Export. Tạo lượt/bản sao/receipt nhất quán; chuẩn bị bất đồng bộ trả cùng lượt đang chuẩn bị/có thể phục hồi, lỗi trước khi tạo thành công rollback, không để draft dở. Retry cùng user/key/payload trả cùng session ID; payload khác trả 409.

Trước khi nhận job, backend kiểm revision canonical có 1–20 câu (tận dụng [config service](backend/app/services/generation/config_service.py)) cho nhập mới, clone và reuse. Từ chối nguồn rỗng/vượt giới hạn trước khi tạo job, giữ quota hoặc gọi AI; UI báo số câu và cho sửa/chọn nguồn. Preview/Export cũng kiểm dữ liệu cũ.

1. Ghi `generation_mode` vào request và saved config; lượt cũ thiếu trường dùng `ai_generation`. Khi claim, snapshot khóa mode, nguồn/revision, số mã và policy từng slot. Resume/retry dùng snapshot đó.
2. Với `shuffle_only`, mọi slot là bản sao nguồn đã xác minh, kể cả blueprint hỗ trợ AI. DB claim, worker, persistence và ledger đều bảo đảm không gọi AI sinh câu, không reserve quota sinh câu. Không suy chế độ từ variation rỗng. Việc nhập/xác minh nguồn mới vẫn theo pipeline.
3. Backend kiểm phiên bản, slot, câu, đáp án, provenance và trạng thái trước khi xác nhận bản sao, chuyển `reviewed` và cho shuffle. AI mode vẫn duyệt từng câu, kể cả slot clone/fallback. Thiếu điều kiện thì trả trạng thái phục hồi; client không tự đặt `approved`.
4. Stage 2 lưu `shuffle_questions` và `shuffle_options`. Tại Preview trước khi ghi hoán vị, cho xác nhận/sửa cả hai qua API preferences ở trạng thái reviewed. Nếu cả hai tắt, giữ nguyên thứ tự. Nhiều mã giống nhau được phép, UI cảnh báo. Sau khi ghi hoán vị thì khóa cờ, hiển thị cấu hình đã dùng; mất response thì đọc lại dữ liệu đã lưu. Preview/matrix/export chỉ dùng dữ liệu sau shuffle.

### EXT-04 · Bank và Finalize

| Trường | Quy tắc |
|---|---|
| `version_id` | ID phiên bản dùng nối nội dung, mã và đáp án qua các lượt. |
| `version_code` | Mã nội bộ MVP, giữ trong pipeline và seed hiện có. |
| `public_version_code` | Mã in, duy nhất trong bộ và bất biến sau duyệt. Bank, matrix, đáp án, đề, phiếu và Export dùng chung ánh xạ theo ID. |

Quỳnh chốt định dạng, miền/sức chứa mã công khai cho Tâm và Đạt trong I-EXT-02; không phụ thuộc kết quả kiểm OMR. Tính sức chứa trước generation khi biết đích, hiển thị mã dự kiến ở Preview và kiểm lại khi ghi. Không giữ chỗ, quay vòng, thu hồi mã hoặc cấp một phần lượt. Đạt xác minh tập con mã OMR hỗ trợ, gồm độ dài và số 0 đầu nếu có. Mã ngoài miền OMR vẫn xuất được đề thường, UI giải thích lý do không chọn được OMR.

1. Hùng hiển thị title in, metadata, nguồn/đích, tên bộ và bảng mã/đáp án. Lưu draft qua `PATCH /sessions/{id}/metadata` gồm `title`, đủ tám trường metadata, `save_action` (`append_existing`/`create_new`) và tên/tag khi tạo mới.
2. `GET /sessions/{id}/finalize/preview` trả `preview_revision` opaque, đích và `{version_id, public_version_code}` cho từng đề/matrix; append có ID bộ nguồn, create mới chưa có ID đích đến khi approve. Revision ràng buộc session, nội dung/thứ tự đã lưu, đáp án/lời giải, title, metadata, save_action/đích, tên/tag khi tạo mới và mã dự kiến. Dữ liệu đổi thì phải tải Preview mới.
3. `POST /sessions/{id}/finalize/approve` yêu cầu `preview_revision`; caller cũ thiếu revision phải tải lại Preview và không ghi dữ liệu. Quỳnh kiểm kê API/service/RPC/grants và đóng chữ ký cũ `finalize_approve_session(uuid, uuid, timestamptz)`. Thu hồi đường ghi cũ với mọi caller, kể cả role từng có quyền; chuyển signature và caller cùng đợt. Giữ RLS, kiểm owner phía server, chỉ đường ghi mới được chuyển approved, kể cả qua DB trực tiếp.
4. Approve chạy trong một transaction: kiểm owner rồi tra receipt theo lượt/revision; đã thành công thì replay đúng receipt cũ kể cả đã exported hoặc đổi tên bộ. Lần ghi mới khóa lượt và bộ theo thứ tự nhất quán, kiểm readiness/revision/tên/sức chứa/mã, tạo/liên kết bộ, ghi đủ mã, khóa snapshot, đổi trạng thái và lưu receipt. Lỗi rollback toàn bộ; xung đột làm thay đổi kết quả đã xem trả 409 và yêu cầu tải Preview lại; hết mã cho chọn bộ mới mà giữ đủ phiên bản.
5. Receipt chứa session/status/approved_at/message/bank_item_id/save_action và mã chính thức. Sau duyệt/reload hiện “Đã duyệt và lưu”, đúng bộ/mã và nút **Về ngân hàng**, **Xuất đề của lượt này**. Mất response thì đọc receipt trước khi retry. Quỳnh/Hùng chốt cách đọc receipt theo lượt từ server trong M2, kể cả khi trình duyệt mất state (F-018).

Dashboard giữ `GET /sessions`. `GET /exam-bank` phân trang theo owner, trả items/total/page/page_size và số mã đã duyệt; hỗ trợ tìm tên/môn/lớp/ngày, lọc metadata, khoảng ngày thi/ngày tạo, tag (AND), phương thức nếu ít nhất một lượt đã duyệt khớp; lọc trước phân trang, mặc định ngày tạo giảm dần rồi ID. Bộ metadata trống vẫn tìm theo tên/ngày tạo. `GET /exam-bank/{id}` trả đề gốc và mã đã duyệt với version/session/public code/số câu/chế độ. Nhãn “Đề gốc”; cho xem đề/lời giải nếu có, xem/tải đáp án riêng của đề gốc hoặc mã, reuse đúng nguồn và mở Export theo lượt. `PATCH /exam-bank/{id}` chỉ sửa tên/tag; mọi thao tác kiểm quyền và quan hệ bộ–lượt–mã.

### EXT-03 · Export và OMR

Đơn vị export là một lượt đã duyệt. Bank ghi “Xuất cả lượt (N mã)” khi chọn một mã; ZIP có file đề riêng theo mã, phân biệt bản thí sinh và phần đáp án/lời giải giáo viên trước tải. Tải đáp án riêng là thao tác khác. Phạm vi 1–20 câu/đề; vượt giới hạn báo lỗi, dàn trang không mất câu.

| Tùy chọn | Hành vi |
|---|---|
| `visible_fields` | Title, tám trường metadata và ô thí sinh `student_name`, `student_id`, `student_class`; mảng rỗng là bố cục cơ bản; metadata null bỏ qua, ô thí sinh để trống, luôn in mã và số câu. |
| `answer_sheet` | `none`, `written_boxes` hoặc `omr_bubbles` theo mẫu đã kiểm; độc lập với trường hiển thị; `written_boxes` là ô A/B/C/D đầu đề, UI minh họa mẫu trước khi tạo gói. |
| `formats` | Mẫu áp dụng PDF; giữ LaTeX/Markdown theo bố cục MVP, đúng dữ liệu/mã; chọn hỗn hợp thì ghi rõ format áp dụng mẫu. Nếu chỉ chọn non-PDF nhưng gửi tùy chọn PDF không mặc định, trả 422. |

Server đọc nội dung từ snapshot đã duyệt, kiểm quyền session; client chỉ gửi cấu hình/key. Phân biệt ba nhánh identity:

| Request | Quy tắc |
|---|---|
| MVP trước migration, không body/key | Giữ projection/serialization cũ (`session_id`, title khóa, versions), revision, packager version và công thức key cũ. Nếu packager đã đổi, dùng ánh xạ legacy ghi khi migration theo đúng lượt/identity. Backfill không tham gia tính key. Còn artifact thì trả đúng file/checksum; thiếu/hết hiệu lực dùng lỗi/phục hồi Private Export cho chính identity đó. |
| EXT mới, không cấu hình | Bố cục/format mặc định MVP nhưng identity mới và mã công khai của lượt. |
| Có cấu hình, kể cả MVP backfill | Identity có phiên bản riêng theo snapshot, ánh xạ mã, title/metadata ảnh hưởng file, packager và cấu hình hiệu lực. Chuẩn hóa tập/thứ tự trường và format trước tính key. Cấu hình tương đương cùng key, đầu ra khác key khác. |

Tên quản lý, tag và thời điểm tải không đổi identity.

`POST /sessions/{id}/export` trả `packaging_key` ngay ở `202 preparing` và `200 ready`. `GET /sessions/{id}/export?packaging_key=…` và `POST /sessions/{id}/export/download-url` với `{"packaging_key":"…"}` đọc đúng gói. Không key dùng nhánh mặc định tương ứng loại lượt. UI giữ session/key qua reload, hiện preparing/failed/ready, chỉ tải khi ready. Mất key thì POST idempotent từ cấu hình đã chọn hoặc yêu cầu chọn lại; không suy ra gói mới nhất. Service/RPC kiểm identity và quyền tải file riêng tư.

TNMaker là ứng viên, không bắt buộc. Chỉ mở OMR sau khi ghi nhận phần mềm/phiên bản, quyền sử dụng mẫu, khổ giấy/tỷ lệ in, điểm định vị, vùng số báo danh/mã đề, số câu, phương án A–D, định dạng nhập đáp án và miền mã; in, tô, chấm nhiều mã và đối chiếu kết quả. Đạt xác minh contract; Bội Anh kiểm PDF/bản in. Chỉ cho chọn OMR với tổ hợp mã/số câu đã kiểm. Chưa xác minh thì OMR đóng, nhưng Bank và PDF/LaTeX/Markdown nghiệm thu độc lập.

## 4. Tích hợp code và migration

Baseline tài liệu trước: `dev@efed79b`, checkout Review `fix/stage3-ui@1072d1c` (không phải HEAD đã xác nhận hiện tại). Duy đối chiếu head nhánh tích hợp trong M2, kiểm inline/dialog/focus/revert, ghi phần tái sử dụng và phần còn thiếu (F-019).

| Điểm tích hợp | Phụ trách và điều phải giữ |
|---|---|
| [Review](frontend/src/features/stage3-review/Stage3ReviewPage.jsx), [route](backend/app/api/routes/review.py) | Duy phụ trách hành động từng câu, idempotency, phản hồi AI; Tâm phối hợp generation. |
| [Sessions](backend/app/api/routes/sessions.py), [generation config](backend/app/models/generation_config.py), [policy 026](backend/migrations/026_per_question_generation_policy.sql) | Tâm phụ trách nguồn/mode/claim-worker; Quỳnh/Hùng tích hợp tên/liên kết. Thống nhất trước khi cùng sửa sessions/schema. |
| [Stage 2](frontend/src/features/stage2-config/Stage2ConfigPage.jsx), [Preview](frontend/src/features/stage3-preview/Stage3PreviewPage.jsx), [Finalize](backend/app/api/routes/finalize.py) | Tâm cung cấp preferences/readiness; Hùng phụ trách Preview/điều hướng và nối Export của Đạt. |
| [Finalize security](backend/migrations/009_finalize_security_boundary.sql), [service](backend/app/services/finalize/) | Quỳnh phụ trách ACL/RLS, backfill, mã và receipt; Tâm giữ invariant shuffle. Thống nhất thứ tự migration trên cùng base. |
| [Export revision](backend/app/services/exporter/snapshot_revision.py), [ledger 020](backend/migrations/020_private_export_ledger.sql), [Private Export](backend/app/api/routes/private_export.py), [UI](frontend/src/features/export/SessionExportPage.jsx) | Đạt phụ trách projection/identity/poll/download/legacy; Bội Anh phụ trách UI Export; Quỳnh/Hùng cung cấp dữ liệu đã khóa và mã theo ID. |

Migration EXT-04 phải:

- Tạo bộ riêng cho từng lượt MVP approved/exported gắn chính nguồn của lượt; giữ `version_code`, backfill `public_version_code`, metadata chưa xác nhận thành null, tag `[]`, thông tin vận hành và mã legacy.
- Draft cũ chỉ hiện trên Dashboard. Lượt thiếu liên kết reuse đáng tin là độc lập. Backfill tên từ title, giữ tên trùng với ID riêng; giữ title khóa, nội dung, mã in và object cũ.
- Chạy lặp lại không đổi ID/liên kết/mã/identity. Đối soát lượt, phiên bản, owner và artifact trước/sau; không tạo revision chưa từng được xác nhận.
- Triển khai DB/caller theo thứ tự giữ invariant. Kiểm đường ghi và backfill trước khi mở luồng mới; caller cũ không ghi qua chữ ký Finalize cũ, artifact phát hành vẫn đọc được, lượt đã duyệt mở lại kết quả lưu và xuất lại được.

## 5. Tiêu chí nghiệm thu

Ghi bằng chứng trên head triển khai; fixture chỉ dùng để thống nhất contract. Retry, concurrency, khóa, migration và quyền phải kiểm với DB thật trong môi trường test; OMR phải có bản in và kết quả chấm thực tế. Người đứng đầu mỗi hàng chủ trì, người sau phối hợp.

| Ca | Chủ trì / phối hợp | Kết quả cần xác minh |
|---|---|---|
| A01 | Duy | Accept khi đang xem câu; chuyển phiên/mã/câu thủ công trước response; lỗi/reload không tự nhảy sai vị trí. Readiness mở Preview; cho quay lại câu đã duyệt. |
| A02 | Duy, Đạt | Reasons thiếu/rỗng/nhiều/đảo thứ tự/trùng/mã lạ; cùng key khác nội dung. Kiểm replay/409/validation, AI/quota, revert, accept lại và đáp án/lời giải xuất cuối. |
| A03 | Tâm, Hùng | Shuffle-only kể cả blueprint hỗ trợ AI và resume sau gián đoạn: zero AI sinh câu/zero reserve quota, slot hợp lệ và reviewed phía backend trước shuffle. Đối chứng AI mode/job cũ. Nhập/clone/reuse ở cả hai mode: 1/20 câu hợp lệ, 0/21 bị chặn trước claim, job/quota không tăng. |
| A04 | Tâm, Hùng | Thử bốn tổ hợp shuffle, đổi trước persist, reload trước/sau persist, đối chiếu câu/nhãn/lời giải. Hai cờ tắt giữ thứ tự; nhiều mã hiện cảnh báo. |
| A05 | Tâm, Hùng | Đề gốc/mã đã duyệt × AI/shuffle-only, đáp án đổi nhãn và nguồn thiếu lời giải; kiểm source ID, confirmation, provenance, blueprint, đáp án và shuffle một lần; từ chối mã ngoài bộ. |
| A06 | Tâm, Quỳnh | API create/clone cũ tạo draft đúng owner/tên/metadata; Bank chưa có lượt mới. Clone nguồn draft/approved thành bản độc lập; lỗi không để lại dữ liệu dở. Reuse mất response rồi retry cùng key trả cùng lượt, payload khác trả 409. |
| A07 | Quỳnh, Tâm | Hai đề metadata giống/null vẫn tạo bộ riêng; reuse thử Bổ sung và Lưu thành bộ mới; tên/ID/đề gốc/mã/đáp án không lẫn. |
| A08 | Quỳnh, Tâm, Hùng | Đổi metadata/Settings làm Preview nêu đích mới; khôi phục nguồn cho phép append. Tag không bị ghi đè. |
| A09 | Quỳnh, Hùng | Hai user có Settings khác; PATCH thiếu/null, nhập mới/reuse null, đổi Settings sau khi lập nháp/reload. Đối chiếu môn/lớp vận hành và nhãn in. |
| A10 | Quỳnh, Đạt, Hùng | Tên trùng và đổi tên theo ID không làm đổi title/mã/checksum. Reuse kế thừa title, sửa title chỉ đổi file mới. Xóa lượt reviewed rảnh và lượt reuse chưa duyệt qua Dashboard/API; giữ nguồn. Chặn xóa khi có job/tranh chấp hoặc sau approved/exported. |
| A11 | Quỳnh, Tâm | Thiếu/cũ revision, caller/RPC cũ dưới role từng có quyền không thể approve; ACL và dữ liệu không tạo approved thiếu bộ/mã/receipt. |
| A12 | Quỳnh, Tâm | Hai lượt append cạnh tranh, yêu cầu 4 mã khi còn ít hơn 4; báo sớm, kiểm lại dưới lock, xung đột trả 409; chọn bộ mới giữ đủ mã. Lỗi transaction rollback toàn bộ. |
| A13 | Quỳnh, Đạt, Hùng | Mất response/reload/retry cùng revision, kể cả sau exported/đổi tên, trả một receipt/đích/mapping; revision khác không replay. Có thể về Bank và export sau. |
| A14 | Quỳnh, Đạt, Hùng, Bội Anh | Hai lượt cùng bộ có mã nội bộ 101–104; lượt sau công khai 105–108. Mã 106 khớp Preview/matrix/Bank/PDF/phiếu/đáp án theo version ID; tải đáp án riêng và cả lượt. |
| A15 | Đạt, Quỳnh | Artifact MVP cũ tải đúng qua caller/key và checksum sau migration; gói cấu hình tải lại đúng sau đổi tên/tag. Lượt EXT mặc định in mã công khai đúng. |
| A16 | Đạt, Bội Anh | Hai cấu hình export song song, preparing/reload, cấu hình tương đương cùng key/mẫu khác khác key, poll/download đúng session/key; key sai user/session, build lỗi và retry không trả nhầm file/URL. |
| A17 | Đạt, Quỳnh, Bội Anh | PDF null/không trường/ô điền/nhiều format; công thức, phân trang, student/teacher; non-PDF kèm tùy chọn PDF trả 422; trên 20 câu báo lỗi. |
| A18 | Đạt, Quỳnh, Bội Anh | Khi OMR chưa xác minh vẫn duyệt/lưu và xuất thường. Khi mở OMR, in/tô/chấm nhiều mã và biên; đối chiếu đáp án, lưu mẫu/thông số; ngoài miền bị chặn. |
| A19 | Quỳnh, Hùng | Bank có bộ chưa xuất/đã xuất/nhiều lượt/metadata trống; lọc AND, tìm tên/ngày/tag và phân trang ổn định. User khác không đọc/sửa/reuse/tải dữ liệu hoặc Settings. |
| A20 | Quỳnh, Duy, Tâm, Đạt, Hùng, Bội Anh | Backfill chạy hai lần với tên trùng/hậu tố sẵn, draft/approved/exported, mã legacy ngoài miền OMR. So sánh nguồn/lượt/mã/receipt/artifact; hồi quy AI → Review → Preview → Approve → Export. |

### Truy vết finding

F-001: A11–A13 · F-002: A03 · F-003: A15–A16 · F-004: A07–A08 · F-005: A07, A10, A20 · F-006: A06, A10 · F-007: A09–A10, A14 · F-008: A05–A06 · F-009: A04 · F-010: A13

F-011: A08–A09 · F-012: A12, A18 · F-013: A01–A02 · F-014: A14–A15 · F-015: A06, A11 · F-016: A13, A17–A18 · F-017: A03 · F-018: A13 · F-019: A01–A02

F-018 và F-019 là đầu việc phải chốt trong M2; các finding còn lại được bao phủ bởi contract và ca nghiệm thu tương ứng.

# W4-MVP-07 — Plan và bàn giao: adapter DB tạo `ApprovedExportSnapshot`

- Nguồn giao việc: [W4_ASSIGNMENT](W4_ASSIGNMENT.md) (v2.1, đề xuất chưa phê duyệt hết) và [W4_TASK_DETAIL](W4_TASK_DETAIL.md), mục W4-MVP-07. Đây là sub-deliverable của TASK-308, không tạo task trùng.
- Phụ trách: Hùng (`benalexx007`); reviewer: Duy (đề xuất, chưa xác nhận). Chế độ: author. Workflow v0.1 proposed.
- Repo/nhánh: `feat/w4-mvp-07-export-adapter`, từ `dev@ed81acd`; PR: Draft (link ghi trên PR).
- Hạn: 10/11/2026 18:00 (UTC+7) theo W4. ETA tác giả: phần chắc chắn (hợp đồng, fixture, hàm thuần, test cục bộ) trong hạn này; phần chờ xác nhận thì không có ETA cho tới khi người cung cấp trả lời. Chưa có ai xác nhận ETA.

## Mình cần làm gì?

- Hành vi: đọc từ DB đã khóa (session `approved`/`exported`) và dựng một `ApprovedExportSnapshot` đã kiểm hợp lệ cho exporter (task 08), không nhận key/câu hỏi/hoán vị từ client.
- Tiêu chí đạt (DoD của W4_TASK_DETAIL):
  - chỉ export từ snapshot đã duyệt và lưu bền;
  - fail-closed khi thiếu hoặc sai dữ liệu: `solution_md` trống, thiếu slot, trùng current, 4 phương án không khác nhau, status câu khác `approved`, key lệch `answer_keys`, session chưa approved, receipt hoán vị cũ (`exam_versions.is_finalized` khác true, thiếu `shuffle_seed`/`permutations`);
  - 403/409 và test cho trùng current, lệch mapping;
  - ghi log đã làm sạch định danh snapshot (`session_id`, `revision`, số version/câu; không ghi nội dung câu hỏi, lời giải hay khóa) để so ZIP với preview;
  - fixture có kiểu và code bàn giao cho 08;
  - đối chiếu 100% 6 vị trí Golden (3 câu × N=2, OFF/OFF) với preview — fixture của task 05 ở `2c6247b` (PR #49) có vẻ đã là OFF/OFF (identity); **chờ Tâm xác nhận** trước khi viết test.
- Quy tắc kiểm của hàm thuần (vì `DisplayVersion`/`ApprovedExportSnapshot` chỉ kiểm thứ tự liền mạch, cùng số câu và 1–4 version):
  - số `exam_versions` == `generation_configs.n_versions` (1–4), mã version duy nhất;
  - mỗi (version, source_question) có đúng 1 dòng current `approved`, số slot == số `source_questions`;
  - `answer_keys` phủ đúng (version, 1..M); `correct_option` == `display_correct_key` == `version_questions.correct_key`; `display_no` == `question_no`; `canonical_question_no` hợp lệ và không bị thay thế ngầm.
- Ngoài phạm vi: route/Storage/ZIP/signed URL và RPC `approved → exported` (task 08); preview API (task 05, Tâm); thêm migration (ledger do Duy giữ, Q08); sửa nhánh hoặc file có sẵn của người khác.
- Hiện đã có: mô hình `bundle_models.py`, bundler/compiler trên `dev`; `FinalizeRepository.fetch_matrix_raw` làm mẫu kiểm answer key. Chưa có adapter DB nào trên `dev` (`git grep` chỉ thấy exporter dùng `ApprovedExportSnapshot`).

## Thiết kế: tách phần chắc chắn khỏi phần chờ xác nhận

File mới trong package exporter (không sửa file có sẵn của `finalize/`), tách đọc và dựng:

| Phần | Vị trí dự kiến | Trạng thái |
|---|---|---|
| Kiểu biên `RawSnapshotRows` (dataclass/TypedDict: meta session, `n_versions`, số nguồn, versions, dòng current, `answer_keys`) — ranh giới giữa bộ đọc và bộ dựng | `backend/app/services/exporter/snapshot_rows.py` | Làm ngay, cố định chữ ký |
| Hàm thuần dựng và kiểm snapshot, dùng thẳng `DisplayQuestion`/`DisplayVersion` | `backend/app/services/exporter/snapshot_builder.py` | Làm ngay |
| Bộ đọc DB (owner, trạng thái, truy vấn bảng) trả `RawSnapshotRows` | `backend/app/services/exporter/snapshot_reader.py` | Làm ngay; thay bằng RPC chỉ đổi file này |
| Hợp đồng JSON snapshot + fixture thành công/lỗi | `docs/api/export-snapshot-contract.md`, `backend/tests/fixtures/` | Làm ngay; dẫn xuất từ `bundle_models.py`, không định nghĩa lại projection của preview (Q06) |
| Nguồn của `revision` | hàm `snapshot_revision(session_meta, versions) -> str`, mặc định SHA-256 nội dung chuẩn hóa | Chờ Duy; đổi hàm này và giá trị `revision` trong fixture/hợp đồng |
| Đối chiếu preview (6 vị trí Golden) | test riêng, thêm sau | Chờ Tâm xác nhận fixture ở `2c6247b` (W4-MVP-05; PR #49) |

Tính nhất quán khi đọc (kết luận từ đọc code/SQL trên `dev`, chưa kiểm bằng test PG thật, chưa kiểm RPC 005/016): migration 009 chặn ghi trực tiếp vào các bảng nội dung khi session `approved`/`exported` hoặc `approved_at` khác NULL (`ERR_SESSION_LOCKED`; route dịch thành 423), và các RPC Review/shuffle/`persist_generation_result` đã đọc đều kiểm khóa; trên `dev` không có đường mở khóa. Mỗi lệnh PostgREST là một giao dịch riêng nên không có snapshot isolation giữa các lệnh; cách đọc chỉ đúng khi **đọc `exam_sessions` trước**, chỉ tiếp tục nếu `status ∈ {approved, exported}` và `approved_at` khác NULL, rồi đọc nội dung, rồi **đọc lại** trạng thái/`approved_at` để kiểm không đổi. Đây vẫn là câu hỏi mở cho Duy (Q06/Q08).

Quyền và mã lỗi (tái dùng `ReviewDomainException`, theo quy ước `finalize/`): adapter nhận `user_id` đã xác thực từ lớp gọi, không từ client. Session không thấy được hoặc không tồn tại → 404 `ERR_SESSION_NOT_FOUND`; thấy được nhưng `user_id` khác → 403 `ERR_UNAUTHORIZED` (nếu client là service; với client RLS của người dùng thì người khác sẽ thấy 404 — Duy chọn client); UUID sai → 400 `ERR_INVALID_SESSION_ID`; chưa approved/exported → 409 `ERR_INVALID_SESSION_STATE`; khóa/đáp án lệch → 409 `ERR_INCONSISTENT_ANSWER_KEYS` (đã có); các lỗi dữ liệu khác → 409 `ERR_EXPORT_SNAPSHOT_INVALID` (**mã mới, đề xuất**, chưa đăng ký ở đâu khác). Thông báo không lộ SQL hay dữ liệu thô.

## File và thứ tự triển khai từ thứ 6

| Lượt / file | Mục đích | Cách kiểm |
|---|---|---|
| 1. Hợp đồng JSON + fixture | Bàn giao shape cho 08/FE/OPS | Fixture nạp được vào `ApprovedExportSnapshot` |
| 2. `snapshot_rows.py`, `snapshot_builder.py` | Dựng + kiểm snapshot | Test đơn vị từng ca lỗi (kể cả trùng current, vì index DB không cho tạo ca này) |
| 3. `snapshot_reader.py` | Đọc, kiểm owner, status, đọc lại trạng thái | Test với stub bảng |
| 4. Test PostgreSQL thật (opt-in) | Đọc đúng từ DB đã khóa, session chưa approved, mapping lệch | `RUN_POSTGRES_MIGRATION_TESTS=1`, tái dùng harness `sql_client_fixture` hiện có; ca "trùng current" chỉ mô phỏng bằng cách bỏ `idx_single_current_version_question` trong container dùng một lần, ghi rõ là mô phỏng |
| 5. Test đối chiếu preview | 6 vị trí Golden | Sau khi Tâm xác nhận fixture |

## Đầu vào và câu hỏi (hỏi trên Draft PR)

| Cần ai | Câu hỏi | Cần trước | Mặc định mình dùng | ETA bên cung cấp | Link trả lời |
|---|---|---|---|---|---|
| Duy | `revision` lấy từ đâu? (DB không có; contract preview của Tâm đề xuất `exam_sessions.updated_at`, nhưng giá trị này đổi khi approve) — [câu hỏi](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/58#issuecomment-6761402596) | Trước khi chốt fixture | SHA-256 snapshot chuẩn hóa; hoặc `approved_at`/`updated_at` | chưa có | chờ |
| Duy | Đọc bằng truy vấn bảng hay RPC đọc riêng? Dùng client nào (service hay RLS người dùng) để có 403 thay vì 404? | Trước lượt 3 | Bảng, không thêm migration (Q08, ledger chưa chốt) | chưa có | chờ |
| Tâm | Contract preview (4.2) để adapter cấp `title`/`revision` từ `exam_sessions`: đúng ý? Fixture OFF/OFF ở `2c6247b` có phải bản chốt? Adapter đọc DB (không dựng từ response preview) và chỉ dùng preview làm đối chiếu: ổn? — [câu hỏi](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/58#issuecomment-6761403010) | Trước lượt 5 | Adapter tự cấp; đối chiếu sau khi Tâm xác nhận | chưa có | chờ |
| Tâm + Duy | `solution_md` trống: fail-closed (Q01 bản tạm của W4)? | Trước lượt 2 | Fail-closed; Q01 mới là đề xuất, chờ Tâm chốt khi merge vào `dev` | chưa có | chờ |

- Output mình cần giao cho task sau: task 08 (Hùng) nhận typed fixture + code (`RawSnapshotRows`, builder, reader); hợp đồng JSON cho Philip/Đạt/Quỳnh. ETA: cùng hạn 10/11 18:00 cho phần cục bộ; chưa ai xác nhận.
- Lịch có khả thi không? Phần cục bộ khả thi trong ngày. Task 05 API thật hạn 10/11 12:00; fixture ở `2c6247b` đã đọc được nhưng chưa được Tâm xác nhận. 08 hạn 11/11 18:00 chỉ tích hợp thật được sau 07 và bucket của 11s. Nếu chưa xác nhận kịp, đối chiếu preview chuyển sang sau; báo Duy điều phối.
- Quyết định đã thống nhất: chưa có.

## Kế hoạch tự kiểm

- Test đơn vị cho hàm thuần và bộ đọc (stub), rồi PostgreSQL 15 thật.
- Ruff/mypy theo CI. Chưa kiểm: staging, Supabase thật, đối chiếu preview thật.

## Bàn giao — điền theo kết quả thực tế

- PR/commit/output: PR #58 (Draft). Code: `snapshot_{rows,revision,common,builder,reader,adapter}.py`, hợp đồng `docs/api/export-snapshot-contract.md`, fixture `backend/tests/fixtures/export_snapshot_golden.json`.
- Đã làm / đã kiểm (Python 3.11 Windows, stub bảng, không DB thật): test exporter 157 passed / 8 skipped (87 test của adapter) ở commit này; ruff check, ruff format (file mới) và mypy sạch. Toàn bộ backend chưa chạy lại ở commit này: ở commit trước, lần chạy đầy đủ (trừ `tests/migrations`) được 1166 passed / 10 skipped, và trong lần chạy lại độc lập có 1 test timing (sympy hoặc gateway) lúc fail lúc pass, không thuộc file nào của PR này. **Chưa có test PostgreSQL thật** (lượt 4), nên DoD "unit/DB tests" mới đạt phần unit. Chưa kiểm RPC 005/016, staging, Supabase.
- Chưa làm: đối chiếu 6 vị trí Golden với preview (chờ Tâm xác nhận fixture); nguồn `revision`, cách đọc/client (chờ Duy).
- Đã chấp nhận: chưa có (chưa có review GitHub).
- Còn chờ: các câu hỏi ở trên.

# W4-MVP-07 — Adapter DB tạo ApprovedExportSnapshot

- Nguồn: [W4_ASSIGNMENT](W4_ASSIGNMENT.md), [W4_TASK_DETAIL](W4_TASK_DETAIL.md), phần 07 của TASK-308.
- Author: Hùng (`benalexx007`), [PR #58](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/58), nhánh `feat/w4-mvp-07-export-adapter`.
- Workflow v0.1 proposed, gồm INPUT-20261109 tại `dev@21887c1`. Base ban đầu `ed81acd`; đã merge `dev@21887c1` không conflict ngày 12/11/2026.
- Hạn giao: 10/11/2026 18:00 UTC+7, đã qua. Không tự đổi hạn hoặc coi task đã nghiệm thu.
- Quyền lượt này: hoàn thiện code/test/docs 07; làm xong phần đã chốt rồi mới đăng câu hỏi còn thiếu. Không làm 08/12, sửa nhánh owner khác hay merge PR.

## Hành vi và triển khai

Đọc session của user đã `approved`/`exported`, dựng model frozen
`ApprovedExportSnapshot` từ DB cho 08. Không nhận câu/key/hoán vị từ client.
Fail closed khi thiếu slot, trùng current, key sai mapping, receipt cũ, câu chưa
approved, stem/solution trống hoặc options không phân biệt. Contract chuẩn:
[export-snapshot-contract](../api/export-snapshot-contract.md).

| Phần | Trách nhiệm | Kiểm |
|---|---|---|
| `snapshot_rows.py` | Biên typed raw rows giữa reader/builder | Fixture, unit |
| `snapshot_builder.py`, `snapshot_common.py` | Kiểm matrix/keys/content, dùng DisplayQuestion/Version có sẵn | Hợp lệ và fail-closed |
| `snapshot_revision.py` | SHA-256 ID + title chuẩn hóa + versions; loại status/timestamps | Title/content đổi hash; whitespace/lifecycle không đổi hash |
| `snapshot_reader.py`, `snapshot_adapter.py` | Client RLS user; kiểm owner/approval trước đọc và re-check sau đọc | Stub, PostgreSQL thật |
| `export_snapshot_golden.json` | Output typed có hoán vị câu/options | Equality với builder |
| `export_preview_off_off.json` | Fixture nguyên bản PR49 tại `0f760067d9ba343401b46f0c41839065633bc48a` | Đủ 6 slot sau shuffle/approve thật |
| `test_export_snapshot_pg.py` | Full schema/migrations002–018, shuffle/approve RPC, RLS, lock, fencing, concurrency | PostgreSQL15 dùng một lần |

Reader gồm nhiều transaction, không phải transactional snapshot. Test kiểm khóa
sau duyệt, concurrent readers/writes bị chặn và approve chưa commit. Không thêm
read RPC khi chưa có bằng chứng cần thiết. Network/SDK errors không đổi thành409;
08 chịu trách nhiệm response an toàn. Ngoài scope: export route, compiler/PDF,
Storage, ZIP/signed URL, writer approved→exported (08), API/docs preview (Tâm/05), migration mới.

## Bảng input duy nhất

| ID / người giao → nhận | Lựa chọn và nội dung | Trạng thái / bằng chứng | Còn cần |
|---|---|---|---|
| I07-01 Duy → Hùng | SHA-256 chuẩn hóa **gồm title**, ổn định qua approved→exported | **Decided, Delivered, Accepted, Integrated cục bộ** theo [Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/58#issuecomment-6801792075); code/fixture/test đã cập nhật | Review code cuối; không hỏi lại lựa chọn |
| I07-02 Duy → Hùng | Table reads với `get_user_db` có RLS; foreign có thể404 | **Decided, Delivered, Accepted, Integrated cục bộ**, cùng comment; PostgreSQL kiểm RLS/lock/concurrency | Không chờ read RPC/service client |
| I07-03 Duy → Hùng | Giữ lỗi cũ +409 `ERR_EXPORT_SNAPSHOT_INVALID`; availability khác409 | **Decided, Delivered, Accepted, Integrated cục bộ**, cùng comment; timeout/connection/PostgREST tests | Không hỏi lại mã lỗi |
| I07-04 Tâm (`AI-WFox`) → Hùng | Dùng fixture OFF/OFF PR49 tại SHA trên, preview trước duyệt bằng export sau duyệt từ cùng DB | **Requested**: [câu hỏi gốc](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/58#issuecomment-6761403010); reply bị cắt chưa là Delivered. Đã tự kiểm parity, chưa coi owner chấp nhận | Tâm xác nhận fixture bản chốt, cập nhật §4.2 contract preview theo revision Duy đã chốt và dẫn commit; ETA chưa được xác nhận |
| I07-05 Duy → Hùng; upstream: Duy, Quỳnh (`nhatquynh1107`), Tâm (`AI-WFox`) | Export thiếu solution phải fail-closed, không tự tạo solution/autoapprove | **Decided, Delivered, Accepted, Integrated cục bộ** theo [issue46](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/46#issuecomment-6745367064). Hùng bàn giao409 `ERR_EXPORT_SNAPSHOT_INVALID` khi solution trống | Gate confirm/config/generation của Q01 và chính sách ngoài Golden vẫn do các owner trên chốt; không là lựa chọn còn thiếu của adapter07 |

Integrated ở bảng chỉ là áp dụng input trong working tree, không phải task Done,
GitHub Approve hay deploy. Đã hoàn thiện phần độc lập rồi đăng [follow-up trên #58](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/58#issuecomment-6813431143):
Tâm nhận hai yêu cầu fixture/contract; Duy và Quỳnh được tag ở bàn giao Q01.
Không sửa PR/issue descriptions. Chưa có phản hồi mới nên I07-04 vẫn Requested.

## Tự kiểm ngày 12/11/2026 trước sửa F01

- Docker Desktop local, Python3.11, PostgreSQL15-alpine dùng một lần, backend dependencies
  và Jinja2 trong image test; mạng internal, không host ports, key thật, DB chung hay Docker socket.
- `pytest backend/tests/exporter backend/tests/migrations/test_export_snapshot_pg.py -q`:
  **182 passed, 1 skipped, 12 subtests passed**, với repository preview tại SHA trên
  nạp riêng trong harness (SQL/RLS thật). Skip là compiler external không có, không phải
  bằng chứng PDF. Một pytest warning do harness import plugin trước collection.
- Với đúng code nhánh hiện tại, không nạp PR49 riêng: **181 passed, 2 skipped,
  12 subtests passed**; skip thêm là parity preview chưa merge. Cả hai lần đều có
  PostgreSQL thật. Fixture Golden được kiểm byte-for-byte với commit PR49 đã ghim.
- Đã kiểm: hash title/content, typed fixture, availability khác data conflict, foreign RLS,
  khóa các bảng/metadata, Review/shuffle bị chặn; `persist_version_question` (005) và
  `persist_generation_result` (016) bị fenced; approve chưa commit; concurrent read/write;
  đủ 6 slot Golden và projection preview trước duyệt khớp export sau duyệt, gồm matrix.
- `ruff check backend/app scripts/blueprint` và Ruff các test snapshot/PG mới: pass.
  `mypy backend/app --ignore-missing-imports`: pass, 97 source files.
  Ruff format check9file mới/thay và `git diff --check`: pass; JSON/link nội bộ hợp lệ.
- Giới hạn: SQL transport thay HTTP; seed historical reviewed exam, không full W2/AI
  producer. Chưa deployed Supabase/JWT/PostgREST, Gemini, compiler/PDF, Storage hoặc E2E08.
  Preview chưa merge thì parity test trong repo skip rõ; phải chạy lại sau tích hợp cuối.
  [Hướng dẫn chạy](../../backend/tests/migrations/README.md#w4-mvp-07-export-snapshot).

## F01 — Author: claimed_fixed (12/11/2026)

- Lỗi review: canonical bị ép thành1..M khiến session approved có số câu nguồn3,8,9
  bị từ chối export dù display1,2,3 và mapping hợp lệ.
- Sửa: chỉ display slots phải liên tiếp; canonical là số nguyên dương không trùng,
  giữ nguyên nhãn nguồn. Không thay quyền/reader/RawSnapshotRows hoặc đổi dữ liệu
  nguồn; source/canonical binding vẫn do shuffle/approval xác thực. Adapter tiếp
  tục kiểm coverage nguồn, completeness và key/canonical khớp nhau.
- Thêm14 unit regressions cho số nguồn có khoảng trống và các lỗi kiểu/trùng/
  thiếu câu/lệch key; thêm2 PostgreSQL regressions dùng actual shuffle→approve→adapter
  với3×2slots và chặn approval khi key mapping bị tráo. Không bypass guard/DDL.
- Exporter + PostgreSQL native: **197 passed, 2 skipped, 12 subtests**. Bản cuối
  đối chiếu repository PR49 đã ghim: **198 passed, 1 skipped, 12 subtests**.
  Skip còn lại là XeLaTeX, warning do harness import plugin trước collection.
  Ruff/format pass, mypy pass97files, diff check pass. Các giới hạn môi trường
  và deployment của mục trước vẫn giữ nguyên.
- Contract và migration test README đã đồng bộ. Đây là kết quả author tự kiểm,
  chưa có reviewer xác minh bản sửa hoặc GitHub Approve; không sửa báo cáo review cũ.

## Bàn giao và điều kiện còn lại

08 (Hùng) nhận entry point, model, fixtures và contract; dùng user RLS, đưa sync I/O
vào worker thread ở async route, sanitize lỗi hạ tầng tại route. Không service-role
read để vượt RLS. Code07 không tự upload hay đổi trạng thái.

Đã có code cho các quyết định đã chốt; còn I07-04, review/acceptance cuối và
kiểm preview sau merge. Đợt bàn giao này đưa code/test/contract hoàn thiện07 và bản
sửa F01 vào cùng PR58; trạng thái published/CI/approval theo GitHub, chưa coi là đã nghiệm thu.

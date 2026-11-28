# EXT-01 / 02 — Durable reasons và DB receipt

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Bắt đầu local với contract Q01; chốt signature/số migration/deploy phải qua G3/Q05.
- **File / đầu vào:** `backend/migrations/<next>_ext01_review_reasons.sql`; `backend/app/services/review/{repository,receipts,service}.py`; đầu ra gói 01.
- **Thứ tự làm:** Kiểm callers và ACL; thêm canonical reasons vào receipt; sửa lookup/reserve và parser; cùng binding ở mọi retry/settle; rehearsal trên DB cô lập; phối hợp gói 03 cho completion projection.
- **Đầu ra / điều kiện hoàn thành gói:** Receipt/API adapter có binding, legacy compatibility và evidence PG; gói 03/04 chỉ tin receipt đã xác minh. Không deploy migration độc lập với backend tương thích.
- **Kiểm chứng:** A02-04/05/06/07/08/17/19/23/30. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** chưa xác nhận code/test của gói. Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-3-2"></a>

### 3.2. Database và durable reasons (V01, V09; R01, R11)

**Thiết kế lưu trữ EXT-01 (rollout liên task chờ Q05):** lưu mảng canonical tại `review_operations.reservation_result.reasons` khi reserve trong cùng transaction. Đây là JSONB receipt hiện hữu, đủ để so sánh tập lý do và audit operation; không cần cột/bảng mới nếu kiểm chứng caller cho phép. Nếu chọn cột riêng vì lý do ràng buộc SQL, chỉ một nguồn authoritative, projection receipt phải derive từ cột đó. Không lưu hai bản độc lập. Không sửa migration 006 đã phát hành. Receipt lịch sử không có key `reasons` tương đương `[]`; key hiện diện nhưng malformed không được âm thầm coi là rỗng.

- Fingerprint logic: `(actor_id, session_id, question_id, action=REJECT, canonical_reasons)`. So sánh canonical set trực tiếp, không bắt buộc hash mới. API và DB RPC đều kiểm array/string/allowlist, sort + deduplicate ổn định; từ chối payload sai trước reserve/dispatch. Giữ ownership và session/question membership trước khi tiết lộ receipt; không cấp SELECT ledger.
- Sửa cả `review_lookup_regeneration` và `review_reserve_regeneration` (006:448–515). Giữ session-first lock, global operation UUID advisory lock, unique active operation/session, private ledger RLS/ACL, 30 calls/session, tối đa 4 calls/operation. Replay không gọi AI/charge. Existing key khác reasons trả 409 kể cả khi candidate cũ không current hoặc session đã khóa; replay hợp lệ không bị editability/mode/quota guard của operation mới chặn.
- `ReservationReceipt` (`extra="forbid"`) và parser/identity checks phải cập nhật đồng bộ; default legacy chỉ áp dụng trường vắng mặt. Reasons không thuộc `snapshot` frozen: `_review_check_frozen_artifacts` (006:1176+) so sánh toàn bộ artifact trừ peers. AI chỉ dùng reasons từ receipt đã xác nhận.

| Caller thực tế (service.py) | Thay đổi bắt buộc |
|---|---|
| `reject_question` lookup trước reserve (248–256) | Truyền request canonical reasons |
| `_reserve_receipt` (207–231), tối đa ba retry 503 | Cùng operation ID và cùng canonical reasons |
| `frozen_inputs` + dispatch (271–282) | Dùng `reservation.reasons`; không trộn vào frozen artifacts |
| `_settle` lookup khi mất phản hồi (184–205) | Truyền `reservation.reasons`, kể cả cancellation/complete uncertainty |
| `_replay` và completion projection | Bind owner/session/question/operation/reasons trước dựng kết quả; không đọc live candidate làm kết quả cũ |

Kiểm kê callers bằng search toàn repo (bao gồm tests/mocks/docs), RPC overloads, ACL và PostgREST trước khi viết migration. Theo phương án đề xuất Q05 (chỉ deploy sau G3 ở [§0.1](../../../EXT-01-Implementation-Plan-v1.2.md#section-0-1)), chọn rollout **đồng bộ DB/backend/FE có maintenance window ngắn**: dừng nhận operation mới, cho operation active settle hoặc recover đúng lease, `DROP` chữ ký 3 tham số `review_lookup_regeneration` / `review_reserve_regeneration` và giữ 1 chữ ký 4 tham số duy nhất (không `DEFAULT` để tránh `PGRST203` & bypass), `NOTIFY pgrst, 'reload schema'`, smoke rồi mở FE. Test quyền `authenticated`/`anon`/`service_role`. Không chạy DDL shared DB khi chưa có deployment gate. Thứ tự trên Git là baseline `027`, EXT-02 mode `028`, EXT-01 Review `029`. Applied ledger chung chưa xác minh.

<a id="section-3-2-1"></a>

### 3.2.1. Migration và kế hoạch phục hồi triển khai

- Trước DDL, kiểm inventory thực tế ở integration HEAD, applied ledger của môi trường đích, mọi overload và grants; Số các migration sau `029` phụ thuộc inventory và xác nhận owner. Nếu ledger đã ghi EXT-01 dưới số `028`, cần đối chiếu nội dung đã áp và thống nhất migration tiến về trước cùng owner trước khi rollout. Phần guard mode phụ thuộc G2 và schema EXT-02: nếu schema/helper chỉ xuất hiện sau migration Review thì tách guard sang migration kế tiếp hoặc đổi thứ tự được owner xác nhận. Không phát hành guard tham chiếu cột chưa tồn tại, cũng không âm thầm bỏ guard khi thiếu schema.
- DDL trong transaction: thay signature, cập nhật mọi SQL caller phụ thuộc, projection receipt, REVOKE/GRANT rõ ràng cho signature mới. Không dùng DROP CASCADE để giải quyết dependency. Parser mới đọc receipt cũ vắng reasons là `[]`; receipt malformed phải fail closed. Giữ owner/member check trước trả receipt, replay trước guard của operation mới.
- Maintenance áp dụng cho mọi entry point có thể tạo Review operation, kể cả caller trực tiếp có quyền RPC; không chỉ ẩn nút FE. Drain operation active hoặc recover đúng DB lease; không cưỡng bức complete/fail operation chưa hết hạn. Deploy backend/DB tương thích trong cửa sổ này, reload PostgREST schema rồi smoke HTTP/RPC trước mở lại traffic.
- Rehearsal trên DB disposable gồm fresh chain và populated legacy receipts. Lưu migration list, signature/grants trước/sau, row counts, quota và receipt identity. Triển khai thật chỉ sau gate môi trường đã được cấp quyền; không lấy DB test pass làm bằng chứng DB shared đã áp.
- Nếu DDL lỗi: transaction rollback, giữ maintenance và kiểm schema trước retry. Nếu backend/smoke lỗi sau DDL commit: giữ maintenance, ưu tiên roll-forward bản backend tương thích signature mới. Không rollback riêng backend sang caller 3 tham số hoặc xóa reasons/receipt đã ghi. Khôi phục backup chỉ theo phương án owner triển khai đã xác nhận và có rehearsal; plan không cấp quyền restore/xóa dữ liệu shared.

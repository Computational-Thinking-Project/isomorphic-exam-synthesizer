# EXT-01 / 03 — Replay bất biến và recovery

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Bắt đầu helper/DTO và tests local ngay; tích hợp reasons binding sau gói 02.
- **File / đầu vào:** `backend/app/services/review/{service,repository,receipts}.py`, `backend/app/api/routes/review.py`, `backend/app/models/schemas.py`; Q02/Q03.
- **Thứ tự làm:** Dùng completion payload cho cả ba response path; phân loại active/terminal/uncertain; thêm recovery route với owner check trước worker RPC; đối soát snapshot; test crash, expiry, race và lost response.
- **Đầu ra / điều kiện hoàn thành gói:** Response/recovery contract và tests để gói 05 nối client; không giữ lock xuyên AI hoặc coi local lock là DB authority.
- **Kiểm chứng:** A02-10/11/12/13/19/20/25; A01-14 phối hợp UI. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** đã có bản G0/G1 của author. Xem [bằng chứng và giới hạn ngày 27/11](08-verification.md#evidence-20261127). Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-3-3"></a>

### 3.3. Replay và recovery (V02, V03, V05; R01, R02, R04, R05)

**Completed result:** `_result()` hiện đọc live `version_questions`, trong khi ledger lưu `completion_candidate` (`stem_latex`, `solution_md`, `options`, `correct_key`, `api_calls_count`, `validation_report`) và `settlement_result` (`previous_question_id`, `question_id`, `session_id`; status khởi tạo tại commit là `'pending_review'`, `006:545–603`). Đề xuất mở rộng owner lookup projection để trả `completion_candidate` đã commit cho receipt completed, cập nhật cả `ReservationReceipt` và `CompletionReceipt` (`extra="forbid"` trong `receipts.py`); không cấp table read hoặc tạo receipt system mới. Một helper dựng `RegeneratedQuestionResponse` từ completion payload đã lưu (`content` map từ `stem_latex`), `previous_question_id`, `question_id` và `status='pending_review'`; kiểm session/operation/lineage/shape (lưu ý `review_logs.reason` tiếp tục ghi `'REGENERATED'` trừ khi chốt khác). Cả ba đường trả kết quả dùng cùng helper: `_replay`, normal complete và `_settle` phát hiện complete đã commit. Có thể dùng lookup đã bind reasons sau commit (read failure trả 503 retry same key, **không settle lại**); tránh RPC mới nếu đủ. Không suy ra kết quả lịch sử từ dữ liệu live nếu thiếu completion evidence. Kiểm first response và replay bằng cùng payload kể cả accept/reject/shuffle sau đó; FE luôn đọc snapshot hiện hành riêng.

| Operation status | Quy tắc đề xuất |
|---|---|
| Không tồn tại | Reserve sau ownership, editability, mode, current candidate, quota |
| Cùng key khác canonical reasons | `409 ERR_ATTEMPT_REPLAYED` (mapping `REVIEW_IDEMPOTENCY_CONFLICT` trong `repository.py:65–68`), không dispatch/mutation |
| `completed` cùng reasons | Trả projection bất biến đã commit, không gọi AI |
| `active` còn hạn | `409 ERR_QUESTION_BUSY`, giữ key; không dispatch/settle hộ operation khác |
| `active` hết hạn | Recover qua RPC hiện hữu, đọc lại receipt cùng binding; không chạy lại operation cũ |
| `failed` / `recovered` | Terminal, trả `409 ERR_OPERATION_FINISHED`, không dispatch |

**Quy tắc Q02:** `completed` phải trả cùng payload projection như lần đầu; mọi terminal `failed` và `recovered` cùng key (kể cả receipt lịch sử) trả thống nhất `409 ERR_OPERATION_FINISHED` (ngoại lệ terminal thống nhất của EXT-01 để client cấp `Idempotency-Key` mới). `failure_code()` và `generation_error()` hiện không ánh xạ một-một, không suy lỗi lịch sử từ rollback code. Lỗi trước reservation/uncertain transport không phải terminal receipt. Không tự mở rộng sang immutable response cho Accept/Revert.

**Recovery Q03:** retry cùng key `active` phải kiểm recovery dưới `session_lock_registry` **trước** `if self.ai_generator is None:` và trước khi trả `409 ERR_QUESTION_BUSY` (dùng DB clock, không dùng đồng hồ FE quyết định expiry); sau recovery lookup lại bằng `reasons` (`service.py:248–270`). Với reload/mất key, reuse `ReviewRepository.recover_stale_operations` → service-role `review_recover_session` qua action owner-authenticated `POST /api/sessions/{session_id}/review/recover` (trả `{ "recovered_count", "has_active_operation", "snapshot" }`; kiểm owner và tuân thủ các guard `REVIEW_NOT_READY` / `REVIEW_LOCKED` / `REVIEW_POST_SHUFFLE_LOCKED` của `021`). GET snapshot/progress vẫn read-only. Không thêm scheduler/queue. FE khi mở snapshot có candidate `regenerating` mà không giữ key active trong tab gọi `/recover` 1 lần; nếu `has_active_operation=true`, hiện đang xử lý và cho nút **Kiểm tra lại**; sau action cập nhật từ snapshot trả về. Khi lease 180 giây hết hạn, recover trả prior_status; nếu complete thắng race, đọc candidate mới. Không hủy active chưa hết hạn, không hoàn quota đã dispatch. Nếu recovery/refetch lỗi, giữ trạng thái cần đồng bộ, không cho mutation/Preview khi chưa xác nhận.

**Key lifecycle:** key thuộc actor/session/candidate/action + payload canonical. Lỗi transport/503 uncertain hoặc active: giữ key và payload; không đổi reasons rồi retry key đó. Sau terminal được xác nhận, mới cho user tạo operation mới bằng key mới. Sau success, retire key khi đã đối soát kết quả; stale candidate không được hồi sinh. Nếu reload còn key thì đối soát bằng key (chỉ lưu tối thiểu trong bộ nhớ/session tab theo Q03, không lưu nội dung đề hay approval). Nếu mất key, recovery vẫn dựa trên session và snapshot server. Sau bất kỳ mutation error, đọc lại server; không auto-advance do lần đọc phát hiện approved nếu accept trước đó báo lỗi. Với 409/423 routing, giữ logic post-shuffle/approved/exported hiện hữu.

<a id="section-3-3-1"></a>

### 3.3.1. Recovery authorization và kết quả lỗi

Endpoint recovery mới là mutation, không chỉ một snapshot read. `session_lock_registry` chỉ giảm cạnh tranh trong process; DB session lock là authority giữa workers.

1. Parse UUID, authenticate caller; xác minh owner bằng RLS-bound repository trước mọi lời gọi service-role. `recover_stale_operations()` hiện gọi worker RPC, tự nó không chứng minh caller sở hữu session. Non-owner/not-found trả lỗi theo API contract hiện hành, không tiết lộ receipt/count.
2. Kiểm editability/post-shuffle theo owner snapshot/guards trước recovery; giữ logic guard trong DB để tránh race. Không chỉ gọi recovery rồi mới dựa vào snapshot để từ chối caller. Nếu cần wrapper DB cho owner check + recovery nguyên tử, thống nhất signature/ACL trong Q05, vẫn tái sử dụng settlement hiện hữu.
3. Dưới local lock, gọi recovery; RPC dùng DB clock và parent-first lock. Đọc lại owner snapshot sau mutation, derive `has_active_operation` từ trạng thái `regenerating` của snapshot đó. Đây là quan sát tại thời điểm đọc, không cam kết không có request khác xuất hiện sau response.
4. Nếu recovery đã commit nhưng snapshot read lỗi, trả lỗi unavailable theo mapping API, không dựng snapshot giả; FE giữ sync-required và retry recovery/refetch an toàn. Không hoàn quota đã dispatch. Nút Kiểm tra lại dùng cùng action, không tự cấp operation mới.
5. Với retry reject có key active: owner-bound lookup trước, recover rồi lookup lại dưới lock trước AI availability/busy handling. Nếu terminal thì trả Q02; nếu vẫn active thì busy. Không giữ session lock xuyên AI call. Nếu snapshot bị khóa bởi approve/shuffle thắng race, FE dùng routing tương ứng thay vì cố mở Review.

Bổ sung DTO recovery vào `models/schemas.py`, route và service adapter FE; status/error codes đi qua mapping repository/API hiện hữu. Mã lỗi mới phải có mapping/test rõ ràng, không để lỗi domain mới rơi về 500. Authentication không thay authorization.

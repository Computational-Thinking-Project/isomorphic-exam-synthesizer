# EXT-01 — Review & Targeted Regeneration

**M2 Implementation Plan · v1.2, hiệu chỉnh sau review ngày 26/11/2026 · proposed tại ranh giới liên task**

## 0. Thông tin và trạng thái

| Mục | Giá trị |
|---|---|
| Dự án | Isomorphic Exam Synthesizer — Nhóm 04 |
| Nguồn giao việc | `Ke-hoach-phan-cong-EXT-v3.1-final.md`, EXT v3.1 ngày 25/11/2026, mục 1, 3, 4, 5 |
| Phụ trách | Duy — EXT-01 và điều phối M1 |
| Reviewer / dự phòng | Đề xuất `@nhatquynh1107` (DB/ACL), `@AI-WFox` (AI/policy), `@benalexx007` (FE); chưa phân công chính thức; dự phòng TBD |
| Repository | [isomorphic-exam-synthesizer](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer) |
| Base đã kiểm | `dev@efed79b1662f63d1bc083eb147dc55421684ea16` |
| Baseline UI tham chiếu | `fix/stage3-ui@1072d1ceee8e126640b2d03a10545f94cac70475` — [PR #109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109) (đã merge ngày 26/11; merge commit `b29244346094811eaa038fd31fea67969f8f5b7f`) |
| Branch / PR dự kiến | `feat/ext-01-review` → `dev`; [Draft PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111); HEAD triển khai đang cập nhật |
| Workflow | [v0.1 proposed + INPUT-20261109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/7b7387f/docs/review/WORKFLOW.md); [M2 template trên baseline](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/TEMPLATES.md#m2) |
| Mốc đợt | M2/Draft PR 26/11; code từ 27/11; báo kết quả tối 01/12/2026 |
| ETA task | 29–45 giờ công trực tiếp, dự toán hiệu chỉnh chưa được Duy xác nhận; thời gian chờ input/review không nằm trong số này |
| Trạng thái | Draft PR #111 đã mở; G1 đủ thiết kế để bắt đầu; G0/G2–G5 còn pending. Môi trường local do chủ trì báo đã chuẩn bị, chưa được lượt hiệu chỉnh này kiểm runtime |

> Kiểm chứng ngày 26/11/2026: PR #109 đã merge, merge commit `b29244346094811eaa038fd31fea67969f8f5b7f`; PR #111 vẫn Draft (đã đăng [comment chốt Q04–Q08](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7181001101), đang chờ owner phản hồi). Các ID `V/R` là finding kế hoạch, không phải implementation đã đạt; chưa chạy product/DB/AI tests cho EXT-01 mới.

### 0.1. Điều kiện bắt đầu và thứ tự mở khóa

Plan này dùng để triển khai phần EXT-01 đã rõ; không thay xác nhận của owner cho contract liên task. Các phương án Q04–Q08 chưa là quyết định được owner phê duyệt. Giữ filename v1.2 để không phá đường dẫn PR; revision nội dung nhận diện bằng commit khi bàn giao.

| Gate | Công việc và tiêu chí đủ | Phần được mở khóa | Trạng thái tại lần hiệu chỉnh |
|---|---|---|---|
| G0 — Baseline | Bảo toàn working tree; đưa plan và nguồn phân công vào gói review chia sẻ được hoặc dẫn nguồn đã được owner xác nhận; đồng bộ nhánh với `dev` chứa merge #109; ghi integration HEAD và diff | Thay đổi UI dựa trên #109 và kết luận regression theo head mới | Chưa đồng bộ; không tự nhận SHA merge #109 là HEAD hiện tại của dev |
| G1 — Nội bộ | Q01–Q03 theo §3, gồm thứ tự owner check trước service-role recovery; fixture/unit test local | API reasons, receipt/replay, recovery, inline UI/navigation độc lập | Đủ thiết kế để bắt đầu; implementation/tests chưa thực hiện |
| G2 — Mode/policy | Tâm xác nhận Q04: frozen mode, phân biệt legacy/new snapshot, slot policy, mã lỗi và projection UI; bổ sung vào contract chuẩn | Guard mode/clone và tích hợp targeted policy | Pending owner confirmation |
| G3 — DB rollout | Quỳnh và các owner xác nhận Q05: số migration thực tế, thứ tự dependency, signature/ACL, deployment window, rehearsal và phương án phục hồi | Chốt migration để tích hợp/deploy; không chặn soạn migration local tên tạm | Pending owner confirmation |
| G4 — Consumer | Q06–Q08 được xác nhận; I-EXT-01 có full fixture + revision, consumer xác nhận phạm vi đủ dùng | Tích hợp Preview/Export/Delete/readiness liên task | Pending; ví dụ ở Phụ lục A chưa là fixture Delivered |
| G5 — Nghiệm thu | A01/A02 và checks áp dụng có evidence ở integration HEAD, reviewer độc lập, GitHub Approve/CI theo CONTRIBUTING | Ready/merge; deployment vẫn theo G3 | Chưa thực hiện |

Nếu G2–G4 chưa đạt: tiếp tục G1 với fixture có nhãn rõ, ghi blocker và ETA trên PR; không bật shuffle-only hoặc tuyên bố đã tích hợp các EXT. Không có quyền tự xác nhận thay owner hoặc tự đăng comment từ nội dung plan.

## 1. Mình cần làm gì?

### 1.1. Hành vi bắt buộc

- Hiển thị đáp án, lời giải và nút duyệt dưới từng câu; nếu thiếu lời giải, hiển thị “Chưa có lời giải”.
- Accept theo `candidate_id` hiện hành. Chỉ auto-advance sau accept thành công, đã đối soát server, và giáo viên vẫn ở đúng phiên/mã/câu, chưa tự điều hướng trong lúc chờ. Ưu tiên câu chưa duyệt trong cùng mã (kể cả câu đã bỏ qua), sau đó mã khác. Cho quay lại câu đã duyệt; không tự chuyển sang Preview.
- Reject nhận `reasons` tùy chọn, rỗng hoặc nhiều mã hợp lệ; chuẩn hóa tập lý do, lưu cùng operation, đưa vào targeted regeneration. Cùng key/tập reasons replay kết quả cũ; khác tập trả 409; receipt cũ thiếu reasons tương đương rỗng.
- Giữ blueprint, validator, quota, attempt permit, ownership, lock, current candidate và recovery hiện có. Candidate sinh lại phải được duyệt lại; revert theo điều kiện hợp lệ, bảo toàn đáp án/lời giải/provenance.
- Reload và lỗi phải đọc lại trạng thái server; có đường phục hồi operation hết hạn. Không dùng trạng thái optimistic làm nguồn sự thật.
- Preview chỉ mở khi toàn phiên đủ điều kiện theo server; phân biệt `reviewed` với `approved`.
- Bàn giao I-EXT-01 cho Tâm, Đạt, Quỳnh; chủ trì A01/A02, phối hợp A20; chốt F-019 trong M2.

### 1.2. Ngoài phạm vi

Không viết lại ReviewService, tạo ledger/queue/AI service/validator mới, lịch sử candidate dạng timeline, sửa câu hỏi thủ công, nhập prompt tự do, thống kê reasons, redesign Preview/Bank/Export, lưu vị trí xem trên DB hay thay framework quản lý state. EXT-02 sở hữu mode/reuse/shuffle; EXT-04 sở hữu Finalize/Bank/xóa draft; EXT-03 sở hữu Export/OMR. Chỉ sửa ranh giới cần thiết với các owner này.

## 2. Code thực tế và gap analysis (F-019)

Các link dưới đây ghim vào commit đã đọc; không ngụ ý code đã được deploy.

| Thành phần / bằng chứng | Đã có | Delta EXT-01 |
|---|---|---|
| [PR #109 / Stage3ReviewPage](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/1072d1c/frontend/src/features/stage3-review/Stage3ReviewPage.jsx) | So sánh nguồn–biến thể, dialog, focus, navigator, lưu vị trí `sessionStorage` | Inline đáp án/lời giải/accept; đổi thứ tự auto-advance; điều hướng trong lúc chờ; reconciliation |
| [Stage3InspectionDialog](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/1072d1c/frontend/src/features/stage3-review/Stage3InspectionDialog.jsx) | Dialog đáp án, lời giải, xác nhận regenerate/revert | Tái sử dụng confirmation, thêm reasons; không lặp nội dung inline |
| [review.py:80–109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/api/routes/review.py#L80-L109), [stage3Service.js:42–58](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/frontend/src/services/stage3Service.js#L42-L58) | Reject không body; client gửi null | Request schema, backward compatibility, reasons |
| [006:246–293](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/006_stage3_review_and_shuffle.sql#L246-L293), [006:448–515](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/006_stage3_review_and_shuffle.sql#L448-L515) | `review_operations`, `review_attempts`, `review_action_receipts`; lookup/reserve | Canonical reasons binding trên cả lookup/reserve; replay đúng payload |
| [006:545–675](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/006_stage3_review_and_shuffle.sql#L545-L675) | Complete/fail/recover, `completion_candidate`, `settlement_result` | Dùng dữ liệu đã lưu cho replay; recovery khi mở lại hoặc retry |
| [ReviewService](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/review/service.py), [ReviewRepository](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/review/repository.py) | Lifecycle và RPC adapter | Truyền reasons đã xác nhận, xử lý receipt/failure/recovery |
| [TargetedRegenerator](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/generation/targeted_service.py), [GenerationService](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/generation/service.py) | Frozen source, blueprint, validator, retry | Teacher feedback giữ qua mọi retry; kiểm ranh giới slot policy |
| [018:138–222](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/018_review_current_snapshot.sql#L138-L222) | Authoritative `_review_progress()` | FE dùng `progress.ready`; phối hợp EXT-02 |
| [021:644–1147](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/021_w4_confirmed_source_fallback.sql#L644-L1147) | Định nghĩa lại `get_review_current_snapshot`, thêm `confirmed_source_fallback`, dùng `_review_progress` | Đọc 021 thay vì chỉ 018 khi sửa snapshot; giữ provenance và post-shuffle/locked guards |
| [009](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/009_finalize_security_boundary.sql) | Finalize kiểm progress và transaction boundary | Không mở đường ghi ngoài contract; phối hợp EXT-04 |
| [024:345–548](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/024_source_reuse_optional_solutions.sql#L345-L548) | Revert frozen-source tạo candidate pending; hỗ trợ placeholder lời giải | Giữ contract, kiểm legacy và Export |
| [026](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/026_per_question_generation_policy.sql) | Per-question generation policy | Chốt tác động tới targeted regeneration với Tâm |

**Gate baseline:** #109 đã merge tại `b29244346094811eaa038fd31fea67969f8f5b7f`, head FE tham chiếu vẫn là `1072d1c`. Nhánh local `feat/ext-01-review@880d9d7` chứa plan trên nền `efed79b`, chưa chứa baseline UI mới. Trước sửa UI, lưu thay đổi hiện có theo quyền, cập nhật refs rồi merge/rebase dev theo workflow; giải quyết conflict mà không ghi đè công việc khác, ghi integration HEAD và kiểm diff Stage 3. Không checkout/reset cưỡng bức. Các line reference ghim `1072d1c`/`efed79b` phải được đối chiếu lại ở head tích hợp. Nhánh workflow-stabilization cũ không dùng làm baseline.

## 3. File và thứ tự triển khai từ thứ Sáu

| Lượt | File dự kiến (đường dẫn tương đối từ root) | Output | Input / cách kiểm |
|---|---|---|---|
| 1 — API | `backend/app/models/schemas.py`, `backend/app/api/routes/review.py` | Optional reasons, enum, 422, caller cũ | Chốt Q01; API tests |
| 2 — DB | `backend/migrations/<next>_ext01_review_reasons.sql` (tên/số TBD), `backend/app/services/review/{repository,receipts,service}.py` | Durable reasons, lookup/reserve, replay | Chốt Q01/Q02/Q03/Q05; PG thật; cả lookup nội bộ, reserve retry và completion projection |
| 3 — AI | `backend/app/services/generation/{targeted_service,service,prompts}.py` | Feedback immutable theo operation, retry | Chốt Q04; AI regression, không đổi fingerprint Stage 2 |
| 4 — Recovery | `backend/app/services/review/{service,repository}.py`, `backend/app/api/routes/review.py` nếu cần | Reconcile active/expired, retry đúng key | Chốt Q03; worker crash/expiry test |
| 5 — UI | `frontend/src/features/stage3-review/{Stage3ReviewPage,Stage3Comparison,Stage3InspectionDialog,Stage3ReviewNotifications}.jsx`, `stage3Review.css`, `frontend/src/services/stage3Service.js` | Inline review, reasons, navigation, snapshot | PR #109 baseline + contract; FE tests |
| 6 — Readiness/revert | Cùng các file Review, chỉ thêm migration/adapter nếu chứng minh cần | Gate server, đúng provenance và answer | I-EXT-01; A01/A02; phối hợp EXT-02/03/04 |
| 6b — Consumer integration (sau G4) | `backend/app/services/exporter/{snapshot_reader,snapshot_provenance}.py`, `backend/app/services/finalize/repository.py`; renderer/Preview nếu contract hiển thị đổi | R09 đầy đủ qua reader/classifier/verifier; giữ quyền owner EXT-03/04 | §3.6.1; A02-28, Preview/Export tests và artifact thật |
| 7 — Evidence | Tests hiện hữu, `docs/api/review-rpc-contract.md`, `docs/api/review-snapshot.md` (nếu đổi), `docs/ai-w3-targeted-regeneration.md` (nếu đổi), `docs/change_log.md`, file task | Contract chuẩn, evidence, bàn giao | CI, isolated PG, live integration theo khả năng |

### 3.1. Reject API contract (V01, V09)

Giữ endpoint `POST /api/sessions/{session_id}/questions/{version_question_id}/reject` và header `Idempotency-Key`. `version_question_id` là current candidate ID, không phải số câu. Giữ response `RegeneratedQuestionResponse` hiện hành nếu không có lý do cần đổi.

```json
{"reasons": ["MULTIPLE_CORRECT_ANSWERS", "DIFFICULTY_MISMATCH"]}
```

Reason codes đề xuất, Duy chốt tại M2:

| Code | Nhãn |
|---|---|
| `INCORRECT_ANSWER` | Đáp án không chính xác |
| `NO_CORRECT_ANSWER` | Không có phương án đúng |
| `MULTIPLE_CORRECT_ANSWERS` | Có nhiều phương án đúng |
| `EQUIVALENT_OPTIONS` | Phương án tương đương |
| `INVALID_QUESTION` | Nội dung đề bài sai |
| `ISOMORPHISM_MISMATCH` | Không đảm bảo tính đẳng cấu |
| `DIFFICULTY_MISMATCH` | Mức độ khó không tương đương |
| `INCORRECT_SOLUTION` | Lời giải không chính xác |

- Không body, body null (caller MVP), `{}`, `{"reasons": []}`: tương đương tập rỗng.
- Mảng hợp lệ: sort + deduplicate, không phân biệt thứ tự; mã enum phân biệt hoa/thường. Mã lạ, sai kiểu, field lạ, body top-level array (kể cả `[]`), scalar hoặc JSON không hợp lệ: 422 trước AI/quota/operation write. `reasons: null` trả 422 theo Q01; không coercion chuỗi thành list.
- Không thêm free text hoặc endpoint quản lý reason codes. Không đổi policy header optional của MVP nếu chưa được thống nhất.

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

Kiểm kê callers bằng search toàn repo (bao gồm tests/mocks/docs), RPC overloads, ACL và PostgREST trước khi viết migration. Theo phương án đề xuất Q05 (chỉ deploy sau G3 ở §0.1), chọn rollout **đồng bộ DB/backend/FE có maintenance window ngắn**: dừng nhận operation mới, cho operation active settle hoặc recover đúng lease, `DROP` chữ ký 3 tham số `review_lookup_regeneration` / `review_reserve_regeneration` và giữ 1 chữ ký 4 tham số duy nhất (không `DEFAULT` để tránh `PGRST203` & bypass), `NOTIFY pgrst, 'reload schema'`, smoke rồi mở FE. Test quyền `authenticated`/`anon`/`service_role`. Không chạy DDL shared DB khi chưa có deployment gate. Slot migration đề xuất `028`, phối hợp Quỳnh/Tâm/Đạt.

### 3.2.1. Migration và kế hoạch phục hồi triển khai

- Trước DDL, kiểm inventory thực tế ở integration HEAD, applied ledger của môi trường đích, mọi overload và grants; `028–031` chỉ là số đề xuất, không được chiếm số đã có. Phần guard mode phụ thuộc G2 và schema EXT-02: nếu schema/helper chỉ xuất hiện sau migration Review thì tách guard sang migration kế tiếp hoặc đổi thứ tự được owner xác nhận. Không phát hành guard tham chiếu cột chưa tồn tại, cũng không âm thầm bỏ guard khi thiếu schema.
- DDL trong transaction: thay signature, cập nhật mọi SQL caller phụ thuộc, projection receipt, REVOKE/GRANT rõ ràng cho signature mới. Không dùng DROP CASCADE để giải quyết dependency. Parser mới đọc receipt cũ vắng reasons là `[]`; receipt malformed phải fail closed. Giữ owner/member check trước trả receipt, replay trước guard của operation mới.
- Maintenance áp dụng cho mọi entry point có thể tạo Review operation, kể cả caller trực tiếp có quyền RPC; không chỉ ẩn nút FE. Drain operation active hoặc recover đúng DB lease; không cưỡng bức complete/fail operation chưa hết hạn. Deploy backend/DB tương thích trong cửa sổ này, reload PostgREST schema rồi smoke HTTP/RPC trước mở lại traffic.
- Rehearsal trên DB disposable gồm fresh chain và populated legacy receipts. Lưu migration list, signature/grants trước/sau, row counts, quota và receipt identity. Triển khai thật chỉ sau gate môi trường đã được cấp quyền; không lấy DB test pass làm bằng chứng DB shared đã áp.
- Nếu DDL lỗi: transaction rollback, giữ maintenance và kiểm schema trước retry. Nếu backend/smoke lỗi sau DDL commit: giữ maintenance, ưu tiên roll-forward bản backend tương thích signature mới. Không rollback riêng backend sang caller 3 tham số hoặc xóa reasons/receipt đã ghi. Khôi phục backup chỉ theo phương án owner triển khai đã xác nhận và có rehearsal; plan không cấp quyền restore/xóa dữ liệu shared.


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

### 3.3.1. Recovery authorization và kết quả lỗi

Endpoint recovery mới là mutation, không chỉ một snapshot read. `session_lock_registry` chỉ giảm cạnh tranh trong process; DB session lock là authority giữa workers.

1. Parse UUID, authenticate caller; xác minh owner bằng RLS-bound repository trước mọi lời gọi service-role. `recover_stale_operations()` hiện gọi worker RPC, tự nó không chứng minh caller sở hữu session. Non-owner/not-found trả lỗi theo API contract hiện hành, không tiết lộ receipt/count.
2. Kiểm editability/post-shuffle theo owner snapshot/guards trước recovery; giữ logic guard trong DB để tránh race. Không chỉ gọi recovery rồi mới dựa vào snapshot để từ chối caller. Nếu cần wrapper DB cho owner check + recovery nguyên tử, thống nhất signature/ACL trong Q05, vẫn tái sử dụng settlement hiện hữu.
3. Dưới local lock, gọi recovery; RPC dùng DB clock và parent-first lock. Đọc lại owner snapshot sau mutation, derive `has_active_operation` từ trạng thái `regenerating` của snapshot đó. Đây là quan sát tại thời điểm đọc, không cam kết không có request khác xuất hiện sau response.
4. Nếu recovery đã commit nhưng snapshot read lỗi, trả lỗi unavailable theo mapping API, không dựng snapshot giả; FE giữ sync-required và retry recovery/refetch an toàn. Không hoàn quota đã dispatch. Nút Kiểm tra lại dùng cùng action, không tự cấp operation mới.
5. Với retry reject có key active: owner-bound lookup trước, recover rồi lookup lại dưới lock trước AI availability/busy handling. Nếu terminal thì trả Q02; nếu vẫn active thì busy. Không giữ session lock xuyên AI call. Nếu snapshot bị khóa bởi approve/shuffle thắng race, FE dùng routing tương ứng thay vì cố mở Review.

Bổ sung DTO recovery vào `models/schemas.py`, route và service adapter FE; status/error codes đi qua mapping repository/API hiện hữu. Mã lỗi mới phải có mapping/test rõ ràng, không để lỗi domain mới rơi về 500. Authentication không thay authorization.


### 3.4. Targeted AI feedback (V01, V06)

```text
HTTP validate → lookup/reserve → validated reservation
    → frozen_inputs + persisted reasons
    → TargetedRegenerator → GenerationService.regenerate_from_snapshots
    → _generate → build_prompt → Gemini → CandidateValidator
    → complete/fail → refetch snapshot
```

- Mapping mã lý do thành feedback cố định phía server. Reason codes là bắt buộc; đưa thêm rejected candidate từ frozen inputs chỉ khi test chứng minh cần, không ép thành `GeneratedQuestion` giả. Nếu dùng, giữ riêng evidence cố định; `previous_payload` động dành cho candidate do validator/solution repair xử lý, không ghi đè bằng câu giáo viên đã reject (R12).
- Giữ teacher feedback xuyên suốt operation. `_generate()` hiện ghi đè `feedback` khi schema/validator lỗi; hợp nhất teacher feedback cố định với feedback động mỗi lần build prompt. Có thể tận dụng `feedback` hiện hữu, không bắt buộc thêm cấu trúc prompt nếu không cần.
- Blueprint/invariants/validator/duplicate checks không bị nới lỏng. Không cam kết AI khắc phục hoàn toàn mọi lý do hoặc chứng minh độ khó tương đương.
- Giữ durable permit, tối đa 4 calls, timeout hiện tại targeted 40s / review 45s / FE reject 60s, trừ khi có bằng chứng cần đổi. **Không bump `PROMPT_VERSION` dùng chung** chỉ vì thêm teacher feedback targeted. `_request_fingerprint` (service.py:77–84) chứa version, resume so sánh fingerprint (322–330); đổi version/identity chung có thể gây `RESUME_MISMATCH` trên job Stage 2 cũ. Truyền feedback tùy chọn chỉ cho targeted path, giữ prompt mặc định/fingerprint cũ khi không dùng feature. Nếu buộc đổi identity chung phải thống nhất compatibility với Tâm và có regression resume job cũ (R03).
- `regenerate_from_snapshots()` hiện truyền `variation_modes=[]`; phối hợp Tâm xác định policy frozen slot nào được áp dụng cho targeted regeneration. Không suy `shuffle_only` từ variation rỗng hoặc candidate origin. AI mode vẫn yêu cầu Accept cho mọi AI/clone/fallback candidate. Test frozen per-slot policy và legacy mode mặc định `ai_generation`; mode/policy do Tâm sở hữu, không tự tạo nguồn cấu hình thứ hai (R07).
- Với `shuffle_only`, reject/regen phải bị chặn ở backend/DB trước reserve/AI. Không thay semantics replay của operation đã tồn tại tùy tiện. Tâm sở hữu generation mode và verified clone transition; Duy sở hữu Review guard tương ứng. Revert trong shuffle-only đề xuất không mở; cần chốt Q04.

### 3.4.1. Contract mode/policy cần Tâm xác nhận (G2)

- Khi có frozen job snapshot: Review resolve snapshot thuộc đúng session/current candidate; dùng mode đã khóa khi claim, không đọc live config làm nguồn quyết định duy nhất. Nếu config và snapshot không khớp, từ chối operation mới bằng lỗi conflict đã thống nhất, không gọi AI/giữ quota. Replay operation cũ cùng binding vẫn theo Q02.
- Legacy: chỉ fallback `ai_generation` khi evidence xác định snapshot thuộc schema trước EXT-02. Tâm cần giao marker/version hoặc quy tắc nhận diện legacy đủ kiểm được, cùng vị trí frozen `generation_mode`. Chưa có bằng chứng phân biệt legacy/new thì chưa bật feature mode. Snapshot mới thiếu/null/mã mode lạ phải fail closed. Không sửa snapshot lịch sử để hợp thức hóa mode.
- Với `mapping_version='1.1'`: derive `canonical_dimensions` từ frozen canonical blueprint của source, đối chiếu `question_policies[source_question_id]` trong job snapshot theo semantics `_generation_question_policy`/`_generation_is_clone` của 026. Policy thiếu/sai hoặc source binding sai phải conflict trước reserve. Với `1.0`/legacy artifact: dùng contract frozen cũ, không tự áp policy 1.1 lên job cũ; Tâm xác nhận ca tương thích và fixture.
- `values`/`context` là dimensions đưa vào `_prepare` và `_generate` của `GenerationService.regenerate_from_snapshots`; không truyền public aliases như `NUMERICAL`. Thêm tham số tùy chọn cho targeted path, cập nhật adapter/mocks; stage-2 default và fingerprint không đổi. Việc suy policy và teacher feedback phải đi qua validated reservation/frozen evidence, không tin body FE.
- Shuffle-only: chặn reject/revert mới trước reserve/AI. AI mode slot clone-only: đề xuất chặn reject mới, vẫn Accept/Revert theo guard hiện hữu; đây là thay đổi hành vi cần owner xác nhận, không suy permission chỉ từ origin. UI nhận mode/capability từ server theo DTO được chốt (hoặc adapter từ evidence đã công bố), không tự tái dựng policy từ label/variation rỗng. Chốt field chính xác và fixture trong `review-snapshot.md` trước nối FE; backend/DB vẫn enforce khi gọi trực tiếp.
- Bàn giao G2 gồm: nơi lưu frozen mode, legacy discriminator, mapping policy 1.0/1.1, DTO UI, error mapping, migration dependency và test fixture cho từng nhánh. Nếu chưa giao đủ, chỉ triển khai phần targeted reasons độc lập; chưa bật guard mới với quy tắc giả định.


### 3.5. Inline Review, auto-advance và state (V04, V07)

Tận dụng `Stage3Comparison`, `ReviewQuestionContent`, `Stage3ReviewNotifications`, `MathRenderer`, CSS, focus và confirmation dialog từ PR #109. Đáp án/lời giải/Accept hiển thị inline dưới câu; dialog dành cho chọn reasons và xác nhận sinh lại/hoàn nguyên. Không cần redesign cả workspace. Giữ API service `rejectAndRegenerateQuestion(sessionId, questionId, key, config)`; đề xuất thêm reasons trong options/config được destructure tách khỏi Axios config hoặc tham số bổ sung tương thích, không thay ý nghĩa tham số thứ tư; kiểm mọi caller (R11).

- Snapshot authoritative quyết định nội dung, candidate identity, trạng thái duyệt và readiness. Sau mutation success **hoặc lỗi**, refetch qua cơ chế read epoch chung; nếu thất bại hoặc kết quả chưa nhất quán, báo cần đồng bộ và khóa mutation/Preview. Nếu accept báo lỗi nhưng snapshot sau đó đã approved, hiển thị đúng server nhưng không auto-advance. Không ghi đè snapshot bằng response cũ (`732-742`), không merge `approvedVariantIds` cũ vào tập authoritative (`757-764`), không giữ fallback `correct_key: s.correct_key || 'A'` ở `adaptReviewSnapshot` (`stage3Service.js:170`), và không dựa vào `res?.has_warning` / `res?.is_fallback` từ `RegeneratedQuestionResponse` (vốn không có trong schema) thay cho snapshot sau refetch.
- Derive candidate đang xem từ snapshot và tọa độ phiên/mã/câu; tránh giữ nhiều bản sao cạnh tranh (`session`, `selectedSolution`, `approvedVariantIds`). Chỉ refactor state/handler liên quan trực tiếp, không viết lại toàn bộ trang.
- Dùng `candidate_id` cho mutation; dùng `version_id`/version index và source question identity cho điều hướng theo contract. Guard mounted, session generation/identity (kể cả A→B→A), mutation token; dùng một cơ chế read epoch chung cho initial load, refetch/reconcile cùng session hoặc tuần tự hóa đọc. Không cho request bắt đầu trước mutation/refetch mới ghi đè snapshot mới. `freshness_token` là hash, không phải thứ tự tăng dần. Test hai response cùng session về sai thứ tự (R08).
- Cho đổi mã/câu/session trong lúc chờ Accept (cả click và keyboard — gỡ khóa `isApprovingSingle` ở `Stage3ReviewPage.jsx:1056, 1089, 1364, 1394`); chỉ khóa mutation xung đột trên slot đích. Đặt Accept inline, không phụ thuộc modal giữ focus/khóa navigator. Ghi nhận `navigationEpoch` khi gửi accept và tăng mỗi lần người dùng chủ động điều hướng. Chỉ auto-advance nếu epoch, session và cặp mã/câu chưa đổi, snapshot xác nhận candidate đích đã approved. Tránh ghi đè candidate mới đang xem dù chỉ khác mã/câu trong cùng session.
- Dùng một helper nhỏ `findNextUnreviewed` cho auto-advance và điều hướng chủ động (thay vòng lặp question-major `(qNo - 1) * versions + versionIndex` ở `771-777`): tìm câu chưa duyệt phía sau trong mã hiện tại; vòng lại câu đã bỏ qua cùng mã; sau đó chuyển mã khác theo thứ tự ổn định. Bỏ qua slot không có candidate để duyệt, hiển thị recovery nếu còn slot thiếu. Không auto-advance khi lỗi, reload, read-only hoặc khi không xác nhận được trạng thái. Khi không còn câu cần duyệt, focus Preview nếu readiness hợp lệ; không tự điều hướng sang Preview.
- Hỗ trợ `pending_review`, `approved`, `rejected`, `regenerating`, `candidate: null` và `read_only`. `origin`, `is_reverted`, `has_warning`, validation report chỉ là evidence; không tạo FE business validator thay backend.
- Giữ hỗ trợ bàn phím/focus và MathRenderer. Vị trí xem lưu client là tiện ích, không phải business state; server quyết định tiến độ. Xác minh tab/session reload, deep link, trạng thái post-shuffle và khóa approved/exported theo routing contract hiện hành.

**Readiness gate:** dùng `snapshot.progress.ready === true`, session `reviewed` và các UI guard hiện hành (không busy, không read-only, không đang cần reconcile). Không suy readiness từ số câu duyệt. Trạng thái post-shuffle dùng API Preview tương ứng; không ép review snapshot đọc được sau shuffle.

`ReviewSnapshotProgress` hiện chỉ có `expected_slots`, `current_slots`, `approved_slots`, `missing_slots`, `ready`. `regenerating_slots` và `duplicate_slots` thuộc `/review/progress`, không tự thêm vào `/review/snapshot` chỉ để FE kiểm lại business rule.

### 3.6. Revert và nguồn thiếu lời giải (V08)

Migration 024 `_review_apply_action` đã kiểm frozen source, source revision, blueprint, source hash; tạo candidate mới `pending_review`, giữ đáp án/lời giải và provenance. Tái sử dụng đường này, không viết lại. Lưu ý PR #109 (`Stage3ReviewPage.jsx:1576`) hiện khóa `canRevert` theo `session?.confirmation_id && session?.job_snapshot_id`, cần mở điều kiện hợp lệ cho nhánh `legacy_root` (`NOT has_conf AND NOT has_job`) sau khi chốt phạm vi; không đổi ngữ nghĩa auto-approve legacy nếu chưa chốt contract với consumer.

Nguồn thiếu lời giải hiện có thể được biểu diễn bằng null/rỗng ở nguồn hoặc placeholder `Không có lời giải cho câu hỏi này.` ở candidate (`024`/`026`). Cần sửa kiểm tra truthiness tại `Stage3InspectionDialog.jsx:66` (và khối lời giải inline mới) để chuẩn hóa hiển thị `"Chưa có lời giải"` khi gặp `null`, chuỗi rỗng hoặc chính chuỗi placeholder đó, không hiểu placeholder là lời giải toán học. Không tự sinh lời giải khi revert; không tự đổi placeholder thành null nếu chưa thống nhất Q06 vì Preview/Export kiểm provenance cho lời giải rỗng.

R09: migration 026:351–382 clone mới dùng placeholder, nhưng tương thích replay `legacy_expected` với solution null. Export `verified_empty_solution` hiện kiểm `active_variation_modes`, `canonical_dimensions`, `public_modes` rỗng ở cấp session khi origin là clone. Mixed-policy AI mode có clone legacy null có thể không thỏa; đây là rủi ro tĩnh, không kết luận lỗi production. Kiểm riêng AI-generated/regenerated có lời giải, clone/fallback/reverted thiếu nguồn và legacy clone null/rỗng trong mixed policy. Chỉ sửa adapter thuộc owner Đạt nếu test xác nhận blocker; không tự nới provenance hoặc backfill solution hàng loạt.

Đọc [snapshot_provenance.py](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/exporter/snapshot_provenance.py) và [snapshot_builder.py](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/exporter/snapshot_builder.py) cùng Đạt; xác minh key/solution sau shuffle, Preview và Export. Nếu contract thiếu bằng chứng để phân biệt lời giải thiếu, chốt thay đổi tối thiểu trước khi code.

### 3.6.1. R09 — Thực hiện đầy đủ Preview/Export provenance (G4)

Đây là kế hoạch phối hợp EXT-03/04, không cấp quyền Duy tự sửa nhánh owner. Scope sửa chỉ được mở khi fixture tái hiện case và owner xác nhận. Giữ nhánh fallback/reverted hiện hữu, không dùng exception clone cho AI-generated/regenerated thiếu solution.

| Lớp / file | Thay đổi cần có | Tiêu chí kiểm |
|---|---|---|
| Export `snapshot_reader.py` | Mở rộng projection `generation_job_snapshots` có `mapping_version` và phần `snapshot_payload` cần cho frozen source/policy. Giữ giới hạn truy vấn theo session và snapshot IDs từ ledger của question đã được RLS-authorized | Reader thật đưa đủ evidence vào `RawSnapshotRows`; không chỉ truyền fixture giàu dữ liệu thẳng vào helper |
| Export `snapshot_provenance.py` | Tách xác minh legacy 1.0 và per-slot 1.1; bỏ điều kiện config toàn phiên rỗng chỉ cho nhánh 1.1 có evidence hợp lệ | Mixed-policy clone null hợp lệ đi qua; AI-result hoặc policy sai không được miễn solution |
| Finalize `repository.py`: `_fetch_provenance_ledger` | Lấy cùng projection frozen evidence như Export; giữ kiểm duplicate ledger/snapshot identity | Không có lỗi do SELECT thiếu field dù helper unit test pass |
| Finalize `_classify_empty_solution_kind` và call sites | Không loại clone 1.1 chỉ vì `_is_original_clone_config(config_row)` false. Cho bước phân loại sử dụng ledger/snapshot đã xác minh, hoặc candidate classification tạm luôn qua verifier bắt buộc trước chấp nhận | Mixed-policy đi tới verifier; chưa đủ evidence không được chấp nhận Preview |
| Finalize `_is_valid_ledger_entry` | Nhánh clone 1.1 dùng per-source policy; 1.0 giữ semantics cũ; unknown/malformed version fail closed | Preview và Export cùng chấp nhận/từ chối một bộ evidence |

Verifier phải giữ: đúng một successful ledger entry, session/source/question/snapshot binding, result_kind clone, fingerprint shape, warning/report phù hợp, không regenerated; riêng 1.1 kiểm policy đầy đủ (kind + dimensions), khớp frozen blueprint theo 026, không chỉ kiểm string `ORIGINAL_CLONE`. Không nới provenance bằng config live hoặc HTTP payload. Snapshot version/policy thiếu hoặc không biết trả lỗi domain hiện hành, không mặc định thành clone. Với 1.0 giữ các invariant legacy đã có; không giả lập 1.1 cho receipt cũ.

Fixture positive: job 1.1 mixed-policy có một clone thiếu solution và một AI slot có solution; legacy 1.0 clone; clone/source có solution; confirmed fallback/reverted theo contract hiện hữu. Fixture negative: thiếu projection/policy, policy lệch blueprint, sai source/session/snapshot, duplicate ledger, fingerprint sai, AI_RESULT giả clone, regenerated thiếu solution. Test qua reader/repository → Preview/Export builder, sau đó kiểm artifact thực ở A02-24. Nếu không có dữ liệu hợp lệ tái hiện legacy-null/1.1, ghi đây là compatibility fixture và không tuyên bố lỗi production.


## 4. Đầu vào và câu hỏi — giải đáp trên Draft PR

Nơi tổng hợp input duy nhất: bảng M2 dưới đây (sau khi tạo PR có thể chuyển sang comment tổng hợp và dẫn link). Các ETA dưới đây là đề xuất; ETA được owner xác nhận vẫn là TBD. Không coi im lặng hoặc PR merge là consumer acceptance.

| ID / nguồn | Provider → Consumer | Điều kiện đủ dùng | Need-by / ETA | Mức hiện tại / bước tiếp |
|---|---|---|---|---|
| I-EXT-01 (EXT v3.1 §1) | Duy → Tâm, Đạt, Quỳnh | Contract current candidate, accept/revert, readiness, missing solution và fixture đúng schema; sau đó evidence từ DB/API thật | Contract 26/11; code/evidence dự kiến 30/11; ETA xác nhận TBD | Requested theo phân công; cần consumer xác nhận |
| I-EXT-02 (EXT v3.1 §1) | Quỳnh → Tâm, Đạt | Mẫu nguồn/đích, metadata nullable, receipt/snapshot, miền và sức chứa mã sản phẩm, cặp ID/mã của hai lượt; Duy cần phối hợp migration/session lock cho Review | Contract 26/11; ETA TBD | Theo M1; không đổi owner hoặc ranh giới input |
| I-EXT-03 (EXT v3.1 §1) | Tâm → Quỳnh, Đạt | Canonical source, trạng thái mở lại, projection hậu shuffle có đáp án/lời giải; Duy cần mode guard/slot policy thống nhất với Tâm | Quyết định 26–27/11; ETA TBD | Theo M1; cần thống nhất điểm nối Review |
| I-EXT-04 (EXT v3.1 §1) | Đạt → Quỳnh | Tập con mã/số câu OMR đã kiểm; miền mã sản phẩm từ I-EXT-02 | Trước mở OMR; ETA TBD | Không chặn EXT-01 |
| I-EXT-05 (EXT v3.1 §1) | Đạt/Bội Anh ↔ Hùng/Quỳnh | ID lượt, tải đáp án riêng, contract gói cũ/mới, key và reload | Contract 26–27/11; ETA TBD | Không mở rộng nhiệm vụ Duy ngoài điều phối/điểm nối |

### 4.1. Phương án chốt đề xuất (chỉ cần xác nhận đồng ý / chỉnh điểm bất đồng)

Thay vì liệt kê phương án mở, dưới đây là **một phương án triển khai cụ thể** cho từng điểm `Q01–Q08`. Nhóm `Q01–Q03` thuộc nội bộ EXT-01 (Duy chốt và triển khai từ 27/11); nhóm `Q04–Q08` chạm ranh giới liên task — các owner liên quan chỉ cần xác nhận **“Chốt”** trên [Draft PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111) hoặc báo rõ điểm cần đổi.

| ID | Chủ trì ↔ Phối hợp | Thiết kế triển khai; điểm liên task chỉ mở sau gate tương ứng |
|---|---|---|
| **Q01** | Duy (nội bộ EXT-01) | • DTO `RejectQuestionRequest`: `{ "reasons"?: ReviewReasonCode[] }` (`extra="forbid"`).<br>• Allowlist đúng 8 mã uppercase ở §3.1.<br>• No body / `null` / `{}` / `{"reasons": []}` → `[]`; body top-level `[]`, field lạ, `{"reasons": null}`, sai kiểu phần tử hoặc mã lạ → `422` trước DB/AI.<br>• Chuẩn hóa `sorted(set(reasons))`; giữ header `Idempotency-Key` optional tương thích MVP (UI mới luôn gửi key). |
| **Q02** | Duy (nội bộ EXT-01) | • `completed` cùng key + cùng canonical `reasons`: dựng `RegeneratedQuestionResponse` từ `completion_candidate` (`content = stem_latex`, `options`, `correct_key`, `solution_md`, `validation_report`) + `settlement_result` (`question_id`, `regenerated_from_id = previous_question_id`, `status = "pending_review"`), không đọc live `version_questions`.<br>• `failed` hoặc `recovered` cùng key + cùng `reasons`: trả `409 ERR_OPERATION_FINISHED` (FE tạo `Idempotency-Key` mới cho lần reject sau và refetch snapshot).<br>• Cùng key nhưng khác `canonical_reasons`: trả `409 ERR_ATTEMPT_REPLAYED` (map từ SQL `REVIEW_IDEMPOTENCY_CONFLICT` tại `repository.py:65–68`). |
| **Q03** | Duy (nội bộ EXT-01) | • Thêm endpoint `POST /api/sessions/{session_id}/review/recover` (owner auth + `session_lock_registry`), gọi `recover_stale_operations(session_id)` → `get_current_snapshot(session_id)` (giữ nguyên các guard `409 REVIEW_NOT_READY` / `423 REVIEW_LOCKED` / `409 REVIEW_POST_SHUFFLE_LOCKED` của `021`), trả HTTP `200`:<br>  `{ "recovered_count": int, "has_active_operation": bool, "snapshot": ReviewSnapshotResponse }` (`has_active_operation` = còn slot `status == "regenerating"`).<br>• Thứ tự trong `reject_question`: khi `lookup_regeneration(reasons)` trả `operation_status == "active"`, chạy `recover_stale_operations` dưới lock **trước** `if self.ai_generator is None:` và trước `409 ERR_QUESTION_BUSY`, rồi lookup lại theo `reasons`.<br>• FE mở snapshot thấy slot `regenerating` mà không giữ key active trong tab → gọi `/recover` 1 lần; nếu `has_active_operation == true` (còn hạn 180s), hiện trạng thái đang xử lý + nút **Kiểm tra lại**. `GET /review/snapshot` và `GET /review/progress` giữ nguyên read-only. |
| **Q04** | Duy ↔ **`@AI-WFox`** (Tâm) | • **Chế độ `shuffle_only`:** Chặn cả `reject` và `revert` ngay tại DB RPC (`409 ERR_MODE_SHUFFLE_ONLY`), ẩn/disable hai nút này trên UI. Nguồn authoritative là mode trong frozen job snapshot khi claim (EXT v3.1 §3), không chỉ live `generation_configs`. Áp dụng contract §3.4.1; Tâm xác nhận vị trí/schema và marker legacy/new trước tích hợp. Không dùng `COALESCE` chung để biến snapshot mới bị thiếu mode thành AI mode.<br>• **Chế độ `ai_generation` (kể cả `026` mixed-policy):** `TargetedRegenerator` bỏ hardcode `variation_modes=[]`, rút chiều biến đổi (`values`, `context`) từ frozen `blueprint` của chính slot đó theo `_generation_question_policy` (`026:35-38`).<br>• **Slot `ORIGINAL_CLONE` trong `ai_generation` mixed-policy:** Chặn `reject` trên slot có `canonical_dimensions == []` (`409 ERR_SLOT_POLICY_CLONE_ONLY`), chỉ cho `Accept` hoặc `Revert` (vì blueprint không mở chiều biến đổi để AI sinh câu mới khác đề gốc). |
| **Q05** | **`@nhatquynh1107`** ↔ Duy, `@AI-WFox`, `@Thanhdat3010` | • Số migration đề xuất, phải kiểm inventory và dependency theo §3.2.1 trước chốt: `028` (EXT-01 Review reasons/guard/recover), `029` (EXT-02 Reuse/mode/1–20/shuffle), `030` (EXT-04 Bank/Finalize/Public codes/Delete lock/Backfill), `031` (EXT-03 Export ledger v2).<br>• Deploy `028`: maintenance window ngắn, `DROP` chữ ký 3 tham số `review_lookup_regeneration` / `review_reserve_regeneration`, thay bằng **1 chữ ký 4 tham số duy nhất (không `DEFAULT`)** để tránh PostgREST overload `PGRST203` và chặn caller cũ bypass reasons; chạy `NOTIFY pgrst, 'reload schema'`. |
| **Q06** | **`@Thanhdat3010`**, **`@htbaax`** ↔ Duy, `@AI-WFox`, `@nhatquynh1107` | • **DB:** Giữ nguyên chuỗi `'Không có lời giải cho câu hỏi này.'` cho revert/clone thiếu lời giải (`024`/`026`) để không phá provenance rỗng tại Finalize/Export.<br>• **Review UI (`EXT-01`):** `null`, `""`, và đúng chuỗi `'Không có lời giải cho câu hỏi này.'` đều hiển thị `"Chưa có lời giải"`.<br>• **Preview & Export (`EXT-03`/`04`):** `Stage3PreviewPage` và exporter (`typst_compiler.py`, `source_renderer.py`) đối chiếu đúng chuỗi placeholder đó để hiển thị `"Chưa có lời giải"` (thống nhất chữ với Review).<br>• **Fix R09:** triển khai đầy đủ reader → classifier → provenance → Preview/Export theo §3.6.1. Export sửa `snapshot_reader.py` và `snapshot_provenance.py`; Finalize sửa `_classify_empty_solution_kind`, `_fetch_provenance_ledger`, `_is_valid_ledger_entry` cùng call sites. Không có hàm `verified_empty_solution` trong Finalize. Không chỉ thay một predicate hoặc nới kiểm tra session-wide mà bỏ evidence. |
| **Q07** | **`@nhatquynh1107`** ↔ Duy, `@AI-WFox` | • Chuyển `DELETE /sessions/{id}` sang RPC `delete_draft_session(p_session_id)`: khóa `exam_sessions ... FOR UPDATE` (cùng khóa root-first với Review/Job/Finalize), kiểm owner.<br>• Chặn `423` nếu `approved`/`exported`/`approved_at IS NOT NULL`; chặn `409` nếu `status='generating'` hoặc `active_job_id IS NOT NULL`.<br>• Tự dọn `review_operations` `active` đã hết hạn (`expires_at <= clock_timestamp()`) trong cùng transaction, chỉ chặn `409 ERR_REVIEW_OPERATION_ACTIVE` nếu còn operation `active` chưa hết hạn. |
| **Q08** | **`@benalexx007`**, **`@AI-WFox`** ↔ Duy | • Nút mở Preview chỉ enable khi `session.session_status === 'reviewed' && session.progress?.ready === true && !reviewSyncRequired && !hasActiveMutation`; không tự chuyển trang sang Preview, không cộng count client, không tự set `approved`.<br>• Giữ điều hướng/chặn sửa cho phiên đã post-shuffle / `approved` / `exported`. |

Duy triển khai `Q01–Q03` và phần FE nội bộ ngay sau khi đồng bộ PR #109; các điểm `Q04–Q08` cần xác nhận từ owner trước khi chốt PR/migration chung.

### 4.2. Output I-EXT-01

- Tâm: trạng thái candidate, server readiness, provenance, AI-mode review / shuffle-only guard.
- Quỳnh: điều kiện đủ `reviewed`, canonical snapshot sau accept/revert, active operation lock boundary.
- Đạt: ví dụ câu trước/sau regenerate/revert, answer key, solution, nguồn thiếu solution và provenance, hậu shuffle đúng mapping.

Tận dụng `backend/tests/fixtures/review_snapshot/` (`complete.json`, `partial.json`, `regenerated.json`, `clone.json`, `invalid_validation.json`); chỉ bổ sung fixture revert/missing-solution hoặc case khác còn thiếu. Fixture có ID thực tế hoặc ID giả hợp lệ, mapping source/candidate/version, options, key, solution và provenance khớp DTO; không tự tạo trường không có trong contract.

`complete.json` là đủ candidate sinh ra, **không phải đã duyệt đủ** (`approved_slots=0`, `ready=false`). Tạo fixture ready riêng hoặc chuyển trạng thái fixture bằng helper test. Các ví dụ transition ở Phụ lục A là trích contract để thảo luận, chưa phải full snapshot chạy được hay artifact Delivered.

Ví dụ **trích** `progress` của `/review/snapshot`, không phải full response:

```json
{
  "expected_slots": 2,
  "current_slots": 2,
  "approved_slots": 2,
  "missing_slots": 0,
  "ready": true
}
```

Bàn giao contract/fixture (Decided/Delivered) khác với tích hợp thật (Integrated). Mỗi consumer ghi Accepted theo phiên bản và phạm vi đủ dùng; sau đó bổ sung evidence DB/API thật. Dùng M2 và link PR thay vì nhiều bảng theo dõi trùng nhau.

## 5. Kế hoạch tự kiểm

### 5.1. Ma trận nghiệm thu A01 — Review UI và recovery

| ID | Ca kiểm | Kết quả mong đợi |
|---|---|---|
| A01-01 | 2 mã × 3 câu, accept C1 mã 101 | Sang C2 mã 101, không sang mã 102 trước khi hết câu chưa duyệt cùng mã |
| A01-02 | Bỏ qua C1, duyệt câu cuối cùng mã | Quay lại C1 trước khi đổi mã |
| A01-03 | Chuyển câu/mã/session trước response | Không auto-advance hoặc ghi đè candidate đang xem mới |
| A01-04 | Chuyển đi rồi quay lại vị trí cũ trước response | Epoch thay đổi, không auto-advance |
| A01-05 | Accept lỗi hoặc timeout; refetch lỗi | Không nhảy câu, đối soát server; khóa Preview nếu chưa sync |
| A01-06 | Accept trả success nhưng snapshot khác status/ID | Không ép status approved, không dùng approval ID cũ |
| A01-07 | Reload sau accept/reject/revert; quay lại câu đã duyệt | Server authoritative; vị trí xem chỉ là tiện ích |
| A01-08 | Tất cả local approved nhưng server ready=false; missing/active operation | Preview khóa; hiển thị tình trạng có thể phục hồi |
| A01-09 | ready=true, reviewed, không busy/sync issue | Cho mở Preview; không auto mở |
| A01-10 | Read-only, post-shuffle, approved/exported, deep link | Không ghi dữ liệu trái contract; route thích hợp |
| A01-11 | Inline answer/solution, thiếu lời giải, keyboard/focus/confirmation | Đúng candidate, đúng nhãn, không tạo validator FE |
| A01-12 | N=1/4, M=1/20; slot thiếu; điều hướng sau last | Không sai index, không lặp vô hạn, không nhảy sang slot không thể duyệt |
| A01-13 | Initial load/refetch cùng session trả sai thứ tự; A→B→A | Chỉ nhận read hợp lệ; không ghi đè snapshot mới |
| A01-14 | Accept error nhưng server đã commit; reload đang regenerating | Hiển thị server đúng, không auto-advance; reconcile theo Q03 |

### 5.2. Ma trận nghiệm thu A02 — Reasons, idempotency, AI và DB

| ID | Ca kiểm | Kết quả mong đợi |
|---|---|---|
| A02-01 | Không body/body null/`{}`/`{"reasons": []}` | Caller MVP tương thích; canonical reasons `[]` |
| A02-02 | Nhiều reasons; trùng/đảo thứ tự | Cùng tập canonical, lưu đúng |
| A02-03 | Mã lạ, sai kiểu, null theo Q01 | 422, không gọi AI/tạo operation/tăng quota |
| A02-04 | Cùng key/tập reasons; receipt lịch sử thiếu reasons | Replay đúng kết quả cũ; legacy rỗng |
| A02-05 | Cùng key, khác reasons ở lookup và reserve | 409; không phát sinh write/AI |
| A02-06 | Hai request cùng key đồng thời, cùng/khác tập | Chỉ operation hợp lệ dispatch; conflict đúng |
| A02-07 | Cross-owner/cross-session/candidate cũ | 404/409/423 theo contract; không truy cập trái quyền |
| A02-08 | RPC signature cũ và role trực tiếp | Không bypass reason binding hoặc RLS/ACL |
| A02-09 | AI prompt đầu tiên, retry schema/validator/solution repair | Teacher reasons được giữ; validator/blueprint không suy yếu |
| A02-10 | Duplicate candidate, timeout, cancel, quota 30, max 4 calls | Giữ prior candidate khi failure; đúng permit/settlement, không charge replay |
| A02-11 | Kill worker sau reserve, lease hết hạn; retry cùng key hoặc reload mất key | Recover prior status; không dispatch mới khi operation active; key mới sau terminal |
| A02-12 | Completed reject replay sau accept, regenerate tiếp, shuffle | Đúng kết quả operation cũ; không hồi sinh candidate lịch sử; UI refetch |
| A02-13 | Failed/recovered operation và retry mới | Không tái dùng key terminal vô hạn; theo Q02/Q03 |
| A02-14 | Regeneration thành công → accept mới | ID mới, pending_review, giữ mapping/answer/solution |
| A02-15 | Revert frozen source có/thiếu lời giải; accept lại | Đúng nguồn, key, provenance; pending_review; Preview/Export nhất quán |
| A02-16 | Shuffle-only reject trực tiếp | Chặn trước reserve/AI, không tăng quota; AI mode vẫn hoạt động |
| A02-17 | Migration fresh, DB populated có receipt cũ, chạy lại nếu quy trình yêu cầu | Không đổi ID, quota, receipt, ACL ngoài dự kiến |
| A02-18 | Race delete/approve với review operation | Không xóa/approve dở dang; phối hợp EXT-04 với session lock |
| A02-19 | Mất response reserve/complete/settlement với reasons không rỗng | Retry cùng binding, `_settle` không conflict sai, không dispatch thêm; 503 sau commit không rollback |
| A02-20 | Normal complete / uncertain complete / replay | Cùng projection đã commit, cả khi live candidate đổi |
| A02-21 | Job Stage 2 cũ có saved results, resume sau thay đổi targeted prompt | Fingerprint generation thường không đổi; A03 phối hợp Tâm |
| A02-22 | AI/clone/fallback mixed policy; legacy clone null | AI mode cần Accept; provenance/Export đúng hoặc blocker có owner; không suy mode từ origin |
| A02-23 | Rollout old/new DB/backend/FE và RPC schema cache | Caller hợp lệ hoạt động theo chiến lược Q05, caller cũ không bypass |
| A02-24 | Reject A → generate B → Accept B → Shuffle → Preview → Approve → Export | A/B có key khác nhau; shuffle đổi nhãn; file đề/đáp án/lời giải đúng B và projection, không lẫn A |
| A02-25 | Recovery non-owner/unknown session, approved/post-shuffle; recovery commit rồi snapshot read lỗi | Không có worker mutation trước owner check; đúng routing; lỗi đọc không che commit, retry không double-settle |
| A02-26 | Frozen/live mode lệch; legacy/new thiếu mode; mode lạ; policy 1.0/1.1 | Legacy có evidence mới dùng default; dữ liệu mới sai bị chặn trước reserve/AI; replay cũ giữ Q02 |
| A02-27 | Clone-only AI reject, shuffle-only reject/revert trực tiếp; UI đọc capability | Đúng Q04 đã được xác nhận; không bypass qua direct RPC, không tạo operation/quota |
| A02-28 | R09 qua Export reader và Finalize repository với mixed-policy/negative fixtures §3.6.1 | Projection đủ field; classifier không chặn nhầm; provenance invalid bị từ chối ở cả Preview/Export |
| A02-29 | Body `[]`, scalar, field lạ, malformed JSON, `reasons:null` | 422 trước operation write/AI/quota; phân biệt với `{"reasons":[]}` |
| A02-30 | Migration dependency/schema thiếu; DDL rollback; backend smoke lỗi sau DDL | Không bật guard/traffic sớm; rollback transaction hoặc roll-forward tương thích, không mất receipt |

A20 (Quỳnh chủ trì, Duy/Tâm/Đạt/Hùng/Bội Anh phối hợp): backfill hai lần với tên trùng và hậu tố sẵn, draft/approved/exported, mã legacy ngoài miền OMR; so sánh nguồn/lượt/mã/receipt/artifact trước/sau; hồi quy `AI → Review → Preview → Approve → Export`. Duy kiểm phần Review và điều phối đầy đủ bằng chứng, không nhận thay scope migration Bank/Export. Duy không tự chứng nhận A20 khi consumer chưa tích hợp. A03/A05 có case liên quan source/mode do Tâm chủ trì; Duy hỗ trợ tại Review boundary.

### 5.3. Test files và commands

| Nhóm | File hiện có ưu tiên |
|---|---|
| API / snapshot | `backend/tests/api/test_review_api.py`, `test_review_rpc_http.py`, `test_review_snapshot.py` |
| Service / receipt | `backend/tests/services/test_review_lifecycle.py`, `test_review_receipts.py`, `test_review_flow.py`, `test_review_contract_parsers.py` |
| PostgreSQL | `backend/tests/migrations/test_review_rpcs.py`, `test_review_snapshot_pg.py`, `test_review_migration_chain.py`, `test_w4_baseline_chain.py`; `backend/tests/services/test_review_real_db_integration.py` |
| AI | `backend/tests/ai/test_targeted_regeneration.py`, `backend/tests/services/test_review_ai_dependency.py` |
| Preview/Export R09 | `backend/tests/exporter/test_snapshot_reader.py`, `test_snapshot_q01.py`, `test_snapshot_builder.py`; `backend/tests/services/test_finalize_display_contract.py`; `backend/tests/api/test_finalize_preview.py`; `backend/tests/migrations/test_export_q01_pg.py` |
| Policy | `backend/tests/generation/test_per_question_policy.py` cùng targeted/DB guard tests mới |
| FE | `frontend/src/features/stage3-review/Stage3Review.test.js`, `frontend/src/services/stage3Service.test.js` |

**Regression FE cần chỉnh có chủ đích tại #109@1072d1c:** test dòng 597 (dialog → inline, đồng thời cập nhật assertion ở dòng 654 không còn cấm `'Lý do từ chối'`), 660 (accept + snapshot mock phải cập nhật), 871 (Preview gate `progress.ready`), 996 (hiện mới test `acceptQuestionFn`, cần bổ sung case `reject` retry uncertain/terminal + `reasons`), 2816 và 2864 (question-major → version-major, accept inline); giữ focus test 2889 cho reasons/revert dialog. Giữ các test candidate identity #85, stale session/unmount, read-only/partial, post-shuffle 409 và approved/exported 423. Mock snapshot phải phản ánh mutation thực, không sửa business logic để thỏa mock tĩnh. Không bỏ test regression để làm xanh CI.

Từ root repo, trong môi trường đã setup dependencies theo hướng dẫn:

```bash
ruff check backend/app scripts/blueprint
mypy backend/app --ignore-missing-imports
python -m pytest backend/tests/api/test_review_api.py backend/tests/services/test_review_lifecycle.py backend/tests/services/test_review_receipts.py backend/tests/ai/test_targeted_regeneration.py -q
python -m pytest backend/tests/exporter/test_snapshot_reader.py backend/tests/exporter/test_snapshot_q01.py backend/tests/exporter/test_snapshot_builder.py backend/tests/services/test_finalize_display_contract.py backend/tests/api/test_finalize_preview.py backend/tests/generation/test_per_question_policy.py -q
python -m pytest backend/tests scripts/blueprint/tests -q
```

```bash
cd frontend
node --test --test-concurrency=1 src/features/stage3-review/Stage3Review.test.js src/services/stage3Service.test.js
npm run lint
npm run build
npm test
```

Theo [isolated_postgres.py](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/tests/services/isolated_postgres.py), TASK-305 real DB suite cần Docker và hai biến opt-in. Ví dụ Bash, **chỉ cho disposable test DB**:

```bash
RUN_TASK305_REAL_DB_TESTS=1 EXAM_TEST_DB_DESTRUCTIVE=1 \
  python -m pytest backend/tests/services/test_review_real_db_integration.py -q
```

PowerShell tương đương: thiết lập `$env:RUN_TASK305_REAL_DB_TESTS='1'` và `$env:EXAM_TEST_DB_DESTRUCTIVE='1'`, chạy cùng pytest target, sau đó xóa hai biến môi trường. Không chạy trên DB chia sẻ/production. Kiểm tra fixture áp migration nào: suite trên dùng `schema.sql` rồi 006, 007, 008, 009 và adapter asyncpg; **không đủ chứng minh full current chain**. `test_review_migration_chain.py` cũng opt-in `RUN_UPSTREAM_MIGRATION_TESTS=1` và cần các pinned commits; không mặc định nó bao phủ EXT migration.

Bổ sung rehearsal/test full chain đúng baseline đến 027 + migration mới và migration phối hợp EXT-02/04 (tùy head triển khai), trên DB cô lập mới và DB có dữ liệu/receipt cũ. Ghi rõ migration list, role, kết quả pass/fail/skip. PG thật không chứng minh PostgREST schema cache; chạy smoke RPC mới qua PostgREST môi trường test với owner và non-owner, kiểm old caller theo Q05. Đối chiếu [w4-migration-candidate](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/w4-migration-candidate.md); Git inventory không phải applied ledger.

Local runtime theo CONTRIBUTING: `scripts/dev.ps1 setup`, `doctor`, `up`, `smoke`, `test` (PowerShell/pwsh theo nền tảng). Chạy UI browser thật và API/DB thật cho A01/A02, ít nhất một ca targeted regeneration với AI thật nếu cấu hình/quota cho phép; mock prompt tests không thay kiểm provider. Nếu thiếu môi trường/key, ghi blocker và phạm vi chưa đạt, không nhận live integration pass. CI theo `.github/workflows/ci.yml`, `docker-ci.yml`; không bỏ checks. `ci.yml` ở base chỉ thấy frontend install + build; không suy npm lint/test đã chạy từ CI xanh. Ghi kết quả chạy riêng. A01/A02 và retry/concurrency/ACL/migration cần bằng chứng môi trường test thật theo task §5; mock không thay nghiệm thu.

## 6. Lịch, PR và công sức

| Ngày (2026) | Công việc | Output / gate |
|---|---|---|
| 26/11 | Đồng bộ #109, M2, chốt Q01–Q08, Draft PR #111 | Base/head, contract, migration slot, I-EXT-01 contract/fixture draft |
| 27/11 | API/DB/receipt | Canonical reasons, lookup/reserve, replay/failure unit + PG tests |
| 28/11 | AI feedback, recovery; UI phần độc lập nếu đủ input | Reasons qua retries; reconcile expired; contract test |
| 29/11 | Inline UI, navigation, snapshot/readiness | A01 component tests; no stale local override |
| 30/11 | Integration, revert/provenance, DB chain | A01/A02 evidence, I-EXT-01 giao bản có head |
| 01/12 | Regression, independent review, sửa blocker, báo cáo | M3/M5 theo tình hình, ghi Accepted/Integrated thực tế và phần còn chờ |

| Hạng mục | Giờ công ước lượng |
|---|---:|
| Baseline/M1/M2 | 3–4 |
| API/DB/receipt | 7–11 |
| AI feedback | 3–5 |
| Recovery | 3–5 |
| Inline UI | 3–4 |
| Navigation/snapshot | 4–7 |
| Kiểm thử/bàn giao | 6–9 |
| **Tổng** | **29–45** |

Đây là dự báo, không phải velocity đã đo. 26/11 là ngày plan, 27/11 mới bắt đầu code. Nếu 6 giờ/ngày trong 6 ngày thì có 36 giờ tổng công suất, không đủ kịch bản 45 giờ và chưa có buffer review/điều phối. Khoảng 29–45h là dự toán trước hiệu chỉnh, chưa cộng phần reader/classifier R09 và contract mode bổ sung; phải tái ước lượng sau G2/G4. Phần sửa của EXT-03/04 do owner tương ứng ước lượng, không mặc định nằm trong giờ Duy. Chốt khả năng thực tế với Duy; không biến hạn báo kết quả 01/12 thành cam kết tất cả EXT hoàn tất. Ưu tiên contract, durable correctness và A01/A02; báo sớm phần còn chờ, không cắt test an toàn.

### 6.1. Chiến lược PR

Mặc định một Draft PR `feat/ext-01-review` với commit plan trước, các commit code/test logic rõ ràng. Tối đa hai PR nếu review thực sự dễ hơn: A (API/DB/AI/recovery) và B (FE). Nếu chia, B phụ thuộc A và UI reasons chỉ mở khi backend/AI đã tích hợp. Không tách riêng PR AI sau khi API đã mở hành vi reasons chưa được sử dụng; không tạo integration PR nếu không có diff tích hợp cần review. Reviewer đề xuất theo chuyên môn, chưa giao chính thức; tối thiểu một GitHub Approve độc lập và CI đạt theo CONTRIBUTING; xử lý blocker trên đúng thread/head.

### 6.2. M1 — Điều phối của Duy

Thứ tự tích hợp chính `EXT-01/EXT-02 → EXT-04 → EXT-03`. Hợp đồng I-EXT-02 từ Quỳnh phải đến sớm cho Tâm/Đạt dù code EXT-04 hoàn thành sau; I-EXT-04 chỉ chặn mở OMR, không chặn xuất thường. Hùng/Quỳnh và Đạt/Bội Anh chốt I-EXT-05 sớm. M1 phải ghi riêng need-by, ETA provider giao contract/fixture, ETA code hoàn tất, thời gian consumer tích hợp/kiểm/sửa, reviewer/backup và link Draft PR/tracker. Dưới đây là khung điền, không phải M1 đã xác nhận. §4 là nơi duy nhất tổng hợp input, không lặp tracker input.

| EXT / owner | Reviewer / backup | PR / tracker | ETA task được xác nhận | Consumer tích hợp + kiểm + sửa |
|---|---|---|---|---|
| 01 — Duy (`@johannguyen015`) | Đề xuất `@nhatquynh1107` / `@AI-WFox` / `@benalexx007`; dự phòng TBD | [PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111) | TBD (dự toán 29–45h) | `@AI-WFox`/`@Thanhdat3010`/`@nhatquynh1107`: TBD |
| 02 — Tâm (`@AI-WFox`) | TBD / TBD | TBD | TBD | `@nhatquynh1107`/`@Thanhdat3010`: TBD |
| 04 — Quỳnh (`@nhatquynh1107`) / Hùng (`@benalexx007`) | TBD / TBD | TBD | TBD | `@Thanhdat3010`/`@htbaax`: TBD |
| 03 — Đạt (`@Thanhdat3010`) / Bội Anh (`@htbaax`) | TBD / TBD | TBD | TBD | `@nhatquynh1107`/`@benalexx007`: TBD |

Tại bảng §4, điền vào cột Need-by / ETA của từng input: need-by (giữ đề xuất hoặc cập nhật), ETA provider giao contract/fixture, ETA task cung cấp, consumer estimate tích hợp/kiểm/sửa, người và thời điểm xác nhận. Các ETA và estimate consumer đều TBD trước phản hồi. I-EXT-01 đề xuất need-by contract 26/11, evidence integration theo head 30/11; không gọi các ngày đề xuất là ETA đã cam kết. Không tự điền ETA của người khác nếu chưa xác nhận.

Critical path dự kiến EXT-02/04 vì mode/reuse và transaction approve/migration; kiểm lại sau khi owner báo ETA. Với input trễ: ghi phần nghiệm thu độc lập, điều kiện chưa đủ, owner và mốc xử lý trên M2/M1. Giữ một nơi tổng hợp input; không lập thêm hệ thống tracker trùng lặp.

## 7. Truy vết các finding từ lần kiểm chứng kế hoạch

Đây là finding của **kế hoạch**, không mặc định là defect đã tái hiện production. Tất cả đang ở trạng thái plan-adjusted hoặc pending decision, chưa có implementation evidence.

| ID | Mức | Delta đã đưa vào v1.1 | Kiểm chứng khi code |
|---|---|---|---|
| V01 | P1 | Reasons persisted và verified receipt; tách frozen snapshot; giữ feedback qua retry | A02-02–06, 09 |
| V02 | P1 | Replay từ completion/settlement, không live projection | A02-04, 12 |
| V03 | P1 | Reconciliation cho expired operation, kể cả reload mất key | A02-11 |
| V04 | P1 | Snapshot authoritative, navigation epoch, bỏ overwrite optimistic | A01-03–09 |
| V05 | P1 | Phân loại active/uncertain/terminal, key lifecycle | A02-11, 13 |
| V06 | P1 | Mode guard và slot policy với Tâm | A02-16, Q04 |
| V07 | P2 | Fixture khớp `ReviewSnapshotProgress` | A01-08–09, I-EXT-01 |
| V08 | P2 | Placeholder/null/provenance; không phá Export | A02-15, Q06 |
| V09 | P2 | Kiểm caller/signature/grants, không wrapper vô cớ | A02-08, 17 |
| V10 | P2 | Một PR mặc định, tối đa hai | M2/M3 scope |
| V11 | P2 | Opt-in PG, full chain, populated DB, CI và ETA có điều kiện | §5.3, §6 |

### 7.1. Audit v1.1 → v1.2 (R01–R16)

| ID | Mức audit | Thay đổi / nơi kiểm | Trạng thái |
|---|---|---|---|
| R01 | P1 | §3.2: mọi caller gồm `_settle`, A02-19 | Plan adjusted |
| R02 | P1 | §3.3: cả 3 đường dựng projection, A02-20 | Plan adjusted |
| R03 | P1 | §3.4: giữ fingerprint thường, A02-21/A03 | Plan adjusted |
| R04 | P1 | §3.3/Q02: terminal result semantics, A02-13 | Plan adjusted; pending implementation |
| R05 | P1 | §3.3/Q03: active/expired, reload mất key, A02-11/25 | Plan adjusted; pending implementation |
| R06 | P1 | §5.3: cập nhật các regression FE có chủ đích | Plan adjusted |
| R07 | P1 | §3.4/Q04: frozen mode/policy, AI clone/fallback, A02-16/22 | Pending integration |
| R08 | P1 | §3.5: read epoch chung, A01-13/14 | Plan adjusted |
| R09 | P1 | §3.6/Q06: legacy/mixed clone, A02-22 | Pending integration |
| R10 | P2 | §2: migration 021/026 đúng implementation | Plan adjusted |
| R11 | P2 | §3.2/Q05: rollout, ACL/cache, FE signature, A02-23 | Pending decision |
| R12 | P2 | §3.4: teacher feedback và previous repair độc lập, A02-09 | Plan adjusted |
| R13 | P1 | A02-24: file xuất cuối từ candidate mới sau shuffle | Plan adjusted |
| R14 | P2 | §5.3: PG selected/full chain, PostgREST và CI scope | Plan adjusted |
| R15 | P2 | §4.2/Phụ lục A: transition samples, ready fixture đúng nghĩa | Pending delivery |
| R16 | P2 | §4/§5/§6.2: đầy đủ I-EXT-02, A20, M1 fields | Pending confirmation |

F-013 → A01/A02; F-019 → baseline/delta tại §2 và M2 gate. A20 là nghiệm thu liên task, không coi fixture đủ thay integration.

### 7.2. Review ngày 26/11 — F01–F04

| Finding trong chat | Chỉnh trong plan | Trạng thái / kiểm còn lại |
|---|---|---|
| F01 — Q06 thiếu reader/classifier | §3.6.1, file list lượt 6b, A02-28 | Plan adjusted; owner xác nhận G4, chưa có code/runtime evidence |
| F02 — Mode đọc live config thay frozen | §3.4.1, Q04, migration dependency §3.2.1, A02-26/27 | Plan adjusted; G2 còn chờ schema/legacy discriminator/DTO từ Tâm |
| F03 — Body `[]` mâu thuẫn DTO | §3.1/Q01, mẫu comment, A02-01/29 | Plan adjusted; API tests phải xác minh khi code |
| F04 — Baseline/status và gói review | §0/G0, §2, §9 | Metadata merge đã kiểm; chưa đồng bộ nhánh/commit/push hoặc bàn giao nguồn phân công |

## 8. Definition of Done

- [ ] F-019: PR #109 và integration HEAD đã đối chiếu, ghi phần tái sử dụng/delta và evidence; không nhầm kết quả tác giả với tự kiểm.
- [ ] M1/M2: scope, base/head, reviewer/dự phòng, ETA, input dependencies và migration ordering đã chốt.
- [ ] Gates G0–G4 được xác nhận theo phạm vi bàn giao; ghi link/head/owner, không tick chỉ vì plan đã đủ nội dung.
- [ ] Recovery endpoint kiểm owner trước service-role mutation; A02-25 đạt.
- [ ] Frozen mode/policy và legacy discriminator có contract/fixture; A02-26/27 đạt.
- [ ] R09 có reader/classifier/verifier đầy đủ và test qua repository; A02-28 đạt hoặc ghi blocker owner nếu ngoài phần bàn giao.
- [ ] API: optional reasons, enum validation, canonicalization, caller MVP tương thích.
- [ ] DB: lookup/reserve cùng binding, legacy receipt rỗng, concurrency, ACL, quota và mode guard đạt trên PG thật.
- [ ] Replay/recovery: cả ba response path cùng projection; non-empty reasons khi settlement uncertain; Q02/Q03 chốt; worker chết/expiry/reload, failure retry, không duplicate dispatch.
- [ ] AI: reasons từ reservation đã xác nhận, giữ qua retry; blueprint/validator/permit không suy yếu; resume job cũ không hồi quy, Q04 mode/policy đã tích hợp.
- [ ] FE: inline đáp án/lời giải/accept, reasons dialog, revert, navigation epoch và authoritative snapshot.
- [ ] Readiness: server gate; không tự approve hoặc tự chuyển Preview; missing/recovery/lock đúng.
- [ ] A01/A02 đạt trên HEAD triển khai; A02-24 đối soát artifact cuối, answer/solution đúng; phần live/DB chưa kiểm ghi rõ.
- [ ] I-EXT-01 có fixture đúng schema, contract version, consumer acknowledgement và evidence tích hợp khi có.
- [ ] Migration chain/rehearsal, PostgREST smoke/rollout, regression, lint/typecheck/build, CI áp dụng đạt; independent review, xử lý blocker.
- [ ] A20 phối hợp khi đủ các EXT; không tuyên bố hoàn thành toàn nhóm nếu chưa có evidence.

## 9. Bàn giao — cập nhật theo kết quả thật

- PR/commit/output: [Draft PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111) trên nhánh `feat/ext-01-review` (từ `dev@efed79b`).
- Đã có trước lượt hiệu chỉnh: plan và Draft PR #111. Lượt 26/11 cập nhật gates G0–G5, Q01 body contract, Q03 authorization, Q04 frozen mode/policy, Q05 deployment/dependency/recovery, Q06 reader/classifier/provenance, ma trận A02-25–30, và đã đăng [comment chốt Q04–Q08](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7181001101) lên PR #111.
- Đã kiểm: code và metadata GitHub; PR #109 đã merge tại `b2924434`; môi trường local/test do chủ trì báo đã chuẩn bị, lượt hiệu chỉnh này chưa kiểm runtime; chưa chạy bộ test ứng dụng hay DB/AI cho code EXT-01 mới.
- Đã chấp nhận: chưa có xác nhận M2 từ reviewer/consumer (`Q04–Q08`).
- Còn chờ: đồng bộ `feat/ext-01-review` với dev đã chứa #109 và ghi integration HEAD, xác nhận của các owner cho `Q04–Q08` và thứ tự migration sau `027`.

## 10. Tài liệu tham chiếu

- EXT v3.1: `Ke-hoach-phan-cong-EXT-v3.1-final.md` (file phân công cung cấp ngày 25/11/2026; repo link TBD).
- [AGENTS.md](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/AGENTS.md), [CONTRIBUTING.md](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/CONTRIBUTING.md), [WORKFLOW](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/WORKFLOW.md), [TEMPLATES — M2](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/TEMPLATES.md#m2).
- [Review RPC Contract](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/api/review-rpc-contract.md), [Review Snapshot Contract](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/api/review-snapshot.md), [Targeted Regeneration](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/ai-w3-targeted-regeneration.md).
- [PR #109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109), [ISSUE-95 plan](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/1072d1c/docs/tasks/ISSUE-95.md), [Compare dev...fix/stage3-ui](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/compare/efed79b...1072d1c).

**Giới hạn:** Plan dựa trên static inspection của commit đã ghim, không xác nhận schema đang deploy hay correctness runtime. Reason codes/Q01–Q03 là thiết kế nội bộ EXT-01 trong bản này; `Q04–Q08` và rollout cần owner liên quan xác nhận qua [Draft PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111).


## Phụ lục A — I-EXT-01: mẫu transition để chốt contract

Các mẫu sau là **dữ liệu giả, trích trường theo DTO hiện hành**, không phải full JSON snapshot hay kết quả test. Dùng cùng `session_id=10000000-0000-0000-0000-000000000001`, `version_id=30000000-0000-0000-0000-000000000001` (mã nội bộ 101), `source_question_id=20000000-0000-0000-0000-000000000001`; câu nguồn `2x + 4 = 0`, options `["x = -2", "x = 2", "x = -4", "x = 4"]`, key `A`, solution nguồn null trong ca thiếu lời giải. Khi tạo full fixture, lấy đúng envelope/confirmation/job/source revision từ fixture baseline, cập nhật status, counts, provenance, timestamp và freshness token nhất quán; không giả token thành revision tăng dần.

| Transition | candidate_id (UUID giả) | status | Nội dung / options theo A–D | correct_key | solution_md | origin / is_reverted |
|---|---|---|---|---|---|---|
| Trước accept | `40000000-0000-0000-0000-000000000001` | pending_review | 3x + 6 = 0 / `["x = 2", "x = -2", "x = -3", "x = 3"]` | B | `3x = -6 nên x = -2. Chọn B.` | ai_generated / false |
| Sau accept | cùng ID …0001 | approved | Giữ nguyên | B | Giữ nguyên | ai_generated / false |
| Sau reject/regenerate | `40000000-0000-0000-0000-000000000002` | pending_review | 5x - 15 = 0 / `["x = 3", "x = -3", "x = 5", "x = -5"]` | A | `5x = 15 nên x = 3. Chọn A.` | regenerated / false |
| Sau accept mới | cùng ID …0002 | approved | Giữ nguyên | A | Giữ nguyên | regenerated / false |
| Sau revert (nhánh riêng) | `40000000-0000-0000-0000-000000000003` | pending_review | Nội dung/options nguồn | A | `Không có lời giải cho câu hỏi này.` | reverted / true |
| Sau reaccept revert | cùng ID …0003 | approved | Giữ nguồn | A | Giữ placeholder; UI “Chưa có lời giải” | reverted / true |

Mỗi snapshot chỉ chứa candidate current của slot, không chứa cả ba lịch sử. Revert frozen-source phải có validation report/provenance theo 024; mẫu trên không thay thế kiểm nguồn thực. Với 1 phiên bản × 1 câu: trước accept/regen/revert, `progress = {"expected_slots":1,"current_slots":1,"approved_slots":0,"missing_slots":0,"ready":false}`; sau accept nếu tất cả điều kiện DB đủ, `approved_slots:1,ready:true` và session `reviewed`. Missing slot: `candidate:null`, current/approved=0, missing=1, ready=false; regenerating: candidate giữ ID hiện hành, ready=false. Kiểm riêng nhiều mã theo A01; `ready` không suy chỉ từ counts.

A02-24 dùng nhánh candidate …0002: hoán vị options sang `["x = -3", "x = 5", "x = 3", "x = -5"]` thì display key `C`, lời giải đồng bộ `Chọn C`, canonical key vẫn A. Preview/Approve/Export phải dùng projection hậu shuffle và đúng version ID; file xuất không được lấy câu 3x + 6 = 0. Dùng seed fixture hợp lệ có mapping làm đổi nhãn, hoặc chọn case thực tế có mapping đó; chạy shuffler thật, kiểm projection dựa trên mapping đã persist (ví dụ hoán vị trên chỉ minh họa, không mặc định mọi seed cho C). Nhánh revert thiếu solution kiểm độc lập. Mã công khai do EXT-04 cấp, không giả định luôn là 101.

Bàn giao thêm mẫu AI-mode original clone/fallback với pending_review, legacy clone null/mixed-policy và case source có solution. Người nhận xác nhận đủ dùng theo contract, sau đó test thật. Không đánh dấu Decided/Delivered/Accepted/Integrated chỉ vì mẫu đã nằm trong plan.

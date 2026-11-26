# EXT-01 — Review & Targeted Regeneration

**M2 Implementation Plan · v1.2 (proposed) · 25/11/2026**

## 0. Thông tin và trạng thái

| Mục | Giá trị |
|---|---|
| Dự án | Isomorphic Exam Synthesizer — Nhóm 04 |
| Nguồn giao việc | `Ke-hoach-phan-cong-EXT-v3.1-final.md`, EXT v3.1 ngày 25/11/2026, mục 1, 3, 4, 5 |
| Phụ trách | Duy — EXT-01 và điều phối M1 |
| Reviewer / dự phòng | Đề xuất Quỳnh (DB/ACL), Tâm (AI/policy), Hùng (FE); chưa phân công chính thức; dự phòng TBD |
| Repository | [isomorphic-exam-synthesizer](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer) |
| Base đã kiểm | `dev@efed79b1662f63d1bc083eb147dc55421684ea16` |
| Baseline UI tham chiếu | `fix/stage3-ui@1072d1ceee8e126640b2d03a10545f94cac70475` — [PR #109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109), open, chưa merge tại thời điểm kiểm |
| Branch / PR dự kiến | `feat/ext-01-review` → `dev`; link PR TBD; HEAD triển khai TBD |
| Workflow | [v0.1 proposed + INPUT-20261109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/7b7387f/docs/review/WORKFLOW.md); [M2 template trên baseline](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/TEMPLATES.md#m2) |
| Mốc đợt | M2/Draft PR 26/11; code từ 27/11; báo kết quả tối 01/12/2026 |
| ETA task | 29–45 giờ công trực tiếp, dự toán hiệu chỉnh chưa được Duy xác nhận; thời gian chờ input/review không nằm trong số này |
| Trạng thái | Plan đề xuất sau kiểm chứng tĩnh; chưa code, chưa chạy test, chưa có nghiệm thu |

> Bản v1.2 thay thế v1.1, đối chiếu lại EXT v3.1 (181 dòng), audit V01–V11 và R01–R16, code tại hai SHA nêu trên. PR #109 được kiểm lại và vẫn open, chưa merge. Các ID V/R là finding kế hoạch, không phải bug production đã tái hiện. Những giải pháp, ETA, reviewer và migration number chưa được xác nhận là đề xuất, không phải quyết định đã chốt. Khi mở Draft PR, cập nhật base thực tế và link file phân công trong repo nếu đã được đưa lên GitHub.

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

**Gate baseline:** PR #109 đi trước dev 13 commit (10 file thay đổi, chủ yếu FE/test/docs). `htbaax` báo tự chạy 621/621 frontend tests pass, lint/build đạt; `htbaax` đã approve HEAD `1072d1c`; `AI-WFox` kiểm UI với mocked API. Review trước của `johannguyen015` yêu cầu sửa F109-R1-03. Duy cần re-review finding, kiểm CI và điều kiện merge theo CONTRIBUTING. Review trước không yêu cầu sửa optimistic approval trong phạm vi #109; EXT-01 có yêu cầu điều hướng/reload mới nên phải kiểm lại chính phần đó, không mở lại finding đã resolved vô cớ. Chưa coi báo cáo của reviewer khác là kết quả tự kiểm. Nếu #109 chưa merge, chuẩn bị backend từ dev và tránh sửa trùng UI; đồng bộ base trước khi tích hợp. Nhánh `fix/workflow-stabilization-candidate` trả 404 khi kiểm trước đó, không chọn làm baseline.

## 3. File và thứ tự triển khai từ thứ Sáu

| Lượt | File dự kiến (đường dẫn tương đối từ root) | Output | Input / cách kiểm |
|---|---|---|---|
| 1 — API | `backend/app/models/schemas.py`, `backend/app/api/routes/review.py` | Optional reasons, enum, 422, caller cũ | Chốt Q01; API tests |
| 2 — DB | `backend/migrations/<next>_ext01_review_reasons.sql` (tên/số TBD), `backend/app/services/review/{repository,receipts,service}.py` | Durable reasons, lookup/reserve, replay | Chốt Q01/Q02/Q03/Q05; PG thật; cả lookup nội bộ, reserve retry và completion projection |
| 3 — AI | `backend/app/services/generation/{targeted_service,service,prompts}.py` | Feedback immutable theo operation, retry | Chốt Q04; AI regression, không đổi fingerprint Stage 2 |
| 4 — Recovery | `backend/app/services/review/{service,repository}.py`, `backend/app/api/routes/review.py` nếu cần | Reconcile active/expired, retry đúng key | Chốt Q03; worker crash/expiry test |
| 5 — UI | `frontend/src/features/stage3-review/{Stage3ReviewPage,Stage3Comparison,Stage3InspectionDialog}.jsx`, `stage3Review.css`, `frontend/src/services/stage3Service.js` | Inline review, reasons, navigation, snapshot | PR #109 baseline + contract; FE tests |
| 6 — Readiness/revert | Cùng các file Review, chỉ thêm migration/adapter nếu chứng minh cần | Gate server, đúng provenance và answer | I-EXT-01; A01/A02; phối hợp EXT-02/03/04 |
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
- Mảng hợp lệ: sort + deduplicate, không phân biệt thứ tự; mã enum phân biệt hoa/thường. Mã lạ, sai kiểu: 422 trước AI/quota/operation write. `reasons: null` đề xuất 422; chốt Q01.
- Không thêm free text hoặc endpoint quản lý reason codes. Không đổi policy header optional của MVP nếu chưa được thống nhất.

### 3.2. Database và durable reasons (V01, V09; R01, R11)

**Phương án ưu tiên (Q01/Q05, chưa phê duyệt):** lưu mảng canonical tại `review_operations.reservation_result.reasons` khi reserve trong cùng transaction. Đây là JSONB receipt hiện hữu, đủ để so sánh tập lý do và audit operation; không cần cột/bảng mới nếu kiểm chứng caller cho phép. Nếu chọn cột riêng vì lý do ràng buộc SQL, chỉ một nguồn authoritative, projection receipt phải derive từ cột đó. Không lưu hai bản độc lập. Không sửa migration 006 đã phát hành. Receipt lịch sử không có key `reasons` tương đương `[]`; key hiện diện nhưng malformed không được âm thầm coi là rỗng.

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

Kiểm kê callers bằng search toàn repo (bao gồm tests/mocks/docs), RPC overloads, ACL và PostgREST trước khi viết migration. Q05 chọn rollout **đồng bộ DB/backend/FE có maintenance window** nếu OPS xác nhận; dừng nhận operation mới, cho operation active settle hoặc recover đúng lease, rehearsal migration, deploy backend, refresh/kiểm schema cache, smoke rồi mới bật FE. Nếu cần duy trì backend cũ, dùng wrapper 3 tham số chuyển `[]` vào cùng implementation mới; không để chữ ký cũ bypass binding, không tạo overload mơ hồ với default args. Test old→new, new→old (không bật feature nếu DB chưa hỗ trợ), quyền `authenticated`/`anon`/`service_role`. Không chạy DDL shared DB khi chưa có deployment gate. Migration number TBD, phối hợp Quỳnh/Tâm/Đạt.

### 3.3. Replay và recovery (V02, V03, V05; R01, R02, R04, R05)

**Completed result:** `_result()` hiện đọc live `version_questions`, trong khi ledger lưu `completion_candidate` và `settlement_result` (006:545–603). Đề xuất mở rộng owner lookup projection để trả `completion_candidate` đã commit cho receipt completed, cập nhật parser strict; không cấp table read hoặc tạo receipt system mới. Một helper dựng `RegeneratedQuestionResponse` từ completion payload đã lưu, `previous_question_id`, `question_id` và status `pending_review` tại thời điểm commit; kiểm session/operation/lineage/shape. Cả ba đường trả kết quả dùng cùng helper: `_replay`, normal complete và `_settle` phát hiện complete đã commit. Có thể dùng lookup đã bind reasons sau commit (read failure trả 503 retry same key, **không settle lại**); tránh RPC mới nếu đủ. Không suy ra kết quả lịch sử từ dữ liệu live nếu thiếu completion evidence. Kiểm first response và replay bằng cùng payload kể cả accept/reject/shuffle sau đó; FE luôn đọc snapshot hiện hành riêng.

| Operation status | Quy tắc đề xuất |
|---|---|
| Không tồn tại | Reserve sau ownership, editability, mode, current candidate, quota |
| Cùng key khác canonical reasons | 409, không dispatch/mutation |
| `completed` cùng reasons | Trả projection bất biến đã commit, không gọi AI |
| `active` còn hạn | 409 busy, giữ key; không dispatch/settle hộ operation khác |
| `active` hết hạn | Recover qua RPC hiện hữu, đọc lại receipt cùng binding; không chạy lại operation cũ |
| `failed` / `recovered` | Terminal, không dispatch. Q02 phải chốt lỗi public ổn định và cách tương thích lịch sử trước code |

Q02: ưu tiên hiểu “trả kết quả cũ” theo nghĩa kết quả terminal ổn định. Completed phải cùng payload; đối với failure mới, cân nhắc lưu projection lỗi public tối thiểu (status/code, thông báo an toàn) trong settlement receipt **chỉ nếu cần** để lần đầu và replay dùng cùng kết quả. `failure_code()` và `generation_error()` hiện không ánh xạ một-một, không suy lỗi lịch sử từ rollback code. Giữ `409 ERR_OPERATION_FINISHED` cho receipt cũ không đủ evidence và recovered nếu owner chấp nhận; nếu chọn giữ MVP terminal 409 cho mọi replay thất bại, phải xác nhận đó là ngoại lệ được thống nhất của task, không gọi là replay nguyên lỗi. Lỗi trước reservation/uncertain transport không phải terminal receipt. Không tự mở rộng sang immutable response cho Accept/Revert.

**Recovery đề xuất Q03:** retry cùng key active phải kiểm recovery trước trả busy (DB clock, không dùng đồng hồ FE quyết định expiry); sau recovery lookup lại bằng reasons. Với reload/mất key, reuse `ReviewRepository.recover_stale_operations` → service-role `review_recover_session` qua action owner-authenticated tối thiểu, tên route TBD; kiểm owner trước privileged call và giữ cùng khóa session. GET snapshot/progress vẫn read-only. Không thêm scheduler/queue. FE khi mở snapshot có candidate `regenerating` gọi action reconcile; nếu còn active, hiện đang xử lý và cho nút Đọc lại/Thử phục hồi (có thể refresh có giới hạn nếu cần UX); sau action đọc snapshot. Khi lease 180 giây hết hạn, recover trả prior_status; nếu complete thắng race, đọc candidate mới. Không hủy active chưa hết hạn, không hoàn quota đã dispatch. Nếu recovery/refetch lỗi, giữ trạng thái cần đồng bộ, không cho mutation/Preview khi chưa xác nhận.

**Key lifecycle:** key thuộc actor/session/candidate/action + payload canonical. Lỗi transport/503 uncertain hoặc active: giữ key và payload; không đổi reasons rồi retry key đó. Sau terminal được xác nhận, mới cho user tạo operation mới bằng key mới. Sau success, retire key khi đã đối soát kết quả; stale candidate không được hồi sinh. Nếu reload còn key thì đối soát bằng key; lưu client tối thiểu tùy Q03 (không lưu nội dung đề hay approval). Nếu mất key, recovery vẫn dựa trên session và snapshot server. Sau bất kỳ mutation error, đọc lại server; không auto-advance do lần đọc phát hiện approved nếu accept trước đó báo lỗi. Với 409/423 routing, giữ logic post-shuffle/approved/exported hiện hữu.

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

### 3.5. Inline Review, auto-advance và state (V04, V07)

Tận dụng `Stage3Comparison`, `ReviewQuestionContent`, `MathRenderer`, notification, CSS, focus và confirmation dialog từ PR #109. Đáp án/lời giải/Accept hiển thị inline dưới câu; dialog dành cho chọn reasons và xác nhận sinh lại/hoàn nguyên. Không cần redesign cả workspace. Giữ API service `rejectAndRegenerateQuestion(sessionId, questionId, key, config)`; đề xuất thêm reasons trong options/config được destructure tách khỏi Axios config hoặc tham số bổ sung tương thích, không thay ý nghĩa tham số thứ tư; kiểm mọi caller (R11).

- Snapshot authoritative quyết định nội dung, candidate identity, trạng thái duyệt và readiness. Sau mutation success **hoặc lỗi**, refetch qua cơ chế read epoch chung; nếu thất bại hoặc kết quả chưa nhất quán, báo cần đồng bộ và khóa mutation/Preview. Nếu accept báo lỗi nhưng snapshot sau đó đã approved, hiển thị đúng server nhưng không auto-advance. Không ghi đè snapshot bằng response cũ, không merge approval ID cũ vào tập authoritative, không fallback `correct_key='A'` khi thiếu key trong dữ liệu không hợp lệ.
- Derive candidate đang xem từ snapshot và tọa độ phiên/mã/câu; tránh giữ nhiều bản sao cạnh tranh (`session`, `selectedSolution`, `approvedVariantIds`). Chỉ refactor state/handler liên quan trực tiếp, không viết lại toàn bộ trang.
- Dùng `candidate_id` cho mutation; dùng `version_id`/version index và source question identity cho điều hướng theo contract. Guard mounted, session generation/identity (kể cả A→B→A), mutation token; dùng một cơ chế read epoch chung cho initial load, refetch/reconcile cùng session hoặc tuần tự hóa đọc. Không cho request bắt đầu trước mutation/refetch mới ghi đè snapshot mới. `freshness_token` là hash, không phải thứ tự tăng dần. Test hai response cùng session về sai thứ tự (R08).
- Cho đổi mã/câu/session trong lúc chờ Accept (cả click và keyboard); chỉ khóa mutation xung đột. Đặt Accept inline, không phụ thuộc modal giữ focus/khóa navigator. Ghi nhận `navigationEpoch` khi gửi accept và tăng mỗi lần người dùng chủ động điều hướng. Chỉ auto-advance nếu epoch, session và cặp mã/câu chưa đổi, snapshot xác nhận candidate đích đã approved. Tránh ghi đè candidate mới đang xem dù chỉ khác mã/câu trong cùng session.
- Dùng một helper nhỏ `findNextUnreviewed` cho auto-advance và điều hướng chủ động: tìm câu chưa duyệt phía sau trong mã hiện tại; vòng lại câu đã bỏ qua cùng mã; sau đó chuyển mã khác theo thứ tự ổn định. Bỏ qua slot không có candidate để duyệt, hiển thị recovery nếu còn slot thiếu. Không auto-advance khi lỗi, reload, read-only hoặc khi không xác nhận được trạng thái. Khi không còn câu cần duyệt, focus Preview nếu readiness hợp lệ; không tự điều hướng sang Preview.
- Hỗ trợ `pending_review`, `approved`, `rejected`, `regenerating`, `candidate: null` và `read_only`. `origin`, `is_reverted`, `has_warning`, validation report chỉ là evidence; không tạo FE business validator thay backend.
- Giữ hỗ trợ bàn phím/focus và MathRenderer. Vị trí xem lưu client là tiện ích, không phải business state; server quyết định tiến độ. Xác minh tab/session reload, deep link, trạng thái post-shuffle và khóa approved/exported theo routing contract hiện hành.

**Readiness gate:** dùng `snapshot.progress.ready === true`, session `reviewed` và các UI guard hiện hành (không busy, không read-only, không đang cần reconcile). Không suy readiness từ số câu duyệt. Trạng thái post-shuffle dùng API Preview tương ứng; không ép review snapshot đọc được sau shuffle.

`ReviewSnapshotProgress` hiện chỉ có `expected_slots`, `current_slots`, `approved_slots`, `missing_slots`, `ready`. `regenerating_slots` và `duplicate_slots` thuộc `/review/progress`, không tự thêm vào `/review/snapshot` chỉ để FE kiểm lại business rule.

### 3.6. Revert và nguồn thiếu lời giải (V08)

Migration 024 `_review_apply_action` đã kiểm frozen source, source revision, blueprint, source hash; tạo candidate mới `pending_review`, giữ đáp án/lời giải và provenance. Tái sử dụng đường này, không viết lại. Kiểm riêng nhánh legacy không có frozen evidence (có thể auto-approve root); không đổi ngữ nghĩa legacy nếu chưa chốt contract với consumer.

Nguồn thiếu lời giải hiện có thể được biểu diễn bằng null/rỗng ở nguồn hoặc placeholder `Không có lời giải cho câu hỏi này.` ở candidate. Hiển thị “Chưa có lời giải” theo bằng chứng nguồn/representation đã thống nhất, không hiểu placeholder là lời giải toán học. Không tự sinh lời giải khi revert; không tự đổi placeholder thành null vì Preview/Export kiểm provenance cho lời giải rỗng.

R09: migration 026:351–382 clone mới dùng placeholder, nhưng tương thích replay `legacy_expected` với solution null. Export `verified_empty_solution` hiện kiểm `active_variation_modes`, `canonical_dimensions`, `public_modes` rỗng ở cấp session khi origin là clone. Mixed-policy AI mode có clone legacy null có thể không thỏa; đây là rủi ro tĩnh, không kết luận lỗi production. Kiểm riêng AI-generated/regenerated có lời giải, clone/fallback/reverted thiếu nguồn và legacy clone null/rỗng trong mixed policy. Chỉ sửa adapter thuộc owner Đạt nếu test xác nhận blocker; không tự nới provenance hoặc backfill solution hàng loạt.

Đọc [snapshot_provenance.py](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/exporter/snapshot_provenance.py) và [snapshot_builder.py](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/exporter/snapshot_builder.py) cùng Đạt; xác minh key/solution sau shuffle, Preview và Export. Nếu contract thiếu bằng chứng để phân biệt lời giải thiếu, chốt thay đổi tối thiểu trước khi code.

## 4. Đầu vào và câu hỏi — giải đáp trên Draft PR

Nơi tổng hợp input duy nhất: bảng M2 dưới đây (sau khi tạo PR có thể chuyển sang comment tổng hợp và dẫn link). Các ETA dưới đây là đề xuất; ETA được owner xác nhận vẫn là TBD. Không coi im lặng hoặc PR merge là consumer acceptance.

| ID / nguồn | Provider → Consumer | Điều kiện đủ dùng | Need-by / ETA | Mức hiện tại / bước tiếp |
|---|---|---|---|---|
| I-EXT-01 (EXT v3.1 §1) | Duy → Tâm, Đạt, Quỳnh | Contract current candidate, accept/revert, readiness, missing solution và fixture đúng schema; sau đó evidence từ DB/API thật | Contract 26/11; code/evidence dự kiến 30/11; ETA xác nhận TBD | Requested theo phân công; cần consumer xác nhận |
| I-EXT-02 (EXT v3.1 §1) | Quỳnh → Tâm, Đạt | Mẫu nguồn/đích, metadata nullable, receipt/snapshot, miền và sức chứa mã sản phẩm, cặp ID/mã của hai lượt; Duy cần phối hợp migration/session lock cho Review | Contract 26/11; ETA TBD | Theo M1; không đổi owner hoặc ranh giới input |
| I-EXT-03 (EXT v3.1 §1) | Tâm → Quỳnh, Đạt | Canonical source, trạng thái mở lại, projection hậu shuffle có đáp án/lời giải; Duy cần mode guard/slot policy thống nhất với Tâm | Quyết định 26–27/11; ETA TBD | Theo M1; cần thống nhất điểm nối Review |
| I-EXT-04 (EXT v3.1 §1) | Đạt → Quỳnh | Tập con mã/số câu OMR đã kiểm; miền mã sản phẩm từ I-EXT-02 | Trước mở OMR; ETA TBD | Không chặn EXT-01 |
| I-EXT-05 (EXT v3.1 §1) | Đạt/Bội Anh ↔ Hùng/Quỳnh | ID lượt, tải đáp án riêng, contract gói cũ/mới, key và reload | Contract 26–27/11; ETA TBD | Không mở rộng nhiệm vụ Duy ngoài điều phối/điểm nối |

### 4.1. Các quyết định cần chốt (chưa được owner xác nhận)

| ID | Câu hỏi | Đề xuất / người cần phối hợp |
|---|---|---|
| Q01 | Enum reasons, `null`, header optional và HTTP validation? | Duy chốt allowlist; không body/body null/`{}`/mảng rỗng tương đương; trường reasons null đề xuất 422. |
| Q02 | Replay completed phải bất biến đến đâu; failure replay trả gì? | Duy + Quỳnh: trả đúng kết quả reject đã commit, refetch current state; chốt completed và failure/recovered theo §3.3; nếu giữ terminal 409 cho failure thì ghi rõ ngoại lệ đã được chấp nhận. Gate trước code receipt. |
| Q03 | Recover expired operation khi reload mất key, giữ/xóa key và cách phân loại lỗi? | Duy + Quỳnh/Đạt: owner-authenticated reconciliation qua RPC sẵn có; trigger từ active same-key retry và reload thấy regenerating, không mutation trên GET; chốt route/response, active/expired/race/error. |
| Q04 | Shuffle-only và frozen per-slot policy tác động reject/revert thế nào? | Tâm + Duy: chặn AI sinh lại ở DB/API cho shuffle-only; chốt editability và targeted variation policy trong AI mode. |
| Q05 | Migration number, signature RPC, deploy order và grants? | Quỳnh + Duy + Đạt: chọn maintenance window hoặc wrapper tạm thời cùng implementation; kiểm caller, ACL, PostgREST cache, drain/recover operation đang chạy. |
| Q06 | Revert legacy và nguồn thiếu solution biểu diễn ra sao? | Duy + Tâm + Đạt: giữ representation hiện tại trừ khi có contract mới đã thống nhất; kiểm Preview/Export, legacy clone null và mixed-policy. |
| Q07 | Active review operation có chặn xóa draft không? | Quỳnh + Duy: đề xuất có; cùng parent-session lock để tránh race với reserve/complete/recover/approve. |
| Q08 | Reviewed → Preview, reload/deep-link, trường readiness nào? | Hùng + Tâm + Duy: giữ routing contract, không tự gán `approved`; đối chiếu post-shuffle API. |
| Q09 | Chia PR, reviewer, dự phòng, ETA và mốc tích hợp? | Duy điều phối; một Draft PR mặc định, tối đa hai nếu giảm review coupling có thực. |

Không cần chặn toàn bộ công việc bởi câu hỏi chưa liên quan trực tiếp: có thể soạn API fixture và test độc lập; không triển khai giả định chưa chốt tại boundary chung.

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
| A02-01 | Không body/body null/`{}`/mảng rỗng | Caller MVP tương thích |
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

A20 (Quỳnh chủ trì, Duy/Tâm/Đạt/Hùng/Bội Anh phối hợp): backfill hai lần với tên trùng và hậu tố sẵn, draft/approved/exported, mã legacy ngoài miền OMR; so sánh nguồn/lượt/mã/receipt/artifact trước/sau; hồi quy `AI → Review → Preview → Approve → Export`. Duy kiểm phần Review và điều phối đầy đủ bằng chứng, không nhận thay scope migration Bank/Export. Duy không tự chứng nhận A20 khi consumer chưa tích hợp. A03/A05 có case liên quan source/mode do Tâm chủ trì; Duy hỗ trợ tại Review boundary.

### 5.3. Test files và commands

| Nhóm | File hiện có ưu tiên |
|---|---|
| API / snapshot | `backend/tests/api/test_review_api.py`, `test_review_rpc_http.py`, `test_review_snapshot.py` |
| Service / receipt | `backend/tests/services/test_review_lifecycle.py`, `test_review_receipts.py`, `test_review_flow.py`, `test_review_contract_parsers.py` |
| PostgreSQL | `backend/tests/migrations/test_review_rpcs.py`, `test_review_snapshot_pg.py`, `test_review_migration_chain.py`, `test_w4_baseline_chain.py`; `backend/tests/services/test_review_real_db_integration.py` |
| AI | `backend/tests/ai/test_targeted_regeneration.py`, `backend/tests/services/test_review_ai_dependency.py` |
| FE | `frontend/src/features/stage3-review/Stage3Review.test.js`, `frontend/src/services/stage3Service.test.js` |

**Regression FE cần chỉnh có chủ đích tại #109@1072d1c:** test dòng 597 (dialog → inline), 660 (accept + snapshot mock phải cập nhật), 871 (Preview gate `progress.ready`), 996 (retry uncertain/terminal), 2816 và 2864 (question-major → version-major, accept inline); giữ focus test 2889 cho reasons/revert dialog. Giữ các test candidate identity #85, stale session/unmount, read-only/partial, post-shuffle 409 và approved/exported 423. Mock snapshot phải phản ánh mutation thực, không sửa business logic để thỏa mock tĩnh. Không bỏ test regression để làm xanh CI.

Từ root repo, trong môi trường đã setup dependencies theo hướng dẫn:

```bash
ruff check backend/app scripts/blueprint
mypy backend/app --ignore-missing-imports
python -m pytest backend/tests/api/test_review_api.py backend/tests/services/test_review_lifecycle.py backend/tests/services/test_review_receipts.py backend/tests/ai/test_targeted_regeneration.py -q
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
| 26/11 | Re-review #109, M1/M2, chốt Q01–Q09, Draft PR | Base/head, contract, reviewer/backup/ETA, migration slot, I-EXT-01 contract/fixture draft |
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

Đây là dự báo, không phải velocity đã đo. 26/11 là ngày plan, 27/11 mới bắt đầu code. Nếu 6 giờ/ngày trong 6 ngày thì có 36 giờ tổng công suất, không đủ kịch bản 45 giờ và chưa có buffer review/điều phối. Chốt khả năng thực tế với Duy; không biến hạn báo kết quả 01/12 thành cam kết tất cả EXT hoàn tất. Ưu tiên contract, durable correctness và A01/A02; báo sớm phần còn chờ, không cắt test an toàn.

### 6.1. Chiến lược PR

Mặc định một Draft PR `feat/ext-01-review` với commit plan trước, các commit code/test logic rõ ràng. Tối đa hai PR nếu review thực sự dễ hơn: A (API/DB/AI/recovery) và B (FE). Nếu chia, B phụ thuộc A và UI reasons chỉ mở khi backend/AI đã tích hợp. Không tách riêng PR AI sau khi API đã mở hành vi reasons chưa được sử dụng; không tạo integration PR nếu không có diff tích hợp cần review. Reviewer đề xuất theo chuyên môn, chưa giao chính thức; tối thiểu một GitHub Approve độc lập và CI đạt theo CONTRIBUTING; xử lý blocker trên đúng thread/head.

### 6.2. M1 — Điều phối của Duy

Thứ tự tích hợp chính `EXT-01/EXT-02 → EXT-04 → EXT-03`. Hợp đồng I-EXT-02 từ Quỳnh phải đến sớm cho Tâm/Đạt dù code EXT-04 hoàn thành sau; I-EXT-04 chỉ chặn mở OMR, không chặn xuất thường. Hùng/Quỳnh và Đạt/Bội Anh chốt I-EXT-05 sớm. M1 phải ghi riêng need-by, ETA provider giao contract/fixture, ETA code hoàn tất, thời gian consumer tích hợp/kiểm/sửa, reviewer/backup và link Draft PR/tracker. Dưới đây là khung điền, không phải M1 đã xác nhận. §4 là nơi duy nhất tổng hợp input, không lặp tracker input.

| EXT / owner | Reviewer / backup | PR / tracker | ETA task được xác nhận | Consumer tích hợp + kiểm + sửa |
|---|---|---|---|---|
| 01 — Duy | TBD / TBD | TBD | TBD (dự toán 29–45h) | Tâm/Đạt/Quỳnh: TBD |
| 02 — Tâm | TBD / TBD | TBD | TBD | Quỳnh/Đạt: TBD |
| 04 — Quỳnh/Hùng | TBD / TBD | TBD | TBD | Đạt/Bội Anh: TBD |
| 03 — Đạt/Bội Anh | TBD / TBD | TBD | TBD | Quỳnh/Hùng: TBD |

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
| R04 | P1 | §3.3/Q02: terminal result semantics, A02-13 | Pending decision |
| R05 | P1 | §3.3/Q03: active/expired, reload mất key, A02-11 | Pending decision |
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

## 8. Definition of Done

- [ ] F-019: PR #109 và integration HEAD đã đối chiếu, ghi phần tái sử dụng/delta và evidence; không nhầm kết quả tác giả với tự kiểm.
- [ ] M1/M2: scope, base/head, reviewer/dự phòng, ETA, input dependencies và migration ordering đã chốt.
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

- PR/commit/output: TBD (chưa tạo PR từ file này).
- Đã làm: lập plan, đối chiếu source/PR/migration/schema/fixture/test configuration tĩnh tại baseline nêu trên.
- Đã kiểm: code và metadata GitHub; chưa chạy application tests, isolated PostgreSQL, live Supabase hoặc Gemini.
- Đã chấp nhận: chưa có xác nhận M2 từ owner/reviewer/consumer.
- Còn chờ: Q01–Q09, PR #109 baseline, migration ordering/deployment gate, test environment và ETA xác nhận.

## 10. Tài liệu tham chiếu

- EXT v3.1: `Ke-hoach-phan-cong-EXT-v3.1-final.md` (file phân công cung cấp ngày 25/11/2026; repo link TBD).
- [AGENTS.md](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/AGENTS.md), [CONTRIBUTING.md](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/CONTRIBUTING.md), [WORKFLOW](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/WORKFLOW.md), [TEMPLATES — M2](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/TEMPLATES.md#m2).
- [Review RPC Contract](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/api/review-rpc-contract.md), [Review Snapshot Contract](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/api/review-snapshot.md), [Targeted Regeneration](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/ai-w3-targeted-regeneration.md).
- [PR #109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109), [ISSUE-95 plan](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/1072d1c/docs/tasks/ISSUE-95.md), [Compare dev...fix/stage3-ui](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/compare/efed79b...1072d1c).

**Giới hạn:** Plan dựa trên static inspection của commit đã ghim, không xác nhận schema đang deploy hay correctness runtime. Các reason codes, cách lưu reasons, recovery action, failure replay, rollout, PR split, reviewer và lịch là đề xuất cần chốt; không phải contract đã được nhóm phê duyệt. Không có thao tác push, tạo Issue/PR hoặc sửa GitHub trong quá trình tạo file này.


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

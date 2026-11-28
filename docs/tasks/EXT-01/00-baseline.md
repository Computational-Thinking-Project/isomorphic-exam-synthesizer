# EXT-01 / 00 — Baseline và đối chiếu code

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Bắt đầu ngay bằng đọc/kiểm; đồng bộ code theo G0 trước khi sửa UI.
- **File / đầu vào:** Git refs/working tree; source Stage 3 tại #109; plan M2 hiện tại.
- **Thứ tự làm:** Ghi base/head và file tái sử dụng; bảo toàn thay đổi; đồng bộ dev theo quyền; đối chiếu API/migration/FE đã ghim.
- **Đầu ra / điều kiện hoàn thành gói:** Integration HEAD, diff và bằng chứng F-019; G0 chưa tự đạt chỉ vì file này tồn tại.
- **Kiểm chứng:** F-019; G0; lịch sử V/R/F bên dưới. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** chưa xác nhận code/test của gói. Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-2"></a>

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
| [024:345–547](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/024_source_reuse_optional_solutions.sql#L345-L547) | Revert frozen-source tạo candidate pending; hỗ trợ placeholder lời giải | Giữ contract, kiểm legacy và Export (EOF ở dòng `547`, không phải `548`) |
| [026](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/migrations/026_per_question_generation_policy.sql) | Per-question generation policy | Chốt tác động tới targeted regeneration với Tâm (dòng `351–382` khớp tại integration HEAD) |

**Gate baseline (G0 đã đồng bộ local):**
- **Pre-sync split-docs commit (`feat/ext-01-review`):** `29f1378b4e57ef87833f716f87fa7ad8bf1828c8` (`29f1378`, commit đúng 12 file plan/task và `Ke-hoach-phan-cong-EXT-v3.1-final.md` từ `4618075`).
- **`origin/dev` vs local `dev`:** `origin/dev` ở `b29244346094811eaa038fd31fea67969f8f5b7f` (xác nhận là hậu duệ của merge PR #109 `b2924434`; `git diff --stat 1072d1ce..origin/dev` rỗng, không có PR khác sau #109), trong khi nhánh `dev` local chưa fast-forward vẫn ở `efed79b1662f63d1bc083eb147dc55421684ea16`.
- **Integration Merge HEAD (`feat/ext-01-review` sau `git merge --no-ff origin/dev`):** `57e900bb920bbef70a9aefe9de3f47c81c500be3` (`57e900b`); nhánh cũ `fix/workflow-stabilization-candidate` (`9305de5`) không dùng làm baseline và giữ nguyên không sửa.
- **Stage 3 diff (`29f1378..57e900b`):** Tổng merge 10 file (`1522 insertions(+), 606 deletions(-)`). Riêng phạm vi Stage 3 (`frontend/src/features/stage3-review/*`, `frontend/src/services/stage3Service.js`, `backend/app/api/routes/review.py`, `backend/app/services/review/*`, `backend/app/services/generation/*`): 6 file (`913 insertions(+), 605 deletions(-)` — `Stage3Comparison.jsx`, `Stage3InspectionDialog.jsx`, `Stage3ReviewNotifications.jsx`, `Stage3ReviewPage.jsx`, `stage3Review.css`, `Stage3Review.test.js`; `stage3Service.js`, backend và migrations `002–027` giữ nguyên).
- **Đối chiếu line reference tại Integration HEAD (`57e900b`):** Toàn bộ line reference Stage 3 UI từ `1072d1c` trong gói [05 — Review UI](05-review-ui.md) (`Stage3ReviewPage.jsx` các dòng `732–742`, `757–764`, `771–777`, `1056`, `1071–1086`, `1089`, `1364`, `1394`, `1576`; `Stage3InspectionDialog.jsx:66`; `Stage3Comparison.jsx:1–48`) đã có mặt trực tiếp và khớp 100%; các mốc `stage3Service.js` (`42–58`, `170`), `review.py` (`80–109`), `review/{service,repository}.py`, `generation/{targeted_service,service}.py` và migrations `006`, `009`, `018`, `021`, `024` (EOF `547`), `026` khớp 100% không bị lệch. (Push remote thực hiện ở M6 khi cập nhật PR.)

<a id="section-3"></a>

## 3. File và thứ tự triển khai từ thứ Sáu

| Lượt | File dự kiến (đường dẫn tương đối từ root) | Output | Input / cách kiểm |
|---|---|---|---|
| 1 — API | `backend/app/models/schemas.py`, `backend/app/api/routes/review.py` | Optional reasons, enum, 422, caller cũ | Chốt Q01; API tests |
| 2 — DB | `backend/migrations/<next>_ext01_review_reasons.sql` (tên/số TBD), `backend/app/services/review/{repository,receipts,service}.py` | Durable reasons, lookup/reserve, replay | Chốt Q01/Q02/Q03/Q05; PG thật; cả lookup nội bộ, reserve retry và completion projection |
| 3 — AI | `backend/app/services/generation/{targeted_service,service,prompts}.py` | Feedback immutable theo operation, retry | Feedback/retry tests bắt đầu ngay; policy integration chờ Q04/gói 06; không đổi fingerprint Stage 2 |
| 4 — Recovery | `backend/app/services/review/{service,repository}.py`, `backend/app/api/routes/review.py` nếu cần | Reconcile active/expired, retry đúng key | Chốt Q03; worker crash/expiry test |
| 5 — UI | `frontend/src/features/stage3-review/{Stage3ReviewPage,Stage3Comparison,Stage3InspectionDialog,Stage3ReviewNotifications}.jsx`, `stage3Review.css`, `frontend/src/services/stage3Service.js` | Inline review, reasons, navigation, snapshot | PR #109 baseline + contract; FE tests |
| 6 — Readiness/revert | Cùng các file Review, chỉ thêm migration/adapter nếu chứng minh cần | Gate server, đúng provenance và answer | I-EXT-01; A01/A02; phối hợp EXT-02/03/04 |
| 6b — Consumer integration (sau G4) | `backend/app/services/exporter/{snapshot_reader,snapshot_provenance}.py`, `backend/app/services/finalize/repository.py`; renderer/Preview nếu contract hiển thị đổi | R09 đầy đủ qua reader/classifier/verifier; giữ quyền owner EXT-03/04 | [§3.6.1](07-preview-export-provenance.md#section-3-6-1); A02-28, Preview/Export tests và artifact thật |
| 7 — Evidence | Tests hiện hữu, `docs/api/review-rpc-contract.md`, `docs/api/review-snapshot.md` (nếu đổi), `docs/ai-w3-targeted-regeneration.md` (nếu đổi), `docs/change_log.md`, file task | Contract chuẩn, evidence, bàn giao | CI, isolated PG, live integration theo khả năng |

<a id="section-7"></a>

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
| V11 | P2 | Opt-in PG, full chain, populated DB, CI và ETA có điều kiện | [§5.3](08-verification.md#section-5-3), [§6](../../../EXT-01-Implementation-Plan-v1.2.md#section-6) |

<a id="section-7-1"></a>

### 7.1. Audit v1.1 → v1.2 (R01–R16)

| ID | Mức audit | Thay đổi / nơi kiểm | Trạng thái |
|---|---|---|---|
| R01 | P1 | [§3.2](02-durable-reasons.md#section-3-2): mọi caller gồm `_settle`, A02-19 | Plan adjusted |
| R02 | P1 | [§3.3](03-replay-recovery.md#section-3-3): cả 3 đường dựng projection, A02-20 | Plan adjusted |
| R03 | P1 | [§3.4](04-ai-feedback.md#section-3-4): giữ fingerprint thường, A02-21/A03 | Plan adjusted |
| R04 | P1 | [§3.3](03-replay-recovery.md#section-3-3)/Q02: terminal result semantics, A02-13 | Plan adjusted; pending implementation |
| R05 | P1 | [§3.3](03-replay-recovery.md#section-3-3)/Q03: active/expired, reload mất key, A02-11/25 | Plan adjusted; pending implementation |
| R06 | P1 | [§5.3](08-verification.md#section-5-3): cập nhật các regression FE có chủ đích | Plan adjusted |
| R07 | P1 | [§3.4](04-ai-feedback.md#section-3-4)/Q04: frozen mode/policy, AI clone/fallback, A02-16/22 | Pending integration |
| R08 | P1 | [§3.5](05-review-ui.md#section-3-5): read epoch chung, A01-13/14 | Plan adjusted |
| R09 | P1 | [§3.6](05-review-ui.md#section-3-6)/Q06: legacy/mixed clone, A02-22 | Pending integration |
| R10 | P2 | [§2](#section-2): migration 021/026 đúng implementation | Plan adjusted |
| R11 | P2 | [§3.2](02-durable-reasons.md#section-3-2)/Q05: rollout, ACL/cache, FE signature, A02-23 | Pending decision |
| R12 | P2 | [§3.4](04-ai-feedback.md#section-3-4): teacher feedback và previous repair độc lập, A02-09 | Plan adjusted |
| R13 | P1 | A02-24: file xuất cuối từ candidate mới sau shuffle | Plan adjusted |
| R14 | P2 | [§5.3](08-verification.md#section-5-3): PG selected/full chain, PostgREST và CI scope | Plan adjusted |
| R15 | P2 | [§4.2](09-inputs-handoff.md#section-4-2)/[Phụ lục A](09-inputs-handoff.md#appendix-a): transition samples, ready fixture đúng nghĩa | Pending delivery |
| R16 | P2 | [§4](09-inputs-handoff.md#section-4)/[§5](08-verification.md#section-5)/[§6.2](09-inputs-handoff.md#section-6-2): đầy đủ I-EXT-02, A20, M1 fields | Pending confirmation |

F-013 → A01/A02; F-019 → baseline/delta tại [§2](#section-2) và M2 gate. A20 là nghiệm thu liên task, không coi fixture đủ thay integration.

<a id="section-7-2"></a>

### 7.2. Review ngày 26/11 — F01–F04

| Finding trong chat | Chỉnh trong plan | Trạng thái / kiểm còn lại |
|---|---|---|
| F01 — Q06 thiếu reader/classifier | [§3.6.1](07-preview-export-provenance.md#section-3-6-1), file list lượt 6b, A02-28 | Plan adjusted; owner xác nhận G4, chưa có code/runtime evidence |
| F02 — Mode đọc live config thay frozen | [§3.4.1](06-mode-policy.md#section-3-4-1), Q04, migration dependency [§3.2.1](02-durable-reasons.md#section-3-2-1), A02-26/27 | Plan adjusted; G2 còn chờ schema/legacy discriminator/DTO từ Tâm |
| F03 — Body `[]` mâu thuẫn DTO | [§3.1](01-reject-api.md#section-3-1)/Q01, mẫu comment, A02-01/29 | Plan adjusted; API tests phải xác minh khi code |
| F04 — Baseline/status và gói review | [§0](../../../EXT-01-Implementation-Plan-v1.2.md#section-0)/G0, [§2](#section-2), [§9](../../../EXT-01-Implementation-Plan-v1.2.md#section-9) | Plan tách và `Ke-hoach-phan-cong-EXT-v3.1-final.md` đã commit tại `29f1378`; đã đồng bộ `origin/dev` (`b2924434`) tại Integration HEAD `57e900b` và đối chiếu line-ref khớp 100%; push remote thực hiện ở M6/cập nhật PR |

# TASK-301 — Plan và Bàn Giao: API Thẩm Định 1-1, Vòng Đời `is_current`, Revert Nguyên Tử & Safe Re-shuffle Invalidation

- **Nguồn giao việc:** [W3_ASSIGNMENT.md](W3_ASSIGNMENT.md) (v2.1; 28/10/2026), [w3.md](../../w3.md)
- **Phụ trách:** Duy (`johannguyen015` — Lead); Hùng (`benalexx007` — Contributor)
- **Reviewer:** Hùng (`benalexx007` — đã chốt)
- **Repo/nhánh:** `feat/duy-task-301-review-lifecycle-api`; PR: [#28](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28)
- **Hạn đợt:** tối thứ 3 03/11/2026; **ETA task:** Thứ 7 31/10/2026 (Duy xác nhận)
- **Phiên bản:** v7.2 (Tiếp thu toàn diện phản biện F07: Chuyển sang Kiến trúc A - Pure Per-Acquire Atomic Accounting & Durable DB Ledger; Khắc phục Quota Boundary Conflict, Non-Durable RAM State, Rollback Uncertain Grant)

---

## 1. Sáu Nguyên Tắc Bất Biến (Phải Tuân Thủ Tuyệt Đối)

1. **CSDL Ledger là Single Source of Truth cho Quota (Kiến trúc A):** TX1 không cộng trước 4 quota. `acquire_attempt` tăng nguyên tử có điều kiện `gemini_review_calls + 1 <= 30` cho từng permit được cấp. Emergency Rollback và Stale Recovery KHÔNG refund quota (bảo tồn nguyên vẹn các permit đã commit; không có nguy cơ hoàn tiền sai).
2. **Atomic Replay Detection qua DB Ledger (`review_attempts`):** Kiểm tra chống phát lại trực tiếp trên CSDL với `INSERT ... ON CONFLICT (attempt_id) DO NOTHING`. Nếu rowcount == 0 $\rightarrow$ `replayed = True, dispatch_permitted = False`. Tuyệt đối không dùng RAM state (bảo đảm an toàn multi-worker/multi-process).
3. **Atomic Ownership qua Rowcount:** Chỉ tiến trình nào UPDATE được `status = 'regenerating' -> X` với `rowcount == 1` mới sở hữu quyền chuyển trạng thái. Ai `rowcount == 0` tuyệt đối không thao tác.
4. **Thứ tự Invariant:** UPDATE câu cũ (`is_current = false`) trước $\rightarrow$ INSERT câu mới (`is_current = true`) sau để bảo vệ Partial Unique Index.
5. **Không giữ kết nối DB khi gọi AI:** Tách biệt hoàn toàn TX1, pha gọi Gemini AI (không giữ DB connection), và TX2.
6. **Concurrency Model A:** Khóa mức session — chỉ cho phép duy nhất 1 câu hỏi đang trong tiến trình sinh lại (`regenerating`) trên mỗi session đề; chặn Shuffle/Finalize nếu còn câu regenerating. Thao tác Accept trên câu khác vẫn được phép chạy song song.

---

## 2. Ma Trận Trạng Thái Hệ Thống (State Transition Matrix)

### 2.1. Ma trận Trạng thái Phiên (Session Level Guards)
| Endpoint | Session `generating` | Session `generated` / `reviewed` | Session `approved` / `exported` |
|---|---|---|---|
| `POST .../accept` | `HTTP 409 Conflict` | ✅ Cho phép duyệt độc lập | `HTTP 423 Locked` |
| `POST .../reject` | `HTTP 409 Conflict` | ✅ Cho phép xử lý (nếu quota còn đủ $\ge 4$) | `HTTP 423 Locked` |
| `POST .../revert` | `HTTP 409 Conflict` | ✅ Cho phép xử lý độc lập | `HTTP 423 Locked` |
| `GET .../progress`| ✅ Trả về tiến độ | ✅ Trả về tiến độ (Read-only) | ✅ Trả về tiến độ (Read-only) |

*Nguyên tắc:* Nếu session đang có câu `regenerating`, endpoint `GET /progress` trả về `can_finalize = False` để ngăn chặn shuffle khi chưa ổn định.

### 2.2. Ma trận Trạng thái Câu hỏi (Question Level Guards)
| Hành động | Câu `is_current = false` | Câu `pending_review` (`is_current=true`) | Câu `regenerating` (`is_current=true`) | Câu `approved` (`is_current=true`) |
|---|---|---|---|---|
| **Accept** | `HTTP 400 Bad Request` | ✅ Chuyển `approved` (`rowcount=1`) | `HTTP 409 Conflict` | `HTTP 200 OK` (Idempotent) |
| **Reject** | `HTTP 400 Bad Request` | ✅ Reserve 4 calls & Kích hoạt 2-TX | `HTTP 409 Conflict` | ✅ Cho phép reject lại (hạ shuffle) |
| **Revert** | `HTTP 400 Bad Request` | ✅ Nếu đã từng biến thể $\rightarrow$ Revert; Nếu chưa từng biến thể $\rightarrow$ `HTTP 400` | `HTTP 409 Conflict` | ✅ Nếu đã là bản revert $\rightarrow$ `HTTP 200` Idempotent |

---

## 3. Kiến Trúc Chi Tiết & Giải Pháp Kỹ Thuật

### 3.1. Idempotency TX2 & Emergency Rollback qua `regeneration_id`
- Thêm cột `regeneration_id UUID NULL` và Partial Unique Index `uq_version_questions_regeneration` trên `version_questions`.
- Sinh `regeneration_id = uuid4()` 1 lần duy nhất tại Service layer cho mỗi request reject.
- **TX2 (`complete_regeneration_tx`):**
  - SELECT theo `regeneration_id`: nếu đã tồn tại $\rightarrow$ trả về kết quả cũ (idempotent, không insert/refund lần 2).
  - UPDATE câu cũ `status = 'rejected'` với điều kiện `status = 'regenerating'`: chỉ tiếp tục nếu `rowcount == 1`.
  - INSERT câu mới mang `regeneration_id`, kế thừa đầy đủ `source_question_id`, `version_id`.
  - Refund phần dư `4 - actual_calls` và ghi log `review_logs` (`action_type = 'REJECT'`).
- **Emergency Rollback (`emergency_rollback_tx`):**
  - SELECT theo `regeneration_id`: nếu câu mới đã commit $\rightarrow$ return `False` ngay (không refund, không đổi trạng thái).
  - UPDATE câu cũ `status = 'pending_review'` với điều kiện `status = 'regenerating'`: chỉ khi `rowcount == 1` mới hoàn quota (tối đa 4 - actual_dispatched) và ghi log `REJECT_FAILED`.

### 3.2. Công Thức `required_count` Đa Version Bất Biến
```sql
SELECT COUNT(*) 
FROM (
    SELECT DISTINCT version_id, source_question_id 
    FROM version_questions vq
    JOIN exam_versions ev ON vq.version_id = ev.id
    WHERE ev.session_id = :session_id
      AND vq.source_question_id IS NOT NULL
) AS required_slots;
```
Bảo đảm phiên có $N$ mã đề $\times$ $M$ câu luôn ra đúng $N \times M$ slots câu hỏi, bất biến qua reject và revert.

### 3.3. Kiến Trúc A: Pure Per-Acquire Atomic Accounting & Durable Attempt Ledger (F07 v3.0)
- Hằng số: `MAX_AI_CALLS_PER_REJECT = 4` (trần tối đa 4 attempts cho 1 operation theo TASK-304); `MAX_SESSION_REVIEW_QUOTA = 30` (trần toàn session).
- **TX1 (`reserve_max_quota_and_start_regenerating` / `reserve_regeneration`):** Kiểm tra `gemini_review_calls < 30`, khóa câu hỏi sang `regenerating`. **Tuyệt đối KHÔNG cộng trước 4 vào `gemini_review_calls`** (loại bỏ hoàn toàn lỗi chặn nhầm ở mốc 26-29 calls).
- **Acquire Permit (`acquire_attempt`):**
  - **Tích hợp RPC Production (Primary Path):** Gọi `review_acquire_attempt(p_operation_id, p_attempt_id)` thuộc migration `008_stage3_review_acquire_attempt_rpc.sql`. Stored procedure thực thi trong 1 transaction duy nhất với `SELECT ... FOR UPDATE` trên bảng `exam_sessions`, đảm bảo kiểm tra replay, trần operation (4), trần session (30), và tăng `gemini_review_calls` hoàn toàn nguyên tử giữa nhiều worker/process độc lập.
  - **Adapter Offline / Fallback Path (Atomic CAS):** Khi chạy offline hoặc RPC chưa sẵn sàng, repository tự động chuyển sang mô hình Atomic CAS (Compare-And-Swap):
    - Ghi bản ghi `review_attempts` với `status = 'requested'` và xử lý unique constraint `attempt_id` để phát hiện replay.
    - Thực thi SQL CAS: `UPDATE exam_sessions SET gemini_review_calls = current_calls + 1 WHERE id = session_id AND gemini_review_calls = current_calls`.
    - Nếu `rowcount == 0` (bị worker khác tranh chấp quota ở mốc biên 29 calls): CAS thất bại, cập nhật bản ghi sang `status = 'denied'` và trả `dispatch_permitted = False` (fail closed, triệt tiêu 100% rủi ro oversubscription).
    - Nếu CAS thành công: cập nhật `status = 'granted'` và trả `dispatch_permitted = True`.
- **TX2 & Emergency Rollback (No Refund):**
  - Không thực hiện bất kỳ phép hoàn trả (refund) quota nào, vì counter session đã phản ánh chính xác số permit thực tế đã commit.
  - Xóa bỏ triệt để nguy cơ hoàn trả làm mất permit đã cấp khi gặp sự cố mạng hoặc `REVIEW_PERMIT_UNCERTAIN`.
- **Ranh giới Schema Dependency & Tích hợp:** Cung cấp migration `008_stage3_review_acquire_attempt_rpc.sql` và cập nhật `backend/scripts/schema.sql` định nghĩa bảng `review_attempts` cùng stored procedure `review_acquire_attempt` theo đúng chuẩn `docs/api/review-rpc-contract.md`. Bộ test suite bao phủ 100% cả RPC path và Barrier CAS fallback.


### 3.4. State Guards & Lock Registry
- **Chặn Revert câu chưa từng biến thể:** Ném ngay `HTTP 400 ERR_QUESTION_NOT_REGENERATED`.
- **Accept SQL Check-and-Act:** UPDATE câu `pending_review` $\rightarrow$ `approved` với kiểm tra rowcount.
- **Lock Registry:** Dùng `WeakValueDictionary[UUID, asyncio.Lock]` đồng bộ trong event loop, giải phóng tự động qua GC.

---

## 4. Kế Hoạch File Triển Khai

| Lượt / file | Mục đích | Output mong muốn | Cách kiểm |
|---|---|---|---|
| Lượt 0: Schema & Migrations | Bổ sung `regeneration_id` và audit log | `004_stage3_review_and_shuffle.sql` (Hùng) hoặc `005_regeneration_id.sql` | SQL schema check |
| Lượt 1: `backend/app/models/schemas.py` | Schemas, `ReserveResult` enum, `ReviewDomainException` | Request/Response models, Error handlers | `mypy backend/app/models/schemas.py` |
| Lượt 2: `backend/app/services/review/repository.py` | Thao tác DB với `rowcount == 1`, TX2 idempotent, emergency rollback | Repository functions | Unit tests mock DB |
| Lượt 3: `backend/app/services/review/service.py` | Orchestration TX1 $\rightarrow$ AI timeout 45s $\rightarrow$ TX2 retry backoff | ReviewService, SessionLockRegistry | Service tests |
| Lượt 4: `backend/app/api/routes/review.py` | FastAPI Router cho 4 endpoints | Route handlers | FastAPI TestClient |
| Lượt 5: `backend/tests/services/test_review_lifecycle.py` | 18 ca kiểm thử tích hợp chuyên sâu | Bộ test suite 18/18 pass | `pytest backend/tests/services/test_review_lifecycle.py -v` |

---

## 5. Danh Mục 18 Ca Kiểm Thử Tự Động Bắt Buộc

1. `test_connection_pool_zero_checkout_during_ai` (P0)
2. `test_tx2_network_error_after_commit_is_idempotent` (P0)
3. `test_emergency_rollback_idempotent_no_double_refund` (P0)
4. `test_emergency_rollback_after_tx2_succeeded_no_refund` (P0)
5. `test_stale_guard_and_emergency_rollback_race` (P0)
6. `test_multi_version_required_count_invariant` (P0)
7. `test_quota_marginal_success_at_26` (P0)
8. `test_quota_blocked_at_27` (P0)
9. `test_revert_never_regenerated_question_returns_400` (P1)
10. `test_concurrent_accept_while_other_question_regenerating` (P1)
11. `test_revert_idempotency_returns_200` (P1)
12. `test_immediate_rollback_and_quota_refund_on_ai_timeout` (P1)
13. `test_partial_unique_index_order_prevents_violation` (P1)
14. `test_idor_cross_session_returns_404` (P1)
15. `test_session_status_guards` (P1)
16. `test_can_finalize_matrix_multi_version` (P1)
17. `test_review_logs_audit_integrity` (P1)
18. `test_safe_invalidation_unsets_finalized` (P1)

---

## 6. Lệnh Kiểm Tra Nghiệm Thu

```bash
ruff check backend/app/services/review backend/app/api/routes/review.py
mypy backend/app/services/review --strict
pytest backend/tests/services/test_review_lifecycle.py -v
```


---

## 7. Bàn Giao & Kết Quả Thực Tế — Đồng Bộ Hóa Toàn Diện Với Hùng (TASK-302)

- **F01/F02/F05/F06 (Reservation, Candidate Payload & Strict Audit Actor):**
  - Đảm bảo snapshot canonical độc lập khi AI sinh biến thể mới.
  - Toàn bộ thao tác ghi log `review_logs` luôn kèm `user_id` xác thực (tuân thủ `CHECK (user_id IS NOT NULL)` của Migration 006).
  - Tự động thu hồi câu treo `regenerating > 3 phút` (Stale Recovery) khi gọi endpoint tiến độ review.
- **F03 (Canonical Invariance):**
  - Bảo toàn tuyệt đối mô hình dữ liệu chuẩn của câu bị reject, sinh bộ đáp án mới độc lập.
- **F04 (Production Dependency Injection):**
  - Dependency `get_ai_generator` ném `503 Service Unavailable` nếu chưa cấu hình AI Adapter trên môi trường thật, ngăn ngừa âm thầm dùng mock data.
- **F07 (Attempt Accounting & Durable AttemptPermit Integration — Giải Quyết Triệt Để 3 Lỗi Biên Theo Kiến Trúc A):**
  - **Khắc phục Lỗi 1 (Quota Boundary 26 calls):** Chuyển từ upfront reservation sang Pure Per-Acquire Atomic Accounting. TX1 chỉ kiểm tra trần session (< 30) mà không trừ trước 4 calls. Request ở mốc 26–29 calls được cấp phép bình thường, không bị false rejection.
  - **Khắc phục Lỗi 2 (Non-Durable RAM State):** Xóa bỏ toàn bộ biến RAM (`self._operation_permits`, `self._operation_attempts`). Trực tiếp lưu và kiểm tra chống replay bằng bảng CSDL `review_attempts` với `INSERT ... ON CONFLICT (attempt_id) DO NOTHING`. Hoạt động an toàn 100% trên môi trường multi-worker/multi-process.
  - **Khắc phục Lỗi 3 (Rollback Quota Refund & Uncertain Grant):** Bỏ toàn bộ logic refund quota trong `complete_regeneration_tx` và `emergency_rollback_tx`. Session counter phản ánh chính xác số permit thực tế đã commit. Khi gặp `REVIEW_PERMIT_UNCERTAIN` hoặc lỗi mạng, các permit đã cấp được bảo toàn nguyên vẹn (Conservative Accounting), không bao giờ bị hoàn mất.
  - **Ánh xạ lỗi chuẩn xác:** `REVIEW_QUOTA_EXHAUSTED` $\rightarrow$ HTTP 429; `OPERATION_EXHAUSTED` $\rightarrow$ HTTP 429; `REVIEW_ATTEMPT_REPLAYED` $\rightarrow$ HTTP 409; `REVIEW_PERMIT_UNCERTAIN` / `REVIEW_PERMIT_INVALID` $\rightarrow$ HTTP 502; `DB_UNAVAILABLE` $\rightarrow$ HTTP 503 (fail-closed, không grant mù).



- **C01 (Model A Concurrency):**
  - Áp dụng khóa mức session: Chỉ cho phép duy nhất 1 câu hỏi đang trong tiến trình sinh lại (`regenerating`) trên mỗi session đề. Thao tác thứ 2 bị từ chối với HTTP 409 (`ERR_SESSION_BUSY_REGENERATING`).
- **C02 (Readiness & Progress Slots Shape):**
  - Mở rộng `ReviewProgressResponse` với các trường slot chuẩn hóa: `expected_slots`, `current_slots`, `approved_slots`, `regenerating_slots`, `missing_slots`, `duplicate_slots`, `ready`. Duy trì 100% backward compatibility cho frontend.
- **Invalidation Toàn Diện (Session-wide Reshuffle Invalidation):**
  - Khi reject/revert trên phiên đã shuffle: xóa sạch `answer_keys` cũ, reset `is_finalized = false`, xóa trắng `shuffle_seed` và `permutations`, hạ session status về `generated`.
- **Kết Quả Kiểm Thử Thực Tế:**
  - `pytest backend/tests/services/test_review_lifecycle.py backend/tests/api/test_review_api.py -v`: **46/46 tests passed (100% bao gồm 11 regression test cases của F07)**.
  - `ruff check`: All checks passed.
  - `ruff format --check`: All files already formatted.
- **Trạng thái PR:** PR #28 đã sẵn sàng 100% để chuyển sang **Ready for Review** và bàn giao cho Hùng (@benalexx007) duyệt (Approve).

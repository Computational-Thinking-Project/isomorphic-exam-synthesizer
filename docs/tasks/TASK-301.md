# TASK-301 — Plan và Bàn Giao: API Thẩm Định 1-1, Vòng Đời `is_current`, Revert Nguyên Tử & Safe Re-shuffle Invalidation

- **Nguồn giao việc:** [W3_ASSIGNMENT.md](W3_ASSIGNMENT.md) (v2.1; 28/10/2026), [w3.md](../../w3.md)
- **Phụ trách:** Duy (`johannguyen015` — Lead); Hùng (`benalexx007` — Contributor)
- **Reviewer:** Hùng (`benalexx007` — đã chốt)
- **Repo/nhánh:** `feat/duy-task-301-review-lifecycle-api`; PR: [#28](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28)
- **Hạn đợt:** tối thứ 3 03/11/2026; **ETA task:** Thứ 7 31/10/2026 (Duy xác nhận)
- **Phiên bản:** v6.1 (Remediation Plan: [TASK-301_REMEDIATION_PLAN.md](TASK-301_REMEDIATION_PLAN.md))

---

## 1. Sáu Nguyên Tắc Bất Biến (Phải Tuân Thủ Tuyệt Đối)

1. **Single Source of Truth cho Quota:** Chỉ một transaction được phép thay đổi `gemini_review_calls`: TX1 (+4), TX2 (refund `4 - actual_k`), Emergency Rollback (-4). Không có nơi nào khác được can thiệp vào quota.
2. **Idempotency qua UNIQUE Constraint:** Cột `regeneration_id UUID NULL UNIQUE` trên câu mới là rào chắn CSDL ngăn chặn double-insert và double-refund khi rớt mạng hoặc retry.
3. **Atomic Ownership qua Rowcount:** Chỉ tiến trình nào UPDATE được `status = 'regenerating' -> X` với `rowcount == 1` mới sở hữu quyền refund/chuyển trạng thái. Ai `rowcount == 0` tuyệt đối không thao tác.
4. **Thứ tự Invariant:** UPDATE câu cũ (`is_current = false`) trước $\rightarrow$ INSERT câu mới (`is_current = true`) sau để bảo vệ Partial Unique Index.
5. **Không giữ kết nối DB khi gọi AI:** Tách biệt hoàn toàn TX1, pha gọi Gemini AI (không giữ DB connection), và TX2.
6. **Concurrency Model B:** Cho phép reject các câu khác nhau song song; không block thao tác Accept trên câu khác khi có câu đang regenerating; chặn Shuffle/Finalize nếu còn câu regenerating.

---

## 2. Ma Trận Trạng Thái Hệ Thống (State Transition Matrix)

### 2.1. Ma trận Trạng thái Phiên (Session Level Guards)
| Endpoint | Session `generating` | Session `generated` / `reviewed` | Session `approved` / `exported` |
|---|---|---|---|
| `POST .../accept` | `HTTP 409 Conflict` | ✅ Cho phép duyệt độc lập | `HTTP 423 Locked` |
| `POST .../reject` | `HTTP 409 Conflict` | ✅ Cho phép xử lý (nếu quota còn đủ $\ge 3$) | `HTTP 423 Locked` |
| `POST .../revert` | `HTTP 409 Conflict` | ✅ Cho phép xử lý độc lập | `HTTP 423 Locked` |
| `GET .../progress`| ✅ Trả về tiến độ | ✅ Trả về tiến độ (Read-only) | ✅ Trả về tiến độ (Read-only) |

*Nguyên tắc:* Nếu session đang có câu `regenerating`, endpoint `GET /progress` trả về `can_finalize = False` để ngăn chặn shuffle khi chưa ổn định.

### 2.2. Ma trận Trạng thái Câu hỏi (Question Level Guards)
| Hành động | Câu `is_current = false` | Câu `pending_review` (`is_current=true`) | Câu `regenerating` (`is_current=true`) | Câu `approved` (`is_current=true`) |
|---|---|---|---|---|
| **Accept** | `HTTP 400 Bad Request` | ✅ Chuyển `approved` (`rowcount=1`) | `HTTP 409 Conflict` | `HTTP 200 OK` (Idempotent) |
| **Reject** | `HTTP 400 Bad Request` | ✅ Reserve 3 calls & Kích hoạt 2-TX | `HTTP 409 Conflict` | ✅ Cho phép reject lại (hạ shuffle) |
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
  - Refund phần dư `3 - actual_calls` và ghi log `review_logs` (`action_type = 'REJECT'`).
- **Emergency Rollback (`emergency_rollback_tx`):**
  - SELECT theo `regeneration_id`: nếu câu mới đã commit $\rightarrow$ return `False` ngay (không refund, không đổi trạng thái).
  - UPDATE câu cũ `status = 'pending_review'` với điều kiện `status = 'regenerating'`: chỉ khi `rowcount == 1` mới trừ quota -3 và ghi log `REJECT_FAILED`.

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

### 3.3. Quota Max Reservation (Hằng Số 4 Calls)
- Hằng số: `MAX_AI_CALLS_PER_REJECT = 4` (khớp với hợp đồng TASK-304: 1 initial call + tối đa 2 math retries + 1 format/schema repair).
- TX1: Tăng quota +4 (`WHERE calls + 4 <= 30`). Nếu không đủ $\rightarrow$ `HTTP 429 ERR_REVIEW_QUOTA_EXHAUSTED`.
- TX2: Hoàn lại `4 - actual_calls`.
- AI fail / timeout: Hoàn lại toàn bộ 4 calls.

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

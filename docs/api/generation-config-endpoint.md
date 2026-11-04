# Contract Tài Liệu: Generation Config RPC & Worker Operations (TASK-207a/b)

Tài liệu này xác định hợp đồng giao tiếp (API / Database Stored Procedure Contract) cho pha cấu hình Stage 2 và quy trình thực thi worker sinh đề hàng loạt (Generation Job Worker Lifecycle).

---

## 1. RPC `save_generation_config` (Stage 2 Configuration)

### 1.1. Chữ ký hàm & Quyền thực thi
```sql
FUNCTION public.save_generation_config(
  p_session_id UUID,
  p_n_versions INT,
  p_active_variation_modes JSONB DEFAULT '[]'::jsonb,
  p_ordering_preferences JSONB DEFAULT '{"shuffle_questions": true, "shuffle_options": true}'::jsonb
) RETURNS JSONB;
```
- **Quyền gọi (ACL):** `authenticated`, `service_role` (REVOKE `PUBLIC`, `anon`).
- **Xác thực:** Chủ sở hữu phiên (`auth.uid() = session.user_id`) hoặc `service_role`.

### 1.2. Ràng buộc & Tiền điều kiện (Invariants)
1. Phiên thi phải ở trạng thái `blueprinted` hoặc `configured`.
2. `p_n_versions` bắt buộc từ 1 đến 4.
3. `p_active_variation_modes` bắt buộc là JSON array gồm các chuỗi mode không rỗng:
   - Chấp nhận `[]` (chế độ sao chép đề gốc không dùng biến thể toán học).
   - Mọi mode trong mảng phải được **100% câu hỏi nguồn (question blueprints)** trong phiên hỗ trợ (giao tập hợp mode).
   - Giữ nguyên định dạng hoa/thường (case-sensitive) của mode ID.
   - Toàn bộ confirmed blueprints của phiên phải có `variation_modes` đúng định dạng mảng (F01).
4. `p_ordering_preferences` bắt buộc là JSON object có 2 trường boolean `shuffle_questions` và `shuffle_options`.
5. Phiên thi phải có từ 1 đến 20 câu hỏi nguồn (`source_questions`), tất cả đều đã có blueprint được xác nhận (`confirmed_at IS NOT NULL`).

### 1.3. Response Payload (200 OK)
```json
{
  "success": true,
  "session_id": "c1f7b822-7772-4e0e-9411-cf974205c317",
  "config_id": "a9b8c7d6-e5f4-4321-abcd-0123456789ab",
  "status": "configured",
  "config": {
    "n_versions": 4,
    "active_variation_modes": ["NUMERICAL", "context_swap"],
    "ordering_preferences": {
      "shuffle_questions": true,
      "shuffle_options": true
    }
  }
}
```

---

## 2. Vòng đời Worker: Bộ RPCs Điều Phối Sinh Đề (TASK-207b)

### 2.1. `claim_generation_job`
Khóa phiên làm việc, cấp phát fencing token (`active_job_id`) và chuyển trạng thái sang `generating`.
```sql
FUNCTION public.claim_generation_job(
  p_session_id UUID,
  p_is_retry BOOLEAN DEFAULT FALSE
) RETURNS JSONB;
```
- **Quyền:** `authenticated`, `service_role`.
- **Ràng buộc:** Nếu `p_is_retry = false`, session phải ở trạng thái `configured`. Nếu `p_is_retry = true`, session phải ở trạng thái `partial_generated` hoặc `failed`.
- **Response:**
```json
{
  "success": true,
  "session_id": "c1f7b822-7772-4e0e-9411-cf974205c317",
  "job_id": "d1e2f3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a",
  "is_retry": false,
  "config": {
    "n_versions": 4,
    "active_variation_modes": ["NUMERICAL"],
    "ordering_preferences": {"shuffle_questions": true, "shuffle_options": true}
  },
  "current_quota": 0,
  "committed_targets": [
    {"version_code": "101", "source_question_id": "..."}
  ]
}
```

### 2.2. `reserve_generation_quota`
Đặt trước quota gọi Gemini AI (giới hạn cứng 250 calls/session).
```sql
FUNCTION public.reserve_generation_quota(
  p_session_id UUID,
  p_calls_requested INT,
  p_job_token UUID
) RETURNS JSONB;
```
- **Quyền:** `service_role` ONLY.
- **Ràng buộc:** Fencing token `p_job_token` phải khớp với `exam_sessions.active_job_id`. Tổng quota không vượt quá 250.

### 2.3. `persist_version_question`
Ghi nhận câu hỏi biến thể an toàn, chống zombie worker và bảo vệ tính bất biến của câu hỏi đã commit (F03/F04/F05).
```sql
FUNCTION public.persist_version_question(
  p_session_id UUID,
  p_job_token UUID,
  p_version_index INT,
  p_source_question_id UUID,
  p_question_no INT,
  p_content TEXT,
  p_options JSONB,
  p_correct_key TEXT,
  p_solution_md TEXT,
  p_has_warning BOOLEAN DEFAULT FALSE
) RETURNS JSONB;
```
- **Quyền:** `service_role` ONLY.
- **Ràng buộc:**
  1. `p_job_token` phải khớp `active_job_id`.
  2. `p_version_index` không được vượt quá `n_versions` đã cấu hình (F04).
  3. Nếu slot `(version_id, source_question_id)` đã commit nội dung:
     - Replay cùng payload $\rightarrow$ thành công an toàn (idempotent).
     - Payload khác $\rightarrow$ ném lỗi SQLSTATE `23505` (F03).
  4. Tự động cập nhật `exam_sessions.updated_at = now()` trong cùng transaction (F05).

### 2.4. `finish_generation_job`
Kết thúc tiến trình sinh đề, xác thực tính đầy đủ Cartesian của ma trận đề thi và giải phóng fencing token (F04).
```sql
FUNCTION public.finish_generation_job(
  p_session_id UUID,
  p_outcome TEXT, -- 'generated', 'partial_generated', 'failed'
  p_job_token UUID
) RETURNS JSONB;
```
- **Quyền:** `service_role` ONLY.
- **Cartesian Completeness Guard (F04):** Khi `p_outcome = 'generated'`, RPC bắt buộc xác minh 100% các cặp `(version_code, source_question_id)` thuộc `1..n_versions` đều có bản ghi `version_questions` mang `is_current = TRUE`. Nếu thiếu câu hoặc sai vị trí $\rightarrow$ từ chối với SQLSTATE `22023`.

### 2.5. `fail_stale_generation_job`
Dọn dẹp các job worker bị treo/crash dựa trên timeout `updated_at`.
```sql
FUNCTION public.fail_stale_generation_job(
  p_session_id UUID,
  p_cutoff_seconds INT DEFAULT 720
) RETURNS JSONB;
```
- **Quyền:** `service_role` ONLY.

---

## 3. Bảng Ánh Xạ SQLSTATE & Mã Lỗi Nghiệp Vụ

| SQLSTATE | Tình huống phát sinh | HTTP Status tương ứng |
|---|---|---|
| `P0002` | Session không tồn tại | `404 Not Found` |
| `42501` | Sai quyền hạn (không chính chủ hoặc gọi nhầm RPC worker) | `403 Forbidden` |
| `22023` | Dữ liệu cấu hình không hợp lệ: số mã đề ngoài 1-4, modes không khớp Blueprint, blueprint sai cấu trúc (F01), hoặc ma trận DB chưa đủ khi finish (F04) | `422 Unprocessable Entity` / `400 Bad Request` |
| `55006` | Tranh chấp Fencing token (`active_job_id` mismatch) hoặc session đang bị claim bởi worker khác | `409 Conflict` |
| `23505` | Cố ý ghi đè câu hỏi đã commit bằng nội dung khác khi sinh bù (F03) | `409 Conflict` |
| `54000` | Vượt trần quota 250 cuộc gọi Gemini AI | `429 Too Many Requests` |

---

## 4. Bảo Vệ Cột Worker & Column-Level Security (F07)

Bảng `exam_sessions` được bảo vệ hai tầng chống việc can thiệp trực tiếp từ client `authenticated`:
1. **Column-Level Privileges:** `REVOKE UPDATE (active_job_id, gemini_call_count) ON public.exam_sessions FROM PUBLIC, anon, authenticated;`.
2. **Database Trigger Guard (`trg_guard_exam_sessions_worker_columns`):**
   - Chặn client tự ý INSERT phiên thi mới với `active_job_id IS NOT NULL`, `gemini_call_count > 0`, hoặc `status = 'generating'`.
   - Chặn client tự ý UPDATE thay đổi `active_job_id`, `gemini_call_count` hoặc tự chuyển trạng thái `generating`.
   - Các RPC của hệ thống sử dụng session-level flag `app.internal_worker_rpc` để thực hiện mutation hợp lệ.

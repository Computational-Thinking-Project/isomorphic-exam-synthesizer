# API Contract: GET /api/sessions/{session_id}/review/snapshot

**Endpoint:** `GET /api/sessions/{session_id}/review/snapshot`  
**Authentication:** `Authorization: Bearer <JWT>` (Owner-authenticated)  
**Response Headers:** `Cache-Control: no-store`, `Content-Type: application/json`

---

## 1. Mục đích & Tổng quan

Endpoint này cung cấp snapshot hiện hành của quy trình Review (Stage 3) trước khi shuffle:
- Trả về danh sách câu nguồn đã được đóng băng và xác nhận (`confirmed_sources`), giữ nguyên thứ tự và nội dung chuẩn.
- Dựng ma trận đầy đủ $N \times M$ slots ($N$ phiên bản đề $\times M$ câu nguồn).
- Đối với mỗi slot, chỉ trả về đúng **1 candidate hiện hành** (`is_current = true`), hoặc `candidate: null` nếu slot chưa có biến thể (missing slot).
- Cung cấp nguồn gốc (`origin`) và nguồn báo cáo kiểm định toán học (`validation_source`, `validation_report`).
- Tính toán tiến độ thẩm định (`progress`) và token xác định tính tươi mới (`freshness_token`) nguyên tử trong cùng một truy vấn CSDL.

> [!IMPORTANT]
> **Quy tắc bảo vệ dữ liệu:**
> 1. Endpoint không sử dụng `service_role`. Người dùng chỉ đọc được phiên thi thuộc sở hữu của mình (`auth.uid() = session.user_id`).
> 2. Các phiên thi của người khác hoặc không tồn tại sẽ bị ẩn (trả về `404 Not Found`) để tránh rò rỉ sự tồn tại của tài nguyên (RLS concealment).
> 3. `read_only` là cờ gợi ý cho giao diện người dùng, không thay thế việc kiểm tra quyền ở các Write API.

---

## 2. Ma trận Trạng thái Phiên (Session State Matrix)

| Session Status | HTTP Status | Điều kiện & Hành vi |
| :--- | :---: | :--- |
| `draft`, `blueprinted`, `configured` | `409 Conflict` | Chưa có snapshot review để hiển thị. Mã lỗi: `ERR_REVIEW_STATE_CONFLICT`. |
| `generating` | `409 Conflict` | Tiến trình sinh đang chạy; client cần theo dõi qua SSE của Stage 2. |
| `partial_generated` | `200 OK` | Đã có frozen evidence; hiển thị các slot còn thiếu (`candidate: null`) và cờ `read_only: true`. |
| `generated` | `200 OK` | Snapshot current đầy đủ trước khi shuffle, cờ `read_only: false`. |
| `reviewed` (trước shuffle) | `200 OK` | Trả về candidate đã duyệt, cờ `read_only: false`. |
| `reviewed` (sau shuffle) | `409 Conflict` | Đã hoàn tất shuffle; client cần chuyển sang API Post-shuffle Preview (W4-MVP-05). |
| `failed` | `200 OK` / `409` | Trả về `200 OK` với `read_only: true` nếu có frozen evidence đọc được; nếu không có bằng chứng hợp lệ trả về `409`. |
| `approved`, `exported` | `423 Locked` | Phiên đề đã được duyệt và khóa bất biến vĩnh viễn (Content Lock). |

---

## 3. Cấu trúc Response (200 OK)

### 3.1. Schema Định nghĩa

```typescript
interface ReviewSnapshotResponse {
  session_id: string; // UUID
  session_status: string; // "generated" | "partial_generated" | "reviewed" | "failed"
  read_only: boolean;
  confirmation_id: string; // UUID
  job_snapshot_id: string; // UUID
  confirmed_source_hash: string; // SHA-256 hex string
  freshness_token: string; // Deterministic state hash
  progress: ReviewSnapshotProgress;
  sources: ReviewSnapshotSource[];
  versions: ReviewSnapshotVersion[];
}

interface ReviewSnapshotProgress {
  expected_slots: int;
  current_slots: int;
  approved_slots: int;
  missing_slots: int;
  ready?: boolean;
}

interface ReviewSnapshotSource {
  source_question_id: string; // UUID
  question_no: number;
  source_revision_id: string; // UUID
  content: string;
  options: string[]; // Exactly 4 strings: [A, B, C, D]
  correct_key: string; // "A" | "B" | "C" | "D"
  solution_md: string | null;
}

interface ReviewSnapshotVersion {
  version_index: number; // 1..4
  version_code: string; // e.g. "101", "102"
  version_id: string | null; // UUID if persisted, null if pending
  slots: ReviewSnapshotSlot[];
}

interface ReviewSnapshotSlot {
  source_question_id: string; // UUID
  question_no: number;
  candidate: ReviewSnapshotCandidate | null;
}

interface ReviewSnapshotCandidate {
  candidate_id: string; // UUID (version_questions.id) - Dùng ID này để gọi /accept, /reject, /revert
  status: "pending_review" | "approved" | "rejected" | "regenerating";
  content: string;
  options: string[]; // Exactly 4 strings: [A, B, C, D]
  correct_key: string; // "A" | "B" | "C" | "D"
  solution_md: string | null;
  has_warning: boolean;
  validation_report: Record<string, any> | null;
  validation_source: "version_question" | "generation_result" | "unavailable";
  origin: "ai_generated" | "original_clone" | "regenerated" | "reverted" | "confirmed_source_fallback" | "unknown";
  is_reverted: boolean;
  updated_at: string; // ISO 8601
}
```

---

## 4. Invariants & Quy tắc Ràng buộc

1. **Thứ tự ổn định (Deterministic & Stable Ordering):**
   - Danh sách `sources` sắp xếp tăng dần theo `question_no` từ `confirmed_sources`.
   - Danh sách `versions` sắp xếp theo `version_index` ($1 \dots N$).
   - Danh sách `slots` trong mỗi version có đúng $M$ phần tử, thứ tự `source_question_id` khớp tuyệt đối với thứ tự trong `sources`.
   - F5 hoặc reload không làm thay đổi thứ tự hay mapping giữa nguồn và các candidate.
2. **Current-Only Candidate:**
   - Mỗi slot chỉ chứa tối đa 1 candidate có `is_current = true`. Tuyệt đối không lấy candidate lịch sử để lấp chỗ.
   - Nếu slot chưa có current row, `candidate = null`.
   - Nếu phát hiện nhiều hơn 1 candidate `is_current = true` cho cùng một slot `(version_id, source_question_id)`, hệ thống lập tức fail-closed với mã lỗi `503 Service Unavailable`.
3. **Quy tắc Provenance (`origin`):**
   - `regenerated`: Khi `version_questions.regenerated_from_id IS NOT NULL`.
   - `reverted`: Khi `version_questions.is_reverted = TRUE`.
   - `original_clone`: Khi kết quả sinh từ Stage 2 ghi nhận `result_kind = 'ORIGINAL_CLONE'`.
   - `ai_generated`: Khi câu được sinh thành công qua mô hình sinh biến thể AI (`result_kind = 'AI_RESULT'`).
   - `unknown`: Khi không đủ chứng cứ xác định nguồn gốc tin cậy.
4. **Quy tắc Validation Report:**
   - Ưu tiên đọc báo cáo từ `version_questions.validation_report` (áp dụng cho câu sinh lại hoặc chỉnh sửa trực tiếp).
   - Nếu báo cáo rỗng (`{}` hoặc `null`), đối chiếu `generation_target_results.raw_result.validation` bằng phép join chính xác `(version_question_id, session_id, snapshot_id)`.
   - Nếu không có chứng cứ hợp lệ, gán `validation_report: null` và `validation_source: "unavailable"`. Không tự ý coi `{}` là đã passed.
5. **Freshness Token:**
   - Token là chuỗi băm xác định tính từ định danh snapshot nguồn đóng băng và trạng thái hiện hành của toàn bộ các candidate (ID, status, timestamp, warning).
   - Hai lần GET liên tiếp khi CSDL không đổi sẽ trả về cùng một `freshness_token`. Khi có bất kỳ thay đổi nào (accept, reject, regenerate), token lập tức thay đổi.

---

## 5. Hướng dẫn Tích hợp Frontend (Stage 3 UI)

- **Định danh câu hỏi:** Sử dụng `candidate.candidate_id` làm tham số `version_question_id` cho các endpoint Write:
  - `POST /api/sessions/{session_id}/questions/{candidate_id}/accept`
  - `POST /api/sessions/{session_id}/questions/{candidate_id}/reject`
  - `POST /api/sessions/{session_id}/questions/{candidate_id}/revert`
- **Tải lại dữ liệu (Refetch):** Sau khi thực hiện bất kỳ thao tác ghi (Write) nào thành công, giao diện gọi lại `GET /api/sessions/{session_id}/review/snapshot` để cập nhật trạng thái mới nhất và làm mới token.
- **Không dùng `question_no` làm ID:** Thứ tự `question_no` có thể thay đổi sau khi shuffle, do đó không dùng số thứ tự câu làm khóa chính trong state UI.


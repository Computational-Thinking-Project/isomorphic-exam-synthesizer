# EXT-01 / 04 — Teacher feedback qua targeted AI retries

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Bắt đầu mapping reasons, prompt và regression tests ngay; chưa phụ thuộc quyết định mode để làm phần feedback.
- **File / đầu vào:** `backend/app/services/generation/{targeted_service,service,prompts}.py`; enum gói 01, receipt gói 02.
- **Thứ tự làm:** Thêm teacher feedback cố định tách repair feedback; truyền từ validated receipt; giữ qua mọi retry; giữ permit/timeout/fingerprint Stage 2; cập nhật mocks và targeted tests.
- **Đầu ra / điều kiện hoàn thành gói:** Targeted feedback chạy end-to-end với gói 02/03. Phần thay variation modes/clone guard thuộc gói 06 và chỉ tích hợp sau G2.
- **Kiểm chứng:** A02-09/10/21; live AI khi đủ môi trường, chưa được thay bằng mock evidence. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** chưa xác nhận code/test của gói. Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-3-4"></a>

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

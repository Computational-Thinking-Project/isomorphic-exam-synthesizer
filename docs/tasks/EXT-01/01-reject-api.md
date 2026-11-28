# EXT-01 / 01 — Reject API và chuẩn hóa reasons

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Ưu tiên đầu tiên; đủ thiết kế Q01 để chuẩn bị ngay, code theo lịch từ 27/11.
- **File / đầu vào:** `backend/app/models/schemas.py`, `backend/app/api/routes/review.py`; contract Q01.
- **Thứ tự làm:** Thêm enum/DTO optional body; canonicalize sort + deduplicate; kiểm sai payload trước DB/AI; giữ caller MVP và signature service; cập nhật API tests.
- **Đầu ra / điều kiện hoàn thành gói:** DTO, canonical reasons và tests API dùng được cho gói 02/03/04. Chưa mở hành vi reasons trên hệ thống khi DB/AI chưa nối đầy đủ.
- **Kiểm chứng:** A02-01/02/03/29; API tests trong file 08. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** chưa xác nhận code/test của gói. Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-3-1"></a>

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

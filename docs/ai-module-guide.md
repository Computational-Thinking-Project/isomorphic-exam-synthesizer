> AI W2 dùng gateway async, Blueprint chung và generator kèm solution: xem [hợp đồng tích hợp hiện tại](ai-w2-integration.md). Các API generator đồng bộ bên dưới là legacy; routes W2 phải dùng service mới.

# Hướng Dẫn Tích Hợp Module AI & Isomorphic Generator (TV5)

> **Người phụ trách:** TV5 (AI Integration & Generator)  
> **Model mặc định:** `gemini-3.5-flash-lite`  
> **Branch làm việc:** `feat/task-106-gemini-client`  
> **Ngày cập nhật:** 16/10/2026

---

## 1. Mục đích tài liệu

Tài liệu này cung cấp toàn bộ quy cách kỹ thuật (**Input**, **Output**, **Cách chạy** và **Bàn giao**) của module AI cho toàn bộ thành viên trong nhóm (**TV1 $\rightarrow$ TV7**) để phối hợp cắm đầu nối trực tiếp mà không cần hỏi qua lại.

---

## 2. Input Specs (Module AI cần gì từ nhóm)

### Gemini key pool

Backend nhận `GEMINI_API_KEY` cũ và ba biến tùy chọn `GEMINI_API_KEY_1`,
`GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`. Bỏ key rỗng/trùng; mỗi request sinh câu,
retry hoặc AI schema repair chọn ngẫu nhiên một key trong pool. Chọn ngẫu nhiên
có thể lặp lại cùng key, không bảo đảm phân phối bằng nhau trong một batch nhỏ.
Truyền `GeminiClient(api_key=...)` sẽ chỉ dùng key được chỉ định.

SDK tự retry được tắt để mỗi lần retry do client quản lý đều chọn lại key.
Không tự tạo thêm lượt retry khi hết quota. Các key cùng Google Cloud project
chia sẻ rate limit; pool không giảm tổng request/token và không bảo đảm tránh 429.
Docker backend đã đọc `.env` qua `env_file`; sau thay đổi cần recreate container
(và rebuild để nhận code mới). Không cần thêm dependency cho key pool.
Key thật chỉ nằm trong `.env` được Git ignore; `.env.example` chỉ chứa placeholder.

### 2.1. Cấu hình & Biến môi trường (Dành cho TV6 cấu hình Docker)
Module AI đọc từ `backend/app/core/config.py` và yêu cầu 2 biến trong `.env`:
```env
GEMINI_API_KEY=AIzaSy...  # Lấy từ Google AI Studio
GEMINI_MODEL=gemini-3.5-flash-lite
```

### 2.2. Dữ liệu câu hỏi nguồn (`SourceQuestion`) — Nhận từ TV7 / Parser
Mỗi câu hỏi gốc cần truyền vào hàm sinh phải tuân theo model Pydantic:
```json
{
  "id": "q101",
  "question_text": "Tìm nghiệm của phương trình $x^2 - 3x + 2 = 0$?",
  "options": ["$x=1; x=2$", "$x=2; x=3$", "$x=-1; x=-2$", "$x=0$"],
  "correct_answer": "$x=1; x=2$",
  "solution": "Ta có $(x-1)(x-2)=0 \\implies x=1$ hoặc $x=2$."
}
```

### 2.3. Payload gọi sinh đề từ Frontend / Router (Stage 02)
Giảng viên chỉ cần chọn số lượng $N$ đề thi cần tạo (Blueprint là hộp đen tự động):
```json
{
  "source_exam_id": "exam_math_12_midterm",
  "n_versions": 4
}
```

---

## 3. Output Specs (Kết quả trả ra của Module AI)

### 3.1. Đối tượng biến thể chuẩn (`GeneratedVariant`)
Mỗi biến thể sinh ra sẽ khớp 100% với schema và fixture mẫu tại `contracts/fixtures/variant.json`:
```json
{
  "variant_id": "var_q101_v1",
  "source_question_id": "q101",
  "question_text": "Tìm nghiệm của phương trình $x^2 - 5x + 6 = 0$?",
  "options": [
    "$x=2; x=3$",
    "$x=1; x=6$",
    "$x=-2; x=-3$",
    "$x=0; x=5$"
  ],
  "correct_answer": "$x=2; x=3$",
  "solution_steps": "1. Phân tích thành nhân tử: $(x-2)(x-3) = 0$.\n2. Suy ra $x = 2$ hoặc $x = 3$.\n3. Vậy tập nghiệm là $S = \\{2; 3\\}$.",
  "seed": 42
}
```

> **Lưu ý cho TV2 (Frontend KaTeX):** Tất cả công thức toán học đều nằm trong dấu `$...$` hoặc `$$...$$` theo chuẩn LaTeX. Các phương án A, B, C, D là một mảng 4 phần tử duy nhất, trong đó `correct_answer` trùng khớp với 1 trong 4 phần tử này.

---

## 4. Cách chạy & Bằng chứng kiểm thử (Execution & Evidence)

### 4.1. Chạy Unit Test kiểm tra Mock Client (Không cần API Key)
Mọi thành viên hoặc hệ thống CI/CD có thể kiểm tra module AI chạy độc lập:
```bash
pytest backend/tests/ai/test_client.py -v
```

**Bằng chứng chạy thực tế (Mock):**
```text
tests/ai/test_client.py::test_mock_gemini_client_success PASSED          [ 50%]
tests/ai/test_client.py::test_mock_gemini_client_simulate_quota PASSED   [100%]
============================== 2 passed in 0.39s ==============================
```

### 4.2. Chạy Smoke Test gọi Gemini API thật (`gemini-3.5-flash-lite`)
Lệnh chạy kiểm tra kết nối thật (yêu cầu điền `GEMINI_API_KEY` trong `.env`):
```bash
python backend/scripts/smoke_ai.py
```

**Bằng chứng chạy thực tế với Gemini 3.5 Flash-Lite:**
```text
============================================================
🚀 BẮT ĐẦU SMOKE TEST GEMINI AI CLIENT (TASK-106)
============================================================
• Model sử dụng : gemini-3.5-flash-lite
• Độ trễ phản hồi: 3.05 giây
• Kết quả kiểm chứng:
  ✓ Đủ chính xác 4 lựa chọn không trùng lặp.
  ✓ Đáp án đúng nằm trong danh sách lựa chọn.
  ✓ Định dạng LaTeX ($...$) và Pydantic Schema hoàn toàn hợp lệ.
🎉 SMOKE TEST HOÀN TOÀN THÀNH CÔNG!
```

### 4.3. Chạy Kiểm Thử Tự Động Schema Repair Pass (TASK-106b)
Module `schema_repair.py` bảo vệ hệ thống khỏi lỗi format JSON qua 2 lớp phòng vệ:
1. **Heuristic Sanitize:** Tự động bóc tách markdown fences và tự sửa các ký tự escape LaTeX (`\pm`, `\frac`, `\sqrt`) bị thiếu dấu `\`.
2. **AI-Assisted Repair Pass:** Tự động gửi lại prompt kèm lỗi Pydantic để Gemini sửa định dạng (tối đa 2 lượt retry).

### 4.4. Chạy Kiểm Thử Tự Động Pipeline Sinh Đề Đẳng Cấu (TASK-106c)
Module `generator.py` quản lý toàn bộ logic Stage 02 ($N$ đề hoàn chỉnh) và Stage 03 (tái sinh 1 câu hỏi kèm Feedback-guided Loop):
- Tự động gán seed duy nhất cho từng câu hỏi ở từng phiên bản đề để đảm bảo tính tái lập (reproducibility).
- Kiểm tra tính toàn vẹn trắc nghiệm (đúng 4 lựa chọn không trùng lặp, `correct_answer` nằm trong `options`).
- **Feedback-guided Regeneration & Self-Healing:** Nếu câu hỏi sinh ra bị lỗi hoặc bị từ chối ở tầng validation, generator tự động đưa lỗi vào context prompt để AI sửa sai ở lần retry tiếp theo.

Lệnh chạy kiểm thử toàn bộ test suite:
```bash
pytest backend/tests/ -v
```

**Bằng chứng chạy thực tế (12/12 tests passed in 0.69s):**
```text
backend\tests\ai\test_client.py::test_mock_gemini_client_success PASSED               [  8%]
backend\tests\ai\test_client.py::test_mock_gemini_client_simulate_quota PASSED        [ 16%]
backend\tests\ai\test_client.py::test_prompt_injection_detection_and_xml_escaping PASSED [ 25%]
backend\tests\ai\test_schema_repair.py::test_extract_json_str_with_markdown_fences PASSED [ 33%]
backend\tests\ai\test_schema_repair.py::test_heuristic_repair_success PASSED           [ 41%]
backend\tests\ai\test_schema_repair.py::test_ai_repair_loop_success PASSED            [ 50%]
backend\tests\ai\test_schema_repair.py::test_repair_exceed_max_attempts_raises_error PASSED [ 58%]
backend\tests\generation\test_generator.py::test_generate_n_exam_drafts_with_mock PASSED [ 66%]
backend\tests\generation\test_generator.py::test_regenerate_single_variant_with_mock PASSED [ 75%]
backend\tests\generation\test_generator.py::test_generator_detects_duplicate_options PASSED [ 83%]
backend\tests\generation\test_generator.py::test_feedback_guided_regeneration_passed_to_client PASSED [ 91%]
backend\tests\generation\test_generator.py::test_generator_retry_recovery_with_feedback PASSED [100%]
============================= 12 passed in 0.69s ==============================
```

---

## 5. BÀN GIAO CHO NGƯỜI SAU (Handoff & Next Steps)

Mục này dành cho các thành viên tiếp quản hoặc cắm đầu nối với module AI:

### 5.1. Dành cho TV3 (Backend Routes & Session Controller):
TV3 có thể cắm trực tiếp 2 hàm high-level từ `backend/app/services/generation/generator.py` vào FastAPI router:

1. **Stage 02 — Endpoint Sinh N Đề Thi (`POST /api/v1/exams/{id}/generate`):**
   ```python
   from app.services.generation.generator import generate_n_exam_drafts
   from app.models.schemas import SourceQuestion

   # Lấy danh sách câu hỏi gốc từ DB hoặc Session
   source_questions = [...]  # List[SourceQuestion]

   # Sinh N phiên bản đề thi (N=4)
   exam_packages = generate_n_exam_drafts(
       source_questions=source_questions,
       n_versions=payload.n_versions,
       base_seed=100
   )
   # Trả về List[ExamDraftPackage] cho Frontend
   ```

2. **Stage 03 — Endpoint Tái Sinh 1 Câu Hỏi Khi Giảng Viên Yêu Cầu (`POST /api/v1/exams/{id}/regenerate-question`):**
   ```python
   from app.services.generation.generator import regenerate_single_variant

   # Tái sinh với seed mới; feedback chỉ do validator nội bộ cung cấp
   new_variant = regenerate_single_variant(
       source_question=target_question,
       seed=payload.seed,
       feedback=validation_feedback  # Không nhận prompt từ giáo viên
   )
   ```

3. **Khi viết Unit Test cho Router:**
   - Luôn truyền `ai_client=MockGeminiClient()` vào hàm để router test chạy siêu nhanh (dưới 1s), không tốn quota API:
   ```python
   from app.services.ai.mock_client import MockGeminiClient
   packages = generate_n_exam_drafts(source_questions, n_versions=2, ai_client=MockGeminiClient())
   ```

### 5.2. Dành cho TV1 & TV2 (Frontend — Dashboard, MathRenderer):
* **Trạng thái:** File fixture chuẩn tại `contracts/fixtures/variant.json`.
* **Cách test UI trước:** Bạn có thể load trực tiếp file fixture này để test giao diện hiển thị công thức KaTeX (`MathRenderer.jsx`) và kiểm tra modal nhân bản đề thi mà không cần đợi backend thật.
* **Cấu trúc dữ liệu:** Mỗi phiên bản đề có `version_id`, `version_index`, và mảng `variants`. Trong mỗi variant, 4 lựa chọn nằm trong mảng `options`, và `correct_answer` trùng khớp với 1 trong 4 lựa chọn đó.

### 5.3. Dành cho TV6 (Docker & DevOps):
* Đã cấu hình `GEMINI_MODEL=gemini-3.5-flash-lite` trong `backend/app/core/config.py`.
* File `backend/requirements.txt` đã có `google-genai`. Chỉ cần đảm bảo khi chạy `docker compose up`, container backend nhận được biến `GEMINI_API_KEY` từ file `.env`.
* Đã cấu hình timeout và retry backoff tránh nghẽn khi mạng chập chờn.

### 5.4. Dành cho TV7 (Rules, Blueprints & Validation):
* Điểm cắm của bạn: TV7 cung cấp hàm `validate_question(candidate: GeneratedVariant, blueprint)` trong `backend/app/services/validation/aggregator.py`.
* Khi validation thất bại, TV7 trả về lý do (ví dụ: `rejection_reason = "Nghiệm vi phạm khoảng min-max"`), lý do này sẽ được truyền trực tiếp vào tham số `feedback` của `regenerate_single_variant(..., feedback=rejection_reason)` để Gemini tự sửa.
* Sau này bạn có thể cập nhật thêm đồ thị blueprint hoặc lý thuyết đẳng cấu toán học vào prompt tại `backend/app/services/ai/prompts/variant_generation.txt` mà không làm vỡ code logic hiện tại.

### 5.5. Các lưu ý & Bẫy lỗi (Gotchas):
* ⚠️ **Escape ký tự trong LaTeX:** Luôn dùng raw string `r"..."` hoặc kiểm tra escape `\\` khi parse chuỗi JSON có công thức toán như `\dfrac`, `\sqrt`. Module `schema_repair.py` đã có hàm `sanitize_latex_backslashes()` tự động xử lý.
* ⚠️ **API Key:** Tuyệt đối không commit file `.env` lên GitHub. File `.env.example` đã được chuẩn bị sẵn làm mẫu.
* ⚠️ **Mã lỗi 429:** Nếu tài khoản hết quota miễn phí, `GeminiClient` đã có sẵn cơ chế retry exponential backoff tự động.

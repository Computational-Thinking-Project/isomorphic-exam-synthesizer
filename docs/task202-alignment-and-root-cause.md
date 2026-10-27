# Báo Cáo Định Hướng Kiến Trúc & Phân Tích Gốc Rễ Lỗi (TASK-202 vs Blueprint Pipeline)

> **Mục đích:** Tài liệu này chuẩn hóa ranh giới kiến trúc giữa các nhánh/PR, phân loại tài liệu chuẩn hiện hành (Source of Truth) nhằm tránh dùng lại tài liệu lỗi thời, và bóc tách nguyên nhân gốc rễ của các lỗi lặp đi lặp lại trong PR #15 (TASK-202).

---

## 1. Bản Đồ Nguồn Tài Liệu: Chuẩn Hiện Hành vs Tài Liệu Lỗi Thời

Nhiều lỗi hiểu nhầm và xung đột kiến trúc phát sinh do tham chiếu vào các tài liệu giai đoạn đầu (W1/đầu W2) đã bị thay thế bởi các Quyết định Kiến trúc (ADR) mới.

| STT | Tài liệu | Trạng thái | Hướng dẫn sử dụng |
|:---:|:---|:---:|:---|
| **1** | [docs/adr/0001-confirm-before-blueprint.md](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/docs/adr/0001-confirm-before-blueprint.md) | **CHUẨN BẮT BUỘC (Source of Truth)** | **Quyết định ngày 24/10/2026:** Bắt buộc có bước Giáo viên xác nhận nguồn (`confirm-source`) trước khi kích hoạt Blueprint. **Tuyệt đối không kích hoạt trích xuất Blueprint tự động ngay sau khi Ingest.** |
| **2** | [docs/ai-w2-integration.md](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/docs/ai-w2-integration.md) & [docs/ai-module-guide.md](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/docs/ai-module-guide.md) | **CHUẨN BẮT BUỘC (Source of Truth)** | Hợp đồng giao tiếp giữa Backend và AI Module (PR #18). Quy định rõ `BlueprintService.extract_sources` yêu cầu `confirmed_source_hash` và `RequestContext`. |
| **3** | [backend/app/services/blueprint/science-blueprint.schema.json](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/backend/app/services/blueprint/science-blueprint.schema.json) | **CHUẨN BẮT BUỘC (Source of Truth)** | Canonical Schema phiên bản 0.4.0 của Blueprint (PR #9, PR #18). Mọi cấu trúc dữ liệu Blueprint phải tuân theo schema này. |
| **4** | [docs/api/ingestion-endpoints.md](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/docs/api/ingestion-endpoints.md) | **CẦN CẬP NHẬT (Outdated Section)** | Mục 2.3 hiện tại mô tả `trigger_blueprint_pipeline` như một placeholder cho TASK-203. **Cần gỡ bỏ mục 2.3** vì Ingestion không trigger Blueprint theo ADR 0001. |
| **5** | [docs/planning.md](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/docs/planning.md) (các phần ghi trước 24/10) | **ĐÃ BỊ GHI ĐÈ BỞI ADR 0001** | Các đoạn mô tả Ingest xong tự động extract Blueprint hoặc các endpoint legacy (`POST /blueprints/extract-all`) **không được sử dụng**. |
| **6** | [docs/architecture.md](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/docs/architecture.md) & [docs/description.md](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/docs/description.md) (các sơ đồ cũ) | **THAM KHẢO CÓ CHỌN LỌC** | Chỉ tham khảo cấu trúc tổng thể hệ thống; riêng luồng xử lý Stage 1 & Blueprint phải tuân thủ tuyệt đối ADR 0001. |

---

## 2. Phân Vùng Nhiệm Vụ Rõ Ràng Giữa Các PR & Nhánh

Sự chồng chéo và hiểu nhầm xảy ra khi PR Ingestion (TASK-202) lại cố gắng cài cắm placeholder cho pipeline Blueprint, vốn thuộc về một PR và Task hoàn toàn khác.

```
                          LUỒNG XỬ LÝ CHUẨN THEO ADR 0001
                          
 [User Upload File/Text]
          │
          ▼
 ┌─────────────────────────────────────────────────────────┐
 │ PR #15: TASK-202 (feat/be1-task-202-ingestion-parsers)  │
 │ - Parse file (DOCX, LaTeX, Text/MD)                     │
 │ - Validate in-memory (4 options, OMML, đáp án hợp lệ)   │
 │ - Lưu nguyên tử vào bảng `source_questions`            │
 │ - Trả về HTTP 200 kèm danh sách câu hỏi nguồn           │
 └────────────────────────┬────────────────────────────────┘
                          │ (Dừng tại đây! KHÔNG gọi Blueprint)
                          ▼
             [Giáo viên duyệt trên UI Dashboard]
                          │
                          ▼
 ┌─────────────────────────────────────────────────────────┐
 │ Nhánh feat/be1-task-205-confirm-source (TASK-205)       │
 │ - Endpoint: `POST /api/sessions/{session_id}/confirm`   │
 │ - Tính toán & lưu `confirmed_source_hash` bền vững     │
 │ - Chốt trạng thái phiên làm việc                        │
 └────────────────────────┬────────────────────────────────┘
                          │ (Kích hoạt sau khi nguồn đã CONFIRMED)
                          ▼
 ┌─────────────────────────────────────────────────────────┐
 │ PR #9 & PR #18: TASK-203 (feat/task-203-blueprint)      │
 │ - `BlueprintService.extract_sources(...)`               │
 │ - Gọi Gemini AI trích xuất Blueprint từng câu          │
 │ - Lưu kết quả canonical 0.4.0 vào `question_blueprints` │
 └─────────────────────────────────────────────────────────┘
```

### Bảng Phân Định Phạm Vi (Scope Boundary Matrix)

| Nhánh / PR | Task ID | Nhiệm Vụ Được Phép Làm (In-Scope) | Điều CẤM Làm (Out-of-Scope) |
|---|---|---|---|
| **PR #15** (`feat/be1-task-202-ingestion-parsers`) | **TASK-202** | - Bóc tách văn bản thô, docx, latex, markdown.<br>- Tiền kiểm in-memory (đủ 4 phương án, phát hiện OMML, kiểm tra bảng đáp án tách rời).<br>- Lưu câu hỏi vào database qua RPC nguyên tử `replace_source_questions_atomically`. | ❌ **CẤM** gọi Gemini AI.<br>❌ **CẤM** lưu Blueprint.<br>❌ **CẤM** tạo background task giả lập `trigger_blueprint_pipeline`. |
| **`feat/be1-task-205-confirm-source`** | **TASK-205** | - Cung cấp API `confirm-source` sau khi giáo viên xem lại đề nguồn.<br>- Tạo và lưu `confirmed_source_hash` vào DB.<br>- **ĐÂY MỚI LÀ NƠI GHÉP ĐẦU NỐI** sang pipeline Blueprint! | ❌ Không parse lại file tải lên từ đầu. |
| **PR #9 / PR #18** (Đã merge vào `dev`) | **TASK-203** | - Cung cấp `BlueprintService`, `GeminiGateway`, `AIRuntime`.<br>- Trích xuất Blueprint theo schema canonical 0.4.0.<br>- Quản lý cache `input_fingerprint`, semaphore concurrency và retry. | ❌ Không tự kích hoạt khi chưa có `confirmed_source_hash`. |

---

## 3. Phân Tích Nguyên Nhân Gốc Rễ (Deep Root Cause Analysis)

### 3.1. Vấn đề 1: `trigger_blueprint_pipeline` vẫn là placeholder
* **Hiện tượng:** Reviewer hỏi: *"Đầu nối từ ingestion sang pipeline Blueprint thật sẽ được ghép ở đâu? trigger_blueprint_pipeline vẫn là placeholder; chưa gọi Gemini hoặc lưu Blueprint."*
* **Nguyên nhân gốc rễ:**
  1. **Bất đồng bộ thiết kế (Architectural Drift):** Code của TASK-202 được khởi tạo theo ý tưởng cũ (Ingest xong thì chạy nền trích xuất Blueprint). Nhưng sau đó nhóm đã chốt **ADR 0001 (Confirm before Blueprint)**.
  2. **Dọn dẹp không dứt điểm:** Khi chuyển giao kiến trúc, nhánh TASK-202 không gỡ bỏ hàm placeholder `trigger_blueprint_pipeline`, mà vẫn để nó được gọi trong `background_tasks.add_task(trigger_blueprint_pipeline, ...)`.
  3. **Hiểu lầm trách nhiệm:** Reviewer nhìn thấy một hàm background task có tên gọi hoành tráng nhưng ruột lại rỗng (`await asyncio.sleep(0.01)`), nên reviewer mặc định cho rằng dev làm thiếu tính năng của Ingestion!
* **Kết luận:** **Đầu nối Blueprint KHÔNG nằm ở Ingestion.** Đầu nối thật sự nằm ở **TASK-205** (`confirm-source`). Sự tồn tại của `trigger_blueprint_pipeline` trong PR #15 là một lỗi kiến trúc dư thừa cần loại bỏ.

---

### 3.2. Vấn đề 2: Nhận nhầm công thức `$P(A)=0.1$` thành nhãn phương án
* **Hiện tượng:** Đề bài:
  ```text
  A. P(A)=0.1
  B. P(B)=0.2
  C. P(C)=0.3
  D. P(D)=0.4
  ```
  Sau khi parse, nội dung phương án A bị mất `P(A)`, chỉ còn `= 0.1$`.
* **Cơ chế tái hiện lỗi:**
  Tại [utils.py:179-182](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/backend/app/services/parser/utils.py#L179-L182):
  ```python
  opt_pattern = re.compile(
      r"(?:\n|\s+|\b)(?:(?:[\-\+]|[\*\_]{1,2})\s*)?\(?\[?(?P<opt>[A-D])[\)\]\.\:]\s*(?:\*{1,2}|_{1,2})?\s*(?P<content>.*?)(?=(?:\n|\s+|\b)(?:(?:[\-\+]|[\*\_]{1,2})\s*)?\(?\[?[A-D][\)\]\.\:]|$)",
      re.DOTALL,
  )
  ```
  1. `opt_pattern` khớp `A.` thật, gom nội dung tạm là `P`.
  2. Tiếp theo gặp chuỗi `P(A)=0.1`:
     - Giữa chữ `P` và ký tự `(` là ranh giới từ `\b` (word boundary).
     - Dấu mở ngoặc `(` khớp với `\(?`.
     - Ký tự `A` khớp với `(?P<opt>[A-D])`.
     - Dấu đóng ngoặc `)` khớp với `[\)\]\.\:]`.
     - $\rightarrow$ Regex nhầm tưởng `(A)` là nhãn phương án mới!
  3. Trong vòng lặp [utils.py:192-198](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/backend/app/services/parser/utils.py#L192-L198):
     `found_opts[label] = content` thực hiện ghi đè Dictionary. Nhãn `A` giả với content `=0.1` lập tức đè bẹp nhãn `A` thật trước đó!

* **Vì sao sửa rất nhiều lần vẫn bị tái phát (The Regex Whack-a-Mole Trap)?**
  1. **Tư duy chữa cháy triệu chứng (Symptom-driven patching):**
     - Reviewer yêu cầu hỗ trợ ngoặc tròn `(A)` $\rightarrow$ dev thêm `\(?`.
     - Reviewer yêu cầu hỗ trợ cách 1 space `(A) 1 (B) 2` $\rightarrow$ dev nới lỏng từ `\s{2,}` thành `\s+|\b`.
     - Dev không phân tích bức tranh tổng thể: **Một đề thi THPT là môi trường dày đặc ký hiệu toán học!** Càng nới lỏng regex để khớp các dị thể linh tinh, regex càng nuốt chửng các ký hiệu toán học phổ biến:
       * Xác suất: $P(A)$, $P(B)$, $P(A \cap B)$
       * Hàm số / Dãy số: $f(A)$, $u(n)$
       * Hình học: Khoảng cách $d(A, B)$, tam giác $(ABC)$
       * Hóa học: Khí $(A)$, kim loại $(B)$
  2. **Thiếu ràng buộc ngữ cảnh (Lack of Context Constraints):**
     - Nhãn phương án thực sự phải đứng ở **đầu dòng mới** (`^\s*`), hoặc nếu nằm trên một dòng thì phải cách nhau bởi khoảng trắng có nghĩa, và **tuyệt đối không được đi liền sau một ký tự định danh** (thiếu Negative Lookbehind: `(?<![a-zA-Z0-9_\\])`).
  3. **Thuật toán gom nhãn không có Máy trạng thái (State Machine):**
     - Đề thi trắc nghiệm 4 phương án có tính tuần tự bắt buộc: $A \rightarrow B \rightarrow C \rightarrow D$.
     - Việc gom match vô tội vạ rồi nhét vào Dictionary ghi đè (`found_opts[label] = content`) là một thiết kế lỏng lẻo. Đáng lẽ một khi đã nhận diện được nhãn `A`, bộ parser không được phép nhận thêm bất kỳ nhãn `A` nào khác trong cùng một câu hỏi.
  4. **Thiếu Regression Test Suite bám sát đề thi thực tế:**
     - Các test case hiện có chỉ test các chuỗi giả định do dev tự viết (`test_single_space_options`, `test_bullet_options`).
     - Hoàn toàn vắng bóng các fixture đề thi thật chứa công thức xác suất, hàm số, hình học. Do đó, dev cứ sửa test cục bộ pass nhưng khi reviewer test với đề thi thật thì gãy ngay.

---

## 4. Kế Hoạch Khắc Phục Triệt Để (Không Sửa Vỏ Ngoài)

### Bước 1: Dọn sạch ranh giới Ingestion & Phản hồi Reviewer
1. **Loại bỏ `trigger_blueprint_pipeline`:** Xóa bỏ hoàn toàn hàm này khỏi [ingestion_service.py](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/backend/app/services/parser/ingestion_service.py) và gỡ bỏ `background_tasks.add_task` trong [sessions.py](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/backend/app/api/routes/sessions.py).
2. **Cập nhật tài liệu:** Xóa bỏ Mục 2.3 trong [docs/api/ingestion-endpoints.md](file:///c:/Users/ASUS%20Vivobook/Desktop/CT%20projects/isomorphic-exam-synthesizer/docs/api/ingestion-endpoints.md).
3. **Phản hồi Reviewer:** Trích dẫn chuẩn xác theo **ADR 0001**: 
   > *"Theo ADR 0001, Ingestion chỉ có trách nhiệm parse và lưu trữ câu hỏi nguồn (`source_questions`). Pipeline Blueprint thật sự sẽ được kích hoạt tại TASK-205 (`POST /sessions/{session_id}/confirm-source`) sau khi giáo viên xác nhận đề nguồn, nhằm bảo vệ quota và đảm bảo tính đúng đắn của dữ liệu. Do đó, hook placeholder tại TASK-202 đã được dọn sạch để tránh gây hiểu nhầm."*

### Bước 2: Tái cấu trúc bộ trích xuất phương án (`extract_options_from_text`)
1. **Bổ sung Negative Lookbehind:**
   - Ngăn chặn triệt để việc nhận diện nhãn khi đứng sau một ký tự chữ cái, số, dấu gạch dưới hoặc ký tự gạch chéo ngược LaTeX: `(?<![a-zA-Z0-9_\\])`.
   - Đảm bảo `P(A)` không bao giờ có thể khớp `(A)` vì có chữ `P` đứng ngay trước!
2. **Ưu tiên cấu trúc theo dòng (Line-based parsing):**
   - Ưu tiên phương án nằm riêng biệt trên từng dòng: `^\s*(?:[A-D][\.\)]|\([A-D]\)|\[[A-D]\])`.
3. **Thực thi máy trạng thái tuần tự (Sequential State Enforcement):**
   - Không dùng cơ chế ghi đè Dictionary vô điều kiện. Khi bóc tách, các nhãn phải xuất hiện theo trình tự nghiêm ngặt $A \rightarrow B \rightarrow C \rightarrow D$.
   - Nếu đã ở trong phương án $A$, chỉ chuyển sang phương án tiếp theo khi bắt gặp nhãn $B$. Mọi ký tự `(A)` nằm trong phạm vi của phương án $A$ đều phải được coi là nội dung công thức, không phải nhãn mới.

### Bước 3: Bổ sung bộ Regression Test Suite đặc thù Toán/KHTN
1. Thêm test case xác suất: `A. P(A) = 0.1`, `B. P(B) = 0.2`, `C. P(A \cap B) = 0.05`, `D. P(A \cup B) = 0.25`.
2. Thêm test case hàm số và điểm: `A. f(A) > 0`, `B. d(A, (P)) = 2`, `C. A(1; 2; 3)`, `D. \vec{AB} = (1; 0)`.
3. Thêm test case upload DOCX và Text Ingest kiểm tra tính toàn vẹn 100% của chuỗi công thức sau khi lưu.

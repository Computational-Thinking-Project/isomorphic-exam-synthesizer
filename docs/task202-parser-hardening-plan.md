# Kế hoạch Thực hiện: Củng cố và Nâng cấp Bộ Parser Đề thi (TASK-202) [Đã hiệu chỉnh]
## Hardening Plan for Exam Parsers: DOCX, Markdown, LaTeX & Integrity Guards

> **Trạng thái:** Sẵn sàng triển khai (Sau khi đã cập nhật phản hồi kỹ thuật)  
> **Nhánh làm việc:** `feat/be1-task-202-ingestion-parsers`  
> **Mục tiêu:** Khắc phục triệt để các lỗi P1 ở mức kiến trúc và thuật toán, gia cố tính toàn vẹn dữ liệu, loại bỏ nguy cơ quá tải CPU (từ $O(n^5)$ về $O(n)$), phân tách rõ ràng ảnh minh họa với công thức OMML, và ngăn chặn tuyệt đối tình trạng mất dữ liệu âm thầm.

---

## 1. Nguyên tắc Cốt lõi (Guiding Principles)

1. **Nguyên tắc Không Mất Mát Nội dung Âm thầm (Zero Silent Loss):**  
   Một câu hỏi bị từ chối kèm lỗi rõ ràng (`HTTP 422` có cấu trúc) an toàn hơn gấp nhiều lần một câu hỏi bị mất công thức/đồ thị/bảng lồng nhưng hệ thống vẫn âm thầm chấp nhận lưu vào CSDL.
2. **Độ phức tạp Tuyến tính (Linear Scalability):**  
   Thuật toán trích xuất đáp án và phân đoạn câu hỏi phải vận hành trong thời gian tuyến tính $O(n)$ theo kích thước đầu vào; loại bỏ hoàn toàn các vòng lặp tổ hợp có độ phức tạp lên đến $O(n^5)$ gây cạn kiệt CPU (CPU Exhaustion / DoS).
3. **Phân tách Ngữ cảnh Rõ ràng (Context-Aware Parsing):**  
   Cấu trúc đề thi (tiêu đề câu hỏi, nhãn A–D, marker đáp án) chỉ được nhận diện trong ngữ cảnh văn bản tự nhiên; nội dung bên trong công thức toán (`$...$`), khối mã lập trình (code fence), bảng con, hoặc câu dẫn tuyệt đối không được phép làm sai lệch bộ nhận diện cấu trúc.
4. **Không Suy đoán khi Cấu trúc Mơ hồ:**  
   Nếu cấu trúc văn bản quá mơ hồ hoặc có nhiều cách diễn giải xung đột, hệ thống phải trả về lỗi `AMBIGUOUS_FORMAT` yêu cầu kiểm tra thủ công, không tự ý chọn kết quả theo heuristic không thể chứng minh.

---

## 2. Chi tiết Các Điểm Hiệu chỉnh Kỹ thuật

### 2.1. Tách biệt Phát hiện Ảnh DOCX (`UNPARSED_IMAGE`) khỏi Công thức OMML (`UNPARSED_OMML`)
* **Vấn đề cũ:** Gom chung ảnh Word (`w:drawing`, `w:pict`, `a:blip`) vào `has_unparsed_omml = True` làm sai lệch nguyên nhân lỗi (ảnh đồ thị/hình học không phải là công thức OMML).
* **Giải pháp chuẩn hóa:**
  - Bổ sung trường `has_unparsed_image: bool = False` vào `ParsedQuestionItem`.
  - Mở rộng kiểu lỗi trong `ParserErrorItem.error_type`: bổ sung `UNPARSED_IMAGE` và `AMBIGUOUS_FORMAT`.
  - Kiểm tra cấu trúc XML bằng namespace XML thực tế của WordprocessingML (`w:drawing`, `w:pict`, `v:shape`, `v:imagedata`, `a:blip`), phân biệt rõ với `m:oMath`, `m:oMathPara` (OMML) và `w:object` (OLE Equation.3).
  - Khi phát hiện hình ảnh/đồ họa không thể trích xuất thành LaTeX/text cấu trúc, tạo lỗi `UNPARSED_IMAGE` và chặn nhập tự động.

### 2.2. Đảo ngược Thứ tự Xử lý LaTeX: Môi trường Verbatim trước, Comment sau
* **Vấn đề cũ:** Xóa comment `%` trước có thể phá hủy nội dung code trong `verbatim`/`lstlisting` vốn chứa ký tự `%` hợp lệ.
* **Giải pháp chuẩn hóa:**
  - **Bước 1:** Quét và mask toàn bộ môi trường nguyên văn (`\begin{verbatim}...\end{verbatim}`, `\begin{lstlisting}...\end{lstlisting}`, `\verb|...|`) bằng chuỗi giữ chỗ **bảo toàn nguyên vẹn độ dài ký tự và vị trí dấu xuống dòng** (`\n`).
  - **Bước 2:** Xử lý comment `%`: Kiểm tra tính chẵn lẻ của số lượng dấu gạch chéo ngược (`\`) liền trước:
    * `\%` (1 dấu gạch chéo: lẻ) $\rightarrow$ Ký tự phần trăm thông thường được escape (giữ nguyên).
    * `\\%` (2 dấu gạch chéo: chẵn) $\rightarrow$ Dấu ngắt dòng `\\` theo sau bởi `%` (bắt đầu comment $\rightarrow$ xóa phần còn lại của dòng).
    * `\\\%` (3 dấu gạch chéo: lẻ) $\rightarrow$ `\\` theo sau bởi `\%` (giữ nguyên).
  - **Bước 3:** Phân tích cấu trúc câu hỏi và trích xuất phương án.
  - **Bước 4:** Unmask môi trường nguyên văn hoàn trả dữ liệu.

### 2.3. Mở rộng Hợp đồng Dữ liệu Bảng Đáp Án (`RawAnswerKeyInfo`) cho Validator
* **Vấn đề cũ:** `parse_separate_answer_key()` trả về `dict[int, str]`. Nếu số 1 xuất hiện 2 lần với đáp án khác nhau (`1.A` và `1.B`), dictionary bị ghi đè mất dấu vết xung đột, validator không thể biết để bắt lỗi.
* **Giải pháp chuẩn hóa:**
  - Định nghĩa cấu trúc dữ liệu trung gian:
    ```python
    @dataclass
    class RawAnswerKeyInfo:
        raw_pairs: List[Tuple[int, str]]          # [(1, 'A'), (1, 'B'), (2, 'C')]
        duplicate_keys: List[int]                 # [1]
        conflicts: Dict[int, List[str]]           # {1: ['A', 'B']}
        mapped_keys: Dict[int, str]               # {2: 'C'} (chỉ giữ khóa không xung đột)
        unmatched_keys: List[int]                 # Các khóa không thuộc về câu hỏi nào
    ```
  - Các parser (`docx_parser.py`, `markdown_parser.py`, `latex_parser.py`) trả về `RawAnswerKeyInfo`.
  - `validator.validate_exam_integrity` nhận `RawAnswerKeyInfo` để:
    * Báo lỗi `CONFLICTING_ANSWER_KEY` nếu một câu có nhiều đáp án mâu thuẫn.
    * Báo lỗi `SURPLUS_ANSWER_KEY` nếu bảng đáp án chứa câu không tồn tại trong đề thi.

### 2.4. Phát hiện Thân bài Rỗng Thực sự (`is_empty_stem`)
* **Vấn đề cũ:** Markdown parser hiện fallback `raw_content = stem if stem else q_text`. Nếu `stem` rỗng, `q_text` (chứa toàn bộ A, B, C, D) bị lấp vào, khiến validator không phát hiện được thân bài rỗng.
* **Giải pháp chuẩn hóa:**
  - Bổ sung trường `is_empty_stem: bool = False` vào `ParsedQuestionItem`.
  - Không ghi đè options vào `stem` khi `stem` rỗng. Giữ nguyên ranh giới: `stem` phản ánh đúng phần dẫn câu hỏi trước phương án đầu tiên.
  - `validator.py` kiểm tra cờ `q.is_empty_stem` hoặc `not q.stem.strip()` $\rightarrow$ báo lỗi `EMPTY_STEM` rõ ràng.

### 2.5. Mask Code Fence của Markdown Xuyên suốt Toàn bộ Pipeline
* **Vấn đề cũ:** Code block Markdown chứa `ĐÁP ÁN:` hoặc `Câu 2:` có thể đánh lừa cả `parse_separate_answer_key()` lẫn `MD_QUESTION_HEADER`.
* **Giải pháp chuẩn hóa:**
  - Mask code fence ngay từ điểm bắt đầu của `parse_markdown()`, trước mọi bước phân tích.
  - Bộ mask **bảo toàn 100% độ dài ký tự và vị trí xuống dòng** (thay nội dung bên trong code fence bằng ký tự an toàn không kích hoạt regex, giữ nguyên fences và newlines) để các vị trí offset (start/end) map 1:1 tuyệt đối với chuỗi gốc.
  - Toàn bộ các bước: bóc bảng đáp án, tìm tiêu đề câu hỏi, fallback đánh số, bóc tách lựa chọn đều chạy trên văn bản đã mask.
  - Chỉ unmask sau khi ranh giới của các câu hỏi và các lựa chọn đã được chốt hoàn toàn.

### 2.6. Chính sách Phân định Cảnh báo Bảo mật (`has_security_warning`)
* **Nguyên tắc:** Phân biệt rõ giữa **Lỗi chặn nhập** (Hard Block: lỗi cấu trúc, thiếu đáp án, OMML, ảnh không đọc được, trùng số câu, xung đột) và **Cảnh báo cần xem xét** (Soft Warning: `has_security_warning = True`).
* **Quy tắc:**
  - Không chặn nhập câu hỏi chỉ vì đề thi trắc nghiệm môn Tin học/An toàn thông tin có chứa từ khóa SQL injection hay Prompt Injection.
  - Đánh dấu cờ `has_security_warning = True` trên `ParsedQuestionItem` để giao diện hiển thị cảnh báo cho giáo viên kiểm tra lại.
  - Coi nội dung văn bản đề thi là dữ liệu không đáng tin cậy (untrusted data) khi chuyển tiếp sang cho AI ở Stage 02, dùng prompt isolation và delimiter an toàn.

### 2.7. Thuật toán Tuyến tính $O(n)$ trong `utils.py` và Xử lý Mơ hồ
* **Đánh giá lại độ phức tạp cũ:** 4 vòng lặp lồng nhau kết hợp bước `any(...)` duyệt danh sách nhãn bên trong thực chất có độ phức tạp xấu nhất lên tới $O(n^5)$.
* **Thuật toán mới (Single-Pass Linear Scanner):**
  - Giữ danh sách các nhãn ứng viên đã lọc ranh giới và sắp xếp theo offset `start`.
  - Duyệt tuyến tính qua danh sách, tìm kiếm chuỗi chuyển tiếp hợp lệ $A \rightarrow B \rightarrow C \rightarrow D$ gần nhất thỏa mãn:
    1. Vị trí tăng dần nghiêm ngặt: $start(A) < start(B) < start(C) < start(D)$.
    2. Không có nhãn trùng lặp xen giữa giai đoạn (không có $A$ khác giữa $A$ và $B$).
    3. Định dạng phân cách nhất quán (cùng là `A.`, cùng là `(A)`, hoặc cùng xuống dòng).
  - **Xử lý cấu trúc mơ hồ:** Nếu xuất hiện nhiều bộ tứ có điểm số xung đột tương đương hoặc cấu trúc phân mảnh không thể xác minh, trả về lỗi `AMBIGUOUS_FORMAT`, tuyệt đối không tự chọn kết quả heuristic.
  - **Scoped Marker Detection:** Chỉ kiểm tra ký hiệu `*` hoặc `**` ngay tại nhãn của 4 lựa chọn đã được chốt; không quét toàn cục trên câu dẫn.

### 2.8. Duyệt DOCX Đệ quy và Xử lý Ô Gộp (Merged Cells)
* **Xử lý bảng lồng & ô gộp:**
  - Xây dựng hàm `extract_cell_elements(cell)`: duyệt đệ quy các phần tử XML con (`w:p` và `w:tbl`) của `cell._tc` theo đúng thứ tự tài liệu.
  - Khi duyệt `row.cells`, **loại trừ ô gộp trùng lặp** bằng cách theo dõi danh sách `cell._tc` (XML element identity), tránh việc đọc lặp lại nội dung ô nhiều lần khi ô được gộp ngang (`gridSpan`) hoặc gộp dọc (`vMerge`).

---

## 3. Thứ tự Triển khai 6 Bước (Execution Roadmap)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                  LỘ TRÌNH 6 BƯỚC                                       │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ BƯỚC 1: Chốt hợp đồng dữ liệu & Schema lỗi                                             │
│         - schemas.py: Thêm UNPARSED_IMAGE, AMBIGUOUS_FORMAT, CONFLICTING_ANSWER_KEY    │
│         - schemas.py: Thêm has_unparsed_image, is_empty_stem vào ParsedQuestionItem    │
│         - utils.py: Định nghĩa RawAnswerKeyInfo                                        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ BƯỚC 2: Tái cấu trúc utils.py                                                          │
│         - Chuyển extract_options_from_text sang Linear Scanning O(n)                   │
│         - Xử lý cấu trúc mơ hồ (AMBIGUOUS_FORMAT)                                      │
│         - Scoped Marker Detection (chỉ bắt marker tại nhãn 4 lựa chọn)                 │
│         - Nâng cấp parse_separate_answer_key trả về RawAnswerKeyInfo                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ BƯỚC 3: Sửa Markdown và LaTeX theo ngữ cảnh                                            │
│         - markdown_parser.py: Code fence masking xuyên suốt pipeline, bảo toàn độ dài │
│         - markdown_parser.py: Giữ nguyên ranh giới stem rỗng (is_empty_stem)           │
│         - latex_parser.py: Mask verbatim/lstlisting trước, xử lý % có kiểm tra \\ chẵn/lẻ│
├────────────────────────────────────────────────────────────────────────────────────────┤
│ BƯỚC 4: Sửa DOCX Parser & Cơ chế Báo lỗi Mất nội dung                                 │
│         - docx_parser.py: Duyệt đệ quy bảng lồng theo thứ tự XML                       │
│         - docx_parser.py: Deduplicate ô gộp bằng cell._tc identity                     │
│         - docx_parser.py: Tách phát hiện ảnh (UNPARSED_IMAGE) khỏi OMML theo namespace │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ BƯỚC 5: Hoàn thiện Validator Toàn cục                                                  │
│         - validator.py: Tiêu thụ RawAnswerKeyInfo bắt CONFLICTING & SURPLUS_ANSWER_KEY │
│         - validator.py: Bắt số câu trùng lặp (DUPLICATE_QUESTION_NO)                   │
│         - validator.py: Bắt số thứ tự <= 0 và rỗng thân bài (EMPTY_STEM)               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ BƯỚC 6: Củng cố Bảo mật, Ingestion & Chạy Toàn bộ Kiểm thử                             │
│         - file_security.py: Validate strict UTF-8 decoding cho .md và .tex             │
│         - ingestion_service.py: Bọc .execute() đồng bộ vào asyncio.to_thread           │
│         - Bổ sung Unit Tests & Scalability Benchmarks cho toàn bộ 5 nhóm lỗi P1        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Bảng Tiêu chí Nghiệm thu Có thể Chứng minh (Demonstrable Acceptance Criteria)

| Tiêu chí | Điều kiện nghiệm thu bắt buộc | Phương pháp chứng minh |
| :--- | :--- | :--- |
| **Không mất dữ liệu âm thầm** | Mọi file DOCX chứa ảnh (`w:drawing`, `w:pict`), bảng lồng, hoặc OMML chưa phân tích đều phải được trích xuất đủ hoặc trả lỗi cấu trúc rõ ràng (`UNPARSED_IMAGE`, `UNPARSED_OMML`). Tuyệt đối không có trường hợp bỏ qua âm thầm. | Unit test với file DOCX nhúng ảnh thật và bảng lồng thực tế; xác nhận trả về đúng mã lỗi hoặc đủ số lượng câu hỏi. |
| **Độ chính xác bóc tách** | Đề thi mẫu chuẩn cho DOCX, Markdown, LaTeX tạo đúng 100% câu hỏi, ranh giới 4 lựa chọn A–D, và đáp án đúng. Code fence Markdown và môi trường Verbatim LaTeX được bảo toàn nguyên vẹn. | Golden Fixture Tests so sánh kết quả JSON đầu ra với tệp kết quả kỳ vọng chuẩn. |
| **Kiểm tra toàn vẹn** | Các trường hợp bất thường: số câu trùng lặp, số câu $\le 0$, thân bài rỗng, hoặc bảng đáp án xung đột (`1.A` và `1.B`) đều bị validator phát hiện và từ chối. | Test case chuyên biệt cho từng loại lỗi toàn vẹn trong `test_parsers.py`. |
| **Hiệu năng & Khả năng mở rộng** | Thuật toán trích xuất đáp án tăng trưởng tuyến tính $O(n)$ theo kích thước đầu vào; loại bỏ hoàn toàn hiện tượng nghẽn CPU $O(n^5)$ khi gặp nhiều nhãn nhiễu. | Scalability Benchmark: đo thời gian xử lý với $k=10, 20, 40$ cụm nhãn, chứng minh tỷ lệ tăng thời gian là tuyến tính. |
| **Không hồi quy** | 100% các bài test hiện có (338 tests) và toàn bộ test mới đều PASS; API routes trả đúng HTTP 200/422; không gây lỗi database mutation khi đầu vào không hợp lệ. | Chạy toàn bộ pytest suite và type-check mypy 0 errors. |
| **Bảo mật và vận hành** | File `.md`/`.tex` chứa mã hóa hỏng bị từ chối với HTTP 400 rõ ràng; các thao tác DB không chặn event loop của FastAPI. | Unit test với payload invalid encoding và kiểm tra non-blocking IO. |

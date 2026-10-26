# Backend Core Rules & Architectural Guidelines (BE1 Scope)

Tài liệu này định nghĩa **Bộ Quy Tắc Vàng Bất Di Bất Dịch** cho kỹ sư Backend (BE1) trong toàn bộ dự án **Isomorphic Exam Synthesizer**. Bất kỳ đoạn mã backend nào được viết ra đều phải tuân thủ nghiêm ngặt các nguyên tắc dưới đây.

---

## 1. Kiến Trúc Dữ Liệu & Giao Dịch CSDL (Database ACID & Atomicity)

* **100% In-Memory Pre-validation:**
  * Mọi khâu bóc tách file (`.docx`, `.tex`, `.md`), quét bảng đáp án, và phát hiện OMML phải thực hiện hoàn toàn in-memory trước khi ghi dữ liệu.
* **Database Untouched on Validation Error (Zero Cloud Mutation):**
  * Nếu phát hiện bất kỳ lỗi dữ liệu nào (thiếu đáp án, lỗi OMML không parse được text, số câu ngoài khoảng $[1, 20]$), **TUYỆT ĐỐI không ghi đè, không xóa, không can thiệp vào CSDL và Storage**.
  * Trả về ngay mã `HTTP 422 Unprocessable Entity` với schema lỗi chi tiết để Frontend hiển thị hộp thoại hướng dẫn người dùng.
* **Atomic Replacement qua Stored Procedure (Method 2A):**
  * Không bao giờ thực hiện các lệnh xóa (`delete`) và thêm mới (`insert`) rải rác từ API client qua nhiều network round-trips vì nếu rớt mạng ở bước giữa sẽ để lại dữ liệu rác (orphaned records).
  * Bắt buộc đóng gói toàn bộ logic thay đổi dữ liệu phụ thuộc vào một PostgreSQL Stored Procedure / Function duy nhất (`SECURITY DEFINER`), đảm bảo tính nguyên tử 100% (ACID Atomicity).
* **Bảo vệ Máy Trạng Thái (State Machine Guard):**
  * Mọi API thao tác dữ liệu theo phiên phải kiểm tra trạng thái phiên trước khi thực hiện.
  * Ví dụ: Ingestion và Confirm Source chỉ được phép khi phiên ở trạng thái `draft`. Nếu phiên đã ở trạng thái khác, bắt buộc trả về `HTTP 409 Conflict`.
* **Phân Quyền & Kiểm Soát Sở Hữu Chặt Chẽ (SEC-01, SEC-02):**
  * Mọi API phải kiểm tra quyền sở hữu qua `assert_ownership("exam_sessions", session_id, current_user.id)`.
  * Nếu câu hỏi nguồn có cờ `has_security_warning == true`, bắt buộc request body phải có `acknowledged_security_warnings: true`, nếu không trả về `HTTP 422`.

---

## 2. Quy Tắc Vàng Xử Lý Ngoại Lệ Phân Tán & Mạng (Distributed Exception Handling Rules)

> [!CAUTION]
> **Đây là bài học đắt giá nhất từ PR Review:** Trong kiến trúc mạng phân tán (API Client $\leftrightarrow$ Backend $\leftrightarrow$ Database/External Services), sự cố mạng (network timeout / dropped connection) có thể xảy ra **sau khi** Database đã xử lý và commit xong transaction nhưng **trước khi** Backend nhận được response.

### Quy tắc 2.1: Phân Loại Ngoại Lệ Theo Kiểu Dữ Liệu (`isinstance`), TUYỆT ĐỐI CẤM String Matching
* **CẤM:** Không bao giờ dựa vào `str(exc)` hay kiểm tra từ khóa dạng `"timeout" in str(exc).lower()` hoặc `"connection reset" in str(exc).lower()`.
* **LÝ DO:**
  * Các ngoại lệ mạng thực tế từ các thư viện HTTP client (như `httpx.ReadTimeout("")`, `httpx.ReadError("")`) khi raise thường có **chuỗi thông báo rỗng** (`str(exc) == ""`).
  * Khi server ngắt kết nối đột ngột, exception ném ra là `RemoteProtocolError("Server disconnected without sending a response.")` — hoàn toàn không chứa từ `"timeout"` hay `"connection reset"`.
  * Dò chuỗi sẽ bỏ sót và khiến lỗi lọt xuống nhánh mặc định sai lệch.
* **BẮT BUỘC:** Luôn kiểm tra trực tiếp theo cây phả hệ kiểu ngoại lệ bằng `isinstance`:
  * **Network Timeout:** `(httpx.TimeoutException, httpcore.TimeoutException, TimeoutError)`.
  * **Network Transport / Disconnection:** `(httpx.TransportError, httpx.NetworkError, httpx.ProtocolError, httpcore.NetworkError, httpcore.ProtocolError, ConnectionError)`.
  * Rà soát cả chuỗi ngoại lệ lồng nhau (`exc.__cause__` và `exc.__context__`).

### Quy tắc 2.2: Nguyên Tắc "Trạng Thái Bất Định" (Uncertain Commit Status)
* Khi xảy ra lỗi mạng (timeout, mất kết nối, server đóng socket giữa chừng):
  * **Bản chất:** Backend **HOÀN TOÀN KHÔNG BIẾT** giao dịch phía CSDL đã commit thành công hay bị hủy.
  * **CẤM:** Tuyệt đối không được khẳng định dữ liệu *"chưa bị thay đổi"* (`was not modified`) hoặc *"đã hoàn tác"* (`was rolled back`). Cả hai khẳng định này đều là suy đoán vô căn cứ và nguy hiểm.
  * **BẮT BUỘC:** 
    1. Trả về mã **HTTP 504 Gateway Timeout** (hoặc `HTTP 502 Bad Gateway`).
    2. Thông báo rõ ràng: *Trạng thái giao dịch chưa xác định do sự cố mạng, giao dịch có thể đã hoàn tất*.
    3. Luôn đính kèm hướng dẫn bắt buộc: *Vui lòng kiểm tra lại trạng thái phiên trước khi thử lại* (`Please verify session state before retrying`) để tránh gửi lặp gây xung đột dữ liệu.

### Quy tắc 2.3: Nguyên Tắc "Chỉ Khẳng Định Rollback Khi Có Bằng Chứng CSDL" (Evidence-Based Rollback)
* **BẰNG CHỨNG CSDL LÀ GÌ?** Là khi Backend nhận được phản hồi lỗi chính thức từ chính Database Engine (ví dụ: `postgrest.exceptions.APIError`, mã lỗi PostgreSQL SQLSTATE như `P0001`, `23505`, v.v.). Khi nhận được mã lỗi này từ CSDL, PostgreSQL mới thực sự đã hủy và rollback transaction.
* **HÀNH VI:**
  * **Có bằng chứng CSDL:** Trả về **HTTP 500 Internal Server Error** với thông báo xác nhận: `"Database atomic replacement failed and was rolled back."`.
  * **Lỗi nội bộ không xác định (Internal Fault không có bằng chứng CSDL):** Trả về **HTTP 500** nhưng thông báo trung lập, yêu cầu kiểm tra phiên và **tuyệt đối không khẳng định đã rollback**.

---

## 3. Kỷ Luật Kiểm Thử Ngoại Lệ & Mocking Thực Tế (Testing & Fault Injection Discipline)

> [!WARNING]
> **CẤM FAKE MOCKING:** Mock giả lập sai lệch là nguyên nhân trực tiếp dẫn tới "cảm giác an toàn giả tạo", khiến test pass 100% ở local nhưng vỡ trận trên môi trường thật.

* **Quy tắc Mock Ngoại lệ Thật (Realistic Mocking Rule):**
  * Khi viết unit test kiểm thử xử lý lỗi mạng / CSDL, **bắt buộc phải mock bằng đúng instance ngoại lệ thật từ thư viện thực tế**:
    * Mô phỏng timeout mạng: Dùng `httpx.ReadTimeout("")`, `httpx.ConnectTimeout("")`.
    * Mô phỏng mất kết nối / mất phản hồi: Dùng `httpx.ReadError("")`, `httpx.RemoteProtocolError("Server disconnected without sending a response.")`, `httpcore.RemoteProtocolError(...)`.
    * Mô phỏng lỗi CSDL có bằng chứng: Dùng `APIError({"code": "P0001", "message": "Constraint violation"})`.
  * **Tuyệt đối CẤM:** Không được dùng `RuntimeError("httpx.ReadTimeout: The read operation timed out")` hoặc exception tự chế chứa chuỗi text mồi từ khóa.
* **Bộ Kiểm Thử Biên Bắt Buộc Đối Với Mọi Exception Handler:**
  1. Test với thông báo rỗng (`message == ""`).
  2. Test với trường hợp server disconnect sau khi xử lý (mất phản hồi).
  3. Test với ngoại lệ có bằng chứng DB thật (khẳng định rollback).
  4. Test với ngoại lệ bất định không có bằng chứng DB (không khẳng định rollback).

---

## 4. Chuẩn Hóa Mã Lỗi HTTP & Hợp Đồng Với Frontend (HTTP Error Contract)

Mọi endpoint backend phải tuân thủ bảng ánh xạ mã lỗi chuẩn mực sau:

| Mã HTTP | Tên chuẩn | Khi nào sử dụng? |
| :--- | :--- | :--- |
| **400** | Bad Request | Lỗi định dạng đầu vào, vi phạm an ninh file (SEC-04: quá 10MB, zip bomb, sai magic bytes). |
| **401** | Unauthorized | Thiếu hoặc token JWT không hợp lệ / hết hạn. |
| **403** | Forbidden | Không có quyền truy cập / vi phạm sở hữu tài nguyên (`assert_ownership`). |
| **404** | Not Found | Phiên làm việc hoặc tài nguyên truy vấn không tồn tại trong CSDL. |
| **409** | Conflict | Xung đột máy trạng thái (ví dụ: phiên không ở trạng thái `draft`). |
| **422** | Unprocessable Entity | Dữ liệu hợp lệ về cú pháp nhưng vi phạm nghiệp vụ nội dung (thiếu đáp án, công thức OMML không đọc được, số câu ngoài $[1, 20]$). |
| **504** | Gateway Timeout | Lỗi mạng / timeout / ngắt kết nối với upstream CSDL; kết quả giao dịch **chưa xác định**. Yêu cầu kiểm tra phiên trước khi thử lại. |
| **500** | Internal Server Error | Lỗi thực thi nội bộ CSDL đã xác nhận rollback, hoặc lỗi hệ thống không xác định. |

---

## 5. Tiêu Chuẩn Mã Nguồn & Công Nghệ

* **Ngôn ngữ & Runtime:** Python 3.11+, FastAPI, Pydantic v2.
* **Type Hinting:** Bắt buộc type annotation đầy đủ trên tất cả các hàm, endpoint, services (dùng `typing.Optional`, `list[T]`, `dict[K, V]`).
* **Text & Encoding:** Chuẩn hóa toàn bộ text sang Unicode NFC (`unicodedata.normalize('NFC', text)`) để tránh lỗi font tiếng Việt.
* **Linter & Type Checker:** Tuân thủ cấu hình Ruff (line-length: 100) và Mypy trong `backend/pyproject.toml`.

---

## 6. Kỷ Luật Phạm Vi Mã Nguồn & Chống Conflict Git (Scope & Git Discipline)

* **Tuyệt đối KHÔNG tự ý format toàn bộ dự án:**
  * KHÔNG chạy `ruff format app/ tests/` hoặc `ruff check --fix` trên toàn bộ codebase.
  * Chỉ được format và sửa lint trên **đúng các file thuộc phạm vi task được phân công**.
  * Tuyệt đối không chạm vào, không reformat các file của thành viên khác (`app/services/generation/`, `app/services/ai/`, v.v.) để tránh gây merge conflict hàng loạt trên nhánh `dev`.
* **Không tự ý commit file quản trị sprint & file cá nhân:**
  * Không commit các file kế hoạch sprint chung (như `w2_21_10.md`), file nháp hay scratchpad cá nhân.
* **Quy trình kiểm tra tính sạch (Clean Tree Verification) trước khi commit:**
  1. Luôn chạy `git status` và `git diff --stat` để rà soát danh sách file thay đổi.
  2. Nếu phát hiện file ngoài phạm vi bị modified (do auto-format của IDE), phải dùng `git restore <file>` khôi phục ngay trước khi stage.
  3. Chỉ `git add` đúng các file cần thiết cho task.

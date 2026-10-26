# Backend Engineering Rules for AI Agents (BE1)

## 0. Mục đích, phạm vi và thứ tự ưu tiên

Tài liệu này là hợp đồng kỹ thuật bắt buộc cho mọi AI agent thực hiện công việc Backend (nhánh `feat/be1-*`) trong dự án **Isomorphic Exam Synthesizer**. Áp dụng cho việc đọc code, lập kế hoạch, sửa lỗi, thêm tính năng, viết test, thay đổi schema/API và chuẩn bị commit.

- **Không đoán kiến trúc khi chưa đọc code.** Trước khi sửa, phải tìm entry point, luồng gọi thực tế, schema, migration, test và quy ước hiện có.
- **Không mở rộng phạm vi tùy tiện.** Chỉ sửa file cần thiết để giải quyết yêu cầu; không refactor unrelated code hoặc format toàn dự án gây conflict trên nhánh `dev`.
- **Không đánh đổi tính đúng đắn để lấy test pass.** Không xóa test, hạ assertion, bỏ type, nuốt exception hay nới validation chỉ để làm CI xanh.
- **Tuân thủ toàn bộ 5 cổng kiểm tra CI.** Mọi commit trước khi push bắt buộc phải vượt qua toàn bộ các kiểm tra tương đương GitHub Actions CI (`ci.yml` và `docker-ci.yml`).
- **Khi tài liệu mâu thuẫn với hành vi hiện tại**, ghi rõ mâu thuẫn, xác minh từ code/test/DB contract và chọn phương án ít rủi ro nhất; không âm thầm giả định.
- `SKILL.md` quy định checklist thao tác, failure mode playbook và lệnh kiểm tra. Tài liệu này quy định các nguyên tắc kiến trúc và hành vi không được vi phạm.

## 1. Quy trình bắt buộc trước khi code

### 1.1. Khảo sát hiện trạng

Trước khi sửa file, phải:

1. Đọc yêu cầu, tiêu chí nghiệm thu và các file chỉ dẫn liên quan.
2. Kiểm tra `git status --short` và `git diff --stat` để nhận biết thay đổi có sẵn; tuyệt đối không ghi đè công việc chưa commit của người khác.
3. Truy vết luồng hiện tại từ API route → dependency/auth → service → parser/AI/DB client → database hoặc external service → response.
4. Đọc schema/model, SQL function/migration liên quan, exception handler, test hiện tại và cấu hình trong `backend/pyproject.toml`.
5. Phân biệt **đã xác minh**, **giả thuyết**, **chưa biết**. Không trình bày giả thuyết như sự thật.

Không bắt đầu chỉnh sửa khi chưa hoàn thành khảo sát đủ để biết điểm vào, dữ liệu vào/ra, ranh giới side effect và cách kiểm thử.

### 1.2. Bắt buộc lập kế hoạch trước khi triển khai

Trước khi chỉnh sửa code, agent phải trình bày một kế hoạch ngắn gọn nhưng cụ thể theo mẫu chuẩn trong `SKILL.md`. Nếu môi trường có hỗ trợ plan artifact, hãy cập nhật plan ở đó. Nếu người dùng yêu cầu vừa sửa vừa triển khai, hãy nêu kế hoạch trước rồi tiếp tục thực hiện trong cùng lượt; không dừng chờ phê duyệt trừ khi có quyết định rủi ro cao hoặc yêu cầu mơ hồ không thể giải quyết an toàn.

Kế hoạch tối thiểu phải có:
1. **Mục tiêu và ngoài phạm vi:** hành vi cần đạt, điều không được thay đổi.
2. **Hiện trạng và luồng liên quan:** entry point, các lớp/module liên quan, trạng thái và side effect hiện tại.
3. **Danh sách nhiệm vụ theo thứ tự:** mỗi nhiệm vụ ghi rõ file/vùng code dự kiến, thay đổi cần làm và phụ thuộc.
4. **Phân tích lỗi/rủi ro theo từng nhiệm vụ:** lỗi có thể xảy ra, nguyên nhân gốc cần xác minh, cách phát hiện, cách giải quyết tại nguồn và test hồi quy.
5. **Ma trận kiểm thử:** happy path, input biên, validation failure, quyền truy cập, trạng thái không hợp lệ, lỗi DB/mạng và regression phù hợp.
6. **Tác động dữ liệu/API:** có ghi DB/Storage, đổi schema/migration, đổi HTTP status hoặc response contract hay không.
7. **Tiêu chí nghiệm thu:** điều kiện quan sát được để xác nhận hoàn thành.
8. **Giả định và điểm chưa chắc chắn:** cách kiểm chứng hoặc phương án an toàn nếu không thể xác minh.

Không viết kế hoạch kiểu chung chung như “sửa parser, thêm test”. Phải chỉ rõ parser nào, dữ liệu nào, failure mode nào, test nào và kết quả mong đợi.

### 1.3. Nguyên tắc điều tra nguyên nhân gốc

**Bắt buộc sửa nguyên nhân gốc, không chỉ che dấu hiệu.** Khi gặp bug hoặc test fail:

1. Tái hiện lỗi bằng test/lệnh/input tối thiểu; giữ lại thông báo lỗi, stack trace và trạng thái trước/sau.
2. Truy dấu dữ liệu và luồng điều khiển qua các lớp; xác định tầng đầu tiên nơi invariant bị phá vỡ.
3. Đưa ra giả thuyết có thể kiểm chứng, kiểm tra từng giả thuyết bằng code, log, test hoặc bằng chứng DB.
4. Mô tả nguyên nhân gốc bằng quan hệ **điều kiện → cơ chế gây lỗi → biểu hiện**.
5. Sửa ở đúng tầng tạo ra lỗi; thêm test hồi quy tái hiện lỗi trước khi sửa và chứng minh hành vi đúng sau khi sửa.
6. Chạy lại test phạm vi và kiểm tra tác động phụ.

**Không chấp nhận** các cách xử lý như: catch-all rồi trả success/giá trị mặc định; retry mù; dò chuỗi thông báo exception; bỏ qua test; tăng timeout chỉ để che lỗi hiệu năng chưa rõ nguyên nhân; thêm `sleep`; tắt type/lint; nới validation; hoặc sửa test để khớp với code sai.

Nếu chỉ có thể áp dụng biện pháp giảm thiểu tạm thời, phải ghi rõ nguyên nhân gốc chưa được xử lý, rủi ro còn lại và bằng chứng cần có để xử lý dứt điểm. Không được gọi workaround là root-cause fix.

## 2. Input Validation, Parsers & AI Output Processing

### 2.1. Pre-validation hoàn toàn in-memory

Mọi khâu đọc/bóc tách file người dùng (`.docx`, `.tex`, `.md`) cũng như xử lý JSON sinh ra từ Gemini API (Blueprints, Variants) phải hoàn thành validation trong bộ nhớ trước khi bắt đầu mutation DB hoặc Storage.

Trình tự logic bắt buộc:

1. Kiểm tra đầu vào ở lớp tiếp nhận: kích thước, định dạng thực tế/magic bytes, JSON syntax và ràng buộc an ninh.
2. Đọc và parse nội dung trong memory; không upload/ghi dữ liệu trung gian lên Storage hoặc DB trong giai đoạn validation.
3. Trích xuất, chuẩn hóa và kiểm tra dữ liệu; làm rõ phần nào parse được, phần nào không parse được.
4. Tổng hợp validation issues theo schema lỗi ổn định, có vị trí/field/code/message khi xác định được.
5. Chỉ khi toàn bộ validation nghiệp vụ thành công mới được đi tới bước ghi dữ liệu.

Nếu có lỗi nội dung như thiếu đáp án, OMML không thể chuyển thành nội dung cần thiết, số câu ngoài khoảng `[1, 20]`, hoặc AI trả về sai schema không thể sửa chữa, trả mã lỗi phù hợp (`HTTP 400` hoặc `HTTP 422`). **Không được thay đổi DB hay Storage** trước hoặc trong phản hồi lỗi validation.

### 2.2. Kiểm soát file và dữ liệu không tin cậy

- Tuân thủ giới hạn SEC-04: file upload tối đa 10 MB; phát hiện zip bomb và kiểm tra magic bytes (`PK\x03\x04` cho DOCX) thay vì chỉ tin phần mở rộng file.
- Không giải nén toàn bộ archive thiếu kiểm soát; đặt giới hạn phù hợp cho tổng kích thước sau giải nén (<= 50 MB), số entry và mức tiêu thụ tài nguyên.
- Không thực thi macro, script hoặc nội dung nhúng từ file đầu vào.
- Phát hiện Prompt Injection (SEC-02): kiểm tra các pattern cố tình thao túng prompt hệ thống trong nội dung câu hỏi nguồn.
- Không log nội dung đề thi, đáp án, token, secret hoặc toàn bộ file khi không cần thiết.

### 2.3. Chuẩn hóa text Unicode NFC

Chuẩn hóa text người dùng/đề thi sang Unicode NFC bằng `unicodedata.normalize("NFC", text)` tại ranh giới nhập hoặc nơi chuẩn hóa dữ liệu đã xác định. Không áp dụng chuẩn hóa một cách mù quáng lên bytes, token, ID kỹ thuật hoặc dữ liệu mà phép biến đổi có thể làm đổi ý nghĩa.

### 2.4. Kiểm soát đầu ra từ AI (Gemini Structured Outputs & Schema Repair)

- Mọi lời gọi Gemini API sinh dữ liệu có cấu trúc (Blueprint, Isomorphic Variant, Solver) phải áp dụng **Structured Outputs với JSON Schema**.
- Kết quả trả về từ LLM phải được parse qua Pydantic schema trong memory.
- Khi LLM trả về cấu trúc thiếu trường hoặc sai định dạng:
  - Phải chuyển qua bộ lọc sửa chữa cú pháp (`schema_repair`) hoặc tự động kích hoạt retry theo ngân sách `retry_count`.
  - Nếu sửa chữa thất bại: Ghi nhận lỗi có cấu trúc, trả mã lỗi phù hợp; tuyệt đối không insert dữ liệu rác, nửa vời vào CSDL (Zero Mutation).

## 3. Database, atomicity và vòng đời State Machine

### 3.1. Zero mutation khi validation thất bại

Nếu pre-validation thất bại (do file lỗi, cú pháp toán học sai, hoặc AI sinh cấu trúc không đạt), không được gọi bất kỳ thao tác ghi DB/Storage nào. Test phải xác nhận không chỉ HTTP status/response mà còn **số lần gọi mutation bằng 0**.

### 3.2. Atomic replacement — Method 2A

- Không triển khai thay thế dữ liệu bằng nhiều lệnh `delete`/`insert` độc lập từ API client qua nhiều network round-trip.
- Toàn bộ thao tác thay thế dữ liệu phụ thuộc phải đi qua **một PostgreSQL Stored Procedure/Function call** theo thiết kế Method 2A, để phần thay đổi dữ liệu liên quan được thực thi trong một transaction nguyên tử.
- Tính atomicity đến từ ranh giới transaction và cách DB thực thi; `SECURITY DEFINER` **không tự tạo ra atomicity**. Chỉ dùng `SECURITY DEFINER` khi cần ranh giới đặc quyền rõ ràng.
- Với function `SECURITY DEFINER`, phải kiểm tra tối thiểu: `search_path` được cố định an toàn (`public, auth, pg_temp`); quyền `EXECUTE` được giới hạn (thu hồi từ `PUBLIC`, `anon`; chỉ cấp cho `authenticated`, `service_role`); quyền/ownership được xác minh ở phía DB; tránh SQL động không an toàn; không dựa vào việc client tự truyền `user_id` để chứng minh quyền sở hữu.
- Kiểm tra mã SQLSTATE/response lỗi chính thức của DB; không suy luận rollback từ việc client nhận được một exception bất kỳ.
- Không tạo mutation phụ trước hoặc sau function có thể khiến kết quả thay thế mất tính nhất quán. Nếu Storage cũng cần thay đổi, thiết kế rõ trình tự, khả năng phục hồi và trạng thái lỗi; không giả định transaction PostgreSQL tự rollback một dịch vụ Storage bên ngoài.

### 3.3. Toàn bộ vòng đời State Machine (10 trạng thái) & Race Condition

Hệ thống quản lý phiên thi qua 10 trạng thái tuần tự chặt chẽ:
```
draft → blueprinted → configured → generating → partial_generated → generated → reviewed → approved → exported
                                  ↳ failed (khi sinh đề thất bại kiệt retry)
```

- **Quy tắc chuyển trạng thái hợp lệ:**
  - `draft`: Chỉ cho phép Ingestion, Confirm Source, Replace Source Questions.
  - `blueprinted`: Chỉ cho phép chỉnh sửa Blueprint, cấu hình ma trận sinh đề (`configured`).
  - `configured`: Cho phép kích hoạt tiến trình sinh đề (`generating`).
  - `generating`: Đang chạy Background Job / SSE stream. Khóa toàn bộ thao tác ghi từ người dùng.
  - `partial_generated` / `generated`: Cho phép chuyển sang bước Review 1-to-1 (`reviewed`).
  - `reviewed`: Cho phép xác nhận phê duyệt toàn bộ đề thi (`approved`).
  - `approved`: Cho phép biên dịch xuất bản tài liệu PDF / Typst / ZIP (`exported`).
- **Bảo vệ Race Condition:**
  - Mọi API thay đổi trạng thái phiên phải kiểm tra trạng thái hiện tại bằng câu lệnh có khóa hàng (`SELECT ... FOR UPDATE`) bên trong transaction hoặc RPC.
  - Bất kỳ request nào cố tình thực hiện thao tác sai trạng thái đều phải bị từ chối với `HTTP 409 Conflict`.

## 4. Authentication, ownership và cảnh báo bảo mật

- Tất cả API phải dùng cơ chế xác thực/dependency hiện có (`get_current_user`); không tự viết đường xác thực thứ hai nếu không có lý do kiến trúc được xác minh.
- Mọi API thao tác session phải kiểm tra quyền sở hữu bằng quy ước `assert_ownership("exam_sessions", session_id, current_user.id)` hoặc cơ chế tương đương đang được dự án chuẩn hóa.
- Không dùng `user_id` do client gửi làm bằng chứng ownership. Danh tính phải lấy từ principal/token đã xác thực.
- Nếu câu hỏi nguồn có `has_security_warning == true`, request phải chứa `acknowledged_security_warnings: true`; nếu thiếu hoặc sai giá trị, trả `HTTP 422` và không mutation.
- Không để lộ dữ liệu của người dùng khác qua response, exception, log hoặc khác biệt response không cần thiết. Giữ hợp đồng `403`/`404` của dự án.

## 5. Tích hợp AI (Gemini API) & Đánh giá toán học (SymPy Engine)

### 5.1. Tích hợp Gemini API (AI Service Layer)

- Sử dụng thư viện chính thức `google-genai` theo wrapper chuẩn tại `app/services/ai/`.
- Quản lý Quota & Rate Limit: Bắt buộc cấu hình cơ chế exponential backoff khi gặp `HTTP 429 Resource Exhausted`.
- Theo dõi chi phí & giám sát: Cập nhật chính xác `gemini_call_count` và `retry_count` trên bản ghi `exam_sessions` sau mỗi lượt gọi LLM.
- Bảo mật thông tin: Tuyệt đối không log nội dung prompt chứa đề thi nhạy cảm hoặc API Key (`GEMINI_API_KEY`).

### 5.2. Đánh giá toán học & Symbolic Computation (SymPy Engine)

- **Giới hạn thời gian tính toán (Timeout Guard):** Các phép toán đại số tượng trưng (tính đạo hàm, giải phương trình, tích phân, kiểm tra tương đương logic) có thể gây treo CPU/DoS. Mọi lời gọi SymPy trong `sympy_evaluator.py` và `logic_checker.py` phải được bảo vệ bởi timeout phù hợp.
- **An toàn cú pháp toán học:**
  - CẤM TUYỆT ĐỐI dùng `eval()` hoặc `exec()` của Python trên chuỗi công thức từ người dùng hoặc do AI sinh ra.
  - Bắt buộc phân tích công thức qua `sympy.parsing.latex.parse_latex` hoặc AST parser an toàn.
  - Đảm bảo runtime ANTLR (`antlr4-python3-runtime`) luôn được cài đặt và kiểm tra smoke test trước khi chạy.

## 6. Xử lý exception phân tán và trạng thái commit chưa xác định

> **Mạng bị ngắt sau khi DB commit nhưng trước khi client nhận response là tình huống hoàn toàn có thể xảy ra.** Một network exception không chứng minh DB chưa commit hoặc đã rollback.

### 6.1. Phân loại bằng kiểu exception

- Cấm phân loại bằng `str(exc)`, nội dung message hoặc tìm từ khóa như `"timeout" in str(exc).lower()`.
- Dùng `isinstance` theo cây kế thừa của thư viện thực tế:
  - Timeout: `(httpx.TimeoutException, httpcore.TimeoutException, TimeoutError)`.
  - Transport/disconnection/protocol: các loại tương ứng của `httpx`/`httpcore`, như `httpx.TransportError`, `httpx.NetworkError`, `httpx.ProtocolError`, `httpcore.NetworkError`, `httpcore.RemoteProtocolError`, `ConnectionError`.
- Rà soát `exc.__cause__` và `exc.__context__` khi cần phân loại exception lồng nhau; chống vòng lặp khi duyệt chain.
- Kiểm tra tên lớp và import trong phiên bản thư viện thực tế của dự án trước khi thêm loại exception mới. Không bắt một superclass quá rộng khiến lỗi lập trình bị gắn nhãn lỗi mạng.
- Thứ tự xử lý phải giữ được bằng chứng: phân loại lỗi DB/API chính thức, lỗi mạng, validation/domain error và lỗi không xác định theo đúng ranh giới của project; không để `except Exception` nuốt các nhánh cụ thể.

### 6.2. Network error: trạng thái commit chưa xác định

Khi timeout, mất kết nối hoặc protocol disconnect xảy ra trong một thao tác ghi và không có bằng chứng xác định kết quả DB:

1. Trả `HTTP 504 Gateway Timeout` theo HTTP contract hiện tại của dự án.
2. Nêu rõ giao dịch có thể đã hoàn tất; **không** nói dữ liệu chắc chắn chưa thay đổi hoặc đã rollback.
3. Hướng dẫn: `Please verify session state before retrying` / “Vui lòng kiểm tra lại trạng thái phiên trước khi thử lại”.
4. Không retry tự động thao tác ghi một cách mù quáng. Nếu nghiệp vụ yêu cầu retry an toàn, phải có cơ chế idempotency/deduplication được thiết kế và kiểm thử rõ ràng.

### 6.3. Chỉ khẳng định rollback khi có bằng chứng

- **Có response lỗi chính thức từ DB** (ví dụ `postgrest.exceptions.APIError` với SQLSTATE như `P0001`, `23505`, v.v. theo đường thực thi đã xác minh): có thể trả `HTTP 500` với thông điệp `Database transaction failed and was rolled back.` chỉ khi kiến trúc transaction/function chứng minh lỗi đó đồng nghĩa transaction đã rollback.
- **Lỗi nội bộ không có bằng chứng DB**: trả `HTTP 500` với thông điệp trung lập; không khẳng định rollback. Hướng dẫn kiểm tra trạng thái phiên nếu kết quả mutation có thể chưa xác định.
- Không tiết lộ stack trace, SQL, secret hoặc nội dung exception nội bộ cho client; log phía server phải đủ ngữ cảnh để điều tra nhưng không ghi dữ liệu nhạy cảm.

## 7. HTTP error contract

Giữ hợp đồng nhất quán giữa endpoint, schema lỗi, test và frontend. Không đổi status chỉ để làm test pass.

| HTTP | Ý nghĩa trong dự án | Hành vi bắt buộc |
|---|---|---|
| `400` | Request/file sai định dạng hoặc vi phạm an ninh file (SEC-04: quá 10 MB, zip bomb, magic bytes không hợp lệ) | Từ chối trước khi có mutation; message không tiết lộ nội bộ |
| `401` | Thiếu token hoặc JWT không hợp lệ/hết hạn | Không chạy nghiệp vụ cần xác thực |
| `403` | Không có quyền truy cập theo contract hiện tại | Không đọc/ghi dữ liệu ngoài quyền |
| `404` | Session/tài nguyên không tồn tại theo contract | Không mutation |
| `409` | Xung đột state machine, ví dụ session không ở trạng thái hợp lệ của action | Trả trạng thái hiện tại/xung đột theo schema đã thống nhất; không mutation sai trạng thái |
| `422` | Cú pháp request hợp lệ nhưng dữ liệu vi phạm nghiệp vụ: thiếu đáp án, OMML không parse được, số câu ngoài `[1, 20]`, AI schema lỗi, chưa xác nhận cảnh báo bảo mật | Response có cấu trúc ổn định; validation failure không ghi DB/Storage |
| `504` | Timeout/mất kết nối upstream mà kết quả mutation chưa xác định | Nêu uncertain commit; yêu cầu kiểm tra trạng thái trước khi retry |
| `500` | Lỗi thực thi nội bộ hoặc DB failure đã được phân loại theo bằng chứng | Không khẳng định rollback nếu không có bằng chứng CSDL rõ ràng |

## 8. Chuẩn mã nguồn và kiến trúc

- Runtime: Python 3.11+, FastAPI, Pydantic v2.
- Mọi hàm, route, dependency và service mới/sửa đổi phải có type annotation đầy đủ; dùng `list[T]`, `dict[K, V]`, `Optional[T]` khi thích hợp và kiểm tra `None` rõ ràng.
- Tuân thủ Ruff với `line-length = 100` và Mypy theo cấu hình `backend/pyproject.toml`; không tạo `Any` để né type error nếu có thể biểu diễn type chính xác.
- Giữ ranh giới module hiện hữu (route/dependency → service → parser/AI/DB adapter); không nhét parsing, authorization, AI prompt và transaction vào một hàm lớn.
- Dọn dẹp tài nguyên & file tạm: Mọi thao tác biên dịch Typst/PDF hoặc đóng gói ZIP xuất bản (Export Engine) phải dọn sạch thư mục tạm sau khi hoàn tất.
- Dùng logging chuẩn; không thêm `print()` debug vào code production.
- Response/schema phải ổn định và tương thích frontend. Không đổi tên field, error code hoặc ý nghĩa status mà không rà soát consumer/test liên quan.

## 9. Kiểm thử bắt buộc theo failure mode

Với mỗi thay đổi, chọn test phù hợp; không nhất thiết mọi task phải test mọi nhóm, nhưng kế hoạch phải giải thích vì sao nhóm nào không áp dụng.

- **Happy path:** dữ liệu hợp lệ tạo kết quả đúng.
- **Boundary/validation:** biên số câu `[1, 20]`, thiếu đáp án, OMML lỗi/không hỗ trợ, file trống/giả mạo/quá lớn khi liên quan.
- **No-side-effect:** validation/auth/state failure không gọi mutation DB/Storage.
- **Security:** người dùng không sở hữu session, token thiếu/hết hạn, cảnh báo bảo mật chưa acknowledge.
- **Transaction/state:** atomic replacement, lỗi DB chính thức, trạng thái không hợp lệ và race condition khi phù hợp.
- **Distributed exception:** timeout có message rỗng, read error, remote disconnect sau xử lý, lỗi DB có bằng chứng rollback và lỗi nội bộ không có bằng chứng rollback.
- **AI/Math failure mode:** AI sinh sai schema, SymPy timeout, công thức LaTeX không parse được.
- **Regression:** các endpoint hoặc luồng cũ liên quan vẫn hoạt động.
- Dùng exception thật của thư viện trong test fault injection; không tạo `RuntimeError("httpx.ReadTimeout ...")` để giả lập lỗi mạng.

## 10. Git và Quy tắc kiểm tra CI trước khi Push

- **Phạm vi sửa đổi:** Tuyệt đối không chạy `ruff format app/ tests/` hoặc `ruff check --fix` trên toàn bộ codebase để sửa task cục bộ. Chỉ format và sửa lint trên các file thuộc task.
- **File rác:** Không commit file kế hoạch sprint chung (ví dụ `w2_21_10.md`), scratchpad cá nhân, log, file tạm hoặc cache.
- **Bắt buộc vượt qua 4 kiểm tra CI cục bộ trước khi push (tương đương GitHub Actions `ci.yml`):**
  1. `ruff check backend/app`
  2. `mypy backend/app --ignore-missing-imports`
  3. SymPy LaTeX smoke test: `parse_latex('x^2 + 1')`
  4. Pytest toàn bộ backend suite với test env vars đầy đủ (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`).
- Chỉ stage đúng các file task cần thiết. Không chạy `git restore` trên file có sẵn thay đổi của người khác khi chưa xác minh nguồn thay đổi.

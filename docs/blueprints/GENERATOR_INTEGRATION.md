> Backend W2 đã tích hợp lõi extractor dùng chung; không spawn CLI từ routes. Dùng [contract AI W2](../ai-w2-integration.md) và chỉ extract sau xác nhận nguồn. Tài liệu bên dưới giữ hợp đồng CLI độc lập.

**Hợp đồng bàn giao script tạo blueprint cho người phụ trách generator**

Giao diện này đã được triển khai tại [create_blueprints.py](../../scripts/blueprint/create_blueprints.py). Đã kiểm thử file/stdin, single/batch, gọi từ working directory khác và API Gemini thật. Hướng dẫn chạy, cấu hình và kết quả kiểm thử tóm tắt nằm trong [README script](../../scripts/blueprint/README.md). Phase tạo blueprint bàn giao qua file JSON; phần tích hợp generator do người phụ trách phase generate thực hiện.

**1. Trách nhiệm hai phía**

| Script tạo blueprint | Chương trình gọi, bao gồm generator |
|---|---|
| Nhận JSON câu mẫu từ file hoặc stdin. | Chuẩn bị câu nguồn tự đầy đủ, ID và context nếu có. |
| Gọi AI API và kiểm tra từng blueprint. | Gọi script bằng interpreter có dependencies riêng. |
| Ghi một file JSON chứa kết quả một hoặc nhiều câu. | Đọc exit code và file kết quả, ghép về câu nguồn bằng question_id. |
| Trả lỗi riêng từng câu và lỗi toàn lần gọi. | Quyết định xử lý câu lỗi hoặc gọi lại các câu cần thiết. |
| Kết thúc sau khi ghi kết quả. | Tự thực hiện phase generate, hiển thị candidate và vòng phản hồi. |

Script không cần backend server, session, DB hoặc quyền truy cập code generator. Câu nguồn là dữ liệu đã được parser/caller chuẩn hóa; script không nhận DOCX/PDF để tự tách câu trong hợp đồng này.

**2. Môi trường và cách gọi**

Môi trường và cấu hình được hướng dẫn trong [README script](../../scripts/blueprint/README.md). Truyền khóa bằng `GEMINI_API_KEY`; model ưu tiên `--model`, `BLUEPRINT_MODEL`, `GEMINI_MODEL`, `[ai].model` trong file `--config`, rồi mặc định `gemini-3.5-flash-lite`. Dùng [TOML mẫu](blueprint.config.example.toml) nếu cần. `--provider mock` dành cho thử hợp đồng không gọi mạng.

Caller phải nạp key/model vào môi trường subprocess; script không tự đọc `.env` hay `.env.example`. Script truyền GEMINI_API_KEY tường minh vào SDK để tránh key khác trong môi trường ghi đè ngầm.

Ví dụ lệnh, dùng interpreter của môi trường đã cài đúng dependencies:

```text
python scripts/blueprint/create_blueprints.py --mode single --input question.json --output blueprint-result.json
python scripts/blueprint/create_blueprints.py --mode batch --input questions.json --output blueprints-result.json --concurrency 3
python scripts/blueprint/create_blueprints.py --mode single --input - --output blueprint-result.json
```

Khi gọi từ chương trình khác, dùng đường dẫn tuyệt đối cho script, input và output. Working directory không cần là gốc repo. Script tự tìm schema/prompt theo vị trí cài đặt; nếu bàn giao ngoài repo phải kèm tài nguyên và có thể dùng `--schema` để trỏ file chuẩn.

Một lần chạy batch là một subprocess và một file output. Bên trong script, mỗi câu có request AI riêng và được giới hạn đồng thời; caller không cần tự tách thành nhiều process cho từng câu.

Input phải là UTF-8 và toàn document không vượt `262144` byte; đây không phải giới hạn từng câu. JSON trùng khóa, NaN/Infinity hoặc nhiều document nối nhau bị từ chối. Thời gian chờ hàng đợi của batch nằm ngoài timeout từng câu. Với `n` câu và concurrency `c`, caller nên cấp tối thiểu `ceil(n/c) * item_timeout_seconds` cộng thời gian khởi động/I/O, hoặc áp giới hạn toàn process theo nhu cầu riêng.

**3. JSON đầu vào một câu**

Mode `single` nhận trực tiếp object sau, không bọc trong `questions`:

```json
{
  "source": {
    "question_id": "q_derivative_001",
    "content": [
      {
        "id": "SRC_STEM",
        "type": "text",
        "text": "Tính đạo hàm của f(x) = x^2 + 4x + 4 tại x = 0."
      }
    ],
    "options": [],
    "supplied_answer": null,
    "supplied_solution": null,
    "references": []
  },
  "context": {
    "subject": "mathematics",
    "language": "vi",
    "audience": null,
    "generation_preferences": null
  }
}
```

`source` tuân theo `$defs.source` trong [schema chuẩn](science-blueprint.schema.json). Trường `context` tùy chọn; nếu có thì chỉ gồm `subject`, `language`, `audience`, `generation_preferences`, mỗi trường được phép bỏ hoặc có giá trị `null`. Subject dùng enum của schema, language dùng mã ngôn ngữ, audience và generation_preferences là mô tả bằng chuỗi. Context chỉ hướng dẫn trích xuất, không thêm trường vào blueprint.

Trong `source`, đáp án và lời giải chỉ ghi khi có từ nguồn. Không có thì dùng `null`; thiếu phương án/tham chiếu thì dùng `[]`. Phần dẫn chung, dữ kiện bảng và công thức cần đưa vào `content` để câu tự đầy đủ. Các block text/formula/table phải là dữ liệu thực, không phải ảnh. Caller chịu trách nhiệm giữ ánh xạ với dữ liệu parser gốc.

Các ID bắt đầu bằng chữ, theo pattern của schema. Nếu DB dùng UUID bắt đầu bằng số, dùng `q_<uuid>` làm question_id và giữ ánh xạ ở caller. ID trong mỗi blueprint là phạm vi riêng; ví dụ `SRC_STEM` có thể xuất hiện ở các câu khác nhau. Question_id phải duy nhất trong batch.

Mọi trường trong `source` ở ví dụ đều bắt buộc, kể cả khi giá trị là `[]`/`null`. Có thể bỏ hẳn `context`, nhưng không truyền `context: null`; bên trong context, từng thuộc tính được phép bỏ hoặc null. `subject` là mã enum tiếng Anh, `language` là mã như `vi`/`en`; không dùng tên môn/ngôn ngữ tự do. Nên truyền cả hai để giảm suy đoán của AI.

**4. JSON đầu vào nhiều câu**

Mode `batch` nhận object có duy nhất trường `questions`, là danh sách không rỗng các item cùng cấu trúc single. Ví dụ hai câu:

```json
{
  "questions": [
    {
      "source": {
        "question_id": "q_math_001",
        "content": [
          {
            "id": "SRC_STEM",
            "type": "text",
            "text": "Tính đạo hàm của f(x) = x^2 + 4x + 4 tại x = 0."
          }
        ],
        "options": [],
        "supplied_answer": null,
        "supplied_solution": null,
        "references": []
      },
      "context": {"subject": "mathematics", "language": "vi"}
    },
    {
      "source": {
        "question_id": "q_physics_001",
        "content": [
          {
            "id": "SRC_STEM",
            "type": "text",
            "text": "Một vật có khối lượng 2 kg chịu hợp lực 6 N. Tính độ lớn gia tốc của vật trong hệ quy chiếu quán tính."
          }
        ],
        "options": [],
        "supplied_answer": null,
        "supplied_solution": null,
        "references": []
      },
      "context": {"subject": "physics", "language": "vi"}
    }
  ]
}
```

Mỗi câu có context riêng; batch không áp một ngôn ngữ hay một môn chung cho mọi câu. Script giữ thứ tự input, dù các request AI hoàn tất khác thứ tự.

**5. File JSON kết quả dùng chung**

File kết quả gồm các trường sau; `contract_version` là phiên bản envelope, khác `requirement.schema_version` của blueprint:

| Trường | Ý nghĩa |
|---|---|
| `contract_version` | `"1.0.0"`. |
| `mode` | `"single"` hoặc `"batch"`, khớp mode đã gọi. |
| `results` | Danh sách kết quả theo thứ tự input. Single cũng dùng danh sách nhưng có một item. |
| `results[].index` | Vị trí input, bắt đầu từ 0. |
| `results[].question_id` | Khớp source.question_id; nếu item lỗi không có ID hợp lệ thì là `null`. |
| `results[].blueprint` | Blueprint đầy đủ theo schema `0.4.0`, hoặc `null` khi item lỗi. |
| `results[].error` | `null` khi thành công; khi lỗi là object `code`, `message`, `details`. |
| `summary` | `total`, `succeeded`, `failed`; tổng thành công và lỗi bằng số item. |
| `error` | `null` khi đã xử lý từng item; object lỗi toàn lần gọi nếu preflight không thể tiếp tục. |
| `run_metadata` | Thông tin kỹ thuật lần chạy; không thuộc nội dung blueprint. |

Mỗi item có đúng một trong blueprint/error khác null. Khi item có blueprint, lấy nguyên object đó để lưu hoặc truyền sang phase generate; không truyền cả envelope như thể đó là một blueprint. Hai phần trong object blueprint vẫn chỉ là `requirement` và `constraint`.

Đường dẫn lấy dữ liệu là `result["results"][i]["blueprint"]`. Script tạo `blueprint_id` mới cho từng lần trích xuất; `question_id` giữ ánh xạ về source của caller. Source được script sao chép nguyên giá trị JSON (gồm text/LaTeX, options, đáp án/lời giải có sẵn); thứ tự key và cách thụt dòng trong file không được coi là nội dung nguồn.

`source_check.computed_answer` là đề xuất của AI, tách khỏi `source.supplied_answer`. Extractor hiện luôn đặt `source_check.methods=[]`, `evidence=[]` vì không có bộ xác minh chuyên môn. Thành công của script nghĩa là đạt schema và các kiểm tra liên trường đang triển khai; caller vẫn phải thẩm định nội dung trước khi dùng cho phase generate.

Ví dụ kết quả single bị từ chối vì phụ thuộc hình, exit code `4` (metadata rút gọn):

```json
{
  "contract_version": "1.0.0",
  "mode": "single",
  "results": [
    {
      "index": 0,
      "question_id": "q_image",
      "blueprint": null,
      "error": {
        "code": "IMAGE_DEPENDENCY",
        "message": "Câu có dữ kiện phụ thuộc hình; phase này chỉ nhận văn bản, công thức và bảng.",
        "details": []
      }
    }
  ],
  "summary": {"total": 1, "succeeded": 0, "failed": 1},
  "error": null,
  "run_metadata": {"requests": 0}
}
```

Lỗi toàn lần gọi có hình dạng khác: `error` ở root khác null, `results=[]` và summary đều `0`. Batch có lỗi riêng câu vẫn giữ đủ item; nhận các blueprint thành công và xử lý item lỗi theo index/question_id.

Không có `status`, `review_status`, `boundary_examples` hoặc `open_issues` trong blueprint. Thông tin lỗi của lần chạy không khóa blueprint hoặc tạo trạng thái duyệt.

Lỗi cấp lần gọi như JSON hỏng, mode không khớp shape, ID trùng hoặc thiếu cấu hình cần thiết có `error` cấp file, `results: []` và summary bằng 0. Item có cấu trúc/nội dung riêng không hợp lệ được ghi lỗi tại vị trí tương ứng; các item khác tiếp tục. Chẩn đoán chi tiết dùng JSON Pointer nếu có thể. Không có file output nếu lỗi I/O khiến script không ghi được; stderr sẽ ghi nguyên nhân.

**6. Exit code và cách caller xử lý**

| Exit code | Hành động của caller |
|---|---|
| `0` | Đọc file, kiểm tra contract và nhận mọi blueprint. |
| `3` | Đọc file batch; nhận các item thành công, xử lý riêng item lỗi. |
| `4` | Đọc file lấy lỗi từng câu; không có blueprint thành công trong lần này. |
| `2` | Đọc envelope lỗi nếu có; nếu tham số CLI không đủ để xác định output thì dùng stderr. Sửa input/cấu hình trước khi gọi lại. |
| `1` | Dùng stderr và kiểm tra file có phải kết quả mới không; không tự tiếp tục generate từ file cũ. |

`0`, `3`, `4` chỉ trả sau khi ghi file kết quả hoàn tất. Single thành công dùng `0`, item lỗi dùng `4`; mã `3` chỉ áp dụng batch thành công một phần. Exit code là kết quả process, không phải trạng thái vòng đời blueprint.

Các code thường gặp và nơi xử lý:

| Code | Vị trí thường gặp | Việc caller cần làm |
|---|---|---|
| `API_KEY_MISSING`, `CONFIG_INVALID` | Root `error`, exit 2 | Sửa môi trường hoặc cấu hình trước khi gọi lại. |
| `INVALID_JSON`, `DUPLICATE_JSON_KEY`, `INPUT_TOO_LARGE`, `DUPLICATE_QUESTION_ID` | Root `error`, exit 2 | Sửa JSON/ID hoặc chia nhỏ batch; không tự cắt câu. |
| `ITEM_INPUT_INVALID`, `IMAGE_DEPENDENCY` | `results[i].error` | Sửa dữ liệu riêng câu hoặc bỏ câu không được hỗ trợ. |
| `API_AUTH`, `API_MODEL` | `results[i].error` | Kiểm tra quyền truy cập và model; không fallback ngầm. |
| `API_REQUEST`, `API_TRANSPORT`, `ITEM_TIMEOUT` | `results[i].error` | Xem HTTP status nếu có, quota/kết nối/budget; caller quyết định gọi lại. |
| `BLUEPRINT_INVALID` | `results[i].error` | Đã hết budget mà chưa hợp lệ; xem details và metadata, rà soát câu/prompt. |
| `MOCK_NO_FIXTURE` | `results[i].error` | Dùng source khớp fixture hoặc chuyển tường minh sang provider thật. |

Bảng là các code điển hình, không phải enum đóng của mọi lỗi SDK. Message SDK thô không được ghi vì có thể chứa thông tin nhạy cảm. Lỗi có thể ghi JSON Pointer trong details khi xác định được vị trí.

Caller cấp output path mới trong thư mục tạm riêng cho từng lần gọi để tránh nhầm kết quả cũ. Script ghi file tạm rồi thay thế nguyên tử; không đọc output khi process còn chạy. Timeout của caller phải tính đến số câu, concurrency và ngân sách request mỗi câu. Nếu caller dừng process do timeout thì coi lần gọi chưa hoàn tất, không nhận file cũ.

Khi dùng `subprocess`, truyền danh sách argument và `shell=False`; JSON đi qua stdin với UTF-8 hoặc input file. Không ghép JSON thành command string. Mẫu gọi tham khảo dưới đây chỉ minh họa hợp đồng, không phải code tích hợp đã thêm vào generator:

```python
import json
import subprocess
import tempfile
from pathlib import Path

# Các đường dẫn và request_payload do chương trình gọi chuẩn bị.
with tempfile.TemporaryDirectory(prefix="blueprint_run_") as run_dir:
    output_path = Path(run_dir) / "result.json"
    process = subprocess.run(
        [
            str(python_executable),
            str(script_path),
            "--mode", mode,
            "--input", "-",
            "--output", str(output_path),
        ],
        input=json.dumps(request_payload, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        shell=False,
        timeout=caller_timeout_seconds,
    )
    if process.returncode not in (0, 3, 4):
        raise RuntimeError(process.stderr)
    result = json.loads(output_path.read_text(encoding="utf-8"))
    # Kiểm tra envelope, mode, index và question_id trước khi nhận blueprint.
```

Không dùng `check=True` nếu caller muốn xử lý file kết quả thành công một phần với exit code `3`. Khi đọc xong, kiểm tra phiên bản envelope, summary, số item, index và question_id so với input; chỉ nhận item có error null và blueprint hợp lệ. Metadata model/prompt/schema hash giúp truy lại đúng lần tạo blueprint.

**7. Việc cần làm sau khi nhận blueprint — do người phụ trách generator thực hiện**

Generator lấy chính sách và mô hình từ blueprint, dựng prompt sinh candidate theo các điều kiện đó và kiểm tra candidate của phase generate. Phản hồi có thể dẫn đến sửa blueprint hiện hành hoặc cấu hình generator; các bước đó không do script tạo blueprint tự kích hoạt.

Nếu muốn trích xuất lại, caller gọi lại script với source/context mới. Đây là thao tác tạo blueprint mới và có thể thay nội dung do AI đề xuất; caller tự quyết định lưu/thay thế/so sánh với bản đã sửa tay. Script không tự ghi đè blueprint đang được người dùng chỉnh trong ứng dụng.

Người tích hợp tự quản lưu trữ, phiên bản nội dung, candidate và giao diện. Không cần endpoint confirm hoặc trạng thái duyệt để gọi script. File kết quả là điểm bàn giao giữa hai phase.

# Cấu trúc blueprint chung cho các môn tự nhiên — 0.4.0

## Tài liệu bàn giao và thứ tự đọc

| Nhu cầu | Đọc tài liệu | Nội dung chính |
|---|---|---|
| Chạy thử và cấu hình | [README script](../../scripts/blueprint/README.md), [TOML mẫu](blueprint.config.example.toml) | Build, cấp key, single/batch, cấu hình, kiểm thử và giới hạn. |
| Tích hợp với generator | [Generator integration](GENERATOR_INTEGRATION.md) | Input/output single/batch, exit code, xử lý lỗi và lấy blueprint từ envelope. |
| Hiểu nội dung blueprint | README này, [schema chuẩn](science-blueprint.schema.json), [examples](examples) | Ý nghĩa trường, ngôn ngữ, tương đương và bất biến. |

Commit ba tài liệu: README này, `GENERATOR_INTEGRATION.md` và `scripts/blueprint/README.md`, cùng schema `science-blueprint.schema.json`, bốn file `examples/*.json` và TOML mẫu. Schema chuẩn/contracts trong code xác định shape; `config.py` xác định cấu hình thực thi. Kết quả kiểm thử có ngày kiểm tra được tóm tắt trong README script; không duy trì plan/report phiên làm việc thành tài liệu riêng.

Phần tạo candidate và vòng phản hồi bên dưới là thiết kế cho phase generate; script TASK-203 hiện kết thúc sau khi ghi file blueprint.

Phạm vi gồm Toán, Vật lý, Hóa học, Sinh học và câu tích hợp giữa các môn này. Mỗi blueprint mô tả một họ biến thể của một câu nguồn, với nội dung dạng văn bản, công thức hoặc bảng dữ liệu. Cấu trúc dùng cho câu tính toán, câu lý thuyết, câu suy luận từ số liệu và câu giải thích.

Hợp đồng dữ liệu nằm trong [science-blueprint.schema.json](science-blueprint.schema.json), sử dụng JSON Schema Draft 2020-12. Script độc lập cho TASK-203 đã được triển khai và thử Gemini API thật; cách sử dụng, kiểm thử và giới hạn nằm trong [README script](../../scripts/blueprint/README.md). Validator cấu trúc/tham chiếu đã có; bộ kiểm tra chuyên môn tổng quát và thẩm định sư phạm vẫn cần phát triển riêng.

Phase này nhận JSON một hoặc nhiều câu và xuất một file JSON kết quả; cách generator gọi script nằm trong [GENERATOR_INTEGRATION.md](GENERATOR_INTEGRATION.md). Môi trường Docker và model `gemini-3.5-flash-lite` được cấu hình độc lập. Việc tích hợp generator thuộc người thực hiện phase generate.

Luồng hiện tại là tạo một blueprint ban đầu, dùng generator sinh đúng một candidate, rồi dựa trên candidate để chỉnh blueprint và generator. Blueprint được cập nhật liên tục và không có trạng thái hay bước chuyển trạng thái để cho phép chỉnh sửa hoặc sinh câu. Hợp đồng hiện có 17 trường cấp nội dung: 14 trong `requirement` và 3 trong `constraint`.

Mỗi bản ghi có đúng hai phần chính:

| Phần | Vai trò |
|---|---|
| `requirement` | Mô tả câu nguồn, năng lực cần đánh giá, cấu trúc kiến thức, các bất biến, phạm vi biến đổi và cách trả lời. |
| `constraint` | Ghi kết quả kiểm tra câu nguồn và các điều kiện phải kiểm tra trên blueprint hoặc câu sinh ra. |

Tên trường luôn bằng tiếng Anh. Các mã như `physics`, `single_choice`, `required`, `pass` giữ ổn định để phần mềm xử lý. Nội dung mô tả, giải thích, tiêu chí chấm và ví dụ dùng cùng ngôn ngữ với đề nguồn; ngôn ngữ được ghi tại `requirement.language`. Công thức, ký hiệu, đơn vị chuẩn và mã định danh không dịch. Các chú giải của file schema này viết bằng tiếng Việt để nhóm đọc; chúng không quyết định ngôn ngữ của dữ liệu từng câu.

Ví dụ quy tắc ngôn ngữ:

```json
{
  "language": "vi",
  "language_policy": {
    "field_names": "en",
    "descriptive_values": "source_language",
    "machine_codes": "stable"
  }
}
```

**Các trường của Requirement**

| Trường | Nội dung và cách sử dụng |
|---|---|
| `blueprint_id`, `schema_version` | Định danh bản ghi và phiên bản hợp đồng. Phiên bản hiện tại là `0.4.0`; đây là phiên bản cấu trúc dữ liệu, không phải số lần người dùng sửa blueprint. |
| `subject` | `mathematics`, `physics`, `chemistry`, `biology` hoặc `integrated_science`. |
| `language`, `language_policy` | Ngôn ngữ đề nguồn và chính sách ngôn ngữ đã nêu. |
| `source` | Nội dung câu nguồn, phương án nếu có, đáp án và lời giải được cung cấp, nguồn tham khảo. Đáp án được cung cấp không mặc nhiên đúng. |
| `assessment` | Mục tiêu đánh giá, kiến thức, thao tác nhận thức và kiến thức tiên quyết. |
| `knowledge_basis` | Các định luật, định nghĩa hoặc mệnh đề làm cơ sở. Ghi rõ lấy từ đề, tài liệu hay do AI suy ra; ghi tham chiếu bằng chứng. |
| `semantic_model` | Đối tượng, đại lượng, quan hệ, giả thiết và đích cần tìm. Cùng một bộ trường dùng cho cả bốn môn. |
| `reasoning_model` | Các bước suy luận chính và quan hệ phụ thuộc; các cách giải khác chấp nhận được; lối tắt làm mất yêu cầu đánh giá. |
| `invariants` | Những đặc trưng bắt buộc giữ: kiến thức, quan hệ, cách suy luận, mức tính toán, điều kiện áp dụng, phân phối xác suất hoặc dạng trả lời. |
| `variation_policy` | Mức tương đương, phép biến đổi được phép, điều kiện áp dụng, miền giá trị tham số nếu có, thay đổi bị cấm và giới hạn công việc học sinh phải làm. |
| `response_spec` | Dạng trả lời, số phương án nếu có, cách chấm, đơn vị, dung sai, làm tròn và chính sách phương án nhiễu. |
| `presentation` | Chỉ nhận văn bản, công thức và bảng; cấm phụ thuộc hình ảnh; các yêu cầu diễn đạt. |

Các trường cấp trên đều xuất hiện trong mọi bản ghi để hợp đồng ổn định. Danh sách không áp dụng dùng `[]`; một giá trị đơn chưa biết hoặc không áp dụng dùng `null` theo schema. Không dùng chuỗi rỗng thay cho dữ kiện thiếu. Ví dụ, câu Hóa học nhận biết định luật có `quantities: []`; câu trả lời bằng lời có `expected_unit: null`.

`source.content` chứa các khối có kiểu `text`, `formula`, `table`. Phần dẫn chung cần để ngay trong các khối này hoặc được giải quyết từ nguồn để câu tự đầy đủ; không để câu sinh ra phụ thuộc một đoạn dẫn bị thiếu. Với bảng, `columns` chứa tên cột còn `rows` chứa dữ liệu; tên cột là nội dung, được viết theo ngôn ngữ đề.

`source.supplied_answer` và `source.supplied_solution` chỉ chứa nội dung có sẵn từ nguồn. Lời giải do AI suy ra đi vào `reasoning_model` và `constraint.source_check`, không được ghi thành lời giải nguồn. Một đáp án gồm `option_ids`, `value`, `explanation`; ít nhất một phần phải có nội dung. Khi thiếu đáp án nguồn vẫn có thể tạo blueprint và sinh candidate, nhưng đáp án suy ra cần được xác minh độc lập khi đánh giá kết quả.

**Biểu diễn kiến thức của từng môn bằng cùng một cấu trúc**

| Trường trong `semantic_model` | Toán | Vật lý | Hóa học | Sinh học |
|---|---|---|---|---|
| `entities` | Hàm, tập hợp, biến cố, đa giác | Vật, hệ, quá trình | Chất, hệ, phản ứng | Tế bào, cơ thể, quần thể, quá trình |
| `quantities` | Hệ số, số lượng, xác suất | Khối lượng, lực, điện áp | Khối lượng, lượng chất, nồng độ | Số cá thể, tỉ lệ, kết quả đo |
| `relations` | Phương trình, quan hệ tập hợp | Quan hệ giữa các đại lượng | Bảo toàn, phương trình phản ứng | Nhân quả, điều hòa, quy luật di truyền |
| `assumptions` | Miền xác định, đồng khả năng | Hệ quy chiếu, bỏ qua lực cản | Hệ kín, điều kiện phản ứng | Điều kiện môi trường, tính thấm của màng |
| `target` | Tìm giá trị hoặc chứng minh | Tính, dự đoán hoặc giải thích | Nhận biết, tính hoặc suy luận | Nhận biết, dự đoán hoặc giải thích |

Đặc trưng riêng của câu nằm trong giá trị dữ liệu và các quan hệ; không tạo trường cấp cao riêng như `red_lamp_count` hay `cell_membrane_type`. Các lượng đó được biểu diễn thành phần tử có `id`, `description`, `value` và `unit`. Câu lý thuyết có thể không có đại lượng số nào.

Giá trị số có kiểu `integer`, `decimal`, `rational`; ngoài ra có `symbolic`, `text`, `boolean`. Ví dụ phân số dùng `{"type":"rational","numerator":32,"denominator":55}`. Số thập phân dùng chuỗi, ví dụ `{"type":"decimal","value":"9.8"}`. Đơn vị lưu riêng; việc quy đổi đơn vị và so sánh số cần bộ kiểm tra chuyên môn.

`relations.expression` là biểu diễn bổ trợ cho `description`. `formalism` cho biết cách đọc: công thức toán, LaTeX, logic hoặc phương trình hóa học. Khi quan hệ chỉ có thể mô tả bằng lời, dùng `formalism: "none"` và `expression: null`. Không yêu cầu mọi câu lý thuyết phải ép thành công thức. Chuỗi biểu thức là dữ liệu, không thực thi bằng `eval`.

`assumptions` và `knowledge_basis` ghi `origin: "source" | "inferred" | "reference"`. Hai trường hợp lấy từ nguồn hoặc tài liệu phải có `evidence_refs` trỏ tới khối nội dung hay tài liệu tương ứng. AI suy đoán một điều kiện chưa có trong đề phải đánh dấu là suy ra. Người dùng đối chiếu các giả thiết này khi xem candidate và sửa blueprint nếu cần; việc ghi nguồn gốc hoặc bằng chứng không tự chứng minh mệnh đề đúng. Khi dựng blueprint từ đề đúng, quan hệ suy ra có thể dùng làm thông tin nội bộ nhưng không mặc định đưa vào câu hỏi để học sinh đọc.

**Đẳng cấu và phạm vi biến đổi**

`strict_structure` yêu cầu giữ cấu trúc quan hệ và yêu cầu suy luận trong blueprint hiện tại. Các yêu cầu được đối chiếu trên candidate và có thể chỉnh sửa qua từng vòng phản hồi. `assessment_equivalent` cho phép thay đổi cấu trúc cụ thể trong giới hạn đã nêu nếu vẫn giữ mục tiêu đánh giá; mức này cần thẩm định riêng và không được tự động báo là đẳng cấu chặt.

Mỗi phép biến đổi có đối tượng áp dụng, điều kiện trước khi đổi và giới hạn. Khi kết hợp nhiều phép biến đổi, phải đánh giá lại toàn bộ câu; việc từng phép biến đổi riêng lẻ hợp lệ chưa bảo đảm tổ hợp của chúng hợp lệ. `workload_limits` là tiêu chí dự kiến về lượng tính toán hoặc suy luận, không chứng minh hai câu có độ khó thực nghiệm bằng nhau.

`parameter_domains` chỉ dùng khi có đại lượng được biến thiên. Các giới hạn trong cùng một miền được áp dụng đồng thời: danh sách giá trị, cận dưới, cận trên và điều kiện bằng lời. Cận số là cận đóng; kiểu và đơn vị phải phù hợp đại lượng được tham chiếu. Quan hệ liên tham số, như lực chia khối lượng phải là số nguyên, ghi trong `conditions` và phải được bộ kiểm tra chuyên môn xác nhận. Câu lý thuyết có thể để danh sách này rỗng.

Không được tự mở rộng phạm vi biến đổi để đủ số lượng câu. Nếu một họ câu chỉ có ít biến thể có ý nghĩa, cần báo giới hạn để người dùng điều chỉnh phạm vi hoặc tạo một họ khác.

**Định dạng trả lời và cách chấm**

| `response_spec.format` | Quy ước |
|---|---|
| `single_choice` | Có phương án; đúng một đáp án; chấm theo khóa sau khi xác minh nội dung. |
| `multiple_choice` | Có phương án; số đáp án đúng được khai báo; chấm tập khóa. |
| `true_false` | Một mệnh đề đúng/sai; giá trị đáp án là boolean. |
| `numeric` | Giá trị số, đơn vị, dung sai và làm tròn được quy định. |
| `short_text` | Câu trả lời ngắn; chọn so khớp giá trị, tương đương biểu thức hoặc tiêu chí chấm tùy nội dung. |
| `explanation` | Chấm bằng danh sách tiêu chí có mô tả và điểm, chấp nhận diễn đạt tương đương. |

Một bộ câu đúng/sai có nhiều ý được tách thành các câu nguyên tử ở phiên bản này. Nếu các ý phụ thuộc nhau hoặc dùng kết quả của ý trước thì phải thiết kế hỗ trợ câu nhiều phần trước khi sử dụng; không tự tách làm mất phụ thuộc.

Với dung sai số: chấp nhận khi sai lệch tuyệt đối không vượt quá `max(absolute, relative × abs(expected))`, sau khi quy đổi đúng đơn vị. `numeric_tolerance: null` nghĩa là so sánh chính xác khi đang chấm giá trị số. Không mặc định làm tròn; nếu có, ghi quy tắc cụ thể. Với tiêu chí chấm bằng lời, dung sai số không áp dụng.

**Các trường của Constraint**

| Trường | Nội dung |
|---|---|
| `validation_policy` | Quy ước kết quả kiểm tra `pass/fail/unknown`; điều kiện bắt buộc chưa xác minh sẽ chặn tự động chấp nhận candidate; điểm khuyến nghị không bù được lỗi bắt buộc. |
| `source_check` | Đáp án suy ra của câu nguồn, phương pháp và bằng chứng kiểm tra. Nếu chưa có đáp án suy ra dùng `null`; phương pháp và bằng chứng chưa có dùng `[]`. |
| `rules[].requirement_refs` | Các ID trong Requirement mà điều kiện kiểm tra phục vụ. |
| `rules[].scope` | Kiểm tra blueprint, nguồn, câu mới, cặp nguồn–câu mới hay cả lô sinh. |
| `rules[].severity` | `required` hoặc `advisory`. |
| `rules[].verification_methods` | Kiểm tra schema, toán chính xác, liệt kê, đơn vị, luật chuyên môn, đối chiếu nguồn, tiêu chí ngữ nghĩa hoặc người duyệt. |
| `rules[].pass_criteria` | Tiêu chí cụ thể để kết luận đạt; không chỉ viết “câu phải đúng”. |
| `rules[].on_failure` | Loại, sinh lại hoặc chuyển duyệt khi điều kiện thất bại. |

Các tên phương pháp chỉ khai báo cách kiểm tra dự kiến, chưa chứng minh project có bộ kiểm tra tương ứng. Khi không có bộ kiểm tra hoặc không đủ bằng chứng, kết quả là `unknown`. LLM đánh giá ngữ nghĩa có thể hỗ trợ nhưng không tương đương một chứng minh hoặc nguồn kiến thức đã xác minh.

`pass/fail/unknown` là kết quả từng lần chạy kiểm tra, được quản lý cùng candidate và bản blueprint đã dùng bên ngoài hợp đồng này. Chúng không tạo vòng đời cho blueprint và không khóa quyền cập nhật. `source_check.methods` và `source_check.evidence` chỉ ghi những phương pháp đã thực hiện và bằng chứng thực tế; kết quả tổng hợp của mỗi lần kiểm tra được quản lý bên ngoài blueprint.

`source_check.computed_answer` là đáp án của câu nguồn. Khi sinh câu mới phải tính hoặc suy ra lại đáp án từ chính câu mới. Không so đáp án mới với đáp án nguồn trừ khi một bất biến đã quy định chúng phải bằng nhau. Trường hợp câu bóng đèn giữ nguyên mọi số lượng thì xác suất vẫn bằng 32/55, nhưng giá trị kP thay đổi theo k.

**Những kiểm tra cần làm ngoài JSON Schema**

Schema chặn thiếu trường, trường lạ, sai kiểu, mẫu số bằng 0, khối ảnh và số đáp án sai với định dạng một lựa chọn. Các điều kiện sau cần kiểm tra bổ sung:

1. Mọi `id` trong Requirement là duy nhất. ID trong `requirement_refs`, `evidence_refs`, `target_refs` và `refs` phải tồn tại, đúng loại và đúng phạm vi. ID của các rule cũng phải duy nhất.
2. `quantity_ref` phải trỏ tới đại lượng; `depends_on` phải trỏ tới bước suy luận và không tạo chu trình.
3. Mỗi bất biến có ít nhất một rule bắt buộc kiểm tra. Một rule có thể phục vụ nhiều bất biến.
4. Bảng có số ô mỗi hàng bằng số cột. `null` là ô thiếu, không phải số 0; dữ liệu thiếu ảnh hưởng đáp án phải được xử lý để có thể xác minh candidate.
5. Số phương án và số đáp án đúng khớp `response_spec`; khóa đáp án tồn tại. Câu không có phương án không được chứa khóa lựa chọn. Giá trị đáp án đúng kiểu của định dạng trả lời.
6. Kiểm tra ngôn ngữ mô tả, công thức, tính hợp lý của miền tham số, đơn vị, làm tròn và các mâu thuẫn giữa điều kiện.
7. Phát hiện cả hình nhúng trong Markdown/HTML/LaTeX và lời dẫn như “theo hình dưới”. Từ `requires_image: false` do AI khai báo chưa đủ chứng minh câu không cần hình.
8. Đối chiếu mô hình nội bộ với đề, phương án và lời giải của candidate thực tế. Phản hồi trên candidate được dùng để sửa blueprint và generator.
9. Mỗi lần chạy kiểm tra phải đối chiếu với đúng bản blueprint và candidate đã dùng. Khi blueprint hoặc generator thay đổi, sinh và kiểm tra lại candidate theo bản mới; kết quả cũ không tự áp dụng cho bản mới. Candidate chưa đạt vẫn được hiển thị cùng kết quả kiểm tra để chỉnh sửa, không tự động chấp nhận.

Hình học mô tả đầy đủ bằng chữ vẫn nằm trong phạm vi, như đa giác đều 12 cạnh. Câu yêu cầu đọc đồ thị, ảnh hiển vi, sơ đồ mạch hoặc cấu trúc hóa học ở dạng ảnh bị loại khỏi phạm vi này. Câu có hình minh họa đi kèm cũng không được đưa thẳng vào schema: phải có một phiên bản nguồn thuần văn bản đã được người dùng xác nhận là đầy đủ trước khi tạo blueprint. Bảng và công thức phải là dữ liệu thực, không phải ảnh chụp.

**Các bản mẫu dùng chung schema**

| Bản mẫu | Điểm được minh họa |
|---|---|
| [Toán — câu bóng đèn](examples/mathematics_partition_probability.json) | Chuyển câu đã thảo luận sang cấu trúc chung; xác suất tổ hợp; không cần trường riêng cho hình vuông. |
| [Vật lý — định luật II Newton](examples/physics_newton_acceleration.json) | Bảng dữ kiện, đại lượng có đơn vị, miền tham số và câu trả lời số. |
| [Hóa học — bảo toàn khối lượng](examples/chemistry_mass_conservation.json) | Câu nhận biết, không có đại lượng số; kiểm tra phạm vi định luật và tính duy nhất của đáp án. |
| [Sinh học — giải thích co nguyên sinh](examples/biology_osmosis_explanation.json) | Quan hệ nhân quả, không có tham số số; chấm bằng tiêu chí và chấp nhận diễn đạt tương đương. |

Ba câu Vật lý/Hóa học/Sinh học được soạn để minh họa cấu trúc. Phép tính của câu Toán và Vật lý đã được kiểm tra trong mô hình nêu ở đề. Phần bằng chứng của các mẫu Hóa học và Sinh học mô tả nội dung cần thẩm định chuyên môn khi đánh giá candidate. Các bản mẫu có thể tiếp tục được chỉnh sửa theo phản hồi.

Ví dụ câu bóng đèn được hỗ trợ là [bản Toán 0.4.0](examples/mathematics_partition_probability.json); các bản thiết kế riêng trước đó không thuộc bộ bàn giao hiện tại.

**Luồng sử dụng blueprint trong toàn project**

TASK-203 triển khai script nhận JSON câu nguồn và trả file JSON blueprint. Các bước sinh candidate, phản hồi và điều chỉnh generator bên dưới mô tả luồng sử dụng của toàn project, được người phụ trách phase generate tích hợp riêng theo tài liệu bàn giao.

1. Chuẩn hóa câu nguồn thành khối văn bản/công thức/bảng; kiểm tra ngôn ngữ, thiếu dữ kiện và phụ thuộc hình.
2. LLM tạo một blueprint ban đầu: phân tích mục tiêu, kiến thức, mô hình ngữ nghĩa, cách suy luận, bất biến, phạm vi biến đổi, cách chấm và các rule kiểm tra. Ghi rõ nguồn gốc của các giả thiết và kiến thức.
3. Kiểm tra cấu trúc và tham chiếu của blueprint, rồi đưa vào generator để sinh đúng một candidate gồm câu hỏi, đáp án và lời giải.
4. Kiểm tra candidate theo Constraint và hiển thị cho người dùng cùng câu nguồn, blueprint và kết quả kiểm tra. Kết quả chưa đạt hoặc chưa xác minh là dữ liệu cho vòng chỉnh sửa.
5. Người dùng nhận xét trên candidate. Sửa blueprint khi mục tiêu, bất biến, phạm vi biến đổi hoặc cách chấm chưa đúng ý định. Sửa generator khi cách dựng prompt, áp dụng blueprint, sinh phương án hoặc lời giải chưa đáp ứng yêu cầu. Có thể sửa cả hai trong cùng một vòng.
6. Dùng blueprint và generator đã sửa để sinh lại một candidate và đánh giá lại. Candidate cũ dùng làm căn cứ phản hồi; câu nguồn vẫn là đầu vào gốc cho việc xác định tính tương đương.
7. Lặp cho đến khi người dùng hài lòng với candidate và các kiểm tra cần thiết đạt. Blueprint vẫn có thể được sửa ở các vòng tiếp theo; một candidate đạt chưa chứng minh mọi biến thể sau đều đạt, nên từng câu sinh ra vẫn cần kiểm tra.

Phản hồi, candidate và cấu hình hoặc prompt của generator được quản lý trong luồng xử lý bên ngoài blueprint. Schema này lưu đặc tả sinh câu và điều kiện kiểm tra. Mỗi lần sinh thử cần lưu lại blueprint và cấu hình generator đã dùng cùng candidate, để phản hồi áp dụng đúng phiên bản. Luồng trên là thiết kế cần tích hợp, chưa phải chức năng đã triển khai trong backend.

Schema này là hợp đồng dữ liệu lưu trữ và kiểm tra của project. Khi tích hợp AI API, cần đối chiếu các từ khóa JSON Schema API hỗ trợ và tạo lớp chuyển đổi nếu cần. File hợp lệ về cấu trúc không đồng nghĩa có thể đưa nguyên schema vào mọi API.

Bản 0.3.0 đã loại bỏ `boundary_examples` và `open_issues`. Bản 0.4.0 tiếp tục bỏ `requirement.status`, `review_status` của kiến thức và giả thiết, `source_check.status` và các điều kiện phụ thuộc trạng thái. Bốn bản mẫu trong `examples` được cập nhật đồng bộ. Các lần kiểm tra trước trên bản 0.2.0 gồm xác thực schema, tình huống sai cấu trúc và lỗi liên trường; các kết quả đó là lịch sử kiểm tra của bản cũ. Phép tính Toán và Vật lý đã được kiểm tra độc lập. Đây là các tài liệu thiết kế, chưa phải bộ kiểm tra chạy trong backend và chưa chứng minh chất lượng sư phạm của các câu.

Nguồn tham khảo cho thiết kế: [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) và [điều kiện if/then/else](https://json-schema.org/understanding-json-schema/reference/conditionals) cho hợp đồng dữ liệu; [mô hình nhận thức trong sinh câu hỏi](https://onlinelibrary.wiley.com/doi/10.1002/9781118956588.ch6) cho việc mô tả kiến thức và thao tác đánh giá. Cách tổ chức trường cụ thể ở đây là đề xuất của project.

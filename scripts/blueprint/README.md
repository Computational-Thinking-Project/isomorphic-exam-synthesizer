> Lõi triển khai hiện ở `backend/app/services/blueprint`; script chỉ là entry point dùng chung. Build context Docker là gốc repo. Schema canonical nằm trong backend package, schema trong docs là reference tương thích. Xem `docs/ai-w2-halfway.md`.

# Script tạo blueprint — TASK-203

Nhận JSON một hoặc nhiều câu mẫu, gọi Gemini và ghi **một file JSON kết quả**. Điểm bàn giao cho generator là file này. Xem [hợp đồng input/output](../../docs/blueprints/GENERATOR_INTEGRATION.md) và [thiết kế blueprint](../../docs/blueprints/README.md).

## Chạy với Docker

Cần Docker và Compose, Linux engine đang hoạt động, cùng checkout repository đầy đủ. Chạy từ gốc repo; code/prompts/schema được mount từ checkout nên chỉ có image là chưa đủ.

Build và thử không gọi API, không cần key:

```text
docker compose -f docker-compose.blueprint.yml build --pull blueprint
docker compose -f docker-compose.blueprint.yml run --rm -T blueprint
docker compose -f docker-compose.blueprint.yml run --rm -T blueprint python /workspace/scripts/blueprint/create_blueprints.py --mode single --input /workspace/scripts/blueprint/tests/fixtures/single_input.json --output /workspace/outputs/mock-single.json --provider mock
```

Lệnh `run` không có command kiểm tra môi trường; lệnh mock kỳ vọng exit `0`, một item thành công. Mock chỉ replay bốn source khớp fixture; câu mới báo `MOCK_NO_FIXTURE`.

Để dùng Gemini, tạo `.env` ở gốc repo (cùng cấp Compose), đặt `GEMINI_API_KEY=your_actual_key`. `.env` được Git bỏ qua. Trong Compose dùng `GEMINI_API_KEY: ${GEMINI_API_KEY:-}`, không đặt key thật làm fallback. Compose đọc `.env` và truyền biến vào container; script Python chỉ đọc môi trường process. Biến shell cùng tên có thể ghi đè `.env`. Không commit key hoặc in toàn bộ cấu hình đã resolve để kiểm tra key.

Các lệnh sau gọi API thật, dùng quota và có thể tính phí:

```text
docker compose -f docker-compose.blueprint.yml run --rm -T blueprint python /workspace/scripts/blueprint/create_blueprints.py --mode single --input /workspace/scripts/blueprint/tests/fixtures/single_input.json --output /workspace/outputs/single-result.json
docker compose -f docker-compose.blueprint.yml run --rm -T blueprint python /workspace/scripts/blueprint/create_blueprints.py --mode batch --input /workspace/scripts/blueprint/tests/fixtures/batch_input.json --output /workspace/outputs/batch-result.json --concurrency 3
```

| Host | Container | Quyền/vai trò |
|---|---|---|
| `scripts/blueprint` | `/workspace/scripts/blueprint` | Read-only: code, prompts, contracts, fixtures. |
| `docs/blueprints` | `/workspace/docs/blueprints` | Read-only: schema, cấu hình mẫu. |
| `outputs/blueprint` | `/workspace/outputs` | Đọc/ghi: input mới và kết quả; được Git bỏ qua. |

Đặt `question.json` mới trong `outputs/blueprint`, truyền `--input /workspace/outputs/question.json`, chọn output khác input. Mọi đường dẫn CLI trong Docker là đường dẫn container. Dùng riêng Compose blueprint; không ghép Compose backend/frontend.

Nếu không nhận Docker server, kiểm tra `docker info` và khởi động engine. Trên Windows, hoàn tất WSL 2/restart nếu trình cài yêu cầu. Dùng `docker compose -f docker-compose.blueprint.yml config --quiet` để kiểm tra cấu hình mà không in key.

## Gọi trực tiếp bằng Python

Cần Python 3.11+ và dependencies trong `requirements.txt`; môi trường đã kiểm thử dùng Python 3.15.0. Caller nạp `GEMINI_API_KEY` vào môi trường subprocess, script không tự đọc `.env`.

```text
python -m pip install -r scripts/blueprint/requirements.txt
python scripts/blueprint/create_blueprints.py --mode single --input question.json --output result.json
python scripts/blueprint/create_blueprints.py --mode batch --input questions.json --output results.json
python scripts/blueprint/create_blueprints.py --mode single --input - --output result.json
```

Input UTF-8, tối đa **262144 byte cho cả document**. Single nhận `{"source": {...}, "context": {...}}`, batch nhận `{"questions": [item, ...]}`. Context tùy chọn; source thiếu đáp án/lời giải dùng `null`, không có phương án/tham chiếu dùng `[]`. Question ID phải bắt đầu bằng chữ và duy nhất trong batch. Xem [fixtures](tests/fixtures) và [hợp đồng chi tiết](../../docs/blueprints/GENERATOR_INTEGRATION.md).

Stdin nhận một JSON document đến EOF. Caller nên dùng `subprocess.run(..., input=json.dumps(payload, ensure_ascii=False), encoding="utf-8", shell=False)`; pipeline text của Windows PowerShell 5 có thể mặc định ASCII. Dùng đường dẫn tuyệt đối cho script/input/output nếu gọi từ working directory khác.

## Cấu hình

Mặc định provider `gemini`, model `gemini-3.5-flash-lite`. Ưu tiên: CLI → biến `BLUEPRINT_*` tương ứng → TOML chỉ định bằng `--config` → mặc định. Riêng model: `--model` → `BLUEPRINT_MODEL` → `GEMINI_MODEL` → TOML → mặc định.

| Thiết lập | CLI | Biến môi trường process | Mặc định / giới hạn |
|---|---|---|---|
| Provider | `--provider` | `BLUEPRINT_PROVIDER` | `gemini` hoặc `mock`. |
| Model | `--model` | `BLUEPRINT_MODEL`, `GEMINI_MODEL` | `gemini-3.5-flash-lite`. |
| Đồng thời | `--concurrency` | `BLUEPRINT_CONCURRENCY` | 3; số nguyên 1–32. |
| Timeout/request | `--request-timeout-seconds` | `BLUEPRINT_REQUEST_TIMEOUT_SECONDS` | 120 giây; số dương. |
| Timeout/câu | `--item-timeout-seconds` | `BLUEPRINT_ITEM_TIMEOUT_SECONDS` | 360 giây; gồm API/backoff/repair, không gồm chờ hàng đợi. |
| Budget request/câu | `--max-requests-per-item` | `BLUEPRINT_MAX_REQUESTS_PER_ITEM` | 3; số nguyên 1–3, gồm retry và repair. |
| Output token/request | `--max-output-tokens` | `BLUEPRINT_MAX_OUTPUT_TOKENS` | 16384; số nguyên 1–65536. |
| Schema | `--schema` | `BLUEPRINT_SCHEMA_PATH` | Schema `0.4.0` trong repo. |
| Prompts | `--prompt-directory` | `BLUEPRINT_PROMPT_DIRECTORY` | `backend/app/services/blueprint/prompts` (package dùng chung). |

Dùng [TOML mẫu](../../docs/blueprints/blueprint.config.example.toml) bằng `--config /workspace/docs/blueprints/blueprint.config.example.toml` trong Docker. Đường dẫn tài nguyên tương đối trong TOML resolve từ gốc repo/tool, không từ cwd của caller. Các trường `[output]` cố định: UTF-8, atomic write và `log_level="INFO"`; trường log hiện chỉ được loader kiểm tra, không bật progress log. Chưa có override sampling/thinking.

Compose đặt sẵn hai biến model nên chúng có ưu tiên cao hơn `[ai].model`; dùng `--model` để đổi cho một lần chạy. Các biến `BLUEPRINT_*` khác không tự đi từ host vào container: dùng CLI hoặc `docker compose run -e NAME=value`. Key chỉ đọc từ `GEMINI_API_KEY`, không nhận qua CLI/TOML, không fallback sang `GOOGLE_API_KEY`.

Python/dependencies lấy stable mới khi build môi trường; chạy extractor không tự nâng cấp package. Muốn nâng cấp toàn bộ, build với `--pull --no-cache` rồi chạy test. Snapshot phiên bản của image ở `/opt/blueprint/requirements-resolved.txt`. Khi gặp conflict, báo người phụ trách; không tự đổi model hoặc hạ dependencies để vượt lỗi.

## Kết quả và giới hạn

Output envelope `1.0.0` có `mode`, `results`, `summary`, `error`, `run_metadata`. Blueprint nằm tại `results[i].blueprint`; batch giữ thứ tự input và cô lập lỗi từng câu. Exit code: `0` tất cả thành công, `3` thành công một phần, `4` mọi item lỗi, `2` lỗi input/cấu hình toàn lần gọi, `1` lỗi nội bộ/I/O. Chi tiết và ví dụ lỗi ở [hợp đồng bàn giao](../../docs/blueprints/GENERATOR_INTEGRATION.md).

Ghi file UTF-8 nguyên tử qua file tạm. Stdout chỉ có JSON thông báo đường dẫn/summary; stderr có chẩn đoán an toàn. Caller cấp output path riêng từng lần và không nhận file cũ khi process thất bại hoặc bị ngắt.

Pipeline: đọc/snapshot source → dựng prompt và schema API → gọi AI → ghép các trường script sở hữu → validate schema đầy đủ/tham chiếu → repair trong budget → ghi kết quả. `config.py` quản lý cấu hình, `schema_adapter.py` tạo projection, `extractor.py` điều phối, `validators.py` kiểm tra và `common.py` ghi file. SDK đặt retry attempts=1; lỗi auth/model/cấu hình không retry, không tự fallback provider.

Schema gửi API chỉ chứa phần AI cần tạo; script tự ghép source, ID/version, các policy/hằng và hai danh sách `source_check.methods/evidence` rỗng. `computed_answer` là đề xuất AI. Mọi output thành công qua schema chuẩn và kiểm tra liên trường; ngôn ngữ/phụ thuộc hình là heuristic, so sánh cận decimal quá lớn được bỏ qua. Tính đúng chuyên môn và mức đẳng cấu vẫn cần rà soát.

Metadata ghi model yêu cầu/model API trả về, request, token quan sát được, lỗi validation và manifest adapter. Hash schema/source dùng JSON canonical UTF-8; prompt hash từ tên/nội dung file. Contracts dùng registry local, không fetch schema qua mạng. Artifact trong `outputs/blueprint` không có sẵn trong clone mới.

## Kiểm thử

Các lệnh offline không gọi Gemini:

```text
docker compose -f docker-compose.blueprint.yml run --rm -T blueprint python -m pytest /workspace/scripts/blueprint/tests -q -p no:cacheprovider
docker compose -f docker-compose.blueprint.yml run --rm -T blueprint ruff check --no-cache /workspace/scripts/blueprint
```

Test API một câu bật chủ động bằng lệnh sau, cần key và có thể tính phí:

```text
docker compose -f docker-compose.blueprint.yml run --rm -T -e BLUEPRINT_RUN_LIVE_TESTS=1 blueprint python -m pytest /workspace/scripts/blueprint/tests/test_live_api.py -q -p no:cacheprovider
```

Batch thử nghiệm đa môn: dùng `tests/fixtures/live_evaluation_input.json` làm input với mode batch, đối chiếu `live_evaluation_expectations.json`. Lần gọi có 12 câu, tối đa 36 request theo budget mặc định; JSON kết quả không tự tạo báo cáo đối chiếu đáp án.

Snapshot ngày 19/10/2026: **40 test offline đạt, 1 test API skip mặc định; Ruff đạt; API single 1/1 và batch 12/12 thành công**. Batch giữ nguồn/định dạng/ngôn ngữ kỳ vọng 12/12, chín đáp án số khớp kỳ vọng. Đây là smoke test trên tập nhỏ do người triển khai chuẩn bị, chưa có thẩm định giáo viên, thử lặp hoặc ablation; không đại diện cho mọi câu hay chất lượng sư phạm.

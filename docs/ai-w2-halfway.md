> Bản ghi tại mốc nửa đầu; phần AI còn lại đã được triển khai cục bộ. Xem [bàn giao hiện tại](ai-w2-integration.md) cho service, tests và các bước tích hợp còn thiếu.

# AI W2: phần đầu để review

Baseline: dev `c6b2290`. Phần này triển khai gateway async và tái sử dụng lõi
Blueprint của PR #9 trong backend. Chưa triển khai generator theo Blueprint,
routes xác nhận nguồn, persistence, SSE hoặc UI. Generator đồng bộ cũ vẫn giữ
để các caller hiện tại tiếp tục chạy; chưa chuyển nó sang gateway mới.

## Code cần xem

- `backend/app/services/ai/gateway.py`: một call là một attempt SDK; chọn ngẫu
  nhiên key sẵn sàng, cooldown 429, loại key lỗi 401/403, semaphore dùng chung
  tối đa 3, deadline/cancellation, budget hook và đóng clients.
- `backend/app/services/blueprint/`: lõi extractor/schema/prompts/contracts đã
  chuyển từ script sang backend. Không viết lại validators hoặc JSON repair.
- `backend/app/services/blueprint/service.py`: entry point cho nguồn đã xác
  nhận, kiểm fingerprint và snapshot trước khi chạy; trả kết quả từng câu.
- `scripts/blueprint/blueprint_tool/__init__.py`: lớp import tương thích, CLI
  gọi cùng module với backend. Không chứa implementation extractor thứ hai.

## Cách gọi từ orchestrator sau này

```python
import time

from app.core.config import settings
from app.services.ai.gateway import GeminiGateway, RequestBudget, RequestContext
from app.services.blueprint.service import BlueprintService

# Trong async lifespan của app: tạo một gateway, dùng chung giữa các jobs.
async with GeminiGateway(settings) as gateway:
    service = BlueprintService(gateway)
    budget = RequestBudget(250)
    context = RequestContext(time.monotonic() + 600, budget.reserve)
    results, metadata = await service.extract_confirmed(
        confirmed_items,
        confirmed_source_hash=hash_read_from_database,
        context=context,
    )
```

`confirmed_items` theo contract `source/context` của Blueprint, không phải
trực tiếp schema SourceQuestion legacy. BE adapter và profile Toán 4 options
sẽ làm ở phần tích hợp tiếp theo. Hash lưu khi giáo viên xác nhận được tính
bằng `source_fingerprint(items)`. Routes phải kiểm ownership và lấy hash từ DB;
không nhận hash do frontend tự gửi làm bằng chứng đã xác nhận.

`RequestBudget` chỉ bảo đảm nguyên tử trong một process/job. BE phải thay
`reserve_request` bằng thao tác DB nguyên tử dùng chung qua stages/retries
khi nối orchestrator. Không tạo budget mới cho từng câu hoặc mỗi lần retry.
Metadata extractor đếm attempts; budget hook đếm reservations trước transport.
Cancellation ngay sau reservation có thể vẫn tiêu một lượt dự phòng.

Gateway không tự retry nội dung. Extractor giữ budget tối đa 3 attempts/câu
gồm JSON repair và transient retry. Gateway đánh dấu auth error không retry;
những request sau bỏ key đó. Nếu cả pool cooldown thì chờ trong deadline,
không gửi request nóng liên tục. Model lấy từ settings, không tự fallback.

## Xem demo offline

Từ gốc repo, với dependencies đã cài:

```text
python scripts/blueprint/create_blueprints.py --mode single --provider mock --input scripts/blueprint/tests/fixtures/single_input.json --output outputs/blueprint/halfway-demo.json
```

Mock replay fixture đã có, không gọi Gemini và không chứng minh chất lượng
sinh đề bất kỳ. Output là Blueprint của một câu, chưa phải N mã đề.

## Docker và kiểm thử

Đạt tự cập nhật và tự merge phần Docker AI sau review theo rule nhóm.
Manifest/lock thêm jsonschema, referencing và dependencies cần thiết; giữ
nguyên các phiên bản cũ. Vì phiên này không có Docker, lock được sinh bằng
`uv pip compile` nhắm Python 3.11/Linux với constraints từ lock cũ; lệnh đầy đủ
nằm trong header lock. Docker build/test vẫn là bước nghiệm thu còn thiếu.

Schema runtime ở backend package. File schema cũ trong docs là `$ref` tới
schema canonical; CLI giữ hỗ trợ đường dẫn cũ qua alias local, không fetch mạng.
Standalone Compose đổi build context sang root để lấy shared core, có root
`.dockerignore` loại env/venv/node_modules. Backend image giữ context hiện tại.
CI đã bổ sung tests standalone và Docker job cho CLI dùng chung lõi.

```text
python -m pytest backend/tests scripts/blueprint/tests -q
python -m ruff check backend/app scripts/blueprint
python -m mypy backend/app --ignore-missing-imports
docker compose -f docker-compose.blueprint.yml build blueprint
docker compose -f docker-compose.blueprint.yml run --rm -T blueprint python -m pytest /workspace/scripts/blueprint/tests -q -p no:cacheprovider
```

Tests mới bao phủ rate limit, auth, quota/concurrency, deadline khi xếp hàng,
timeout/cancellation, đóng client, fingerprint nguồn và lỗi từng câu. Không
gọi API thật. Backend fixture tự nằm trong build context.

## Phần tiếp theo

Generator dùng Blueprint, sinh câu + đáp án + lời giải trong một request;
validation theo khả năng checker; giáo viên duyệt hoặc bấm sinh lại, không
nhập prompt. Sau đó nối routes/DB/SSE với BE. Đầu vào tổng quát không đồng nghĩa
code có thể chứng minh mọi lời giải đúng toán hoặc mọi candidate đẳng cấu.

## Kết quả tại checkpoint

- Regression backend + CLI: **268 passed, 1 live test skipped** (host Python 3.13).
- Sau đó bổ sung smoke test copy riêng backend app sang thư mục không có docs/scripts:
  service vẫn nạp đủ schema/contracts/prompts. Cả 6 tests service đạt.
- Ruff, Mypy (45 source files) và `pip check` đạt.
- Demo offline: `outputs/blueprint/halfway-demo.json`, 1/1 Blueprint thành công.
- Chưa chạy Docker hoặc Gemini thật; chưa commit, push hay merge.

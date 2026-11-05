# AI W2 — contract/fixtures bàn giao cho TASK-207

## Policy phối hợp đã xác nhận — 05/11/2026

[Duy xác nhận BE/API](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6646768276) và [Bội Anh xác nhận FE2](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6647147329), tiếp nối Quỳnh6635728977. Alias case-sensitive: NUMERICAL/parameter_variation→values, context_swap→context; chỉ selectable khi toàn bộ canonical batch ready và mọi Blueprint cho phép. STRUCTURAL/variable_inversion không công bố ở profile hiện tại; canonical IDs chỉ pass-through nếu public API công bố tường minh. Unknown/unsupported/mixed NONE phải ERR_CONFIG_CONFLICT, không đổi thành rỗng.

Public [] chủ đích là Original Clone; ["NONE"] chuẩn hóa thành [] trước validate/persist. Thiếu metadata không phải clone: is_ready=false/supported_modes=null khóa submit; ready=true/supported_modes=[] cho phép chọn clone. FE gửi hai ordering booleans tường minh. Quỳnh sở hữu worker clone zero Gemini/quota, giữ nguồn/options/key/lời giải nếu có, remap key khi shuffle và không chế lời giải/evidence. AI callable hiện có vẫn nhận canonical dimensions; [] trong callable không có nghĩa clone. Không đưa public aliases/NONE trực tiếp vào generator.

Policy đã chốt khác implementation đã đạt: worker/SQL/FE integration và PostgreSQL E2E còn chờ owners. Đạt cập nhật fixture AI, không viết trùng mapper/preflight/clone của Quỳnh. Snapshot persist riêng public IDs, resolved dimensions/mapping version, ordered source/hash/revisions/config/seed; canonical DB read RPC/ACL/migration vẫn do Duy/Hùng chốt. Mapping profile định danh trong fixture chỉ là tên bàn giao AI, chưa thay DB mapping-version authority.


## Checkpoint trước xác nhận policy (lịch sử)

[Quỳnh đã phản hồi và tiếp nhận bộ fixture](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6635728977): hash, seed, full QuestionResult và resume/cache đủ để chuẩn bị adapter. Quỳnh nhận nhánh clone riêng trong worker PR30, giữ nội dung/đáp án/lời giải, zero Gemini, remap đáp án khi shuffle và lưu record clone riêng. Đây là ownership được Quỳnh xác nhận; không còn chờ người nhận đường clone.

Quỳnh đồng ý hướng alias và chuẩn hóa NONE đã đề xuất; Duy và Bội Anh vẫn cần xác nhận API/UI trước khi coi policy chung đã chốt. Bảng/fixture public-mode tiếp tục proposed, không sửa generator hoặc triển khai public adapter ở PR41. Duy/Hùng còn chốt read snapshot/RPC, revision, ordered batch hash và full-result persistence; Quỳnh giữ preflight/worker/integration. Không coi tiếp nhận fixture là DB/SSE E2E đã đạt.

CI tại implementation41a6677 đã đạt5/5 checks. Chưa có independent review/Approve cho PR41. Đồng bộ dev chứa TASK301 đã merge chỉ cập nhật nền; checks cho head mới phải ghi riêng trong PR.


- Phụ trách: Trương Thành Đạt. Nguồn: [Duy yêu cầu tại PR30](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6629393300), input I-B-AI/I-B-POLICY; liên quan AI203/402.
- Workflow v0.1 proposed, docs baseline506384b. Nhánh `feat/dat-w2-ai-contract-handoff`, nền dev ac18e72.
- Authority AI: [ai-w2-integration.md](../ai-w2-integration.md); không tạo contract SQL/worker/FE thứ hai.

## Output và thứ tự

| Phần | Đầu ra | Kiểm |
|---|---|---|
| Hash/provenance | Thuật toán canonical và ordered batch/per-question/Blueprint/request/cache fingerprints, manifest cần persist | Fixture hai nguồn, đảo order, so hash thực tế |
| Resume/result | Full success/warning/hard-failure records và rule giữ evidence, slot seed, callback commit | Roundtrip thật và actual GenerationService với persisted completed |
| Guard seed | Từ chối persisted candidate.seed khác slot dù request fingerprint giữ nguyên | Regression trước dispatch/quota |
| Modes/clone | Policy public IDs/clone đã được BE/API và FE2 xác nhận; giữ nguyên generator | Fixture acceptance/rejection/readiness; worker/preflight do Quỳnh triển khai |
| Bàn giao | PR riêng của Đạt và phản hồi link commit/checks tại PR30 | CI/reviewer trước merge |

Không đổi generator architecture, SQL/RPC, worker orchestration, validator aggregator,
frontend, gateway instrumentation hoặc Docker dependencies. Bảo toàn file demo chưa track.

## Phối hợp còn mở

[Đề xuất đã đăng trước khi sửa public behavior](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6629611144):

- Quỳnh/Duy/FE2: triển khai và kiểm tra integration theo policy đã xác nhận ở đầu tài liệu; không còn chờ chốt alias/NONE/owner clone.
- STRUCTURAL/variable_inversion đã loại khỏi profile hiện tại; chỉ mở lại khi có định nghĩa và fixtures được owners xác nhận.
- Duy/Quỳnh/Hùng: map ordered batch snapshot/hash/provenance và full QuestionResult vào W2 storage; W3 per-question revisions không thay batch store.
- Tâm/Quỳnh: report aggregator khác AI checks; giữ adapter rõ nếu adopt, không tự chế confidence.
- Quỳnh: instrumentation observer tại shared gateway; Đạt review khi có patch. Không viết trùng collector.

Phần hash/resume và policy mode/clone đã đủ input để bàn giao. Implementation worker/SQL/FE và kiểm tra tích hợp vẫn thuộc owners tương ứng; không coi xác nhận policy là integration đã hoàn tất.

## Checks / tiến độ

Đã có code/docs/fixture và tests offline trên nhánh; kết quả exact commit, CI và PR
được ghi trong PR description và phản hồi PR30 sau khi thực thi. Không nhận fixture
provider là live Gemini, self-check là Approve, hay AI module là W2 E2E hoàn tất.

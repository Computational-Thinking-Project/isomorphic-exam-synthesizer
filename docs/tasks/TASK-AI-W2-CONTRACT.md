# AI W2 — contract/fixtures bàn giao cho TASK-207

## Cập nhật phối hợp 05/11/2026

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
| Modes/clone | Bảng mapping đề xuất và giới hạn canonical, giữ nguyên generator | Chặn unsupported IDs; chờ owner thống nhất public semantics |
| Bàn giao | PR riêng của Đạt và phản hồi link commit/checks tại PR30 | CI/reviewer trước merge |

Không đổi generator architecture, SQL/RPC, worker orchestration, validator aggregator,
frontend, gateway instrumentation hoặc Docker dependencies. Bảo toàn file demo chưa track.

## Phối hợp còn mở

[Đề xuất đã đăng trước khi sửa public behavior](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6629611144):

- Quỳnh/Duy/FE2: alias public IDs, NONE normalization, supported_modes và owner clone branch.
- STRUCTURAL/variable_inversion chưa có mapping an toàn; cần định nghĩa/fixtures hoặc loại khỏi profile.
- Duy/Quỳnh/Hùng: map ordered batch snapshot/hash/provenance và full QuestionResult vào W2 storage; W3 per-question revisions không thay batch store.
- Tâm/Quỳnh: report aggregator khác AI checks; giữ adapter rõ nếu adopt, không tự chế confidence.
- Quỳnh: instrumentation observer tại shared gateway; Đạt review khi có patch. Không viết trùng collector.

Phần hash/resume hiện có đủ input để bàn giao; phần mode/clone dependent vẫn proposed
đến khi owner phản hồi. Không tự đặt ETA của đồng đội hoặc coi im lặng là đồng ý.

## Checks / tiến độ

Đã có code/docs/fixture và tests offline trên nhánh; kết quả exact commit, CI và PR
được ghi trong PR description và phản hồi PR30 sau khi thực thi. Không nhận fixture
provider là live Gemini, self-check là Approve, hay AI module là W2 E2E hoàn tất.

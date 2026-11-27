# EXT-01 — Review & Targeted Regeneration

**M2 Implementation Plan · v1.2, hiệu chỉnh sau review ngày 26/11/2026 · proposed tại ranh giới liên task**

**Cập nhật author ngày 27/11/2026.** Draft PR #111 đã có bản triển khai G0/G1 tại `7144d33`. M0–M2 dùng checkpoint `49cd9b7`. M3–M5 và fixture M6 nằm trong diff sau checkpoint. Kết quả kiểm theo môi trường và các tiêu chí còn mở nằm ở [gói 08](docs/tasks/EXT-01/08-verification.md#evidence-20261127). Trạng thái consumer và G2–G4 nằm ở [gói 09](docs/tasks/EXT-01/09-inputs-handoff.md#handoff-20261127). Các bảng kế hoạch ngày 26/11 bên dưới giữ mốc dự kiến ban đầu.

## Bắt đầu từ đâu?

Bộ plan được tách từ bản đã commit `4618075` ngày 26/11/2026; giữ các cập nhật và link comment PR hiện có. Trạng thái remote/acknowledgement bên dưới được kế thừa từ bản đó, chưa kiểm lại GitHub trong lượt tách file. Đây là các gói của cùng EXT-01, không phải phân công thành viên hay PR mới. “Bắt đầu ngay” nghĩa đủ đầu vào để chuẩn bị/kiểm local; lịch code từ 27/11 vẫn giữ nguyên.

| Ưu tiên | Gói công việc | Làm ngay / dependency |
|---|---|---|
| P0 | [00 — Baseline](docs/tasks/EXT-01/00-baseline.md) | Kiểm working tree/head ngay; đồng bộ G0 trước UI |
| P0 | [01 — Reject API](docs/tasks/EXT-01/01-reject-api.md) | Bắt đầu Q01: DTO, canonical reasons và API tests |
| P0 | [02 — Durable reasons](docs/tasks/EXT-01/02-durable-reasons.md) | Soạn receipt/SQL local theo Q01; tích hợp API sau 01; deploy chờ G3 |
| P0 | [03 — Replay/recovery](docs/tasks/EXT-01/03-replay-recovery.md) | Helper/DTO/tests ngay; bind receipt sau 02 |
| P0 | [04 — AI feedback](docs/tasks/EXT-01/04-ai-feedback.md) | Mapping/prompt/retry tests ngay; receipt integration sau 02/03 |
| P1 | [05 — Review UI](docs/tasks/EXT-01/05-review-ui.md) | Sau G0 làm inline/navigation; nối reasons/recovery sau 01–04 |
| Chờ G2 | [06 — Mode/policy](docs/tasks/EXT-01/06-mode-policy.md) | Chuẩn bị fixture; chưa khóa guard/schema khi Q04 chưa xác nhận |
| Chờ G4 | [07 — Preview/Export provenance](docs/tasks/EXT-01/07-preview-export-provenance.md) | Chuẩn bị fixture R09; sửa/tích hợp theo quyền owner Q06 |
| Xuyên suốt | [08 — Kiểm thử/nghiệm thu](docs/tasks/EXT-01/08-verification.md) | Test từng gói; ma trận A01/A02 và DoD chỉ giữ tại đây |
| P0, xuyên suốt | [09 — Inputs/bàn giao](docs/tasks/EXT-01/09-inputs-handoff.md) | Full fixture, contract Q01–Q08, xác nhận input; nguồn trạng thái duy nhất |

**Thứ tự triển khai khuyến nghị:** kiểm 00 → 01 → 02 → 03 → 04; sau G0 có thể làm phần inline/navigation của 05 mà chưa chờ mode/provenance. 06 và 07 chỉ mở phần phụ thuộc khi gate đạt. 08 chạy cùng mỗi gói; 09 giao fixture/contract sớm. Đây là thứ tự công việc, không phải yêu cầu tạo agent hoặc giao thêm người.

**Ranh giới tích hợp:** 01–04 cùng tạo một đường reasons hoàn chỉnh. Không phát hành API nhận reasons nhưng bỏ qua ở DB/AI; không mở UI reasons trước backend tương thích. Các gói chia sẻ `service.py`, `repository.py`, `schemas.py` cần tích hợp tuần tự và kiểm diff, không coi chia file plan là tách được mọi thay đổi code.

Giữ một nơi sửa mỗi nội dung: thiết kế chi tiết ở gói tương ứng; quyết định/acknowledgement Q và I ở 09; tiêu chí/test ở 08; trạng thái tổng thể, scope và lịch ở file này. Số mục lịch sử được giữ và dẫn link xuyên file để finding cũ vẫn truy vết được.


<a id="section-0"></a>

## 0. Thông tin và trạng thái

| Mục | Giá trị |
|---|---|
| Dự án | Isomorphic Exam Synthesizer — Nhóm 04 |
| Nguồn giao việc | `Ke-hoach-phan-cong-EXT-v3.1-final.md`, EXT v3.1 ngày 25/11/2026, mục 1, 3, 4, 5 |
| Phụ trách | Duy — EXT-01 và điều phối M1 |
| Reviewer / dự phòng | Đề xuất `@nhatquynh1107` (DB/ACL), `@AI-WFox` (AI/policy), `@benalexx007` (FE); chưa phân công chính thức; dự phòng TBD |
| Repository | [isomorphic-exam-synthesizer](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer) |
| Base đã kiểm | `dev@efed79b1662f63d1bc083eb147dc55421684ea16` (đã đồng bộ `origin/dev@b29244346094811eaa038fd31fea67969f8f5b7f`) |
| Baseline UI tham chiếu | `fix/stage3-ui@1072d1ceee8e126640b2d03a10545f94cac70475` — [PR #109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109) (đã merge ngày 26/11; merge commit `b29244346094811eaa038fd31fea67969f8f5b7f`, khớp tree `1072d1c`) |
| Branch / PR dự kiến | `feat/ext-01-review` → `dev`; [Draft PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111); Integration HEAD local `57e900bb920bbef70a9aefe9de3f47c81c500be3` (push remote ở M6) |
| Workflow | [v0.1 proposed + INPUT-20261109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/7b7387f/docs/review/WORKFLOW.md); [M2 template trên baseline](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/TEMPLATES.md#m2) |
| Mốc đợt | M2/Draft PR 26/11; code từ 27/11; báo kết quả tối 01/12/2026 |
| ETA task | 29–45 giờ công trực tiếp, dự toán hiệu chỉnh chưa được Duy xác nhận; thời gian chờ input/review không nằm trong số này |
| Trạng thái | Draft PR #111 đã mở; G0 đã đồng bộ local tại `57e900b` (chờ push M6); G1 đủ thiết kế để bắt đầu; G2–G5 còn pending. Môi trường local chưa kiểm runtime product/DB/AI trong M0 |

> Kiểm chứng ngày 26/11/2026: PR #109 đã merge, merge commit `b29244346094811eaa038fd31fea67969f8f5b7f`; PR #111 vẫn Draft (đã đăng [comment chốt Q04–Q08](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7181001101), đang chờ owner phản hồi). Các ID `V/R` là finding kế hoạch, không phải implementation đã đạt; chưa chạy product/DB/AI tests cho EXT-01 mới.

<a id="section-0-1"></a>

### 0.1. Điều kiện bắt đầu và thứ tự mở khóa

Plan này dùng để triển khai phần EXT-01 đã rõ; không thay xác nhận của owner cho contract liên task. Các phương án Q04–Q08 chưa là quyết định được owner phê duyệt. Giữ filename v1.2 để không phá đường dẫn PR; revision nội dung nhận diện bằng commit khi bàn giao.

| Gate | Công việc và tiêu chí đủ | Phần được mở khóa | Trạng thái tại lần hiệu chỉnh |
|---|---|---|---|
| G0 — Baseline | Bảo toàn working tree; đưa plan và nguồn phân công vào gói review chia sẻ được hoặc dẫn nguồn đã được owner xác nhận; đồng bộ nhánh với `dev` chứa merge #109; ghi integration HEAD và diff | Thay đổi UI dựa trên #109 và kết luận regression theo head mới | Đạt đồng bộ local (`29f1378` split docs, merge `origin/dev@b2924434` tại `57e900b`, đã kiểm line-ref); push remote ở M6 |
| G1 — Nội bộ | Q01–Q03 theo [§3](docs/tasks/EXT-01/00-baseline.md#section-3), gồm thứ tự owner check trước service-role recovery; fixture/unit test local | API reasons, receipt/replay, recovery, inline UI/navigation độc lập | Đủ thiết kế để bắt đầu; implementation/tests chưa thực hiện |
| G2 — Mode/policy | Tâm xác nhận Q04: frozen mode, phân biệt legacy/new snapshot, slot policy, mã lỗi và projection UI; bổ sung vào contract chuẩn | Guard mode/clone và tích hợp targeted policy | Pending owner confirmation |
| G3 — DB rollout | Quỳnh và các owner xác nhận Q05: số migration thực tế, thứ tự dependency, signature/ACL, deployment window, rehearsal và phương án phục hồi | Chốt migration để tích hợp/deploy; không chặn soạn migration local tên tạm | Pending owner confirmation |
| G4 — Consumer | Q06–Q08 được xác nhận; I-EXT-01 có full fixture + revision, consumer xác nhận phạm vi đủ dùng | Tích hợp Preview/Export/Delete/readiness liên task | Pending; ví dụ ở [Phụ lục A](docs/tasks/EXT-01/09-inputs-handoff.md#appendix-a) chưa là fixture Delivered |
| G5 — Nghiệm thu | A01/A02 và checks áp dụng có evidence ở integration HEAD, reviewer độc lập, GitHub Approve/CI theo CONTRIBUTING | Ready/merge; deployment vẫn theo G3 | Chưa thực hiện |

Nếu G2–G4 chưa đạt: tiếp tục G1 với fixture có nhãn rõ, ghi blocker và ETA trên PR; không bật shuffle-only hoặc tuyên bố đã tích hợp các EXT. Không có quyền tự xác nhận thay owner hoặc tự đăng comment từ nội dung plan.

<a id="section-1"></a>

## 1. Mình cần làm gì?

<a id="section-1-1"></a>

### 1.1. Hành vi bắt buộc

- Hiển thị đáp án, lời giải và nút duyệt dưới từng câu; nếu thiếu lời giải, hiển thị “Chưa có lời giải”.
- Accept theo `candidate_id` hiện hành. Chỉ auto-advance sau accept thành công, đã đối soát server, và giáo viên vẫn ở đúng phiên/mã/câu, chưa tự điều hướng trong lúc chờ. Ưu tiên câu chưa duyệt trong cùng mã (kể cả câu đã bỏ qua), sau đó mã khác. Cho quay lại câu đã duyệt; không tự chuyển sang Preview.
- Reject nhận `reasons` tùy chọn, rỗng hoặc nhiều mã hợp lệ; chuẩn hóa tập lý do, lưu cùng operation, đưa vào targeted regeneration. Cùng key/tập reasons replay kết quả cũ; khác tập trả 409; receipt cũ thiếu reasons tương đương rỗng.
- Giữ blueprint, validator, quota, attempt permit, ownership, lock, current candidate và recovery hiện có. Candidate sinh lại phải được duyệt lại; revert theo điều kiện hợp lệ, bảo toàn đáp án/lời giải/provenance.
- Reload và lỗi phải đọc lại trạng thái server; có đường phục hồi operation hết hạn. Không dùng trạng thái optimistic làm nguồn sự thật.
- Preview chỉ mở khi toàn phiên đủ điều kiện theo server; phân biệt `reviewed` với `approved`.
- Bàn giao I-EXT-01 cho Tâm, Đạt, Quỳnh; chủ trì A01/A02, phối hợp A20; chốt F-019 trong M2.

<a id="section-1-2"></a>

### 1.2. Ngoài phạm vi

Không viết lại ReviewService, tạo ledger/queue/AI service/validator mới, lịch sử candidate dạng timeline, sửa câu hỏi thủ công, nhập prompt tự do, thống kê reasons, redesign Preview/Bank/Export, lưu vị trí xem trên DB hay thay framework quản lý state. EXT-02 sở hữu mode/reuse/shuffle; EXT-04 sở hữu Finalize/Bank/xóa draft; EXT-03 sở hữu Export/OMR. Chỉ sửa ranh giới cần thiết với các owner này.

<a id="section-6"></a>

## 6. Lịch, PR và công sức

| Ngày (2026) | Công việc | Output / gate |
|---|---|---|
| 26/11 | Đồng bộ #109, M2, chốt Q01–Q08, Draft PR #111 | Base/head, contract, migration slot, I-EXT-01 contract/fixture draft |
| 27/11 | API/DB/receipt | Canonical reasons, lookup/reserve, replay/failure unit + PG tests |
| 28/11 | AI feedback, recovery; UI phần độc lập nếu đủ input | Reasons qua retries; reconcile expired; contract test |
| 29/11 | Inline UI, navigation, snapshot/readiness | A01 component tests; no stale local override |
| 30/11 | Integration, revert/provenance, DB chain | A01/A02 evidence, I-EXT-01 giao bản có head |
| 01/12 | Regression, independent review, sửa blocker, báo cáo | M3/M5 theo tình hình, ghi Accepted/Integrated thực tế và phần còn chờ |

| Hạng mục | Giờ công ước lượng |
|---|---:|
| Baseline/M1/M2 | 3–4 |
| API/DB/receipt | 7–11 |
| AI feedback | 3–5 |
| Recovery | 3–5 |
| Inline UI | 3–4 |
| Navigation/snapshot | 4–7 |
| Kiểm thử/bàn giao | 6–9 |
| **Tổng** | **29–45** |

Đây là dự báo, không phải velocity đã đo. 26/11 là ngày plan, 27/11 mới bắt đầu code. Nếu 6 giờ/ngày trong 6 ngày thì có 36 giờ tổng công suất, không đủ kịch bản 45 giờ và chưa có buffer review/điều phối. Khoảng 29–45h là dự toán trước hiệu chỉnh, chưa cộng phần reader/classifier R09 và contract mode bổ sung; phải tái ước lượng sau G2/G4. Phần sửa của EXT-03/04 do owner tương ứng ước lượng, không mặc định nằm trong giờ Duy. Chốt khả năng thực tế với Duy; không biến hạn báo kết quả 01/12 thành cam kết tất cả EXT hoàn tất. Ưu tiên contract, durable correctness và A01/A02; báo sớm phần còn chờ, không cắt test an toàn.

<a id="section-6-1"></a>

### 6.1. Chiến lược PR

Mặc định một Draft PR `feat/ext-01-review` với commit plan trước, các commit code/test logic rõ ràng. Tối đa hai PR nếu review thực sự dễ hơn: A (API/DB/AI/recovery) và B (FE). Nếu chia, B phụ thuộc A và UI reasons chỉ mở khi backend/AI đã tích hợp. Không tách riêng PR AI sau khi API đã mở hành vi reasons chưa được sử dụng; không tạo integration PR nếu không có diff tích hợp cần review. Reviewer đề xuất theo chuyên môn, chưa giao chính thức; tối thiểu một GitHub Approve độc lập và CI đạt theo CONTRIBUTING; xử lý blocker trên đúng thread/head.

<a id="section-9"></a>

## 9. Bàn giao — cập nhật theo kết quả thật

- Lượt tách file & G0 local: đã commit 10 gói `docs/tasks/EXT-01/`, `EXT-01-Implementation-Plan-v1.2.md` và `Ke-hoach-phan-cong-EXT-v3.1-final.md` tại `29f1378`, merge `origin/dev` (`b2924434`, PR #109) vào `feat/ext-01-review` tại Integration HEAD `57e900b`, và đối chiếu lại line-ref Stage 3 / backend / migration; chưa push remote (push ở M6) và chưa thay đổi code sản phẩm.
- PR/commit/output: [Draft PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111) trên nhánh `feat/ext-01-review` (Integration HEAD local `57e900b` + commit cập nhật baseline `00-baseline.md`).
- Đã có trước lượt hiệu chỉnh: plan và Draft PR #111. Lượt 26/11 cập nhật gates G0–G5, Q01 body contract, Q03 authorization, Q04 frozen mode/policy, Q05 deployment/dependency/recovery, Q06 reader/classifier/provenance, ma trận A02-25–30, và đã đăng [comment chốt Q04–Q08](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7181001101) lên PR #111.
- Đã kiểm: code, metadata GitHub và đồng bộ G0 local (`b2924434` là ancestor của `HEAD`); chưa chạy bộ test ứng dụng hay DB/AI cho code EXT-01 mới.
- Đã chấp nhận: chưa có xác nhận M2 từ reviewer/consumer (`Q04–Q08`).
- Còn chờ: push cập nhật `feat/ext-01-review` ở M6, xác nhận của các owner cho `Q04–Q08` và thứ tự migration sau `027`.

<a id="section-10"></a>

## 10. Tài liệu tham chiếu

- EXT v3.1: [Ke-hoach-phan-cong-EXT-v3.1-final.md](Ke-hoach-phan-cong-EXT-v3.1-final.md) (file phân công cung cấp ngày 25/11/2026; đã tracked trong nhánh `feat/ext-01-review` tại `29f1378`).
- [AGENTS.md](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/AGENTS.md), [CONTRIBUTING.md](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/CONTRIBUTING.md), [WORKFLOW](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/WORKFLOW.md), [TEMPLATES — M2](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/review/TEMPLATES.md#m2).
- [Review RPC Contract](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/api/review-rpc-contract.md), [Review Snapshot Contract](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/api/review-snapshot.md), [Targeted Regeneration](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/ai-w3-targeted-regeneration.md).
- [PR #109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109), [ISSUE-95 plan](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/1072d1c/docs/tasks/ISSUE-95.md), [Compare dev...fix/stage3-ui](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/compare/efed79b...1072d1c).

**Giới hạn:** Plan dựa trên static inspection của commit đã ghim, không xác nhận schema đang deploy hay correctness runtime. Reason codes/Q01–Q03 là thiết kế nội bộ EXT-01 trong bản này; `Q04–Q08` và rollout cần owner liên quan xác nhận qua [Draft PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111).

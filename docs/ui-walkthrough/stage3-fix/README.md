# PR #109 — gói kiểm chứng C5

**Source Windows8a6f600:** targeted65/65, mutation bắt gate warning, lint/build đạt. Sau xác nhận user, full suite Windows chạy lại tại HEAD72adb9f đạt **621/621**,2suites,0fail/skip/cancel/108.27s/exit0; source không đổi. [Checkpoint6.25](../../tasks/ISSUE-95.md) và log workspace tmp/pr109-windows-r1-full-approved.log là bằng chứng mới thay lần chạy bị auto-review chặn trước. Full621Linux c7044d6 là evidence riêng. Cần native/reviewer QA và CI trên head Windows sau push.

**Lượt áp delta Windows25/11:** nội dung source R1 c7044d6 được áp lại trên parent c2b680a và docs a1b0ddb hợp nhất nội dung với plan Windows, không nhập nguyên object Linux hoặc overwrite docs local. [Checkpoint6.24](../../tasks/ISSUE-95.md) là trạng thái/checks Windows mới nhất; các dòng chưa nhập R1 bên dưới là lịch sử trước lượt này. Native/reviewer verification vẫn còn mở, không mặc định source author-fixed là đã resolved.

**Trạng thái checkout Windows25/11:** local/remote PR vẫn9f5a04d; hai object R1 c7044d6/docs a1b0ddb của lượt Linux chưa có trong repo Windows, chưa push. Kết quả targeted65/full621/lint/build thuộc lượt Linux, không thay proof cho Windows/PR hiện tại. [Checkpoint6.23](../../tasks/ISSUE-95.md) ghi việc cần nhập/đối chiếu bundle và giữ các docs Windows đang sửa. Tài liệu Windows này chưa nhận R1 Integrated/reviewer-verified hoặc native QA sau fix đã đạt.

**Cập nhật25/11 — Q01 đã đủ input:** [Duy7137928390](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#issuecomment-7137928390) chốt bỏ validation policy FE, giữ guard hiện hành và evidence/provenance BE; hard failure được xử lý trước persistence. [Plan6.21](../../tasks/ISSUE-95.md) nhận Accepted cho R1, thay trạng thái pending input bên dưới. R1 chưa triển khai/kiểm/reviewer xác minh; R2 vẫn cần native delta QA. Không nhận PR đã đủ merge từ việc input được cung cấp.

**Checkpoint lịch sử trước xác nhận manual QA, ngày24/11/2026:** author tự kiểm trên nhánh `fix/stage3-ui`. Khi đó C5 có kiểm tự động/checklist bàn giao, chưa hoàn tất native visual, chưa đề nghị Ready hoặc nhận GitHub Approve. Trạng thái mới ở đoạn kế tiếp.

**Cập nhật sau checkpoint trên:** Philip đã xác nhận manual test và duyệt bản854709d trong conversation; PR hiện Ready for review. [Duy Request changes](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#pullrequestreview-6038442931) còn F109-R1-03; [Tâm Commented](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/109#pullrequestreview-6040588696) đã kiểm6viewport/long content/native focus trên Chromium với API/auth mock, chưa Approve. Các dòng pending/checks bên dưới giữ nguyên như lịch sử trước xác nhận và không thay kết quả reviewer. [Plan sửa6.19](../../tasks/ISSUE-95.md) chia R1/R2/R3; chưa có code fix mới. Bản sửa tiếp theo cần kiểm lại delta trên head mới, không kế thừa visual pass854709d cho mọi thay đổi.

**Feedback UI mới cùng ngày, sau commit `787b338`:** user yêu cầu logo nhỏ hơn, bỏ metadata/legend/nhãn điều hướng phụ và bộ lọc trạng thái, tăng chiều cao panel và cho nở theo nội dung/cuộn trang. Các quy tắc cuộn/chiều cao mới bên dưới thay fixed-viewport của mốc C2; không thay contract backend. Bằng chứng 619tests/code `5e890f9` bên dưới là checkpoint trước feedback này; checks mới ghi tại mục6.18 của plan.

## Phiên bản và scope

- Task/plan: [Issue #95, mục 6.6 và 6.16](../../tasks/ISSUE-95.md). Workflow v0.1 + INPUT-20261109, trạng thái proposed theo [WORKFLOW](../../review/WORKFLOW.md).
- Mốc C5 trước feedback: base PR đọc từ GitHub `efed79b1662f63d1bc083eb147dc55421684ea16`, remote head lúc đó `1b661406006eda228eee6f804490a78e0e18afdf`, code kiểm `5e890f9ab43d15c55b994f1f1f634caaacb0d321`, docs `787b338`. Lượt feedback mới bắt đầu từ local/tracking `787b338`, không đọc lại head GitHub; khi yêu cầu review phải dùng head sau push.
- Tham chiếu: [walkthrough](../README.md), [PREVIEW.html](../PREVIEW.html), package `UI-WALKTHROUGH-20261102-TRANSPARENT-BRAND-HANDOFF-V2`. Đã kiểm lại SHA256 `8f9d6ebca4ad42b3ebddc15cf2fb4119b9599b8eb175c1b2c4d749b5f779dfaa`.
- PR sửa FE S06: nguồn trái/biến thể phải, tabs mã, modal inspection/confirmation, thứ tự câu trước/mã sau, lỗi/toast và guard API hiện hành. Không redesign S07/Export, đổi auth/router/service/backend hoặc tích hợp API mới.
- C4b retry ô thiếu và C4c partial-write là follow-up ngoài PR, không chờ PR #110 hoặc Gemini key mới. Bảng input/owner còn thiếu và ETA TBD giữ tại [mục 6.5/6.16 của plan](../../tasks/ISSUE-95.md); không tạo tracker hay tự gán owner khác.

## Checks checkpoint C5 trước feedback UI

Môi trường Windows, Node `v22.20.0`, npm `10.9.3`; lệnh dưới chạy từ `frontend/`. Tests component dùng DOM harness và services giả lập, không có browser layout engine hoặc API/DB thật.

| Kiểm | Lệnh / thao tác | Kết quả |
|---|---|---|
| Focus regression | Lọc hai ca C3 focus và C5 readonly link, lệnh bên dưới. | 2/2 pass trước mutation. |
| Mutation | Tạm đổi selector về chỉ `button`, chạy ca `C5:` rồi khôi phục source trong `finally`. | Test fail đúng assertion Tab từ nút đóng tới link; source đã phục hồi. |
| Full frontend | `node --test --test-concurrency=1` | 619/619 pass, 2 suites, 0 fail/skip/cancel; 165.19s. Bao gồm ca C5 và regression Review/service/Preview/Export. |
| Lint | `npm run lint` | Exit 0, không warning. |
| Build | `npm run build` | Exit 0, 55.22s; JS 1159.09kB, gzip336.50kB; còn cảnh báo chunk >500kB. |
| Tài liệu | `git diff --check` và kiểm liên kết tương đối thay đổi | Đạt trước commit evidence; không chạy lại product tests cho delta chỉ docs. |

```powershell
node --test --test-name-pattern='C5:|C3: focus' src/features/stage3-review/Stage3Review.test.js
```

Tests còn warning KaTeX quirks-mode của DOM giả, React Router future flags, MockTimers experimental và một số cập nhật Preview/MemoryRouter chưa bọc `act`. Không gọi suite là không warning; lint đạt ngưỡng 0 warning. Các cảnh báo này không được dùng làm bằng chứng browser đã chạy.

Raw logs local: `tmp/stage3-c5-focus-tests.log`, `tmp/stage3-c5-mutation.log`, `tmp/stage3-c5-full-tests.log`, `tmp/stage3-c5-lint.log`, `tmp/stage3-c5-build.log` tính từ workspace root. Không commit raw logs hoặc dữ liệu phiên.

## Kiểm lại sau feedback UI

Baseline `787b338` + delta header/notes/filter/page-scroll, cùng môi trường Windows/Node/npm bên trên. Scope và bốn thay đổi ở [plan6.18](../../tasks/ISSUE-95.md); code không đổi sau checks, các delta còn lại chỉ docs. Đây vẫn là DOM/service mock, không phải browser layout hoặc API thật.

- Focused: 8/8 pass, lệnh `node --test --test-name-pattern='R78-02:|UI109:|C2:' src/features/stage3-review/Stage3Review.test.js`.
- Mutation đảo điều kiện chọn câu bị ca legacy-storage bắt đúng lỗi nguồn câu2 thành câu1; đã restore trong `finally` trước checks cuối.
- Full `node --test --test-concurrency=1`: **620/620 pass**,2suites,0fail/skip/cancel/142.77s, gồm Review/service/Preview/Export. Lint exit0/0warning; build exit0/51.05s, JS1157.29kB/gzip335.87kB còn chunk warning. Tests còn warning DOM/Router/MockTimers/act như mốc trước.
- Logs: `tmp/stage3-ui109-focused.log`, `tmp/stage3-ui109-mutation.log`, `tmp/stage3-ui109-full-tests.log`, `tmp/stage3-ui109-lint.log`, `tmp/stage3-ui109-build.log` từ workspace root. Native QA sau sửa vẫn mở; ảnh user gửi là bản trước sửa.

## Finding và audit

**Lượt R2 sau review Tâm:** source fixes F01–F04 tại [plan6.20](../../tasks/ISSUE-95.md), commit `ebab331`/parent854709d, chỉ Page/CSS. Có khoảng cách nội dung biến thể, dot/counter cùng cụm, link inspection gạch chân và heading focus dùng màu theme. Checks R2 ghi dưới; native visual/focus trên bản sau sửa chưa kiểm, chưa reviewer-verified. F109-R1-03/Q01 vẫn open và validator/guard chưa đổi.

- Trên source `ebab331`: full `node --test --test-concurrency=1` **620/620 pass**,2suites,0fail/skip/cancel/118.23s; lint exit0/0warning; build exit0/32.30s, JS1157.37kB/gzip335.89kB còn chunk warning. Tests có warning DOM/Router/MockTimers/act. Delta sau checks chỉ docs. Logs `tmp/stage3-r2-full-tests.log`, `tmp/stage3-r2-lint.log`, `tmp/stage3-r2-build.log` từ workspace root.
- Cần kiểm lại375/320, desktop, plain/warning/long content, nhận diện link trước focus, heading keyboard focus/Tab/Shift+Tab/Escape/restore. Q02 cần ca40câu native; CSS hiện cuộn ngang, chưa có bằng chứng wrap. Không dùng review Chromium tại854709d làm kết quả mới cho R2.

**M5 dự thảo cho Philip sau push, chưa gửi:** F01–F04 đã sửa source trong commit `ebab331`, checks như trên, native/reviewer verification còn mở. F04 chọn outline theo theme và giữ keyboard visibility. F109-R1-03 chưa nhận fixed; nhờ làm rõ Q01 bằng contract/invariant BE hiện hành. Q02 giữ navigator đã được Philip duyệt theo6.18, chưa tái hiện wrap và cần case40câu để kết luận.

**F109-C5-01 — lỗi accessibility được đưa vào từ C3, đã sửa và tự kiểm.** Popup chỉ xem có một nút đóng, còn lời giải Markdown có thể có link. Trap chỉ liệt kê button nên Tab từ nút đóng bị vòng về chính nó, bỏ qua link; Shift+Tab cũng không tới link cuối. Selector mới bao gồm link và phần tử có tabindex không âm, vẫn loại nút disabled và heading tabindex -1. Test kiểm không chặn Tab ở nút đóng, wrap từ link cuối, Shift+Tab và Escape/restore focus. Đây là kiểm handler bằng DOM harness; native traversal vẫn nằm trong checklist dưới.

File chung ngoài feature: `frontend/src/test-support/domHarness.js` bổ sung selector nhóm đơn giản để test button/link theo thứ tự cây DOM. Không thay runtime sản phẩm hoặc thêm dependency. Full suite được chạy vì file hỗ trợ này dùng chung.

Self-review năm trục: correctness của boundary/focus và guard; readability của selector/test; architecture giữ logic trong inspection và test support; security không thêm HTML thô, quyền hoặc dữ liệu bí mật; performance chỉ query trong modal khi nhấn Tab. Không có finding code mới khác được xác nhận trong lượt này. Đây là author audit, không phải review độc lập hay approval.

## Checklist native browser còn mở

Phiên này không có công cụ kết nối browser để kiểm bản chạy. Không có screenshot trước/sau mới; DOM assertions, CSS source và build không được tính là visual pass. Có thể kiểm với fixture ghi rõ là mock hoặc phiên đã đăng nhập qua API hiện hành; không cần tạo Gemini key, bỏ auth hay nới `read_only` để nghiệm thu FE.

| Viewport / thao tác | Điều kiện đạt | Trạng thái |
|---|---|---|
| 1440×900, 1366×768, 1024×768 | Logo không giãn theo header; bỏ note/filter phụ; nguồn trái, một biến thể phải, tabs trong panel phải. Panel cao hơn và tự nở theo nội dung, cuộn trang để tới nội dung/CTA; palette/type/hierarchy theo walkthrough. | Chưa kiểm native sau sửa; ảnh user là bằng chứng finding trước sửa. |
| 768×1024, 375×812, 320×768 | Reflow dọc và cuộn trang; logo không tràn; đọc nguồn/biến thể và tabs/nav được; CTA không chồng nội dung; không cuộn ngang toàn trang. | Chưa kiểm native. |
| Zoom 200%, công thức/phương án/lời giải dài, nhiều câu/mã | Nội dung tăng chiều cao panel, không bị ép vào khung thấp; cuộn trang tới cuối và dùng được CTA. Modal vẫn có body cuộn riêng và actions truy cập được. | Chưa kiểm native. |
| Modal editable và chỉ xem có link Markdown | Focus vào heading; Tab/Shift+Tab qua đầy đủ controls/link; Escape/nút đóng/backdrop trả focus; busy chặn đóng và mutation khác. Confirmation không mở modal thứ hai. | Chưa kiểm native; có DOM regression. |
| Hai câu × hai mã | Đổi mã giữ nguồn; accept đúng candidate mới chọn Q1/M1 → Q1/M2 → Q2/M1 → Q2/M2; regenerate/revert cần duyệt lại, không tự qua S07. | Chưa kiểm native; có DOM regression. |
| Lỗi/toast, read-only, mất snapshot, conflict/lock | Toast không đẩy layout; lỗi còn truy cập khi toast ẩn; các guard và “Đọc lại trạng thái” hoạt động; ô thiếu ghi đúng retry cấp phiên. | Chưa kiểm native; có DOM/service regression. |
| S07/Export | Chỉ vào sau thao tác chủ động/đủ điều kiện; F5 không tự mutation; không đổi flow shuffle hoặc xuất file. | Chưa kiểm native/live; có automated regression. |

Khi bổ sung bằng chứng, ghi browser/version, code head, viewport/zoom, fixture hoặc API thật, kết quả từng hàng và ảnh nếu có. Không dùng ảnh walkthrough hoặc ảnh PR khác làm ảnh bản chạy hiện tại.

## Bàn giao review

- Output: implementation C2/C3/C4a, bản sửa F109-C5-01 và checks ở trên. Hai giới hạn API vẫn công khai: không targeted retry ô thiếu không ID; không duyệt cặp khỏe khi session đang read-only.
- PR hiện Ready với title/body cập nhật ở854709d; Philip đã xác nhận manual QA. Sau các fix mới phải cập nhật head/checks và trạng thái từng finding, không kế thừa manual pass cho delta chưa kiểm. Lượt sửa R2 chưa cập nhật metadata hoặc gửi comment lên GitHub.
- Duy đang Request changes F109-R1-03, Tâm Commented UI; chưa Approve. Q01 đã rõ theo Duy7137928390; cần native/reviewer kiểm lại delta và CI trên head sau push, ít nhất một thành viên khác GitHub Approve trước merge. Không đóng toàn Issue95 hoặc nhận live FE–BE–DB từ báo cáo này.

## M5 dự thảo cho bản Windows, chưa gửi

- F109-R1-03: source8a6f600 áp delta c7044d6 theo Q01; xóa reviewPairIssue/hasInvalidVariants và gate FE tự tính. Giữ BE warning/evidence, missing/read_only/busy/lock/identity/reconciliation/explicit approval. Author-fixed, chưa reviewer-verified/resolve.
- Windows targeted65/lint/build đạt, mutation bắt gate warning; full621/621 đạt sau user xác nhận chạy lại, source8a6f600/HEAD72adb9f. Evidence Windows tách khỏi full621Linux; native/CI/reviewer verification chưa hoàn tất.
- F01–F04 giữ sourceebab331; Q02 giữ navigator đã duyệt/CSS flex/overflow-x:auto. Native delta/40câu/zoom200% chưa có bằng chứng mới. Cần CI/reviewer kiểm đúng head sau push, không thêm API hoặc mở C4b/C4c.

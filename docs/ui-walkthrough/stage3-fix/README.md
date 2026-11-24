# PR #109 — gói kiểm chứng C5

Ngày 24/11/2026, author tự kiểm trên nhánh `fix/stage3-ui`. C5 đã có kiểm tự động và checklist bàn giao; **chưa hoàn tất nghiệm thu visual/native browser**, chưa đề nghị Ready hoặc nhận GitHub Approve.

## Phiên bản và scope

- Task/plan: [Issue #95, mục 6.6 và 6.16](../../tasks/ISSUE-95.md). Workflow v0.1 + INPUT-20261109, trạng thái proposed theo [WORKFLOW](../../review/WORKFLOW.md).
- Base PR đọc trực tiếp từ GitHub: `efed79b1662f63d1bc083eb147dc55421684ea16`. Remote head khi đọc: `1b661406006eda228eee6f804490a78e0e18afdf`; code cuối local `5e890f9ab43d15c55b994f1f1f634caaacb0d321` đã kiểm bên dưới, commit evidence sau đó chỉ sửa docs. Chưa push; khi yêu cầu review phải dùng head sau push.
- Tham chiếu: [walkthrough](../README.md), [PREVIEW.html](../PREVIEW.html), package `UI-WALKTHROUGH-20261102-TRANSPARENT-BRAND-HANDOFF-V2`. Đã kiểm lại SHA256 `8f9d6ebca4ad42b3ebddc15cf2fb4119b9599b8eb175c1b2c4d749b5f779dfaa`.
- PR sửa FE S06: nguồn trái/biến thể phải, tabs mã, modal inspection/confirmation, thứ tự câu trước/mã sau, lỗi/toast và guard API hiện hành. Không redesign S07/Export, đổi auth/router/service/backend hoặc tích hợp API mới.
- C4b retry ô thiếu và C4c partial-write là follow-up ngoài PR, không chờ PR #110 hoặc Gemini key mới. Bảng input/owner còn thiếu và ETA TBD giữ tại [mục 6.5/6.16 của plan](../../tasks/ISSUE-95.md); không tạo tracker hay tự gán owner khác.

## Checks thực tế

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

## Finding và audit

**F109-C5-01 — lỗi accessibility được đưa vào từ C3, đã sửa và tự kiểm.** Popup chỉ xem có một nút đóng, còn lời giải Markdown có thể có link. Trap chỉ liệt kê button nên Tab từ nút đóng bị vòng về chính nó, bỏ qua link; Shift+Tab cũng không tới link cuối. Selector mới bao gồm link và phần tử có tabindex không âm, vẫn loại nút disabled và heading tabindex -1. Test kiểm không chặn Tab ở nút đóng, wrap từ link cuối, Shift+Tab và Escape/restore focus. Đây là kiểm handler bằng DOM harness; native traversal vẫn nằm trong checklist dưới.

File chung ngoài feature: `frontend/src/test-support/domHarness.js` bổ sung selector nhóm đơn giản để test button/link theo thứ tự cây DOM. Không thay runtime sản phẩm hoặc thêm dependency. Full suite được chạy vì file hỗ trợ này dùng chung.

Self-review năm trục: correctness của boundary/focus và guard; readability của selector/test; architecture giữ logic trong inspection và test support; security không thêm HTML thô, quyền hoặc dữ liệu bí mật; performance chỉ query trong modal khi nhấn Tab. Không có finding code mới khác được xác nhận trong lượt này. Đây là author audit, không phải review độc lập hay approval.

## Checklist native browser còn mở

Phiên này không có công cụ kết nối browser để kiểm bản chạy. Không có screenshot trước/sau mới; DOM assertions, CSS source và build không được tính là visual pass. Có thể kiểm với fixture ghi rõ là mock hoặc phiên đã đăng nhập qua API hiện hành; không cần tạo Gemini key, bỏ auth hay nới `read_only` để nghiệm thu FE.

| Viewport / thao tác | Điều kiện đạt | Trạng thái |
|---|---|---|
| 1440×900, 1366×768, 1024×768 | Nguồn trái, một biến thể phải; tabs trong panel phải; palette/type/hierarchy theo walkthrough; vùng đọc cuộn riêng, header/nav/CTA truy cập được. | Chưa kiểm native. |
| 768×1024, 375×812, 320×768 | Reflow dọc; đọc nguồn/biến thể và tabs/nav được; CTA không mất hoặc chồng nội dung; không cuộn ngang toàn trang. | Chưa kiểm native. |
| Zoom 200%, công thức/phương án/lời giải dài, nhiều câu/mã | Nội dung không bị cắt mất, cuộn tới cuối; footer và modal actions dùng được. | Chưa kiểm native. |
| Modal editable và chỉ xem có link Markdown | Focus vào heading; Tab/Shift+Tab qua đầy đủ controls/link; Escape/nút đóng/backdrop trả focus; busy chặn đóng và mutation khác. Confirmation không mở modal thứ hai. | Chưa kiểm native; có DOM regression. |
| Hai câu × hai mã | Đổi mã giữ nguồn; accept đúng candidate mới chọn Q1/M1 → Q1/M2 → Q2/M1 → Q2/M2; regenerate/revert cần duyệt lại, không tự qua S07. | Chưa kiểm native; có DOM regression. |
| Lỗi/toast, read-only, mất snapshot, conflict/lock | Toast không đẩy layout; lỗi còn truy cập khi toast ẩn; các guard và “Đọc lại trạng thái” hoạt động; ô thiếu ghi đúng retry cấp phiên. | Chưa kiểm native; có DOM/service regression. |
| S07/Export | Chỉ vào sau thao tác chủ động/đủ điều kiện; F5 không tự mutation; không đổi flow shuffle hoặc xuất file. | Chưa kiểm native/live; có automated regression. |

Khi bổ sung bằng chứng, ghi browser/version, code head, viewport/zoom, fixture hoặc API thật, kết quả từng hàng và ảnh nếu có. Không dùng ảnh walkthrough hoặc ảnh PR khác làm ảnh bản chạy hiện tại.

## Bàn giao review

- Output: implementation C2/C3/C4a, bản sửa F109-C5-01 và checks ở trên. Hai giới hạn API vẫn công khai: không targeted retry ô thiếu không ID; không duyệt cặp khỏe khi session đang read-only.
- PR title đề xuất: `fix(stage3): align review workspace and inspection with walkthrough`.
- Mô tả GitHub hiện còn plan-only; sau push cần cập nhật scope/head/checks, link report này và giữ visual pending cho tới khi có kết quả. Lượt này chưa sửa metadata hoặc gửi comment lên GitHub.
- Reviewer chưa được phân công mới. Cần native QA còn mở, CI áp dụng trên head sau push và ít nhất một thành viên khác review/Approve theo CONTRIBUTING trước merge. Không đóng toàn Issue #95 hoặc nhận live FE–BE–DB từ báo cáo này.

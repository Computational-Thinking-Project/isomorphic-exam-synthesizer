# Issue #98 — Trung tâm trợ giúp và FAQ

- Nguồn giao việc: [Issue #98](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/98).
- Chế độ: Author. Reviewer và ETA chưa chốt.
- Nhánh: `feat/issue-98-help-center`. Base `origin/dev` tại `6131352e925f4e48b3f315afc7ceaa2cdd7311a9`. Người phụ trách tự mở PR vào `dev`.
- Workflow v0.1 proposed, INPUT-20261109, docs commit `7b7387f4c5034e7cf92f4591e80f8a9eb4452122`.

## Phạm vi và đầu vào

- `/help` công khai với hướng dẫn ba Stage, 10 FAQ, bảy nhóm lỗi và giới hạn AI. Lối vào ở Login và Thư viện đề. Nội dung tĩnh, độc lập với auth, dữ liệu phiên đề và Settings.
- Đầu vào nội dung đủ dùng cho bản này: hành vi nhập và xác nhận nguồn, cấu hình 1–4 mã, khôi phục và duyệt trên base; generation policy #70 qua PR #101; ZIP mỗi mã có một tài liệu cho từng định dạng theo [#92](ISSUE-92-PACKAGING.md). Hướng dẫn xáo trộn thứ tự câu hỏi chỉ xuất hiện tại Final Preview của Stage 3 theo quyết định của người phụ trách #98.
- Đầu vào UI: [walkthrough light](../ui-walkthrough/PREVIEW.html), `BrandLogo` và artwork thư viện hiện có. Khung 1.160 px, tiêu đề 30/40 px, tiêu đề mục 24/28 px, nội dung 16 px. Accent vàng trong mục lục và khối AI; thao tác trên trang là liên kết quay về, mục lục và mở câu hỏi FAQ.
- File phân công sau MVP, reviewer và ETA chưa có nguồn xác nhận. Không có input chờ làm thay đổi phạm vi triển khai.

## File và thứ tự triển khai

| Lượt / file | Input | Mục đích và đầu ra | Cách kiểm |
|---|---|---|---|
| `frontend/src/features/help/helpContent.js` | #98, code trên base và ZIP #92 | Soạn hướng dẫn ba Stage, FAQ, xử lý lỗi và giới hạn AI | Đủ 3/10/7 nhóm nội dung và đúng thuật ngữ trong sản phẩm |
| `frontend/src/features/help/HelpPage.jsx` | Nội dung và Paper Canvas | Dựng khung đọc desktop/mobile, mục lục, FAQ native và focus ở đích | Kiểm viewport đầu đến FAQ ở 1440 × 900/1000, thử anchor, FAQ, focus |
| `frontend/src/App.jsx` | Router và auth hiện có | Nối `/help` ngoài nhánh khởi tạo phiên và hồ sơ | Khách và người đã đăng nhập đọc được Help; route phiên đề vẫn được bảo vệ |
| `LoginPage.jsx`, `DashboardRoute.jsx` | Link công khai và link trong thư viện | Thêm hai lối vào, giữ đích quay về theo ngữ cảnh | Kiểm đi/về trên hai màn |
| `frontend/src/AppHelp.test.js`, `auth-loader.js` | Router, DOM harness và Supabase stub | Kiểm route, render, nội dung và điều hướng bằng fixture | Suite frontend và kiểm trình duyệt |

## Tự kiểm và bàn giao

- Windows, Node v24.22.1. Chạy trực tiếp các lệnh tương ứng với scripts frontend trong `frontend/`: `node node_modules/eslint/bin/eslint.js . --max-warnings 0` PASS, `node --test` PASS **570/570**, `node node_modules/vite/bin/vite.js build` PASS. Vite báo cảnh báo kích thước chunk JavaScript.
- Chromium với bản build local: 1440 × 1000, 1440 × 900, 1024 × 900, 768 × 900, 375 × 812 và 320 × 700 đều vừa chiều ngang. Viewport 1440 × 1000 hiện ba dòng FAQ đầy đủ và 1440 × 900 hiện một dòng đầy đủ. Đã kiểm palette, logo, link bỏ qua điều hướng, bốn anchor, reload với fragment, Tab/Shift+Tab, Enter/Space, Login → Help, quay lại Login và Back. Network của Help không có request fetch/XHR.
- Lối vào từ Thư viện đề và quay về với phiên đã đăng nhập được kiểm bằng fixture trong bộ test router. OAuth thật và deployment chưa được kiểm trong lượt này. Chưa có nghiệm thu độc lập.
- Gói M3 ghi base/head, diff và giới hạn kiểm. Người phụ trách tự push, mở PR và gửi yêu cầu review.

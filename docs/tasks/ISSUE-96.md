# Issue #96 — Cài đặt cá nhân

- **Nguồn giao việc:** [Issue #96](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/96), mục Sau MVP. Hạn và reviewer chưa xác nhận.
- **Phụ trách:** Quỳnh (`nhatquynh1107`). Nhánh `feat/issue-96-settings` từ `dev@6131352`. Chờ mở Draft PR vào `dev`.
- **Quy trình:** [WORKFLOW v0.1 proposed + INPUT-20261109](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/7b7387f/docs/review/WORKFLOW.md), revision `7b7387f`.

## Phạm vi

- Giáo viên đã đăng nhập mở `/settings` từ avatar trên Dashboard và xem tên, email, ngày tham gia. Tái sử dụng hồ sơ đã xác minh qua `GET /users/me` và trạng thái của `ProtectedRoute`. Avatar dùng metadata Google của đúng tài khoản hoặc chữ cái đại diện.
- Lưu tùy chọn từ 1 đến 4 theo tài khoản trên trình duyệt. Stage 2 ưu tiên cấu hình phiên đã lưu, rồi đến tùy chọn trong Settings, rồi mặc định 2. Giáo viên có thể vào thẳng Stage 2 và thay đổi số mã đề trong phiên.
- Dùng palette sáng của [UI walkthrough](../ui-walkthrough/PREVIEW.html). Nút chính dùng `accent`, ô đang chọn dùng `accent-soft` và liên kết dùng `highlight`. Route trợ giúp, chính sách dữ liệu và liên hệ chưa có trong app tại base đã kiểm.

## File và thứ tự triển khai

| Bước và file | Input | Mục đích và output | Cách kiểm |
|---|---|---|---|
| `features/settings/defaultVersionsPreference.js` | ID hồ sơ và quyết định lưu riêng từng tài khoản | Đọc/ghi số mặc định theo tài khoản. Storage thiếu, bị chặn hoặc dữ liệu sai trả về trạng thái an toàn. | Test 1–4, hai tài khoản và lỗi đọc/ghi. |
| `features/settings/SettingsPage.jsx`, `features/auth/UserAvatar.jsx` | Auth store, mockup và palette UI walkthrough | Hai thẻ hồ sơ và tùy chọn. Nút lưu báo kết quả. Tái sử dụng avatar và thêm kích cỡ lớn cho thẻ hồ sơ. | Test hồ sơ thiếu trường, avatar, lưu/lỗi/thử lại. Chrome desktop và mobile. |
| `App.jsx`, `features/dashboard/DashboardRoute.jsx` | I-96-NAV | Thêm route dưới `ProtectedRoute` và link vào/ra từ Dashboard. | Chrome kiểm khách, hồ sơ lỗi và hành trình Dashboard ↔ Settings. |
| `services/stage2Service.js`, `features/stage2-config/Stage2ConfigPage.jsx`, `Stage2ConfigCard.jsx` | I-96-STAGE2 và helper đọc tùy chọn | Phân biệt số thực sự đã lưu với giá trị chuẩn hóa cho tiến trình. Chọn giá trị khi khởi tạo form, giữ đường submit hiện tại. | Test ưu tiên phiên đã lưu, lưu riêng từng phiên, phiên khóa và chuyển session. Chrome kiểm 2 → 3 → mở phiên đã lưu 1, không phát sinh request ghi khi mở. |

Các đường dẫn code ở trên tính từ `frontend/src`.

## Đầu vào cần xác nhận trên Draft PR

| ID | Người cung cấp → người nhận | Mục đích và mức hiện tại | Phần còn thiếu |
|---|---|---|---|
| [I-96-NAV](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/96) | Owner route và Dashboard → Quỳnh | Đã kiểm cục bộ việc thêm route và link ở vùng tài khoản. | Xác nhận phạm vi sửa `App.jsx`, `DashboardRoute.jsx` và phần mở rộng kích cỡ `UserAvatar`. Owner/ETA `TBD`. |
| [I-96-STAGE2](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/94) | Bội Anh (`htbaax`) → Quỳnh | Đã kiểm phần khởi tạo số mã đề trên `dev@6131352`. | Chốt với owner #94 điểm ghép `initialNumVersions` và chạy lại kiểm khi Stage 2 redesign được tích hợp. ETA `TBD`. |

## Bàn giao

- **Đã kiểm:** Trên Windows với Node 24, frontend lint và build đạt, 566 test qua và `git diff --check` đạt. Vite báo cảnh báo kích thước bundle khi build.
- **Chrome với fixture:** Xác minh bảo vệ route, điều hướng, hồ sơ lỗi, Tab và phím mũi tên, màu nút `#F5CE58`, màu ô chọn `#FEF7DD`, tải lại sau lưu và thứ tự ưu tiên Stage 2. Có ảnh 1440 px và 375 px để đính kèm PR. Chưa kiểm Google OAuth/API thật.
- **Còn chờ:** Chủ nhánh push và mở Draft PR. Dẫn bảng input trên để xin xác nhận, đính kèm ảnh, theo dõi CI và phản hồi review trước khi merge.

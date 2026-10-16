# Nhật Ký Quyết Định Công Nghệ & Thay Đổi Kiến Trúc (Architecture & Tech Change Log)

> **Mục đích:** Tài liệu này dùng để lưu trữ các **quyết định kỹ thuật (Architecture Decision Records - ADR)**, các thay đổi công nghệ hoặc điều chỉnh quy trình phát triển phát sinh trong quá trình triển khai dự án so với tài liệu thiết kế ban đầu.  
> Khi dự án triển khai, mọi thay đổi về stack, quy ước code, cấu trúc thư mục hoặc luồng phối hợp giữa các thành viên đều cần được ghi chép tại đây để đảm bảo tính minh bạch và thống nhất cho toàn đội.

---

## 📋 Mục lục các Quyết định

*(Chưa có thay đổi phát sinh trong giai đoạn triển khai)*

---

## Chi tiết các Quyết định

*(Các quyết định kỹ thuật sẽ được cập nhật tại đây khi có thay đổi trong quá trình code)*
### DEC-TV1-001: Chuẩn bị Login UI và kiểm tra frontend

- Ngày/người thực hiện: 16/10/2026 — Trung Anh, TV1.
- Bối cảnh: TASK-101 cần màn đăng nhập; frontend có script lint nhưng chưa có công cụ và cấu hình ESLint.
- Quyết định: bổ sung ESLint cho JavaScript/JSX và React Hooks, lockfile, trang /login và router đầu vào.
- Phạm vi ảnh hưởng: frontend package/config, App.jsx và features/auth/LoginPage.jsx.
- Giới hạn: nút Google chỉ hiển thị thông báo; chưa kết nối Supabase hoặc xác thực người dùng.
- Kiểm tra: mở/bấm/reload trang login; npm run lint và npm run build thành công.

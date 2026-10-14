# Nhật Ký Quyết Định Công Nghệ & Thay Đổi Kiến Trúc (Architecture & Tech Change Log)

> **Mục đích:** Tài liệu này ghi nhận lại toàn bộ các **quyết định kỹ thuật (Architecture Decision Records - ADR)**, các thay đổi công nghệ hoặc điều chỉnh quy trình phát triển so với tài liệu thiết kế ban đầu (`planning.md`, `architecture.md`, `description.md`, `w1.md`).  
> Mọi thay đổi về stack, quy ước code, cấu trúc thư mục hoặc luồng phối hợp đều cần được ghi chép tại đây để đảm bảo tính minh bạch và thống nhất cho cả 7 thành viên trong nhóm.

---

## 📋 Mục lục các Quyết định

- [DEC-001: Chuyển đổi Frontend từ TypeScript sang JavaScript/JSX](#dec-001-chuyển-đổi-frontend-từ-typescript-sang-javascriptjsx)
- [DEC-002: Chuẩn hóa nhánh tích hợp duy nhất là `dev` (Loại bỏ `develop`)](#dec-002-chuẩn-hóa-nhánh-tích-hợp-duy-nhất-là-dev-loại-bỏ-develop)
- [DEC-003: Bổ sung cấu hình `.dockerignore` cho Frontend và Backend](#dec-003-bổ-sung-cấu-hình-dockerignore-cho-frontend-và-backend)
- [DEC-004: Tinh gọn quy trình quản lý: Chuyển từ GitHub Issues sang Pull Requests (Draft PR)](#dec-004-tinh-gọn-quy-trình-quản-lý-chuyển-từ-github-issues-sang-pull-requests-draft-pr)

---

## Chi tiết các Quyết định

### DEC-001: Chuyển đổi Frontend từ TypeScript sang JavaScript/JSX
* **Ngày quyết định:** 14/10/2026
* **Trạng thái:** Đã chấp thuận & Đã triển khai
* **Người đề xuất:** Nhóm Frontend (TV1, TV2) & thống nhất toàn đội

#### 1. Ngữ cảnh & Vấn đề ban đầu
Trong tài liệu ban đầu (`planning.md`, `w1.md`), Frontend được định hướng sử dụng **React 18 + Vite + TypeScript**. Tuy nhiên, trong tuần 1:
- Khối lượng công việc giao diện cần hoàn thành rất lớn: Tích hợp Google OAuth, Dashboard quản lý phiên, Component KaTeX toán phức tạp, Modal nhân bản đề.
- Việc ép kiểu dữ liệu ngặt nghèo của TypeScript (`interface`, generics Zustand/Axios, type check `tsc`) dễ tạo ra rào cản kỹ thuật, gây phát sinh lỗi compile chặn đứng CI và làm chậm tiến độ bàn giao của TV1, TV2.

#### 2. Quyết định mới
- Toàn bộ mã nguồn Frontend chuyển sang sử dụng **JavaScript / JSX thuần**:
  - File logic, API service, state store: dùng `.js`.
  - Component có chứa JSX: dùng `.jsx`.
  - Gỡ bỏ hoàn toàn `tsc`, `tsconfig.json`, `tsconfig.node.json` và devDependencies TypeScript.
- **Biện pháp bù đắp an toàn dữ liệu:** Giữ kỷ luật API Contract thông qua **Pydantic Schemas ở Backend** và các **JSON Fixtures mẫu** để Frontend JS kiểm tra đối chiếu dữ liệu.

#### 3. Các file bị ảnh hưởng
- `frontend/package.json`: Sửa script `"build": "vite build"`, gỡ `typescript` & `@types/*`.
- `frontend/vite.config.ts` $\to$ `frontend/vite.config.js`.
- `frontend/src/main.tsx` $\to$ `frontend/src/main.jsx`.
- `frontend/src/App.tsx` $\to$ `frontend/src/App.jsx`.
- `frontend/index.html`: Cập nhật thẻ script trỏ đến `/src/main.jsx`.
- `frontend/tsconfig.json`, `frontend/tsconfig.node.json`: Đã xóa.
- `.github/workflows/ci.yml`: Bỏ bước kiểm tra `npx tsc --noEmit`.

---

### DEC-002: Chuẩn hóa nhánh tích hợp duy nhất là `dev` (Loại bỏ `develop`)
* **Ngày quyết định:** 14/10/2026
* **Trạng thái:** Đã chấp thuận & Đã triển khai
* **Người đề xuất:** Nhóm trưởng & TV4 (DevOps)

#### 1. Ngữ cảnh & Vấn đề ban đầu
- Khởi tạo ban đầu của repository tạo nhánh tích hợp tên là `develop`.
- Bản kế hoạch điều chỉnh ngày 14/10 quy định tên nhánh tích hợp là `dev`.
- Việc tồn tại song song cả `dev` và `develop` sẽ gây phân mảnh: người mở PR vào `dev`, người mở vào `develop`, dẫn đến merge conflict và thất lạc code.

#### 2. Quyết định mới
- **Chỉ sử dụng duy nhất một nhánh tích hợp là `dev`**.
- Mọi nhánh tính năng (`feat/...`, `fix/...`, `chore/...`) bắt buộc rẽ nhánh từ `dev` và mở PR về `dev`.
- Nhánh `main` chỉ nhận code khi kết thúc giai đoạn release thông qua PR `dev` $\to$ `main`.
- Loại bỏ hoàn toàn nhánh `develop` khỏi cấu hình CI, tài liệu và repository.

#### 3. Các file bị ảnh hưởng
- `.github/workflows/ci.yml`: Chỉ lắng nghe `push` và `pull_request` trên `[main, dev]`.
- `CONTRIBUTING.md`: Cập nhật quy ước rẽ nhánh và hướng dẫn PR về `dev`.

---

### DEC-003: Bổ sung cấu hình `.dockerignore` cho Frontend và Backend
* **Ngày quyết định:** 14/10/2026
* **Trạng thái:** Đã chấp thuận & Đã triển khai
* **Người đề xuất:** TV6 (Docker Owner)

#### 1. Ngữ cảnh & Vấn đề ban đầu
Repo ban đầu chưa có file `.dockerignore` cho cả hai thư mục `frontend/` và `backend/`. Khi các thành viên chạy lệnh `npm install` hoặc tạo virtualenv Python ở máy local (Windows/macOS), lệnh `COPY . .` trong `Dockerfile` sẽ copy toàn bộ các file này vào image Linux của Docker, gây:
- Build Docker cực kỳ chậm do dung lượng context quá lớn.
- Xung đột nhị phân (binary architecture mismatch) giữa máy cá nhân và Linux container.

#### 2. Quyết định mới
- Tạo `frontend/.dockerignore`: Loại trừ `node_modules`, `dist`, `.env`, log files.
- Tạo `backend/.dockerignore`: Loại trừ `__pycache__`, `venv`, `.pytest_cache`, `.mypy_cache`, `.env`.

#### 3. Các file bị ảnh hưởng
- `frontend/.dockerignore`: Tạo mới.
- `backend/.dockerignore`: Tạo mới.

---

### DEC-004: Tinh gọn quy trình quản lý: Chuyển từ GitHub Issues sang Pull Requests (Draft PR)
* **Ngày quyết định:** 14/10/2026
* **Trạng thái:** Đã chấp thuận
* **Người đề xuất:** Toàn đội

#### 1. Ngữ cảnh & Vấn đề ban đầu
Tài liệu tuần 1 ban đầu có tiêu đề *"Kế Hoạch & Nội Dung Issues"* với dự định tạo 14+ GitHub Issues riêng lẻ. Đối với tiến độ nước rút 6 ngày của tuần 1, việc vừa cập nhật Issue vừa cập nhật PR tạo overhead hành chính không cần thiết.

#### 2. Quyết định mới
- Không tạo GitHub Issues độc lập.
- Mọi thảo luận kỹ thuật, cập nhật tiến độ, báo cáo blockers và bàn giao đều được thực hiện trực tiếp trên **Pull Request (sử dụng Draft PR ngay từ ngày 1)**.
- Gắn thẻ mã task (ví dụ `TASK-101`, `TASK-105`) trực tiếp vào tên branch, commit message và tiêu đề PR.

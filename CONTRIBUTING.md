# Hướng dẫn Đóng góp Dự án (Contribution Guidelines)

Nhằm đảm bảo tính nhất quán, an toàn bảo mật và chất lượng mã nguồn theo kế hoạch triển khai, mọi thành viên trong nhóm cần tuân thủ các quy tắc sau:

---

## 1. Quy ước Nhánh (Branching Strategy)
- **`main`**: Nhánh chính, luôn ở trạng thái production-ready và ổn định.
- **`dev`**: Nhánh tích hợp duy nhất của toàn đội trong tuần 1. Mọi nhánh tính năng đều rẽ nhánh từ `dev` và tạo Pull Request (PR) về `dev`.
- **Nhánh tính năng / sửa lỗi:**
  - Quy tắc đặt tên: `<type>/<task-id>-<short-description>`
  - Ví dụ:
    - `feat/task-101-auth-ui`
    - `feat/task-107b-sympy-evaluator`
    - `fix/task-207a-config-conflict`

---

## 2. Quy ước Commit (Conventional Commits)
Thông điệp commit phải tuân theo cấu trúc:
```text
<type>(<scope>): <mô tả ngắn bằng tiếng Anh hoặc tiếng Việt>
```

- **Types:**
  - `feat`: Tính năng mới (ví dụ: `feat(auth): integrate google oauth with supabase`)
  - `fix`: Sửa lỗi (ví dụ: `fix(parser): handle unescaped xml entities in docx`)
  - `test`: Thêm hoặc cập nhật test (ví dụ: `test(validator): add sympy latex smoke test`)
  - `refactor`: Tái cấu trúc mã nguồn không làm thay đổi hành vi
  - `chore`: Cập nhật cấu hình, dependency, CI/CD
  - `docs`: Cập nhật tài liệu

---

## 3. Quy trình Pull Request (PR)
1. Trước khi tạo PR, đảm bảo code đã pass các kiểm tra cục bộ:
   - Backend: `ruff check app` và `mypy app`
   - Frontend: `npm run lint` và `npm run build`
2. Tạo PR từ nhánh tính năng vào nhánh `dev`.
3. Bắt buộc vượt qua 100% kiểm tra của **GitHub Actions CI Pipeline** (`.github/workflows/ci.yml`).
4. Ít nhất 1 thành viên review và phê duyệt (Approve) trước khi merge.
5. Nếu PR có thay đổi công nghệ, cấu trúc thư mục hoặc hợp đồng dữ liệu so với thiết kế ban đầu, **bắt buộc phải cập nhật [docs/change_log.md](docs/change_log.md)** trong cùng PR.

---

## 4. Quy định Ghi nhận Thay đổi & Quyết định Kỹ thuật (Change Log)
Mọi thay đổi phát sinh trong quá trình triển khai làm lệch so với tài liệu thiết kế ban đầu (`planning.md`, `architecture.md`) đều phải được ghi lại tại **[docs/change_log.md](docs/change_log.md)** nhằm đảm bảo tính minh bạch và thống nhất:

- **Khi nào cần ghi:**
  - Thêm, bớt hoặc đổi thư viện / công nghệ cốt lõi.
  - Thay đổi cấu trúc thư mục, quy ước code hoặc quy trình Git/CI.
  - Thay đổi schema CSDL, hợp đồng API hoặc giao thức kết nối (ví dụ: SSE, REST).
  - Các quyết định kỹ thuật mới được nhóm thống nhất trong các buổi họp.
- **Cấu trúc mỗi mục ghi nhận (ADR format):**
  - **Mã & Tiêu đề:** `DEC-xxx: Tên quyết định`.
  - **Ngày & Người đề xuất:** Ngày ra quyết định và thành viên phụ trách.
  - **Ngữ cảnh & Vấn đề (Context):** Lý do vì sao cần thay đổi.
  - **Quyết định mới (Decision):** Nội dung thay đổi cụ thể và giải pháp bù đắp.
  - **Phạm vi ảnh hưởng (Impact):** Danh sách các file, module và thành viên bị ảnh hưởng.

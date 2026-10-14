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

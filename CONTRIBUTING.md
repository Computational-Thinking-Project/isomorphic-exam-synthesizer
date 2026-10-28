# Hướng dẫn Đóng góp Dự án (Contribution Guidelines)

Nhằm đảm bảo tính nhất quán, an toàn bảo mật và chất lượng mã nguồn theo kế hoạch triển khai, mọi thành viên trong nhóm cần tuân thủ các quy tắc sau:

---

## 1. Quy ước Nhánh (Branching Strategy)
- **`main`**: Nhánh chính, luôn ở trạng thái production-ready và ổn định.
- **`dev`**: Nhánh tích hợp của toàn đội. Mọi nhánh tính năng đều rẽ nhánh từ `dev` và tạo Pull Request (PR) về `dev`. PR `dev → main` dành cho mốc/giai đoạn đã được kiểm và chấp nhận.
- **Nhánh tính năng / sửa lỗi:**
  - Quy tắc đặt tên: `<type>/<task-id>-<short-description>`
  - Ví dụ:
    - `feat/task-101-auth-ui`
    - `feat/task-107b-sympy-evaluator`
    - `fix/task-207a-config-conflict`
  - Nhánh tài liệu có thể dùng `docs/<short-description>`, ví dụ `docs/update-workflow`.

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
1. Tạo **Draft PR trong thứ 5** từ nhánh task vào `dev`, có commit plan và link file phân công; dùng PR để giải đáp trước khi code từ thứ 6. Draft chỉ có tài liệu ghi đúng phần chưa code/chưa kiểm, không phải chờ có code mới mở PR.
2. Trước khi chuyển **Ready for review**, tự kiểm phù hợp với thay đổi và ghi lệnh/môi trường/kết quả/phần chưa kiểm:
   - Backend: lint/typecheck và tests liên quan theo [CI](.github/workflows/ci.yml) hoặc [Docker setup](docs/setup-docker.md). Từ root, CI dùng `ruff check backend/app scripts/blueprint`, `mypy backend/app --ignore-missing-imports` và các suite trong workflow.
   - Frontend: từ `frontend/`, `npm run lint`, `npm run build` và tests liên quan; cách chạy chung qua Docker theo hướng dẫn setup.
   - Chỉ tài liệu: kiểm link, Markdown, diff và tính nhất quán; không nhận đã chạy product tests nếu chưa chạy. Điều này không miễn CI trước merge.
3. Bắt buộc đạt các kiểm tra CI áp dụng trên bản cuối trước merge; giữ [CI Pipeline](.github/workflows/ci.yml) và [Docker environment](.github/workflows/docker-ci.yml) hiện hành. Không tự bỏ checks vì PR là docs hoặc sắp tới hạn tuần.
4. Ít nhất **1 thành viên khác** review và phê duyệt (GitHub Approve) trước merge; khai báo file chung/contract bị ảnh hưởng và phối hợp owner liên quan. Không tự đặt thêm yêu cầu chỉ leader duyệt hoặc hai approvals cho mọi PR.
5. Sửa trên cùng nhánh/PR, xử lý blocker/conflict và kiểm lại phần thay đổi sau review. Không merge Draft. Người có quyền repo merge khi đủ điều kiện; “agent đã xác minh” hoặc comment “OK” không thay GitHub Approve.
6. Nếu PR thay công nghệ, cấu trúc, hợp đồng dữ liệu **hoặc quy trình Git/review**, cập nhật [docs/change_log.md](docs/change_log.md) trong cùng PR, ghi đúng proposed/đã chấp nhận.

### Quy trình tuần và phối hợp agent

Đọc [WORKFLOW](docs/review/WORKFLOW.md) và lấy mẫu ở [TEMPLATES](docs/review/TEMPLATES.md); agent bắt đầu từ [AGENTS.md](AGENTS.md). WORKFLOW v0.1 đang ở trạng thái **proposed để review/pilot**, chưa là bằng chứng nhóm đã chạy thử. Nhịp tuần được Trung Anh xác nhận ngày 28/10/2026:

- Duy giao việc thứ 4 hoặc sáng thứ 5, dùng M1 để xếp thứ tự task theo phụ thuộc và ETA giao input đủ sớm cho task sau.
- Thành viên đọc/lập plan và tạo Draft PR trong thứ 5, giải đáp scope/input/ETA trên Conversation; bắt đầu code từ thứ 6.
- Hạn đợt là tối thứ 3 tuần sau, chưa chốt giờ cụ thể. Không bỏ review/checks để chạy hạn.

M1/M2 nằm trong file tuần/task; M3 ở PR body hoặc comment tổng hợp có link; M4/M5 ở cùng review thread/ID. PR template mới không tự cập nhật PR đang mở. Không bắt tạo Issue: dùng task/link thật, chỉ dùng `Closes #...` khi có Issue thật liên quan.

Khi thử quy trình, hai owner phải nhận cùng bản docs và yêu cầu agent đọc lại, xác định task/head/scope/quyền. Chọn PR/owner pilot trước khi chạy; các đề xuất giới hạn vòng sửa trong WORKFLOW chưa tự thành luật bắt buộc. Bộ Markdown không cài messenger, đánh thức agent hoặc cấp quyền đăng/push/merge.

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

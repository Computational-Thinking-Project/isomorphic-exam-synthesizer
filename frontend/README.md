# Frontend — thiết lập local và checkpoint Auth

Frontend sản phẩm dùng React/Vite và JavaScript/JSX. Đây là hướng dẫn cho repo sản phẩm; bộ `ui-draft` trong workspace là tài liệu thiết kế riêng.

## Chạy bằng Docker của nhóm

Giữ Docker Desktop chạy Linux containers. Tại thư mục gốc repo, chạy lần lượt:

```powershell
.\scripts\dev.ps1 setup
# Điền hai biến public VITE_* trong .env gốc trước khi chạy up.
.\scripts\dev.ps1 doctor
.\scripts\dev.ps1 up
```

`setup` chỉ tạo `.env` từ mẫu nếu file chưa có. Docker dùng **`.env` ở gốc repo** để nhận `VITE_SUPABASE_URL` và `VITE_SUPABASE_PUBLISHABLE_KEY`; không tự lấy hai giá trị từ `frontend/.env.local`. Dùng cấu hình Supabase/Google hiện có, không tạo lại project/provider. Không đưa secret vào `VITE_*`.

Mở `http://localhost:3000/login` và `http://localhost:8000/docs`. Giữ terminal `up` mở để theo dõi thay đổi source. Không chạy frontend/backend trực tiếp cùng cổng trong lúc dùng Docker.

Mở terminal khác tại gốc repo để kiểm:

```powershell
.\scripts\dev.ps1 test
```

Khi dừng, Ctrl+C chỉ dừng theo dõi source; chạy `.\scripts\dev.ps1 down` để dừng các container. Sau khi sửa env, chạy lại `up`. Xem [hướng dẫn Docker](../docs/setup-docker.md) cho đổi cổng và xử lý lỗi.

## Chạy trực tiếp bằng Node.js

Cần Node.js/npm đã cài. Lượt kiểm trực tiếp ngày 19/10/2026 dùng Node.js 22.20.0; checkpoint Docker mới ở mục Kiểm tra bên dưới.

Tại thư mục `frontend`:

```powershell
npm.cmd ci
if (-not (Test-Path -LiteralPath .env.local)) {
    Copy-Item -LiteralPath .env.example -Destination .env.local
}
```

Chỉ sao chép mẫu khi **chưa có** `.env.local`; giữ file cấu hình đã chuẩn bị nếu nó tồn tại. Điền hai biến sau bằng cấu hình public của Supabase project dùng chung:

```dotenv
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_replace_me
```

`.env.local` được Git ignore. Frontend chỉ dùng publishable key; Google client secret và Supabase service-role/secret key không thuộc frontend. Khi chạy trực tiếp tại `frontend`, dùng `.env.local`; khi chạy bằng Docker, dùng `.env` gốc theo mục trên.

```powershell
npm.cmd run dev
```

Mở `http://localhost:3000/login`. Nếu Vite chuyển sang 3001, dùng đúng URL được terminal thông báo. Khởi động lại Vite sau khi sửa env.

## Redirect và cấu hình nhóm đã chuẩn bị

- Dùng Supabase project/provider Google hiện có, không tạo lại chỉ để chạy frontend.
- Nút Google dùng `redirectTo = window.location.origin + '/login'`. Supabase Redirect URLs cần cho phép origin/cổng local tương ứng; checkpoint nhóm đã chuẩn bị `http://localhost:3000/login` và `http://localhost:3001/login`.
- Callback cấu hình bên Google là `<SUPABASE_PROJECT_URL>/auth/v1/callback`; `/login` là đích quay về frontend sau đó.
- `/api` được Vite proxy tới `API_PROXY_TARGET`, mặc định `http://localhost:8000` khi chạy trực tiếp và được cấu hình `http://backend:8000` trong Docker. Các luồng backend/profile vẫn cần tích hợp sau review; chạy được Vite không chứng minh API nghiệp vụ đã tích hợp.
- Cấu hình Docker của Tâm đã được đồng bộ vào nhánh Auth. Compose dev truyền hai biến public vào Vite; bản static dùng build args. Sau đổi env cần chạy lại `up` để áp dụng.

## Trạng thái Auth hiện tại

| Trạng thái | Hành vi |
|---|---|
| `checking` | Chưa xác minh được phiên; chặn trang nội bộ. Nếu kiểm phiên lỗi tạm thời/chưa xác định, có thông báo và nút Thử lại. |
| `unauthenticated` | Có thể bắt đầu đăng nhập Google. |
| `profile_pending` | Đã nhận phiên Supabase nhưng **chưa xác nhận profile ứng dụng**; vẫn chặn Dashboard, cho đăng xuất. |
| `reauth_required` | Phiên hiện tại bị chặn; cho đăng xuất phiên cũ rồi đăng nhập lại. Request mới và kết quả của request cũ không được tiếp tục dùng phiên này. |

Bootstrap dùng `getSession` và một auth subscription; sự kiện mới/version mới có ưu tiên hơn kết quả bootstrap trả về muộn. `SIGNED_OUT` xóa trạng thái user/session và thông báo trung tính rằng phiên đã kết thúc, không tự đoán nguyên nhân. Đăng xuất từ UI dùng scope `local`.

Các module dùng chung:

- [supabase.js](src/services/supabase.js): một Supabase client qua `getSupabase()`.
- [authStore.js](src/features/auth/authStore.js): trạng thái phiên/profile và version của lượt đăng nhập.
- [api.js](src/services/api.js): Axios client cho API sản phẩm, lấy token hiện tại, 401 refresh/retry tối đa một lần, 403 giữ nguyên lỗi. Lỗi tạm không tự yêu cầu đăng nhập lại; lỗi không còn phiên được xử lý khi scope/token vẫn hiện hành. Không gọi signOut từ interceptor.
- [authErrors.js](src/services/authErrors.js) và [authRefresh.js](src/services/authRefresh.js): phân loại lỗi Auth và chia sẻ refresh promise đồng thời.

Việc kiểm phiên trong frontend không thay backend JWT validation/RLS/ownership. Không dùng publishable key làm Bearer access token hoặc ghi token/session thật vào log để kiểm.

## Kiểm tra

Tại `frontend`, chạy lần lượt:

```powershell
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

Unit tests dùng source thật và Auth/HTTP giả lập, không cần key/env hoặc gọi Supabase thật. Mốc local 19/10/2026 đạt 37 unit tests, lint/build và 20 ca UI bootstrap bằng fixture có điều khiển: retry, lỗi tạm/hết phiên, StrictMode/cleanup, kết quả đến muộn và protected route. 20 ca UI là lượt kiểm browser riêng, **không** nằm trong `npm run test` và không chứng minh expiry/OAuth/backend thật. Workflow Docker mới chạy `scripts/dev.ps1 test`, gồm frontend test/lint/build; không tự chạy 20 ca browser hoặc OAuth thật. Chưa có kết quả CI cho nhánh Auth sau lần đồng bộ này.

**Checkpoint Docker do tác giả kiểm ngày 21/10/2026**, tại merge commit `225c3db` (nhận dev `c583f4a`): setup/doctor/up đạt, mở được frontend/backend docs; đã báo hoàn thành kiểm Google quay về login, reload giữ phiên, chặn Dashboard khi profile_pending và đăng xuất. Lệnh `scripts/dev.ps1 test` đạt: backend **70 passed, 1 warning**; SymPy parser và frontend test/lint/build đều đạt theo kết quả tác giả cung cấp, chưa ghi số test frontend của lượt này. Cảnh báo StarletteDeprecationWarning đề nghị chuyển TestClient từ httpx sang httpx2; chưa đổi dependency/lockfile backend trong task Auth. Agent không trực tiếp chạy lại bộ kiểm Docker này.

Kiểm thủ công với tài khoản được phép: Google quay về `/login`, reload nhận lại phiên, vẫn chờ profile, đăng xuất và đăng nhập lại.

## Phần đang chờ tích hợp/review

- **Profile: chờ PR của Duy, TV1 review trước khi ghép.** Chưa chốt fallback khi thiếu profile, chưa nối tên/ảnh/navbar hoặc mở Dashboard từ profile thật.
- Dashboard danh sách phiên/API list/clone, Clone Modal của Bội Anh và điều hướng theo dữ liệu thật chưa được tích hợp trong nhánh Auth này.
- Chưa nghiệm thu quyền dữ liệu thật với tài khoản A/B, expiry thật hoặc profile/session API. Docker startup và Auth có checkpoint tác giả kiểm ở trên; chưa kiểm bản static Nginx, CI của tổ hợp Auth mới hoặc nghiệm thu tích hợp toàn bộ.

Đây là checkpoint phần frontend độc lập; **TASK-101/103 chưa được coi hoàn tất**. Không dùng mock profile để bỏ qua phần tích hợp đang chờ.

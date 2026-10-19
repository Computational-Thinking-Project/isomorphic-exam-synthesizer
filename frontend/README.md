# Frontend — thiết lập local và checkpoint Auth

Frontend sản phẩm dùng React/Vite và JavaScript/JSX. Đây là hướng dẫn cho repo sản phẩm; bộ `ui-draft` trong workspace là tài liệu thiết kế riêng.

## Chạy local

Cần Node.js/npm đã cài. Lượt kiểm ngày 19/10/2026 dùng Node.js 22.20.0; chưa kiểm lại nhánh này trên Docker/CI.

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

`.env.local` được Git ignore. Frontend chỉ dùng publishable key; Google client secret và Supabase service-role/secret key không thuộc frontend. Root `.env` cho backend không tự thay thế cấu hình Vite này.

```powershell
npm.cmd run dev
```

Mở `http://localhost:3000/login`. Nếu Vite chuyển sang 3001, dùng đúng URL được terminal thông báo. Khởi động lại Vite sau khi sửa env.

## Redirect và cấu hình nhóm đã chuẩn bị

- Dùng Supabase project/provider Google hiện có, không tạo lại chỉ để chạy frontend.
- Nút Google dùng `redirectTo = window.location.origin + '/login'`. Supabase Redirect URLs cần cho phép origin/cổng local tương ứng; checkpoint nhóm đã chuẩn bị `http://localhost:3000/login` và `http://localhost:3001/login`.
- Callback cấu hình bên Google là `<SUPABASE_PROJECT_URL>/auth/v1/callback`; `/login` là đích quay về frontend sau đó.
- `/api` được Vite proxy tới `http://localhost:8000`. Các luồng backend/profile vẫn cần đầu vào được Duy xác nhận; chạy được Vite không chứng minh API backend đã tích hợp.
- Docker/env build do Tâm phụ trách. `VITE_*` được Vite đọc lúc dev/build; không suy việc đặt biến backend vào container là frontend tự nhận. Hướng dẫn local này chưa xác nhận Docker đã nạp đúng env.

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

Unit tests dùng source thật và Auth/HTTP giả lập, không cần key/env hoặc gọi Supabase thật. Mốc local 19/10/2026 đạt 37 unit tests, lint/build và 20 ca UI bootstrap bằng fixture có điều khiển: retry, lỗi tạm/hết phiên, StrictMode/cleanup, kết quả đến muộn và protected route. 20 ca UI là lượt kiểm browser riêng, **không** nằm trong `npm run test` và không chứng minh expiry/OAuth/backend thật. Workflow CI hiện chỉ build frontend, chưa tự chạy bộ 37 tests hoặc 20 ca browser này.

Kiểm thủ công với tài khoản được phép: Google quay về `/login`, reload nhận lại phiên, vẫn chờ profile, đăng xuất và đăng nhập lại.

## Phần đang chờ tích hợp/review

- **Profile: chờ PR của Duy, TV1 review trước khi ghép.** Chưa chốt fallback khi thiếu profile, chưa nối tên/ảnh/navbar hoặc mở Dashboard từ profile thật.
- Dashboard danh sách phiên/API list/clone, Clone Modal của Bội Anh và điều hướng theo dữ liệu thật chưa được tích hợp trong nhánh Auth này.
- Chưa nghiệm thu quyền dữ liệu thật với tài khoản A/B, expiry thật hoặc Docker/env. Phiên Google đã có checkpoint user tự kiểm trước đó; lượt QA mô phỏng mới không thay checkpoint cloud đó.

Đây là checkpoint phần frontend độc lập; **TASK-101/103 chưa được coi hoàn tất**. Không dùng mock profile để bỏ qua phần tích hợp đang chờ.

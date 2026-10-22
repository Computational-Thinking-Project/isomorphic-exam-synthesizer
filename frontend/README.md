# Frontend — thiết lập local và checkpoint Auth

Frontend sản phẩm dùng React/Vite và JavaScript/JSX. Đây là hướng dẫn cho repo sản phẩm; bộ `ui-draft` trong workspace là tài liệu thiết kế riêng.

## Chạy bằng Docker của nhóm

Giữ Docker Desktop chạy Linux containers. Tại thư mục gốc repo, chạy lần lượt:

```powershell
.\scripts\dev.ps1 setup
# Điền cấu hình public frontend và backend trong .env gốc theo bảng bên dưới.
.\scripts\dev.ps1 doctor
.\scripts\dev.ps1 up
```

`setup` chỉ tạo `.env` từ mẫu nếu file chưa có. Docker dùng **`.env` ở gốc repo** để nhận `VITE_SUPABASE_URL` và `VITE_SUPABASE_PUBLISHABLE_KEY`; không tự lấy hai giá trị từ `frontend/.env.local`. Dùng cấu hình Supabase/Google hiện có, không tạo lại project/provider. Không đưa secret vào `VITE_*`.

Để gọi API profile thật, điền đủ bốn biến trong chính `.env` gốc:

| Biến | Giá trị cần điền |
|---|---|
| `VITE_SUPABASE_URL` | Project URL dùng chung của nhóm. |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Publishable key của project đó. |
| `SUPABASE_URL` | Cùng giá trị với `VITE_SUPABASE_URL`. |
| `SUPABASE_ANON_KEY` | Cùng publishable key với `VITE_SUPABASE_PUBLISHABLE_KEY`; đây là tên biến backend hiện đang đọc. |

Hai biến `VITE_*` phục vụ frontend; backend đọc hai biến không có tiền tố này. Supabase hướng dẫn dùng publishable key với Python client tại [Python quickstart](https://supabase.com/docs/guides/getting-started/quickstarts/flask). API `/api/users/me` hiện dùng key public kết hợp JWT của người đăng nhập để kiểm quyền theo user; không cần service-role key cho endpoint này.

**Chẩn đoán 23/10/2026:** backend/frontend đều healthy nhưng backend đang nhận URL/key rỗng, log báo `SUPABASE_URL and SUPABASE_ANON_KEY must be configured`, còn `/api/users/me` trả 500. Điền hai biến backend trên rồi chạy lại `up` để Compose cập nhật environment; chỉ `restart` không nạp thay đổi `.env`. Chưa có bằng chứng API trả 200 sau bước sửa này. Health check đạt chỉ xác nhận server khởi động, chưa xác nhận kết nối Supabase/profile.

**Kiểm tiếp 23/10/2026:** container đã nhận đủ URL/key backend và URL khớp frontend. Log lỗi profile mới là `PGRST205`, không tìm thấy `public.users` trong schema cache của Data API. Bảng đã được khai báo ở [schema.sql](../backend/scripts/schema.sql), nhưng chưa xác minh trạng thái triển khai/exposure/cache trên Supabase chung; cần Duy kiểm schema/quyền/RLS và phối hợp người quản lý DB, không tự chạy lại toàn bộ SQL hoặc dùng service-role để bỏ qua lỗi. Chưa có API profile200.

**Cập nhật từ người quản lý 23/10/2026:** TV1 Trung Anh và TV3 Duy cùng quản lý Supabase; TV1 có thể trực tiếp bổ sung bảng/cấu hình theo schema repo và ghi lại phần đã áp dụng để phối hợp với Duy. User xác nhận `public.users` chưa có. Kiểm function/trigger hiện có trước khi áp phần Auth, gồm bảng, RLS/quyền API, đồng bộ user mới và bổ sung các user đã đăng nhập trước đó; chưa có bằng chứng SQL được chạy hoặc profile trả200. Các ghi chú cần chờ Duy thao tác phía trên là checkpoint lịch sử.

Kết quả SELECT do TV1 cung cấp: `users_exists=false`, `sync_function_exists=false`, `auth_triggers=[]`. Đã chuẩn bị [setup_auth_profiles.sql](../backend/scripts/setup_auth_profiles.sql) cho trạng thái chưa có các đối tượng Auth này. Script dùng bảng/function/trigger/policy từ schema nhóm, thêm quyền SELECT cho `authenticated` và bổ sung các tài khoản Auth có email đã tồn tại; không tạo dữ liệu mẫu. Toàn bộ phần ghi nằm trong một transaction, không thay thế các đối tượng đã có. Chạy một lần trong SQL Editor với role `postgres`, xem dòng kiểm cuối (các cờ true và profile_count), rồi thử lại từ Login. Chưa có kết quả thực thi/cloud200 tại checkpoint chuẩn bị này. Khi triển khai phần schema còn lại, đối chiếu các mục Auth đã áp; `schema.sql` có các policy trùng tên và không được thiết kế để chạy lại nguyên file sau setup này.

**SQL Auth đã áp theo TV1 — 23/10/2026:** người dùng báo năm cờ kiểm cuối đều `true`, `profile_count=1` sau khi chạy script trong Supabase. Đây là bằng chứng bảng/function/trigger/RLS/quyền SELECT đã có và một hồ sơ đã được bổ sung; chưa chứng minh trigger hoạt động với user mới, cách ly A/B hoặc API profile trả200. Bước tiếp bấm Thử lại tải hồ sơ trên Login và kiểm Network `/api/users/me`, không chạy lại script đã áp.

**Profile và phiên thật đã qua — 23/10/2026:** TV1 xác nhận yêu cầu từ ứng dụng `GET /api/users/me` trả **200**, Dashboard hiển thị đúng tên sau khi áp SQL. TV1 kiểm thủ công đạt: reload giữ phiên/profile; đăng xuất về Login, truy cập lại `/dashboard` và reload vẫn bị chặn; đăng nhập Google lại nhận profile 200 và đúng tên. Chưa kiểm trigger với tài khoản mới, ownership A/B hoặc expiry thật; các mốc lỗi500 và chuẩn bị SQL phía trên là lịch sử trước kết quả này.

Kiểm profile bằng nút đăng nhập/Thử lại tải hồ sơ trên `/login`, rồi xem yêu cầu `/api/users/me` trong Network. Mở thẳng URL này trên thanh địa chỉ không đi qua API client gắn token, nên phản hồi `401 {"detail":"Missing authorization header"}` là kết quả đúng cho yêu cầu chưa xác thực; nó khác lỗi500 của yêu cầu ứng dụng.

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
- `/api` được Vite proxy tới `API_PROXY_TARGET`, mặc định `http://localhost:8000` khi chạy trực tiếp và được cấu hình `http://backend:8000` trong Docker. Profile đã nối `GET /api/users/me`; API danh sách/clone phiên vẫn ở bước tích hợp riêng. Chạy được Vite không chứng minh API nghiệp vụ đã tích hợp.
- Cấu hình Docker của Tâm đã được đồng bộ vào nhánh Auth. Compose dev truyền hai biến public vào Vite; bản static dùng build args. Sau đổi env cần chạy lại `up` để áp dụng.

## Trạng thái Auth hiện tại

| Trạng thái | Hành vi |
|---|---|
| `checking` | Chưa xác minh được phiên; chặn trang nội bộ. Nếu kiểm phiên lỗi tạm thời/chưa xác định, có thông báo và nút Thử lại. |
| `unauthenticated` | Có thể bắt đầu đăng nhập Google. |
| `profile_pending` | Đã nhận phiên Supabase; hook tải profile từ backend. Trong lúc chờ hoặc lỗi vẫn chặn Dashboard, cho thử lại và đăng xuất. |
| `authenticated` | Profile hợp lệ khớp tài khoản/lượt đăng nhập; mở Dashboard và hiển thị tên. |
| `reauth_required` | Phiên hiện tại bị chặn; cho đăng xuất phiên cũ rồi đăng nhập lại. Request mới và kết quả của request cũ không được tiếp tục dùng phiên này. |

Bootstrap dùng `getSession` và một auth subscription; sự kiện mới/version mới có ưu tiên hơn kết quả bootstrap trả về muộn. `SIGNED_OUT` xóa trạng thái user/session và thông báo trung tính rằng phiên đã kết thúc, không tự đoán nguyên nhân. Đăng xuất từ UI dùng scope `local`.

Các module dùng chung:

- [supabase.js](src/services/supabase.js): một Supabase client qua `getSupabase()`.
- [authStore.js](src/features/auth/authStore.js): trạng thái phiên/profile và version của lượt đăng nhập.
- [api.js](src/services/api.js): Axios client cho API sản phẩm, lấy token hiện tại, 401 refresh/retry tối đa một lần, 403 giữ nguyên lỗi. Lỗi tạm không tự yêu cầu đăng nhập lại; lỗi không còn phiên được xử lý khi scope/token vẫn hiện hành. Không gọi signOut từ interceptor.
- [profile.js](src/services/profile.js): lấy profile qua API client dùng chung và kiểm ID/email cơ bản.
- [useAuthProfile.js](src/features/auth/useAuthProfile.js): tải/thử lại profile, đối chiếu tài khoản/version, hủy và bỏ kết quả cũ khi cleanup.
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

Mốc agent kiểm ngày 22/10 trước commit UI `08cd96a`: **51/51 Node tests**, lint/build đạt và **17/17 browser cases** riêng trên App/React StrictMode với Auth/HTTP giả lập; không cộng thành 68 npm tests. Ngày 23/10 TV1 kiểm thủ công trên tích hợp thật: profile 200/đúng tên, reload giữ phiên, đăng xuất/chặn Dashboard và Google login lại đều đạt. Chưa kiểm trigger tài khoản mới, expiry thật hoặc ownership A/B. Chưa chạy lại test/lint/build cho lượt cập nhật tài liệu này.

**Checkpoint Docker do tác giả kiểm ngày 21/10/2026**, tại merge commit `225c3db` (nhận dev `c583f4a`): setup/doctor/up đạt, mở được frontend/backend docs; đã báo hoàn thành kiểm Google quay về login, reload giữ phiên, chặn Dashboard khi profile_pending và đăng xuất. Lệnh `scripts/dev.ps1 test` đạt: backend **70 passed, 1 warning**; SymPy parser và frontend test/lint/build đều đạt theo kết quả tác giả cung cấp, chưa ghi số test frontend của lượt này. Cảnh báo StarletteDeprecationWarning đề nghị chuyển TestClient từ httpx sang httpx2; chưa đổi dependency/lockfile backend trong task Auth. Agent không trực tiếp chạy lại bộ kiểm Docker này.

Kiểm thủ công với tài khoản được phép: Google quay về `/login`, profile200 mở Dashboard; reload khôi phục phiên rồi xác nhận lại profile; đăng xuất về Login và mở lại `/dashboard` vẫn bị chặn; đăng nhập lại mở đúng tài khoản.

## Phần đang chờ tích hợp/review

- Profile của Duy đã được ghép; TV1 xác nhận API 200/đúng tên và kiểm thật reload/logout/chặn Dashboard/đăng nhập lại đạt. Còn avatar, trigger tài khoản mới, ownership A/B, expiry thật và review; chưa có nghiệm thu đầy đủ TASK-101.
- Dashboard danh sách phiên/API list/clone, Clone Modal của Bội Anh và điều hướng theo dữ liệu thật chưa được tích hợp trong nhánh Auth này.
- Chưa nghiệm thu quyền dữ liệu thật với tài khoản A/B, expiry thật, trigger tạo profile cho user mới hoặc session API. Docker startup và profile có checkpoint tác giả kiểm ở trên; chưa kiểm bản static Nginx, CI của tổ hợp Auth mới hoặc nghiệm thu tích hợp toàn bộ.

Đây là checkpoint frontend và profile tích hợp từng phần; **TASK-101/103 chưa được coi hoàn tất**. Không dùng mock profile để bỏ qua phần tích hợp đang chờ.

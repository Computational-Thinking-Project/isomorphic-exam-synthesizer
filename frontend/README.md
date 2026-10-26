# Frontend — thiết lập local và checkpoint TASK-101/103

Frontend sản phẩm dùng React/Vite và JavaScript/JSX. Đây là hướng dẫn cho repo sản phẩm; bộ `ui-draft` trong workspace là tài liệu thiết kế riêng.

## Đồng bộ dev — lượt 1, 27/10/2026

- Nhánh TASK103 nhận dev `0307b1c` (PR18 AI/Blueprint) từ nền Dashboard `c2613c4`; merge không xung đột, giữ nguyên App/Dashboard/Stage1 và client dùng chung. Chưa lấy PR15/16 hoặc triển khai thêm màn/trạng thái.
- Kiểm cây kết hợp trước commit: frontend146tests/lint/build đạt. Image backend build theo lockfile đạt; snapshot không chứa env thật, container tạm không mạng: backend + standalone Blueprint304tests đạt/1live opt-in skipped/1Starlette deprecation warning; Ruff đạt, Mypy52source files đạt, SymPy LaTeX smoke và pip check đạt.
- Các kiểm này không gọi AI/cloud và không restart container sản phẩm. UI Stage1 qua Docker/Google thật vẫn là lượt2; full status routing và màn đích còn theo plan, TASK103 chưa hoàn tất. Nhật ký chi tiết ở workspace `tmp/task103-sync-dev-20261027/QA.md`.

## Checkpoint hiện hành — TASK103 lượt C, 26/10/2026

- Nền dev đã merge tại170b847; create/detail service và SQL prerequisite đã lưu tại a117f0c/51db6be. User đã kiểm API thật: tạo/đọc phiên thành công, B đọc phiên A bị404, exam_versions setup đạt metadata checks. Các checkpoint pending merge bên dưới là lịch sử.
- Tạo đề mới mở `/session/new/stage1`, form thông tin chỉ POST khi xác nhận; thành công replace sang ID thật. Tiếp tục draft (kể cả bản clone) mở đúng ID và đọc lại detail. Không tự tạo khi mount/F5. Nếu trạng thái mới không còn draft thì hiện thông báo; các màn trạng thái khác còn chưa nối.
- Agent146 tests/lint/build đạt; kiểm trình duyệt local bằng Auth/API mô phỏng đạt create/replace/F5/retry/protected/account reset/mobile và Dashboard/clone/mở bản sao. Chưa kiểm màn entry mới bằng Docker/OAuth/cloud thật hoặc Nginx; không lấy kiểm API lượt B thay cho kiểm UI mới.
- Đây là entry/metadata của103, chưa có nhập/trích xuất/xác nhận nguồn W2 hoặc Stage2. TASK103 chưa Done. Chi tiết: [Stage1 entry](src/features/stage1-ingestion/README.md).

## Đồng bộ nền dev — 26/10/2026

- Đang ghép `origin/dev` tại `bbb7c5e` vào `feat/task-103-dashboard-api` bằng merge dừng trước commit. Auth PR #7 đã squash merge vào dev; không còn chờ review Auth để tiếp tục Dashboard.
- Giữ nguyên Dashboard API/list/phân trang/Clone Modal và account guard; nhận các file Blueprint/config/health từ dev. Không đưa mock vào route sản phẩm, không nhận các PR backend W2 đang chờ merge.
- Kiểm tự động sau ghép: agent chạy **113/113 Node tests**, lint và build đều đạt ngày26/10. DashboardRoute giữ nguyên nội dung so với mốc đã kiểm trước merge; diff cây chuẩn bị commit với dev chỉ còn11file Dashboard/setup DB/docs. Chưa kiểm browser/cloud/Docker mới; checkpoint24/10 bên dưới vẫn là bằng chứng lịch sử. Tạo mới/Mở Stage chưa được triển khai trong lượt đồng bộ này.

## Checkpoint TASK-103 — 24/10/2026

- Nhánh `feat/task-103-dashboard-api` đã đồng bộ PR6 tại merge `e7530a4` (dev `2c68b3a`). Dashboard tải list thật, phân trang, đủ10nhãn trạng thái và mở Clone Modal với service thật. Thành công tải lại trang1; adapter riêng chuyển thông báo lỗi nhưng giữ một API/Supabase client/store và xử lý401 chung. Tạo/mở Stage vẫn là thông báo.
- Tại code `6c16807`, TV1 kiểm trình duyệt/API/Supabase thật: danh sách trống và có dữ liệu; modal mở/đóng, focus/Tab/Esc, chặn tiêu đề trống; clone201, danh sách tự cập nhật và F5 giữ bản sao. Lỗi mạng giữ modal/tiêu đề, không tự đăng xuất/gửi lại; chủ động thử lại sau khôi phục mạng thành công.
- TV1 kiểm A có4phiên thử; B tải list200 không thấy phiên A và gọi clone ID nguồn A có thật nhận404, không tạo bản ghi. Verifier chỉ đọc do TV1 chạy trả `passed: true`: nguồn/bản sao mỗi bên1câu và1blueprint, nội dung đúng fixture, ID khác và liên kết đúng bản sao. Dữ liệu là fixture kỹ thuật, không phải đề/blueprint đã được AI hoặc giáo viên duyệt. Chi tiết và giới hạn ở [bằng chứng Dashboard](src/features/dashboard/README.md#live-browser-and-cloud-verification--24102026).
- Sau đồng bộ, TV1 báo frontend host **85 tests** và lint/build đạt; lượt Docker tiếp theo: backend **209 passed, 1 warning trong14.22s**, frontend **85 tests passed**. Warning là `StarletteDeprecationWarning` về `httpx` trong TestClient, không phải test fail; chưa đổi dependency trong phạm vi này. Đây là kết quả TV1 chạy, agent không rerun Docker.
- Mốc ghép modal: agent kiểm **113/113 Node tests**, lint/build và **18/18 ca ghép riêng** bằng ReactDOM thật với DOM/SDK/HTTP mô phỏng. Bộ18 không nằm trong113 hoặcCI, không phải kiểm trình duyệt/cloud. Chi tiết tại [checkpoint Dashboard](src/features/dashboard/README.md).
- Còn thiếu: màn/route và nơi tạo bản ghi phiên được nhóm chốt, ghép/kiểm Tạo mới và Mở/Tiếp tục. Phân trang nhiều trang, race và lỗi HTTP khác đã kiểm bằng fixtures; chưa kiểm nhiều trang cloud, mọi chiều/endpoint quyền hoặc cleanup khi cloud clone lỗi. Chưa đánh dấu TASK-103 Done hoặc đã được reviewer nghiệm thu.

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

### Profile trên Supabase

TV1 Trung Anh và TV3 Duy cùng quản lý Supabase. Ngày 23/10/2026 TV1 đã áp [setup_auth_profiles.sql](../backend/scripts/setup_auth_profiles.sql) khi bảng `public.users`, function đồng bộ và custom trigger chưa tồn tại. Script lấy định nghĩa Auth từ [schema.sql](../backend/scripts/schema.sql), tạo bảng/FK/RLS/policy/trigger, cấp SELECT cho `authenticated` và bổ sung profile từ các tài khoản Auth đã có. Năm cờ kiểm cuối đều true; sau đó tài khoản Google B mới tự có profile với ID khớp Auth và API profile trả 200 theo kiểm thủ công của TV1.

**Không chạy lại script trên project đã setup.** Script dành cho trạng thái chưa có các đối tượng Auth và không thay thế chúng. Khi triển khai schema còn lại, Duy cần đối chiếu các đối tượng Auth đã áp; không chạy nguyên `schema.sql` vì có policy trùng tên. Đây không phải migration đầy đủ cho các bảng nghiệp vụ.

Hai lỗi đã xử lý trong quá trình setup: backend thiếu URL/key và Data API báo `PGRST205` do chưa có `public.users`. Nếu đổi `.env`, chạy lại `up` để Compose cập nhật environment; chỉ `restart` không nạp cấu hình mới. Health check đạt không thay việc kiểm API profile.

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
- `/api` được Vite proxy tới `API_PROXY_TARGET`, mặc định `http://localhost:8000` khi chạy trực tiếp và được cấu hình `http://backend:8000` trong Docker. Profile nối `GET /api/users/me`; Dashboard nối list/clone theo checkpoint24/10. Chạy được Vite hoặc health check không thay việc kiểm các request nghiệp vụ.
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
- [UserAvatar.jsx](src/features/auth/UserAvatar.jsx): ảnh từ metadata của phiên Google có ID khớp profile; thiếu/lỗi ảnh hiển thị chữ viết tắt. Dashboard giữ tên từ backend, reset component theo tài khoản/version/URL ảnh.
- [authErrors.js](src/services/authErrors.js) và [authRefresh.js](src/services/authRefresh.js): phân loại lỗi Auth và chia sẻ refresh promise đồng thời.

Việc kiểm phiên trong frontend không thay backend JWT validation/RLS/ownership. Không dùng publishable key làm Bearer access token hoặc ghi token/session thật vào log để kiểm.

## Kiểm tra

Tại `frontend`, chạy lần lượt:

```powershell
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

### Bằng chứng kiểm tại mốc chốt tài liệu 23/10/2026

| Phạm vi | Kết quả và nguồn |
|---|---|
| Google login, profile backend | TV1 kiểm thật: `/api/users/me` 200, Dashboard đúng tên/ảnh. |
| Khôi phục và kết thúc phiên | TV1 kiểm thật: reload giữ phiên/profile; sign-out về Login, mở Dashboard/reload vẫn bị chặn; đăng nhập lại thành công. |
| Tài khoản mới và đổi A/B | TV1 kiểm thật: B chưa tồn tại trước login, profile tự tạo có ID khớp Auth; reload đúng B và chuyển lại A đúng thông tin. |
| RLS SELECT profile | TV1 chạy truy vấn `users.select('id')` không lọc tài khoản bằng JWT từng A và B: mỗi lần thành công, chỉ có một dòng ID của chính user. Không suy ra quyền ghi/sessions/storage. |
| Refresh chủ động | TV1 gọi helper `refreshSessionOnce()` với Supabase thật rồi `getMyProfile()`: hai cờ refresh/profile khớp đều true; vẫn ở Dashboard đúng tài khoản và F5 giữ phiên. Đây chưa phải ca token tự hết hạn. |
| Avatar | TV1 kiểm ảnh thật và đổi URL ảnh lỗi trong DevTools: chuyển chữ viết tắt, reload lấy lại ảnh. |
| Frontend tự động | Agent kiểm ngày 22/10: 51/51 Node tests, lint/build đạt; TV1 báo test/lint/build đạt sau khi thêm avatar ngày 23/10, không cung cấp số test mới. |
| Browser giả lập | Agent kiểm ngày 22/10: 17/17 ca App/React StrictMode với Auth/HTTP giả lập, gồm lỗi/retry, 401, logout và đổi tài khoản. Đây là lượt riêng, không cộng vào Node tests và không chứng minh expiry thật. |
| Docker trước khi ghép profile mới | TV1 kiểm ngày 21/10 tại `225c3db`: backend 70 tests/1 warning, SymPy parser và frontend test/lint/build đạt. Không phải lượt kiểm Docker mới nhất của toàn bộ nhánh Auth. |

Unit tests dùng source thật và Auth/HTTP giả lập, không cần key/env hoặc gọi Supabase thật. Không ghi token, email hoặc ID tài khoản thật vào tài liệu/bằng chứng. Agent không chạy lại test/lint/build trong lượt chỉ sửa tài liệu này.

`scripts/dev.ps1 test` chạy backend tests, SymPy parser và frontend test/lint/build trong Docker; không tự chạy các ca browser hay Google OAuth thật. Job frontend trong [ci.yml](../.github/workflows/ci.yml) chỉ build; [docker-ci.yml](../.github/workflows/docker-ci.yml) chạy helper trên để kiểm test/lint/build trong container. Kết quả CI của head mới sau push cần xem trên PR. Warning Starlette/httpx ở checkpoint cũ chưa được sửa dependency trong task này.

## Phần đang chờ tích hợp/review

- TASK-101: code Google login/profile/avatar đã được squash merge qua PR #7 vào dev tại `bbb7c5e`. Token tự hết hạn hoặc refresh thật thất bại chưa kiểm trên cloud; hành vi 401/refresh thất bại có kiểm giả lập. Việc merge không thay bằng chứng cho các ca chưa kiểm.
- TASK-103: list API/phân trang và Clone Modal đã nối; browser/cloud list, clone, persistence, copy câu/blueprint và ca B bị chặn clone nguồn A đã đạt theo TV1 ở checkpoint24/10. Điều hướng Stage/nơi tạo phiên chưa chốt; chưa kiểm phân trang nhiều trang cloud hoặc mọi endpoint/chiều quyền.
- Chưa kiểm lại bản static Nginx hoặc CI của commit merge Dashboard sắp lưu. Bằng chứng sessions chỉ áp cho các thao tác/fixture đã nêu; không suy ra quyền UPDATE, storage hoặc cleanup khi lỗi cloud. Quyền SELECT profile không thay kiểm các phần đó.

Nhánh đang triển khai: `feat/task-103-dashboard-api`, ban đầu từ nền Auth `978003a`; đang đồng bộ dev sau khi Auth squash merge. PR #6 Clone Modal đã merge tại `2c68b3a` và đã ghép vào Dashboard. Trước khi PR #17 vào dev, cần lưu merge, kiểm diff chỉ còn phạm vi TASK-103 và hoàn tất các tiêu chí tạo/mở còn thiếu. **TASK-103 chưa hoàn tất.** Quyết định Auth và SQL được ghi ở [DEC-TV1-002](../docs/change_log.md#dec-tv1-002-tích-hợp-google-oauth-profile-và-bootstrap-auth); các checkpoint23–24/10 phía trên là lịch sử theo phạm vi đã nêu.

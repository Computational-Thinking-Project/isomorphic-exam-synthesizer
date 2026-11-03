# UI walkthrough — exam mirror

**Bản portable 02/11/2026 — logo trong suốt và transition hai giai đoạn S00→S01.** Giữ tên sản phẩm rõ ở S00, nhấn đáp án S03/S06 và thao tác trong popup S06. Mở [launcher](index.html) hoặc [PREVIEW.html](PREVIEW.html) bằng Chrome sau khi lấy về máy. Không cần npm, Docker, API key hoặc server. GitHub chỉ hiển thị nội dung HTML, không chạy demo ngay trong trang xem file.

## Lấy gói về máy

Gói nằm trên nhánh `fix/ui-ux-demo`, đường dẫn `docs/ui-walkthrough/`. Trong clone hiện có, kiểm `git status` trước. Nếu có thay đổi chưa lưu hoặc nhánh local phân kỳ, giữ công việc của mình; không dùng reset/force để lấy demo.

```sh
git fetch origin
```

Nếu chưa có local branch:

```sh
git switch --track -c fix/ui-ux-demo origin/fix/ui-ux-demo
```

Nếu đã có local branch:

```sh
git switch fix/ui-ux-demo
git pull --ff-only origin fix/ui-ux-demo
```

Mở `docs/ui-walkthrough/index.html` bằng Chrome từ trình quản lý file. Giữ nguyên cả thư mục nếu chia sẻ lại để các liên kết tương đối vẫn dùng được. Riêng PREVIEW.html tự chứa toàn bộ app, font, artwork và notices, có thể mở độc lập.

**Mốc đóng gói:** bản logo transparent/transition v2 chuẩn bị trên `fix/ui-ux-demo` từ `289ada0`. Đây là thông tin lúc chuẩn bị commit; lịch sử Git và remote cho biết commit/push thực tế. Kiểm hash để nhận đúng bản.

## Bản và nguồn

- Nguồn: `project/ui-draft/redesign/PREVIEW.html` ở workspace thiết kế, không phải build frontend sản phẩm.
- 2.858.883 bytes; SHA256 `8f9d6ebca4ad42b3ebddc15cf2fb4119b9599b8eb175c1b2c4d749b5f779dfaa`.
- CSS `index-CfK_83Th.css`, JS `index-BGhsC9Oi.js` đã nhúng cùng font, artwork, cả hai logo và third-party notices.
- Nền repo khi đóng gói: `289ada0c39b609d35f81eee34c19f6916441581f`; đây không phải source commit của artifact ui-draft.
- [version.json](version.json) ghi nguồn/hash/trạng thái kiểm. `.gitattributes` giữ nguyên bytes PREVIEW, không tự chuyển CRLF/LF.

Kiểm file bằng PowerShell:

```powershell
Get-Item ./docs/ui-walkthrough/PREVIEW.html | Select-Object Length
Get-FileHash ./docs/ui-walkthrough/PREVIEW.html -Algorithm SHA256
```

## Walkthrough hiện hành

### S00 → S03: nguồn

S00 dùng logo nhỏ, tên **EXAM MIRROR** bằng chữ navy, slogan, hai dòng mô tả và CTA `Bắt đầu "mirroring" nào!`. Đã bỏ audience, hint đăng nhập và hai caption artwork; giữ hai artwork trang trí. Entrance gồm bốn nhóm600ms, gap80ms, tổng840ms theo cấu hình.

Header S01 sau transition, S02–S08 và menu drawer dùng PNG trong suốt do user cung cấp:666×375/73.021bytes, SHA256 `eebdc875bb4e827401ab12f26023eb0771c7bf14c46fc5a6e43c77631c8b9307`; nguồn `Computational_Thinking_-_Midterm-removebg-preview.png`. Ảnh được nhúng nguyên trạng, giữ alpha0..255; CSS dùng khung594×128 tại(40,128) bỏ canvas trống. Light không có nền đệm cố định; dark experimental giữ backing sáng riêng để đọc chữ đen. Giữ chữ serif/phản chiếu trong artwork, không thêm font ứng dụng. Không có license riêng đi kèm ảnh; ghi đúng nguồn user cung cấp, không tự gán license.

Khi pointer chuyển từ S00 và assets/fonts đã sẵn, logo cũ travel450ms với scale đồng đều đến đúng phần biểu tượng bên trái của logo mới. Ngay callback hoàn tất, logo mới phủ lên và logo cũ mờ đi trong140ms; sau đó React gỡ node cũ khỏi DOM. Khung ngoài giữ kích thước cuối, geometry theo chiều rộng header thực. Luồng chuẩn590ms là cấu hình, chưa đo Chrome. Slogan giữFLIP450ms, card300ms+delay130ms, focus login ngay; không cộng lại reveal350ms cũ.

Hai ảnh/fonts preload ở nền, CTA không chờ2s. Bấm sớm khi chưa sẵn, mở S01 trực tiếp, sign-out, keyboard/reduced/hidden hoặc hình học lỗi đi thẳng logo cuối. Interrupt/resize/ảnh lỗi/WAAPI failure giữa chừng cũng về final, cleanup animation/observer/listener và không gọi callback cũ sau unmount. Mobile giữ logo256px/hai hàng header112px; desktop thấp giữheader52/56px. Đây là logic đã dựng, chưa kiểm hiển thị/timing thực hoặc Designer/user nghiệm thu.

Mở S00 từ launcher. Login/Library là giao diện demo. Tạo phiên mới hoặc dùng checkpoint S03 empty; bấm **Xem dữ liệu mẫu**, đọc đề, **Xác nhận toàn bộ đề**, rồi **Tiếp theo**. Chọn file chỉ dùng tên file, không upload/parse nội dung.

Trong **Bản đọc S03** và **hai panel S06**, phương án mang khóa đáp án có nền xanh lam xám nhẹ, viền navy và nhãn chữ **Đáp án**. Nhãn theo option ID nên đi cùng phương án sau trộn, không cố định theo chữ A/B/C/D. Đây là khóa đang gán trong nội dung, không xác nhận đáp án đúng hoặc giáo viên đã duyệt; xanh lá vẫn dành cho **Đã duyệt**. Giấy nguồn và bản đề học sinh không hiện dấu đáp án. Popup giữ tóm tắt đáp án/lời giải hiện có.

### S04 → S05: vào duyệt ngay khi có kết quả

Nhập **2**, xác nhận **5 câu/mã × 2 mã = 10 biến thể**, bấm **Tạo biến thể** và xác nhận. S05 bắt đầu ở 0/10 rồi tự nhận từng cặp câu–mã bằng bộ mô phỏng. Ngay khi có ít nhất một cặp hợp lệ đã nhận, nút **Bắt đầu duyệt** bật; không phải đợi đủ 10 hoặc readiness cả bộ. Màn không tự điều hướng.

Bấm vào ngay sau kết quả đầu tiên để thấy tiến trình tiếp tục tại S06. Tiến trình mẫu thường chạy khoảng 4,5 giây cho 10 cặp, rồi có một bước readiness riêng; đây là lịch timer trong source, chưa phải thời gian đo trên Chrome hoặc AI latency. Nếu đợi hết rồi mới bấm thì tất cả ô đã có nội dung, không còn skeleton.

### S06: duyệt từ Câu 1 trong khi phần còn lại tiếp tục tạo

Lượt tạo mới mở **Câu 1/mã 101**, **0/10 đã duyệt**. Không tự duyệt sẵn 9 câu. Riêng **Câu 3/mã 101 giữ lỗi nội dung B=C** để thử đối chiếu/Tạo lại/duyệt; các cặp khác vẫn tạo bình thường. Đây là lỗi nội dung mẫu đã nhận, không phải job tạo thất bại. Bộ mô phỏng nằm ở workflow chung, nên chuyển S05→S06 không khởi động lại lượt tạo hoặc hủy timer đang chờ.

- Ô câu và tab mã hiển thị biểu tượng đang tạo, chờ lượt hoặc lỗi theo đúng cặp đang chọn. Vẫn bấm chọn được ô đang tải.
- Cặp đang tạo/chờ lượt hiển thị skeleton ở panel biến thể bên phải; đề nguồn vẫn đọc được bên trái. Chưa hiện đề biến thể, phương án, key hoặc lời giải trước khi nhận kết quả.
- Khi đúng cặp nhận xong, skeleton đổi thành nội dung mà không đổi câu/mã đang chọn. Tạo lại và Kiểm tra đáp án khóa khi cặp còn tải.
- Trên trang chính chỉ có lối **Kiểm tra đáp án**. Popup có **Tạo lại** và **Duyệt biến thể** cạnh nhau, cùng căn bên phải; bỏ Quay lại, dùng X ở góc phải trên để đóng. Với cặp đã nhận, đối chiếu rồi **Duyệt biến thể**. Sau khi model ghi nhận đúng revision, popup đóng, chọn câu chưa duyệt tiếp theo theo thứ tự nguồn và giữ mã. Câu tiếp theo còn tải thì hiện skeleton, không bỏ qua.
- Hết câu của mã hiện tại, tự chọn mã khác để tiếp tục. S06 không tự chuyển S07.
- S06 chỉ đọc, không còn Chỉnh sửa, editor, Lưu/Hủy hoặc checkbox đối chiếu. **Tạo lại** là thao tác thay nội dung duy nhất, nằm trong popup Kiểm tra đáp án và có xác nhận đúng cặp ngay trong cùng cửa sổ. Kết quả mới vẫn chưa duyệt và phải kiểm tra lại; nhận nền không ghi đè nội dung hoặc approval hiện có.

**Rà bộ đề** vẫn cần toàn bộ cặp hợp lệ đã nhận, readiness và đủ approval hiện hành. **Chốt cả bộ** còn cần rà đủ hai loại bản của mọi mã ở revision hiện tại. Bật nút vào S06 sớm không làm nhẹ các gate này.

### Ca lỗi nội dung mặc định ở Câu 3/mã 101

Sau khi nhận Câu 3, B=C=`{3;4}` và duyệt bị chặn. Bấm **Kiểm tra đáp án**, đọc lỗi rồi **Tạo lại** ngay trong popup. Nội dung chuyển sang xác nhận **Tạo lại đúng cặp**, có **Hủy tạo lại**; không mở chồng dialog. Sau khi model nhận kết quả, popup vẫn mở và hiển thị đề/key/steps cùng revision mới, chưa được duyệt. Đọc lại ngay tại đó rồi **Duyệt biến thể**; duyệt đúng revision mới đóng popup/chuyển câu. Không tự approve hoặc nạp9approval. Đi lại giữa S05/S06 không seed lỗi lại; lượt mới/reload fixture mới khôi phục B=C. Đây là ca UI mẫu, không phải output AI thật.

Ở hai panel, chỉ C mang key được nhấn **Đáp án** dù B trùng nội dung C; cảnh báo trùng và khóa duyệt vẫn giữ. Thiếu key, ID rỗng/trùng hoặc thứ tự phương án không hợp lệ không tạo marker giả.

### Lỗi, tạm dừng và thử lại

Cặp thiếu hoặc tạo thất bại vẫn mở được **Kiểm tra đáp án** ở chế độ phục hồi, không bịa nội dung/key/steps. Bấm **Tạo lại** trong popup và xác nhận để enqueue đúng phần lỗi; các cặp khỏe còn chờ tiếp tục chạy. Thử lại chỉ enqueue phần lỗi, giữ nội dung/approval đã có. Cặp không có mẫu phù hợp với nguồn đã sửa không tự thay bằng câu khác; cần xử lý nguồn hoặc tạo lại phù hợp.

Trong `view=review`, công cụ S05 cho tạm dừng/nhận mẫu/làm lỗi thủ công. Trạng thái tạm dừng theo sang S06; bấm **Tiếp tục tạo** để chạy tiếp. Lượt tạo mới reset pause và chọn Câu 1/mã 101. Callback của lượt/revision cũ bị chặn. Rời workflow dừng timer; quay lại tiếp tục phiên trong bộ nhớ, không có job server chạy nền.

### Đóng popup, thông báo và Tạo lại

X/Esc/backdrop cùng đóng popup và hủy ý định chưa xác nhận. Trong khoảng đang Tạo lại, khóa đóng để chờ model acknowledgement; callback của revision/lượt cũ bị chặn. Hủy xác nhận trở về nội dung đang kiểm. Focus intent: heading xác nhận → Tạo lại khi hủy, hoặc heading nội dung mới sau thành công; đóng popup về nút mở. Đây là logic đã dựng, chưa đo focus native.

S06 dùng toast góc trên phải dưới header/preview bar, tối đa 2 cùng lúc, tự ẩn sau 5 giây từ lúc hiện. Toast không chiếm chiều cao hai panel. Badge và nút phục hồi vẫn giữ; hết toast không xóa lỗi hoặc mở khóa duyệt. Lỗi trong popup đáp án hoặc xác nhận Tạo lại giữ tại chỗ. Reduced motion tắt animation, không dừng job mô phỏng.

Tạo lại vẫn hỏi xác nhận, dùng cửa sổ offset 1–8 so với seed nguồn và tránh nội dung trùng cặp hiện tại/mã khác cùng nguồn. Hết ứng viên thì giữ nguyên câu và báo rõ. S00→S01 giữ bản sửa CTA không xuất hiện muộn trên login. Không suy độ khó tương đương từ giới hạn số của demo.

## Checkpoint và reset

- Luồng chính: S00/S03 → S04 → S05 → S06. Giữ cùng tab, không reload để giữ tiến trình/nội dung hiện hành.
- Dự phòng S05 success nạp một phần kết quả mẫu rồi tiếp tục chạy; không phải tiếp tục job cũ.
- Dự phòng S06 success đã nhận đủ mẫu, 0/10 approval, chọn Câu 1. Muốn thấy loading/skeleton phải tạo lượt mới từ S04.
- `presenter-issue` chỉ còn là fixture QA cũ gọi tường minh, ngoài launcher và luồng chính. Các cue Full flow v3 về Câu 3/9 approval không còn mô tả bản này; chưa cập nhật Docs/deck Presenter.
- Reload hoặc mở checkpoint sẽ tạo fixture mới, mất state vừa thao tác. Back không phục hồi run. Nếu thao tác lỗi, ghi actual; không ghép hai checkpoint thành một run.
- Ưu tiên light, desktop Chrome, zoom 100%; S07 provisional, dark experimental.

## Kiểm đã làm và còn chờ

Lượt transition v2 mới nhất: **20 kiểm tập trung/hồi quy qua**, TypeScript/build cuối qua (1625 modules). Có geometry uniform, preload/bấm sớm, travel→replace→final/removal, interrupt/error/observer/unmount/callback cũ, simulated effect replay, shared runner completion reason/zero-argument compatibility và page/Modal smoke. Arrival có logo+slogan; đã thay kỳ vọng signature reveal350ms/slogan-only cũ.58 source khác,62 public assets và packager giữ hash trong lượt v2.

Các suite nhận diện18 ca/transparent7 ca ở lượt trước không được nhận là đã rerun nguyên vẹn; bộ20 hiện hành thay các kỳ vọng đã đổi. Kiểm fake DOM/WAAPI không thay native geometry/readability/elapsed timing/focus/StrictMode browser pass.

Lượt nhấn đáp án trước đó có84 ca và32 so sánh markup qua; không chạy lại khi chỉ đổi nhận diện. Tương phản tính từ tokens light nội dung/nhãn 13.14:1/7.74:1, dark13.51:1/8.33:1; chưa kiểm màu thực hoặc screen reader.

Lượt popup trước đó có 151 ca và 40 so sánh markup qua; không nhận toàn bộ đã chạy lại cho bản này. Fake timers/hooks/React element/handler checks không phải browser pass. SSR useLayoutEffect warnings không dùng để nghiệm thu visual.

Gói chia sẻ được kiểm bytes/hash nguồn–dist–repo, tài nguyên/licenses nhúng, liên kết tương đối, Git attributes và phạm vi diff. Không chạy test hoặc build sản phẩm/backend.

| Kiểm trực tiếp Chrome cần làm | Trạng thái |
|---|---|
| Mở file ở folder mới, font/artwork/công thức | Chưa kiểm |
| S00→S01 travel450/overlay140/legacy DOM removal; transparent/căn nét/header mobile/drawer | Chưa kiểm |
| Nhãn/nền/viền đáp án, panel hẹp, công thức dài, screen reader | Chưa kiểm |
| S04→S05, mở duyệt sau cặp đầu, progress tiếp tục ở S06 | Chưa kiểm |
| Click ô/tab còn tải, spinner/clock/skeleton rồi hiện nội dung | Chưa kiểm |
| Một popup: Tạo lại/xác nhận/kết quả mới/approve khi các cặp khác đang nhận | Chưa kiểm |
| Lỗi/thử lại, pause/resume và gate Rà bộ đề | Chưa kiểm |
| X/Esc/backdrop, focus/Tab/Enter, toast5giây, scroll/overflow/zoom200% | Chưa kiểm |
| Reduced motion và Designer/user nghiệm thu | Chưa kiểm |

Người trực tiếp chạy ghi ngày, bản/hash, browser/version, viewport/zoom, actual và lỗi. Công cụ trước bị chặn PREVIEW file://; không dùng server, localhost, CDP hoặc surface khác để vượt chặn. Hướng walkthrough live không bắt buộc ảnh/video.

## Giới hạn tuyên bố

Preview dùng dữ liệu mẫu và bộ nhớ tab, chưa auth/upload/parser/AI/lưu server/PDF thật. Không dùng fixture làm output AI hoặc approval giáo viên thật; không suy coverage toàn Đại số, comparable difficulty, accuracy hay thời gian tiết kiệm. Không tạo file giả đuôi PDF. Giữ notices nhúng khi phân phối lại.

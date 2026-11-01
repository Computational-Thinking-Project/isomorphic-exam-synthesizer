# UI walkthrough — exam mirror

**Bản portable 01/11/2026 — duyệt trong lúc tạo.** Mở [launcher](index.html) hoặc [PREVIEW.html](PREVIEW.html) bằng Chrome sau khi lấy về máy. Không cần npm, Docker, API key hoặc server. GitHub chỉ hiển thị nội dung HTML, không chạy demo ngay trong trang xem file.

## Lấy gói về máy

Gói nằm trên nhánh `feat/ui-ux-demo`, đường dẫn `docs/ui-walkthrough/`. Trong clone hiện có, kiểm `git status` trước. Nếu có thay đổi chưa lưu hoặc nhánh local phân kỳ, giữ công việc của mình; không dùng reset/force để lấy demo.

```sh
git fetch origin
```

Nếu chưa có local branch:

```sh
git switch --track -c feat/ui-ux-demo origin/feat/ui-ux-demo
```

Nếu đã có local branch:

```sh
git switch feat/ui-ux-demo
git pull --ff-only origin feat/ui-ux-demo
```

Mở `docs/ui-walkthrough/index.html` bằng Chrome từ trình quản lý file. Giữ nguyên cả thư mục nếu chia sẻ lại để các liên kết tương đối vẫn dùng được. Riêng PREVIEW.html tự chứa toàn bộ app, font, artwork và notices, có thể mở độc lập.

**Phát hành:** refresh duyệt trong lúc tạo này còn local, **chưa commit/push**. HEAD lúc đóng gói là `879319f` (toast, local/ahead1); remote `23d0df9` vẫn là demo Presenter cũ. Pull nhánh hiện tại chưa có refresh này cho tới khi được publish. Kiểm hash để nhận đúng bản.

## Bản và nguồn

- Nguồn: `project/ui-draft/redesign/PREVIEW.html` ở workspace thiết kế, không phải build frontend sản phẩm.
- 2.758.050 bytes; SHA256 `cdebc94e3ccdf4803ca3a7e0e2e640252b06e6154506326a0cb0f0fe92e3d22d`.
- CSS `index-WFK8JX_V.css`, JS `index-DvC3dO1A.js` đã nhúng cùng font, artwork và third-party notices.
- Nền repo khi đóng gói: `879319fa3fac30c89f7f504ef185ab4f6cb912b0`; đây không phải source commit của artifact ui-draft.
- [version.json](version.json) ghi nguồn/hash/trạng thái kiểm. `.gitattributes` giữ nguyên bytes PREVIEW, không tự chuyển CRLF/LF.

Kiểm file bằng PowerShell:

```powershell
Get-Item ./docs/ui-walkthrough/PREVIEW.html | Select-Object Length
Get-FileHash ./docs/ui-walkthrough/PREVIEW.html -Algorithm SHA256
```

## Walkthrough hiện hành

### S00 → S03: nguồn

Mở S00 từ launcher. Login/Library là giao diện demo. Tạo phiên mới hoặc dùng checkpoint S03 empty; bấm **Xem dữ liệu mẫu**, đọc đề, **Xác nhận toàn bộ đề**, rồi **Tiếp theo**. Chọn file chỉ dùng tên file, không upload/parse nội dung.

### S04 → S05: vào duyệt ngay khi có kết quả

Nhập **2**, xác nhận **5 câu/mã × 2 mã = 10 biến thể**, bấm **Tạo biến thể** và xác nhận. S05 bắt đầu ở 0/10 rồi tự nhận từng cặp câu–mã bằng bộ mô phỏng. Ngay khi có ít nhất một cặp hợp lệ đã nhận, nút **Bắt đầu duyệt** bật; không phải đợi đủ 10 hoặc readiness cả bộ. Màn không tự điều hướng.

Bấm vào ngay sau kết quả đầu tiên để thấy tiến trình tiếp tục tại S06. Tiến trình mẫu thường chạy khoảng 4,5 giây cho 10 cặp, rồi có một bước readiness riêng; đây là lịch timer trong source, chưa phải thời gian đo trên Chrome hoặc AI latency. Nếu đợi hết rồi mới bấm thì tất cả ô đã có nội dung, không còn skeleton.

### S06: duyệt từ Câu 1 trong khi phần còn lại tiếp tục tạo

Lượt tạo mới mở **Câu 1/mã 101**, **0/10 đã duyệt**. Không tự duyệt sẵn 9 câu. Riêng **Câu 3/mã 101 giữ lỗi nội dung B=C** để thử đối chiếu/sửa/duyệt; các cặp khác vẫn tạo bình thường. Đây là lỗi nội dung mẫu đã nhận, không phải job tạo thất bại. Bộ mô phỏng nằm ở workflow chung, nên chuyển S05→S06 không khởi động lại lượt tạo hoặc hủy timer đang chờ.

- Ô câu và tab mã hiển thị biểu tượng đang tạo, chờ lượt hoặc lỗi theo đúng cặp đang chọn. Vẫn bấm chọn được ô đang tải.
- Cặp đang tạo/chờ lượt hiển thị skeleton ở panel biến thể bên phải; đề nguồn vẫn đọc được bên trái. Chưa hiện đề biến thể, phương án, key hoặc lời giải trước khi nhận kết quả.
- Khi đúng cặp nhận xong, skeleton đổi thành nội dung mà không đổi câu/mã đang chọn. Chỉnh sửa, Tạo lại và Kiểm tra đáp án khóa khi cặp còn tải.
- Với cặp đã nhận: mở **Kiểm tra đáp án**, đối chiếu rồi **Duyệt biến thể**. Sau khi model ghi nhận đúng revision, popup đóng, chọn câu chưa duyệt tiếp theo theo thứ tự nguồn và giữ mã. Câu tiếp theo còn tải thì hiện skeleton, không bỏ qua.
- Hết câu của mã hiện tại, tự chọn mã khác để tiếp tục. S06 không tự chuyển S07.
- Sửa/lưu vẫn cần checkbox đối chiếu; trạng thái kiểm cũ hết hiệu lực, phải review lại và duyệt revision mới. Kết quả tới từ cặp khác không ghi đè bản sửa hoặc approval hiện có.

**Rà bộ đề** vẫn cần toàn bộ cặp hợp lệ đã nhận, readiness và đủ approval hiện hành. **Chốt cả bộ** còn cần rà đủ hai loại bản của mọi mã ở revision hiện tại. Bật nút vào S06 sớm không làm nhẹ các gate này.

### Ca lỗi nội dung mặc định ở Câu 3/mã 101

Sau khi nhận Câu 3, B=C=`{3;4}` và duyệt bị chặn. Mở Chỉnh sửa, đổi riêng B thành `{2;6}`, giữ C/key/lời giải, tick đối chiếu và Lưu thay đổi. Nội dung chuyển sang kiểm cũ hết hiệu lực; mở Kiểm tra đáp án lại rồi Duyệt biến thể. Có thể chọn Tạo lại để thay đúng cặp bằng mẫu hợp lệ. Sửa/tạo lại không tự đánh dấu duyệt hoặc nạp 9 approval. Đi lại giữa S05/S06 không chèn lỗi lại; tạo lượt mới hoặc reload fixture mới khôi phục ca lỗi mặc định. Đây là dữ liệu cố ý chuẩn bị cho UI, không phải lỗi/output AI thật.

### Lỗi, tạm dừng và thử lại

Cặp lỗi có badge và nút **Thử lại câu này** cố định; các cặp khỏe còn chờ tiếp tục chạy. Thử lại chỉ enqueue phần lỗi, giữ nội dung/approval đã có. Cặp không có mẫu phù hợp với nguồn đã sửa không tự thay bằng câu khác; cần xử lý nguồn hoặc tạo lại phù hợp.

Trong `view=review`, công cụ S05 cho tạm dừng/nhận mẫu/làm lỗi thủ công. Trạng thái tạm dừng theo sang S06; bấm **Tiếp tục tạo** để chạy tiếp. Lượt tạo mới reset pause và chọn Câu 1/mã 101. Callback của lượt/revision cũ bị chặn. Rời workflow dừng timer; quay lại tiếp tục phiên trong bộ nhớ, không có job server chạy nền.

### Thông báo và Tạo lại

S06 dùng toast góc trên phải dưới header/preview bar, tối đa 2 cùng lúc, tự ẩn sau 5 giây từ lúc hiện. Toast không chiếm chiều cao hai panel. Badge và nút phục hồi vẫn giữ; hết toast không xóa lỗi hoặc mở khóa duyệt. Lỗi field editor và popup đáp án giữ tại chỗ. Reduced motion tắt animation, không dừng job mô phỏng.

Tạo lại vẫn hỏi xác nhận, dùng cửa sổ offset 1–8 so với seed nguồn và tránh nội dung trùng cặp hiện tại/mã khác cùng nguồn. Hết ứng viên thì giữ nguyên câu và báo rõ. S00→S01 giữ bản sửa CTA không xuất hiện muộn trên login. Không suy độ khó tương đương từ giới hạn số của demo.

## Checkpoint và reset

- Luồng chính: S00/S03 → S04 → S05 → S06. Giữ cùng tab, không reload để giữ tiến trình/bản sửa.
- Dự phòng S05 success nạp một phần kết quả mẫu rồi tiếp tục chạy; không phải tiếp tục job cũ.
- Dự phòng S06 success đã nhận đủ mẫu, 0/10 approval, chọn Câu 1. Muốn thấy loading/skeleton phải tạo lượt mới từ S04.
- `presenter-issue` chỉ còn là fixture QA cũ gọi tường minh, ngoài launcher và luồng chính. Các cue Full flow v3 về Câu 3/9 approval không còn mô tả bản này; chưa cập nhật Docs/deck Presenter.
- Reload hoặc mở checkpoint sẽ tạo fixture mới, mất state vừa sửa. Back không phục hồi run. Nếu thao tác lỗi, ghi actual; không ghép hai checkpoint thành một run.
- Ưu tiên light, desktop Chrome, zoom 100%; S07 provisional, dark experimental.

## Kiểm đã làm và còn chờ

Source: **10 ca default B=C + 29 ca progressive review + 30 ca S06 + 37 ca Đại số + 16 ca toast = 122 ca qua**, TypeScript/build qua (1619 modules). 29 ca scheduler dùng fixture nội dung sạch tường minh; 10 ca mới kiểm luồng thực có B=C, sửa/stale/approve và Tạo lại. Các ca dùng fake timer, hook trong bộ nhớ và React element/static markup; không phải pass thao tác hay hình học trên browser. SSR có cảnh báo useLayoutEffect; không dùng SSR để nghiệm thu toast/animation.

Gói chia sẻ được kiểm bytes/hash nguồn–dist–repo, tài nguyên/licenses nhúng, liên kết tương đối, Git attributes và phạm vi diff. Không chạy test hoặc build sản phẩm/backend.

| Kiểm trực tiếp Chrome cần làm | Trạng thái |
|---|---|
| Mở file ở folder mới, font/artwork/công thức | Chưa kiểm |
| S04→S05, mở duyệt sau cặp đầu, progress tiếp tục ở S06 | Chưa kiểm |
| Click ô/tab còn tải, spinner/clock/skeleton rồi hiện nội dung | Chưa kiểm |
| Chỉnh sửa/lưu và duyệt khi các cặp khác đang nhận | Chưa kiểm |
| Lỗi/thử lại, pause/resume và gate Rà bộ đề | Chưa kiểm |
| Toast 5 giây/vị trí/focus, Tab/Enter/Esc, scroll/overflow/zoom 200% | Chưa kiểm |
| Reduced motion và Designer/user nghiệm thu | Chưa kiểm |

Người trực tiếp chạy ghi ngày, bản/hash, browser/version, viewport/zoom, actual và lỗi. Công cụ trước bị chặn PREVIEW file://; không dùng server, localhost, CDP hoặc surface khác để vượt chặn. Hướng walkthrough live không bắt buộc ảnh/video.

## Giới hạn tuyên bố

Preview dùng dữ liệu mẫu và bộ nhớ tab, chưa auth/upload/parser/AI/lưu server/PDF thật. Không dùng fixture làm output AI hoặc approval giáo viên thật; không suy coverage toàn Đại số, comparable difficulty, accuracy hay thời gian tiết kiệm. Không tạo file giả đuôi PDF. Giữ notices nhúng khi phân phối lại.

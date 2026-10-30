# UI walkthrough — exam mirror

**Bản portable 30/10/2026**, dùng cho Full flow v3. Mở [launcher](index.html) hoặc [PREVIEW.html](PREVIEW.html) bằng Chrome sau khi lấy file về máy. Không cần npm, Docker, API key hoặc server. GitHub chỉ hiển thị nội dung HTML; không chạy demo ngay trong trang xem file GitHub.

## Lấy gói về máy

Gói nằm trên nhánh `feat/ui-ux-integration`, đường dẫn `docs/ui-walkthrough/`. Trong clone hiện có, kiểm `git status` trước. Nếu có thay đổi chưa lưu hoặc nhánh local phân kỳ, dừng cập nhật và giữ công việc của mình; không dùng reset/force để lấy demo.

```sh
git fetch origin
```

Nếu chưa có local branch:

```sh
git switch --track -c feat/ui-ux-integration origin/feat/ui-ux-integration
```

Nếu đã có local branch:

```sh
git switch feat/ui-ux-integration
git pull --ff-only origin feat/ui-ux-integration
```

Mở `docs/ui-walkthrough/index.html` bằng Chrome từ trình quản lý file. Nếu chỉ chia sẻ lại file, giữ nguyên cả thư mục nhỏ này để các liên kết tương đối vẫn dùng được. Riêng PREVIEW.html tự chứa toàn bộ app và có thể mở độc lập.

**Phát hành:** lúc chuẩn bị gói ngày30/10, các file mới còn local, chưa commit/push. Thành viên chỉ pull được sau khi chủ nhánh đã publish commit chứa thư mục này. Không coi nhánh đã tồn tại trên remote là gói mới đã có trên remote.

## Bản và nguồn

- Nguồn artifact: `project/ui-draft/redesign/PREVIEW.html` ở workspace thiết kế, không phải bản build của frontend sản phẩm.
- 2.746.995 bytes; SHA256 `b24f43f83013dfea2d164b96f99193634609b8280b4fba7cb2a627fb758872b9`.
- CSS `index-5UxxvQ3V.css`, JS `index-Bbcu_oXc.js` đã nhúng. Font, artwork, app và third-party notices được giữ nguyên.
- Nền repo khi đóng gói: `813f4976ac95a336eed8f71ec77b3426eef6edf5`. Đây là base repo chứa gói, không phải commit tạo artifact ui-draft.
- [version.json](version.json) giữ nguồn/hash/trạng thái kiểm. Quy tắc Git trong thư mục giữ nguyên bytes PREVIEW, không tự chuyển CRLF/LF.

Kiểm file sau khi pull bằng PowerShell, không cần chạy ứng dụng:

```powershell
Get-Item ./docs/ui-walkthrough/PREVIEW.html | Select-Object Length
Get-FileHash ./docs/ui-walkthrough/PREVIEW.html -Algorithm SHA256
```

## Walkthrough trực tiếp

### S00 → W1: nguồn

Mở S00 từ launcher. Login/Library là giao diện demo, không OAuth thật. Có thể dùng checkpoint W1 để vào S03 empty; bấm **Xem dữ liệu mẫu**, chọn Câu 3 để đọc, **Xác nhận toàn bộ đề** rồi **Tiếp theo**. Chọn file nếu có chỉ dùng tên file, không upload hoặc parse nội dung.

### W2: cấu hình và tiến trình

S04 nhập **2**, xác nhận **5 câu/mã × 2 mã = 10 biến thể**, bấm **Tạo biến thể** và xác nhận. S05 tự nhận kết quả mô phỏng, đủ số rồi readiness mới bật **Bắt đầu duyệt**. Không cần sửa query để chạy và không tự sang S06 hoặc auto-approve. Tiến trình này không phải AI latency hoặc thời gian tiết kiệm đã đo.

Nếu cần phục hồi, mở checkpoint **S05 ready** từ launcher và giới thiệu đây là trạng thái chuẩn bị sẵn. Mở liên kết sẽ tạo lại state trong tab; không nhận là tiếp tục job trước đó.

### W3→W5: phát hiện lỗi, sửa và duyệt

Từ launcher, mở **Ca sửa chuẩn bị sẵn — S06**, chọn **Câu 3**, giữ **mã101**. Giới thiệu rõ đã đổi sang prepared correction checkpoint có **9 approval nạp sẵn**, không phải toàn bộ luồng trước vừa sinh và duyệt liên tục.

1. **W3:** B=C=`{3;4}`, counter9/10. Mở **Kiểm tra đáp án**, đối chiếu cảnh báo trùng và trạng thái chặn duyệt. Đóng popup rồi mở **Chỉnh sửa**.
2. **W4:** sửa riêng B thành `{2;6}`. Giữ C=`{3;4}`, key và lời giải. Chọn checkbox đối chiếu trong editor rồi **Lưu thay đổi**. Notice stale cho biết kết quả kiểm cũ hết hiệu lực; chưa approve và vẫn9/10.
3. **W5:** mở **Kiểm tra đáp án** lại, đọc B mới, key C và steps `(x−3)(x−4)=0`, nghiệm3hoặc4. Bấm **Duyệt biến thể** trực tiếp, không popup approve thứ hai. Sau khi model nhận đúng approval, popup đóng và counter10/10. Dừng ở S06; không tuyên bố đã chốt hoặc xuất PDF.

Nguồn ca này: `x²−5x+6=0`; mã101: `x²−7x+12=0`; mã102: `x²−9x+20=0`. Key theo option ID, không theo chữ C bất biến sau trộn. Chuỗi prepared có expected v2→v3 khi lưu; không hứa có badge version trên main panel. Approve v3 không chạy lại math validator và check có thể vẫn stale.

## Reset và xử lý gián đoạn

- Trong W3→W5, giữ cùng tab và không reload, đổi scenario hoặc bấm Tạo lại. Reload sẽ nạp lại fixture, mất phần vừa sửa.
- Nếu làm nhầm, về launcher rồi mở lại ca S06, chọn Câu3/101. Nói rõ bắt đầu lượt mới; không ghép hai lượt thành một run.
- Nếu S05 hoặc một thao tác lỗi, ghi actual và chuyển checkpoint đã chuẩn bị nếu dùng được; không nói bước lỗi đã đạt. Không có checkpoint sau lưu/approve được tạo giả để bỏ qua lỗi.
- Ưu tiên light, Chrome desktop, zoom100%; ghi viewport thực khi diễn tập. S07/S08 nằm trong app nhưng ngoài chuỗi chính của launcher; S07 còn provisional, dark experimental.

## Kiểm đã làm và còn chờ

Gói được kiểm tĩnh về bytes/hash nguồn–đích, tài nguyên nhúng, licenses, liên kết tương đối, Git attributes/ignore và phạm vi diff. Không build lại hoặc chạy test frontend/backend sản phẩm. Các báo cáo source ui-draft trước đó không tự là native pass của gói chia sẻ này.

| Smoke test trực tiếp trên Chrome | Kết quả lúc đóng gói |
|---|---|
| Mở từ folder mới, S00 đọc được font/artwork | Chưa kiểm |
| S04→S05 tự tiến, readiness riêng, nút vào S06 | Chưa kiểm |
| W3 duplicate warning và chặn approve | Chưa kiểm |
| W4 sửa B/lưu/stale/9/10 | Chưa kiểm |
| W5 review lại/approve trực tiếp/10/10 | Chưa kiểm |
| Tab/Enter/Esc/focus, scroll và công thức | Chưa kiểm |

Người trực tiếp chạy ghi browser/version, ngày, viewport/zoom, actual và lỗi trước khi xác nhận sẵn sàng demo. Công cụ trước bị chặn PREVIEWfile://; không dùng server, localhost, CDP hoặc surface khác để vượt chặn. Không có yêu cầu ảnh/video bắt buộc cho hướng walkthrough live này.

## Giới hạn tuyên bố

Đây là preview thiết kế bằng dữ liệu mẫu và state trong bộ nhớ tab. Chưa auth/upload/parser/AI/lưu server/xuất PDF thật. Không gọi ca chuẩn bị là output AI hoặc teacher approval thực; không suy độ khó tương đương, coverage toàn Đại số, accuracy hay time saving từ ví dụ. Giữ thông báo licenses nhúng khi phân phối lại PREVIEW.

# Stage1 native regression — F01/F04

Từ `frontend/`, chạy `npm.cmd run dev -- --host 127.0.0.1`, mở
`http://127.0.0.1:3000/test-support/stage1-native/index.html`.
Dùng cổng Vite báo nếu 3000 đang có Docker. Trang không cần đăng nhập/config/key:
Auth và Axios adapter được mock riêng trong entry này; không có request cloud.
Dialog/panel/controller/service là code sản phẩm import trực tiếp, không dùng dialog stub.
Trang không được import bởi App hoặc production entry. Node tests không chạy bài native này.

1. Bấm **Chạy focus-out / lifecycle**. Tất cả assertions phải PASS: modal native mở,
   focus button/input nền bị từ chối, rerender không thoát focus, close/unmount trả
   quyền focus nền và unmount không gọi callback nghiệp vụ. Report ghi expected/actual.
2. Bấm **Mở dialog để kiểm phím**. Dùng Tab/Shift+Tab vài vòng (chỉ trong modal),
   Escape thật: đóng và trả focus nút mở. Mở lại, bấm Đóng; kiểm lại không kẹt nền.
   Bài tự động không dispatch keyboard event giả để nhận Escape native PASS.
3. Panel phía dưới: nhập nháp `Kiểm F01`, bấm Nạp nguồn một lần → fixture422.
   Bấm **Chọn tệp đã sửa** bằng chuột/bàn phím thật. Picker phải mở ngay; Hủy.
   Chuyển Nhập trực tiếp: nháp còn; source A/keyA còn; request POST vẫn1.
   Nạp lần nữa rồi chuyểntext trong dialog: textarea nhận focus, không có POST thêm.
4. Mở lại dialog, chọn một MD/TeX/DOCX. Filename đổi, chưa POST; Nạp chủ động mới
   tăng POST và trả422. Sửa file local rồi chọn lại cùng file qua dialog, filename
   vẫn được nhận; không tự gửi. Hủy picker phải giữ file cũ/nháp/source.
5. Lưu report, kết quả manual từng mục, git HEAD và diff/code hash nếu working tree
   chưa commit, browser/version/OS/ngày. Report tự động không xác nhận manual PASS.

Để kiểm bài test thực sự phát hiện baseline, xuất component cũ tạm vào cùng thư mục:
`git show 1fc501c:frontend/src/features/stage1-ingestion/IncompleteContentDialog.jsx`
và lưu UTF-8 thành `baseline.local.jsx`. Mở URL thêm `?baseline=1`, chạy mục1:
native-modal/focus-out phải FAIL. Xóa file tạm sau kiểm, không stage/commit bản sao cũ.
Candidate luôn chạy URL không có query và import code thật hiện tại.

## Browser matrix / giới hạn

| Môi trường | Bằng chứng trước harness | Kết quả harness mới |
|---|---|---|
| Chrome156 / Windows10,04/11/2026 | Author fixture và user Docker đã báo đạt native focus/picker/Hủy | Author chạy candidate8/8assertions PASS; baseline1fc501c FAIL native-modal và2focus-out. ShiftTab/Escape trảfocus, picker từtext phát native filechooser, chuyểntext giữnháp/focus và không POST thêm đạt. Chọn file/Hủy OS/same-file chưa chạy lại trong harness mới. |
| Safari / macOS, Safari / iOS | Chưa kiểm | Not run |
| Firefox / Edge | Chưa kiểm | Not run |

Matrix trên là bằng chứng kiểm, chưa là quyết định hỗ trợ sản phẩm. F04 non-blocking:
Safari/iOS chưa kiểm không chứng minh có bug hoặc Chrome-only. Nếu owner đưa Safari/iOS
vào acceptance, cần native thiết bị/browser tương ứng; Chromium không chứng minh WebKit/iOS.
Fixture422 không phải backend/cloud, DB/Storage audit hoặc end-to-end AI/PDF.

## TASK-204 — xác nhận nguồn và F5

Mở `/test-support/stage1-native/confirmation.html?case=retry` trong một tab mới.
Đây là Stage 1 thật, với Auth/HTTP giả lập và màn đích Stage 2 chỉ để kiểm ID bàn giao.

1. Tab đến ô nhập, điền đề rồi dùng bàn phím bấm **Nạp nguồn**. Kiểm preview đổi từ A sang B sau GET.
2. Dùng bàn phím kích hoạt **Xác nhận đề gốc và tiếp tục**. Lần đầu mất response, màn vẫn Stage 1.
3. F5. Kiểm báo cáo vẫn có đúng một POST confirm và có GET phiên/artifact để đối soát.
4. Kích hoạt **Thử xác nhận lại**. Kiểm `Retry giữ key: true` và đúng ID ở Stage 2 fixture.
5. Mở tab mới với `?case=committed`. Sau lần confirm đầu mất response, F5 phải chuyển Stage 2
   ngay từ GET và số POST confirm vẫn là một.

Fixture dùng trạng thái mô phỏng riêng trong tab, không gọi backend, Supabase hay AI.

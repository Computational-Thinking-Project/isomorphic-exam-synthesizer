# CloneSessionModal — TASK-103b

Component modal nhân bản một phiên đề thi hiện có sang một phiên mới độc lập ở trạng thái `draft`.

## Đặc tả Props (Tương thích handoff từ TV1 & TV3)

| Prop | Kiểu dữ liệu | Bắt buộc | Mô tả |
|---|---|---|---|
| `isOpen` | `boolean` | Có | Điều khiển hiển thị modal (`true` = mở, `false` = đóng) |
| `session` | `Object` | Có | Phiên nguồn được chọn từ `onClone(session)` trên `DashboardSessionCard` |
| `onClose` | `Function` | Có | Callback khi bấm Hủy, click ra ngoài hoặc bấm ESC |
| `onSuccess` | `Function` | Có | Callback khi nhân bản thành công: `onSuccess(newSession)` |
| `cloneFn` | `Function` | Không | Hàm gọi API clone (mặc định là `mockCloneSession`). **Quy ước:** hàm gọi `POST /api/sessions/{id}/clone` gửi kèm body `{ "new_title": title }`, trả về trực tiếp đối tượng phiên mới (unwrap `response.data` trước khi trả về). |

## Điểm tích hợp vào `DashboardRoute.jsx` (TV1)

```jsx
import { useState } from 'react';
import CloneSessionModal from './CloneSessionModal.jsx';

export default function DashboardRoute() {
  const [cloningSession, setCloningSession] = useState(null);

  return (
    <>
      <DashboardPage
        loadSessions={listDashboardSessions}
        onCreate={...}
        onOpen={...}
        onClone={(session) => setCloningSession(session)}
      />

      <CloneSessionModal
        isOpen={Boolean(cloningSession)}
        session={cloningSession}
        onClose={() => setCloningSession(null)}
        onSuccess={(newSession) => {
          setCloningSession(null);
          // Điều hướng tới phiên mới hoặc làm mới danh sách
          console.log('Phiên mới đã tạo:', newSession);
        }}
      />
    </>
  );
}
```

## Tính năng bảo vệ & UX
1. **Gợi ý tiêu đề tự động**: Điền sẵn `[Bản sao] ${session.title}` và auto-focus/select text.
2. **Focus Trap & Khôi phục vị trí chọn**:
   - Khi modal mở, lưu phần tử đã kích hoạt (`triggerElementRef`).
   - Phím `Tab` và `Shift + Tab` bị khóa vòng lặp bên trong modal, không cho nhảy ra các nút Dashboard phía sau.
   - Khi modal đóng, tự động đưa focus trở lại nút kích hoạt trên Dashboard.
3. **Chống Double Submission**: Vô hiệu hóa nút và input khi đang gọi API, hiển thị spinner xoay.
4. **Chống Stale Request / Race Condition & Hủy kết quả khi đóng/ẩn**:
   - Sử dụng `activeRequestIdRef` và kiểm tra đồng bộ trong render lẫn `useEffect`.
   - Nếu người dùng chủ động đóng modal (bấm Hủy, ESC, backdrop) hoặc component cha đặt `isOpen=false` / đổi sang phiên khác trong lúc đang chờ máy chủ phản hồi, toàn bộ kết quả thành công hoặc lỗi mạng muộn sẽ bị bỏ qua hoàn toàn: KHÔNG gọi `onSuccess`, KHÔNG gọi `onClose` thừa và KHÔNG mở khóa nhầm cờ đang gửi của phiên mới.
5. **Giữ modal khi lỗi**: Khi API thất bại trong khi modal vẫn mở, không đóng modal mà hiển thị thông báo lỗi trong alert màu đỏ để người dùng sửa tiêu đề và bấm thử lại.

## Kiểm thử Unit Test
Toàn bộ 23/23 test vượt qua với `npm test`, bao gồm:
- 5 test service `cloneMock.test.js`
- 14 test component `CloneSessionModal.test.js` (render, focus trap, aria, ESC handling, gửi form, double-submit, hủy request khi Hủy, hủy request khi trang cha đặt `isOpen=false`, hủy lỗi máy chủ muộn, unmount khi đang chờ, chuyển phiên A -> B giữ khóa khi A thành công/lỗi, xử lý lỗi khi mở)
- 3 test store `authStore.test.js`
- 1 loader test `test-loader.mjs`

## Xem thử giao diện (Standalone Preview)
Chạy `npm run dev` trong `frontend/` và truy cập `/clone-modal-preview.html`.

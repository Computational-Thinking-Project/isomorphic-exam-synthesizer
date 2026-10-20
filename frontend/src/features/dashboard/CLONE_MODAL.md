# CloneSessionModal — TASK-103b

Component modal nhân bản một phiên đề thi hiện có sang một phiên mới độc lập ở trạng thái `draft`.

## Đặc tả Props (Tương thích handoff từ TV1 & TV3)

| Prop | Kiểu dữ liệu | Bắt buộc | Mô tả |
|---|---|---|---|
| `isOpen` | `boolean` | Có | Điều khiển hiển thị modal (`true` = mở, `false` = đóng) |
| `session` | `Object` | Có | Phiên nguồn được chọn từ `onClone(session)` trên `DashboardSessionCard` |
| `onClose` | `Function` | Có | Callback khi bấm Hủy, click ra ngoài hoặc bấm ESC |
| `onSuccess` | `Function` | Có | Callback khi nhân bản thành công: `onSuccess(newSession)` |
| `cloneFn` | `Function` | Không | Hàm gọi API clone (mặc định là `mockCloneSession`). **Quy ước:** hàm trả về trực tiếp đối tượng phiên mới (unwrap `response.data` trước khi trả về). |

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
4. **Chống Stale Request / Race Condition**: Mỗi lượt submit và mỗi lượt đổi phiên được đánh dấu bằng `requestId`. Nếu người dùng đổi sang phiên khác hoặc unmount trước khi server phản hồi, kết quả cũ sẽ bị bỏ qua hoàn toàn, không gây đóng nhầm modal mới hoặc báo lỗi chéo.
5. **Giữ modal khi lỗi**: Khi API thất bại, không đóng modal mà hiển thị thông báo lỗi trong alert màu đỏ để người dùng sửa tiêu đề và bấm thử lại.

## Xem thử giao diện (Standalone Preview)
Chạy `npm run dev` trong `frontend/` và truy cập `/clone-modal-preview.html`.

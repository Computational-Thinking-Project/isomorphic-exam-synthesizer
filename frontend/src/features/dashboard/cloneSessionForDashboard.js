import axios from 'axios';
import { cloneSession } from '../../services/sessions.js';
import { classifyAuthError } from '../../services/authErrors.js';

const expiredMessage = 'Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.';
const httpMessages = new Map([
  [401, expiredMessage],
  [403, 'Bạn không có quyền nhân bản phiên này.'],
  [404, 'Không tìm thấy phiên nguồn hoặc bạn không có quyền truy cập. Hãy tải lại danh sách.'],
  [422, 'Thông tin nhân bản không hợp lệ. Vui lòng kiểm tra tiêu đề.'],
  [429, 'Bạn thao tác quá nhanh. Hãy chờ một chút rồi thử lại.'],
]);

// Chỉ chuyển thông báo cho UI; token/401 và chống kết quả cũ thuộc API client chung.
export async function cloneSessionForDashboard(sessionId, title) {
  try {
    return await cloneSession(sessionId, title);
  } catch (cause) {
    if (axios.isCancel(cause)) throw cause;

    let message;
    if (axios.isAxiosError(cause)) {
      const status = cause.response?.status;
      message = !status || status >= 500
        ? 'Chưa xác nhận được kết quả nhân bản. Hãy tải lại trang để kiểm tra danh sách trước khi thử lại.'
        : httpMessages.get(status) ?? 'Không thể nhân bản phiên lúc này. Vui lòng thử lại.';
    } else {
      const kind = classifyAuthError(cause);
      if (kind === 'expired') {
        message = expiredMessage;
      } else if (kind === 'temporary') {
        message = 'Chưa thể kiểm tra phiên đăng nhập. Vui lòng kiểm tra kết nối rồi thử lại.';
      } else {
        // Giữ thông báo kiểm input/phản hồi do service tạo, gồm lời nhắc kiểm danh sách.
        throw cause;
      }
    }

    throw new Error(message, { cause });
  }
}

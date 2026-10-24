/**
 * Mô phỏng API nhân bản phiên làm việc (clone session).
 * Dùng cho phát triển giao diện trước khi nối endpoint thực tế của TV3.
 *
 * @param {string} sessionId - ID phiên gốc cần nhân bản
 * @param {string} newTitle - Tiêu đề mới của phiên nhân bản
 * @returns {Promise<Object>} Trả về đối tượng phiên mới đã được clone
 */
export async function mockCloneSession(sessionId, newTitle) {
  // Giả lập độ trễ mạng để kiểm tra trạng thái loading và vô hiệu hóa nút bấm
  await new Promise((resolve) => setTimeout(resolve, 500));

  if (!sessionId) {
    throw new Error('Mã phiên gốc không hợp lệ.');
  }

  const trimmedTitle = typeof newTitle === 'string' ? newTitle.trim() : '';
  if (!trimmedTitle) {
    throw new Error('Tiêu đề phiên mới không được để trống.');
  }

  // Hỗ trợ kiểm thử kịch bản lỗi khi tiêu đề chứa từ khóa 'error'
  if (trimmedTitle.toLowerCase().includes('error')) {
    throw new Error('Lỗi máy chủ giả lập: Không thể nhân bản phiên lúc này. Vui lòng thử lại.');
  }

  return {
    id: `mock-session-clone-${Date.now()}`,
    title: trimmedTitle,
    subject: 'Toán',
    status: 'draft',
    created_at: new Date().toISOString(),
    source_session_id: sessionId,
  };
}

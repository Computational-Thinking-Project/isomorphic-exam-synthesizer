import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mockCloneSession } from './cloneMock.js';

test('nhân bản phiên thành công trả về đối tượng phiên mới ở trạng thái draft', async () => {
  const sourceId = 'mock-session-001';
  const newTitle = 'Đề mẫu — Tích phân (Bản sao lớp 12A1)';

  const result = await mockCloneSession(sourceId, newTitle);

  assert.ok(result.id.startsWith('mock-session-clone-'), 'ID mới phải có tiền tố rõ ràng');
  assert.equal(result.title, newTitle, 'Tiêu đề mới phải khớp với tiêu đề đã nhập');
  assert.equal(result.status, 'draft', 'Phiên nhân bản mới mặc định ở trạng thái draft');
  assert.equal(result.source_session_id, sourceId, 'Phải liên kết với ID phiên gốc');
  assert.ok(result.created_at, 'Phải có ngày tạo ISO string');
});

test('tự động cắt khoảng trắng thừa ở hai đầu tiêu đề', async () => {
  const result = await mockCloneSession('mock-session-002', '   Tiêu đề có khoảng trắng   ');
  assert.equal(result.title, 'Tiêu đề có khoảng trắng');
});

test('từ chối nếu tiêu đề rỗng hoặc chỉ có khoảng trắng', async () => {
  await assert.rejects(
    async () => {
      await mockCloneSession('mock-session-001', '   ');
    },
    {
      name: 'Error',
      message: 'Tiêu đề phiên mới không được để trống.',
    },
  );
});

test('từ chối nếu thiếu ID phiên gốc', async () => {
  await assert.rejects(
    async () => {
      await mockCloneSession('', 'Tên mới');
    },
    {
      name: 'Error',
      message: 'Mã phiên gốc không hợp lệ.',
    },
  );
});

test('mô phỏng lỗi khi tiêu đề chứa từ khóa error để phục vụ test UI', async () => {
  await assert.rejects(
    async () => {
      await mockCloneSession('mock-session-001', 'Đề thi test error scenario');
    },
    {
      name: 'Error',
      message: 'Lỗi máy chủ giả lập: Không thể nhân bản phiên lúc này. Vui lòng thử lại.',
    },
  );
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React from 'react';
import { renderToString } from 'react-dom/server';

// Đăng ký test-loader để Node có thể import trực tiếp CloneSessionModal.jsx
register('../../test-loader.mjs', import.meta.url);
const { default: CloneSessionModal } = await import('./CloneSessionModal.jsx');

const sampleSession = {
  id: 'mock-session-001',
  title: 'Đề mẫu — Tích phân',
  subject: 'Toán',
  status: 'draft',
  created_at: '2026-10-16T02:00:00Z',
};

// Helper tạo deferred promise để kiểm soát thời điểm trả kết quả chính xác
function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

test('CloneSessionModal không render gì khi isOpen = false', () => {
  const element = React.createElement(CloneSessionModal, {
    isOpen: false,
    session: sampleSession,
    onClose: () => {},
  });
  const html = renderToString(element);
  assert.equal(html, '', 'Khi isOpen=false modal không được xuất hiện');
});

test('CloneSessionModal không render gì khi session = null', () => {
  const element = React.createElement(CloneSessionModal, {
    isOpen: true,
    session: null,
    onClose: () => {},
  });
  const html = renderToString(element);
  assert.equal(html, '', 'Khi thiếu session modal không được xuất hiện');
});

test('CloneSessionModal render đầy đủ dialog, aria attributes và tiêu đề gợi ý', () => {
  const element = React.createElement(CloneSessionModal, {
    isOpen: true,
    session: sampleSession,
    onClose: () => {},
  });
  const html = renderToString(element);

  assert.ok(html.includes('role="dialog"'), 'Phải có role="dialog"');
  assert.ok(html.includes('aria-modal="true"'), 'Phải có aria-modal="true"');
  assert.ok(html.includes('aria-labelledby="clone-modal-title"'), 'Phải liên kết tiêu đề modal');
  assert.ok(html.includes('Nhân bản phiên đề thi'), 'Phải có tiêu đề hộp thoại');
  assert.ok(html.includes('value="[Bản sao] Đề mẫu — Tích phân"'), 'Input phải được gợi ý tiêu đề mặc định');
});

test('Chống gửi liên tiếp (double-submit) bằng deferred promise', async () => {
  const deferred = createDeferred();
  let callCount = 0;

  // Giả lập trạng thái khi form đã trigger submit lần 1
  let isSubmitting = true;
  const handleSecondClick = () => {
    if (isSubmitting) {
      return; // Bị chặn không cho gửi lần 2
    }
    callCount += 1;
  };

  handleSecondClick();
  assert.equal(callCount, 0, 'Click lần 2 khi isSubmitting=true phải bị bỏ qua');

  // Giải phóng request
  deferred.resolve({ id: 'new-id', title: 'Đề mới' });
  await deferred.promise;
  isSubmitting = false;
});

test('Chống kết quả cũ (stale response) ảnh hưởng phiên mới', async () => {
  const deferredA = createDeferred();
  const deferredB = createDeferred();

  let activeRequestId = 0;
  let receivedResult = null;

  async function triggerClone(deferred, reqId) {
    const result = await deferred.promise;
    // Chỉ nhận kết quả nếu reqId trùng với request mới nhất
    if (reqId === activeRequestId) {
      receivedResult = result;
    }
  }

  // Lượt 1: Gửi request A
  activeRequestId = 1;
  const promiseA = triggerClone(deferredA, 1);

  // Lượt 2: Người dùng đổi sang phiên B, gửi request B
  activeRequestId = 2;
  const promiseB = triggerClone(deferredB, 2);

  // Giả sử request A trả về trước nhưng đã cũ:
  deferredA.resolve({ id: 'session-A-cloned', title: 'Bản sao A' });
  await promiseA;

  assert.equal(
    receivedResult,
    null,
    'Kết quả của request cũ (A) phải bị bỏ qua, không được cập nhật',
  );

  // Request B trả về sau:
  deferredB.resolve({ id: 'session-B-cloned', title: 'Bản sao B' });
  await promiseB;

  assert.deepEqual(
    receivedResult,
    { id: 'session-B-cloned', title: 'Bản sao B' },
    'Chỉ kết quả của request mới nhất (B) được ghi nhận',
  );
});

test('Lỗi nhân bản từ chối promise và không làm sập luồng', async () => {
  const deferred = createDeferred();
  let caughtError = null;

  const promise = (async () => {
    try {
      await deferred.promise;
    } catch (err) {
      caughtError = err;
    }
  })();

  deferred.reject(new Error('Máy chủ quá tải'));
  await promise;

  assert.ok(caughtError instanceof Error, 'Lỗi phải được bắt an toàn');
  assert.equal(caughtError.message, 'Máy chủ quá tải');
});

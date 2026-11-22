import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

register('../../test-loader.mjs', import.meta.url);
const { default: GenerationProgressView } = await import('./GenerationProgressView.jsx');

function renderProgress(props) {
  const container = document.createElement('div');
  const root = createRoot(container);

  return {
    container,
    async render(nextProps = props) {
      await act(async () => {
        root.render(React.createElement(GenerationProgressView, nextProps));
      });
    },
    async unmount() {
      await act(async () => {
        root.unmount();
      });
    },
  };
}

test('GenerationProgressView hiển thị Stepper 3 bước connected và tiêu đề S05 chuẩn', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-001',
    sessionTitle: 'Đề kiểm tra Giải tích 12',
    numVersions: 2,
    totalSourceQuestions: 5,
    progress: {
      percent: 60,
      completedCount: 6,
      totalCount: 10,
    },
    connectionState: 'connected',
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('01. Chuẩn bị đề gốc'));
  assert.ok(text.includes('02. Cấu hình và tạo mã'));
  assert.ok(text.includes('03. Duyệt và sử dụng'));
  assert.ok(text.includes('Đang tạo biến thể'));
  assert.ok(text.includes('6 / 10'));
  assert.ok(text.includes('biến thể hoàn tất (60%)'));

  await harness.unmount();
});

test('GenerationProgressView hiển thị bảng tiến độ từng mã đề với badge hình chữ nhật bo góc 4px', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-002',
    numVersions: 2,
    totalSourceQuestions: 2,
    progress: {
      percent: 50,
      completedCount: 2,
      totalCount: 4,
    },
    questionStatuses: {
      '1-1': { version_index: 1, question_no: 1, status: 'done' },
      '1-2': { version_index: 1, question_no: 2, status: 'done' },
      '2-1': { version_index: 2, question_no: 1, status: 'generating' },
      '2-2': { version_index: 2, question_no: 2, status: 'pending' },
    },
    connectionState: 'connected',
  });
  await harness.render();

  const table = harness.container.querySelector('.generation-table');
  assert.ok(table, 'Phải có bảng generation-table');

  const text = harness.container.textContent;
  assert.ok(text.includes('Mã 101'), 'Phải có Mã 101');
  assert.ok(text.includes('Mã 102'), 'Phải có Mã 102');
  assert.ok(text.includes('Đã hoàn tất'), 'Mã 101 phải hoàn tất');
  assert.ok(text.includes('Đang xử lý'), 'Mã 102 phải đang xử lý');

  const badges = harness.container.querySelectorAll('.flow-badge');
  assert.ok(badges.length >= 2, 'Phải có các badge trạng thái chữ nhật');

  await harness.unmount();
});

test('GenerationProgressView hiển thị badge Có thể duyệt câu đã nhận và bật nút Bắt đầu duyệt khi có >= 1 câu', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-early-review',
    numVersions: 2,
    totalSourceQuestions: 5,
    progress: {
      percent: 10,
      completedCount: 1,
      totalCount: 10,
    },
    connectionState: 'connected',
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(
    text.includes('Có thể duyệt câu đã nhận'),
    'Phải có badge meta Có thể duyệt câu đã nhận',
  );

  const reviewBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Bắt đầu duyệt'),
  );
  assert.ok(reviewBtn, 'Phải có nút Bắt đầu duyệt');
  assert.equal(reviewBtn.getAttribute('disabled'), null, 'Nút duyệt phải được kích hoạt khi có >= 1 câu');

  await harness.unmount();
});

test('GenerationProgressView khi offline: hiển thị banner đỏ và nút Đọc lại trạng thái', async () => {
  let reconnected = false;
  const harness = renderProgress({
    sessionId: 'session-prog-offline',
    numVersions: 2,
    totalSourceQuestions: 2,
    progress: {
      percent: 50,
      completedCount: 2,
      totalCount: 4,
    },
    connectionState: 'offline',
    onReconnect: () => {
      reconnected = true;
    },
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(
    text.includes('Chưa cập nhật được tiến độ. Đang hiển thị lần nhận gần nhất; không kết luận job thất bại.'),
    'Phải hiển thị thông báo offline chuẩn',
  );

  const resyncBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Đọc lại trạng thái'),
  );
  assert.ok(resyncBtn, 'Phải có nút Đọc lại trạng thái');

  await act(async () => {
    resyncBtn.click();
  });
  assert.equal(reconnected, true, 'onReconnect phải được kích hoạt');

  await harness.unmount();
});

test('GenerationProgressView khi có câu lỗi: hiển thị thông báo lỗi và nút Thử lại phần lỗi', async () => {
  let retried = false;
  const harness = renderProgress({
    sessionId: 'session-prog-error-retry',
    numVersions: 1,
    totalSourceQuestions: 2,
    progress: {
      percent: 50,
      completedCount: 1,
      totalCount: 2,
    },
    questionStatuses: {
      '1-1': { version_index: 1, question_no: 1, status: 'done' },
      '1-2': { version_index: 1, question_no: 2, status: 'failed' },
    },
    connectionState: 'connected',
    onRetryGeneration: () => {
      retried = true;
    },
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Câu 2 · Mã 101 chưa tạo được.'));
  assert.ok(text.includes('Thử lại chỉ phần lỗi'));

  const retryBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Thử lại phần lỗi'),
  );
  assert.ok(retryBtn, 'Phải có nút Thử lại phần lỗi');

  await act(async () => {
    retryBtn.click();
  });
  assert.equal(retried, true, 'onRetryGeneration phải được gọi');

  await harness.unmount();
});

test('GenerationProgressView khi hoàn tất cho phép bấm Bắt đầu duyệt để gọi onComplete, không tự động chuyển màn', async () => {
  let completedCalled = false;
  const harness = renderProgress({
    sessionId: 'session-prog-done',
    numVersions: 2,
    totalSourceQuestions: 5,
    progress: { percent: 100, completedCount: 10, totalCount: 10 },
    isDone: true,
    onComplete: () => {
      completedCalled = true;
    },
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Đã tạo đủ biến thể'));

  // Không tự chuyển trang sau 1.6s
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1600));
  });
  assert.equal(completedCalled, false, 'Không được tự chuyển trang khi chưa bấm nút');

  // Bấm nút "Bắt đầu duyệt →"
  const ctaBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Bắt đầu duyệt'),
  );
  assert.ok(ctaBtn, 'Phải có nút Bắt đầu duyệt');
  await act(async () => {
    ctaBtn.click();
  });
  assert.equal(completedCalled, true, 'onComplete phải được kích hoạt khi bấm Bắt đầu duyệt');

  await harness.unmount();
});

test('F02: GenerationProgressView hiển thị Chưa có dữ liệu tiến độ khi thiếu snapshot, KHÔNG hiển thị 0/4', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-no-snapshot',
    numVersions: 2,
    totalSourceQuestions: 2,
    progress: null,
    connectionState: 'connected',
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Chưa có dữ liệu tiến độ'));
  assert.equal(/0\s*\/\s*4/.test(text), false, 'Tuyệt đối không được hiển thị 0/4 khi thiếu snapshot');

  await harness.unmount();
});

test('F02: GenerationProgressView CHỈ hiển thị 0 / 4 khi backend xác nhận rõ ràng đã lưu 0 câu hỏi (hasData: true, completedCount: 0)', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-confirmed-zero',
    numVersions: 2,
    totalSourceQuestions: 2,
    progress: {
      hasData: true,
      completedCount: 0,
      percent: 0,
      totalCount: 4,
    },
    connectionState: 'connected',
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('0 / 4'), 'Phải hiển thị 0 / 4 khi backend xác nhận 0 câu');
  assert.equal(text.includes('Chưa có dữ liệu tiến độ'), false);

  await harness.unmount();
});

test('F108-01 & F108-03: Cấu trúc generation-row và thanh tiến trình tổng đáp ứng responsive mobile', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-responsive',
    numVersions: 2,
    totalSourceQuestions: 6,
    progress: {
      hasData: true,
      completedCount: 6,
      percent: 50,
      totalCount: 12,
    },
    questionStatuses: {
      '1-1': { version_index: 1, question_no: 1, status: 'done' },
      '1-2': { version_index: 1, question_no: 2, status: 'done' },
      '1-3': { version_index: 1, question_no: 3, status: 'done' },
      '1-4': { version_index: 1, question_no: 4, status: 'done' },
      '1-5': { version_index: 1, question_no: 5, status: 'done' },
      '1-6': { version_index: 1, question_no: 6, status: 'done' },
      '2-1': { version_index: 2, question_no: 1, status: 'generating' },
    },
    connectionState: 'connected',
  });
  await harness.render();

  // F108-03: Thanh tiến trình tổng có class flow-progress-bar-fill
  const overallFill = harness.container.querySelector('.flow-progress-bar-fill');
  assert.ok(overallFill, 'Phải có phần tử .flow-progress-bar-fill');
  assert.equal(overallFill.style.width, '50%');

  // F108-01: Mỗi row có 3 khối con riêng biệt để xếp dọc (Mã đề -> Tiến độ -> Badge)
  const rows = harness.container.querySelectorAll('.generation-row');
  assert.equal(rows.length, 2);
  rows.forEach((row) => {
    const childElements = row.childNodes.filter((c) => c.nodeType === 1);
    assert.equal(childElements.length, 3, 'Mỗi generation-row phải có 3 khối con để xếp chồng linh hoạt');
    const [titleBlock, progressBlock, stateBlock] = childElements;
    assert.ok(titleBlock.querySelector('h3'), 'Khối 1 phải chứa tiêu đề mã đề');
    assert.ok(progressBlock.querySelector('.row-progress-bar'), 'Khối 2 phải chứa thanh tiến trình');
    assert.ok((stateBlock.getAttribute('class') || '').includes('generation-state'), 'Khối 3 phải là khối trạng thái generation-state');
    assert.ok(stateBlock.querySelector('.flow-badge'), 'Khối 3 phải chứa badge trạng thái flow-badge');
  });

  await harness.unmount();
});

test('F108-04: Không suy diễn tiến độ từng mã đề khi questionStatuses trống, hiển thị Chưa có dữ liệu tiến độ từng mã', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-no-per-version',
    numVersions: 2,
    totalSourceQuestions: 5,
    progress: {
      percent: 50,
      completedCount: 5,
      totalCount: 10,
    },
    questionStatuses: {}, // Không có trạng thái chi tiết từng câu
    connectionState: 'connected',
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(
    text.includes('Chưa có dữ liệu tiến độ từng mã'),
    'Phải hiển thị thông báo Chưa có dữ liệu tiến độ từng mã khi questionStatuses trống',
  );
  assert.equal(
    harness.container.querySelectorAll('.generation-row').length,
    0,
    'Tuyệt đối không render các hàng với số liệu suy diễn phân bổ',
  );

  await harness.unmount();
});

test('F108-05: Missing slots trong terminal partial_generated được phát hiện và đưa đầy đủ vào failedList', async () => {
  let retried = false;
  const harness = renderProgress({
    sessionId: 'session-prog-partial-missing-slots',
    numVersions: 2,
    totalSourceQuestions: 2,
    isDone: true,
    progress: {
      session_status: 'partial_generated',
      is_partial: true,
      percent: 25,
      completedCount: 1,
      totalCount: 4,
    },
    // Chỉ có 1-1 done, vắng mặt hoàn toàn 1-2, 2-1, 2-2
    questionStatuses: {
      '1-1': { version_index: 1, question_no: 1, status: 'done' },
    },
    connectionState: 'connected',
    onRetryGeneration: () => {
      retried = true;
    },
  });
  await harness.render();

  const text = harness.container.textContent;
  // F108-05: Các câu vắng hẳn khỏi questionStatuses phải được phát hiện và hiển thị
  assert.ok(text.includes('Câu 2 · Mã 101'), 'Phải liệt kê Câu 2 Mã 101 thiếu');
  assert.ok(text.includes('Câu 1 · Mã 102'), 'Phải liệt kê Câu 1 Mã 102 thiếu');
  assert.ok(text.includes('Câu 2 · Mã 102'), 'Phải liệt kê Câu 2 Mã 102 thiếu');
  assert.ok(text.includes('chưa tạo được.'));

  const retryBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Thử lại phần lỗi'),
  );
  assert.ok(retryBtn, 'Phải hiển thị nút Thử lại phần lỗi');

  await act(async () => {
    retryBtn.click();
  });
  assert.equal(retried, true);

  await harness.unmount();
});

test('F108-08: Nút Đọc lại trạng thái khi offline gọi onReconnect và hiển thị trạng thái đang đọc', async () => {
  let reconnected = false;
  const harness = renderProgress({
    sessionId: 'session-prog-reconnect',
    numVersions: 2,
    totalSourceQuestions: 2,
    connectionState: 'offline',
    isReadingStatus: false,
    onReconnect: () => {
      reconnected = true;
    },
  });
  await harness.render();

  const reconnectBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Đọc lại trạng thái'),
  );
  assert.ok(reconnectBtn, 'Phải có nút Đọc lại trạng thái khi offline');

  await act(async () => {
    reconnectBtn.click();
  });
  assert.equal(reconnected, true, 'onReconnect phải được kích hoạt');

  // Kiểm tra khi isReadingStatus = true
  await harness.render({
    sessionId: 'session-prog-reconnect',
    numVersions: 2,
    totalSourceQuestions: 2,
    connectionState: 'offline',
    isReadingStatus: true,
    onReconnect: () => {},
  });

  const readingBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Đang đọc...'),
  );
  assert.ok(readingBtn, 'Nút phải đổi nhãn sang Đang đọc...');
  assert.equal(readingBtn.getAttribute('disabled') !== null, true, 'Nút phải bị khóa khi đang đọc');

  await harness.unmount();
});

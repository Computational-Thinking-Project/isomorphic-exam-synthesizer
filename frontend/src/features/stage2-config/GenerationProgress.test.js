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

test('GenerationProgressView hiển thị đúng thanh tiến trình và số lượng hoàn thành', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-001',
    sessionTitle: 'Đề kiểm tra Đại số 12',
    numVersions: 2,
    totalSourceQuestions: 5,
    progress: {
      percent: 60,
      completedCount: 6,
      totalCount: 10,
      message: 'Đang xử lý mã đề 2',
      estimatedSeconds: 18,
    },
    connectionState: 'connected',
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('60%'), 'Phải hiển thị 60%');
  assert.ok(text.includes('6 / 10'), 'Phải hiển thị 6 / 10 câu hỏi');
  assert.ok(text.includes('Kết nối thời gian thực'), 'Phải có badge kết nối thời gian thực');
  assert.ok(text.includes('Ước tính: ~18s') || text.includes('~18s'), 'Phải hiển thị thời gian ước tính');

  await harness.unmount();
});

test('GenerationProgressView hiển thị chính xác 5 trạng thái thân thiện của từng câu hỏi', async () => {
  const questionStatuses = {
    '1-1': { version_index: 1, question_no: 1, status: 'analyzing', message: 'Đang phân tích cấu trúc' },
    '1-2': { version_index: 1, question_no: 2, status: 'generating', message: 'Đang soạn nội dung' },
    '1-3': { version_index: 1, question_no: 3, status: 'validating', message: 'Đang kiểm tra lời giải' },
    '1-4': { version_index: 1, question_no: 4, status: 'retrying', message: 'Đang tinh chỉnh đáp án' },
    '1-5': { version_index: 1, question_no: 5, status: 'done', message: 'Đã hoàn thành' },
  };

  const harness = renderProgress({
    sessionId: 'session-prog-002',
    numVersions: 1,
    totalSourceQuestions: 5,
    questionStatuses,
    connectionState: 'connected',
  });
  await harness.render();

  const text = harness.container.textContent;
  // Kiểm tra đủ cả 5 trạng thái theo đúng yêu cầu người dùng
  assert.ok(text.includes('Đang phân tích'), '1. Phải có trạng thái Đang phân tích');
  assert.ok(text.includes('Đang soạn nội dung'), '2. Phải có trạng thái Đang soạn nội dung');
  assert.ok(text.includes('Đang kiểm tra'), '3. Phải có trạng thái Đang kiểm tra');
  assert.ok(text.includes('Đang tinh chỉnh'), '4. Phải có trạng thái Đang tinh chỉnh');
  assert.ok(text.includes('Hoàn thành'), '5. Phải có trạng thái Hoàn thành');

  // Kiểm tra không chứa các thuật ngữ nội bộ gây khó hiểu
  assert.equal(text.includes('thẩm định 4 tầng'), false, 'Không được hiển thị thuật ngữ thẩm định 4 tầng');
  assert.equal(text.includes('cảnh báo cục bộ flag'), false, 'Không được hiển thị thuật ngữ kỹ thuật cục bộ');

  await harness.unmount();
});

test('GenerationProgressView hiển thị trạng thái kết nối lại khi rớt mạng', async () => {
  const harness = renderProgress({
    sessionId: 'session-prog-003',
    connectionState: 'reconnecting',
    reconnectCount: 2,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Đang kết nối lại (2)'), 'Phải báo đang kết nối lại lần 2');

  await harness.unmount();
});

test('GenerationProgressView hiển thị thông báo lỗi và nút Thử lại khi mất kết nối', async () => {
  let reconnected = false;
  const harness = renderProgress({
    sessionId: 'session-prog-004',
    connectionState: 'disconnected',
    error: 'Mất kết nối máy chủ',
    onReconnect: () => {
      reconnected = true;
    },
  });
  await harness.render();

  const alertBox = harness.container.querySelector('[role="alert"]');
  assert.ok(alertBox, 'Phải có alert box');
  assert.ok(alertBox.textContent.includes('Mất kết nối máy chủ'));

  const retryBtn = alertBox.querySelector('button');
  assert.ok(retryBtn, 'Phải có nút Kết nối lại');
  await act(async () => {
    retryBtn.click();
  });
  assert.equal(reconnected, true, 'onReconnect phải được gọi');

  await harness.unmount();
});

test('GenerationProgressView tự động gọi onComplete sau khi nhận isDone = true', async () => {
  let completedCalled = false;
  const harness = renderProgress({
    sessionId: 'session-prog-005',
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
  assert.ok(text.includes('Đã sinh xong 2 mã đề thi đẳng cấu!'));
  assert.ok(text.includes('Đã hoàn tất'));

  // Đợi timer chuyển hướng tự động 1.5s
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1600));
  });

  assert.equal(completedCalled, true, 'onComplete phải được kích hoạt sau 1.5s');

  await harness.unmount();
});

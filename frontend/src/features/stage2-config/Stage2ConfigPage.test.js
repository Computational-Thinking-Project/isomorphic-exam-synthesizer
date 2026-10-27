import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

register('../../test-loader.mjs', import.meta.url);
const { default: Stage2ConfigPage } = await import('./Stage2ConfigPage.jsx');

function renderPage(sessionId = 'session-123', customProps = {}) {
  const container = document.createElement('div');
  const root = createRoot(container);

  return {
    container,
    async render() {
      await act(async () => {
        root.render(
          React.createElement(
            MemoryRouter,
            { initialEntries: [`/session/${sessionId}/stage2`] },
            React.createElement(
              Routes,
              null,
              React.createElement(Route, {
                path: '/session/:id/stage2',
                element: React.createElement(Stage2ConfigPage, customProps),
              }),
            ),
          ),
        );
      });
    },
    async unmount() {
      await act(async () => {
        root.unmount();
      });
    },
  };
}

test('Stage2ConfigPage hiển thị cảnh báo khi phiên đang ở trạng thái draft chưa duyệt Stage 1', async () => {
  const mockLoadSession = async () => ({
    id: 'draft-session-1',
    title: 'Đề Toán nháp',
    status: 'draft',
  });

  const harness = renderPage('draft-session-1', {
    loadSession: mockLoadSession,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Đề nguồn chưa được xác nhận'));
  assert.ok(text.includes('Giai đoạn 1'));

  await harness.unmount();
});

test('Stage2ConfigPage hiển thị lỗi khi loadSession thất bại', async () => {
  const mockLoadSession = async () => {
    throw new Error('Lỗi kết nối máy chủ 500');
  };

  const harness = renderPage('err-session-1', {
    loadSession: mockLoadSession,
  });
  await harness.render();

  const alertBox = harness.container.querySelector('[role="alert"]');
  assert.ok(alertBox, 'Phải có alert box');
  assert.ok(alertBox.textContent.includes('Lỗi kết nối máy chủ 500'));

  await harness.unmount();
});

test('Stage2ConfigPage tải thành công và hiển thị form Stage2ConfigCard khi status là blueprinted', async () => {
  const mockLoadSession = async () => ({
    id: 'blueprinted-session-1',
    title: 'Đề thi chuẩn hóa',
    status: 'blueprinted',
    subject: 'Toán',
    grade: 12,
    source_questions: [
      { id: 'q1', question_no: 1 },
      { id: 'q2', question_no: 2 },
    ],
    blueprint_summary: {
      total_questions: 2,
      supported_modes: [
        {
          id: 'parameter_variation',
          label: 'Thay số',
          question_count: 2,
          is_available: true,
        },
      ],
    },
  });

  const harness = renderPage('blueprinted-session-1', {
    loadSession: mockLoadSession,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Đề thi chuẩn hóa'));
  assert.ok(text.includes('2 câu hỏi'));
  assert.ok(text.includes('Bắt đầu sinh đề'));

  await harness.unmount();
});

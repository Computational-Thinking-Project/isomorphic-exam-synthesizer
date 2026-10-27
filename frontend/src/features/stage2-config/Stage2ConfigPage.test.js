import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

register('../../test-loader.mjs', import.meta.url);
const { default: Stage2ConfigPage } = await import('./Stage2ConfigPage.jsx');

function renderPage(sessionId = 'session-123', customProps = {}) {
  const container = document.createElement('div');
  const root = createRoot(container);
  let navigateFn = null;

  function NavigationCapture() {
    navigateFn = useNavigate();
    return null;
  }

  return {
    container,
    async render() {
      await act(async () => {
        root.render(
          React.createElement(
            MemoryRouter,
            { initialEntries: [`/session/${sessionId}/stage2`] },
            React.createElement(NavigationCapture),
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
    async navigate(nextId) {
      await act(async () => {
        navigateFn(`/session/${nextId}/stage2`);
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

test('Stage2ConfigPage xử lý lỗi Axios 400 có ERR_CONFIG_CONFLICT: đọc response.data.code và hiển thị tiếng Việt rõ ràng', async () => {
  const mockLoadSession = async () => ({
    id: 'conflict-session-1',
    title: 'Đề thi xung đột',
    status: 'blueprinted',
    source_questions: [{ id: 'q1', question_no: 1 }],
    blueprint_summary: {
      total_questions: 1,
      supported_modes: [
        { id: 'parameter_variation', label: 'Thay số', question_count: 1, is_available: true },
      ],
    },
  });

  // Mô phỏng lỗi chuẩn của Axios khi server trả về HTTP 400 body { code: 'ERR_CONFIG_CONFLICT' }
  const mockSaveConfig = async () => {
    const axiosError = new Error('Request failed with status code 400');
    axiosError.code = 'ERR_BAD_REQUEST'; // Axios luôn gán err.code = 'ERR_BAD_REQUEST' trên HTTP 400
    axiosError.response = {
      status: 400,
      data: {
        code: 'ERR_CONFIG_CONFLICT',
        detail: 'Chế độ được chọn không tương thích với Blueprint câu hỏi đã thẩm định.',
      },
    };
    throw axiosError;
  };

  const harness = renderPage('conflict-session-1', {
    loadSession: mockLoadSession,
    saveConfig: mockSaveConfig,
  });
  await harness.render();

  const form = harness.container.querySelector('form');
  assert.ok(form, 'Phải có form cấu hình');

  await act(async () => {
    form.dispatchEvent({
      type: 'submit',
      bubbles: true,
      cancelable: true,
      preventDefault: () => {},
    });
  });

  const alertBox = harness.container.querySelector('[role="alert"]');
  assert.ok(alertBox, 'Phải xuất hiện alert box thông báo lỗi');
  assert.ok(alertBox.textContent.includes('ERR_CONFIG_CONFLICT'), 'Phải nhận diện được mã lỗi ERR_CONFIG_CONFLICT từ Axios response');
  assert.ok(alertBox.textContent.includes('không tương thích với Blueprint'), 'Phải hiển thị nội dung detail hướng dẫn');
  assert.equal(alertBox.textContent.includes('status code 400'), false, 'Không được hiển thị lỗi thô status code 400');

  await harness.unmount();
});

test('Stage2ConfigPage cô lập trạng thái: chuyển từ phiên A đang generating sang phiên B blueprinted hiển thị lại form cấu hình', async () => {
  const sessions = {
    'session-A': {
      id: 'session-A',
      title: 'Đề A đang sinh',
      status: 'generating',
      source_questions: [{ id: 'q1', question_no: 1 }],
      blueprint_summary: {
        total_questions: 1,
        supported_modes: [{ id: 'parameter_variation', label: 'Thay số', is_available: true }],
      },
    },
    'session-B': {
      id: 'session-B',
      title: 'Đề B mới duyệt',
      status: 'blueprinted',
      source_questions: [{ id: 'q2', question_no: 1 }],
      blueprint_summary: {
        total_questions: 1,
        supported_modes: [{ id: 'parameter_variation', label: 'Thay số', is_available: true }],
      },
    },
  };

  const mockLoadSession = async (id) => sessions[id];
  const mockUseSSE = () => ({
    connectionState: 'connected',
    progress: { percent: 50, completedCount: 1, totalCount: 2 },
    questionStatuses: {},
    isDone: false,
    error: null,
    reconnectCount: 0,
    reconnect: () => {},
  });

  const harness = renderPage('session-A', {
    loadSession: mockLoadSession,
    useSSEHook: mockUseSSE,
  });

  // 1. Tải phiên A: trạng thái generating -> hiển thị màn tiến độ
  await harness.render();
  let text = harness.container.textContent;
  assert.ok(text.includes('Tiến trình sinh đề AI') || text.includes('Đang tạo các biến thể đề thi'));

  // 2. Chuyển sang phiên B: trạng thái blueprinted -> phải lập tức reset isGenerating và hiển thị lại form
  await harness.navigate('session-B');
  text = harness.container.textContent;
  assert.ok(text.includes('Đề B mới duyệt'), 'Phải hiển thị tiêu đề đề B');
  assert.ok(text.includes('Bắt đầu sinh đề'), 'Phải hiển thị nút Bắt đầu sinh đề của form, không kẹt lại màn tiến độ A');

  await harness.unmount();
});

test('Stage2ConfigPage nạp cấu hình đã lưu (initialConfig n_versions: 4) khi mở lại phiên', async () => {
  const mockLoadSession = async () => ({
    id: 'session-configured-4',
    title: 'Đề đã lưu 4 mã',
    status: 'configured',
    source_questions: [{ id: 'q1', question_no: 1 }],
    config: {
      n_versions: 4,
      active_variation_modes: ['parameter_variation'],
      ordering_preferences: { shuffle_questions: true },
    },
    blueprint_summary: {
      total_questions: 1,
      supported_modes: [
        { id: 'parameter_variation', label: 'Thay số', question_count: 1, is_available: true },
      ],
    },
  });

  const harness = renderPage('session-configured-4', {
    loadSession: mockLoadSession,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('4 mã đề'), 'Phải hiển thị đúng 4 mã đề từ cấu hình đã lưu');

  await harness.unmount();
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

register('../../test-loader.mjs', import.meta.url);
const { default: Stage2ConfigPage } = await import('./Stage2ConfigPage.jsx');

function renderPage(sessionId = 'session-123', customProps = {}) {
  const container = document.createElement('div');
  const root = createRoot(container);
  let navigateFn = null;
  let currentLocation = `/session/${sessionId}/stage2`;

  function NavigationCapture() {
    navigateFn = useNavigate();
    const loc = useLocation();
    currentLocation = loc.pathname;
    return null;
  }

  return {
    container,
    getLocation() {
      return currentLocation;
    },
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
              React.createElement(Route, {
                path: '/session/:id/stage3',
                element: React.createElement('div', null, 'Trang Stage 3 Đã Chuyển Hướng'),
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
      config: { n_versions: 2, active_variation_modes: ['parameter_variation'] },
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
    warnings: [],
    isDone: false,
    error: null,
    reconnectCount: 0,
    reconnect: () => {},
  });

  const harness = renderPage('session-A', {
    loadSession: mockLoadSession,
    useSSEHook: mockUseSSE,
  });

  // 1. Tải phiên A: trạng thái generating có config -> hiển thị màn tiến độ
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

test('Stage2ConfigPage hiển thị trạng thái đồng bộ và không tự đoán 2 mã khi mở lại phiên generating thiếu config', async () => {
  const mockLoadSession = async () => ({
    id: 'session-gen-no-config',
    title: 'Đề generating thiếu config',
    status: 'generating',
    source_questions: [{ id: 'q1', question_no: 1 }],
    config: null,
    exam_versions: [],
    blueprint_summary: {
      total_questions: 1,
      supported_modes: [{ id: 'parameter_variation', label: 'Thay số', is_available: true }],
    },
  });

  const mockUseSSE = () => ({
    connectionState: 'connecting',
    progress: { percent: 0 },
    questionStatuses: {},
    warnings: [],
    isDone: false,
    error: null,
    reconnectCount: 0,
    reconnect: () => {},
  });

  const harness = renderPage('session-gen-no-config', {
    loadSession: mockLoadSession,
    useSSEHook: mockUseSSE,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(
    text.includes('Đang đồng bộ tiến trình sinh đề') ||
    text.includes('Đang đồng bộ cấu hình số lượng mã đề'),
    'Phải hiển thị màn hình chờ đồng bộ',
  );
  assert.equal(text.includes('Mã đề #1'), false, 'Không tự vẽ tab mã đề #1 khi chưa biết số mã');
  assert.equal(text.includes('Mã đề #2'), false, 'Không tự đoán mặc định 2 mã đề');

  await harness.unmount();
});

test('Stage2ConfigPage cô lập submit: chuyển A đang lưu sang B thì form B không bị khoá và A không kích hoạt sinh đề', async () => {
  let resolveSaveA;
  const saveAPromise = new Promise((resolve) => {
    resolveSaveA = resolve;
  });

  let startGenCalledSession = null;

  const sessions = {
    'session-A': {
      id: 'session-A',
      title: 'Đề A',
      status: 'blueprinted',
      source_questions: [{ id: 'q1', question_no: 1 }],
      blueprint_summary: {
        total_questions: 1,
        supported_modes: [{ id: 'parameter_variation', label: 'Thay số', is_available: true }],
      },
    },
    'session-B': {
      id: 'session-B',
      title: 'Đề B',
      status: 'blueprinted',
      source_questions: [{ id: 'q2', question_no: 1 }],
      blueprint_summary: {
        total_questions: 1,
        supported_modes: [{ id: 'parameter_variation', label: 'Thay số', is_available: true }],
      },
    },
  };

  const harness = renderPage('session-A', {
    loadSession: async (id) => sessions[id],
    saveConfig: async (id) => {
      if (id === 'session-A') return saveAPromise;
      return { success: true };
    },
    startGen: async (id) => {
      startGenCalledSession = id;
    },
  });
  await harness.render();

  // Bấm submit ở phiên A
  const formA = harness.container.querySelector('form');
  await act(async () => {
    formA.dispatchEvent({
      type: 'submit',
      bubbles: true,
      cancelable: true,
      preventDefault: () => {},
    });
  });

  // Chuyển sang phiên B khi saveConfig(A) còn đang pending
  await harness.navigate('session-B');

  // Form B phải sẵn sàng, nút nộp trên B KHÔNG bị khoá ở trạng thái đang lưu của A
  const submitBtnB = harness.container.querySelector('button[type="submit"]');
  assert.ok(submitBtnB, 'Phải có nút submit trên form B');
  assert.equal(submitBtnB.getAttribute('disabled') === null, true, 'Nút submit của B không được bị khoá');
  assert.ok(submitBtnB.textContent.includes('Bắt đầu sinh đề'));

  // Phản hồi saveConfig của A trả về muộn
  await act(async () => {
    resolveSaveA({ success: true });
  });

  // startGen(A) tuyệt đối không được gọi vì phiên đã chuyển sang B
  assert.equal(startGenCalledSession, null, 'Không được gọi startGen(A) sau khi đã chuyển sang phiên B');

  await harness.unmount();
});

test('Stage2ConfigPage truyền và hiển thị cảnh báo SSE tới giao diện tiến trình', async () => {
  const mockLoadSession = async () => ({
    id: 'session-warnings',
    title: 'Đề có cảnh báo',
    status: 'generating',
    config: { n_versions: 2 },
    source_questions: [{ id: 'q1', question_no: 1 }],
    blueprint_summary: {
      total_questions: 1,
      supported_modes: [{ id: 'parameter_variation', label: 'Thay số', is_available: true }],
    },
  });

  const mockUseSSE = () => ({
    connectionState: 'connected',
    progress: { percent: 30, completedCount: 0, totalCount: 2 },
    questionStatuses: {},
    warnings: [
      {
        version_index: 1,
        question_no: 1,
        message: 'Phương sai bài toán hơi lớn, cần lưu ý khi thẩm định',
      },
    ],
    isDone: false,
    error: null,
    reconnectCount: 0,
    reconnect: () => {},
  });

  const harness = renderPage('session-warnings', {
    loadSession: mockLoadSession,
    useSSEHook: mockUseSSE,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Phương sai bài toán hơi lớn'), 'Cảnh báo từ SSE phải được hiển thị tới người dùng');
  assert.ok(text.includes('Có 1 cảnh báo trong quá trình sinh đề'));

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

test('Stage2ConfigPage phiên generating thiếu config: SSE báo lỗi hiển thị rõ ràng và có nút kết nối lại', async () => {
  let reconnected = false;
  const mockLoadSession = async () => ({
    id: 'session-gen-err',
    title: 'Đề generating thiếu config',
    status: 'generating',
    source_questions: [{ id: 'q1', question_no: 1 }],
    config: null,
    exam_versions: [],
    blueprint_summary: {
      total_questions: 1,
      supported_modes: [],
      is_ready: true,
    },
  });

  const mockUseSSE = () => ({
    connectionState: 'failed',
    progress: { percent: 15 },
    questionStatuses: {},
    warnings: [],
    isDone: false,
    error: 'Hết hạn quota Gemini API (ERR_QUOTA_EXCEEDED)',
    reconnectCount: 1,
    reconnect: () => {
      reconnected = true;
    },
  });

  const harness = renderPage('session-gen-err', {
    loadSession: mockLoadSession,
    useSSEHook: mockUseSSE,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Hết hạn quota Gemini API'), 'Lỗi SSE phải được hiển thị ngay cả khi thiếu config');

  const reconnectBtn = Array.from(harness.container.querySelectorAll('button')).find((b) =>
    b.textContent.includes('Kết nối lại'),
  );
  assert.ok(reconnectBtn, 'Phải có nút Kết nối lại');
  reconnectBtn.click();
  assert.equal(reconnected, true, 'Bấm nút phải gọi hàm reconnect của hook');

  await harness.unmount();
});

test('Stage2ConfigPage phiên generating thiếu config: SSE báo done kết thúc trạng thái chờ và chuyển hướng Stage3', async () => {
  const mockLoadSession = async () => ({
    id: 'session-gen-done-no-config',
    title: 'Đề generating thiếu config hoàn thành',
    status: 'generating',
    source_questions: [{ id: 'q1', question_no: 1 }],
    config: null,
    exam_versions: [],
    blueprint_summary: {
      total_questions: 1,
      supported_modes: [],
      is_ready: true,
    },
  });

  const mockUseSSE = () => ({
    connectionState: 'connected',
    progress: { percent: 100 },
    questionStatuses: {},
    warnings: [],
    isDone: true,
    error: null,
    reconnectCount: 0,
    reconnect: () => {},
  });

  const harness = renderPage('session-gen-done-no-config', {
    loadSession: mockLoadSession,
    useSSEHook: mockUseSSE,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Đã sinh xong tất cả các mã đề thi đẳng cấu!'), 'Phải hiển thị thông báo hoàn tất');

  // Đợi timer auto-redirect chạy
  await new Promise((r) => setTimeout(r, 1600));
  assert.equal(
    harness.getLocation(),
    '/session/session-gen-done-no-config/stage3',
    'Phải tự động điều hướng sang Stage 3',
  );

  await harness.unmount();
});

test('Stage2ConfigPage phiên partial_generated: SSE báo done nhưng isPartial = true không tự động điều hướng sang Stage 3 và hiển thị cảnh báo sinh một phần', async () => {
  const mockLoadSession = async () => ({
    id: 'session-partial-gen',
    title: 'Đề sinh một phần',
    status: 'generating',
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    config: { num_versions: 2 },
    exam_versions: [],
    blueprint_summary: {
      total_questions: 2,
      supported_modes: [],
      is_ready: true,
    },
  });

  const mockUseSSE = () => ({
    connectionState: 'connected',
    progress: {
      percent: 50,
      completedCount: 2,
      totalVariants: 4,
      session_status: 'partial_generated',
      is_partial: true,
    },
    questionStatuses: {},
    warnings: [],
    isDone: true,
    isPartial: true,
    error: null,
    reconnectCount: 0,
    reconnect: () => {},
  });

  const harness = renderPage('session-partial-gen', {
    loadSession: mockLoadSession,
    useSSEHook: mockUseSSE,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('partial_generated'), 'Phải hiển thị nhãn partial_generated');
  assert.ok(text.includes('Còn thiếu 2 câu'), 'Phải tính và hiển thị đúng số câu còn thiếu');

  // Đợi timer 1600ms để kiểm tra xem có redirect nhầm hay không
  await new Promise((r) => setTimeout(r, 1600));
  assert.equal(
    harness.getLocation(),
    '/session/session-partial-gen/stage2',
    'Không được tự động điều hướng sang Stage 3 khi chỉ mới hoàn thành một phần',
  );

  await harness.unmount();
});

test('Stage2ConfigPage xử lý lỗi 409 sinh bù dạng object detail: {code, message} an toàn, không làm crash React child', async () => {
  const mockLoadSession = async () => ({
    id: 'session-retry-error-test',
    title: 'Đề kiểm tra lỗi retry 409',
    status: 'generating',
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    config: { num_versions: 2 },
    exam_versions: [],
    blueprint_summary: {
      total_questions: 2,
      supported_modes: [],
      is_ready: true,
    },
  });

  const mockUseSSE = () => ({
    connectionState: 'connected',
    progress: {
      percent: 50,
      completedCount: 2,
      totalVariants: 4,
      session_status: 'partial_generated',
      is_partial: true,
    },
    questionStatuses: {},
    warnings: [],
    isDone: true,
    isPartial: true,
    error: null,
    reconnectCount: 0,
    reconnect: () => {},
  });

  // Giả lập lỗi HTTP 409 trả về object detail: { code, message }
  const mockRetryGen = async () => {
    const err = new Error('Request failed with status code 409');
    err.response = {
      status: 409,
      data: {
        detail: {
          code: 'ERR_SESSION_CONFLICT',
          message: 'Phiên đang trong tiến trình sinh đề nền, không thể sinh bù trùng lặp.',
        },
      },
    };
    throw err;
  };

  const harness = renderPage('session-retry-error-test', {
    loadSession: mockLoadSession,
    useSSEHook: mockUseSSE,
    retryGen: mockRetryGen,
  });
  await harness.render();

  const retryBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Sinh bù các câu còn thiếu'),
  );
  assert.ok(retryBtn, 'Phải có nút Sinh bù các câu còn thiếu');

  await act(async () => {
    retryBtn.click();
  });

  // Xác minh thông báo lỗi được hiển thị dưới dạng chuỗi an toàn, không gây crash màn hình React
  const alertBox = harness.container.querySelector('[role="alert"]');
  assert.ok(alertBox, 'Phải có alert box hiển thị lỗi');
  assert.ok(alertBox.textContent.includes('Phiên đang trong tiến trình sinh đề nền'));

  await harness.unmount();
});

test('F02: Stage2ConfigPage mở phiên partial_generated với response chỉ có metadata mã đề (PR32) hiển thị Chưa có dữ liệu tiến độ, không hiển thị 0/4 và vẫn có nút Sinh bù', async () => {
  // Mô phỏng response GET detail từ PR #32: chỉ có exam_versions rỗng (metadata mã đề), không có progress hay questions
  const mockLoadSession = async () => ({
    id: 'session-pr32-meta-only',
    title: 'Đề thi PR32',
    status: 'partial_generated',
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    config: { num_versions: 2 },
    exam_versions: [{ version_index: 1 }, { version_index: 2 }],
    blueprint_summary: {
      total_questions: 2,
      supported_modes: [],
      is_ready: true,
    },
    progress: null, // Không có snapshot DB
  });

  const harness = renderPage('session-pr32-meta-only', {
    loadSession: mockLoadSession,
  });
  await harness.render();

  const text = harness.container.textContent;
  // 1. Phải báo "Chưa có dữ liệu tiến độ"
  assert.ok(text.includes('Chưa có dữ liệu tiến độ'), 'Phải thông báo Chưa có dữ liệu tiến độ');
  // 2. Tuyệt đối không hiện "0 / 4" hoặc "0/4"
  assert.equal(/0\s*\/\s*4/.test(text), false, 'Không được hiển thị 0/4 khi thiếu snapshot');
  // 3. Vẫn hiển thị nút "Sinh bù các câu còn thiếu" vì session.status là partial_generated
  const retryBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Sinh bù các câu còn thiếu'),
  );
  assert.ok(retryBtn, 'Phải có nút Sinh bù các câu còn thiếu');

  await harness.unmount();
});

test('F02 Ca còn lỗi: F5/mở lại phiên partial_generated khi generation-snapshot có kết quả 3/4 thì đọc snapshot và hiển thị đúng 75%, 3/4 và lưới câu đã lưu', async () => {
  let fetchGenSnapshotCalled = false;
  const mockLoadSession = async (sessionId) => ({
    id: sessionId,
    title: 'Đề thi cần phục hồi snapshot',
    status: 'partial_generated',
    source_questions: [
      { id: 'q1', question_no: 1 },
      { id: 'q2', question_no: 2 },
    ],
    config: { num_versions: 2 },
    exam_versions: [{ version_index: 1 }, { version_index: 2 }],
    blueprint_summary: {
      total_questions: 2,
      supported_modes: [],
      is_ready: true,
    },
    progress: null, // Ban đầu session detail chưa nhúng progress
  });

  const mockFetchGenSnapshot = async () => {
    fetchGenSnapshotCalled = true;
    return {
      progress: {
        percent: 75,
        completed_count: 3,
        total_count: 4,
        completedCount: 3,
        totalCount: 4,
        hasData: true,
      },
      question_statuses: {
        '1-1': { version_index: 1, question_no: 1, status: 'done', message: 'Đã hoàn thành câu 1.1' },
        '1-2': { version_index: 1, question_no: 2, status: 'done', message: 'Đã hoàn thành câu 1.2' },
        '2-1': { version_index: 2, question_no: 1, status: 'done', message: 'Đã hoàn thành câu 2.1' },
      },
      resume_after_event_id: 72,
      stream_epoch: 'epoch-2',
    };
  };

  const harness = renderPage('session-f02-snapshot-reload', {
    loadSession: mockLoadSession,
    fetchGenSnapshot: mockFetchGenSnapshot,
  });
  await harness.render();

  assert.equal(fetchGenSnapshotCalled, true, 'fetchGenSnapshot phải được gọi chủ động khi mở phiên partial_generated');

  const text = harness.container.textContent;
  // TIÊU CHÍ ĐẠT: FE đọc snapshot và hiển thị đúng 75%, 3/4 cùng lưới câu đã lưu
  assert.ok(text.includes('75%'), 'Phải hiển thị tiến độ 75%');
  assert.ok(text.includes('3 / 4'), 'Phải hiển thị 3 / 4 câu hỏi đã hoàn tất');
  assert.equal(text.includes('Chưa có dữ liệu tiến độ'), false, 'Không được hiển thị Chưa có dữ liệu tiến độ');

  await harness.unmount();
});

test('F06 Ca còn lỗi: Điều hướng A -> B -> A, snapshot của lượt A đầu tiên trả về muộn không được ghi đè lên lượt A thứ hai trên trang', async () => {
  let resolveSessionAFirstSnapshot;
  const sessionAFirstPromise = new Promise((resolve) => {
    resolveSessionAFirstSnapshot = resolve;
  });

  let loadACount = 0;
  const mockLoadSession = async (sessionId) => {
    if (sessionId === 'session-A') {
      loadACount += 1;
      return {
        id: 'session-A',
        title: 'Phiên A',
        status: 'partial_generated',
        source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
        config: { num_versions: 2 },
        exam_versions: [{ version_index: 1 }, { version_index: 2 }],
        blueprint_summary: { total_questions: 2, supported_modes: [], is_ready: true },
        progress: null,
      };
    }
    return {
      id: 'session-B',
      title: 'Phiên B',
      status: 'partial_generated',
      source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
      config: { num_versions: 2 },
      exam_versions: [{ version_index: 1 }, { version_index: 2 }],
      blueprint_summary: { total_questions: 2, supported_modes: [], is_ready: true },
      progress: { percent: 10, completed_count: 1, total_count: 4, hasData: true },
    };
  };

  const mockFetchGenSnapshot = async (sessionId) => {
    if (sessionId === 'session-A' && loadACount === 1) {
      // Lượt A đầu tiên: trả về chậm sau đó
      return await sessionAFirstPromise;
    }
    if (sessionId === 'session-A' && loadACount > 1) {
      // Lượt A thứ hai: trả về 25% (1/4 câu)
      return {
        progress: { percent: 25, completed_count: 1, total_count: 4, hasData: true },
        question_statuses: { '1-1': { status: 'done', message: 'Câu 1 Đề 1 xong' } },
      };
    }
    return {
      progress: { percent: 10, completed_count: 1, total_count: 4, hasData: true },
    };
  };

  const harness = renderPage('session-A', {
    loadSession: mockLoadSession,
    fetchGenSnapshot: mockFetchGenSnapshot,
  });
  await harness.render();

  // Chuyển sang phiên B
  await harness.navigate('session-B');
  await act(async () => {
    await new Promise((r) => setTimeout(r, 50));
  });

  // Chuyển quay lại phiên A (lượt A thứ hai)
  await harness.navigate('session-A');
  await act(async () => {
    await new Promise((r) => setTimeout(r, 50));
  });

  // Kiểm tra lượt A thứ hai đang hiển thị 25%
  let text = harness.container.textContent;
  assert.ok(text.includes('25%'), 'Lượt A thứ hai phải hiển thị tiến độ 25%');

  // Bây giờ snapshot của lượt A đầu tiên mới trả về với 90%
  await act(async () => {
    resolveSessionAFirstSnapshot({
      progress: { percent: 90, completed_count: 9, total_count: 10, hasData: true },
      question_statuses: { '1-1': { status: 'done', message: 'Lượt cũ 90%' } },
    });
    await new Promise((r) => setTimeout(r, 100));
  });

  // TIÊU CHÍ ĐẠT: Lượt A hiện tại phải giữ nguyên 25%, KHÔNG bị 90% của lượt cũ ghi đè
  text = harness.container.textContent;
  assert.ok(text.includes('25%'), 'Tiến độ của phiên A vẫn phải giữ nguyên 25%');
  assert.equal(text.includes('90%'), false, 'Tuyệt đối không bị 90% của lượt A cũ ghi đè');

  await harness.unmount();
});

test('F07: Khi GET detail trả generating nhưng snapshot báo generated (100%, 4/4), trang hoàn tất và điều hướng Stage 3 mà không cần chờ done từ stream', async () => {
  const mockLoadSession = async (sessionId) => ({
    id: sessionId,
    title: 'Đề Toán hoàn thành nền',
    status: 'generating', // GET detail trả generating
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    config: { num_versions: 2 },
    exam_versions: [{ version_index: 1 }, { version_index: 2 }],
    blueprint_summary: { total_questions: 2, supported_modes: [], is_ready: true },
    progress: null,
  });

  const mockFetchGenSnapshot = async () => ({
    status: 'generated',
    progress: {
      percent: 100,
      completed_count: 4,
      total_count: 4,
      completedCount: 4,
      totalCount: 4,
      session_status: 'generated',
      hasData: true,
    },
    question_statuses: {
      '1-1': { version_index: 1, question_no: 1, status: 'done' },
      '1-2': { version_index: 1, question_no: 2, status: 'done' },
      '2-1': { version_index: 2, question_no: 1, status: 'done' },
      '2-2': { version_index: 2, question_no: 2, status: 'done' },
    },
  });

  const harness = renderPage('session-f07-done-without-stream', {
    loadSession: mockLoadSession,
    fetchGenSnapshot: mockFetchGenSnapshot,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('100%'), 'Phải hiển thị tiến độ 100%');
  assert.ok(text.includes('Đã hoàn tất'), 'Phải hiển thị trạng thái Đã hoàn tất');

  // Chờ timer 1.5s tự động chuyển sang Stage 3
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1600));
  });

  assert.equal(
    harness.getLocation(),
    '/session/session-f07-done-without-stream/stage3',
    'Phải tự động điều hướng sang Stage 3 khi snapshot đã hoàn tất',
  );

  await harness.unmount();
});

test('F08: Một lần F5/mở trang chỉ gọi endpoint snapshot đúng 1 lần khi loadSession đã có sẵn snapshot', async () => {
  let fetchGenSnapshotCalls = 0;
  const mockLoadSession = async (sessionId) => ({
    id: sessionId,
    title: 'Đề F5 không lặp snapshot',
    status: 'partial_generated',
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    config: { num_versions: 2 },
    exam_versions: [{ version_index: 1 }, { version_index: 2 }],
    blueprint_summary: { total_questions: 2, supported_modes: [], is_ready: true },
    progress: {
      percent: 75,
      completed_count: 3,
      total_count: 4,
      completedCount: 3,
      totalCount: 4,
      hasData: true,
    },
  });

  const mockFetchGenSnapshot = async () => {
    fetchGenSnapshotCalls += 1;
    return {
      progress: { percent: 75, completed_count: 3, total_count: 4, hasData: true },
    };
  };

  const harness = renderPage('session-f08-single-snapshot', {
    loadSession: mockLoadSession,
    fetchGenSnapshot: mockFetchGenSnapshot,
  });
  await harness.render();

  // TIÊU CHÍ ĐẠT: Khi loadSession đã có snapshot (từ fetchSessionDetail), Stage2ConfigPage không gọi lặp endpoint
  assert.equal(fetchGenSnapshotCalls, 0, 'Tuyệt đối không gọi lặp lại generation-snapshot khi đã có sẵn snapshot');

  const text = harness.container.textContent;
  assert.ok(text.includes('75%'), 'Vẫn hiển thị đầy đủ tiến độ 75%');
  assert.ok(text.includes('3 / 4'), 'Vẫn hiển thị 3 / 4');

  await harness.unmount();
});

test('F06: Callback handleResyncSnapshot của lượt A đầu tiên trả về muộn sau khi chuyển A -> B -> A không được ghi đè vào lượt A thứ hai', async () => {
  let resolveFirstResync;
  const firstResyncPromise = new Promise((resolve) => {
    resolveFirstResync = resolve;
  });

  let capturedResyncCallback = null;
  const mockUseSSE = (sid, options) => {
    capturedResyncCallback = options.onResync;
    return {
      connectionState: 'connected',
      progress: {
        percent: sid === 'session-A' ? 25 : 10,
        completedCount: 1,
        totalCount: 4,
        hasData: true,
      },
      questionStatuses: {
        '1-1': { status: 'done', message: `Câu của ${sid} mới` },
      },
      warnings: [],
      isDone: false,
      isPartial: false,
      error: null,
      reconnectCount: 0,
      reconnect: () => {},
    };
  };

  let resyncCallCount = 0;
  const mockFetchGenSnapshot = async (sid) => {
    resyncCallCount += 1;
    if (sid === 'session-A' && resyncCallCount === 1) {
      return await firstResyncPromise;
    }
    return {
      progress: { percent: 25, completed_count: 1, total_count: 4, hasData: true },
      question_statuses: { '1-1': { status: 'done', message: 'Câu mới 25%' } },
    };
  };

  const mockLoadSession = async (sid) => ({
    id: sid,
    title: `Phiên ${sid}`,
    status: 'partial_generated',
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    config: { num_versions: 2 },
    exam_versions: [{ version_index: 1 }, { version_index: 2 }],
    blueprint_summary: { total_questions: 2, supported_modes: [], is_ready: true },
    progress: { percent: 25, completed_count: 1, total_count: 4, hasData: true },
  });

  const harness = renderPage('session-A', {
    loadSession: mockLoadSession,
    fetchGenSnapshot: mockFetchGenSnapshot,
    useSSEHook: mockUseSSE,
  });
  await harness.render();

  // Kích hoạt resync ở lượt A đầu tiên (bị hoãn lại bởi firstResyncPromise)
  assert.ok(capturedResyncCallback, 'Phải có capturedResyncCallback');
  const resyncPromise1 = capturedResyncCallback('session-A');

  // Chuyển sang phiên B rồi quay lại phiên A
  await harness.navigate('session-B');
  await act(async () => {
    await new Promise((r) => setTimeout(r, 50));
  });

  await harness.navigate('session-A');
  await act(async () => {
    await new Promise((r) => setTimeout(r, 50));
  });

  // Bây giờ snapshot của lượt A đầu tiên mới hoàn tất (trả 90% và câu cũ)
  await act(async () => {
    resolveFirstResync({
      progress: { percent: 90, completed_count: 9, total_count: 10, hasData: true },
      question_statuses: { '1-1': { status: 'done', message: 'Dữ liệu cũ 90% của lượt 1' } },
    });
    await resyncPromise1;
    await new Promise((r) => setTimeout(r, 100));
  });

  // TIÊU CHÍ ĐẠT: Lưới câu của lượt A thứ hai không nhận dữ liệu cũ của lượt 1!
  const text = harness.container.textContent;
  assert.equal(
    text.includes('Dữ liệu cũ 90% của lượt 1'),
    false,
    'Lưới câu của lượt A thứ hai tuyệt đối không được nhận dữ liệu cũ của lượt 1',
  );

  await harness.unmount();
});

test('F09 Ca 1: Stream báo tiến độ 100% (4/4 câu) nhưng chưa có done (status: generating) -> KHÔNG chuyển Stage 3, tiếp tục theo dõi; chỉ chuyển Stage 3 khi sự kiện done xuất hiện', async () => {
  let sseStateSetter = null;
  const mockLoadSession = async (sessionId) => ({
    id: sessionId,
    title: 'Đề Toán đang sinh 100% chưa done',
    status: 'generating',
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    config: { num_versions: 2 },
    exam_versions: [{ version_index: 1 }, { version_index: 2 }],
    blueprint_summary: { total_questions: 2, supported_modes: [], is_ready: true },
    progress: { percent: 50, completed_count: 2, total_count: 4, hasData: true },
  });

  function MockSSEHook() {
    const [state, setState] = React.useState({
      connectionState: 'connected',
      progress: {
        percent: 100,
        completed_count: 4,
        total_count: 4,
        completedCount: 4,
        totalCount: 4,
        hasData: true,
        session_status: 'generating',
      },
      questionStatuses: {
        '1-1': { status: 'done' },
        '1-2': { status: 'done' },
        '2-1': { status: 'done' },
        '2-2': { status: 'done' },
      },
      warnings: [],
      isDone: false, // CHƯA CÓ SỰ KIỆN DONE TỪ STREAM
      error: null,
      reconnectCount: 0,
      reconnect: () => {},
    });
    sseStateSetter = setState;
    return state;
  }

  const harness = renderPage('session-f09-stream-100-no-done', {
    loadSession: mockLoadSession,
    useSSEHook: MockSSEHook,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('100%'), 'Phải hiển thị 100%');
  assert.equal(
    text.includes('Đã hoàn tất sinh đề!'),
    false,
    'Tuyệt đối không được hiển thị hoàn tất khi chưa có done',
  );

  // Đợi 1600ms (khoảng thời gian timer auto-redirect nếu có lỗi)
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1600));
  });

  // TIÊU CHÍ ĐẠT: Vẫn ở lại Stage 2, không điều hướng sang Stage 3
  assert.equal(
    harness.getLocation(),
    '/session/session-f09-stream-100-no-done/stage2',
    'Phải tiếp tục ở lại Stage 2 theo dõi khi job vẫn generating và chưa có done',
  );

  // Bây giờ stream phát sự kiện done -> isDone = true
  await act(async () => {
    sseStateSetter((prev) => ({
      ...prev,
      isDone: true,
      progress: {
        ...prev.progress,
        session_status: 'generated',
      },
    }));
  });

  // Đợi timer 1.5s auto-redirect
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1600));
  });

  // Sau khi có done, phải chuyển sang Stage 3 thành công
  assert.equal(
    harness.getLocation(),
    '/session/session-f09-stream-100-no-done/stage3',
    'Sau khi có sự kiện done xác nhận, phải chuyển sang Stage 3',
  );

  await harness.unmount();
});

test('F09 Ca 2: Snapshot phục hồi báo 100% nhưng session_status vẫn là generating -> KHÔNG chuyển Stage 3, tiếp tục theo dõi', async () => {
  const mockLoadSession = async (sessionId) => ({
    id: sessionId,
    title: 'Đề Toán phục hồi snapshot generating 100%',
    status: 'generating',
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    config: { num_versions: 2 },
    exam_versions: [{ version_index: 1 }, { version_index: 2 }],
    blueprint_summary: { total_questions: 2, supported_modes: [], is_ready: true },
    progress: null,
  });

  const mockFetchGenSnapshot = async () => ({
    status: 'generating',
    session_status: 'generating', // BACKEND VẪN GENERATING
    progress: {
      percent: 100,
      completed_count: 4,
      total_count: 4,
      completedCount: 4,
      totalCount: 4,
      session_status: 'generating',
      hasData: true,
    },
    question_statuses: {
      '1-1': { status: 'done' },
      '1-2': { status: 'done' },
      '2-1': { status: 'done' },
      '2-2': { status: 'done' },
    },
  });

  const harness = renderPage('session-f09-snapshot-generating-100', {
    loadSession: mockLoadSession,
    fetchGenSnapshot: mockFetchGenSnapshot,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('100%'), 'Phải hiển thị tiến độ 100%');
  assert.equal(
    text.includes('Đã hoàn tất sinh đề!'),
    false,
    'Tuyệt đối không hiển thị hoàn tất khi snapshot báo session_status vẫn là generating',
  );

  // Chờ 1600ms timer
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1600));
  });

  // TIÊU CHÍ ĐẠT: Không điều hướng sang Stage 3!
  assert.equal(
    harness.getLocation(),
    '/session/session-f09-snapshot-generating-100/stage2',
    'Không được chuyển Stage 3 khi snapshot báo 100% nhưng session_status vẫn là generating',
  );

  await harness.unmount();
});

test('Stage2ConfigPage: hiển thị Recovery View và mã lỗi generation_error_code khi phiên ở trạng thái failed', async () => {
  const mockLoadSession = async () => ({
    id: 'failed-session-1',
    title: 'Đề Toán lỗi',
    status: 'failed',
    generation_error_code: 'ERR_MODEL_QUOTA_EXHAUSTED',
  });

  const harness = renderPage('failed-session-1', {
    loadSession: mockLoadSession,
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(
    text.includes('Tiến trình sinh đề thi bị gián đoạn hoặc thất bại'),
    'Phải hiển thị tiêu đề Recovery View khi phiên bị failed',
  );
  assert.ok(
    text.includes('ERR_MODEL_QUOTA_EXHAUSTED'),
    'Phải hiển thị mã lỗi generation_error_code',
  );
  const retryBtn = harness.container.querySelector('button');
  assert.ok(retryBtn, 'Phải có nút bấm');
  assert.ok(
    text.includes('Thử lại tiến trình sinh đề'),
    'Phải có nút Thử lại tiến trình sinh đề',
  );

  await harness.unmount();
});

test('Stage2ConfigPage: bấm Thử lại tiến trình sinh đề khi phiên failed gọi retryGeneration thành công', async () => {
  let retryCalledWith = null;
  const mockLoadSession = async () => ({
    id: 'failed-session-2',
    title: 'Đề Toán lỗi retry',
    status: 'failed',
    generation_error_code: 'ERR_GENERATION_INTERRUPTED',
  });

  const mockRetryGen = async (id) => {
    retryCalledWith = id;
    return { ok: true };
  };

  const harness = renderPage('failed-session-2', {
    loadSession: mockLoadSession,
    retryGen: mockRetryGen,
  });
  await harness.render();

  const buttons = Array.from(harness.container.querySelectorAll('button'));
  const retryButton = buttons.find((btn) => btn.textContent.includes('Thử lại'));
  assert.ok(retryButton, 'Phải tìm thấy nút Thử lại');

  await act(async () => {
    retryButton.click();
  });

  assert.equal(
    retryCalledWith,
    'failed-session-2',
    'Phải gọi retryGen với đúng sessionId',
  );

  await harness.unmount();
});

test('Stage2ConfigPage: bấm Thử lại tiến trình sinh đề khi máy chủ báo lỗi hiển thị thông báo lỗi', async () => {
  const mockLoadSession = async () => ({
    id: 'failed-session-3',
    title: 'Đề Toán lỗi mạng',
    status: 'failed',
    generation_error_code: 'ERR_MODEL_TIMEOUT',
  });

  const mockRetryGen = async () => {
    const error = new Error('Lỗi kết nối máy chủ khi thử lại');
    error.response = { data: { error_message: 'Hệ thống đang bảo trì worker.' } };
    throw error;
  };

  const harness = renderPage('failed-session-3', {
    loadSession: mockLoadSession,
    retryGen: mockRetryGen,
  });
  await harness.render();

  const buttons = Array.from(harness.container.querySelectorAll('button'));
  const retryButton = buttons.find((btn) => btn.textContent.includes('Thử lại'));
  assert.ok(retryButton, 'Phải tìm thấy nút Thử lại');

  await act(async () => {
    retryButton.click();
  });

  const text = harness.container.textContent;
  assert.ok(
    text.includes('Hệ thống đang bảo trì worker.'),
    'Phải hiển thị thông báo lỗi an toàn khi retry thất bại',
  );

  await harness.unmount();
});

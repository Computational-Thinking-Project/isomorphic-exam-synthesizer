import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useNavigate, useLocation } from 'react-router-dom';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

register('../../test-loader.mjs', import.meta.url);
const { default: Stage3ReviewPage } = await import('./Stage3ReviewPage.jsx');

function renderStage3Page(sessionId, { loadSession, retryGen } = {}) {
  const container = document.createElement('div');
  const root = createRoot(container);
  let navigateFn = null;
  let currentLocation = `/session/${sessionId}/stage3`;

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
            { initialEntries: [`/session/${sessionId}/stage3`] },
            React.createElement(NavigationCapture),
            React.createElement(
              Routes,
              null,
              React.createElement(Route, {
                path: '/session/:sessionId/stage3',
                element: React.createElement(Stage3ReviewPage, {
                  loadSession,
                  retryGen,
                }),
              }),
              React.createElement(Route, {
                path: '/session/:sessionId/stage2',
                element: React.createElement('div', null, 'Trang Stage 2 Đã Chuyển Hướng'),
              }),
            ),
          ),
        );
      });
    },
    async navigate(nextId) {
      await act(async () => {
        navigateFn(`/session/${nextId}/stage3`);
      });
    },
    async unmount() {
      await act(async () => {
        root.unmount();
      });
    },
  };
}

test('Stage3ReviewPage hiển thị cảnh báo partial_generated, khóa xuất bản và hiển thị nút Sinh bù câu này cho câu thiếu', async () => {
  const retryCalls = [];
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi Toán 12 — Sinh thiếu một phần',
    status: 'partial_generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 2 },
    source_questions: [
      { id: 'q1', question_no: 1, raw_content: 'Tính tích phân $\\int_0^1 x dx$' },
      { id: 'q2', question_no: 2, raw_content: 'Tìm nghiệm của $x^2 - 4 = 0$' },
    ],
    exam_versions: [
      {
        version_index: 1,
        questions: [
          {
            question_no: 1,
            content: 'Tính tích phân $\\int_0^2 x dx$',
            options: { A: '1', B: '2', C: '3', D: '4' },
            correct_key: 'B',
            has_warning: false,
            solution_md: 'Ta có $\\int_0^2 x dx = \\frac{x^2}{2}\\Big|_0^2 = 2$.',
          },
          // Câu 2 bị thiếu trong mã đề 1
        ],
      },
      {
        version_index: 2,
        questions: [],
      },
    ],
  });

  const mockRetryGen = async (sId) => {
    retryCalls.push(sId);
    return { ok: true };
  };

  const harness = renderStage3Page('sess-partial-3', {
    loadSession: mockLoadSession,
    retryGen: mockRetryGen,
  });

  await harness.render();

  const text = harness.container.textContent;
  // 1. Kiểm tra banner partial_generated
  assert.ok(text.includes('partial_generated'), 'Phải hiển thị nhãn cảnh báo partial_generated');
  assert.ok(text.includes('Cảnh báo: Đề thi có câu hỏi chưa hoàn tất'), 'Phải có nội dung giải thích lỗi');

  // 2. Kiểm tra nút Xuất bản file bị vô hiệu hóa / khóa
  const exportBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Xuất bản file'),
  );
  assert.ok(exportBtn, 'Phải có nút Xuất bản file');
  assert.equal(exportBtn.getAttribute('disabled') !== null, true, 'Nút Xuất bản file phải bị disabled khi partial_generated');

  // 3. Kiểm tra câu 1 đã sinh có đầy đủ nội dung và badge Đạt chuẩn
  assert.ok(text.includes('Câu 1 (Mã đề #101)'), 'Phải hiển thị Câu 1');
  assert.ok(text.includes('Đạt chuẩn'), 'Câu 1 không warning phải hiện Đạt chuẩn');

  // 4. Kiểm tra câu 2 bị thiếu hiển thị nút Sinh bù câu này
  assert.ok(text.includes('Câu 2 (Mã đề #101) — Chưa được sinh thành công'), 'Phải báo Câu 2 chưa hoàn tất');
  const retryBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Sinh bù câu này'),
  );
  assert.ok(retryBtn, 'Câu thiếu phải có nút Sinh bù câu này');

  // Bấm nút "Sinh bù câu này" trên câu 2 bị thiếu
  await act(async () => {
    retryBtn.click();
  });

  assert.equal(retryCalls.length, 1);
  assert.equal(retryCalls[0], 'sess-partial-3');

  await harness.unmount();
});

test('Stage3ReviewPage hiển thị đúng badge Cần thẩm định (Có cảnh báo) khi câu hỏi mang has_warning: true', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi Toán 12 — Có câu cảnh báo',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'q1', question_no: 1 }],
    exam_versions: [
      {
        version_index: 1,
        questions: [
          {
            question_no: 1,
            content: 'Giải phương trình $2x = 4$',
            options: { A: 'x = 1', B: 'x = 2' },
            correct_key: 'B',
            has_warning: true,
            warning_message: 'Nghiệm không phải số nguyên đẹp sau 3 lần retry.',
          },
        ],
      },
    ],
  });

  const harness = renderStage3Page('sess-warning-3', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  const text = harness.container.textContent;
  // Tuyệt đối không được hiện Đạt chuẩn khi has_warning là true
  assert.ok(text.includes('Cần thẩm định (Có cảnh báo)'), 'Phải hiển thị badge cảnh báo');
  assert.ok(text.includes('Nghiệm không phải số nguyên đẹp sau 3 lần retry'), 'Phải hiển thị nội dung cảnh báo');
  assert.equal(text.includes('Đạt chuẩn'), false, 'Không được hiển thị Đạt chuẩn khi có cảnh báo');

  await harness.unmount();
});

test('Stage3ReviewPage hiển thị trạng thái chờ đồng bộ khi phiên chưa có dữ liệu biến thể thay vì báo sai câu thiếu', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi vừa sinh xong chờ tải chi tiết',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 2 },
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    exam_versions: [
      // exam_versions từ backend chỉ có metadata, chưa có mảng questions
      { id: 'v1', version_code: '101' },
      { id: 'v2', version_code: '102' },
    ],
  });

  const harness = renderStage3Page('sess-syncing-3', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  const text = harness.container.textContent;
  // Không được vội kết luận là câu hỏi "Chưa được sinh thành công"
  assert.equal(text.includes('Chưa được sinh thành công'), false, 'Không được kết luận câu thiếu khi dữ liệu đang chờ đồng bộ');
  assert.ok(text.includes('Đang đồng bộ dữ liệu chi tiết các mã đề từ Backend'), 'Phải hiển thị thẻ thông báo đang đồng bộ');

  await harness.unmount();
});

test('Stage3ReviewPage đối với phiên partial_generated nhưng API chưa nạp mảng variants: hiển thị trạng thái chờ đồng bộ, không kết luận câu đã lưu là chưa sinh', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi sinh dở chờ API chi tiết',
    status: 'partial_generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 2 },
    source_questions: [{ id: 'q1', question_no: 1 }, { id: 'q2', question_no: 2 }],
    exam_versions: [
      // Backend chỉ trả exam_versions metadata, chưa trả version_questions
      { id: 'v1', version_code: '101' },
      { id: 'v2', version_code: '102' },
    ],
  });

  const harness = renderStage3Page('sess-partial-syncing', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  const text = harness.container.textContent;
  // Không được kết luận bừa các câu là "Chưa được sinh thành công"
  assert.equal(text.includes('Chưa được sinh thành công'), false, 'Không được kết luận câu thiếu khi API chưa nạp mảng variants');
  assert.ok(text.includes('Đang đồng bộ dữ liệu chi tiết các mã đề từ Backend'), 'Phải hiển thị thẻ thông báo đang đồng bộ');

  await harness.unmount();
});

test('Stage3ReviewPage nút Phê duyệt & Xuất bản đề bị khóa khi phiên hoàn tất, hiển thị rõ đang chờ tích hợp Stage 3', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi hoàn tất',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'q1', question_no: 1 }],
    exam_versions: [
      {
        version_index: 1,
        questions: [{ question_no: 1, content: 'Toán 1', options: { A: '1' }, correct_key: 'A' }],
      },
    ],
  });

  const harness = renderStage3Page('sess-completed-btn', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  const approveBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Phê duyệt & Xuất bản đề'),
  );
  assert.ok(approveBtn, 'Phải có nút Phê duyệt & Xuất bản đề');
  assert.equal(approveBtn.getAttribute('disabled') !== null, true, 'Nút Phê duyệt & Xuất bản đề phải bị disabled');
  assert.ok(approveBtn.textContent.includes('Chờ Stage 3'), 'Nút phải ghi rõ Chờ Stage 3');

  await harness.unmount();
});

test('Stage3ReviewPage chuyển phiên A -> B: phản hồi A về muộn không được ghi đè phiên B', async () => {
  let resolveSessionA;
  let resolveSessionB;

  const mockLoadSession = (sId) => {
    if (sId === 'session-A') {
      return new Promise((resolve) => {
        resolveSessionA = () =>
          resolve({
            id: 'session-A',
            title: 'Đề thi A (Phiên cũ)',
            status: 'generated',
            subject: 'Toán',
            grade: 12,
            exam_versions: [
              {
                version_index: 1,
                questions: [{ question_no: 1, content: 'Đề A câu 1', options: { A: '1' }, correct_key: 'A' }],
              },
            ],
          });
      });
    }
    if (sId === 'session-B') {
      return new Promise((resolve) => {
        resolveSessionB = () =>
          resolve({
            id: 'session-B',
            title: 'Đề thi B (Phiên mới)',
            status: 'generated',
            subject: 'Toán',
            grade: 12,
            exam_versions: [
              {
                version_index: 1,
                questions: [{ question_no: 1, content: 'Đề B câu 1', options: { A: '2' }, correct_key: 'A' }],
              },
            ],
          });
      });
    }
    return Promise.reject(new Error('Unknown session'));
  };

  const harness = renderStage3Page('session-A', {
    loadSession: mockLoadSession,
  });

  // 1. Mở phiên A (đang tải)
  await harness.render();

  // 2. Chuyển sang phiên B trong khi A vẫn đang chờ mạng
  await harness.navigate('session-B');

  // 3. Phiên B hoàn thành tải trước
  await act(async () => {
    resolveSessionB();
  });

  // Màn hình hiển thị đề thi B
  assert.ok(harness.container.textContent.includes('Đề thi B (Phiên mới)'));
  assert.equal(harness.container.textContent.includes('Đề thi A (Phiên cũ)'), false);

  // 4. Phản hồi của A về muộn
  await act(async () => {
    resolveSessionA();
  });

  // Phản hồi của A phải bị bỏ qua, màn hình vẫn giữ nguyên đề thi B
  assert.ok(harness.container.textContent.includes('Đề thi B (Phiên mới)'));
  assert.equal(
    harness.container.textContent.includes('Đề thi A (Phiên cũ)'),
    false,
    'Phản hồi đến muộn của phiên A không được ghi đè phiên B',
  );

  await harness.unmount();
});

test('Stage3ReviewPage hủy bỏ phản hồi khi unmount trong lúc tải', async () => {
  let resolveSession;
  const mockLoadSession = () =>
    new Promise((resolve) => {
      resolveSession = () =>
        resolve({
          id: 'session-unmount',
          title: 'Đề thi unmount',
          status: 'generated',
        });
    });

  const harness = renderStage3Page('session-unmount', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  // Rời trang khi chưa tải xong
  await harness.unmount();

  // Phản hồi về sau khi đã unmount
  await act(async () => {
    resolveSession();
  });
});

test('Stage3ReviewPage: retry A thành công rồi chuyển B trước khi hết timer 1.2s phải giữ nguyên B, không kéo về A/stage2', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: `Đề thi ${sId}`,
    status: 'partial_generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 2 },
    source_questions: [{ id: 'q1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [] }],
  });

  const retryCalls = [];
  const mockRetryGen = async (sId) => {
    retryCalls.push(sId);
    return { ok: true };
  };

  const harness = renderStage3Page('session-A', {
    loadSession: mockLoadSession,
    retryGen: mockRetryGen,
  });

  await harness.render();
  assert.equal(harness.getLocation(), '/session/session-A/stage3');

  // 1. Bấm nút "Sinh bù tất cả câu thiếu" ở phiên A
  const retryAllBtn = Array.from(harness.container.querySelectorAll('button')).find((b) =>
    b.textContent.includes('Sinh bù tất cả câu thiếu'),
  );
  assert.ok(retryAllBtn);
  await act(async () => {
    retryAllBtn.click();
  });
  assert.equal(retryCalls.length, 1);
  assert.equal(retryCalls[0], 'session-A');

  // 2. Chuyển sang phiên B trước khi timer 1.2s hết hạn (sau 50ms)
  await new Promise((r) => setTimeout(r, 50));
  await harness.navigate('session-B');
  assert.equal(harness.getLocation(), '/session/session-B/stage3');

  // 3. Chờ thêm 1.4s (đã vượt quá mốc 1.2s của timer phiên A)
  await new Promise((r) => setTimeout(r, 1400));

  // Timer của A phải bị hủy: URL bắt buộc phải giữ nguyên ở phiên B!
  assert.equal(
    harness.getLocation(),
    '/session/session-B/stage3',
    'Timer điều hướng của phiên A không được kéo URL về /session/session-A/stage2',
  );

  await harness.unmount();
});

test('Stage3ReviewPage: retry A thành công rồi chuyển A -> B -> A trước khi timer chạy, thao tác cũ của A không được điều hướng', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: `Đề thi ${sId}`,
    status: 'partial_generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 2 },
    source_questions: [{ id: 'q1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [] }],
  });

  const retryCalls = [];
  const mockRetryGen = async (sId) => {
    retryCalls.push(sId);
    return { ok: true };
  };

  const harness = renderStage3Page('session-A', {
    loadSession: mockLoadSession,
    retryGen: mockRetryGen,
  });

  await harness.render();

  // Bấm sinh bù tất cả ở phiên A
  const retryAllBtn = Array.from(harness.container.querySelectorAll('button')).find((b) =>
    b.textContent.includes('Sinh bù tất cả câu thiếu'),
  );
  await act(async () => {
    retryAllBtn.click();
  });

  // Nhanh chóng chuyển sang B rồi quay lại A
  await new Promise((r) => setTimeout(r, 50));
  await harness.navigate('session-B');
  await new Promise((r) => setTimeout(r, 50));
  await harness.navigate('session-A');

  // Chờ vượt quá thời gian 1.2s của timer từ thao tác đầu tiên
  await new Promise((r) => setTimeout(r, 1400));

  // Vẫn phải ở lại Stage 3 của A (vì thao tác cũ đã bị vô hiệu hóa bởi bộ đếm lượt và hủy timer)
  assert.equal(
    harness.getLocation(),
    '/session/session-A/stage3',
    'Thao tác cũ không được kích hoạt điều hướng nhầm khi chuyển A -> B -> A',
  );

  await harness.unmount();
});

test('Stage3ReviewPage: retry A thành công rồi unmount trước khi timer chạy không gây lỗi và không điều hướng', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: `Đề thi ${sId}`,
    status: 'partial_generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 2 },
    source_questions: [{ id: 'q1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [] }],
  });

  const mockRetryGen = async () => ({ ok: true });

  const harness = renderStage3Page('session-unmount-timer', {
    loadSession: mockLoadSession,
    retryGen: mockRetryGen,
  });

  await harness.render();

  const retryAllBtn = Array.from(harness.container.querySelectorAll('button')).find((b) =>
    b.textContent.includes('Sinh bù tất cả câu thiếu'),
  );
  await act(async () => {
    retryAllBtn.click();
  });

  // Unmount ngay lập tức khi timer đang chờ
  await harness.unmount();

  // Chờ timer hết hạn
  await new Promise((r) => setTimeout(r, 1400));
});

test('Stage3ReviewPage: retry thông thường ở A không đổi phiên sẽ tự động điều hướng về /session/A/stage2 sau 1.2s', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: `Đề thi ${sId}`,
    status: 'partial_generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 2 },
    source_questions: [{ id: 'q1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [] }],
  });

  const mockRetryGen = async () => ({ ok: true });

  const harness = renderStage3Page('session-normal-retry', {
    loadSession: mockLoadSession,
    retryGen: mockRetryGen,
  });

  await harness.render();
  assert.equal(harness.getLocation(), '/session/session-normal-retry/stage3');

  const retryAllBtn = Array.from(harness.container.querySelectorAll('button')).find((b) =>
    b.textContent.includes('Sinh bù tất cả câu thiếu'),
  );
  await act(async () => {
    retryAllBtn.click();
  });

  // Chờ timer 1.2s hoàn tất
  await new Promise((r) => setTimeout(r, 1400));

  // Phải điều hướng thành công về Stage 2 của phiên hiện tại
  assert.equal(
    harness.getLocation(),
    '/session/session-normal-retry/stage2',
    'Phải tự động điều hướng về Stage 2 khi người dùng ở lại phiên',
  );

  await harness.unmount();
});

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

function renderStage3Page(
  sessionId,
  { loadSession, retryGen, acceptQuestionFn, regenerateQuestionFn } = {},
) {
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
                  acceptQuestionFn,
                  regenerateQuestionFn,
                }),
              }),
              React.createElement(Route, {
                path: '/session/:sessionId/stage2',
                element: React.createElement('div', null, 'Trang Stage 2 Đã Chuyển Hướng'),
              }),
              React.createElement(Route, {
                path: '/session/:sessionId/stage3/preview',
                element: React.createElement('div', null, 'Trang Stage 3 Preview Rà Bộ Đề'),
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

test('Stage3ReviewPage: Bấm "Kiểm tra đáp án" mở SolutionDialog hiển thị 2 cột, đúng key, lời giải KaTeX và đúng 2 nút', async () => {
  const sampleVariant = {
    id: 'var-q1-v1',
    question_no: 1,
    content: 'Tính tích phân $\\int_0^2 2x dx$',
    options: { A: '2', B: '4', C: '6', D: '8' },
    correct_key: 'B',
    solution_md: 'Ta có $\\int_0^2 2x dx = x^2\\Big|_0^2 = 4$.',
    status: 'pending_review',
  };

  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi Giải tích',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1, raw_content: 'Tính tích phân $\\int_0^1 x dx$' }],
    exam_versions: [{ version_index: 1, questions: [sampleVariant] }],
  });

  const harness = renderStage3Page('session-review-dialog', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  // 1. Tìm nút "Kiểm tra đáp án"
  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  assert.ok(inspectBtn, 'Phải có nút Kiểm tra đáp án');

  // 2. Bấm vào nút "Kiểm tra đáp án"
  await act(async () => {
    inspectBtn.click();
  });

  // 3. Kiểm tra modal SolutionDialog mở ra
  const dialog = harness.container.querySelector('[role="dialog"]');
  assert.ok(dialog, 'Modal SolutionDialog phải mở');

  const title = dialog.querySelector('#solution-dialog-title');
  assert.ok(title, 'Phải có tiêu đề dialog');
  assert.ok(title.textContent.includes('Kiểm tra đáp án · Câu 1 · Mã 101'));

  // 4. Kiểm tra hiển thị đáp án đúng và lời giải chi tiết
  const text = dialog.textContent;
  assert.ok(text.includes('Đáp án đúng: B'), 'Phải làm nổi bật đáp án đúng B');
  assert.ok(text.includes('Ta có'), 'Phải chứa nội dung lời giải chi tiết');

  // 5. Kiểm tra đúng 2 nút hành động: "Tạo lại" và "Duyệt biến thể" (KHÔNG có nút Revert, KHÔNG có modal lý do)
  const regenerateBtn = dialog.querySelector('[data-review-regenerate="true"]');
  const approveBtn = dialog.querySelector('[data-review-approve="true"]');

  assert.ok(regenerateBtn, 'Phải có nút Tạo lại');
  assert.equal(regenerateBtn.textContent.trim(), 'Tạo lại');
  assert.ok(approveBtn, 'Phải có nút Duyệt biến thể');
  assert.equal(approveBtn.textContent.trim(), 'Duyệt biến thể');

  assert.equal(text.includes('Hoàn nguyên'), false, 'KHÔNG có nút Hoàn nguyên (Revert)');
  assert.equal(text.includes('Lý do từ chối'), false, 'KHÔNG có modal hỏi lý do từ chối');

  await harness.unmount();
});

test('Stage3ReviewPage: Bấm "Duyệt biến thể" gọi accept API, chuyển sang "Đã duyệt" và tăng tiến độ ở thanh dưới cùng', async () => {
  const sampleVariant = {
    id: 'var-q1-v1',
    question_no: 1,
    content: 'Tính tích phân $\\int_0^2 2x dx$',
    options: { A: '2', B: '4', C: '6', D: '8' },
    correct_key: 'B',
    solution_md: 'Ta có $\\int_0^2 2x dx = 4$.',
    status: 'pending_review',
  };

  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi Giải tích',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [sampleVariant] }],
  });

  const acceptCalls = [];
  const mockAcceptQuestion = async (sId, qId) => {
    acceptCalls.push({ sId, qId });
    return { question_id: qId, question_status: 'approved' };
  };

  const harness = renderStage3Page('session-review-approve', {
    loadSession: mockLoadSession,
    acceptQuestionFn: mockAcceptQuestion,
  });

  await harness.render();

  // Ban đầu: chưa duyệt câu nào (0/1 câu), nút "Rà bộ đề" bị disable
  let bottomBarText = harness.container.textContent;
  assert.ok(bottomBarText.includes('Đã duyệt 0/1 câu'), 'Ban đầu là Đã duyệt 0/1 câu');
  const finalizeBtn = harness.container.querySelector('[data-review-finalize="true"]');
  assert.ok(finalizeBtn, 'Phải có nút Rà bộ đề');
  assert.equal(
    finalizeBtn.getAttribute('disabled') !== null,
    true,
    'Nút Rà bộ đề phải bị disable khi chưa duyệt đủ 100%',
  );

  // Mở modal Kiểm tra đáp án
  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  await act(async () => {
    inspectBtn.click();
  });

  const dialog = harness.container.querySelector('[role="dialog"]');
  const approveBtn = dialog.querySelector('[data-review-approve="true"]');

  // Bấm nút "Duyệt biến thể"
  await act(async () => {
    approveBtn.click();
  });

  // Kiểm tra gọi accept API
  assert.equal(acceptCalls.length, 1);
  assert.equal(acceptCalls[0].sId, 'session-review-approve');
  assert.equal(acceptCalls[0].qId, 'var-q1-v1');

  // Nút duyệt chuyển thành "Đã duyệt" và bị disabled
  assert.ok(approveBtn.textContent.includes('Đã duyệt'));
  assert.equal(approveBtn.getAttribute('disabled') !== null, true);

  // Tiến độ ở thanh dưới cùng cập nhật thành 1/1 câu
  bottomBarText = harness.container.textContent;
  assert.ok(bottomBarText.includes('Đã duyệt 1/1 câu'), 'Tiến độ phải cập nhật thành Đã duyệt 1/1 câu');

  // Nút "Rà bộ đề" được mở khóa (enabled) khi đủ 100%
  assert.equal(
    finalizeBtn.getAttribute('disabled'),
    null,
    'Nút Rà bộ đề phải được kích hoạt khi duyệt đủ 100%',
  );

  await harness.unmount();
});

test('Stage3ReviewPage: Bấm "Tạo lại" gọi reject API, giữ nguyên modal mở và hiển thị nội dung câu mới tạo', async () => {
  const sampleVariant = {
    id: 'var-q1-old',
    question_no: 1,
    content: 'Câu hỏi cũ: Cho tham số m',
    options: { A: '1', B: '2', C: '3', D: '4' },
    correct_key: 'A',
    solution_md: 'Lời giải cũ',
    status: 'pending_review',
  };

  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi Giải tích',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [sampleVariant] }],
  });

  const regenCalls = [];
  const mockRegenerateQuestion = async (sId, qId) => {
    regenCalls.push({ sId, qId });
    return {
      question_id: 'var-q1-new',
      regenerated_from_id: qId,
      status: 'pending_review',
      content: 'Câu hỏi mới: Cho tham số k',
      options: ['10', '20', '30', '99'],
      correct_key: 'D',
      solution_md: 'Lời giải mới chi tiết cho k = 99.',
    };
  };

  const harness = renderStage3Page('session-review-regen', {
    loadSession: mockLoadSession,
    regenerateQuestionFn: mockRegenerateQuestion,
  });

  await harness.render();

  // Mở modal Kiểm tra đáp án
  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  await act(async () => {
    inspectBtn.click();
  });

  const dialog = harness.container.querySelector('[role="dialog"]');
  assert.ok(dialog.textContent.includes('Câu hỏi cũ: Cho tham số m'));

  // Bấm nút "Tạo lại"
  const regenerateBtn = dialog.querySelector('[data-review-regenerate="true"]');
  await act(async () => {
    regenerateBtn.click();
  });

  // 1. Kiểm tra API reject/regenerate được gọi
  assert.equal(regenCalls.length, 1);
  assert.equal(regenCalls[0].sId, 'session-review-regen');
  assert.equal(regenCalls[0].qId, 'var-q1-old');

  // 2. Modal vẫn mở và nội dung được cập nhật sang câu mới tạo!
  const dialogAfter = harness.container.querySelector('[role="dialog"]');
  assert.ok(dialogAfter, 'Modal phải tiếp tục mở sau khi tạo lại');
  assert.ok(dialogAfter.textContent.includes('Câu hỏi mới: Cho tham số k'), 'Hiển thị đề bài mới');
  assert.ok(dialogAfter.textContent.includes('Đáp án đúng: D'), 'Hiển thị đáp án đúng D mới');
  assert.ok(dialogAfter.textContent.includes('Lời giải mới chi tiết cho k = 99.'), 'Hiển thị lời giải mới');

  // Nút duyệt biến thể sẵn sàng cho câu mới
  const approveBtn = dialogAfter.querySelector('[data-review-approve="true"]');
  assert.equal(approveBtn.getAttribute('disabled'), null);
  assert.equal(approveBtn.textContent.trim(), 'Duyệt biến thể');

  await harness.unmount();
});

test('Stage3ReviewPage: Hiển thị đúng badge fallback "Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc"', async () => {
  const fallbackVariant = {
    id: 'var-q1-fallback',
    question_no: 1,
    content: 'Câu hỏi gốc dùng tạm do AI lỗi',
    options: { A: '1', B: '2', C: '3', D: '4' },
    correct_key: 'A',
    solution_md: 'Lời giải gốc',
    status: 'pending_review',
    is_fallback: true,
    attempts: 4,
  };

  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi Có Fallback',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [fallbackVariant] }],
  });

  const harness = renderStage3Page('session-fallback-badge', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  const text = harness.container.textContent;
  assert.ok(
    text.includes('Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc'),
    'Phải hiển thị đúng chuỗi badge fallback trên thẻ câu hỏi',
  );

  // Mở modal kiểm tra đáp án cũng phải chứa thông báo này
  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  await act(async () => {
    inspectBtn.click();
  });

  const dialog = harness.container.querySelector('[role="dialog"]');
  assert.ok(
    dialog.textContent.includes('Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc'),
    'Modal cũng phải hiển thị đúng chuỗi badge fallback',
  );

  await harness.unmount();
});

test('Stage3ReviewPage: Bấm "Rà bộ đề" khi duyệt đủ 100% điều hướng tới /session/:id/stage3/preview', async () => {
  const approvedVariant = {
    id: 'var-q1-appr',
    question_no: 1,
    content: 'Câu hỏi đã duyệt',
    options: { A: '1', B: '2', C: '3', D: '4' },
    correct_key: 'A',
    status: 'approved',
  };

  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi đã duyệt toàn bộ',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [approvedVariant] }],
  });

  const harness = renderStage3Page('session-finalize-nav', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  const finalizeBtn = harness.container.querySelector('[data-review-finalize="true"]');
  assert.ok(finalizeBtn);
  assert.equal(finalizeBtn.getAttribute('disabled'), null, 'Duyệt 1/1 câu thì nút Rà bộ đề phải enabled');

  await act(async () => {
    finalizeBtn.click();
  });

  assert.equal(
    harness.getLocation(),
    '/session/session-finalize-nav/stage3/preview',
    'Phải điều hướng tới màn hình Rà bộ đề (/stage3/preview)',
  );

  await harness.unmount();
});

test('Stage3ReviewPage: Candidate bị fallback sau khi tạo lại thành công không còn hiển thị badge fallback', async () => {
  const fallbackVariant = {
    id: 'var-q1-fallback',
    question_no: 1,
    content: 'Câu gốc dùng tạm',
    options: { A: '1', B: '2', C: '3', D: '4' },
    correct_key: 'A',
    solution_md: 'Lời giải gốc',
    status: 'pending_review',
    is_fallback: true,
    attempts: 4,
  };

  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi fallback',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [fallbackVariant] }],
  });

  const mockRegenerate = async () => ({
    question_id: 'var-q1-fresh',
    status: 'pending_review',
    content: 'Biến thể sinh lại thành công hợp lệ',
    options: ['10', '20', '30', '40'],
    correct_key: 'B',
    solution_md: 'Lời giải mới không fallback.',
  });

  const harness = renderStage3Page('session-fallback-reset', {
    loadSession: mockLoadSession,
    regenerateQuestionFn: mockRegenerate,
  });

  await harness.render();

  // Ban đầu có badge fallback
  assert.ok(harness.container.textContent.includes('Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc'));

  // Mở modal và bấm "Tạo lại"
  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  await act(async () => {
    inspectBtn.click();
  });

  const dialog = harness.container.querySelector('[role="dialog"]');
  const regenBtn = dialog.querySelector('[data-review-regenerate="true"]');
  await act(async () => {
    regenBtn.click();
  });

  // Sau khi tạo lại thành công: badge fallback không còn tồn tại trên modal
  assert.equal(
    dialog.textContent.includes('Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc'),
    false,
    'Modal không được còn badge fallback khi biến thể mới đã sinh thành công',
  );

  // Đóng modal để kiểm tra trực tiếp question card ngoài giao diện chính
  const closeBtn = dialog.querySelector('button[aria-label="Đóng"]');
  await act(async () => {
    closeBtn.click();
  });

  assert.equal(harness.container.querySelector('[role="dialog"]'), null, 'Modal đã được đóng');

  // Question card ngoài giao diện chính cũng phải xóa sạch badge fallback
  assert.equal(
    harness.container.textContent.includes('Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc'),
    false,
    'Question card trên trang cũng không được còn badge fallback sau khi tạo lại thành công',
  );

  await harness.unmount();
});

test('Stage3ReviewPage: Idempotency-Key được sinh và giữ nguyên khi retry accept/reject', async () => {
  const sampleVariant = {
    id: 'var-idem-1',
    question_no: 1,
    content: 'Câu hỏi idempotency',
    options: { A: '1', B: '2', C: '3', D: '4' },
    correct_key: 'A',
    solution_md: 'Lời giải',
    status: 'pending_review',
  };

  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi test idempotency',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [{ version_index: 1, questions: [sampleVariant] }],
  });

  let acceptAttempts = 0;
  const capturedKeys = [];
  const mockAccept = async (sId, qId, key) => {
    capturedKeys.push(key);
    acceptAttempts += 1;
    if (acceptAttempts === 1) {
      throw new Error('Mạng bị chập chờn timeout');
    }
    return { question_id: qId, status: 'approved' };
  };

  const harness = renderStage3Page('session-idem-test', {
    loadSession: mockLoadSession,
    acceptQuestionFn: mockAccept,
  });

  await harness.render();

  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  await act(async () => {
    inspectBtn.click();
  });

  const dialog = harness.container.querySelector('[role="dialog"]');
  const approveBtn = dialog.querySelector('[data-review-approve="true"]');

  // Lần 1: Lỗi mạng
  await act(async () => {
    approveBtn.click();
  });

  assert.equal(capturedKeys.length, 1);
  const firstKey = capturedKeys[0];
  assert.ok(firstKey, 'Idempotency-Key phải được sinh ra');

  // Lần 2: Người dùng bấm retry
  await act(async () => {
    approveBtn.click();
  });

  assert.equal(capturedKeys.length, 2);
  assert.equal(capturedKeys[1], firstKey, 'Lần retry phải dùng lại chính xác Idempotency-Key của lần đầu');

  await harness.unmount();
});

test('Stage3ReviewPage: Chặn stale response của phiên cũ khi chuyển sang phiên mới', async () => {
  let resolveRegenA = null;
  const mockRegenerateA = () =>
    new Promise((resolve) => {
      resolveRegenA = resolve;
    });

  const sessionA = {
    id: 'session-A',
    title: 'Đề thi A',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [
      {
        version_index: 1,
        questions: [{ id: 'var-A1', question_no: 1, content: 'Đề câu A1', options: { A: '1' }, status: 'pending_review' }],
      },
    ],
  };

  const sessionB = {
    id: 'session-B',
    title: 'Đề thi B',
    status: 'generated',
    subject: 'Toán',
    grade: 12,
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [
      {
        version_index: 1,
        questions: [{ id: 'var-B1', question_no: 1, content: 'Đề câu B1', options: { A: '9' }, status: 'pending_review' }],
      },
    ],
  };

  const mockLoadSession = async (sId) => (sId === 'session-A' ? sessionA : sessionB);

  const harness = renderStage3Page('session-A', {
    loadSession: mockLoadSession,
    regenerateQuestionFn: mockRegenerateA,
  });

  await harness.render();

  // Mở modal trên session A và bấm Tạo lại
  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  await act(async () => {
    inspectBtn.click();
  });

  const dialog = harness.container.querySelector('[role="dialog"]');
  const regenBtn = dialog.querySelector('[data-review-regenerate="true"]');
  await act(async () => {
    regenBtn.click();
  });

  // Chuyển sang session B trong lúc request của A chưa xong
  await harness.navigate('session-B');

  // Bây giờ response của A mới trả về
  await act(async () => {
    resolveRegenA({
      question_id: 'var-A-new',
      status: 'pending_review',
      content: 'NỘI DUNG MỚI CỦA PHIÊN A',
      options: ['1', '2'],
    });
  });

  // Đảm bảo dữ liệu session B không bị ghi đè bởi response của A
  assert.equal(
    harness.container.textContent.includes('NỘI DUNG MỚI CỦA PHIÊN A'),
    false,
    'Response của phiên cũ không được cập nhật vào phiên mới',
  );

  await harness.unmount();
});

test('F01: Stage3ReviewPage tự động reset activeVersionTab về 1 khi chuyển sang phiên có ít mã đề hơn', async () => {
  const sessionA = {
    id: 'session-multi-version',
    status: 'generated',
    config: { n_versions: 3 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [
      {
        version_index: 1,
        code: '101',
        questions: [{ id: 'var-1-1', question_no: 1, content: 'Biến thể v1 câu 1', options: { A: '1' }, status: 'pending_review' }],
      },
      {
        version_index: 2,
        code: '102',
        questions: [{ id: 'var-2-1', question_no: 1, content: 'Biến thể v2 câu 1', options: { A: '2' }, status: 'pending_review' }],
      },
      {
        version_index: 3,
        code: '103',
        questions: [{ id: 'var-3-1', question_no: 1, content: 'Biến thể v3 câu 1', options: { A: '3' }, status: 'pending_review' }],
      },
    ],
  };

  const sessionB = {
    id: 'session-single-version',
    status: 'generated',
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [
      {
        version_index: 1,
        code: '101',
        questions: [{ id: 'var-b-1', question_no: 1, content: 'Biến thể duy nhất của B', options: { A: '9' }, status: 'pending_review' }],
      },
    ],
  };

  const mockLoad = async (id) => {
    return id === 'session-multi-version' ? sessionA : sessionB;
  };

  const harness = renderStage3Page('session-multi-version', { loadSession: mockLoad });
  await harness.render();

  // Bấm chọn tab mã đề 3
  const tabButtons = Array.from(harness.container.querySelectorAll('button')).filter((b) =>
    b.textContent.includes('Mã đề #103'),
  );
  assert.ok(tabButtons.length > 0, 'Phải có tab Mã đề #103');
  await act(async () => {
    tabButtons[0].click();
  });

  assert.ok(harness.container.textContent.includes('Biến thể v3 câu 1'));

  // Điều hướng sang session B (chỉ có 1 mã đề)
  await harness.navigate('session-single-version');

  // activeVersionTab phải tự động đưa về 1, hiển thị biến thể của B mà không báo missing
  assert.ok(harness.container.textContent.includes('Biến thể duy nhất của B'));
  assert.equal(harness.container.textContent.includes('Chưa tạo câu hỏi cho mã đề này'), false);

  await harness.unmount();
});

test('F02: Khi API rejectAndRegenerate trả solution_md null, biến thể mới không được kế thừa solution_md của câu cũ bị từ chối', async () => {
  const initialSession = {
    id: 'session-solution-fallback',
    status: 'generated',
    config: { n_versions: 1 },
    source_questions: [{ id: 'sq1', question_no: 1 }],
    exam_versions: [
      {
        version_index: 1,
        code: '101',
        questions: [
          {
            id: 'var-old',
            question_no: 1,
            content: 'Nội dung câu cũ',
            solution_md: 'LỜI GIẢI CÂU CŨ BỊ TỪ CHỐI',
            options: { A: 'A', B: 'B' },
            correct_key: 'A',
            status: 'pending_review',
          },
        ],
      },
    ],
  };

  const mockRegen = async () => ({
    question_id: 'var-new-no-solution',
    status: 'pending_review',
    content: 'Nội dung câu mới sinh lại',
    options: ['X', 'Y'],
    correct_key: 'X',
    solution_md: null,
    solution: null,
  });

  const harness = renderStage3Page('session-solution-fallback', {
    loadSession: async () => initialSession,
    regenerateQuestionFn: mockRegen,
  });
  await harness.render();

  // Mở modal Kiểm tra đáp án
  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  await act(async () => {
    inspectBtn.click();
  });

  const dialog = harness.container.querySelector('[role="dialog"]');
  assert.ok(dialog.textContent.includes('LỜI GIẢI CÂU CŨ BỊ TỪ CHỐI'));

  // Bấm Tạo lại
  const regenBtn = dialog.querySelector('[data-review-regenerate="true"]');
  await act(async () => {
    regenBtn.click();
  });

  // Sau khi tạo lại thành công với solution_md = null:
  // Modal phải hiển thị nội dung câu mới, và KHÔNG ĐƯỢC chứa lời giải cũ!
  assert.ok(dialog.textContent.includes('Nội dung câu mới sinh lại'));
  assert.equal(
    dialog.textContent.includes('LỜI GIẢI CÂU CŨ BỊ TỪ CHỐI'),
    false,
    'Tuyệt đối không được lấy lại solution_md của câu cũ khi API trả null',
  );

  await harness.unmount();
});

test('PR #54 Contract: Initial load dựng đúng ma trận câu hỏi và ứng viên từ GET /review/snapshot', async () => {
  const pr54Snapshot = {
    session_id: 'sess-snap-contract-1',
    session_status: 'generated',
    read_only: false,
    confirmation_id: 'conf-uuid-1',
    job_snapshot_id: 'job-uuid-1',
    confirmed_source_hash: 'hash-abc',
    freshness_token: 'token-xyz-1',
    progress: {
      expected_slots: 4,
      current_slots: 4,
      approved_slots: 0,
      missing_slots: 0,
      ready: false,
    },
    sources: [
      {
        source_question_id: 'src-q-1',
        question_no: 1,
        source_revision_id: 'rev-1',
        content: 'Nguồn 1: Tìm đạo hàm $y = x^3$',
        options: ['3x^2', 'x^2', '3x', '0'],
        correct_key: 'A',
        solution_md: 'Đạo hàm là $3x^2$.',
      },
      {
        source_question_id: 'src-q-2',
        question_no: 2,
        source_revision_id: 'rev-2',
        content: 'Nguồn 2: Tính tích phân $\\int_0^1 x dx$',
        options: ['1/2', '1', '2', '0'],
        correct_key: 'A',
        solution_md: 'Tích phân là $1/2$.',
      },
    ],
    versions: [
      {
        version_index: 1,
        version_code: '101',
        version_id: 'v-101',
        slots: [
          {
            source_question_id: 'src-q-1',
            question_no: 1,
            candidate: {
              candidate_id: 'cand-101-q1',
              status: 'pending_review',
              content: 'Biến thể 101-1: Tìm đạo hàm $y = 4x^3$',
              options: ['12x^2', '4x^2', '12x', '0'],
              correct_key: 'A',
              solution_md: 'Đạo hàm là $12x^2$.',
              has_warning: false,
              validation_report: { is_valid: true },
              validation_source: 'version_question',
              origin: 'ai_generated',
              is_reverted: false,
              updated_at: '2026-11-14T10:00:00Z',
            },
          },
          {
            source_question_id: 'src-q-2',
            question_no: 2,
            candidate: {
              candidate_id: 'cand-101-q2',
              status: 'pending_review',
              content: 'Biến thể 101-2: Tính tích phân $\\int_0^2 x dx$',
              options: ['1', '2', '3', '4'],
              correct_key: 'B',
              solution_md: 'Tích phân bằng 2.',
              has_warning: false,
              validation_report: { is_valid: true },
              validation_source: 'version_question',
              origin: 'ai_generated',
              is_reverted: false,
              updated_at: '2026-11-14T10:00:00Z',
            },
          },
        ],
      },
      {
        version_index: 2,
        version_code: '102',
        version_id: 'v-102',
        slots: [
          {
            source_question_id: 'src-q-1',
            question_no: 1,
            candidate: {
              candidate_id: 'cand-102-q1',
              status: 'pending_review',
              content: 'Biến thể 102-1: Tìm đạo hàm $y = 5x^3$',
              options: ['15x^2', '5x^2', '15x', '0'],
              correct_key: 'A',
              solution_md: 'Đạo hàm là $15x^2$.',
              has_warning: false,
              validation_report: { is_valid: true },
              validation_source: 'version_question',
              origin: 'ai_generated',
              is_reverted: false,
              updated_at: '2026-11-14T10:00:00Z',
            },
          },
          {
            source_question_id: 'src-q-2',
            question_no: 2,
            candidate: {
              candidate_id: 'cand-102-q2',
              status: 'pending_review',
              content: 'Biến thể 102-2: Tính tích phân $\\int_0^3 x dx$',
              options: ['9/2', '9', '3', '1'],
              correct_key: 'A',
              solution_md: 'Tích phân bằng $9/2$.',
              has_warning: false,
              validation_report: { is_valid: true },
              validation_source: 'version_question',
              origin: 'ai_generated',
              is_reverted: false,
              updated_at: '2026-11-14T10:00:00Z',
            },
          },
        ],
      },
    ],
  };

  const harness = renderStage3Page('sess-snap-contract-1', {
    loadSession: async () => pr54Snapshot,
  });
  await harness.render();

  const text = harness.container.textContent;
  // Tab mã đề
  assert.ok(text.includes('Mã đề #101'));
  assert.ok(text.includes('Mã đề #102'));

  // Nội dung ứng viên của Mã đề #101
  assert.ok(text.includes('Biến thể 101-1: Tìm đạo hàm'));
  assert.ok(text.includes('Biến thể 101-2: Tính tích phân'));
  assert.ok(text.includes('12x^2'));
  assert.ok(text.includes('Đạo hàm là'));

  // Tiến độ ban đầu
  assert.ok(text.includes('Đã duyệt 0/4 câu'));

  await harness.unmount();
});

test('PR #54 Contract: Approved state hiển thị đúng trạng thái đã duyệt và gọi acceptQuestion với candidate.candidate_id', async () => {
  const pr54SnapshotWithApproved = {
    session_id: 'sess-snap-contract-2',
    session_status: 'generated',
    read_only: false,
    sources: [
      {
        source_question_id: 'src-q-1',
        question_no: 1,
        content: 'Nguồn 1',
        options: ['A', 'B', 'C', 'D'],
        correct_key: 'A',
      },
      {
        source_question_id: 'src-q-2',
        question_no: 2,
        content: 'Nguồn 2',
        options: ['A', 'B', 'C', 'D'],
        correct_key: 'B',
      },
    ],
    versions: [
      {
        version_index: 1,
        version_code: '101',
        slots: [
          {
            source_question_id: 'src-q-1',
            question_no: 1,
            candidate: {
              candidate_id: 'cand-uuid-approved-1',
              status: 'approved',
              content: 'Biến thể 1 đã duyệt',
              options: ['A1', 'B1', 'C1', 'D1'],
              correct_key: 'A',
              solution_md: 'Lời giải 1',
              has_warning: false,
            },
          },
          {
            source_question_id: 'src-q-2',
            question_no: 2,
            candidate: {
              candidate_id: 'cand-uuid-pending-2',
              status: 'pending_review',
              content: 'Biến thể 2 chưa duyệt',
              options: ['A2', 'B2', 'C2', 'D2'],
              correct_key: 'B',
              solution_md: 'Lời giải 2',
              has_warning: false,
            },
          },
        ],
      },
    ],
  };

  const acceptCalls = [];
  const mockAccept = async (sId, qId, idempotencyKey) => {
    acceptCalls.push({ sId, qId, idempotencyKey });
    return { question_id: qId, question_status: 'approved' };
  };

  const harness = renderStage3Page('sess-snap-contract-2', {
    loadSession: async () => pr54SnapshotWithApproved,
    acceptQuestionFn: mockAccept,
  });
  await harness.render();

  // Slot 1 đã duyệt sẵn -> progress là 1/2 câu
  assert.ok(harness.container.textContent.includes('Đã duyệt 1/2 câu'));

  // Mở modal kiểm tra đáp án của câu 2
  const inspectButtons = harness.container.querySelectorAll('[data-review-inspect="true"]');
  assert.equal(inspectButtons.length, 2);
  await act(async () => {
    inspectButtons[1].click(); // Câu 2
  });

  const dialog = harness.container.querySelector('[role="dialog"]');
  assert.ok(dialog.textContent.includes('Biến thể 2 chưa duyệt'));

  // Bấm "Duyệt biến thể"
  const approveBtn = dialog.querySelector('[data-review-approve="true"]');
  await act(async () => {
    approveBtn.click();
  });

  // Xác nhận gọi accept với đúng candidate.candidate_id
  assert.equal(acceptCalls.length, 1);
  assert.equal(acceptCalls[0].sId, 'sess-snap-contract-2');
  assert.equal(acceptCalls[0].qId, 'cand-uuid-pending-2');
  assert.ok(acceptCalls[0].idempotencyKey);

  // Tiến độ cập nhật lên 2/2 câu
  assert.ok(harness.container.textContent.includes('Đã duyệt 2/2 câu'));

  await harness.unmount();
});

test('PR #54 Contract: Replacement sau khi regenerate gọi reject với candidate.candidate_id và refetch snapshot', async () => {
  let loadCallCount = 0;
  const initialSnapshot = {
    session_id: 'sess-snap-contract-3',
    session_status: 'generated',
    sources: [
      {
        source_question_id: 'src-q-1',
        question_no: 1,
        content: 'Nguồn 1',
        options: ['A', 'B', 'C', 'D'],
        correct_key: 'A',
      },
    ],
    versions: [
      {
        version_index: 1,
        version_code: '101',
        slots: [
          {
            source_question_id: 'src-q-1',
            question_no: 1,
            candidate: {
              candidate_id: 'cand-uuid-original',
              status: 'pending_review',
              content: 'Nội dung ban đầu của ứng viên',
              options: ['A1', 'B1', 'C1', 'D1'],
              correct_key: 'A',
              solution_md: 'Lời giải ban đầu',
              has_warning: false,
            },
          },
        ],
      },
    ],
  };

  const refreshedSnapshot = {
    ...initialSnapshot,
    freshness_token: 'token-after-regen',
    versions: [
      {
        version_index: 1,
        version_code: '101',
        slots: [
          {
            source_question_id: 'src-q-1',
            question_no: 1,
            candidate: {
              candidate_id: 'cand-uuid-replacement',
              status: 'pending_review',
              content: 'Nội dung ứng viên thay thế từ snapshot sau regenerate',
              options: ['X', 'Y', 'Z', 'T'],
              correct_key: 'C',
              solution_md: 'Lời giải ứng viên thay thế',
              has_warning: false,
              origin: 'regenerated',
            },
          },
        ],
      },
    ],
  };

  const mockLoadSession = async () => {
    loadCallCount++;
    return loadCallCount === 1 ? initialSnapshot : refreshedSnapshot;
  };

  const rejectCalls = [];
  const mockReject = async (sId, qId, idempotencyKey) => {
    rejectCalls.push({ sId, qId, idempotencyKey });
    return {
      question_id: 'cand-uuid-replacement',
      regenerated_from_id: qId,
      status: 'pending_review',
      content: 'Nội dung ứng viên thay thế từ snapshot sau regenerate',
      options: ['X', 'Y', 'Z', 'T'],
      correct_key: 'C',
      solution_md: 'Lời giải ứng viên thay thế',
    };
  };

  const harness = renderStage3Page('sess-snap-contract-3', {
    loadSession: mockLoadSession,
    regenerateQuestionFn: mockReject,
  });
  await harness.render();

  assert.ok(harness.container.textContent.includes('Nội dung ban đầu của ứng viên'));

  // Mở modal
  const inspectBtn = harness.container.querySelector('[data-review-inspect="true"]');
  await act(async () => {
    inspectBtn.click();
  });

  // Bấm Tạo lại
  const dialog = harness.container.querySelector('[role="dialog"]');
  const regenBtn = dialog.querySelector('[data-review-regenerate="true"]');
  await act(async () => {
    regenBtn.click();
  });

  // Xác nhận gọi reject với đúng candidate.candidate_id ('cand-uuid-original')
  assert.equal(rejectCalls.length, 1);
  assert.equal(rejectCalls[0].sId, 'sess-snap-contract-3');
  assert.equal(rejectCalls[0].qId, 'cand-uuid-original');

  // Xác nhận loadSession được refetch
  assert.ok(loadCallCount >= 2, 'Phải tự động refetch snapshot sau khi regenerate');

  // Modal và màn hình hiển thị ứng viên thay thế
  assert.ok(dialog.textContent.includes('Nội dung ứng viên thay thế từ snapshot sau regenerate'));
  assert.ok(dialog.textContent.includes('Đáp án đúng: C'));

  await harness.unmount();
});

test('PR #54 Contract: Missing slot (candidate: null) hiển thị trạng thái chưa sinh, không tính vào approvedCount', async () => {
  const pr54PartialSnapshot = {
    session_id: 'sess-snap-contract-4',
    session_status: 'partial_generated',
    read_only: true,
    progress: {
      expected_slots: 2,
      current_slots: 1,
      approved_slots: 1,
      missing_slots: 1,
      ready: false,
    },
    sources: [
      {
        source_question_id: 'src-q-1',
        question_no: 1,
        content: 'Nguồn 1: Phương trình bậc 2',
        options: ['1', '2', '3', '4'],
        correct_key: 'A',
      },
      {
        source_question_id: 'src-q-2',
        question_no: 2,
        content: 'Nguồn 2: Hình không gian Oxyz',
        options: ['A', 'B', 'C', 'D'],
        correct_key: 'B',
      },
    ],
    versions: [
      {
        version_index: 1,
        version_code: '101',
        slots: [
          {
            source_question_id: 'src-q-1',
            question_no: 1,
            candidate: {
              candidate_id: 'cand-uuid-slot-1',
              status: 'approved',
              content: 'Biến thể câu 1 đã sinh xong và được duyệt',
              options: ['1', '2', '3', '4'],
              correct_key: 'A',
              solution_md: 'Lời giải câu 1',
              has_warning: false,
            },
          },
          {
            source_question_id: 'src-q-2',
            question_no: 2,
            candidate: null, // missing slot! Chưa sinh thành công
          },
        ],
      },
    ],
  };

  const harness = renderStage3Page('sess-snap-contract-4', {
    loadSession: async () => pr54PartialSnapshot,
  });
  await harness.render();

  const text = harness.container.textContent;

  // 1. Câu 1 hiển thị bình thường với badge Đã duyệt
  assert.ok(text.includes('Biến thể câu 1 đã sinh xong và được duyệt'));

  // 2. Câu 2 (candidate: null) hiển thị card chưa sinh và nút Sinh bù câu này
  assert.ok(
    text.includes('Câu 2 (Mã đề #101) — Chưa được sinh thành công'),
    'candidate: null phải hiển thị trạng thái Chưa được sinh thành công'
  );
  const retryBtn = Array.from(harness.container.querySelectorAll('button')).find(
    (b) => b.textContent.includes('Sinh bù câu này')
  );
  assert.ok(retryBtn, 'Missing slot phải có nút Sinh bù câu này');

  // 3. Approved count: chỉ tính 1/2 câu (slot missing KHÔNG ĐƯỢC tính vào approvedCount)
  assert.ok(text.includes('Đã duyệt 1/2 câu'), 'Missing slot tuyệt đối không được tính là approved');

  // 4. Nút Rà bộ đề bị disabled
  const finalizeBtn = harness.container.querySelector('[data-review-finalize="true"]');
  assert.equal(
    finalizeBtn.getAttribute('disabled') !== null,
    true,
    'Nút Rà bộ đề phải bị vô hiệu hóa khi còn missing slot'
  );

  await harness.unmount();
});

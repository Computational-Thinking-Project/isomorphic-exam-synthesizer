import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

register('../../test-loader.mjs', import.meta.url);
const { default: Stage3ReviewPage } = await import('./Stage3ReviewPage.jsx');

function renderStage3Page(sessionId, { loadSession, retryGen } = {}) {
  const container = document.createElement('div');
  const root = createRoot(container);

  return {
    container,
    async render() {
      await act(async () => {
        root.render(
          React.createElement(
            MemoryRouter,
            { initialEntries: [`/session/${sessionId}/stage3`] },
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

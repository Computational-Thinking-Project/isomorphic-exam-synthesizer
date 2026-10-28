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

test('Stage3ReviewPage hiển thị cảnh báo partial_generated, khóa xuất bản và hiển thị nút Tạo lại câu này cho câu thiếu', async () => {
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

  // 3. Kiểm tra câu 1 đã sinh có đầy đủ nội dung
  assert.ok(text.includes('Câu 1 (Mã đề #101)'), 'Phải hiển thị Câu 1');

  // 4. Kiểm tra câu 2 bị thiếu hiển thị nút Tạo lại câu này
  assert.ok(text.includes('Câu 2 (Mã đề #101) — Chưa được sinh thành công'), 'Phải báo Câu 2 chưa hoàn tất');
  const regenBtns = Array.from(harness.container.querySelectorAll('button')).filter(
    (b) => b.textContent.includes('Tạo lại câu này'),
  );
  assert.ok(regenBtns.length >= 2, 'Cả câu đã sinh và câu bị thiếu đều có nút Tạo lại');

  // Bấm nút "Tạo lại câu này" trên câu 2 bị thiếu
  await act(async () => {
    regenBtns[1].click();
  });

  assert.equal(retryCalls.length, 1);
  assert.equal(retryCalls[0], 'sess-partial-3');

  await harness.unmount();
});

test('Stage3ReviewPage phiên hoàn tất 100% cho phép duyệt và phê duyệt đề thi', async () => {
  const mockLoadSession = async (sId) => ({
    id: sId,
    title: 'Đề thi Toán 12 — Hoàn tất 100%',
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
          },
        ],
      },
    ],
  });

  const harness = renderStage3Page('sess-complete-3', {
    loadSession: mockLoadSession,
  });

  await harness.render();

  const text = harness.container.textContent;
  assert.ok(!text.includes('partial_generated'), 'Không được hiện cảnh báo partial_generated khi hoàn thành 100%');
  assert.ok(text.includes('Phê duyệt & Xuất bản đề'), 'Phải có nút Phê duyệt xuất bản đề');

  await harness.unmount();
});

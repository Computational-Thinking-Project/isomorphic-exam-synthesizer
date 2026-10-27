import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

// Đăng ký test-loader để Node import component .jsx
register('../../test-loader.mjs', import.meta.url);
const { default: Stage2ConfigCard } = await import('./Stage2ConfigCard.jsx');

const sampleSession = {
  id: 'test-session-001',
  title: 'Đề kiểm tra Giải tích 12',
  subject: 'Toán',
  grade: 12,
  status: 'blueprinted',
  source_questions: [
    { id: 'q1', question_no: 1, question_text: 'Câu 1' },
    { id: 'q2', question_no: 2, question_text: 'Câu 2' },
    { id: 'q3', question_no: 3, question_text: 'Câu 3' },
    { id: 'q4', question_no: 4, question_text: 'Câu 4' },
    { id: 'q5', question_no: 5, question_text: 'Câu 5' },
  ],
  blueprint_summary: {
    total_questions: 5,
    supported_modes: [
      {
        id: 'parameter_variation',
        label: 'Thay đổi số liệu / tham số',
        description: 'Biến thiên tham số số học',
        question_count: 5,
        is_available: true,
      },
      {
        id: 'context_swap',
        label: 'Đổi ngữ cảnh thực tế',
        description: 'Đổi tình huống thực tế',
        question_count: 5,
        is_available: true,
      },
      {
        id: 'variable_inversion',
        label: 'Hoán đổi ẩn số',
        description: 'Đổi vị trí ẩn số',
        question_count: 2,
        is_available: false,
        unavailable_reason: 'Chưa đủ điều kiện cho đề này',
      },
    ],
  },
};

function renderCard(props) {
  const container = document.createElement('div');
  const root = createRoot(container);

  return {
    container,
    async render(nextProps = props) {
      await act(async () => {
        root.render(React.createElement(Stage2ConfigCard, nextProps));
      });
    },
    async unmount() {
      await act(async () => {
        root.unmount();
      });
    },
  };
}

test('Stage2ConfigCard hiển thị đầy đủ thông tin đề nguồn và 4 lựa chọn số lượng mã đề', async () => {
  const harness = renderCard({ session: sampleSession });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Đề kiểm tra Giải tích 12'), 'Phải hiển thị tiêu đề phiên');
  assert.ok(text.includes('5 câu hỏi'), 'Phải hiển thị số câu hỏi đề nguồn');
  assert.ok(text.includes('Toán • Khối 12'), 'Phải hiển thị môn học và khối');

  // Kiểm tra 4 nút lựa chọn N in [1, 4]
  const buttons = harness.container.querySelectorAll('button');
  const nButtons = buttons.filter((b) => ['1', '2', '3', '4'].includes(b.textContent.trim().charAt(0)));
  assert.equal(nButtons.length, 4, 'Phải có 4 nút chọn số lượng mã đề');

  await harness.unmount();
});

test('Stage2ConfigCard hiển thị đúng danh sách chế độ biến thể và vô hiệu hóa chế độ không khả dụng', async () => {
  const harness = renderCard({ session: sampleSession });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Thay đổi số liệu / tham số'));
  assert.ok(text.includes('Đổi ngữ cảnh thực tế'));
  assert.ok(text.includes('Hoán đổi ẩn số'));
  assert.ok(text.includes('Chưa đủ điều kiện cho đề này'), 'Phải nêu lý do không khả dụng');

  const checkboxes = harness.container.querySelectorAll('input[type="checkbox"]');
  const inversionCheckbox = checkboxes.find((c) => c.getAttribute('id') === 'mode-variable_inversion');
  assert.ok(inversionCheckbox, 'Phải có checkbox cho variable_inversion');
  assert.equal(inversionCheckbox.getAttribute('disabled') !== null, true, 'variable_inversion phải bị disable');

  await harness.unmount();
});

test('Stage2ConfigCard chỉ cung cấp tùy chọn shuffle_questions và không có shuffle_options', async () => {
  const harness = renderCard({ session: sampleSession });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('shuffle_questions'), 'Phải có tùy chọn shuffle_questions');
  assert.equal(text.includes('shuffle_options'), false, 'Tuyệt đối không có shuffle_options theo yêu cầu');

  const shuffleCb = harness.container.querySelector('#shuffle-questions-checkbox');
  assert.ok(shuffleCb, 'Phải có checkbox id shuffle-questions-checkbox');
  assert.equal(shuffleCb.checked, true, 'shuffle_questions mặc định là Bật');

  await harness.unmount();
});

test('Stage2ConfigCard tự động cập nhật thẻ tóm tắt khi thay đổi số lượng mã đề', async () => {
  const harness = renderCard({ session: sampleSession });
  await harness.render();

  // Mặc định N = 2, total = 5 -> tổng 10 câu
  let text = harness.container.textContent;
  assert.ok(text.includes('2 mã đề'), 'Mặc định chọn 2 mã đề');
  assert.ok(text.includes('10 câu hỏi biến thể'), 'Tổng số câu biến thể: 2 * 5 = 10');

  // Bấm chọn N = 4
  const buttons = harness.container.querySelectorAll('button');
  const btn4 = buttons.find((b) => b.textContent.includes('4 mã đề so le') || b.textContent.trim().startsWith('4'));
  assert.ok(btn4, 'Tìm thấy nút chọn 4 mã đề');

  await act(async () => {
    btn4.click();
  });

  text = harness.container.textContent;
  assert.ok(text.includes('4 mã đề'), 'Đã cập nhật sang 4 mã đề');
  assert.ok(text.includes('20 câu hỏi biến thể'), 'Tổng số câu biến thể: 4 * 5 = 20');

  await harness.unmount();
});

test('Stage2ConfigCard nộp cấu hình thành công với đúng payload quy ước', async () => {
  let submittedPayload = null;

  const harness = renderCard({
    session: sampleSession,
    onSubmit: async (payload) => {
      submittedPayload = payload;
    },
  });
  await harness.render();

  const form = harness.container.querySelector('form');
  assert.ok(form, 'Phải có form element');

  await act(async () => {
    form.dispatchEvent({
      type: 'submit',
      bubbles: true,
      cancelable: true,
      preventDefault: () => {},
    });
  });

  assert.ok(submittedPayload, 'onSubmit phải được gọi');
  assert.equal(submittedPayload.num_versions, 2);
  assert.deepEqual(submittedPayload.variation_modes, ['parameter_variation', 'context_swap']);
  assert.deepEqual(submittedPayload.ordering_preferences, {
    shuffle_questions: true,
  });

  await harness.unmount();
});

test('Stage2ConfigCard hiển thị cảnh báo lỗi khi có xung đột ERR_CONFIG_CONFLICT', async () => {
  const harness = renderCard({
    session: sampleSession,
    error: 'Cấu hình xung đột với Blueprint của đề bài (ERR_CONFIG_CONFLICT)',
  });
  await harness.render();

  const alertBox = harness.container.querySelector('[role="alert"]');
  assert.ok(alertBox, 'Phải có role="alert" thông báo lỗi');
  assert.ok(alertBox.textContent.includes('ERR_CONFIG_CONFLICT'));

  await harness.unmount();
});

test('Stage2ConfigCard khóa nút nộp khi isSubmitting = true', async () => {
  const harness = renderCard({
    session: sampleSession,
    isSubmitting: true,
  });
  await harness.render();

  const submitBtn = harness.container.querySelector('button[type="submit"]');
  assert.ok(submitBtn, 'Có nút submit');
  assert.equal(submitBtn.getAttribute('disabled') !== null, true, 'Nút submit phải bị disabled');
  assert.ok(submitBtn.textContent.includes('Đang lưu cấu hình'));

  await harness.unmount();
});

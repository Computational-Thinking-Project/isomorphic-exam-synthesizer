import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

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
    is_ready: true,
    total_questions: 5,
    supported_modes: [
      {
        id: 'parameter_variation',
        label: 'Thay đổi số liệu / tham số',
        question_count: 5,
        is_available: true,
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

test('Stage2ConfigCard hiển thị đúng Stepper 3 bước chuẩn và thông tin đề gốc đã xác nhận', async () => {
  const harness = renderCard({ session: sampleSession });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('01. Chuẩn bị đề gốc'), 'Phải có bước 1');
  assert.ok(text.includes('02. Cấu hình và tạo mã'), 'Phải có bước 2');
  assert.ok(text.includes('03. Duyệt và sử dụng'), 'Phải có bước 3');
  assert.ok(text.includes('5 câu gốc đã xác nhận'), 'Phải hiển thị 5 câu gốc đã xác nhận');
  assert.ok(text.includes('Tạo mã đề'), 'Phải có tiêu đề Tạo mã đề');

  await harness.unmount();
});

test('Stage2ConfigCard hiển thị ô nhập duy nhất với nhãn Số mã đề (N ∈ [1, 4]) * và thẻ Workload', async () => {
  const harness = renderCard({ session: sampleSession });
  await harness.render();

  const label = harness.container.querySelector('label[for="code-count"]');
  assert.ok(label, 'Phải có label cho code-count');
  assert.ok(label.textContent.includes('Số mã đề (N ∈ [1, 4])'), 'Nhãn phải chứa Số mã đề (N ∈ [1, 4])');

  const input = harness.container.querySelector('#code-count');
  assert.ok(input, 'Phải có ô nhập #code-count');
  assert.equal(input.value, '2', 'Mặc định ban đầu là 2 mã đề');

  const workload = harness.container.querySelector('.workload');
  assert.ok(workload, 'Phải có thẻ workload');
  assert.ok(workload.textContent.includes('5 câu/mã × 2 mã đề = 10 biến thể'));

  await harness.unmount();
});

test('Stage2ConfigCard TUYỆT ĐỐI KHÔNG có checkbox shuffle hay variation mode selector trên UI (Issue #94)', async () => {
  const harness = renderCard({ session: sampleSession });
  await harness.render();

  const shuffleQuestionsCb = harness.container.querySelector('#shuffle-questions-checkbox');
  assert.equal(shuffleQuestionsCb, null, 'Không được có checkbox shuffle-questions');

  const shuffleOptionsCb = harness.container.querySelector('#shuffle-options-checkbox');
  assert.equal(shuffleOptionsCb, null, 'Không được có checkbox shuffle-options');

  const modeBadges = harness.container.querySelectorAll('[id^="mode-badge-"]');
  assert.equal(modeBadges.length, 0, 'Không được có danh sách variation mode selector');

  await harness.unmount();
});

test('Stage2ConfigCard gửi đúng payload chuẩn: n_versions, active_variation_modes: [], ordering_preferences', async () => {
  let submittedPayload = null;
  const harness = renderCard({
    session: sampleSession,
    onSubmit: async (payload) => {
      submittedPayload = payload;
    },
  });
  await harness.render();

  const input = harness.container.querySelector('#code-count');
  await act(async () => {
    input.value = '3';
    input.dispatchEvent({ type: 'input', bubbles: true, target: input });
    input.dispatchEvent({ type: 'change', bubbles: true, target: input });
  });

  const form = harness.container.querySelector('form');
  await act(async () => {
    form.dispatchEvent({ type: 'submit', bubbles: true, cancelable: true, preventDefault: () => {} });
  });

  assert.ok(submittedPayload, 'Form phải submit thành công');
  assert.equal(submittedPayload.n_versions, 3);
  assert.deepEqual(submittedPayload.active_variation_modes, [], 'Gửi mảng rỗng active_variation_modes');
  assert.deepEqual(submittedPayload.ordering_preferences, {
    shuffle_questions: false,
    shuffle_options: false,
  });

  await harness.unmount();
});

test('Stage2ConfigCard hiển thị thông báo chỉ đọc khi phiên cũ có shuffle_options = true và bảo toàn trong payload', async () => {
  let submittedPayload = null;
  const harness = renderCard({
    session: sampleSession,
    initialConfig: {
      n_versions: 2,
      ordering_preferences: {
        shuffle_questions: true,
        shuffle_options: true,
      },
    },
    onSubmit: async (payload) => {
      submittedPayload = payload;
    },
  });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(
    text.includes('Phiên này đang bật xáo trộn đáp án trong toàn bộ mã đề'),
    'Phải có thông báo chỉ đọc khi phiên cũ bật shuffle_options',
  );
  // Không có checkbox
  assert.equal(harness.container.querySelector('input[type="checkbox"]'), null);

  const form = harness.container.querySelector('form');
  await act(async () => {
    form.dispatchEvent({ type: 'submit', bubbles: true, cancelable: true, preventDefault: () => {} });
  });

  assert.ok(submittedPayload);
  assert.equal(submittedPayload.ordering_preferences.shuffle_questions, true);
  assert.equal(submittedPayload.ordering_preferences.shuffle_options, true);

  await harness.unmount();
});

test('Stage2ConfigCard báo lỗi inline khi nhập số ngoài khoảng [1, 4] hoặc không phải số', async () => {
  const harness = renderCard({ session: sampleSession });
  await harness.render();

  const input = harness.container.querySelector('#code-count');
  await act(async () => {
    input.value = '5';
    input.dispatchEvent({ type: 'input', bubbles: true, target: input });
    input.dispatchEvent({ type: 'change', bubbles: true, target: input });
    input.dispatchEvent({ type: 'blur', bubbles: true, target: input });
  });

  const text = harness.container.textContent;
  assert.ok(text.includes('Số mã đề (N) phải nằm trong khoảng từ 1 đến 4.'));

  const submitBtn = harness.container.querySelector('button[type="submit"]');
  assert.equal(submitBtn.getAttribute('disabled') !== null, true, 'Nút submit phải bị vô hiệu hóa khi N=5');

  await harness.unmount();
});

test('Stage2ConfigCard hỗ trợ fallback initialNumVersions từ Cài đặt cá nhân (PR #106)', async () => {
  const harness = renderCard({
    session: sampleSession,
    initialNumVersions: 4,
  });
  await harness.render();

  const input = harness.container.querySelector('#code-count');
  assert.equal(input.value, '4', 'Ưu tiên lấy initialNumVersions = 4');

  await harness.unmount();
});

test('Stage2ConfigCard khóa submit và hiển thị cảnh báo khi Blueprint chưa sẵn sàng', async () => {
  const sessionUnready = {
    ...sampleSession,
    blueprint_summary: {
      is_ready: false,
      total_questions: 5,
    },
  };

  const harness = renderCard({ session: sessionUnready });
  await harness.render();

  const text = harness.container.textContent;
  assert.ok(text.includes('Chưa có thông tin cấu trúc đề khả dụng') || text.includes('Chưa có thông tin Blueprint khả dụng'));

  const submitBtn = harness.container.querySelector('button[type="submit"]');
  assert.equal(submitBtn.getAttribute('disabled') !== null, true);

  await harness.unmount();
});

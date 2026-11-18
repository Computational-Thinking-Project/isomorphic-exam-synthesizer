import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useNavigate, useLocation } from 'react-router-dom';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { api } from '../../services/api.js';
import { GOLDEN_PREVIEW_FIXTURE } from '../../services/stage3PreviewService.js';

ensureDomEnvironment();

register('../../test-loader.mjs', import.meta.url);
const { default: Stage3PreviewPage } = await import('./Stage3PreviewPage.jsx');

function renderPreviewPage(sessionId = '00000000-0000-0000-0000-000000000001') {
  const container = document.createElement('div');
  const root = createRoot(container);
  let navigateFn = null;
  let currentLocation = `/session/${sessionId}/stage3/preview`;

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
    async navigate(path) {
      await act(async () => {
        navigateFn(path);
      });
    },
    async render() {
      await act(async () => {
        root.render(
          React.createElement(
            MemoryRouter,
            { initialEntries: [`/session/${sessionId}/stage3/preview`] },
            React.createElement(NavigationCapture),
            React.createElement(
              Routes,
              null,
              React.createElement(Route, {
                path: '/session/:sessionId/stage3/preview',
                element: React.createElement(Stage3PreviewPage),
              }),
              React.createElement(Route, {
                path: '/session/:sessionId/stage3',
                element: React.createElement('div', null, 'Trang Stage 3 Review'),
              }),
              React.createElement(Route, {
                path: '/session/:sessionId/export',
                element: React.createElement('div', null, 'Trang Stage 4 Export'),
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

test('Stage3PreviewPage: Hiển thị trạng thái chờ khi đang tải dữ liệu', async () => {
  const originalGet = api.get;
  // Giữ request pending
  api.get = () => new Promise(() => {});

  const harness = renderPreviewPage('session-loading');
  try {
    await harness.render();
    assert.match(harness.container.textContent, /Đang tải bản chiếu xem trước đề thi/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Xử lý lỗi 409 ERR_SHUFFLE_REQUIRED hiển thị thẻ Chờ chốt thứ tự, 2 checkbox độc lập mặc định OFF/OFF và nút "Áp dụng & Xem trước"', async () => {
  const originalGet = api.get;
  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      const error = new Error('Cần thực hiện xáo trộn đề trước khi xem bản chiếu');
      error.response = {
        status: 409,
        data: {
          error_code: 'ERR_SHUFFLE_REQUIRED',
          detail: 'Cần thực hiện xáo trộn đề trước khi xem bản chiếu',
        },
      };
      throw error;
    }
    return { data: { id: 'session-needs-shuffle', status: 'reviewed' } };
  };

  const harness = renderPreviewPage('session-needs-shuffle');
  try {
    await harness.render();
    assert.match(harness.container.textContent, /Toàn bộ câu hỏi đã được duyệt thành công/);
    assert.match(harness.container.textContent, /Chờ chốt thứ tự/);

    // 2 checkbox độc lập theo Issue #45
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');
    assert.ok(qCheckbox, 'Checkbox xáo trộn thứ tự câu hỏi phải hiển thị');
    assert.ok(optCheckbox, 'Checkbox xáo trộn thứ tự đáp án phải hiển thị');
    assert.equal(qCheckbox.checked, false, 'Checkbox câu hỏi mặc định OFF (false) theo Issue #45');
    assert.equal(optCheckbox.checked, false, 'Checkbox đáp án mặc định OFF (false) theo Issue #45');

    // Nút hành động duy nhất: "Áp dụng & Xem trước"
    const shuffleBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(shuffleBtn, 'Nút Áp dụng & Xem trước phải hiển thị');
    assert.match(shuffleBtn.textContent, /Áp dụng & Xem trước/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Tổ hợp 1 (OFF/OFF) - Bấm "Áp dụng & Xem trước" với mặc định false/false gửi PATCH false/false và POST shuffle, sau đó nạp lại bản xem trước (Golden Baseline)', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let previewGetCalls = 0;
  const calls = [];

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      previewGetCalls += 1;
      if (previewGetCalls === 1) {
        const error = new Error('Shuffle required');
        error.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
        throw error;
      }
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-off-test' } };
    }
    return { data: { id: 'session-off-test', status: 'reviewed' } };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    return { data: { session_id: 'session-off-test', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-off-test');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');
    assert.equal(qCheckbox.checked, false);
    assert.equal(optCheckbox.checked, false);

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(applyBtn, 'Nút Áp dụng & Xem trước phải hiển thị');

    await act(async () => {
      applyBtn.click();
    });

    assert.equal(calls.length, 2);
    assert.equal(calls[0].type, 'patch');
    assert.deepEqual(calls[0].payload, { shuffle_questions: false, shuffle_options: false });
    assert.equal(calls[1].type, 'post');
    assert.equal(calls[1].url, '/sessions/session-off-test/finalize/shuffle');

    // Sau khi chốt thứ tự gốc, màn hình nạp lại dữ liệu xem trước
    assert.match(harness.container.textContent, /Bản xem trước — Mã đề 101/);
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Tổ hợp 4 (ON/ON) - Bật cả 2 checkbox rồi bấm "Áp dụng & Xem trước" gửi PATCH true/true và POST shuffle, sau đó nạp lại bản xem trước', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let previewGetCalls = 0;
  const calls = [];

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      previewGetCalls += 1;
      if (previewGetCalls === 1) {
        const error = new Error('Shuffle required');
        error.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
        throw error;
      }
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-123' } };
    }
    return { data: { id: 'session-123', status: 'reviewed' } };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    return { data: { session_id: 'session-123', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-123');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');

    // Bật cả 2 checkbox
    await act(async () => {
      qCheckbox.click();
    });
    await act(async () => {
      optCheckbox.click();
    });
    assert.equal(qCheckbox.checked, true);
    assert.equal(optCheckbox.checked, true);

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(applyBtn);

    await act(async () => {
      applyBtn.click();
    });

    assert.equal(calls.length, 2);
    assert.equal(calls[0].type, 'patch');
    assert.deepEqual(calls[0].payload, { shuffle_questions: true, shuffle_options: true });
    assert.equal(calls[1].type, 'post');
    assert.equal(calls[1].url, '/sessions/session-123/finalize/shuffle');

    // Sau khi shuffle xong, màn hình hiển thị danh sách mã đề
    assert.match(harness.container.textContent, /Bản xem trước — Mã đề 101/);
    assert.match(harness.container.textContent, /Sẵn sàng phê duyệt/);
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Tổ hợp 2 (ON/OFF) - Chỉ bật checkbox câu hỏi rồi bấm "Áp dụng & Xem trước" gửi PATCH true/false và POST shuffle', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let previewGetCalls = 0;
  const calls = [];

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      previewGetCalls += 1;
      if (previewGetCalls === 1) {
        const error = new Error('Shuffle required');
        error.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
        throw error;
      }
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-on-off' } };
    }
    return { data: { id: 'session-on-off', status: 'reviewed' } };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    return { data: { session_id: 'session-on-off', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-on-off');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');

    // Chỉ bật câu hỏi (ON/OFF)
    await act(async () => {
      qCheckbox.click();
    });
    assert.equal(qCheckbox.checked, true);
    assert.equal(optCheckbox.checked, false);

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    await act(async () => {
      applyBtn.click();
    });

    assert.equal(calls.length, 2);
    assert.equal(calls[0].type, 'patch');
    assert.deepEqual(calls[0].payload, { shuffle_questions: true, shuffle_options: false });
    assert.equal(calls[1].type, 'post');
    assert.equal(calls[1].url, '/sessions/session-on-off/finalize/shuffle');
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Tổ hợp 3 (OFF/ON) - Chỉ bật checkbox đáp án rồi bấm "Áp dụng & Xem trước" gửi PATCH false/true và POST shuffle', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let previewGetCalls = 0;
  const calls = [];

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      previewGetCalls += 1;
      if (previewGetCalls === 1) {
        const error = new Error('Shuffle required');
        error.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
        throw error;
      }
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-off-on' } };
    }
    return { data: { id: 'session-off-on', status: 'reviewed' } };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    return { data: { session_id: 'session-off-on', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-off-on');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');

    // Chỉ bật đáp án (OFF/ON)
    await act(async () => {
      optCheckbox.click();
    });
    assert.equal(qCheckbox.checked, false);
    assert.equal(optCheckbox.checked, true);

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    await act(async () => {
      applyBtn.click();
    });

    assert.equal(calls.length, 2);
    assert.equal(calls[0].type, 'patch');
    assert.deepEqual(calls[0].payload, { shuffle_questions: false, shuffle_options: true });
    assert.equal(calls[1].type, 'post');
    assert.equal(calls[1].url, '/sessions/session-off-on/finalize/shuffle');
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Khôi phục cấu hình ordering_preferences đã lưu ở backend (ví dụ ON/OFF)', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let previewGetCalls = 0;
  const calls = [];

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      previewGetCalls += 1;
      if (previewGetCalls === 1) {
        const error = new Error('Shuffle required');
        error.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
        throw error;
      }
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-restored' } };
    }
    // GET /sessions/:id trả cấu hình đã lưu
    return {
      data: {
        id: 'session-restored',
        status: 'reviewed',
        generation_config: {
          ordering_preferences: {
            shuffle_questions: true,
            shuffle_options: false,
          },
        },
      },
    };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    return { data: { session_id: 'session-restored', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-restored');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');

    // Kiểm tra đã khôi phục đúng cấu hình đã lưu: true/false
    assert.equal(qCheckbox.checked, true, 'shuffle_questions phải được khôi phục là true');
    assert.equal(optCheckbox.checked, false, 'shuffle_options phải được khôi phục là false');

    // Bấm Áp dụng mà không cần đổi gì sẽ giữ nguyên cấu hình đã lưu
    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    await act(async () => {
      applyBtn.click();
    });

    assert.equal(calls.length, 2);
    assert.equal(calls[0].type, 'patch');
    assert.deepEqual(calls[0].payload, { shuffle_questions: true, shuffle_options: false });
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Không ghi đè ngoài ý muốn - sửa 1 checkbox không ảnh hưởng checkbox còn lại', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let previewGetCalls = 0;
  const calls = [];

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      previewGetCalls += 1;
      if (previewGetCalls === 1) {
        const error = new Error('Shuffle required');
        error.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
        throw error;
      }
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-no-overwrite' } };
    }
    // Khôi phục ON/OFF từ backend
    return {
      data: {
        id: 'session-no-overwrite',
        status: 'reviewed',
        generation_config: {
          ordering_preferences: {
            shuffle_questions: true,
            shuffle_options: false,
          },
        },
      },
    };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    return { data: { session_id: 'session-no-overwrite', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-no-overwrite');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');

    assert.equal(qCheckbox.checked, true);
    assert.equal(optCheckbox.checked, false);

    // Người dùng chỉ click bật checkbox đáp án
    await act(async () => {
      optCheckbox.click();
    });

    // Checkbox câu hỏi vẫn phải giữ nguyên là true (không bị reset về false)
    assert.equal(qCheckbox.checked, true, 'Checkbox câu hỏi không bị ảnh hưởng khi toggle đáp án');
    assert.equal(optCheckbox.checked, true, 'Checkbox đáp án đã chuyển thành true');

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    await act(async () => {
      applyBtn.click();
    });

    // Payload gửi đi là true/true
    assert.deepEqual(calls[0].payload, { shuffle_questions: true, shuffle_options: true });
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Khi phiên bị khóa (approved/exported), các tùy chọn xáo trộn và nút áp dụng đều bị vô hiệu hóa (disabled)', async () => {
  const originalGet = api.get;

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-locked-pref',
          status: 'approved',
          is_finalized: false,
        },
      };
    }
    return {
      data: {
        id: 'session-locked-pref',
        status: 'approved',
        generation_config: {
          ordering_preferences: {
            shuffle_questions: true,
            shuffle_options: false,
          },
        },
      },
    };
  };

  const harness = renderPreviewPage('session-locked-pref');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');
    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');

    assert.ok(qCheckbox, 'Checkbox câu hỏi phải tồn tại');
    assert.ok(optCheckbox, 'Checkbox đáp án phải tồn tại');
    assert.ok(applyBtn, 'Nút Áp dụng phải tồn tại');

    assert.ok(
      qCheckbox.getAttribute('disabled') !== null || Boolean(qCheckbox.disabled),
      'Checkbox câu hỏi phải bị disable khi phiên đã approved'
    );
    assert.ok(
      optCheckbox.getAttribute('disabled') !== null || Boolean(optCheckbox.disabled),
      'Checkbox đáp án phải bị disable khi phiên đã approved'
    );
    assert.ok(
      applyBtn.getAttribute('disabled') !== null || Boolean(applyBtn.disabled),
      'Nút Áp dụng phải bị disable khi phiên đã approved'
    );
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Bấm nút "Quay lại duyệt từng câu" điều hướng về /session/:id/stage3', async () => {
  const originalGet = api.get;
  api.get = async () => ({ data: GOLDEN_PREVIEW_FIXTURE });

  const harness = renderPreviewPage('sess-nav-back');
  try {
    await harness.render();
    const backBtn = harness.container.querySelector('[data-testid="btn-back"]');
    assert.ok(backBtn);

    await act(async () => {
      backBtn.click();
    });

    assert.equal(harness.getLocation(), '/session/sess-nav-back/stage3');
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Hiển thị đầy đủ danh sách mã đề, câu hỏi, phương án, đáp án đúng và lời giải', async () => {
  const originalGet = api.get;
  api.get = async () => ({ data: GOLDEN_PREVIEW_FIXTURE });

  const harness = renderPreviewPage('sess-view');
  try {
    await harness.render();

    // Tabs mã đề
    const tab101 = harness.container.querySelector('[data-testid="tab-version-101"]');
    const tab102 = harness.container.querySelector('[data-testid="tab-version-102"]');
    const tabMatrix = harness.container.querySelector('[data-testid="tab-matrix"]');
    assert.ok(tab101);
    assert.ok(tab102);
    assert.ok(tabMatrix);

    // Thẻ câu hỏi 1
    const q1Card = harness.container.querySelector('[data-testid="question-card-1"]');
    assert.ok(q1Card);
    assert.match(q1Card.textContent, /Câu 1/);
    assert.match(q1Card.textContent, /\[Gốc: #1\]/);
    assert.match(q1Card.textContent, /Cho hàm số/);

    // Badge đáp án đúng
    const correctBadge = q1Card.querySelector('[data-testid="badge-correct"]');
    assert.ok(correctBadge);
    assert.match(correctBadge.textContent, /Đáp án đúng/);

    // Lời giải chi tiết
    assert.match(q1Card.textContent, /Lời giải chi tiết/);
    assert.match(q1Card.textContent, /Đạo hàm/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Chuyển đổi giữa các Tab mã đề hiển thị đúng nội dung của mã đề tương ứng', async () => {
  const originalGet = api.get;
  api.get = async () => ({ data: GOLDEN_PREVIEW_FIXTURE });

  const harness = renderPreviewPage('sess-tab-switch');
  try {
    await harness.render();

    const tab102 = harness.container.querySelector('[data-testid="tab-version-102"]');
    assert.ok(tab102);

    await act(async () => {
      tab102.click();
    });

    assert.match(harness.container.textContent, /Bản xem trước — Mã đề 102/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Bấm Tab "Ma trận đáp án đối soát" hiển thị bảng ma trận chính xác', async () => {
  const originalGet = api.get;
  api.get = async () => ({ data: GOLDEN_PREVIEW_FIXTURE });

  const harness = renderPreviewPage('sess-matrix-view');
  try {
    await harness.render();

    const tabMatrix = harness.container.querySelector('[data-testid="tab-matrix"]');
    assert.ok(tabMatrix);

    await act(async () => {
      tabMatrix.click();
    });

    const matrixTable = harness.container.querySelector('[data-testid="matrix-table"]');
    assert.ok(matrixTable, 'Bảng ma trận phải hiển thị');
    assert.match(matrixTable.textContent, /Câu 1/);
    assert.match(matrixTable.textContent, /Câu 2/);
    assert.match(matrixTable.textContent, /Câu 3/);
    assert.match(matrixTable.textContent, /Mã đề 101/);
    assert.match(matrixTable.textContent, /Mã đề 102/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Bấm "Phê duyệt & Khóa đề" mở modal xác nhận với cảnh báo Kiểm tra kỹ trước khi xác nhận.', async () => {
  const originalGet = api.get;
  api.get = async () => ({ data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-approve-modal' } });

  const harness = renderPreviewPage('sess-approve-modal');
  try {
    await harness.render();

    const openApproveBtn = harness.container.querySelector('[data-testid="btn-open-approve"]');
    assert.ok(openApproveBtn);

    await act(async () => {
      openApproveBtn.click();
    });

    // Modal hiển thị
    const modal = harness.container.querySelector('[role="dialog"]');
    assert.ok(modal, 'Modal phê duyệt phải mở');
    assert.match(modal.textContent, /Xác nhận phê duyệt & Khóa đề thi/);
    assert.match(modal.textContent, /Kiểm tra kỹ trước khi xác nhận./);
    assert.match(modal.textContent, /Hành động này không thể hoàn tác/);

    // Bấm nút Hủy bỏ đóng modal
    const cancelBtn = harness.container.querySelector('[data-testid="btn-cancel-approve"]');
    assert.ok(cancelBtn);

    await act(async () => {
      cancelBtn.click();
    });

    assert.equal(harness.container.querySelector('[role="dialog"]'), null, 'Modal phải đóng sau khi bấm Hủy');
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Xác nhận phê duyệt trong modal gọi POST /finalize/approve và điều hướng sang /session/:id/export', async () => {
  const originalGet = api.get;
  const originalPost = api.post;

  let capturedPost = null;
  api.get = async () => ({ data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-approved' } });

  api.post = async (url, payload) => {
    capturedPost = { url, payload };
    return {
      data: {
        session_id: 'sess-approved',
        status: 'approved',
        approved_at: '2026-11-14T20:00:00Z',
      },
    };
  };

  const harness = renderPreviewPage('sess-approved');
  try {
    await harness.render();

    const openApproveBtn = harness.container.querySelector('[data-testid="btn-open-approve"]');
    await act(async () => {
      openApproveBtn.click();
    });

    const confirmBtn = harness.container.querySelector('[data-testid="btn-confirm-approve"]');
    assert.ok(confirmBtn);

    await act(async () => {
      confirmBtn.click();
    });

    assert.ok(capturedPost);
    assert.equal(capturedPost.url, '/sessions/sess-approved/finalize/approve');
    assert.equal(harness.getLocation(), '/session/sess-approved/export');
  } finally {
    api.get = originalGet;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Khi tải phiên đã ở trạng thái approved hiển thị badge khóa, banner và mở khóa các nút tới Export', async () => {
  const originalGet = api.get;
  const lockedFixture = {
    ...GOLDEN_PREVIEW_FIXTURE,
    status: 'approved',
  };
  api.get = async () => ({ data: lockedFixture });

  const harness = renderPreviewPage('sess-already-locked');
  try {
    await harness.render();

    // Badge trạng thái khóa
    const lockedBadge = harness.container.querySelector('[data-testid="badge-status-locked"]');
    assert.ok(lockedBadge);
    assert.match(lockedBadge.textContent, /Đã phê duyệt & Khóa đề/);

    // Banner đã khóa
    const lockedBanner = harness.container.querySelector('[data-testid="banner-locked"]');
    assert.ok(lockedBanner);
    assert.match(lockedBanner.textContent, /Đề thi đã được phê duyệt và khóa nội dung vĩnh viễn/);

    // Không hiển thị nút Phê duyệt
    assert.equal(harness.container.querySelector('[data-testid="btn-open-approve"]'), null);

    assert.equal(harness.container.querySelector('[data-testid="banner-btn-goto-export"]'), null, 'Không lặp lại nút xuất đề');

    const gotoExportBtn = harness.container.querySelector('[data-testid="btn-goto-export"]');
    assert.ok(gotoExportBtn);
    assert.ok(!gotoExportBtn.disabled && gotoExportBtn.getAttribute('disabled') === null);

    await act(async () => {
      gotoExportBtn.click();
    });

    assert.equal(harness.getLocation(), '/session/sess-already-locked/export');

    await harness.navigate('/session/sess-already-locked/stage3/preview');
    const bannerBtnAfterReturn = harness.container.querySelector('[data-testid="btn-goto-export"]');
    assert.ok(bannerBtnAfterReturn);
    await act(async () => {
      bannerBtnAfterReturn.click();
    });
    assert.equal(harness.getLocation(), '/session/sess-already-locked/export');
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Hiển thị thông báo lỗi mạng và nút "Thử lại"', async () => {
  const originalGet = api.get;
  let attempt = 0;
  api.get = async () => {
    attempt += 1;
    if (attempt === 1) {
      throw new Error('Mất kết nối tới máy chủ');
    }
    return { data: GOLDEN_PREVIEW_FIXTURE };
  };

  const harness = renderPreviewPage('sess-network-err');
  try {
    await harness.render();
    assert.match(harness.container.textContent, /Không thể tải bản xem trước/);
    assert.match(harness.container.textContent, /Mất kết nối tới máy chủ/);

    const retryBtn = harness.container.querySelector('[data-testid="btn-retry"]');
    assert.ok(retryBtn);
    assert.match(retryBtn.textContent, /Thử lại/);

    await act(async () => {
      retryBtn.click();
    });

    // Sau khi thử lại thành công
    assert.match(harness.container.textContent, /Bản xem trước — Mã đề 101/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

// =========================================================================
// BỘ TESTS KIỂM CHỨNG THEO REVIEW DUY (F01 - F05)
// =========================================================================

test('F01 & F02: Không render nút "Xáo trộn lại" và chỉ cho phép approve khi preview đã tải thành công', async () => {
  const originalGet = api.get;
  let resolveGet;
  api.get = () =>
    new Promise((resolve) => {
      resolveGet = resolve;
    });

  const harness = renderPreviewPage('sess-f01-f02');
  try {
    // 1. Khi GET đang pending: loading = true
    await harness.render();
    assert.equal(
      harness.container.querySelector('[data-testid="btn-open-approve"]'),
      null,
      'Khi GET pending, nút approve không được hiển thị',
    );
    assert.equal(
      harness.container.querySelector('[data-testid="btn-reshuffle"]'),
      null,
      'Nút reshuffle không được tồn tại',
    );

    // 2. Khi GET hoàn tất thành công
    await act(async () => {
      resolveGet({ data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-f01-f02' } });
    });

    // Lúc này canApprove = true -> nút approve hiển thị, nhưng nút reshuffle vẫn không có
    assert.ok(
      harness.container.querySelector('[data-testid="btn-open-approve"]'),
      'Nút approve phải hiển thị khi preview đã tải thành công',
    );
    assert.equal(
      harness.container.querySelector('[data-testid="btn-reshuffle"]'),
      null,
      'Nút reshuffle không được tồn tại trên MVP',
    );
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('F02: Khi GET preview lỗi (ví dụ lỗi mạng), nút approve không được hiển thị', async () => {
  const originalGet = api.get;
  api.get = async () => {
    throw new Error('Lỗi tải dữ liệu 500');
  };

  const harness = renderPreviewPage('sess-f02-err');
  try {
    await harness.render();
    assert.equal(
      harness.container.querySelector('[data-testid="btn-open-approve"]'),
      null,
      'Khi GET lỗi, không được hiển thị nút approve',
    );
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('F03: Khi GET preview trả HTTP 409 khác mã ERR_SHUFFLE_REQUIRED, không kích hoạt needsShuffle', async () => {
  const originalGet = api.get;
  api.get = async () => {
    const error = new Error('Session chưa ở trạng thái reviewed');
    error.response = {
      status: 409,
      data: {
        error_code: 'ERR_INVALID_SESSION_STATE',
        detail: 'Session chưa ở trạng thái reviewed',
      },
    };
    throw error;
  };

  const harness = renderPreviewPage('sess-f03-409');
  try {
    await harness.render();
    // Không được hiển thị màn hình chờ xáo trộn và nút shuffle
    assert.equal(harness.container.querySelector('[data-testid="btn-shuffle"]'), null);
    assert.equal(harness.container.querySelector('[data-testid="badge-status-pending"]'), null);

    // Phải hiển thị thông báo lỗi và nút Thử lại
    assert.match(harness.container.textContent, /Không thể tải bản xem trước/);
    assert.match(harness.container.textContent, /Session chưa ở trạng thái reviewed/);
    assert.ok(harness.container.querySelector('[data-testid="btn-retry"]'));
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('F04: Chuyển đổi giữa các tab không gọi lại API GET preview', async () => {
  const originalGet = api.get;
  let getCallCount = 0;
  api.get = async () => {
    getCallCount += 1;
    return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-f04-tabs' } };
  };

  const harness = renderPreviewPage('sess-f04-tabs');
  try {
    await harness.render();
    assert.equal(getCallCount, 1, 'Lần đầu tải trang chỉ gọi GET đúng 1 lần');

    // Chuyển sang tab 102
    const tab102Btn = harness.container.querySelector('[data-testid="tab-version-102"]');
    assert.ok(tab102Btn);
    await act(async () => {
      tab102Btn.click();
    });

    assert.equal(getCallCount, 1, 'Chuyển sang tab 102 không được gọi lại GET');

    // Chuyển sang tab matrix
    const tabMatrixBtn = harness.container.querySelector('[data-testid="tab-matrix"]');
    assert.ok(tabMatrixBtn);
    await act(async () => {
      tabMatrixBtn.click();
    });

    assert.equal(getCallCount, 1, 'Chuyển sang tab matrix không được gọi lại GET');
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('F05: Đổi sessionId từ A sang B, response trả về muộn của A không ghi đè dữ liệu của B', async () => {
  const originalGet = api.get;
  let resolveA;

  api.get = async (url) => {
    if (url.includes('session-A')) {
      return new Promise((resolve) => {
        resolveA = resolve;
      });
    }
    if (url.includes('session-B')) {
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-B',
          versions: [
            {
              ...GOLDEN_PREVIEW_FIXTURE.versions[0],
              questions: [
                {
                  ...GOLDEN_PREVIEW_FIXTURE.versions[0].questions[0],
                  content: 'Nội dung câu hỏi của Session B',
                },
              ],
            },
          ],
        },
      };
    }
    return { data: GOLDEN_PREVIEW_FIXTURE };
  };

  const harness = renderPreviewPage('session-A');
  try {
    // 1. Tải session A (đang pending)
    await harness.render();

    // 2. Chuyển sang session B trên cùng component
    await harness.navigate('/session/session-B/stage3/preview');

    // Session B đã tải xong và hiển thị
    assert.match(harness.container.textContent, /Nội dung câu hỏi của Session B/);

    // 3. Bây giờ session A mới trả về (muộn)
    await act(async () => {
      resolveA({
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-A',
          versions: [
            {
              ...GOLDEN_PREVIEW_FIXTURE.versions[0],
              questions: [
                {
                  ...GOLDEN_PREVIEW_FIXTURE.versions[0].questions[0],
                  content: 'Nội dung câu hỏi của Session A CŨ KỸ',
                },
              ],
            },
          ],
        },
      });
    });

    // Đảm bảo nội dung của session B vẫn được bảo toàn, không bị session A ghi đè
    assert.match(harness.container.textContent, /Nội dung câu hỏi của Session B/);
    assert.doesNotMatch(harness.container.textContent, /Nội dung câu hỏi của Session A CŨ KỸ/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('R1: Đổi sessionId từ A sang B khi modal phê duyệt đang mở, modal phải tự động đóng và không cho phép approve nhầm B', async () => {
  const originalGet = api.get;
  const originalPost = api.post;
  const postCalls = [];

  api.get = async (url) => {
    if (url.includes('session-A')) {
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-A',
        },
      };
    }
    if (url.includes('session-B')) {
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-B',
        },
      };
    }
    return { data: GOLDEN_PREVIEW_FIXTURE };
  };

  api.post = async (url, payload) => {
    postCalls.push({ url, payload });
    return { data: { success: true } };
  };

  const harness = renderPreviewPage('session-A');
  try {
    // 1. Tải session A thành công và mở modal phê duyệt
    await harness.render();
    const openApproveBtn = harness.container.querySelector('[data-testid="btn-open-approve"]');
    assert.ok(openApproveBtn);

    await act(async () => {
      openApproveBtn.click();
    });

    // Modal đang mở ở session A
    assert.ok(harness.container.querySelector('[role="dialog"]'), 'Modal phê duyệt của A phải đang mở');

    // 2. Chuyển sang session B trên cùng component
    await harness.navigate('/session/session-B/stage3/preview');

    // 3. Modal phải lập tức đóng lại khi sessionId đổi, không được giữ modal của A dưới session B
    assert.equal(
      harness.container.querySelector('[role="dialog"]'),
      null,
      'Modal phê duyệt của A phải tự động đóng khi chuyển sang session B',
    );
    assert.equal(postCalls.length, 0, 'Không có lệnh POST nào được gửi khi chuyển route');
  } finally {
    api.get = originalGet;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F02: Khi handleShuffle hoặc handleApprove của session A đang chạy dở, chuyển sang session B thì kết quả của A không tác động lên B', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let resolveShuffleA;
  const shuffleAPromise = new Promise((resolve) => {
    resolveShuffleA = resolve;
  });

  api.get = async (url) => {
    if (url.includes('session-A')) {
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-A', is_finalized: false } };
    }
    if (url.includes('session-B')) {
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-B', is_finalized: false } };
    }
    return { data: GOLDEN_PREVIEW_FIXTURE };
  };

  api.patch = async () => ({ data: { success: true } });
  api.post = async (url) => {
    if (url.includes('session-A')) {
      await shuffleAPromise;
      return { data: { success: true } };
    }
    return { data: { success: true } };
  };

  const harness = renderPreviewPage('session-A');
  try {
    await harness.render();

    // 1. Session A cần shuffle, bấm nút shuffle
    const shuffleBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(shuffleBtn);

    // Bấm shuffle phiên A nhưng chưa resolve promise
    let clickPromise;
    await act(async () => {
      clickPromise = shuffleBtn.click();
    });

    // 2. Chuyển sang session B ngay khi A đang chạy
    await harness.navigate('/session/session-B/stage3/preview');

    // 3. Resolve promise cho A
    await act(async () => {
      resolveShuffleA();
      await clickPromise;
    });

    // 4. Session B vẫn phải giữ đúng dữ liệu của session B, không bị loadData của A ghi đè
    assert.ok(harness.container.querySelector('[data-testid="btn-shuffle"]'), 'Session B vẫn phải ở trạng thái cần shuffle');
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

for (const network of [false, true]) {
  test(`R78-01: ${network ? 'network' : 'HTTP 500'} preference failure blocks writes; retry restores ON/OFF`, async () => {
    const original = { get: api.get, patch: api.patch, post: api.post };
    const writes = [];
    let failed = true;
    let finalized = false;
    api.get = async url => {
      if (url.endsWith('/finalize/preview')) {
        if (finalized) return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'recovery' } };
        const err = new Error('Shuffle required');
        err.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
        throw err;
      }
      if (failed) {
        const err = new Error('Read failed');
        if (!network) err.response = { status: 500 };
        throw err;
      }
      return { data: { status: 'reviewed', generation_config: {
        ordering_preferences: { shuffle_questions: true, shuffle_options: false },
      } } };
    };
    api.patch = async (url, payload) => { writes.push({ type: 'patch', payload }); return { data: {} }; };
    api.post = async () => { writes.push({ type: 'post' }); finalized = true; return { data: {} }; };
    const harness = renderPreviewPage('recovery');
    try {
      await harness.render();
      assert.match(harness.container.textContent, /Không thể tải cấu hình xáo trộn đã lưu/);
      assert.equal(harness.container.querySelector('[data-testid="btn-shuffle"]'), null);
      assert.equal(harness.container.querySelector('#shuffle-questions-checkbox'), null);
      assert.deepEqual(writes, []);
      failed = false;
      await act(async () => { harness.container.querySelector('[data-testid="btn-retry"]').click(); });
      assert.equal(harness.container.querySelector('#shuffle-questions-checkbox').checked, true);
      assert.equal(harness.container.querySelector('#shuffle-options-checkbox').checked, false);
      await act(async () => { harness.container.querySelector('[data-testid="btn-shuffle"]').click(); });
      assert.deepEqual(writes, [
        { type: 'patch', payload: { shuffle_questions: true, shuffle_options: false } },
        { type: 'post' },
      ]);
    } finally { Object.assign(api, original); await harness.unmount(); }
  });
}

for (const rejectLate of [false, true]) {
  test(`R78-01: late preference ${rejectLate ? 'rejection' : 'response'} from A cannot change B`, async () => {
    const originalGet = api.get;
    let settleA;
    api.get = async url => {
      if (url.includes('session-B')) return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-B' } };
      if (url.endsWith('/finalize/preview')) {
        const err = new Error('Shuffle required');
        err.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
        throw err;
      }
      return new Promise((resolve, reject) => {
        settleA = () => rejectLate ? reject(new Error('Stale read')) : resolve({ data: {
          status: 'reviewed', ordering_preferences: { shuffle_questions: true, shuffle_options: true },
        } });
      });
    };
    const harness = renderPreviewPage('session-A');
    try {
      await harness.render();
      assert.equal(typeof settleA, 'function');
      await harness.navigate('/session/session-B/stage3/preview');
      await act(async () => { settleA(); });
      assert.ok(harness.container.querySelector('[data-testid="btn-open-approve"]'));
      assert.equal(harness.container.querySelector('[data-testid="btn-retry"]'), null);
      assert.equal(harness.container.querySelector('[data-testid="btn-shuffle"]'), null);
    } finally { api.get = originalGet; await harness.unmount(); }
  });
}

test('R78-01: authoritative preferences in shuffle-required response avoid another GET', async () => {
  const originalGet = api.get;
  const calls = [];
  api.get = async url => {
    calls.push(url);
    const err = new Error('Shuffle required');
    err.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED',
      ordering_preferences: { shuffle_questions: false, shuffle_options: true },
    } };
    throw err;
  };
  const harness = renderPreviewPage('inline-prefs');
  try {
    await harness.render();
    assert.equal(calls.length, 1);
    assert.equal(harness.container.querySelector('#shuffle-questions-checkbox').checked, false);
    assert.equal(harness.container.querySelector('#shuffle-options-checkbox').checked, true);
  } finally { api.get = originalGet; await harness.unmount(); }
});

test('R78-01: preference rejection after unmount is ignored', async () => {
  const originalGet = api.get;
  let rejectPreferences;
  api.get = async url => {
    if (url.endsWith('/finalize/preview')) {
      const err = new Error('Shuffle required');
      err.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
      throw err;
    }
    return new Promise((resolve, reject) => { rejectPreferences = reject; });
  };
  const harness = renderPreviewPage('unmount-prefs');
  try {
    await harness.render();
    assert.equal(typeof rejectPreferences, 'function');
    await harness.unmount();
    await act(async () => { rejectPreferences(new Error('Late failure')); });
    assert.equal(harness.container.textContent, '');
  } finally { api.get = originalGet; }
});

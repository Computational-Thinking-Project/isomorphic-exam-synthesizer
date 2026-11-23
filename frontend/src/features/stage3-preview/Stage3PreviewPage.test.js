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

test('Stage3PreviewPage: Xử lý lỗi 409 ERR_SHUFFLE_REQUIRED hiển thị thẻ Chờ chốt thứ tự, chỉ có 1 điều khiển shuffle_questions mặc định OFF và nút "Áp dụng & Xem trước"', async () => {
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
    return {
      data: {
        id: 'session-needs-shuffle',
        status: 'reviewed',
        generation_config: {
          ordering_preferences: { shuffle_questions: false, shuffle_options: false },
        },
      },
    };
  };

  const harness = renderPreviewPage('session-needs-shuffle');
  try {
    await harness.render();
    assert.match(harness.container.textContent, /Bước 3\/3 · Xem trước bản cuối/);
    assert.match(harness.container.textContent, /Toàn bộ câu hỏi đã được duyệt thành công/);
    assert.match(harness.container.textContent, /Chờ chốt thứ tự/);

    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    const optCheckbox = harness.container.querySelector('#shuffle-options-checkbox');
    assert.ok(qCheckbox, 'Checkbox xáo trộn thứ tự câu hỏi phải hiển thị');
    assert.equal(optCheckbox, null, 'ISSUE-95: Không được hiển thị điều khiển shuffle_options ở Stage 3');
    assert.equal(qCheckbox.checked, false, 'Checkbox câu hỏi mặc định OFF (false)');

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
    return {
      data: {
        id: 'session-off-test',
        status: 'reviewed',
        generation_config: {
          ordering_preferences: { shuffle_questions: false, shuffle_options: false },
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
    return { data: { session_id: 'session-off-test', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-off-test');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    assert.equal(qCheckbox.checked, false);
    assert.equal(harness.container.querySelector('#shuffle-options-checkbox'), null);

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

    assert.match(harness.container.textContent, /Bản xem trước — Mã đề 101/);
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('ISSUE-95: Phiên cũ có shuffle_options: true hiển thị thông báo chỉ đọc, không có checkbox đáp án và bảo toàn true khi bật shuffle_questions', async () => {
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
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-legacy-on' } };
    }
    return {
      data: {
        id: 'session-legacy-on',
        status: 'reviewed',
        generation_config: {
          ordering_preferences: { shuffle_questions: false, shuffle_options: true },
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
    return { data: { session_id: 'session-legacy-on', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-legacy-on');
  try {
    await harness.render();
    assert.equal(calls.length, 0, 'F5/mở trang không được tự ý PATCH/POST');

    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    assert.ok(qCheckbox);
    assert.equal(qCheckbox.checked, false);
    assert.equal(harness.container.querySelector('#shuffle-options-checkbox'), null);

    const readonlyNotice = harness.container.querySelector('[data-testid="readonly-shuffle-options-notice"]');
    assert.ok(readonlyNotice, 'Phải hiển thị thông báo chỉ đọc khi phiên cũ đang bật shuffle_options');
    assert.match(readonlyNotice.textContent, /xáo trộn thứ tự đáp án/i);

    await act(async () => {
      qCheckbox.click();
    });
    assert.equal(qCheckbox.checked, true);

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    await act(async () => {
      applyBtn.click();
    });

    assert.equal(calls.length, 2);
    assert.equal(calls[0].type, 'patch');
    assert.deepEqual(calls[0].payload, { shuffle_questions: true, shuffle_options: true });
    assert.equal(calls[1].type, 'post');
    assert.equal(calls[1].url, '/sessions/session-legacy-on/finalize/shuffle');

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
    return {
      data: {
        id: 'session-on-off',
        status: 'reviewed',
        generation_config: {
          ordering_preferences: { shuffle_questions: false, shuffle_options: false },
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
    return { data: { session_id: 'session-on-off', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-on-off');
  try {
    await harness.render();
    const qCheckbox = harness.container.querySelector('#shuffle-questions-checkbox');
    assert.equal(harness.container.querySelector('#shuffle-options-checkbox'), null);

    await act(async () => {
      qCheckbox.click();
    });
    assert.equal(qCheckbox.checked, true);

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

test('ISSUE-95: Không đọc được shuffle_options đáng tin cậy phải khóa thao tác ghi và yêu cầu đối soát lại trước', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let serverHasPrefs = false;
  const writes = [];

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      const error = new Error('Shuffle required');
      error.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
      throw error;
    }
    return serverHasPrefs
      ? {
          data: {
            id: 'session-unreliable-prefs',
            status: 'reviewed',
            generation_config: {
              ordering_preferences: { shuffle_questions: false, shuffle_options: true },
            },
          },
        }
      : { data: { id: 'session-unreliable-prefs', status: 'reviewed' } };
  };

  api.patch = async (url, payload) => {
    writes.push({ type: 'patch', payload });
    return { data: { success: true } };
  };
  api.post = async () => {
    writes.push({ type: 'post' });
    return { data: {} };
  };

  const harness = renderPreviewPage('session-unreliable-prefs');
  try {
    await harness.render();
    assert.ok(
      harness.container.querySelector('[data-testid="unreliable-prefs-notice"]'),
      'Phải cảnh báo khi chưa đọc được ordering_preferences đáng tin cậy',
    );
    assert.equal(harness.container.querySelector('[data-testid="btn-shuffle"]'), null);
    assert.equal(harness.container.querySelector('#shuffle-questions-checkbox'), null);
    assert.deepEqual(writes, []);

    const reconcileBtn = harness.container.querySelector('[data-testid="btn-reconcile-prefs"]');
    assert.ok(reconcileBtn, 'Phải có nút Kiểm tra trạng thái để đối soát');

    serverHasPrefs = true;
    await act(async () => {
      reconcileBtn.click();
    });

    assert.ok(harness.container.querySelector('[data-testid="readonly-shuffle-options-notice"]'));
    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(applyBtn);
    await act(async () => {
      applyBtn.click();
    });
    assert.deepEqual(writes, [
      { type: 'patch', payload: { shuffle_questions: false, shuffle_options: true } },
      { type: 'post' },
    ]);
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
    assert.equal(harness.container.querySelector('#shuffle-options-checkbox'), null);
    assert.equal(qCheckbox.checked, true, 'shuffle_questions phải được khôi phục là true');

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

test('ISSUE-95: Sửa shuffle_questions trên phiên cũ không làm ghi đè shuffle_options: true đã lưu', async () => {
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
    return {
      data: {
        id: 'session-no-overwrite',
        status: 'reviewed',
        generation_config: {
          ordering_preferences: {
            shuffle_questions: true,
            shuffle_options: true,
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
    assert.equal(qCheckbox.checked, true);
    assert.ok(harness.container.querySelector('[data-testid="readonly-shuffle-options-notice"]'));

    // Tắt shuffle_questions -> shuffle_options: true vẫn phải được bảo toàn
    await act(async () => {
      qCheckbox.click();
    });
    assert.equal(qCheckbox.checked, false);

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    await act(async () => {
      applyBtn.click();
    });

    assert.deepEqual(calls[0].payload, { shuffle_questions: false, shuffle_options: true });
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
    assert.equal(optCheckbox, null, 'Không hiển thị checkbox đáp án');
    assert.ok(applyBtn, 'Nút Áp dụng phải tồn tại');

    assert.ok(
      qCheckbox.getAttribute('disabled') !== null || Boolean(qCheckbox.disabled),
      'Checkbox câu hỏi phải bị disable khi phiên đã approved'
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

    // Chuyển sang Teacher Mode để xem đáp án đúng, lời giải và bảng đáp án
    await act(async () => {
      harness.container.querySelector('[data-testid="btn-toggle-view-mode"]').click();
    });

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

    // Chuyển sang Teacher Mode để hiển thị tab ma trận
    await act(async () => {
      harness.container.querySelector('[data-testid="btn-toggle-view-mode"]').click();
    });

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
  api.get = (url) => {
    if (url.includes('/finalize/preview')) {
      return new Promise((resolve) => {
        resolveGet = resolve;
      });
    }
    return Promise.resolve({
      data: {
        id: 'sess-f01-f02',
        status: 'reviewed',
        ordering_preferences: { shuffle_questions: false, shuffle_options: false },
      },
    });
  };

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
  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      getCallCount += 1;
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-f04-tabs' } };
    }
    return {
      data: {
        id: 'sess-f04-tabs',
        status: 'reviewed',
        ordering_preferences: { shuffle_questions: false, shuffle_options: false },
      },
    };
  };

  const harness = renderPreviewPage('sess-f04-tabs');
  try {
    await harness.render();
    assert.equal(getCallCount, 1, 'Lần đầu tải trang chỉ gọi GET đúng 1 lần');

    // Chuyển sang Teacher Mode để hiển thị tab ma trận
    await act(async () => {
      harness.container.querySelector('[data-testid="btn-toggle-view-mode"]').click();
    });

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
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-A',
          is_finalized: false,
          ordering_preferences: { shuffle_questions: false, shuffle_options: false },
        },
      };
    }
    if (url.includes('session-B')) {
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-B',
          is_finalized: false,
          ordering_preferences: { shuffle_questions: false, shuffle_options: false },
        },
      };
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
      assert.equal(harness.container.querySelector('#shuffle-options-checkbox'), null);
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
    assert.equal(harness.container.querySelector('#shuffle-options-checkbox'), null);
    assert.ok(harness.container.querySelector('[data-testid="readonly-shuffle-options-notice"]'));
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

test('F84-04-A: Approval commit nhưng response mất -> GET trả approved -> Kiểm tra trạng thái điều hướng tới Export và không POST lại', async () => {
  const originalGet = api.get;
  const originalPost = api.post;
  let postCount = 0;
  let getCount = 0;

  api.post = async () => {
    postCount++;
    throw new Error('Network timeout on approve');
  };

  api.get = async () => {
    getCount++;
    if (getCount === 1) {
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-f84-04-a', status: 'reviewed', is_finalized: true } };
    }
    return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-f84-04-a', status: 'approved', is_finalized: true } };
  };

  const harness = renderPreviewPage('sess-f84-04-a');
  try {
    await harness.render();

    // Mở modal approve và click Phê duyệt
    await act(async () => {
      harness.container.querySelector('[data-testid="btn-open-approve"]').click();
    });
    await act(async () => {
      harness.container.querySelector('[data-testid="btn-confirm-approve"]').click();
    });

    assert.equal(postCount, 1);
    assert.match(harness.container.textContent, /Network timeout on approve/);

    // Nút "Kiểm tra trạng thái" xuất hiện
    const checkStatusBtn = Array.from(harness.container.querySelectorAll('button')).find(
      (b) => b.textContent.includes('Kiểm tra trạng thái'),
    );
    assert.ok(checkStatusBtn, 'Phải có nút Kiểm tra trạng thái');

    // Click Kiểm tra trạng thái
    await act(async () => {
      checkStatusBtn.click();
    });

    // Phải điều hướng tới export và không gọi thêm POST
    assert.equal(harness.getLocation(), '/session/sess-f84-04-a/export');
    assert.equal(postCount, 1, 'Không được gọi thêm POST approve');
  } finally {
    api.get = originalGet;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F84-04-B: Approval chưa thành công (GET trả reviewed) -> không điều hướng tới Export', async () => {
  const originalGet = api.get;
  const originalPost = api.post;

  api.post = async () => {
    throw new Error('Approve failed');
  };

  api.get = async () => ({
    data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-f84-04-b', status: 'reviewed', is_finalized: true },
  });

  const harness = renderPreviewPage('sess-f84-04-b');
  try {
    await harness.render();

    await act(async () => {
      harness.container.querySelector('[data-testid="btn-open-approve"]').click();
    });
    await act(async () => {
      harness.container.querySelector('[data-testid="btn-confirm-approve"]').click();
    });

    const checkStatusBtn = Array.from(harness.container.querySelectorAll('button')).find(
      (b) => b.textContent.includes('Kiểm tra trạng thái'),
    );
    assert.ok(checkStatusBtn);

    await act(async () => {
      checkStatusBtn.click();
    });

    assert.equal(harness.getLocation(), '/session/sess-f84-04-b/stage3/preview');
  } finally {
    api.get = originalGet;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F84-04-C: GET tiếp tục thất bại -> không làm mất trạng thái lỗi, cho phép thử lại', async () => {
  const originalGet = api.get;
  const originalPost = api.post;
  let getCount = 0;

  api.post = async () => {
    throw new Error('Initial approve failed');
  };

  api.get = async () => {
    getCount++;
    if (getCount === 1) {
      return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-f84-04-c', status: 'reviewed', is_finalized: true } };
    }
    throw new Error('Connection error during check');
  };

  const harness = renderPreviewPage('sess-f84-04-c');
  try {
    await harness.render();

    await act(async () => {
      harness.container.querySelector('[data-testid="btn-open-approve"]').click();
    });
    await act(async () => {
      harness.container.querySelector('[data-testid="btn-confirm-approve"]').click();
    });

    const checkStatusBtn = Array.from(harness.container.querySelectorAll('button')).find(
      (b) => b.textContent.includes('Kiểm tra trạng thái'),
    );
    assert.ok(checkStatusBtn);

    await act(async () => {
      checkStatusBtn.click();
    });

    assert.equal(harness.getLocation(), '/session/sess-f84-04-c/stage3/preview');
    assert.match(harness.container.textContent, /Initial approve failed/);
  } finally {
    api.get = originalGet;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F84-04-D: Session switching bỏ qua response cũ khi đối soát', async () => {
  const originalGet = api.get;
  const originalPost = api.post;
  let deferredA;

  api.post = async () => {
    throw new Error('Approve timeout');
  };

  api.get = async (url) => {
    if (url.includes('session-a')) {
      if (!deferredA) {
        return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-a', status: 'reviewed', is_finalized: true } };
      }
      return deferredA.promise;
    }
    return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-b', status: 'reviewed', is_finalized: true } };
  };

  const harness = renderPreviewPage('session-a');
  try {
    await harness.render();

    await act(async () => {
      harness.container.querySelector('[data-testid="btn-open-approve"]').click();
    });
    await act(async () => {
      harness.container.querySelector('[data-testid="btn-confirm-approve"]').click();
    });

    const checkStatusBtn = Array.from(harness.container.querySelectorAll('button')).find(
      (b) => b.textContent.includes('Kiểm tra trạng thái'),
    );
    assert.ok(checkStatusBtn);

    // Tạo deferred response cho request loadData tiếp theo của session A
    let resolveA;
    deferredA = {
      promise: new Promise((res) => { resolveA = res; }),
    };

    // Bắt đầu kiểm tra trạng thái session A
    checkStatusBtn.click();

    // Chuyển sang session B ngay trong lúc GET đang pending
    await harness.navigate('/session/session-b/stage3/preview');

    // Request session A trả về approved muộn
    await act(async () => {
      resolveA({ data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-a', status: 'approved', is_finalized: true } });
    });

    // Phải ở session B, không bị kéo về /session/session-a/export
    assert.equal(harness.getLocation(), '/session/session-b/stage3/preview');
  } finally {
    api.get = originalGet;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F84-05: Student Mode DOM isolation — không có badge-correct, lời giải hoặc bảng đáp án trong DOM', async () => {
  const originalGet = api.get;
  api.get = async () => ({
    data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'sess-student-mode', is_finalized: true, status: 'reviewed' },
  });

  const harness = renderPreviewPage('sess-student-mode');
  try {
    await harness.render();

    // Mặc định là Student Mode (isTeacherMode = false)
    // 1. [data-testid="badge-correct"] không tồn tại trong DOM
    assert.equal(
      harness.container.querySelector('[data-testid="badge-correct"]'),
      null,
      'Student mode: [data-testid="badge-correct"] không được tồn tại trong DOM',
    );

    // 2. Không có lời giải chi tiết trong DOM
    assert.equal(
      harness.container.textContent.includes('Lời giải chi tiết'),
      false,
      'Student mode: lời giải không được xuất hiện trong DOM',
    );

    // 3. Tab bảng đáp án không tồn tại trong DOM
    assert.equal(
      harness.container.querySelector('[data-testid="tab-matrix"]'),
      null,
      'Student mode: tab bảng đáp án không được hiển thị',
    );
    assert.equal(
      harness.container.querySelector('[data-testid="matrix-table"]'),
      null,
      'Student mode: bảng đáp án matrix-table không được xuất hiện',
    );

    // Chuyển sang Teacher Mode
    const toggleBtn = harness.container.querySelector('[data-testid="btn-toggle-view-mode"]');
    assert.ok(toggleBtn);
    await act(async () => {
      toggleBtn.click();
    });

    // 4. Trong Teacher Mode: badge-correct, lời giải và tab bảng đáp án xuất hiện
    assert.ok(
      harness.container.querySelector('[data-testid="badge-correct"]'),
      'Teacher mode: badge-correct phải xuất hiện',
    );
    assert.ok(
      harness.container.textContent.includes('Lời giải chi tiết'),
      'Teacher mode: lời giải phải xuất hiện',
    );
    assert.ok(
      harness.container.querySelector('[data-testid="tab-matrix"]'),
      'Teacher mode: tab bảng đáp án phải xuất hiện',
    );

    // Mở tab matrix trong Teacher mode
    await act(async () => {
      harness.container.querySelector('[data-testid="tab-matrix"]').click();
    });
    assert.ok(
      harness.container.querySelector('[data-testid="matrix-table"]'),
      'Teacher mode: bảng ma trận đáp án phải hiển thị khi chọn tab',
    );

    // Chuyển lại về Student Mode
    await act(async () => {
      toggleBtn.click();
    });

    // Tự động trở về tab version và cách ly DOM
    assert.equal(harness.container.querySelector('[data-testid="badge-correct"]'), null);
    assert.equal(harness.container.querySelector('[data-testid="tab-matrix"]'), null);
    assert.equal(harness.container.querySelector('[data-testid="matrix-table"]'), null);
    assert.equal(harness.container.textContent.includes('Lời giải chi tiết'), false);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('F91-04 / S86-A: GET ban đầu 409 ERR_SHUFFLE_REQUIRED; PATCH thành công; POST đã commit nhưng response timeout; GET đối soát trả 200 is_finalized=true => UI chuyển preview finalized; 1 PATCH, 1 POST, không lặp mutation', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  const calls = [];
  let getCount = 0;

  api.get = async (url) => {
    calls.push({ type: 'get', url });
    if (url.includes('/finalize/preview')) {
      getCount++;
      if (getCount === 1) {
        // Initial load: 409 ERR_SHUFFLE_REQUIRED
        const err = new Error('Shuffle required');
        err.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED', detail: 'Shuffle required' } };
        throw err;
      }
      // Reconcile call: server has committed finalization
      return {
        data: {
          session_id: 'session-s86-a',
          status: 'reviewed',
          is_finalized: true,
          versions: GOLDEN_PREVIEW_FIXTURE.versions,
        },
      };
    }
    return {
      data: {
        id: 'session-s86-a',
        status: 'reviewed',
        ordering_preferences: { shuffle_questions: false, shuffle_options: false },
      },
    };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    if (url.includes('/finalize/shuffle')) {
      // Giả lập network timeout sau khi backend đã commit
      const netErr = new Error('Network timeout after commit');
      netErr.isAxiosError = true;
      throw netErr;
    }
    return { data: {} };
  };

  const harness = renderPreviewPage('session-s86-a');
  try {
    await harness.render();

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(applyBtn, 'Nút Áp dụng & Xem trước phải hiển thị khi 409 ERR_SHUFFLE_REQUIRED');

    await act(async () => {
      applyBtn.click();
    });

    // 1. Kiểm tra UI đã tự đối chiếu authoritative preview và hiển thị preview thành công
    assert.match(harness.container.textContent, /Bản xem trước — Mã đề 101/);
    assert.match(harness.container.textContent, /Sẵn sàng phê duyệt/);

    // 2. Đúng 1 PATCH, 1 POST
    const patchCalls = calls.filter((c) => c.type === 'patch');
    const postCalls = calls.filter((c) => c.type === 'post');
    assert.equal(patchCalls.length, 1, 'Chỉ được gọi PATCH đúng 1 lần');
    assert.equal(postCalls.length, 1, 'Chỉ được gọi POST shuffle đúng 1 lần');
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F91-04 / S86-B: POST timeout và GET đối soát cũng 503 => UI hiển thị chưa xác định kết quả, có nút Kiểm tra trạng thái, không cho bấm PATCH/POST', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  const calls = [];
  let getCount = 0;

  api.get = async (url) => {
    calls.push({ type: 'get', url });
    if (url.includes('/finalize/preview')) {
      getCount++;
      if (getCount === 1) {
        // Initial load: 409 ERR_SHUFFLE_REQUIRED
        const err = new Error('Shuffle required');
        err.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED', detail: 'Shuffle required' } };
        throw err;
      }
      if (getCount === 2) {
        // Reconciliation call fails: 503 Unavailable
        const err503 = new Error('Service Unavailable during reconciliation');
        err503.response = { status: 503, data: { detail: 'Service Unavailable' } };
        throw err503;
      }
      // Third call (user clicks Check Status later): server confirms finalized!
      return {
        data: {
          session_id: 'session-s86-b',
          status: 'reviewed',
          is_finalized: true,
          versions: GOLDEN_PREVIEW_FIXTURE.versions,
        },
      };
    }
    return {
      data: {
        id: 'session-s86-b',
        status: 'reviewed',
        ordering_preferences: { shuffle_questions: false, shuffle_options: false },
      },
    };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    if (url.includes('/finalize/shuffle')) {
      const netErr = new Error('Network Drop on POST');
      netErr.isAxiosError = true;
      throw netErr;
    }
    return { data: {} };
  };

  const harness = renderPreviewPage('session-s86-b');
  try {
    await harness.render();

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(applyBtn);

    await act(async () => {
      applyBtn.click();
    });

    // 1. Phải hiển thị màn hình outcome-unknown-view
    const unknownView = harness.container.querySelector('[data-testid="outcome-unknown-view"]');
    assert.ok(unknownView, 'Phải hiển thị outcome-unknown-view khi reconciliation không thể kết luận');
    assert.match(harness.container.textContent, /Chưa xác định được kết quả chốt thứ tự/);

    // 2. Nút btn-shuffle KHÔNG được xuất hiện để ngăn người dùng bấm lặp PATCH/POST
    const shuffleBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.equal(shuffleBtn, null, 'Nút bấm shuffle không được hiển thị khi outcome chưa xác định');

    // 3. Phải có nút "Kiểm tra trạng thái"
    const checkStatusBtn = harness.container.querySelector('[data-testid="btn-check-status"]');
    assert.ok(checkStatusBtn, 'Phải có nút Kiểm tra trạng thái');

    // Số mutations tại thời điểm này: 1 patch, 1 post
    assert.equal(calls.filter((c) => c.type === 'patch').length, 1);
    assert.equal(calls.filter((c) => c.type === 'post').length, 1);

    // 4. Bấm "Kiểm tra trạng thái" -> CHỈ gọi GET, KHÔNG gọi thêm mutation nào
    await act(async () => {
      checkStatusBtn.click();
    });

    // Không có thêm PATCH hay POST nào
    assert.equal(calls.filter((c) => c.type === 'patch').length, 1, 'Không được gọi thêm PATCH');
    assert.equal(calls.filter((c) => c.type === 'post').length, 1, 'Không được gọi thêm POST');

    // Sau khi GET trả finalized, màn hình chuyển sang preview finalized thành công
    assert.match(harness.container.textContent, /Bản xem trước — Mã đề 101/);
    assert.match(harness.container.textContent, /Sẵn sàng phê duyệt/);
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F91-04 / S86-C: POST trả lỗi, GET đối soát xác nhận 409 ERR_SHUFFLE_REQUIRED => cho phép retry, giữ đúng 2 flags, số mutations đúng', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  const calls = [];
  let postCount = 0;

  api.get = async (url) => {
    calls.push({ type: 'get', url });
    if (url.includes('/finalize/preview')) {
      if (postCount < 2) {
        const err = new Error('Shuffle required');
        err.response = {
          status: 409,
          data: {
            error_code: 'ERR_SHUFFLE_REQUIRED',
            ordering_preferences: { shuffle_questions: true, shuffle_options: false },
          },
        };
        throw err;
      }
      return {
        data: {
          session_id: 'session-s86-c',
          status: 'reviewed',
          is_finalized: true,
          versions: GOLDEN_PREVIEW_FIXTURE.versions,
        },
      };
    }
    return {
      data: {
        id: 'session-s86-c',
        status: 'reviewed',
        ordering_preferences: { shuffle_questions: true, shuffle_options: false },
      },
    };
  };

  api.patch = async (url, payload) => {
    calls.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    calls.push({ type: 'post', url, payload });
    if (url.includes('/finalize/shuffle')) {
      postCount++;
      if (postCount === 1) {
        throw new Error('Immediate server error 500 on shuffle');
      }
      return { data: { session_id: 'session-s86-c', is_finalized: true } };
    }
    return { data: {} };
  };

  const harness = renderPreviewPage('session-s86-c');
  try {
    await harness.render();

    // 1. Kiểm tra cờ được hydrate đúng (ON/OFF) và không hiển thị checkbox đáp án
    const qCheckbox = harness.container.querySelector('[data-testid="checkbox-shuffle-questions"]');
    const optCheckbox = harness.container.querySelector('[data-testid="checkbox-shuffle-options"]');
    assert.equal(qCheckbox.checked, true);
    assert.equal(optCheckbox, null);

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(applyBtn);

    // Lần 1: click và gặp lỗi POST
    await act(async () => {
      applyBtn.click();
    });

    // 2. Vì GET đối soát xác nhận vẫn là 409 ERR_SHUFFLE_REQUIRED, nút thử lại vẫn hiển thị
    const retryBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(retryBtn, 'Nút Áp dụng & Xem trước vẫn còn để người dùng thử lại');
    assert.equal(qCheckbox.checked, true, 'Giữ nguyên cờ shuffle_questions');
    assert.equal(harness.container.querySelector('[data-testid="checkbox-shuffle-options"]'), null);

    // 3. Người dùng bấm thử lại lần 2
    await act(async () => {
      retryBtn.click();
    });

    // Lần 2 thành công và chuyển sang preview
    assert.match(harness.container.textContent, /Bản xem trước — Mã đề 101/);
    assert.equal(calls.filter((c) => c.type === 'patch').length, 2);
    assert.equal(calls.filter((c) => c.type === 'post').length, 2);
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

for (const finalStatus of ['reviewed', 'approved']) {
  test(`F91-R04: successful shuffle keeps recovery read-only until ${finalStatus} preview loads`, async () => {
    const { get, patch, post } = api;
    const sessionId = 'session-r04';
    const calls = [];
    let previewReads = 0;
    const unavailable = () => {
      throw Object.assign(new Error('Preview temporarily unavailable'), { response: { status: 503 } });
    };
    const shuffleRequired = () => {
      throw Object.assign(new Error('Shuffle required'), {
        response: {
          status: 409,
          data: {
            error_code: 'ERR_SHUFFLE_REQUIRED',
            ordering_preferences: { shuffle_questions: false, shuffle_options: false },
          },
        },
      });
    };

    api.get = async (url) => {
      calls.push(['GET', url]);
      switch (++previewReads) {
        case 1:
        case 4:
          return shuffleRequired();
        case 2:
        case 3:
          return unavailable();
        case 5:
          return { data: { session_id: sessionId, status: 'reviewed', is_finalized: false } };
        default:
          return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: sessionId, status: finalStatus } };
      }
    };
    api.patch = async (url) => {
      calls.push(['PATCH', url]);
      return { data: {} };
    };
    api.post = async (url) => {
      calls.push(['POST', url]);
      return { data: { session_id: sessionId, is_finalized: true } };
    };

    const harness = renderPreviewPage(sessionId);
    const find = (testId) => harness.container.querySelector(`[data-testid="${testId}"]`);
    const previewRead = ['GET', `/sessions/${sessionId}/finalize/preview`];
    const expectedCalls = [
      previewRead,
      ['PATCH', `/sessions/${sessionId}/ordering-preferences`],
      ['POST', `/sessions/${sessionId}/finalize/shuffle`],
      previewRead,
    ];
    try {
      await harness.render();
      await act(async () => find('btn-shuffle').click());
      for (let reads = 2; reads <= 5; reads++) {
        assert.deepEqual(calls, expectedCalls);
        assert.ok(!find('btn-shuffle'), 'Recovery must hide the shuffle button');
        assert.equal(find('btn-open-approve'), null);
        assert.equal(find('badge-status-pending'), null);
        assert.match(harness.container.textContent, /Đã chốt thứ tự/);
        assert.ok(find('btn-check-status'));
        await act(async () => find('btn-check-status').click());
        expectedCalls.push(previewRead);
      }
      assert.deepEqual(calls, expectedCalls);
      assert.equal(find('btn-check-status'), null);
      assert.equal(find('btn-shuffle'), null);
      assert.match(harness.container.textContent, /Bản xem trước — Mã đề 101/);
      assert.equal(Boolean(find('btn-open-approve')), finalStatus === 'reviewed');
      assert.equal(Boolean(find('btn-goto-export')), finalStatus === 'approved');
    } finally {
      Object.assign(api, { get, patch, post });
      await harness.unmount();
    }
  });
}

test('F91-R04: late preview recovery for session A leaves session B unchanged', async () => {
  const { get, patch, post } = api;
  const recoveryStarted = Promise.withResolvers();
  const recoveryResponse = Promise.withResolvers();
  let sessionAReads = 0;
  api.get = async (url) => {
    if (url === '/sessions/session-A/finalize/preview') {
      if (++sessionAReads === 2) {
        throw Object.assign(new Error('Preview temporarily unavailable'), { response: { status: 503 } });
      }
      if (sessionAReads === 3) {
        recoveryStarted.resolve();
        return recoveryResponse.promise;
      }
    }
    const sessionId = url.split('/')[2];
    return {
      data: {
        session_id: sessionId,
        status: 'reviewed',
        is_finalized: false,
        ordering_preferences: { shuffle_questions: false, shuffle_options: false },
      },
    };
  };
  api.patch = async () => ({ data: {} });
  api.post = async () => ({ data: { session_id: 'session-A', is_finalized: true } });

  const harness = renderPreviewPage('session-A');
  const find = (testId) => harness.container.querySelector(`[data-testid="${testId}"]`);
  try {
    await harness.render();
    await act(async () => find('btn-shuffle').click());
    await act(async () => find('btn-check-status').click());
    await recoveryStarted.promise;

    await harness.navigate('/session/session-B/stage3/preview');
    const sessionBView = harness.container.textContent;
    await act(async () => {
      recoveryResponse.resolve({ data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-A' } });
      await recoveryResponse.promise;
    });

    assert.equal(harness.getLocation(), '/session/session-B/stage3/preview');
    assert.equal(harness.container.textContent, sessionBView);
    assert.equal(find('btn-shuffle').getAttribute('disabled'), null);
    assert.equal(find('btn-open-approve'), null);
  } finally {
    Object.assign(api, { get, patch, post });
    await harness.unmount();
  }
});

test('F91-04 / S86-D: late shuffle POST for session A leaves session B unchanged', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  const postStarted = Promise.withResolvers();
  const postResponse = Promise.withResolvers();
  const previewReads = [];

  api.get = async (url) => {
    previewReads.push(url);
    if (url.includes('session-A')) {
      return {
        data: {
          session_id: 'session-A',
          status: 'reviewed',
          is_finalized: false,
          exam_versions: [],
          ordering_preferences: { shuffle_questions: false, shuffle_options: false },
        },
      };
    }
    return {
      data: {
        session_id: 'session-B',
        status: 'reviewed',
        is_finalized: false,
        exam_versions: [],
        ordering_preferences: { shuffle_questions: false, shuffle_options: false },
      },
    };
  };

  api.patch = async () => ({ data: { success: true } });

  api.post = (url) => {
    postStarted.resolve(url);
    return postResponse.promise;
  };

  const harness = renderPreviewPage('session-A');
  try {
    await harness.render();

    const applyBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(applyBtn);

    await act(async () => {
      applyBtn.click();
    });
    assert.equal(await postStarted.promise, '/sessions/session-A/finalize/shuffle');

    await harness.navigate('/session/session-B/stage3/preview');
    const sessionBView = harness.container.textContent;
    assert.ok(harness.container.querySelector('[data-testid="btn-shuffle"]'));

    // Resolve and flush the response inside act so its async handler can run.
    await act(async () => {
      postResponse.resolve({ data: { session_id: 'session-A', is_finalized: true } });
      await postResponse.promise;
    });

    assert.equal(harness.getLocation(), '/session/session-B/stage3/preview');
    assert.equal(harness.container.textContent, sessionBView);
    assert.equal(harness.container.querySelector('[data-testid="btn-shuffle"]').getAttribute('disabled'), null);
    assert.deepEqual(previewReads, [
      '/sessions/session-A/finalize/preview',
      '/sessions/session-B/finalize/preview',
    ]);
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F105-01: Cold-load / F5 phiên đã finalized (status reviewed, is_finalized=true) không có ordering_preferences trong preview snapshot vẫn gọi GET /sessions/:id và hiển thị readonly-shuffle-options-notice, không gửi PATCH/POST', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;
  let detailReads = 0;
  let mutationCount = 0;

  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-f105-finalized',
          status: 'reviewed',
          is_finalized: true,
        },
      };
    }
    if (url === '/sessions/session-f105-finalized') {
      detailReads += 1;
      return {
        data: {
          id: 'session-f105-finalized',
          status: 'reviewed',
          ordering_preferences: {
            shuffle_questions: false,
            shuffle_options: true,
          },
        },
      };
    }
    throw new Error(`Unexpected GET ${url}`);
  };
  api.patch = async () => {
    mutationCount += 1;
    return { data: {} };
  };
  api.post = async () => {
    mutationCount += 1;
    return { data: {} };
  };

  const harness = renderPreviewPage('session-f105-finalized');
  try {
    await harness.render();

    assert.equal(detailReads, 1, 'Phải gọi read-only GET /sessions/:id khi preview snapshot không chứa ordering_preferences');
    assert.equal(mutationCount, 0, 'Không được gửi PATCH hoặc POST khi mở lại phiên finalized');

    const notice = harness.container.querySelector('[data-testid="readonly-shuffle-options-notice"]');
    assert.ok(notice, 'Phải hiển thị readonly-shuffle-options-notice sau F5 trên phiên finalized');
    assert.match(notice.textContent, /Đang bật xáo trộn đáp án \(chỉ đọc\)/);
    assert.ok(harness.container.querySelector('[data-testid="btn-open-approve"]'), 'Nút Phê duyệt & Khóa đề vẫn sẵn sàng');
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('F105-01: Cold-load phiên đã approved (locked) với shuffle_options=true khôi phục readonly-shuffle-options-notice và khi GET /sessions/:id lỗi vẫn hiển thị preview an toàn, 0 PATCH/POST', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;
  let mutationCount = 0;

  api.patch = async () => {
    mutationCount += 1;
    return { data: {} };
  };
  api.post = async () => {
    mutationCount += 1;
    return { data: {} };
  };

  // Subcase A: GET /sessions/:id trả về shuffle_options=true cho phiên approved (locked)
  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-f105-approved',
          status: 'approved',
          is_finalized: true,
        },
      };
    }
    return {
      data: {
        id: 'session-f105-approved',
        status: 'approved',
        ordering_preferences: {
          shuffle_questions: true,
          shuffle_options: true,
        },
      },
    };
  };

  const harnessA = renderPreviewPage('session-f105-approved');
  try {
    await harnessA.render();

    const notice = harnessA.container.querySelector('[data-testid="readonly-shuffle-options-notice"]');
    assert.ok(notice, 'Phiên approved cũ có shuffle_options=true phải hiển thị readonly notice');
    assert.match(notice.textContent, /Đang bật xáo trộn đáp án \(chỉ đọc\)/);
    assert.ok(harnessA.container.querySelector('[data-testid="btn-goto-export"]'));
    assert.equal(harnessA.container.querySelector('[data-testid="btn-open-approve"]'), null);
    assert.equal(mutationCount, 0);
  } finally {
    await harnessA.unmount();
  }

  // Subcase B: GET /sessions/:id lỗi -> preview vẫn hiển thị an toàn, ẩn notice, không ghi
  api.get = async (url) => {
    if (url.includes('/finalize/preview')) {
      return {
        data: {
          ...GOLDEN_PREVIEW_FIXTURE,
          session_id: 'session-f105-approved',
          status: 'approved',
          is_finalized: true,
        },
      };
    }
    throw new Error('detail unavailable');
  };

  const harnessB = renderPreviewPage('session-f105-approved');
  try {
    await harnessB.render();

    assert.match(harnessB.container.textContent, /Bản xem trước — Mã đề 101/);
    assert.equal(harnessB.container.querySelector('[data-testid="readonly-shuffle-options-notice"]'), null);
    assert.ok(harnessB.container.querySelector('[data-testid="btn-goto-export"]'));
    assert.equal(mutationCount, 0);
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
    await harnessB.unmount();
  }
});

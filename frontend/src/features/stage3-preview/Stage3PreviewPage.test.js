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

test('Stage3PreviewPage: Xử lý lỗi 409 ERR_SHUFFLE_REQUIRED hiển thị thẻ Chờ xáo trộn và nút duy nhất "Xáo trộn mã đề"', async () => {
  const originalGet = api.get;
  api.get = async () => {
    const error = new Error('Cần thực hiện xáo trộn đề trước khi xem bản chiếu');
    error.response = {
      status: 409,
      data: {
        error_code: 'ERR_SHUFFLE_REQUIRED',
        detail: 'Cần thực hiện xáo trộn đề trước khi xem bản chiếu',
      },
    };
    throw error;
  };

  const harness = renderPreviewPage('session-needs-shuffle');
  try {
    await harness.render();
    assert.match(harness.container.textContent, /Toàn bộ câu hỏi đã được duyệt thành công/);
    assert.match(harness.container.textContent, /Chờ xáo trộn mã đề/);
    const shuffleBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(shuffleBtn, 'Nút Xáo trộn mã đề phải hiển thị');
    assert.match(shuffleBtn.textContent, /Xáo trộn mã đề/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Bấm "Xáo trộn mã đề" gọi PATCH preferences true/true và POST shuffle, sau đó nạp lại bản xem trước', async () => {
  const originalGet = api.get;
  const originalPatch = api.patch;
  const originalPost = api.post;

  let getCalls = 0;
  const calls = [];

  api.get = async () => {
    getCalls += 1;
    if (getCalls === 1) {
      const error = new Error('Shuffle required');
      error.response = { status: 409, data: { error_code: 'ERR_SHUFFLE_REQUIRED' } };
      throw error;
    }
    return { data: GOLDEN_PREVIEW_FIXTURE };
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
    const shuffleBtn = harness.container.querySelector('[data-testid="btn-shuffle"]');
    assert.ok(shuffleBtn);

    await act(async () => {
      shuffleBtn.click();
    });

    assert.equal(calls.length, 2);
    assert.equal(calls[0].type, 'patch');
    assert.deepEqual(calls[0].payload, { shuffle_questions: true, shuffle_options: true });
    assert.equal(calls[1].type, 'post');
    assert.equal(calls[1].url, '/sessions/session-123/finalize/shuffle');

    // Sau khi shuffle xong, màn hình hiển thị danh sách mã đề
    assert.match(harness.container.textContent, /Bản in Đề thi — Mã đề 101/);
    assert.match(harness.container.textContent, /Đã xáo trộn · Sẵn sàng duyệt/);
  } finally {
    api.get = originalGet;
    api.patch = originalPatch;
    api.post = originalPost;
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

    assert.match(harness.container.textContent, /Bản in Đề thi — Mã đề 102/);
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

test('Stage3PreviewPage: Bấm "Phê duyệt & Khóa đề" mở modal xác nhận với cảnh báo HTTP 423 Content Lock', async () => {
  const originalGet = api.get;
  api.get = async () => ({ data: GOLDEN_PREVIEW_FIXTURE });

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
    assert.match(modal.textContent, /HTTP 423 Content Lock/);
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
  api.get = async () => ({ data: GOLDEN_PREVIEW_FIXTURE });
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
    assert.equal(harness.getLocation(), '/session/sess-approved/export', 'Phải điều hướng sang màn hình Export');
  } finally {
    api.get = originalGet;
    api.post = originalPost;
    await harness.unmount();
  }
});

test('Stage3PreviewPage: Khi tải phiên đã ở trạng thái approved hiển thị badge khóa, banner và nút tới Export', async () => {
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
    assert.match(lockedBadge.textContent, /Đã phê duyệt & Khóa đề \(HTTP 423\)/);

    // Banner đã khóa
    const lockedBanner = harness.container.querySelector('[data-testid="banner-locked"]');
    assert.ok(lockedBanner);
    assert.match(lockedBanner.textContent, /Đề thi đã được phê duyệt và khóa nội dung vĩnh viễn/);

    // Không hiển thị nút Phê duyệt
    assert.equal(harness.container.querySelector('[data-testid="btn-open-approve"]'), null);

    // Nút chuyển sang màn hình Export
    const gotoExportBtn = harness.container.querySelector('[data-testid="btn-goto-export"]');
    assert.ok(gotoExportBtn);

    await act(async () => {
      gotoExportBtn.click();
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
    assert.match(harness.container.textContent, /Bản in Đề thi — Mã đề 101/);
  } finally {
    api.get = originalGet;
    await harness.unmount();
  }
});

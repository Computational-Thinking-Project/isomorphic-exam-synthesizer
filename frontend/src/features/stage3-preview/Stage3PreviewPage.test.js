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
    return { data: { ...GOLDEN_PREVIEW_FIXTURE, session_id: 'session-123' } };
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

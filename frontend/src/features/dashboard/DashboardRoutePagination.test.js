import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { register } from 'node:module';
import React, { act } from 'react';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { useAuthStore } from '../auth/authStore.js';
import { auth } from '../../services/test-support/supabase.stub.js';

ensureDomEnvironment();
document.oninput = null;

const { createRoot } = await import('react-dom/client');
const { MemoryRouter } = await import('react-router-dom');
register('../../test-loader.mjs', import.meta.url);
register('../../services/test-support/auth-loader.js', import.meta.url);

const { api } = await import('../../services/api.js');
const { default: DashboardRoute } = await import('./DashboardRoute.jsx');

function createSampleSession(id, title) {
  return {
    id,
    user_id: 'account-a',
    title,
    subject: 'Toán',
    grade: 12,
    status: 'draft',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  };
}

describe('DashboardRoute Pagination (F01 Regression Tests)', () => {
  let listCalls = [];

  beforeEach(() => {
    listCalls = [];
    useAuthStore.getState().setSession({
      user: { id: 'account-a' },
      access_token: 'fixture-token-a',
    });
    useAuthStore.getState().setProfile(
      { id: 'account-a', email: 'teacher@example.test', name: 'Giáo viên A' },
      useAuthStore.getState().sessionVersion,
    );
    auth.getSession = async () => ({
      data: { session: useAuthStore.getState().session },
      error: null,
    });
  });

  async function mountDashboard(totalItems = 25) {
    const container = document.createElement('div');
    const root = createRoot(container);

    api.defaults.adapter = async (config) => {
      if (config.url?.includes('/sessions') && config.method === 'get') {
        const page = config.params?.page || 1;
        const pageSize = config.params?.page_size || 20;
        listCalls.push({ page, pageSize, config });

        const startIndex = (page - 1) * pageSize;
        const items = [];
        for (let i = startIndex; i < Math.min(startIndex + pageSize, totalItems); i++) {
          items.push(createSampleSession(`s-${i + 1}`, `Đề thi số ${i + 1}`));
        }

        return {
          status: 200,
          data: {
            items,
            total: totalItems,
            page,
            page_size: pageSize,
          },
          headers: {},
          config,
        };
      }
      return { status: 200, data: {}, headers: {}, config };
    };

    await act(async () => {
      root.render(
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/dashboard'] },
          React.createElement(DashboardRoute),
        ),
      );
      // Wait for initial session loading
      await new Promise((r) => setTimeout(r, 60));
    });

    function getPaginationElements() {
      const nav = container.querySelector('nav[aria-label="Phân trang phiên đề"]');
      const buttons = nav ? nav.querySelectorAll('button') : [];
      const prevButton = buttons.find((b) => b.textContent.includes('Trước')) || null;
      const nextButton = buttons.find((b) => b.textContent.includes('Sau')) || null;
      const pageInfo = nav ? nav.querySelector('p') : null;

      const isPrevDisabled = prevButton
        ? (prevButton.getAttribute('disabled') !== null || Boolean(prevButton.disabled))
        : true;
      const isNextDisabled = nextButton
        ? (nextButton.getAttribute('disabled') !== null || Boolean(nextButton.disabled))
        : true;

      return {
        nav,
        prevButton,
        nextButton,
        pageInfoText: pageInfo ? pageInfo.textContent : '',
        isPrevDisabled,
        isNextDisabled,
      };
    }

    async function clickNext() {
      const { nextButton, isNextDisabled } = getPaginationElements();
      assert.ok(nextButton, 'Nút Sau phải tồn tại');
      if (isNextDisabled) return false;
      await act(async () => {
        nextButton.dispatchEvent({ type: 'click', bubbles: true });
        await new Promise((r) => setTimeout(r, 60));
      });
      return true;
    }

    async function clickPrev() {
      const { prevButton, isPrevDisabled } = getPaginationElements();
      assert.ok(prevButton, 'Nút Trước phải tồn tại');
      if (isPrevDisabled) return false;
      await act(async () => {
        prevButton.dispatchEvent({ type: 'click', bubbles: true });
        await new Promise((r) => setTimeout(r, 60));
      });
      return true;
    }

    async function unmount() {
      await act(async () => {
        root.unmount();
      });
    }

    return {
      container,
      root,
      getPaginationElements,
      clickNext,
      clickPrev,
      unmount,
    };
  }

  it('Ẩn phân trang cho danh sách rỗng và một trang; chỉ có một CTA tạo bộ đề', async () => {
    for (const total of [0, 1, 20]) {
      const dashboard = await mountDashboard(total);
      assert.equal(dashboard.getPaginationElements().nav, null);
      const createButtons = dashboard.container.querySelectorAll('button').filter(
        (element) => /Tạo bộ đề/.test(element.textContent),
      );
      assert.equal(createButtons.length, 1);
      assert.equal(dashboard.container.querySelector('select'), null);
      assert.equal(dashboard.container.querySelector('input'), null);
      await dashboard.unmount();
    }
  });

  it('F01: Có 2 trang — Trang 1 bấm Sau chuyển sang Trang 2; Trang 2 bấm Trước quay về Trang 1', async () => {
    const dashboard = await mountDashboard(25); // 25 items -> 2 trang (20 + 5)

    // Lúc đầu ở Trang 1
    let pagination = dashboard.getPaginationElements();
    assert.equal(pagination.isPrevDisabled, true, 'Trang 1: nút Trước phải disabled');
    assert.equal(pagination.isNextDisabled, false, 'Trang 1: nút Sau phải enabled');
    assert.match(pagination.pageInfoText, /Trang 1 \/ 2/);
    assert.equal(listCalls.at(-1)?.page, 1, 'Đang load trang 1');

    // Bấm "Sau" -> Chuyển sang Trang 2
    const clickedNext = await dashboard.clickNext();
    assert.equal(clickedNext, true, 'Phải click được nút Sau');

    pagination = dashboard.getPaginationElements();
    assert.equal(pagination.isPrevDisabled, false, 'Trang 2: nút Trước phải enabled');
    assert.equal(pagination.isNextDisabled, true, 'Trang 2: nút Sau phải disabled vì là trang cuối');
    assert.match(pagination.pageInfoText, /Trang 2 \/ 2/);
    assert.equal(listCalls.at(-1)?.page, 2, 'F01 Regression: Sau phải tăng page lên 2, không được giảm');

    // Bấm "Trước" -> Quay về Trang 1
    const clickedPrev = await dashboard.clickPrev();
    assert.equal(clickedPrev, true, 'Phải click được nút Trước');

    pagination = dashboard.getPaginationElements();
    assert.equal(pagination.isPrevDisabled, true, 'Quay về Trang 1: nút Trước phải disabled');
    assert.equal(pagination.isNextDisabled, false, 'Quay về Trang 1: nút Sau phải enabled');
    assert.match(pagination.pageInfoText, /Trang 1 \/ 2/);
    assert.equal(listCalls.at(-1)?.page, 1, 'Trước phải giảm page về 1');

    await dashboard.unmount();
  });

  it('Ở trang cuối cùng (2/2), bấm Sau không chuyển trang vượt quá giới hạn', async () => {
    const dashboard = await mountDashboard(25);

    // Chuyển sang trang 2
    await dashboard.clickNext();
    const callsBefore = listCalls.length;

    // Cố bấm Sau khi đang ở trang 2 (đang disabled)
    const clicked = await dashboard.clickNext();
    assert.equal(clicked, false, 'Không cho phép bấm nút Sau khi đã disabled');
    assert.equal(listCalls.length, callsBefore, 'Không gửi thêm request khi đã ở trang cuối');

    await dashboard.unmount();
  });
});

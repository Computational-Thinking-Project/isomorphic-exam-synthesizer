import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { register } from 'node:module';
import React, { act } from 'react';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { useAuthStore } from '../auth/authStore.js';
import { auth } from '../../services/test-support/supabase.stub.js';

ensureDomEnvironment();
document.oninput = null;
const { createRoot } = await import('react-dom/client');
const { MemoryRouter, Route, Routes } = await import('react-router-dom');
register('../../test-loader.mjs', import.meta.url);
register('../../services/test-support/auth-loader.js', import.meta.url);
const { api } = await import('../../services/api.js');
const { default: SessionExportPage } = await import('./SessionExportPage.jsx');

function findButtons(root, text) {
  const buttons = [];
  const walk = (node) => {
    if (!node) return;
    if (node.nodeName === 'BUTTON' && node.textContent.includes(text)) {
      buttons.push(node);
    }
    if (Array.isArray(node.childNodes)) {
      node.childNodes.forEach(walk);
    }
  };
  walk(root);
  return buttons;
}

async function mountExportPage(props, initialPath = '/session/s1/export') {
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => {
    root.render(
      React.createElement(
        MemoryRouter,
        { initialEntries: [initialPath] },
        React.createElement(
          Routes,
          null,
          React.createElement(Route, {
            path: '/session/:sessionId/export',
            element: React.createElement(SessionExportPage, props),
          }),
          React.createElement(Route, {
            path: '/dashboard',
            element: React.createElement('div', null, 'Dashboard'),
          }),
        ),
      ),
    );
  });
  await act(async () => {
    await Promise.resolve();
  });

  return {
    container,
    unmount: async () => {
      await act(async () => {
        root.unmount();
      });
    },
  };
}

beforeEach(() => {
  useAuthStore.getState().setSession({ user: { id: 'account-a' }, access_token: 'token-a' });
  useAuthStore.getState().setProfile(
    { id: 'account-a', email: 'teacher@example.test' },
    useAuthStore.getState().sessionVersion,
  );
  auth.getSession = async () => ({
    data: { session: useAuthStore.getState().session },
    error: null,
  });
});

test('SessionExportPage hiển thị trạng thái unwired khi chưa truyền Q10 API adapters', async () => {
  const view = await mountExportPage({
    loadSession: async (id) => ({
      id,
      title: 'Đề Đại số 12',
      subject: 'Toán',
      grade: 12,
      status: 'approved',
    }),
    getStatus: null,
    triggerExport: null,
    issueDownloadUrl: null,
  });

  assert.match(view.container.textContent, /Đề Đại số 12/);
  assert.match(view.container.textContent, /chưa được nối vào giao diện/);
  assert.match(view.container.textContent, /Thư viện đề/);
  await view.unmount();
});

test('SessionExportPage chặn phiên chưa approved/exported', async () => {
  const view = await mountExportPage({
    loadSession: async (id) => ({
      id,
      title: 'Đề đang soạn',
      subject: 'Toán',
      grade: 12,
      status: 'reviewed',
    }),
    getStatus: async () => {
      throw new Error('Must not call getStatus');
    },
  });

  assert.match(view.container.textContent, /Phiên chưa ở trạng thái đã duyệt cuối/);
  await view.unmount();
});


test('SessionExportPage prepares approved documents and lists direct PDF downloads', async () => {
  let starts = 0;
  const calls = [];
  api.defaults.adapter = async (config) => {
    calls.push(config);
    return { status: 200, statusText: 'OK', config, headers: {},
      data: { files: [{ filename: 'exam_101.pdf', size_bytes: 100 }] } };
  };
  const view = await mountExportPage({
    loadSession: async () => ({ id: 's1', title: 'Đề HK1', status: 'approved' }),
    getStatus: async () => ({ status: 'idle' }),
    triggerExport: async () => {
      starts += 1;
      return { status: 'ready', filename: 'exam_bundle_s1.zip' };
    },
  });
  await act(async () => {
    findButtons(view.container, 'Chuẩn bị tài liệu')[0].click();
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  assert.equal(starts, 1);
  assert.ok(findButtons(view.container, 'Tải exam_101.pdf').length);
  assert.ok(!view.container.textContent.includes('Tải gói ZIP'));
  assert.equal(calls[0].url, '/sessions/s1/export/files');
  assert.equal(calls[0].params.format, 'pdf');
  await view.unmount();
});

test('SessionExportPage shows a recoverable document listing failure', async () => {
  api.defaults.adapter = async () => { throw new Error('offline'); };
  const view = await mountExportPage({
    loadSession: async () => ({ id: 's1', title: 'Đề HK1', status: 'exported' }),
    getStatus: async () => ({ status: 'ready', filename: 'archive.zip' }),
  });
  assert.match(view.container.textContent, /Không tải được danh sách tài liệu/);
  assert.ok(findButtons(view.container, 'Thử lại').length);
  await view.unmount();
});

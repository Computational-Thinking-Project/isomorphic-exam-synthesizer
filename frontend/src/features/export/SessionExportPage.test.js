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
  assert.match(view.container.textContent, /Quay về Dashboard/);
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

test('SessionExportPage cho phép tạo gói ZIP và tải xuống khi đã nối adapter', async () => {
  let statusCalls = 0;
  let exportCalls = 0;
  let downloadCalls = 0;
  const opened = [];

  const view = await mountExportPage({
    loadSession: async (id) => ({
      id,
      title: 'Đề HK1',
      subject: 'Toán',
      grade: 12,
      status: 'approved',
    }),
    getStatus: async () => {
      statusCalls += 1;
      return { status: 'idle' };
    },
    triggerExport: async (id) => {
      exportCalls += 1;
      return { status: 'ready', filename: `exam_bundle_${id}.zip` };
    },
    issueDownloadUrl: async (id) => {
      downloadCalls += 1;
      return {
        url: `https://storage.example.test/${id}.zip`,
        expires_in: 3600,
        filename: `exam_bundle_${id}.zip`,
      };
    },
    openDownload: (url, filename) => opened.push({ url, filename }),
  });

  assert.equal(statusCalls, 1);
  assert.equal(exportCalls, 0);

  const exportBtn = findButtons(view.container, 'Tạo gói ZIP')[0];
  assert.ok(exportBtn);

  await act(async () => {
    exportBtn.click();
    await Promise.resolve();
  });

  assert.equal(exportCalls, 1);
  assert.match(view.container.textContent, /exam_bundle_s1\.zip/);

  const downloadBtn = findButtons(view.container, 'Tải gói ZIP')[0];
  assert.ok(downloadBtn);

  await act(async () => {
    downloadBtn.click();
    await Promise.resolve();
  });

  assert.equal(downloadCalls, 1);
  assert.deepEqual(opened, [{
    url: 'https://storage.example.test/s1.zip',
    filename: 'exam_bundle_s1.zip',
  }]);

  await view.unmount();
});

test('SessionExportPage chạy trọn luồng qua exportService mặc định với api adapter Q10', async () => {
  const requests = [];
  const opened = [];
  api.defaults.adapter = async (config) => {
    requests.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === 'get' && config.url === '/sessions/s1') {
      return {
        status: 200,
        data: {
          id: 's1',
          user_id: 'account-a',
          title: 'Đề thi thử Q10',
          subject: 'Toán',
          grade: 12,
          status: 'approved',
          created_at: '2026-11-01T00:00:00Z',
          updated_at: '2026-11-15T00:00:00Z',
          source_questions: [],
          exam_versions: [],
        },
        headers: {},
        config,
      };
    }
    if (config.method === 'get' && config.url === '/sessions/s1/export') {
      return { status: 200, data: { state: 'idle' }, headers: {}, config };
    }
    if (config.method === 'post' && config.url === '/sessions/s1/export') {
      return {
        status: 200,
        data: {
          state: 'ready',
          filename: 'exam_bundle_s1.zip',
          sha256: 'hash-q10',
          size_bytes: 5120,
        },
        headers: {},
        config,
      };
    }
    if (config.method === 'post' && config.url === '/sessions/s1/export/download-url') {
      return {
        status: 200,
        data: {
          url: 'https://storage.example.test/exam_bundle_s1.zip?sig=q10',
          expires_at: new Date(Date.now() + 3600_000).toISOString(),
          expires_in: 3600,
          filename: 'exam_bundle_s1.zip',
        },
        headers: {},
        config,
      };
    }
    throw new Error(`Unexpected HTTP call: ${config.method} ${config.url}`);
  };

  const view = await mountExportPage({
    openDownload: (url, filename) => opened.push({ url, filename }),
  });
  // Đợi getSessionDetail -> getExportStatus hoàn tất
  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  const exportBtn = findButtons(view.container, 'Tạo gói ZIP')[0];
  assert.ok(exportBtn);
  await act(async () => {
    exportBtn.click();
    await new Promise((r) => setTimeout(r, 10));
  });

  const downloadBtn = findButtons(view.container, 'Tải gói ZIP')[0];
  assert.ok(downloadBtn);
  await act(async () => {
    downloadBtn.click();
    await new Promise((r) => setTimeout(r, 10));
  });

  assert.deepEqual(
    requests.map((r) => `${r.method.toUpperCase()} ${r.url}`),
    [
      'GET /sessions/s1',
      'GET /sessions/s1/export',
      'POST /sessions/s1/export',
      'POST /sessions/s1/export/download-url',
    ],
  );
  assert.equal(requests[2].data, undefined);
  assert.equal(requests[3].data, undefined);
  assert.deepEqual(opened, [{
    url: 'https://storage.example.test/exam_bundle_s1.zip?sig=q10',
    filename: 'exam_bundle_s1.zip',
  }]);

  await view.unmount();
});

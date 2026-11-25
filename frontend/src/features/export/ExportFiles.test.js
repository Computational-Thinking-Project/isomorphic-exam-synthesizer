import assert from 'node:assert/strict';
import { test } from 'node:test';
import { register } from 'node:module';
import React, { act } from 'react';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { useAuthStore } from '../auth/authStore.js';
import { auth } from '../../services/test-support/supabase.stub.js';

ensureDomEnvironment();
const { createRoot } = await import('react-dom/client');
register('../../test-loader.mjs', import.meta.url);
register('../../services/test-support/auth-loader.js', import.meta.url);
const { api } = await import('../../services/api.js');
const { default: ExportFiles } = await import('./ExportFiles.jsx');

async function mountFiles(isCurrent) {
  useAuthStore.getState().setSession({ user: { id: 'a' }, access_token: 'token-a' });
  auth.getSession = async () => ({ data: { session: useAuthStore.getState().session }, error: null });
  const container = document.createElement('div');
  const root = createRoot(container);
  const render = async (sessionId) => {
    await act(async () => {
      root.render(React.createElement(React.StrictMode, null,
        React.createElement(ExportFiles, { sessionId, isCurrent })));
    });
  };
  await render('s1');
  return { container, render, unmount: () => act(async () => root.unmount()) };
}

for (const end of ['active', 'unmount', 'session', 'account']) {
  test(`ExportFiles bounds a deferred download to its current view (${end})`, async (t) => {
    let finish;
    let downloadConfig;
    let current = true;
    const clicked = [];
    const created = [];
    t.mock.method(URL, 'createObjectURL', (blob) => { created.push(blob); return 'blob:fixture'; });
    t.mock.method(URL, 'revokeObjectURL', () => {});
    const createElement = document.createElement.bind(document);
    t.mock.method(document, 'createElement', (name) => {
      const element = createElement(name);
      if (name === 'a') element.click = () => clicked.push(element.download);
      return element;
    });
    api.defaults.adapter = async (config) => {
      const response = (data) => ({ status: 200, statusText: 'OK', config, headers: {}, data });
      if (!config.params.filename) {
        return response({ files: [{ filename: `${config.url.includes('/s2/') ? 'second' : 'first'}.pdf`, size_bytes: 3 }] });
      }
      downloadConfig = config;
      return new Promise((resolve) => { finish = () => resolve(response(new Blob(['pdf']))); });
    };
    const view = await mountFiles(() => current);
    try {
      await act(async () => {
        view.container.querySelector('button').click();
      });
      assert.ok(downloadConfig, 'download started');
      assert.ok(downloadConfig.signal, 'the transport receives a cancellation signal');
      if (end === 'unmount') await view.unmount();
      if (end === 'session') await view.render('s2');
      if (end === 'account') current = false;
      if (end === 'unmount' || end === 'session') assert.equal(downloadConfig.signal.aborted, true);
      await act(async () => { finish(); });
      assert.deepEqual(clicked, end === 'active' ? ['first.pdf'] : []);
      assert.equal(created.length, end === 'active' ? 1 : 0);
      if (end === 'session') {
        assert.match(view.container.textContent, /Tải second.pdf/);
        assert.doesNotMatch(view.container.textContent, /Không tải được/);
      }
    } finally {
      if (end !== 'unmount') await view.unmount();
    }
  });
}

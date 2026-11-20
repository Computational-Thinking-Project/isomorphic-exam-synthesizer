import assert from 'node:assert/strict';
import { register } from 'node:module';
import { afterEach, beforeEach, test } from 'node:test';
import React, { act } from 'react';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { useAuthStore } from '../auth/authStore.js';
import { auth } from '../../services/test-support/supabase.stub.js';

ensureDomEnvironment();
const { createRoot } = await import('react-dom/client');
const { MemoryRouter, Route, Routes } = await import('react-router-dom');
register('../../test-loader.mjs', import.meta.url);
register('../../services/test-support/auth-loader.js', import.meta.url);

const { api } = await import('../../services/api.js');
const { default: ProtectedRoute } = await import('../auth/ProtectedRoute.jsx');
const { default: StatisticsPage } = await import('./StatisticsPage.jsx');
const { default: DashboardRoute } = await import('../dashboard/DashboardRoute.jsx');
const h = React.createElement;
const originalAdapter = api.defaults.adapter;
const empty = {
  total_sessions: 0,
  in_progress_sessions: 0,
  approved_not_exported_sessions: 0,
  exported_sessions: 0,
  by_status: Object.fromEntries([
    'draft', 'blueprinted', 'configured', 'generating', 'partial_generated', 'generated',
    'reviewed', 'approved', 'exported', 'failed', 'unknown',
  ].map((status) => [status, 0])),
};
const mixed = {
  total_sessions: 6,
  in_progress_sessions: 1,
  approved_not_exported_sessions: 1,
  exported_sessions: 1,
  by_status: { ...empty.by_status, generated: 1, approved: 1, exported: 1, failed: 2, unknown: 1 },
};

let root;
let container;

function signIn(id) {
  const store = useAuthStore.getState();
  store.setSession({ user: { id }, access_token: `token-${id}` });
  store.setProfile({ id, email: `${id}@example.test`, name: id }, useAuthStore.getState().sessionVersion);
}

function response(config, data) {
  return { status: 200, config, data, headers: {} };
}

async function mount(path = '/statistics') {
  await act(async () => root.render(h(MemoryRouter, { initialEntries: [path] },
    h(Routes, null,
      h(Route, { path: '/login', element: h('h1', null, 'Đăng nhập') }),
      h(Route, { element: h(ProtectedRoute) },
        h(Route, { path: '/statistics', element: h(StatisticsPage) }),
        h(Route, { path: '/dashboard', element: h(DashboardRoute) }),
      ),
    ),
  )));
}

beforeEach(() => {
  container = document.createElement('div');
  root = createRoot(container);
  signIn('teacher-a');
  auth.getSession = async () => ({ data: { session: useAuthStore.getState().session }, error: null });
});

afterEach(async () => {
  await act(async () => root.unmount());
  api.defaults.adapter = originalAdapter;
});

test('renders the private overview, chart values, fallback, and return link', async () => {
  const requests = [];
  api.defaults.adapter = async (config) => {
    requests.push(config);
    return response(config, mixed);
  };
  await mount();
  assert.deepEqual(requests.map(({ url }) => url), ['/users/me/statistics']);
  assert.equal(requests[0].headers.get('Authorization'), 'Bearer token-teacher-a');
  assert.ok(requests[0].signal);
  assert.equal(container.querySelector('a').getAttribute('href'), '/dashboard');
  assert.match(container.textContent, /2 phiên sinh đề gặp lỗi và 1 phiên chưa xác định trạng thái/);
  const chart = container.querySelector('section');
  assert.equal(chart.querySelectorAll('dt').length, 11);
  assert.match(chart.textContent, /Đã tạo gói xuất1/);
  assert.match(chart.textContent, /Chưa xác định1/);
  assert.match(chart.textContent, /Đang chuẩn bị đề gốc0/);
});

test('reports loading, retries a failure, and shows real zeros for an empty account', async () => {
  let rejectRequest;
  api.defaults.adapter = (config) => new Promise((_, reject) => {
    assert.equal(config.url, '/users/me/statistics');
    rejectRequest = reject;
  });
  await mount();
  assert.match(container.querySelector('[role="status"]').textContent, /Đang tải/);

  await act(async () => rejectRequest(new Error('Network offline')));
  assert.match(container.querySelector('[role="alert"]').textContent, /Không tải được/);
  api.defaults.adapter = async (config) => response(config, empty);
  await act(async () => container.querySelector('button').dispatchEvent({ type: 'click', bubbles: true }));
  assert.match(container.textContent, /Bạn chưa có phiên đề nào/);
  assert.deepEqual(Array.from(container.querySelectorAll('dd'), (item) => item.textContent), Array(4).fill('0phiên đề'));
});

test('aborts stale account data and renders the new account', async () => {
  let pending;
  api.defaults.adapter = (config) => config.headers.get('Authorization') === 'Bearer token-teacher-a'
    ? new Promise((resolve) => { pending = { resolve, config }; })
    : Promise.resolve(response(config, empty));

  await mount();
  await act(async () => signIn('teacher-b'));
  assert.equal(pending.config.signal.aborted, true);
  await act(async () => pending.resolve(response(pending.config, mixed)));
  assert.match(container.textContent, /Bạn chưa có phiên đề nào/);
  assert.doesNotMatch(container.textContent, /2 phiên sinh đề gặp lỗi/);
});

test('offers a Dashboard entry and gates direct signed-out visits', async () => {
  const requests = [];
  api.defaults.adapter = async (config) => {
    requests.push(config.url);
    return response(config, { items: [], total: 0, page: 1, page_size: 20 });
  };
  await mount('/dashboard');
  const entry = Array.from(container.querySelectorAll('a')).find((link) => link.getAttribute('href') === '/statistics');
  assert.equal(entry?.textContent, 'Thống kê sử dụng');

  await act(async () => root.unmount());
  root = createRoot(container);
  useAuthStore.getState().setSession(null);
  await mount();
  assert.equal(container.querySelector('h1').textContent, 'Đăng nhập');
  assert.deepEqual(requests, ['/sessions']);
});

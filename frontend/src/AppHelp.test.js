import assert from 'node:assert/strict';
import { register } from 'node:module';
import { afterEach, beforeEach, test } from 'node:test';
import { act, createElement } from 'react';
import { useAuthStore } from './features/auth/authStore.js';
import { auth } from './services/test-support/supabase.stub.js';
import { ensureDomEnvironment } from './test-support/domHarness.js';

ensureDomEnvironment();
document.oninput = null;
register('./test-loader.mjs', import.meta.url);
register('./services/test-support/auth-loader.js', import.meta.url);

const { createRoot } = await import('react-dom/client');
const { MemoryRouter, useLocation } = await import('react-router-dom');
const { AppRoutes } = await import('./App.jsx');
const { api } = await import('./services/api.js');

const profile = { id: 'teacher-fixture', email: 'teacher@example.test', name: 'Giáo viên thử nghiệm' };
const session = { user: { id: profile.id }, access_token: 'fixture-token' };
const initialAdapter = api.defaults.adapter;
const initialGetSession = auth.getSession;
let storedSession;
let authCalls;
let requests;

beforeEach(() => {
  storedSession = null;
  authCalls = [];
  requests = [];
  useAuthStore.getState().setSession(null);
  auth.getSession = async () => {
    authCalls.push('getSession');
    return { data: { session: storedSession }, error: null };
  };
  auth.onAuthStateChange = () => {
    authCalls.push('subscribe');
    return { data: { subscription: { unsubscribe() {} } } };
  };
  api.defaults.adapter = async (config) => {
    requests.push(config.url);
    const data = config.url === '/users/me'
      ? profile
      : { items: [], total: 0, page: 1, page_size: 20 };
    return { config, data, status: 200, headers: {} };
  };
});

afterEach(() => {
  api.defaults.adapter = initialAdapter;
  auth.getSession = initialGetSession;
  delete auth.onAuthStateChange;
});

function LocationProbe() {
  return createElement('output', null, useLocation().pathname);
}

async function mount(t, path) {
  const container = document.createElement('div');
  const root = createRoot(container);
  t.after(() => act(() => root.unmount()));

  await act(async () => {
    root.render(createElement(MemoryRouter, {
      initialEntries: [path],
      future: { v7_startTransition: true, v7_relativeSplatPath: true },
    }, createElement(AppRoutes), createElement(LocationProbe)));
  });
  return container;
}

async function clickLink(container, href) {
  const link = container.querySelector(`a[href="${href}"]`);
  assert.ok(link, `Expected a link to ${href}`);
  await act(async () => {
    link.dispatchEvent({ type: 'click', bubbles: true, button: 0, preventDefault() {} });
  });
}

test('public Help renders the guidance and anchors without starting auth', async (t) => {
  const container = await mount(t, '/help');
  assert.equal(container.querySelector('h1').textContent, 'Trung tâm trợ giúp');
  const stages = container.querySelector('section[aria-labelledby="bat-dau"]');
  assert.deepEqual(stages.querySelectorAll('h3').map((node) => node.textContent.slice(0, 7)), ['Stage 1', 'Stage 2', 'Stage 3']);
  assert.equal(container.querySelectorAll('details').length, 10);
  assert.equal(container.querySelector('section[aria-labelledby="xu-ly-loi"]').querySelectorAll('li').length, 7);
  assert.equal(container.querySelector('section[aria-labelledby="gioi-han-ai"]').querySelectorAll('li').length, 4);

  const toc = container.querySelector('nav[aria-labelledby="help-toc"]');
  const anchors = toc.querySelectorAll('a').map((link) => link.getAttribute('href'));
  assert.deepEqual(anchors, ['#bat-dau', '#faq', '#xu-ly-loi', '#gioi-han-ai']);
  for (const anchor of anchors) assert.ok(container.querySelector(anchor));
  assert.deepEqual(authCalls, []);
  assert.deepEqual(requests, []);
});

test('public Help also bypasses session and profile reads for signed-in states', async (t) => {
  for (const status of ['checking', 'profile_pending', 'authenticated']) {
    await t.test(status, async (caseContext) => {
      storedSession = session;
      useAuthStore.setState({ status, session, user: status === 'authenticated' ? profile : null });
      const container = await mount(caseContext, '/help');
      assert.equal(container.querySelector('output').textContent, '/help');
      assert.equal(container.querySelector('h1').textContent, 'Trung tâm trợ giúp');
      assert.ok(!container.textContent.includes(profile.email));
      assert.deepEqual(authCalls, []);
      assert.deepEqual(requests, []);
    });
  }
});

test('a guest can open Help from Login and return to Login', async (t) => {
  const container = await mount(t, '/login');
  assert.match(container.textContent, /Đăng nhập bằng Google/);
  await clickLink(container, '/help');
  assert.equal(container.querySelector('output').textContent, '/help');
  assert.equal(container.querySelector('a[href="/login"]').textContent, 'Đăng nhập');
  await clickLink(container, '/login');
  assert.equal(container.querySelector('output').textContent, '/login');
  assert.match(container.textContent, /Đăng nhập bằng Google/);
});

test('an authenticated teacher can open Help from the library and return there', async (t) => {
  storedSession = session;
  const container = await mount(t, '/dashboard');
  assert.equal(container.querySelector('h1').textContent, 'Thư viện đề');
  const before = { auth: [...authCalls], requests: [...requests] };
  await clickLink(container, '/help');
  assert.equal(container.querySelector('output').textContent, '/help');
  assert.equal(container.querySelector('a[href="/dashboard"]').textContent, 'Về Thư viện đề');
  assert.deepEqual(authCalls, before.auth);
  assert.deepEqual(requests, before.requests);
  await clickLink(container, '/dashboard');
  assert.equal(container.querySelector('h1').textContent, 'Thư viện đề');
});

test('a guest is still redirected away from protected routes', async (t) => {
  for (const path of ['/dashboard', '/session/fixture/stage1']) {
    await t.test(path, async (caseContext) => {
      const container = await mount(caseContext, path);
      assert.equal(container.querySelector('output').textContent, '/login');
      assert.match(container.textContent, /Đăng nhập bằng Google/);
      assert.deepEqual(requests, []);
    });
  }
});

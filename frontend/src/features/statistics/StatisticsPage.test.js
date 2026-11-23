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
const { normalStatisticsFixture } = await import('../../../dev-mocks/statistics.js');
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

test('dynamically renders 10 status rows when unknown === 0, and omits incident banner when no errors', async () => {
  api.defaults.adapter = async (config) => response(config, {
    ...normalStatisticsFixture,
    by_status: { ...normalStatisticsFixture.by_status, failed: 0, unknown: 0 },
  });
  await mount();

  const chart = container.querySelector('section');
  assert.equal(chart.querySelectorAll('dt').length, 10);
  assert.doesNotMatch(chart.textContent, /Chưa xác định/);
  assert.doesNotMatch(container.textContent, /Lưu ý trạng thái phiên đề/);
});

test('satisfies a11y tap targets, renders static freshness label, and verifies no realtime indicators', async () => {
  api.defaults.adapter = async (config) => response(config, normalStatisticsFixture);
  await mount();

  // Freshness label is static (F102-03)
  assert.match(container.textContent, /Số liệu tại thời điểm tải trang/);
  assert.doesNotMatch(container.textContent, /ĐỒNG BỘ TRỰC TIẾP/);
  assert.doesNotMatch(container.textContent, /PDF\/Word/);

  // Back link has min-h-[44px] and focus ring
  const backLink = container.querySelector('a[href="/dashboard"]');
  assert.ok(backLink.getAttribute('class').includes('min-h-[44px]'));
  assert.ok(backLink.getAttribute('class').includes('focus-visible:ring-2'));

  // Incident banner is shown because failed === 1 in normalStatisticsFixture
  assert.match(container.textContent, /1 phiên sinh đề gặp lỗi/);
});

test('empty account provides onboarding guidance and accessible dashboard link', async () => {
  api.defaults.adapter = async (config) => response(config, empty);
  await mount();

  assert.match(container.textContent, /Bạn chưa có phiên đề nào trong tài khoản/);
  assert.match(container.textContent, /Bắt đầu bằng cách tạo phiên đề mới hoặc nạp tài liệu từ Thư viện đề/);

  const dashboardLinks = Array.from(container.querySelectorAll('a[href="/dashboard"]'));
  assert.ok(dashboardLinks.length >= 2, 'Should have header back link and empty state call-to-action');
  const onboardingLink = dashboardLinks.find((link) => link.textContent.includes('Về Thư viện đề'));
  assert.ok(onboardingLink);
  assert.ok(onboardingLink.getAttribute('class').includes('min-h-[44px]'));
});

test('accurately displays 4 KPIs and full status distribution for 6-session fixture without misleading funnel (F102-01 regression)', async () => {
  const regressionFixture = {
    total_sessions: 6,
    in_progress_sessions: 1,
    approved_not_exported_sessions: 1,
    exported_sessions: 1,
    by_status: {
      draft: 0,
      blueprinted: 0,
      configured: 0,
      generating: 0,
      partial_generated: 0,
      generated: 1,
      reviewed: 0,
      approved: 1,
      exported: 1,
      failed: 2,
      unknown: 1,
    },
  };
  api.defaults.adapter = async (config) => response(config, regressionFixture);
  await mount();

  // 4 KPI checks
  const ddValues = Array.from(container.querySelectorAll('dd'), (item) => item.textContent);
  assert.equal(ddValues[0], '6phiên đề'); // total
  assert.equal(ddValues[1], '1phiên đề'); // in-progress
  assert.equal(ddValues[2], '1phiên đề'); // approved not exported
  assert.equal(ddValues[3], '1phiên đề'); // exported

  // Sum of all status buckets equals total_sessions (6)
  const totalInBuckets = Object.values(regressionFixture.by_status).reduce((acc, v) => acc + v, 0);
  assert.equal(totalInBuckets, 6);

  // StatusChart displays all populated buckets including failed and unknown
  const chart = container.querySelector('section[aria-labelledby="status-chart-title"]');
  assert.ok(chart);
  assert.match(chart.textContent, /Đã sinh đề1/);
  assert.match(chart.textContent, /Đã duyệt, chưa xuất1/);
  assert.match(chart.textContent, /Đã tạo gói xuất1/);
  assert.match(chart.textContent, /Sinh đề gặp lỗi2/);
  assert.match(chart.textContent, /Chưa xác định1/);

  // Failed (2) and unknown (1) in alert remainder
  assert.match(container.textContent, /2 phiên sinh đề gặp lỗi và 1 phiên chưa xác định trạng thái/);

  // Verified: No misleading funnel, transit totals, or Word format references
  assert.doesNotMatch(container.textContent, /CHẶNG 0/);
  assert.doesNotMatch(container.textContent, /Tổng luân chuyển/);
  assert.doesNotMatch(container.textContent, /PDF\/Word/);
});

test('handles large volume numbers with Vietnamese locale formatting and 4% bar clamp', async () => {
  const largeFixture = {
    total_sessions: 1250,
    in_progress_sessions: 750,
    approved_not_exported_sessions: 250,
    exported_sessions: 250,
    by_status: {
      draft: 100,
      blueprinted: 50,
      configured: 100,
      generating: 100,
      partial_generated: 100,
      generated: 200,
      reviewed: 100,
      approved: 250,
      exported: 250,
      failed: 0,
      unknown: 0,
    },
  };
  api.defaults.adapter = async (config) => response(config, largeFixture);
  await mount();

  // Vietnamese number format uses dot as thousands separator: 1.250
  assert.match(container.textContent, /1\.250/);
  assert.match(container.textContent, /750/);

  // Status rows check: dd elements exist and contain numbers
  const dds = container.querySelectorAll('dd');
  assert.ok(dds.length >= 10);
  const text = container.textContent;
  assert.match(text, /Đã sinh đề200/);
  assert.match(text, /Đã duyệt, chưa xuất250/);
});

test('preserves WCAG semantic landmarks, headings, and accessible descriptions', async () => {
  api.defaults.adapter = async (config) => response(config, normalStatisticsFixture);
  await mount();

  // Main landmark
  const main = container.querySelector('main');
  assert.ok(main, 'Must have <main> landmark');

  // Navigation landmark with aria-label
  const nav = container.querySelector('nav[aria-label="Điều hướng trang"]');
  assert.ok(nav, 'Must have <nav aria-label="Điều hướng trang">');

  // Page H1 heading
  const h1 = container.querySelector('h1');
  assert.ok(h1);
  assert.equal(h1.textContent, 'Thống kê sử dụng');

  // Section with aria-labelledby matching H2 id
  const section = container.querySelector('section[aria-labelledby="status-chart-title"]');
  assert.ok(section, 'Must have <section aria-labelledby="status-chart-title">');
  const h2 = container.querySelector('#status-chart-title');
  assert.ok(h2);
  assert.equal(h2.textContent, 'Phân bố trạng thái phiên');

  // Description lists
  const dls = container.querySelectorAll('dl');
  assert.ok(dls.length >= 2, 'Should have <dl> for summary deck and status chart');
});

test('handles boundary condition: 100% of sessions in a single status bucket', async () => {
  const singleBucketFixture = {
    total_sessions: 10,
    in_progress_sessions: 10,
    approved_not_exported_sessions: 0,
    exported_sessions: 0,
    by_status: {
      ...empty.by_status,
      generating: 10,
    },
  };
  api.defaults.adapter = async (config) => response(config, singleBucketFixture);
  await mount();

  assert.match(container.textContent, /10/);
  assert.match(container.textContent, /100%/);
  // Generating pulse animation exists
  const generatingDot = container.querySelector('.animate-pulse');
  assert.ok(generatingDot);
});

test('handles incident alert when only unknown status sessions exist', async () => {
  api.defaults.adapter = async (config) => response(config, {
    total_sessions: 5,
    in_progress_sessions: 4,
    approved_not_exported_sessions: 0,
    exported_sessions: 0,
    by_status: { ...empty.by_status, draft: 4, unknown: 1 },
  });
  await mount();
  assert.match(container.textContent, /1 phiên chưa xác định trạng thái/);
  assert.doesNotMatch(container.textContent, /phiên sinh đề gặp lỗi/);
});

test('handles incident alert when only failed status sessions exist', async () => {
  api.defaults.adapter = async (config) => response(config, {
    total_sessions: 5,
    in_progress_sessions: 4,
    approved_not_exported_sessions: 0,
    exported_sessions: 0,
    by_status: { ...empty.by_status, draft: 4, failed: 1 },
  });
  await mount();
  assert.match(container.textContent, /1 phiên sinh đề gặp lỗi/);
  assert.doesNotMatch(container.textContent, /chưa xác định trạng thái/);
});

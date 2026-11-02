import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { register } from 'node:module';
import axios from 'axios';
import React, { act } from 'react';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { useAuthStore } from '../auth/authStore.js';
import { auth } from '../../services/test-support/supabase.stub.js';

ensureDomEnvironment();
// Expose the standard input-event surface before ReactDOM detects DOM support.
document.oninput = null;
const { createRoot } = await import('react-dom/client');
const { renderToStaticMarkup } = await import('react-dom/server');
const { MemoryRouter, Route, Routes, useNavigate } = await import('react-router-dom');
register('../../test-loader.mjs', import.meta.url);
register('../../services/test-support/auth-loader.js', import.meta.url);
const { api } = await import('../../services/api.js');
const { default: Stage1Route } = await import('./Stage1Route.jsx');
const { default: ProtectedRoute } = await import('../auth/ProtectedRoute.jsx');
const { default: SourceQuestionPreview } = await import('./SourceQuestionPreview.jsx');
const question = (id = 'qa', sessionId = 'session-a') => ({
  id, session_id: sessionId, question_no: 1, raw_content: `Nguồn ${id}: rút gọn $\\frac{x^2-9}{x-3}$, với $x\\ne3$.`,
  options: { A: '$x-3$', B: '$x+3$', C: '$x$', D: '$3$' }, correct_key: 'B',
  question_blueprints: { internal: 'PRIVATE_BLUEPRINT' },
});
const detail = (id = 'session-a', questions = [question('qa', id)], status = 'draft') => ({
  id, user_id: 'account-a', title: `Phiên ${id}`, subject: 'Toán', grade: 12, status,
  created_at: '2026-11-02T00:00:00Z', updated_at: '2026-11-02T00:00:00Z',
  source_questions: questions, exam_versions: [],
});
const response = (config, data) => ({ status: 200, data, headers: {}, config });
let calls;
beforeEach(() => {
  calls = [];
  useAuthStore.getState().setSession({ user: { id: 'account-a' }, access_token: 'fixture-token-a' });
  useAuthStore.getState().setProfile({ id: 'account-a', email: 'teacher@example.test' }, useAuthStore.getState().sessionVersion);
  auth.getSession = async () => ({ data: { session: useAuthStore.getState().session }, error: null });
  api.defaults.adapter = async (config) => {
    calls.push(config.method);
    assert.equal(config.method, 'get');
    return response(config, detail(config.url.split('/').at(-1)));
  };
});
function mount(id = 'session-a') {
  const container = document.createElement('div');
  const root = createRoot(container);
  let navigate;
  function Navigation() { navigate = useNavigate(); return null; }
  return {
    container,
    render: () => act(async () => root.render(React.createElement(MemoryRouter,
      { initialEntries: [`/session/${id}/stage1`] }, React.createElement(Navigation),
      React.createElement(Routes, null,
        React.createElement(Route, { element: React.createElement(ProtectedRoute) },
          React.createElement(Route, { path: '/session/:sessionId/stage1', element: React.createElement(Stage1Route) })),
        React.createElement(Route, { path: '/login', element: React.createElement('p', null, 'Đăng nhập') }))))),
    navigate: (next) => act(async () => navigate(`/session/${next}/stage1`)),
    unmount: () => act(async () => root.unmount()),
  };
}
const button = (container, text) => container.querySelectorAll('button').find((el) => el.textContent === text);
const input = (container, text) => {
  const textarea = container.querySelector('textarea');
  Object.getOwnPropertyDescriptor(Object.getPrototypeOf(textarea), 'value').set.call(textarea, text);
  textarea.dispatchEvent({ type: 'input', bubbles: true });
};
const submit = (container) => container.querySelector('form').dispatchEvent({
  type: 'submit', bubbles: true, cancelable: true, preventDefault() {},
});

test('sự kiện input/submit thật của React gọi service rồi đổi đồng thời nguồn/count;422 giữ nguồn cũ', async () => {
  const app = mount();
  await app.render();
  await act(async () => input(app.container, 'Nguồn B'));
  assert.equal(app.container.querySelector('textarea').value, 'Nguồn B');
  api.defaults.adapter = async (config) => {
    calls.push(config.method);
    assert.equal(config.method, 'post');
    assert.deepEqual(JSON.parse(config.data), { raw_text: 'Nguồn B' });
    return response(config, { session_id: 'session-a', total_questions: 2,
      questions: [question('qb'), { ...question('qc'), question_no: 2 }] });
  };
  await act(async () => submit(app.container));
  assert(app.container.textContent.includes('2 câu nguồn'));
  assert(!app.container.textContent.includes('Nguồn qa'));
  assert(app.container.textContent.includes('Nguồn qb'));
  assert.deepEqual(calls, ['get', 'post']);
  await act(async () => input(app.container, 'Nguồn lỗi C'));
  api.defaults.adapter = async (config) => {
    throw { config, response: { status: 422, data: { detail: { errors: [{ question_no: 0 }] } } } };
  };
  await act(async () => submit(app.container));
  assert(app.container.textContent.includes('Chưa đọc được đầy đủ'));
  assert(app.container.textContent.includes('Nguồn qb'));
  assert(app.container.textContent.includes('2 câu nguồn'));
  assert.equal(app.container.querySelector('textarea').value, 'Nguồn lỗi C');
  await app.unmount();
});

test('timeout hiện cảnh báo, đọc lại nguồn không tự gửi hoặc mở khóa POST', async () => {
  const app = mount();
  await app.render();
  await act(async () => input(app.container, 'Nguồn B'));
  api.defaults.adapter = async (config) => {
    calls.push(config.method);
    if (config.method === 'post') throw Object.assign(new Error('Fixture timeout'), { config, code: 'ECONNABORTED' });
    return response(config, detail());
  };
  await act(async () => submit(app.container));
  assert(app.container.textContent.includes('Chưa xác nhận được kết quả'));
  assert.notEqual(button(app.container, 'Nạp nguồn').getAttribute('disabled'), null);
  await act(async () => button(app.container, 'Đọc lại nguồn đã lưu').click());
  assert(app.container.textContent.includes('Chưa xác nhận được kết quả'));
  assert.notEqual(button(app.container, 'Nạp nguồn').getAttribute('disabled'), null);
  assert.deepEqual(calls, ['get', 'post', 'get']);
  await app.unmount();
});

test('route mount/F5 đọc nguồn qua GET, preview/count/key khớp và không có POST', async () => {
  for (let reload = 0; reload < 2; reload++) {
    const app = mount();
    await app.render();
    assert(app.container.textContent.includes('1 câu nguồn'));
    assert(app.container.textContent.includes('Nguồn qa'));
    assert(app.container.textContent.includes('Đáp án: B'));
    assert(!app.container.textContent.includes('PRIVATE_BLUEPRINT'));
    assert(app.container.querySelector('textarea'));
    await app.unmount();
  }
  assert.deepEqual(calls, ['get', 'get']);
});

test('đọc lại nguồn cập nhật cùng count/preview; trạng thái mới không draft thì khóa nhập', async () => {
  const app = mount();
  await app.render();
  api.defaults.adapter = async (config) => {
    calls.push(config.method);
    return response(config, detail('session-a', [question('qb'), { ...question('qc'), question_no: 2 }], 'blueprinted'));
  };
  await act(async () => button(app.container, 'Đọc lại nguồn đã lưu').click());
  assert(app.container.textContent.includes('2 câu nguồn'), JSON.stringify({ text: app.container.textContent, calls }));
  assert(!app.container.textContent.includes('Nguồn qa'));
  assert(app.container.textContent.includes('Nguồn qb'));
  assert(app.container.textContent.includes('không còn ở trạng thái nháp'));
  assert.notEqual(button(app.container, 'Nạp nguồn').getAttribute('disabled'), null);
  assert.deepEqual(calls, ['get', 'get']);
  await app.unmount();
});

test('đổi route bỏ GET cũ trả muộn, không lộ nguồn phiên trước', async () => {
  let resolveA;
  api.defaults.adapter = (config) => config.url.endsWith('/session-a')
    ? new Promise((resolve) => { resolveA = () => resolve(response(config, detail())); })
    : Promise.resolve(response(config, detail('session-b', [question('qb', 'session-b')])));
  const app = mount();
  await app.render();
  await app.navigate('session-b');
  await act(async () => resolveA());
  assert(app.container.textContent.includes('Nguồn qb'));
  assert(!app.container.textContent.includes('Nguồn qa'));
  await app.unmount();
});

test('logout chặn Outlet và xóa nguồn đang hiển thị', async () => {
  const app = mount();
  await app.render();
  await act(async () => useAuthStore.getState().setSession(null));
  assert(app.container.textContent.includes('Đăng nhập'));
  assert(!app.container.textContent.includes('Nguồn qa'));
  assert.equal(app.container.querySelector('textarea'), null);
  await app.unmount();
});

test('đổi tài khoản xóa input/nguồn A; B bị404 phiên A rồi mở được nguồn của B', async () => {
  const app = mount();
  await app.render();
  await act(async () => input(app.container, 'Bản nháp riêng của A'));
  api.defaults.adapter = async (config) => {
    assert.equal(config.headers.get('Authorization'), 'Bearer fixture-token-b');
    if (config.url.endsWith('/session-a')) {
      throw new axios.AxiosError('Not found', 'ERR_BAD_RESPONSE', config, null, { status: 404, data: {}, config });
    }
    return response(config, { ...detail('session-b', [question('qb', 'session-b')]), user_id: 'account-b' });
  };
  await act(async () => {
    useAuthStore.getState().setSession({ user: { id: 'account-b' }, access_token: 'fixture-token-b' });
    useAuthStore.getState().setProfile({ id: 'account-b', email: 'teacher-b@example.test' }, useAuthStore.getState().sessionVersion);
  });
  assert(app.container.textContent.includes('Không tìm thấy phiên'));
  assert(!app.container.textContent.includes('Nguồn qa'));
  assert.equal(app.container.querySelector('textarea'), null);
  await app.navigate('session-b');
  assert(app.container.textContent.includes('Nguồn qb'));
  assert.equal(app.container.querySelector('textarea').value, '');
  await app.unmount();
});

test('POST đang chờ khi đổi route: hủy signal, input mới rỗng, response cũ không ghi đè nguồn B', async () => {
  const app = mount();
  await app.render();
  let resolvePost;
  let signal;
  api.defaults.adapter = (config) => {
    if (config.method === 'post') {
      signal = config.signal;
      return new Promise((resolve) => { resolvePost = () => resolve(response(config, {
        session_id: 'session-a', total_questions: 1, questions: [question('late-post-A')],
      })); });
    }
    return Promise.resolve(response(config, detail('session-b', [question('qb', 'session-b')])));
  };
  await act(async () => input(app.container, 'Nguồn A đang gửi'));
  await act(async () => submit(app.container));
  assert.notEqual(button(app.container, 'Nạp nguồn').getAttribute('disabled'), null);
  await app.navigate('session-b');
  assert(signal.aborted);
  await act(async () => resolvePost());
  assert(app.container.textContent.includes('Nguồn qb'));
  assert(!app.container.textContent.includes('late-post-A'));
  assert.equal(app.container.querySelector('textarea').value, '');
  await app.unmount();
});

test('new chỉ hiện metadata, không GET detail/POST hoặc mount input nguồn', async () => {
  const app = mount('new');
  await app.render();
  assert(app.container.textContent.includes('Tạo phiên đề mới'));
  assert.equal(app.container.querySelector('textarea'), null);
  assert.deepEqual(calls, []);
  await app.unmount();
});

test('preview read-only dùng MathRenderer cho stem/options, giữ điều kiện/key và ẩn Blueprint', () => {
  const html = renderToStaticMarkup(React.createElement(SourceQuestionPreview, { questions: [question()] }));
  assert(html.includes('katex'));
  assert(html.includes('x\\ne3'));
  assert(html.includes('Đáp án: <strong>B</strong>'));
  assert(!html.includes('PRIVATE_BLUEPRINT'));
  assert(!html.includes('<textarea'));
  assert(!html.includes('<button'));
});

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
const selectFile = (container, files) => {
  const picker = container.querySelector('input[type="file"]');
  picker.files = files;
  picker.value = files.length ? `C:\\fakepath\\${files[0].name}` : '';
  picker.dispatchEvent({ type: 'change', bubbles: true });
  return picker;
};
const dropFiles = (container, files) => container.querySelector('input[type="file"]').parentNode.dispatchEvent({
  type: 'drop', bubbles: true, dataTransfer: { files }, preventDefault() {},
});

test('file picker: chỉ chọn/đổi cách nhập không POST; reset chọn lại cùng file, submit gửi đúng multipart', async () => {
  const app = mount();
  await app.render();
  await act(async () => input(app.container, 'Text chưa gửi'));
  await act(async () => button(app.container, 'Tải tệp').click());
  const file = new File(['### Câu 1: Giải $3x-5=10$.'], 'đại số.MD');
  let picker;
  await act(async () => { picker = selectFile(app.container, [file]); });
  assert.equal(picker.value, '');
  assert.equal(picker.getAttribute('accept'), '.docx,.tex,.md');
  assert(app.container.textContent.includes('Đã chọn: đại số.MD'));
  assert(app.container.textContent.includes(`(${file.size.toLocaleString('vi-VN')} byte)`));
  await act(async () => selectFile(app.container, [file]));
  await act(async () => button(app.container, 'Nhập trực tiếp').click());
  assert.equal(app.container.querySelector('textarea').value, 'Text chưa gửi');
  await act(async () => button(app.container, 'Tải tệp').click());
  assert(app.container.textContent.includes('Đã chọn: đại số.MD'));
  assert.deepEqual(calls, ['get']);
  api.defaults.adapter = async (config) => {
    calls.push(config.method);
    assert(config.url.endsWith('/ingest-file'));
    assert(config.data instanceof FormData);
    assert.deepEqual([...config.data.keys()], ['file']);
    assert.equal(config.data.get('file').name, file.name);
    assert.equal(await config.data.get('file').text(), await file.text());
    return response(config, { session_id: 'session-a', total_questions: 1, questions: [question('qb')] });
  };
  await act(async () => submit(app.container));
  assert(app.container.textContent.includes('Nguồn qb'));
  assert(!app.container.textContent.includes('Nguồn qa'));
  assert.deepEqual(calls, ['get', 'post']);
  await app.unmount();
});

test('drop/file validation:PDF/đuôi khác/0byte/quá10MiB/nhiều file chặn POST, sát giới hạn và bỏ chọn được', async () => {
  const app = mount();
  await app.render();
  await act(async () => button(app.container, 'Tải tệp').click());
  for (const files of [[], [new File(['x'], 'de.pdf')], [new File(['x'], 'de.txt')],
    [new File([], 'de.md')], [new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'de.md')],
    [new File(['x'], 'a.md'), new File(['y'], 'b.tex')]]) {
    await act(async () => dropFiles(app.container, files));
    assert(app.container.querySelector('[role="alert"]'));
    assert(app.container.textContent.includes('Chưa chọn tệp.'));
    await act(async () => submit(app.container));
    assert.deepEqual(calls, ['get']);
    assert(app.container.textContent.includes('Nguồn qa'));
  }
  for (const file of [new File([new Uint8Array(10 * 1024 * 1024)], 'giới hạn.DOCX'), new File(['x'], 'đề.TeX')]) {
    await act(async () => dropFiles(app.container, [file]));
    assert.equal(app.container.querySelector('[role="alert"]'), null);
    assert(app.container.textContent.includes(`Đã chọn: ${file.name}`));
  }
  await act(async () => button(app.container, 'Bỏ chọn tệp').click());
  assert(app.container.textContent.includes('Chưa chọn tệp.'));
  assert.deepEqual(calls, ['get']);
  await app.unmount();
});

test('file progress: không total không phần trăm;100% chỉ đang xử lý,422 giữ nguồn/file để chọn lại', async () => {
  const app = mount();
  await app.render();
  await act(async () => button(app.container, 'Tải tệp').click());
  const file = new File(['Nguồn sai định dạng'], 'đề.md');
  await act(async () => selectFile(app.container, [file]));
  let progress;
  let rejectPost;
  api.defaults.adapter = (config) => {
    calls.push(config.method);
    progress = config.onUploadProgress;
    return new Promise((resolve, reject) => { rejectPost = () => reject({ config,
      response: { status: 422, data: { detail: { errors: [{ question_no: 1, error_type: 'MISSING_ANSWER' }] } } } }); });
  };
  await act(async () => submit(app.container));
  assert.equal(app.container.querySelector('progress').getAttribute('value'), null);
  await act(async () => progress({ loaded: 4 }));
  assert(app.container.textContent.includes('Đang tải tệp lên…'));
  assert.equal(app.container.querySelector('progress').getAttribute('value'), null);
  await act(async () => progress({ loaded: 5, total: 10 }));
  assert(app.container.textContent.includes('50%'));
  await act(async () => progress({ loaded: 10, total: 10 }));
  assert(app.container.textContent.includes('Đã tải tệp lên. Đang xử lý nguồn…'));
  assert(!app.container.textContent.includes('Đã nạp'));
  assert(app.container.textContent.includes('Nguồn qa'));
  assert.notEqual(button(app.container, 'Nạp nguồn').getAttribute('disabled'), null);
  assert.notEqual(button(app.container, 'Nhập trực tiếp').getAttribute('disabled'), null);
  await act(async () => submit(app.container));
  assert.deepEqual(calls, ['get', 'post']);
  await act(async () => rejectPost());
  assert(app.container.textContent.includes('Chưa đọc được đầy đủ'));
  assert(app.container.textContent.includes('Nguồn qa'));
  assert(app.container.textContent.includes('Đã chọn: đề.md'));
  assert.equal(app.container.querySelector('progress'), null);
  await act(async () => selectFile(app.container, [file]));
  assert.equal(app.container.querySelector('input[type="file"]').value, '');
  await app.unmount();
});

test('file pending: đổi route hủy và bỏ progress/response cũ, không giữ file ở phiên mới', async () => {
  const app = mount();
  await app.render();
  await act(async () => button(app.container, 'Tải tệp').click());
  await act(async () => selectFile(app.container, [new File(['nguồn A'], 'riêng-A.md')]));
  let configA;
  let resolvePost;
  api.defaults.adapter = (config) => {
    if (config.method === 'post') {
      configA = config;
      return new Promise((resolve) => { resolvePost = () => resolve(response(config, {
        session_id: 'session-a', total_questions: 1, questions: [question('late-A')],
      })); });
    }
    return Promise.resolve(response(config, detail('session-b', [question('qb', 'session-b')])));
  };
  await act(async () => submit(app.container));
  await app.navigate('session-b');
  assert(configA.signal.aborted);
  await act(async () => { configA.onUploadProgress({ loaded: 10, total: 10 }); resolvePost(); });
  assert(app.container.textContent.includes('Nguồn qb'));
  assert(!app.container.textContent.includes('late-A'));
  assert(!app.container.textContent.includes('riêng-A.md'));
  assert.equal(app.container.querySelector('progress'), null);
  await act(async () => button(app.container, 'Tải tệp').click());
  assert(app.container.textContent.includes('Chưa chọn tệp.'));
  await app.unmount();
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

const incompleteResponse = (errors = [{ question_no: 1, error_type: 'MISSING_ANSWER' }]) => ({
  status: 422, data: { detail: { message: 'Exam incomplete', errors } },
});
const dialog = container => container.querySelector('[role="dialog"]');
const dialogButton = (container, text) => button(dialog(container), text);

test('203b: text422 mở lỗi toàn đề/câu; đóng/đổi mode không POST, sửa rồi nạp thay A đúng lúc', async () => {
  const app = mount();
  await app.render();
  await act(async () => input(app.container, 'Nguồn B thiếu key'));
  let attempts = 0;
  api.defaults.adapter = async config => {
    calls.push(config.method);
    if (++attempts === 1) throw { config, response: incompleteResponse([
      { question_no: 0, error_type: 'INVALID_FORMAT' }, { question_no: 3, error_type: 'MISSING_ANSWER' },
    ]) };
    return response(config, { session_id: 'session-a', total_questions: 1, questions: [question('qb')] });
  };
  await act(async () => submit(app.container));
  assert(dialog(app.container).textContent.includes('Toàn đề'));
  assert(dialog(app.container).textContent.includes('Câu 3'));
  assert(!dialog(app.container).textContent.includes('Câu 0'));
  assert(app.container.textContent.includes('Nguồn qa'));
  assert.equal(app.container.querySelector('textarea').value, 'Nguồn B thiếu key');
  await act(async () => dialogButton(app.container, 'Đóng').click());
  await act(async () => button(app.container, 'Tải tệp').click());
  await act(async () => button(app.container, 'Nhập trực tiếp').click());
  assert.equal(dialog(app.container), null);
  assert.deepEqual(calls, ['get', 'post']);
  await act(async () => input(app.container, 'Nguồn B đã sửa'));
  await act(async () => submit(app.container));
  assert.equal(dialog(app.container), null);
  assert(app.container.textContent.includes('Nguồn qb'));
  assert(!app.container.textContent.includes('Nguồn qa'));
  assert.deepEqual(calls, ['get', 'post', 'post']);
  await app.unmount();
});

test('203b: lần nạp mới có thể mở lại cùng error object, không tự mở khi đóng hoặc rerender', async () => {
  const app = mount();
  await app.render();
  const sameError = { response: incompleteResponse() };
  api.defaults.adapter = async config => { calls.push(config.method); sameError.config = config; throw sameError; };
  await act(async () => input(app.container, 'Nguồn sai'));
  await act(async () => submit(app.container));
  assert(dialog(app.container));
  await act(async () => dialogButton(app.container, 'Đóng').click());
  await act(async () => input(app.container, 'Nguồn vẫn sai'));
  assert.equal(dialog(app.container), null);
  assert.deepEqual(calls, ['get', 'post']);
  await act(async () => submit(app.container));
  assert(dialog(app.container));
  assert.deepEqual(calls, ['get', 'post', 'post']);
  await app.unmount();
});

test('203b: chọn file từ dialog text dùng cùng picker trong click, giữ text và không tự POST', async () => {
  const app = mount();
  await app.render();
  const picker = app.container.querySelector('input[type="file"]');
  assert.equal(picker.parentNode.getAttribute('hidden'), '');
  let pickerClicks = 0;
  picker.addEventListener('click', () => { pickerClicks++; });
  await act(async () => input(app.container, 'Text B chưa hoàn chỉnh'));
  api.defaults.adapter = async config => { calls.push(config.method); throw { config, response: incompleteResponse() }; };
  await act(async () => submit(app.container));
  await act(async () => dialogButton(app.container, 'Chọn tệp đã sửa').click());
  assert.equal(pickerClicks, 1);
  assert.equal(dialog(app.container), null);
  assert.equal(app.container.querySelector('input[type="file"]'), picker);
  assert.equal(picker.parentNode.getAttribute('hidden'), null);
  assert.equal(document.activeElement, picker);
  await act(async () => selectFile(app.container, [new File(['B đã sửa'], 'sua-lai.md')]));
  await act(async () => button(app.container, 'Nhập trực tiếp').click());
  assert.equal(app.container.querySelector('textarea').value, 'Text B chưa hoàn chỉnh');
  assert.deepEqual(calls, ['get', 'post']);
  await app.unmount();
});

test('203b: file422 → chuyển text đúng focus/giữ input; chọn lại cùng file chỉ gửi khi bấm Nạp', async () => {
  const app = mount();
  await app.render();
  await act(async () => input(app.container, 'Text dự phòng'));
  await act(async () => button(app.container, 'Tải tệp').click());
  const file = new File(['B thiếu key'], 'loi.md');
  await act(async () => selectFile(app.container, [file]));
  api.defaults.adapter = async config => { calls.push(config.method); throw { config, response: incompleteResponse() }; };
  await act(async () => submit(app.container));
  assert(app.container.textContent.includes('Đã chọn: loi.md'));
  await act(async () => dialogButton(app.container, 'Chuyển sang Nhập trực tiếp').click());
  const textarea = app.container.querySelector('textarea');
  assert.equal(textarea.value, 'Text dự phòng');
  assert.equal(document.activeElement, textarea);
  await act(async () => button(app.container, 'Tải tệp').click());
  await act(async () => selectFile(app.container, [file]));
  assert.equal(app.container.querySelector('input[type="file"]').value, '');
  assert.equal(dialog(app.container), null);
  assert(app.container.textContent.includes('Nguồn qa'));
  assert.deepEqual(calls, ['get', 'post']);
  api.defaults.adapter = async config => {
    calls.push(config.method);
    return response(config, { session_id: 'session-a', total_questions: 1, questions: [question('qb')] });
  };
  await act(async () => submit(app.container));
  assert.equal(dialog(app.container), null);
  assert(app.container.textContent.includes('Nguồn qb'));
  assert.deepEqual(calls, ['get', 'post', 'post']);
  await app.unmount();
});

test('203b: các lỗi khác không mở dialog; timeout vẫn giữ uncertain/khóa gửi', async () => {
  for (const failure of [
    { response: { status: 422, data: { detail: [{ loc: ['body'], msg: 'required' }] } } },
    { response: { status: 422, data: { detail: 'No questions' } } },
    { response: incompleteResponse([]) }, { response: { status: 400 } },
    { response: { status: 409 } }, { response: { status: 429 } }, { code: 'ECONNABORTED' },
  ]) {
    calls = [];
    api.defaults.adapter = async config => { calls.push(config.method); return response(config, detail()); };
    const app = mount();
    await app.render();
    await act(async () => input(app.container, 'B'));
    api.defaults.adapter = async config => { calls.push(config.method); throw { ...failure, config }; };
    await act(async () => submit(app.container));
    assert.equal(dialog(app.container), null);
    assert(app.container.querySelector('[role="alert"]'));
    assert(app.container.textContent.includes('Nguồn qa'));
    if (failure.code === 'ECONNABORTED') {
      assert(app.container.textContent.includes('Chưa xác nhận được kết quả'));
      assert.notEqual(button(app.container, 'Nạp nguồn').getAttribute('disabled'), null);
    }
    assert.deepEqual(calls, ['get', 'post']);
    await app.unmount();
  }
});

test('203b: lỗi GET có envelope422 không mở nhầm dialog hoặc che cảnh báo đọc lại', async () => {
  const app = mount();
  await app.render();
  await act(async () => input(app.container, 'B'));
  api.defaults.adapter = async config => { calls.push(config.method); throw { config, response: incompleteResponse() }; };
  await act(async () => submit(app.container));
  await act(async () => dialogButton(app.container, 'Đóng').click());
  await act(async () => button(app.container, 'Đọc lại nguồn đã lưu').click());
  assert.equal(dialog(app.container), null);
  assert(app.container.textContent.includes('Chưa đọc lại được phiên'));
  assert.notEqual(button(app.container, 'Nạp nguồn').getAttribute('disabled'), null);
  assert.deepEqual(calls, ['get', 'post', 'get']);
  await app.unmount();
});

test('203b: đổi route bỏ incomplete trả muộn; logout khi dialog đang mở xóa cả lỗi và input', async () => {
  const app = mount();
  await app.render();
  await act(async () => input(app.container, 'Nguồn A đang gửi'));
  let rejectOld;
  api.defaults.adapter = config => {
    calls.push(config.method);
    if (config.method === 'post') return new Promise((resolve, reject) => { rejectOld = () => reject({ config, response: incompleteResponse() }); });
    return Promise.resolve(response(config, detail('session-b', [question('qb', 'session-b')])));
  };
  await act(async () => submit(app.container));
  await app.navigate('session-b');
  await act(async () => rejectOld());
  assert.equal(dialog(app.container), null);
  assert(app.container.textContent.includes('Nguồn qb'));
  assert.equal(app.container.querySelector('textarea').value, '');
  api.defaults.adapter = async config => { throw { config, response: incompleteResponse() }; };
  await act(async () => input(app.container, 'Nguồn B sai'));
  await act(async () => submit(app.container));
  assert(dialog(app.container));
  await act(async () => useAuthStore.getState().setSession(null));
  assert.equal(dialog(app.container), null);
  assert(app.container.textContent.includes('Đăng nhập'));
  assert.equal(app.container.querySelector('textarea'), null);
  await app.unmount();
});

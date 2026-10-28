import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createSessionOpener, sessionDestination } from './sessionDestination.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function setup(overrides = {}) {
  const calls = [];
  const destinations = [];
  const opener = createSessionOpener({
    load: async (id, config) => { calls.push({ id, config }); return { id, status: 'draft' }; },
    navigate: (path) => destinations.push(path),
    isCurrent: () => true,
    ...overrides,
  });
  return { opener, calls, destinations };
}

test('resolver chỉ nối draft; chín enum còn lại và unknown không tới màn chưa có', () => {
  assert.deepEqual(sessionDestination({ id: 'a/b', status: 'draft' }), { path: '/session/a%2Fb/stage1', notice: '' });
  for (const status of ['blueprinted', 'configured', 'generating', 'partial_generated', 'generated', 'reviewed', 'approved', 'exported', 'failed']) {
    const result = sessionDestination({ id: 'saved', status });
    assert.equal(result.path, null);
    assert.match(result.notice, /chưa được kết nối/);
  }
  for (const status of ['future_status', '__proto__', undefined]) {
    const result = sessionDestination({ id: 'saved', status });
    assert.equal(result.path, null);
    assert.match(result.notice, /chưa được hỗ trợ/);
  }
});

test('chỉ đọc detail khi bấm mở, lấy trạng thái mới thay vì badge list', async () => {
  let status = 'configured';
  const { opener, calls, destinations } = setup({ load: async (id) => { calls.push({ id }); return { id, status }; } });
  assert.equal(calls.length, 0);
  await opener.open('saved');
  assert.deepEqual(destinations, []);
  assert.match(opener.getSnapshot().notice, /chưa được kết nối/);
  status = 'draft';
  await opener.open('saved');
  assert.deepEqual(destinations, ['/session/saved/stage1']);
  assert.equal(calls.length, 2);
});

test('pending chặn click lặp; hủy mở abort request và bỏ kết quả về muộn', async () => {
  const pending = deferred();
  let signal;
  let requests = 0;
  const { opener, destinations } = setup({ load: (_, config) => { requests += 1; signal = config.signal; return pending.promise; } });
  const first = opener.open('saved');
  await opener.open('saved');
  assert.equal(requests, 1);
  assert.equal(opener.getSnapshot().phase, 'loading');
  opener.cancel();
  assert.equal(signal.aborted, true);
  pending.resolve({ id: 'saved', status: 'draft' });
  await first;
  assert.equal(opener.getSnapshot().phase, 'idle');
  assert.deepEqual(destinations, []);
});

test('đổi ID bỏ response cũ cả khi adapter không tôn trọng abort', async () => {
  const pending = deferred();
  let oldSignal;
  const { opener, destinations } = setup({ load: (id, config) => {
    if (id === 'old') { oldSignal = config.signal; return pending.promise; }
    return Promise.resolve({ id, status: 'draft' });
  } });
  const old = opener.open('old');
  await opener.open('next');
  assert.equal(oldSignal.aborted, true);
  pending.resolve({ id: 'old', status: 'draft' });
  await old;
  assert.equal(opener.getSnapshot().sessionId, 'next');
  assert.deepEqual(destinations, ['/session/next/stage1']);
});

for (const rejects of [false, true]) {
  test(`đổi account/logout bỏ ${rejects ? 'lỗi' : 'detail'} cũ và không điều hướng`, async () => {
    let current = true;
    const pending = deferred();
    const { opener, destinations } = setup({ load: () => pending.promise, isCurrent: () => current });
    const request = opener.open('saved');
    const snapshot = opener.getSnapshot();
    current = false;
    if (rejects) pending.reject(new Error('Private error'));
    else pending.resolve({ id: 'saved', status: 'draft' });
    await request;
    assert.equal(opener.getSnapshot(), snapshot);
    await opener.open('another');
    assert.deepEqual(destinations, []);
  });
}

test('lỗi chỉ hiện thông báo an toàn; không tự retry, thử lại chủ động đọc detail mới', async () => {
  for (const status of [401, 403, 404, 422, 429, 500, undefined]) {
    let attempts = 0;
    const { opener, destinations } = setup({ load: async (id) => {
      attempts += 1;
      if (attempts === 1) throw { response: { status }, message: 'PRIVATE_BACKEND_DETAIL' };
      return { id, status: 'draft' };
    } });
    await opener.open('saved');
    assert.equal(attempts, 1);
    assert.equal(opener.getSnapshot().phase, 'error');
    assert.ok(opener.getSnapshot().error);
    assert.doesNotMatch(opener.getSnapshot().error, /PRIVATE_BACKEND_DETAIL/);
    assert.deepEqual(destinations, []);
    await opener.open('saved');
    assert.equal(attempts, 2);
    assert.deepEqual(destinations, ['/session/saved/stage1']);
  }
});

test('rời trang rồi mở mới không để lỗi request cũ ghi đè', async () => {
  const pending = deferred();
  const { opener, destinations } = setup({ load: (id) => id === 'old' ? pending.promise : Promise.resolve({ id, status: 'draft' }) });
  const old = opener.open('old');
  opener.cancel();
  await opener.open('next');
  pending.reject(new Error('Late failure'));
  await old;
  assert.equal(opener.getSnapshot().sessionId, 'next');
  assert.equal(opener.getSnapshot().error, '');
  assert.deepEqual(destinations, ['/session/next/stage1']);
});

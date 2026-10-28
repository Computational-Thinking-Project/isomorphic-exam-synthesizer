import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createSessionEntryController, validateSessionMetadata } from './sessionEntry.js';

const metadata = { title: ' Phiên mới ', subject: ' Vật lý ', grade: 11 };
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const options = { timeout: 2000 };
function setup(overrides = {}) {
  const calls = [];
  const destinations = [];
  const controller = createSessionEntryController({
    create: async (body, config) => { calls.push({ body, config }); return { id: 'created-id' }; },
    load: async (id, config) => { calls.push({ id, config }); return { id, status: 'draft' }; },
    onCreated: (id) => destinations.push(id),
    ...overrides,
  });
  return { controller, calls, destinations };
}

test('entry khởi tạo không tự tạo/đọc phiên; chỉ submit mới POST metadata đã trim', options, async () => {
  const { controller, calls, destinations } = setup();
  assert.equal(controller.getSnapshot().phase, 'idle');
  assert.equal(calls.length, 0);
  await controller.submit({ ...metadata, user_id: 'injected-owner', status: 'approved' });
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].body, { title: 'Phiên mới', subject: 'Vật lý', grade: 11 });
  assert.ok(calls[0].config.signal instanceof AbortSignal);
  assert.deepEqual(destinations, ['created-id']);
  await controller.submit(metadata);
  assert.equal(calls.length, 1);
});

test('input không hợp lệ không gửi request hoặc điều hướng; chấp nhận môn/lớp ngoài default', options, async () => {
  const { controller, calls, destinations } = setup();
  for (const invalid of [{ title: '   ' }, { title: 'a'.repeat(256) }, { subject: 'a'.repeat(101) }, { grade: '' }, { grade: 1.5 }, { grade: 13 }]) {
    await controller.submit({ ...metadata, ...invalid });
    assert.ok(controller.getSnapshot().error);
  }
  assert.equal(calls.length, 0);
  assert.deepEqual(destinations, []);
  assert.equal(validateSessionMetadata({ title: '😀'.repeat(255), subject: 'Hóa học', grade: 1 }), '');
});

test('submit liên tiếp khi pending chỉ tạo đúng một phiên', options, async () => {
  const pending = deferred();
  let requests = 0;
  const { controller, destinations } = setup({ create: () => { requests += 1; return pending.promise; } });
  const first = controller.submit(metadata);
  await controller.submit(metadata);
  assert.equal(requests, 1);
  assert.equal(controller.getSnapshot().phase, 'creating');
  pending.resolve({ id: 'one-id' });
  await first;
  assert.deepEqual(destinations, ['one-id']);
});

test('mở/F5 phiên chỉ đọc detail, không POST; trạng thái mới được giữ nguyên', options, async () => {
  const { controller, calls, destinations } = setup({ create: () => { throw new Error('Must not create'); } });
  await controller.load('saved-id');
  await controller.load('saved-id');
  assert.deepEqual(calls.map((call) => call.id), ['saved-id', 'saved-id']);
  assert.equal(controller.getSnapshot().detail.id, 'saved-id');
  assert.deepEqual(destinations, []);
  const other = setup({ load: async () => ({ id: 'saved-id', status: 'approved' }) });
  await other.controller.load('saved-id');
  assert.equal(other.controller.getSnapshot().detail.status, 'approved');
});

test('literal new không được gửi tới API detail', options, async () => {
  const { controller, calls } = setup();
  await controller.load('new');
  assert.equal(calls.length, 0);
  assert.equal(controller.getSnapshot().phase, 'error');
});

test('đổi ID loại bỏ detail cũ ngay; phản hồi ID cũ về muộn không thay phiên mới', options, async () => {
  const pending = deferred();
  let signal;
  const { controller } = setup({ load: (id, config) => {
    if (id === 'old') { signal = config.signal; return pending.promise; }
    return Promise.resolve({ id, status: 'draft' });
  } });
  await controller.load('initial');
  const old = controller.load('old');
  assert.equal(controller.getSnapshot().detail, null);
  await controller.load('new-id');
  assert.equal(signal.aborted, true);
  pending.resolve({ id: 'old', status: 'draft' });
  await old;
  assert.equal(controller.getSnapshot().detail.id, 'new-id');
});

for (const kind of ['create', 'load']) {
  test(`${kind}: rời trang hủy signal, không áp kết quả hoặc điều hướng muộn`, options, async () => {
    const pending = deferred();
    let signal;
    const { controller, destinations } = setup({ [kind]: (...args) => {
      signal = args[1].signal;
      return pending.promise;
    } });
    const operation = kind === 'create' ? controller.submit(metadata) : controller.load('existing');
    const snapshot = controller.getSnapshot();
    controller.cancel();
    assert.equal(signal.aborted, true);
    pending.resolve({ id: 'late' });
    await operation;
    assert.equal(controller.getSnapshot(), snapshot);
    assert.deepEqual(destinations, []);
  });

  test(`${kind}: đổi tài khoản/logout khi pending không áp dữ liệu hoặc điều hướng`, options, async () => {
    const pending = deferred();
    let current = true;
    const { controller, destinations } = setup({ [kind]: () => pending.promise, isCurrent: () => current });
    const operation = kind === 'create' ? controller.submit(metadata) : controller.load('existing');
    const snapshot = controller.getSnapshot();
    current = false;
    pending.resolve({ id: 'foreign' });
    await operation;
    assert.equal(controller.getSnapshot(), snapshot);
    assert.deepEqual(destinations, []);
  });
}

test('GET lỗi hiện thông báo an toàn, retry đọc lại thành công và không tự lặp', options, async () => {
  for (const status of [401, 403, 404, 422, 429, 500, undefined]) {
    let calls = 0;
    const { controller } = setup({ load: async () => {
      calls += 1;
      if (calls === 1) throw { response: { status }, message: 'private backend detail' };
      return { id: 'saved', status: 'draft' };
    } });
    await controller.load('saved');
    assert.equal(controller.getSnapshot().phase, 'error');
    assert.ok(!controller.getSnapshot().error.includes('private'));
    assert.equal(calls, 1);
    await controller.load('saved');
    assert.equal(controller.getSnapshot().phase, 'ready');
  }
});

test('POST timeout/5xx/phản hồi không hợp lệ khóa gửi lại và yêu cầu kiểm Dashboard', options, async () => {
  for (const status of [undefined, 408, 500, 503]) {
    let calls = 0;
    const { controller, destinations } = setup({ create: async () => {
      calls += 1;
      throw { response: { status } };
    } });
    await controller.submit(metadata);
    assert.equal(controller.getSnapshot().createUncertain, true);
    assert.match(controller.getSnapshot().error, /Dashboard/);
    await controller.submit(metadata);
    assert.equal(calls, 1);
    assert.deepEqual(destinations, []);
  }
});

test('POST bị từ chối rõ ràng không tự retry, cho phép sửa và gửi lại chủ động', options, async () => {
  for (const status of [401, 403, 404, 422, 429]) {
    let calls = 0;
    const { controller, destinations } = setup({ create: async () => {
      calls += 1;
      if (calls === 1) throw { response: { status } };
      return { id: 'corrected' };
    } });
    await controller.submit(metadata);
    assert.equal(controller.getSnapshot().createUncertain, false);
    assert.equal(calls, 1);
    await controller.submit(metadata);
    assert.deepEqual(destinations, ['corrected']);
  }
});

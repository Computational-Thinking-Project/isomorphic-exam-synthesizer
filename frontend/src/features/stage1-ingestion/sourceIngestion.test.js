import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createSourceIngestionController } from './sourceIngestion.js';

const a = [{ id: 'qa', session_id: 'session-a', question_no: 1, raw_content: 'Nguồn A' }];
const b = [{ id: 'qb', session_id: 'session-a', question_no: 1, raw_content: 'Nguồn B' }];
const detail = (overrides = {}) => ({ id: 'session-a', status: 'draft', source_questions: a, ...overrides });
const httpError = (status) => ({ response: { status, data: { detail: 'private backend text' } } });
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
function fixture(overrides = {}) {
  const writes = [];
  const reads = [];
  const controller = createSourceIngestionController({
    initialDetail: detail(),
    validateText: (text) => text,
    validateFile: (file) => {
      if (!file) throw Object.assign(new Error('Chọn tệp'), { code: 'ERR_INGEST_INPUT' });
      return file;
    },
    ingestFile: async (...args) => { writes.push(args); return { session_id: 'session-a', questions: b }; },
    ingestText: async (...args) => { writes.push(args); return { session_id: 'session-a', questions: b }; },
    load: async (...args) => { reads.push(args); return detail({ source_questions: b }); },
    ...overrides,
  });
  return { controller, writes, reads };
}

test('khởi tạo/sửa input không gọi API hoặc xóa nguồn; success thay cùng snapshot nguồn', async () => {
  const { controller, writes, reads } = fixture();
  assert.equal(controller.getSnapshot().detail.source_questions, a);
  controller.setText('Nguồn B');
  assert.deepEqual([writes.length, reads.length], [0, 0]);
  assert.equal(controller.getSnapshot().detail.source_questions, a);
  await controller.submit();
  assert.equal(writes[0][0], 'session-a');
  assert.equal(writes[0][1], 'Nguồn B');
  assert(writes[0][2].signal instanceof AbortSignal);
  assert.equal(controller.getSnapshot().detail.source_questions, b);
  assert.equal(controller.getSnapshot().text, 'Nguồn B');
  assert.match(controller.getSnapshot().message, /1 câu/);
  assert.equal(a[0].raw_content, 'Nguồn A');
});

test('validation trước POST, giữ cause và cho sửa input', async () => {
  const cause = Object.assign(new Error('Thiếu nội dung'), { code: 'ERR_INGEST_INPUT' });
  const { controller, writes } = fixture({ validateText: () => { throw cause; } });
  await controller.submit();
  assert.equal(writes.length, 0);
  assert.equal(controller.getSnapshot().cause, cause);
  assert.equal(controller.getSnapshot().uncertain, false);
  controller.setText('Nội dung mới');
  assert.equal(controller.getSnapshot().error, '');
});

test('khóa đồng bộ hai POST, sửa input/GET khi đang gửi; không xóa A trong pending', async () => {
  const pending = deferred();
  let calls = 0;
  const { controller, reads } = fixture({ ingestText: () => { calls++; return pending.promise; } });
  controller.setText('B');
  const operation = controller.submit();
  await controller.submit();
  await controller.reload();
  controller.setText('C');
  assert.equal(calls, 1);
  assert.equal(reads.length, 0);
  assert.equal(controller.getSnapshot().text, 'B');
  assert.equal(controller.getSnapshot().detail.source_questions, a);
  pending.resolve({ session_id: 'session-a', questions: b });
  await operation;
  assert.equal(controller.getSnapshot().phase, 'idle');
});

for (const status of [400, 422, 429]) {
  test(`HTTP${status} giữ nguồn A/input/cause, chỉ gửi lại khi người dùng chủ động`, async () => {
    const cause = httpError(status);
    let calls = 0;
    const { controller } = fixture({ ingestText: async () => {
      calls++; if (calls === 1) throw cause;
      return { session_id: 'session-a', questions: b };
    } });
    controller.setText('B');
    await controller.submit();
    assert.equal(calls, 1);
    assert.equal(controller.getSnapshot().detail.source_questions, a);
    assert.equal(controller.getSnapshot().text, 'B');
    assert.equal(controller.getSnapshot().cause, cause);
    assert(!controller.getSnapshot().error.includes('private'));
    assert(controller.canSubmit());
    await controller.submit();
    assert.equal(controller.getSnapshot().detail.source_questions, b);
  });
}

test('409 khóa gửi tới khi GET xác nhận lại draft; non-draft chỉ đọc, không navigate', async () => {
  let read = detail();
  const { controller } = fixture({ ingestText: async () => { throw httpError(409); }, load: async () => read });
  await controller.submit();
  assert(!controller.canSubmit());
  await controller.reload();
  assert(controller.canSubmit());
  read = detail({ status: 'blueprinted', source_questions: b });
  await controller.reload();
  assert(!controller.canSubmit());
  assert.equal(controller.getSnapshot().detail.status, 'blueprinted');
});

for (const status of [401, 403, 404]) {
  test(`HTTP${status} khóa nhập/ẩn nguồn tới khi đọc lại hợp lệ`, async () => {
    const { controller } = fixture({ ingestText: async () => { throw httpError(status); } });
    await controller.submit();
    assert(controller.getSnapshot().unavailable);
    assert(!controller.canSubmit());
    await controller.reload();
    assert.equal(controller.getSnapshot().unavailable, false);
  });
}

for (const cause of [new Error('Lost response'), httpError(408), httpError(500), httpError(504),
  { code: 'ERR_INGEST_RESPONSE', outcomeUncertain: true }]) {
  test(`kết quả chưa rõ (${cause.response?.status ?? cause.code ?? 'network'}): GET không chứng minh POST đã dừng`, async () => {
    let writes = 0;
    const { controller } = fixture({ ingestText: async () => { writes++; throw cause; } });
    await controller.submit();
    await controller.reload();
    assert.equal(controller.getSnapshot().detail.source_questions, b);
    assert(controller.getSnapshot().uncertain);
    assert(!controller.canSubmit());
    await controller.submit();
    assert.equal(writes, 1);
  });
}

test('GET sai phiên/lỗi không ghi đè A hoặc mở khóa gửi; retry chủ động lấy B', async () => {
  let next = { ...detail(), id: 'foreign' };
  const { controller } = fixture({ load: async () => next });
  await controller.reload();
  assert.equal(controller.getSnapshot().detail.source_questions, a);
  assert(!controller.canSubmit());
  next = detail({ source_questions: b });
  await controller.reload();
  assert.equal(controller.getSnapshot().detail.source_questions, b);
  assert(controller.canSubmit());
});

test('response POST sai phiên cũng là uncertain, không đưa nguồn khác vào preview', async () => {
  const { controller } = fixture({ ingestText: async () => ({ session_id: 'foreign', questions: b }) });
  await controller.submit();
  assert.equal(controller.getSnapshot().detail.source_questions, a);
  assert(controller.getSnapshot().uncertain);
});

test('hủy POST giữ A và khóa gửi lại, phản hồi muộn không đổi state', async () => {
  const pending = deferred();
  let signal;
  const { controller } = fixture({ ingestText: (id, text, config) => { signal = config.signal; return pending.promise; } });
  const operation = controller.submit();
  controller.cancelRequest();
  assert(signal.aborted);
  const canceled = controller.getSnapshot();
  pending.resolve({ session_id: 'session-a', questions: b });
  await operation;
  assert.equal(controller.getSnapshot(), canceled);
  assert(controller.getSnapshot().uncertain);
});

test('GET cũ bị hủy không ghi đè POST mới, GET pending cũng chặn gửi', async () => {
  const pending = deferred();
  const { controller, writes } = fixture({ load: () => pending.promise });
  const reading = controller.reload();
  await controller.submit();
  assert.equal(writes.length, 0);
  controller.cancelRequest();
  await controller.submit();
  pending.resolve(detail());
  await reading;
  assert.equal(controller.getSnapshot().detail.source_questions, b);
});

for (const kind of ['load', 'ingestText']) {
  test(`${kind}: dispose/account đổi bỏ kết quả cũ và chặn tác vụ tiếp`, async () => {
    for (const dispose of [false, true]) {
      const pending = deferred();
      let current = true;
      const { controller } = fixture({ [kind]: () => pending.promise, isCurrent: () => current });
      const operation = kind === 'load' ? controller.reload() : controller.submit();
      const snapshot = controller.getSnapshot();
      if (dispose) controller.dispose();
      else current = false;
      pending.resolve(kind === 'load' ? detail({ source_questions: b }) : { session_id: 'session-a', questions: b });
      await operation;
      assert.equal(controller.getSnapshot(), snapshot);
      if (!current) assert(!controller.canSubmit());
    }
  });
}

test('nguồn non-draft ban đầu không gửi POST', async () => {
  const { controller, writes } = fixture({ initialDetail: detail({ status: 'approved' }) });
  await controller.submit();
  assert.equal(writes.length, 0);
});

const file = new File(['Câu 1: Giải 3x-5=10.'], 'đại số.md');

test('file: chọn/đổi cách nhập không POST, giữ text và nguồn; chỉ submit mới gửi file', async () => {
  const { controller, writes } = fixture();
  controller.setText('Văn bản chưa gửi');
  controller.setMode('file');
  controller.selectFiles([file]);
  controller.setMode('text');
  controller.setMode('file');
  assert.equal(controller.getSnapshot().text, 'Văn bản chưa gửi');
  assert.equal(controller.getSnapshot().detail.source_questions, a);
  assert.equal(writes.length, 0);
  await controller.submit();
  assert.equal(writes[0][1], file);
  assert.equal(typeof writes[0][2].onUploadProgress, 'function');
  assert.equal(controller.getSnapshot().detail.source_questions, b);
  assert.equal(controller.getSnapshot().upload, null);
});

test('file: thiếu/chọn nhiều file chặn gửi, bỏ file cũ; chọn lại cùng file và bỏ chọn được', async () => {
  const { controller, writes } = fixture();
  controller.setMode('file');
  await controller.submit();
  assert.equal(controller.getSnapshot().cause.code, 'ERR_INGEST_INPUT');
  controller.selectFiles([file]);
  controller.selectFiles([file, file]);
  assert.equal(controller.getSnapshot().file, null);
  assert.match(controller.getSnapshot().error, /đúng một/);
  await controller.submit();
  assert.equal(writes.length, 0);
  controller.selectFiles([file]);
  controller.clearFile();
  controller.selectFiles([file]);
  assert.equal(controller.getSnapshot().error, '');
  assert.equal(controller.getSnapshot().file, file);
});

test('file: tiến độ không total/total0 là chưa xác định;100% vẫn pending, không thay nguồn hoặc cho gửi tiếp', async () => {
  const pending = deferred();
  let config;
  const { controller } = fixture({ ingestFile: (id, input, options) => { config = options; return pending.promise; } });
  controller.setMode('file');
  controller.selectFiles([file]);
  const operation = controller.submit();
  for (const total of [undefined, 0, NaN, Infinity]) {
    config.onUploadProgress({ loaded: 5, total });
    assert.equal(controller.getSnapshot().upload.total, null);
    assert.equal(controller.getSnapshot().upload.complete, false);
  }
  config.onUploadProgress({ loaded: 5, total: 10 });
  assert.deepEqual(controller.getSnapshot().upload, { loaded: 5, total: 10, complete: false });
  controller.selectFiles([new File(['x'], 'khác.md')]);
  controller.setMode('text');
  controller.clearFile();
  assert.equal(controller.getSnapshot().file, file);
  assert.equal(controller.getSnapshot().mode, 'file');
  config.onUploadProgress({ loaded: 10, total: 10 });
  const complete = controller.getSnapshot();
  assert.equal(complete.phase, 'submitting');
  assert.equal(complete.detail.source_questions, a);
  assert(!controller.canSubmit());
  config.onUploadProgress({ loaded: 2 });
  assert.equal(controller.getSnapshot(), complete);
  pending.resolve({ session_id: 'session-a', questions: b });
  await operation;
  const saved = controller.getSnapshot();
  config.onUploadProgress({ loaded: 3, total: 10 });
  assert.equal(controller.getSnapshot(), saved);
});

test('file:422 giữ file/text/nguồn A và raw cause, sửa file rồi chủ động nạp lại', async () => {
  const cause = httpError(422);
  let attempts = 0;
  const { controller } = fixture({ ingestFile: async () => {
    if (++attempts === 1) throw cause;
    return { session_id: 'session-a', questions: b };
  } });
  controller.setText('text riêng');
  controller.setMode('file');
  controller.selectFiles([file]);
  await controller.submit();
  assert.equal(controller.getSnapshot().file, file);
  assert.equal(controller.getSnapshot().text, 'text riêng');
  assert.equal(controller.getSnapshot().cause, cause);
  assert.equal(controller.getSnapshot().detail.source_questions, a);
  controller.selectFiles([file]);
  await controller.submit();
  assert.equal(attempts, 2);
  assert.equal(controller.getSnapshot().detail.source_questions, b);
});

test('file: cancel sau upload khóa uncertain; chọn file/đổi cách nhập/GET không xóa cảnh báo hay mở khóa', async () => {
  const pending = deferred();
  let config;
  const { controller } = fixture({ ingestFile: (id, input, options) => { config = options; return pending.promise; } });
  controller.setMode('file');
  controller.selectFiles([file]);
  const operation = controller.submit();
  config.onUploadProgress({ loaded: 10, total: 10 });
  controller.cancelRequest();
  assert(config.signal.aborted);
  controller.selectFiles([file]);
  controller.selectFiles([]);
  controller.setMode('text');
  await controller.reload();
  const snapshot = controller.getSnapshot();
  assert(snapshot.uncertain);
  assert.match(snapshot.error, /Chưa xác nhận/);
  assert(!controller.canSubmit());
  config.onUploadProgress({ loaded: 4, total: 10 });
  pending.resolve({ session_id: 'session-a', questions: a });
  await operation;
  assert.equal(controller.getSnapshot(), snapshot);
});

for (const boundary of ['dispose', 'account']) {
  test(`file: ${boundary} bỏ cả progress và response muộn`, async () => {
    const pending = deferred();
    let config;
    let current = true;
    const { controller } = fixture({ isCurrent: () => current,
      ingestFile: (id, input, options) => { config = options; return pending.promise; } });
    controller.setMode('file');
    controller.selectFiles([file]);
    const operation = controller.submit();
    const snapshot = controller.getSnapshot();
    if (boundary === 'dispose') controller.dispose();
    else current = false;
    config.onUploadProgress({ loaded: 10, total: 10 });
    pending.resolve({ session_id: 'session-a', questions: b });
    await operation;
    assert.equal(controller.getSnapshot(), snapshot);
  });
}

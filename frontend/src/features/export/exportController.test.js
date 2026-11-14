import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createExportController } from './exportController.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function setup(overrides = {}) {
  const calls = {
    load: [],
    status: [],
    export: [],
    downloadUrl: [],
    open: [],
  };
  let nowMs = 1_000_000;
  let timerSeq = 1;
  const timers = new Map();

  const controller = createExportController({
    loadSession: async (id, opts) => {
      calls.load.push({ id, signal: opts?.signal });
      return { id, status: 'approved', title: 'Đề kiểm tra', subject: 'Toán', grade: 12 };
    },
    getStatus: async (id, opts) => {
      calls.status.push({ id, signal: opts?.signal });
      return { status: 'idle' };
    },
    triggerExport: async (id, opts) => {
      calls.export.push({ id, signal: opts?.signal });
      return { status: 'ready', filename: `exam_bundle_${id}.zip` };
    },
    issueDownloadUrl: async (id, opts) => {
      calls.downloadUrl.push({ id, signal: opts?.signal });
      return {
        url: `https://storage.example.test/${id}.zip?sig=1`,
        expires_at: new Date(nowMs + 3600_000).toISOString(),
        filename: `exam_bundle_${id}.zip`,
      };
    },
    openDownload: (url, filename) => calls.open.push({ url, filename }),
    now: () => nowMs,
    scheduleTimer: (fn, ms) => {
      const id = timerSeq++;
      timers.set(id, { fn, ms });
      return id;
    },
    clearTimer: (id) => timers.delete(id),
    ...overrides,
  });

  return {
    controller,
    calls,
    advanceTime: (ms) => { nowMs += ms; },
    runNextTimer: async () => {
      const next = timers.entries().next();
      if (next.done) return false;
      const [id, entry] = next.value;
      timers.delete(id);
      await entry.fn();
      return true;
    },
    timerCount: () => timers.size,
  };
}

test('load chặn phiên chưa approved/exported và không gọi status hoặc triggerExport', async () => {
  for (const status of ['draft', 'blueprinted', 'configured', 'generating', 'generated', 'reviewed', 'failed']) {
    const { controller, calls } = setup({
      loadSession: async (id) => ({ id, status, title: 'Đề nháp' }),
    });
    await controller.load('s1');
    assert.equal(controller.getSnapshot().phase, 'blocked');
    assert.equal(calls.status.length, 0);
    assert.equal(calls.export.length, 0);
  }
});

test('load vào unwired khi chưa nối Q10 adapters và không đoán API', async () => {
  const { controller } = setup({
    getStatus: undefined,
    triggerExport: undefined,
    issueDownloadUrl: undefined,
  });
  await controller.load('s1');
  assert.equal(controller.getSnapshot().phase, 'unwired');
  assert.equal(controller.getSnapshot().detail?.id, 's1');
});

test('F5/load với session approved/exported chỉ gọi getStatus, không tự triggerExport', async () => {
  const { controller, calls } = setup({
    loadSession: async (id) => ({ id, status: 'exported', title: 'Đề đã xuất' }),
    getStatus: async (id) => {
      calls.status.push(id);
      return { status: 'ready', filename: `exam_bundle_${id}.zip` };
    },
  });
  await controller.load('s1');
  assert.equal(controller.getSnapshot().phase, 'ready_to_download');
  assert.equal(calls.status.length, 1);
  assert.equal(calls.export.length, 0);
});

test('chống double-click startExport và download khi request đang pending', async () => {
  const pendingExport = deferred();
  const pendingDownload = deferred();
  const { controller, calls } = setup({
    triggerExport: async (id) => {
      calls.export.push(id);
      return pendingExport.promise;
    },
    issueDownloadUrl: async (id) => {
      calls.downloadUrl.push(id);
      return pendingDownload.promise;
    },
  });

  await controller.load('s1');
  const firstExport = controller.startExport();
  const secondExport = controller.startExport();
  assert.equal(calls.export.length, 1);

  pendingExport.resolve({ status: 'ready', filename: 'exam_bundle_s1.zip' });
  await Promise.all([firstExport, secondExport]);
  assert.equal(controller.getSnapshot().phase, 'ready_to_download');

  const firstDl = controller.download();
  const secondDl = controller.download();
  assert.equal(calls.downloadUrl.length, 1);

  pendingDownload.resolve({ url: 'https://storage.example.test/s1.zip', expires_in: 3600 });
  await Promise.all([firstDl, secondDl]);
  assert.equal(calls.open.length, 1);
});

test('bounded polling dừng sau maxPollDurationMs và chuyển sang poll_timeout', async () => {
  let statusChecks = 0;
  const { controller, advanceTime, runNextTimer, timerCount } = setup({
    getStatus: async () => {
      statusChecks += 1;
      return { status: 'preparing' };
    },
    pollIntervalMs: 2000,
    maxPollDurationMs: 4000,
  });

  await controller.load('s1');
  assert.equal(controller.getSnapshot().phase, 'preparing');
  assert.equal(timerCount(), 1);

  advanceTime(2000);
  await runNextTimer();
  assert.equal(controller.getSnapshot().phase, 'preparing');
  assert.equal(timerCount(), 1);

  advanceTime(2000);
  await runNextTimer();
  assert.equal(controller.getSnapshot().phase, 'poll_timeout');
  assert.equal(timerCount(), 0);
  assert.equal(statusChecks, 3);
});

test('signed URL hết hạn tự gọi issueDownloadUrl cấp lại URL mới', async () => {
  let issueCount = 0;
  const { controller, calls, advanceTime } = setup({
    getStatus: async () => ({ status: 'ready', filename: 'exam_bundle_s1.zip' }),
    issueDownloadUrl: async () => {
      issueCount += 1;
      return {
        url: `https://storage.example.test/s1.zip?v=${issueCount}`,
        expires_in: 60,
        filename: 'exam_bundle_s1.zip',
      };
    },
  });

  await controller.load('s1');
  await controller.download();
  assert.equal(calls.open.length, 1);
  assert.equal(issueCount, 1);

  // Còn hạn -> dùng lại URL trong phiên hiện tại
  advanceTime(10_000);
  await controller.download();
  assert.equal(issueCount, 1);
  assert.equal(calls.open.length, 2);

  // Hết hạn -> xin cấp URL mới
  advanceTime(60_000);
  await controller.download();
  assert.equal(issueCount, 2);
  assert.equal(calls.open[2].url, 'https://storage.example.test/s1.zip?v=2');
});

test('cancel hoặc đổi account hủy timer, abort request và bỏ kết quả về muộn', async () => {
  let current = true;
  const pending = deferred();
  const { controller, timerCount } = setup({
    isCurrent: () => current,
    loadSession: () => pending.promise,
  });

  const loadPromise = controller.load('s1');
  current = false;
  controller.cancel();
  pending.resolve({ id: 's1', status: 'approved' });
  await loadPromise;

  assert.equal(controller.getSnapshot().phase, 'idle');
  assert.equal(controller.getSnapshot().detail, null);
  assert.equal(timerCount(), 0);
});

test('mapping lỗi 401/403/404/409/422/423/503 an toàn không lộ raw message', async () => {
  for (const status of [401, 403, 404, 409, 422, 423, 503]) {
    const { controller } = setup({
      getStatus: async () => ({ status: 'idle' }),
      triggerExport: async () => {
        throw { response: { status }, message: 'SECRET_INTERNAL_TRACE' };
      },
    });
    await controller.load('s1');
    await controller.startExport();
    const snap = controller.getSnapshot();
    assert.ok(snap.error);
    assert.doesNotMatch(snap.error, /SECRET_INTERNAL_TRACE/);
    if (status === 503) {
      assert.equal(snap.phase, 'error');
    } else {
      assert.equal(snap.phase, 'failed');
    }
  }
});

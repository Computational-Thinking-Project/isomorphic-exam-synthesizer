import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  createExportController,
  DEFAULT_EXPORT_CONFIG,
  formatExportError,
  makeStorageKey,
} from './exportController.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function createMockStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
  };
}

function setup(overrides = {}) {
  const calls = {
    load: [],
    status: [],
    export: [],
    downloadUrl: [],
    answerKey: [],
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
      calls.status.push({ id, signal: opts?.signal, packagingKey: opts?.packagingKey });
      return { status: 'idle' };
    },
    triggerExport: async (id, configOrOpts, maybeOpts) => {
      const opts = maybeOpts?.signal ? maybeOpts : (configOrOpts?.signal ? configOrOpts : {});
      calls.export.push({ id, signal: opts.signal, config: configOrOpts?.config || configOrOpts });
      return { status: 'ready', filename: `exam_bundle_${id}.zip` };
    },
    issueDownloadUrl: async (id, opts) => {
      calls.downloadUrl.push({ id, signal: opts?.signal, packagingKey: opts?.packagingKey });
      return {
        url: `https://storage.example.test/${id}.zip?sig=1`,
        expires_at: new Date(nowMs + 3600_000).toISOString(),
        filename: `exam_bundle_${id}.zip`,
      };
    },
    fetchAnswerKey: async (id, opts) => {
      calls.answerKey.push({ id, ...opts });
      return 'question_no,answer\n1,A\n2,B';
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

test('ready refresh discards a still-valid URL for the previous packager artifact', async () => {
  let version = 1;
  let issues = 0;
  const { controller, calls } = setup({
    getStatus: async () => ({
      status: 'ready', filename: 'exam_bundle_s1.zip', sha256: String(version).repeat(64),
    }),
    issueDownloadUrl: async () => {
      issues += 1;
      return {
        url: `https://storage.example.test/s1/v${version}.zip`,
        expires_in: 3600,
        filename: 'exam_bundle_s1.zip',
      };
    },
  });
  await controller.load('s1');
  await controller.download();
  await controller.download();
  assert.equal(issues, 1);
  version = 2; // Another tab/device completes the v2 export.
  await controller.refreshStatus();
  assert.equal(controller.getSnapshot().downloadGrant, null);
  await controller.download();
  assert.equal(issues, 2);
  assert.equal(calls.open.at(-1).url, 'https://storage.example.test/s1/v2.zip');
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

test('mapping lỗi 401/403/404/409/422/423/503/504 an toàn không lộ raw message', async () => {
  for (const status of [401, 403, 404, 409, 422, 423, 503, 504]) {
    const { controller } = setup({
      getStatus: async () => ({ state: 'idle' }),
      triggerExport: async () => {
        throw { response: { status }, message: 'SECRET_INTERNAL_TRACE' };
      },
    });
    await controller.load('s1');
    await controller.startExport();
    const snap = controller.getSnapshot();
    assert.ok(snap.error);
    assert.doesNotMatch(snap.error, /SECRET_INTERNAL_TRACE/);
    if (status === 503 || status === 504) {
      assert.equal(snap.phase, 'error');
    } else {
      assert.equal(snap.phase, 'failed');
    }
  }
});

test('đọc đúng payload Q10 với state, sha256 và size_bytes', async () => {
  const { controller } = setup({
    getStatus: async () => ({
      state: 'ready',
      filename: 'exam_bundle_s1.zip',
      sha256: 'deadbeef1234',
      size_bytes: 4096,
    }),
  });
  await controller.load('s1');
  const snap = controller.getSnapshot();
  assert.equal(snap.phase, 'ready_to_download');
  assert.deepEqual(snap.artifact, {
    filename: 'exam_bundle_s1.zip',
    size_bytes: 4096,
    sha256: 'deadbeef1234',
    size: 4096,
    hash: 'deadbeef1234',
  });
});

test('chặn startExport khi đang ở phase error cho tới khi refreshStatus reconcile xong', async () => {
  let statusCheckCount = 0;
  let exportCount = 0;
  const { controller } = setup({
    getStatus: async () => {
      statusCheckCount += 1;
      if (statusCheckCount === 1) return { state: 'idle' };
      return {
        state: 'ready',
        filename: 'exam_bundle_s1.zip',
        sha256: 'abc',
        size_bytes: 100,
      };
    },
    triggerExport: async () => {
      exportCount += 1;
      throw { response: { status: 504 }, message: 'Gateway timeout' };
    },
  });

  await controller.load('s1');
  await controller.startExport();
  assert.equal(controller.getSnapshot().phase, 'error');
  assert.equal(exportCount, 1);

  // Chưa reconcile -> chặn POST /export lặp lại
  await controller.startExport();
  assert.equal(exportCount, 1);

  // Reconcile qua GET /export -> cập nhật sang ready_to_download
  await controller.refreshStatus();
  assert.equal(controller.getSnapshot().phase, 'ready_to_download');
  assert.equal(statusCheckCount, 2);
});

test('cấu hình xuất bản: setConfig cập nhật selectedConfig và resetConfig khôi phục mặc định', async () => {
  const storage = createMockStorage();
  const { controller } = setup({ storage });
  await controller.load('s1', { accountKey: 'teacher_1' });

  assert.deepEqual(controller.getSnapshot().selectedConfig, DEFAULT_EXPORT_CONFIG);

  controller.setConfig({
    visible_fields: ['title', 'institution', 'duration_minutes'],
    answer_sheet: 'written_boxes',
    formats: ['pdf', 'tex'],
  });

  const custom = controller.getSnapshot().selectedConfig;
  assert.deepEqual(custom.visible_fields, ['title', 'institution', 'duration_minutes']);
  assert.equal(custom.answer_sheet, 'written_boxes');
  assert.deepEqual(custom.formats, ['pdf', 'tex']);

  // Kiểm tra lưu vào storage
  const rawSaved = storage.getItem(makeStorageKey('teacher_1', 's1'));
  assert.ok(rawSaved);
  const parsed = JSON.parse(rawSaved);
  assert.equal(parsed.selectedConfig.answer_sheet, 'written_boxes');

  // Khôi phục mặc định
  controller.resetConfig();
  assert.deepEqual(controller.getSnapshot().selectedConfig, DEFAULT_EXPORT_CONFIG);
});

test('startExport gửi cấu hình tùy chọn và lưu packagingKey, identityKind, effectiveConfig', async () => {
  const storage = createMockStorage();
  const { controller, calls } = setup({
    storage,
    triggerExport: async (id, config) => {
      calls.export.push({ id, config });
      return {
        state: 'ready',
        filename: 'exam_configured_101.zip',
        packaging_key: 'pkg_conf_123',
        identity_kind: 'configured',
        effective_config: config,
      };
    },
  });

  await controller.load('s1', { accountKey: 'teacher_1' });
  controller.setConfig({ answer_sheet: 'written_boxes' });
  await controller.startExport();

  const snap = controller.getSnapshot();
  assert.equal(snap.phase, 'ready_to_download');
  assert.equal(snap.packagingKey, 'pkg_conf_123');
  assert.equal(snap.identityKind, 'configured');
  assert.equal(snap.effectiveConfig?.answer_sheet, 'written_boxes');
  assert.equal(calls.export[0].config?.answer_sheet, 'written_boxes');

  // Verify persistence in storage
  const saved = JSON.parse(storage.getItem(makeStorageKey('teacher_1', 's1')));
  assert.equal(saved.packagingKey, 'pkg_conf_123');
  assert.equal(saved.identityKind, 'configured');
});

test('load khôi phục trạng thái từ storage và truyền packagingKey vào getStatus', async () => {
  const storage = createMockStorage({
    [makeStorageKey('teacher_1', 's1')]: JSON.stringify({
      sessionId: 's1',
      packagingKey: 'pkg_saved_999',
      identityKind: 'ext_default',
      effectiveConfig: { answer_sheet: 'none' },
      selectedConfig: { answer_sheet: 'none' },
    }),
  });

  const { controller, calls } = setup({
    storage,
    getStatus: async (id, opts) => {
      calls.status.push({ id, packagingKey: opts?.packagingKey });
      return {
        state: 'ready',
        filename: 'exam_bundle_s1.zip',
        packaging_key: opts?.packagingKey,
        identity_kind: 'ext_default',
      };
    },
  });

  await controller.load('s1', { accountKey: 'teacher_1' });
  assert.equal(calls.status[0].packagingKey, 'pkg_saved_999');
  assert.equal(controller.getSnapshot().phase, 'ready_to_download');
  assert.equal(controller.getSnapshot().packagingKey, 'pkg_saved_999');
  assert.equal(controller.getSnapshot().identityKind, 'ext_default');
});

test('fail-closed khi gói cũ trả về 404: xóa storage và quay về ready_to_export, không tự POST lại', async () => {
  const storage = createMockStorage({
    [makeStorageKey('teacher_1', 's1')]: JSON.stringify({
      sessionId: 's1',
      packagingKey: 'pkg_expired_404',
      identityKind: 'configured',
    }),
  });

  const { controller, calls } = setup({
    storage,
    getStatus: async (id, opts) => {
      calls.status.push({ id, packagingKey: opts?.packagingKey });
      throw { response: { status: 404 }, message: 'Package expired' };
    },
  });

  await controller.load('s1', { accountKey: 'teacher_1' });
  const snap = controller.getSnapshot();

  // Fail-closed an toàn: không tự POST export mới, quay về ready_to_export
  assert.equal(snap.phase, 'ready_to_export');
  assert.equal(snap.packagingKey, null);
  assert.equal(calls.export.length, 0);

  // Storage đã dọn dẹp key cũ
  assert.equal(storage.getItem(makeStorageKey('teacher_1', 's1')), null);
});

test('download truyền packagingKey vào issueDownloadUrl', async () => {
  const { controller, calls } = setup({
    getStatus: async () => ({
      state: 'ready',
      filename: 'exam_custom.zip',
      packaging_key: 'pkg_custom_abc',
      identity_kind: 'configured',
    }),
    issueDownloadUrl: async (id, opts) => {
      calls.downloadUrl.push({ id, packagingKey: opts?.packagingKey });
      return {
        url: 'https://storage.example.test/custom.zip',
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
        filename: 'exam_custom.zip',
      };
    },
  });

  await controller.load('s1');
  await controller.download();

  assert.equal(calls.downloadUrl[0].packagingKey, 'pkg_custom_abc');
  assert.equal(calls.open[0].url, 'https://storage.example.test/custom.zip');
});

test('downloadAnswerKey gọi fetchAnswerKey và kích hoạt tải file CSV / JSON', async () => {
  const { controller, calls } = setup({
    fetchAnswerKey: async (id, opts) => {
      calls.answerKey.push({ id, ...opts });
      if (opts.format === 'json') {
        return { session_id: id, answers: { 1: 'A', 2: 'B' } };
      }
      return 'question,key\n1,A\n2,B';
    },
  });

  await controller.load('s1');

  // Tải CSV
  await controller.downloadAnswerKey({ target: 'version', versionId: 'v101', format: 'csv' });
  assert.equal(calls.answerKey[0].target, 'version');
  assert.equal(calls.answerKey[0].versionId, 'v101');
  assert.equal(calls.answerKey[0].format, 'csv');
  assert.match(calls.open[0].url, /^data:text\/csv/);
  assert.equal(calls.open[0].filename, 'answer_key_s1_v_v101.csv');

  // Tải JSON
  await controller.downloadAnswerKey({ target: 'session', format: 'json' });
  assert.equal(calls.answerKey[1].format, 'json');
  assert.match(calls.open[1].url, /^data:application\/json/);
  assert.equal(calls.open[1].filename, 'answer_key_s1_session.json');
});

test('mapping đầy đủ các mã lỗi nghiệp vụ EXT-03', () => {
  const errQuestionLimit = formatExportError({
    response: { status: 422, data: { error_code: 'ERR_EXPORT_QUESTION_LIMIT' } },
  });
  assert.equal(errQuestionLimit, 'Số lượng câu hỏi vượt quá giới hạn cho phép của mẫu xuất đề.');

  const errConfigInvalid = formatExportError({
    response: { status: 422, data: { error_code: 'ERR_EXPORT_CONFIG_INVALID' } },
  });
  assert.equal(errConfigInvalid, 'Cấu hình xuất bản không hợp lệ. Vui lòng kiểm tra lại các trường đã chọn.');

  const errOmr = formatExportError({
    response: { status: 422, data: { error_code: 'ERR_EXPORT_OMR_UNAVAILABLE' } },
  });
  assert.equal(errOmr, 'Mẫu phiếu trả lời trắc nghiệm (OMR) hiện đang được kiểm định và tạm thời chưa khả dụng.');

  const errPkgNotFound = formatExportError(
    { response: { status: 404, data: { error_code: 'ERR_EXPORT_PACKAGE_NOT_FOUND' } } },
    'status'
  );
  assert.equal(errPkgNotFound, 'Không tìm thấy gói xuất đề đã lưu hoặc gói đã hết hạn. Vui lòng bấm xuất bản lại.');

  const errNotReady = formatExportError(
    { response: { status: 409, data: { error_code: 'ERR_EXPORT_NOT_READY' } } },
    'download'
  );
  assert.equal(errNotReady, 'Gói đề thi chưa sẵn sàng để tải. Vui lòng kiểm tra lại trạng thái đóng gói.');
});

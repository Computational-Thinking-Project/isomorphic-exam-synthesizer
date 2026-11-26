import assert from 'node:assert/strict';
import { register } from 'node:module';
import { beforeEach, test } from 'node:test';
import axios from 'axios';
import { useAuthStore } from '../features/auth/authStore.js';
import { auth } from './test-support/supabase.stub.js';

register('./test-support/auth-loader.js', import.meta.url);
const {
  EXPORT_POST_TIMEOUT_MS,
  getExportStatus,
  triggerExport,
  issueDownloadUrl,
} = await import('./exportService.js');
const { api } = await import('./api.js');

const readyPayload = {
  state: 'ready',
  filename: 'exam_bundle_s1.zip',
  sha256: 'abc123def456',
  size_bytes: 20480,
};

function response(config, data, status = 200) {
  return { status, data, headers: {}, config };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  useAuthStore.getState().setChecking();
  useAuthStore.getState().setSession({
    user: { id: 'account-a' },
    access_token: 'test-export-token-a',
  });
  const version = useAuthStore.getState().sessionVersion;
  useAuthStore.getState().setProfile(
    { id: 'account-a', email: 'teacher@example.test' },
    version,
  );
  auth.getSession = async () => ({
    data: { session: useAuthStore.getState().session },
    error: null,
  });
  auth.refreshSession = async () => {
    throw new Error('Unexpected refreshSession');
  };
  api.defaults.adapter = async () => {
    throw new Error('Mock HTTP adapter required');
  };
});

test('từ chối sessionId rỗng hoặc new trước khi gọi Auth/HTTP', async () => {
  let authCalls = 0;
  auth.getSession = async () => {
    authCalls += 1;
    return { data: { session: useAuthStore.getState().session }, error: null };
  };

  for (const invalidId of ['', '   ', 'new', null, undefined]) {
    await assert.rejects(getExportStatus(invalidId), /ID phiên không hợp lệ/);
    await assert.rejects(triggerExport(invalidId), /ID phiên không hợp lệ/);
    await assert.rejects(issueDownloadUrl(invalidId), /ID phiên không hợp lệ/);
  }
  assert.equal(authCalls, 0);
});

test('getExportStatus mã hóa sessionId và đọc đúng state/metadata Q10', async () => {
  const seen = [];
  api.defaults.adapter = async (config) => {
    seen.push({ method: config.method, url: config.url, headers: config.headers });
    return response(config, readyPayload);
  };

  const result = await getExportStatus('a/b');
  assert.equal(seen[0].method, 'get');
  assert.equal(seen[0].url, '/sessions/a%2Fb/export');
  assert.equal(seen[0].headers.get('Cache-Control'), 'no-store');
  assert.deepEqual(result, {
    state: 'ready',
    status: 'ready',
    filename: 'exam_bundle_s1.zip',
    sha256: 'abc123def456',
    size_bytes: 20480,
    error_code: null,
  });
});

test('getExportStatus hỗ trợ các trạng thái idle, preparing, failed', async () => {
  const states = [
    { state: 'idle' },
    { state: 'preparing' },
    { state: 'failed', error_code: 'ERR_EXPORT_BUILD_FAILED' },
  ];
  for (const payload of states) {
    api.defaults.adapter = async (config) => response(config, payload);
    const res = await getExportStatus('s1');
    assert.equal(res.state, payload.state);
    assert.equal(res.status, payload.state);
    assert.equal(res.error_code, payload.error_code ?? null);
  }
});

test('getExportStatus bác bỏ response thiếu trường hoặc metadata ready sai', async () => {
  for (const invalid of [
    null,
    {},
    { state: 'pending' },
    { state: 'ready', filename: '', sha256: 'abc', size_bytes: 10 },
    { state: 'ready', filename: 'a.zip', sha256: '', size_bytes: 10 },
    { state: 'ready', filename: 'a.zip', sha256: 'abc', size_bytes: -1 },
  ]) {
    api.defaults.adapter = async (config) => response(config, invalid);
    await assert.rejects(getExportStatus('s1'));
  }
});

test('triggerExport gửi empty body (undefined), dùng timeout 120s và nhận cả 200 ready / 202 preparing', async () => {
  let lastConfig;
  api.defaults.adapter = async (config) => {
    lastConfig = config;
    return response(config, readyPayload, 200);
  };
  const readyRes = await triggerExport('s1');
  assert.equal(lastConfig.method, 'post');
  assert.equal(lastConfig.url, '/sessions/s1/export');
  assert.equal(lastConfig.data, undefined);
  assert.equal(lastConfig.timeout, EXPORT_POST_TIMEOUT_MS);
  assert.equal(lastConfig.headers.get('Cache-Control'), 'no-store');
  assert.equal(readyRes.state, 'ready');
  assert.equal(readyRes.sha256, 'abc123def456');
  assert.equal(readyRes.size_bytes, 20480);

  api.defaults.adapter = async (config) => response(config, { state: 'preparing' }, 202);
  const preparingRes = await triggerExport('s1');
  assert.equal(preparingRes.state, 'preparing');
  assert.equal(preparingRes.status, 'preparing');
});

test('issueDownloadUrl gửi empty body, xác thực URL HTTPS + expires_at + expires_in', async () => {
  const expiresAt = new Date(Date.now() + 3600_000).toISOString();
  let lastConfig;
  api.defaults.adapter = async (config) => {
    lastConfig = config;
    return response(config, {
      url: 'https://storage.example.test/exam_bundle_s1.zip?token=xyz',
      expires_at: expiresAt,
      expires_in: 3600,
      filename: 'exam_bundle_s1.zip',
    });
  };

  const grant = await issueDownloadUrl('s1');
  assert.equal(lastConfig.method, 'post');
  assert.equal(lastConfig.url, '/sessions/s1/export/download-url');
  assert.equal(lastConfig.data, undefined);
  assert.equal(grant.expires_in, 3600);
  assert.equal(grant.filename, 'exam_bundle_s1.zip');

  api.defaults.adapter = async (config) => response(config, {
    url: 'http://insecure.example.test/file.zip',
    expires_at: expiresAt,
    expires_in: 3600,
    filename: 'exam_bundle_s1.zip',
  });
  await assert.rejects(issueDownloadUrl('s1'), /liên kết tải xuống không hợp lệ/);
});

test('AbortSignal và đổi account hủy request Export đang chờ', async () => {
  const ac = new AbortController();
  ac.abort();
  let adapterCalls = 0;
  api.defaults.adapter = async (config) => {
    adapterCalls += 1;
    return response(config, { state: 'idle' });
  };
  await assert.rejects(getExportStatus('s1', { signal: ac.signal }), axios.isCancel);
  assert.equal(adapterCalls, 0);

  const entered = deferred();
  const release = deferred();
  api.defaults.adapter = async (config) => {
    adapterCalls += 1;
    entered.resolve();
    await release.promise;
    return response(config, readyPayload);
  };
  const pending = triggerExport('s1');
  await entered.promise;
  useAuthStore.getState().setSession({ user: { id: 'account-b' }, access_token: 'token-b' });
  release.resolve();
  await assert.rejects(pending, axios.isCancel);
  assert.equal(adapterCalls, 1);
});

test('401 trên exportService dùng refresh/retry chung tối đa một lần', async () => {
  let calls = 0;
  let refreshCalls = 0;
  auth.refreshSession = async () => {
    refreshCalls += 1;
    const session = { user: { id: 'account-a' }, access_token: 'refreshed-token' };
    useAuthStore.getState().setSession(session);
    return { data: { session }, error: null };
  };
  api.defaults.adapter = async (config) => {
    calls += 1;
    if (calls === 1) {
      throw new axios.AxiosError('Unauthorized', 'ERR_BAD_RESPONSE', config, null, {
        status: 401,
        data: {},
        headers: {},
        config,
      });
    }
    assert.equal(config.headers.get('Authorization'), 'Bearer refreshed-token');
    return response(config, { state: 'idle' });
  };

  const result = await getExportStatus('s1');
  assert.equal(result.state, 'idle');
  assert.equal(calls, 2);
  assert.equal(refreshCalls, 1);
});

test('individual export files send format and exact filename using authenticated API', async () => {
  const { listExportFiles, downloadExportFile } = await import('./exportService.js');
  const original = api.get;
  const calls = [];
  api.get = async (url, config) => {
    calls.push({ url, ...config });
    return { data: config.responseType === 'blob'
      ? new Blob(['%PDF-test'])
      : { files: [{ filename: 'exam_101.tex', size_bytes: 7 }] } };
  };
  try {
    assert.deepEqual(await listExportFiles('s/1', 'tex'), [{ filename: 'exam_101.tex', size_bytes: 7 }]);
    const blob = await downloadExportFile('s/1', 'pdf', 'exam_101.pdf');
    assert.equal(await blob.text(), '%PDF-test');
    assert.equal(calls[0].url, '/sessions/s%2F1/export/files');
    assert.deepEqual(calls[1].params, { format: 'pdf', filename: 'exam_101.pdf' });
    assert.equal(calls[1].responseType, 'blob');
  } finally {
    api.get = original;
  }
});

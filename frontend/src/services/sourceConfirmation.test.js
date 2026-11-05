import assert from 'node:assert/strict';
import { after, beforeEach, test } from 'node:test';
import { register } from 'node:module';
import { useAuthStore } from '../features/auth/authStore.js';
import { auth } from './test-support/supabase.stub.js';

register('./test-support/auth-loader.js', import.meta.url);
const { api } = await import('./api.js');
const { confirmSource, getSourceArtifactStatus } = await import('./sourceConfirmation.js');

const id = '10000000-0000-4000-8000-000000000001';
const sourceRevision = '20000000-0000-4000-8000-000000000002';
const idempotencyKey = '30000000-0000-4000-8000-000000000003';
const action = { sourceRevision, idempotencyKey };
const confirmation = { session_id: id, confirmation_id: idempotencyKey, status: 'blueprinted',
  canonical_status: 'pending', total_blueprints: 0 };
const response = (config, data, status = 200) => ({ config, data, status, headers: {} });
const adapter = api.defaults.adapter;
after(() => { api.defaults.adapter = adapter; });
beforeEach(() => {
  useAuthStore.getState().setSession({ user: { id: 'account-a' }, access_token: 'fixture-token' });
  auth.getSession = async () => ({ data: { session: useAuthStore.getState().session }, error: null });
  api.defaults.adapter = async () => { throw new Error('Unexpected request'); };
});

test('confirm dùng revision đã xem, cùng UUID và signal; pending vẫn xác nhận thành công', async () => {
  const signal = new AbortController().signal;
  api.defaults.adapter = async (config) => {
    assert.equal(config.method, 'post');
    assert.equal(config.url, `/sessions/${id}/confirm-source`);
    assert.deepEqual(JSON.parse(config.data), { source_revision: sourceRevision });
    assert.equal(config.headers.get('Idempotency-Key'), idempotencyKey);
    assert.equal(config.headers.get('Authorization'), 'Bearer fixture-token');
    assert.equal(config.signal, signal);
    return response(config, confirmation);
  };
  assert.deepEqual(await confirmSource(id, { ...action, signal }), confirmation);
});

test('không gửi confirm khi thiếu hoặc sai revision/key', async () => {
  for (const invalid of [{}, { ...action, sourceRevision: 'not-uuid' }, { ...action, idempotencyKey: '' }]) {
    await assert.rejects(confirmSource(id, invalid), { code: 'ERR_CONFIRM_INPUT' });
  }
});

test('response không chứng minh được confirm thì đánh dấu chưa rõ kết quả', async () => {
  for (const [payload, status] of [
    [{ ...confirmation, session_id: sourceRevision }, 200],
    [{ ...confirmation, confirmation_id: sourceRevision }, 200],
    [{ ...confirmation, status: 'draft' }, 200],
    [confirmation, 201],
  ]) {
    api.defaults.adapter = async (config) => response(config, payload, status);
    await assert.rejects(confirmSource(id, action), { code: 'ERR_CONFIRM_RESPONSE', outcomeUncertain: true });
  }
});

test('giữ nguyên HTTP/domain error và không tự retry lỗi mạng', async () => {
  for (const cause of [Object.assign(new Error('conflict'), {
    response: { status: 409, data: { error_code: 'ERR_SOURCE_REVISION_CONFLICT' } },
  }), new Error('timeout')]) {
    let calls = 0;
    api.defaults.adapter = async () => { calls++; throw cause; };
    await assert.rejects(confirmSource(id, action), (error) => error === cause);
    assert.equal(calls, 1);
  }
});

test('đọc canonical artifact đúng phiên, phân biệt pending với ready không có mode', async () => {
  for (const artifact of [
    { session_id: id, ready: false, canonical_status: 'pending', supported_modes: null },
    { session_id: id, ready: true, canonical_status: 'ready', supported_modes: [] },
  ]) {
    api.defaults.adapter = async (config) => {
      assert.equal(config.method, 'get');
      assert.equal(config.url, `/sessions/${id}/source-artifacts`);
      return response(config, artifact);
    };
    assert.deepEqual(await getSourceArtifactStatus(id), artifact);
  }
});

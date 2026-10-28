import assert from 'node:assert/strict';
import { register } from 'node:module';
import { beforeEach, test } from 'node:test';
import axios from 'axios';
import { AuthRetryableFetchError, AuthSessionMissingError } from '@supabase/supabase-js';
import { useAuthStore } from '../auth/authStore.js';
import { auth } from '../../services/test-support/supabase.stub.js';

register('../../services/test-support/auth-loader.js', import.meta.url);
const { cloneSessionForDashboard } = await import('./cloneSessionForDashboard.js');
const { api } = await import('../../services/api.js');
const options = { timeout: 3000 };
const copy = {
  id: 'copy-a', user_id: 'account-a', title: 'Bản sao', subject: 'Toán',
  status: 'draft', created_at: '2026-10-24T08:00:00Z',
};

beforeEach(() => {
  useAuthStore.getState().setChecking();
  useAuthStore.getState().setSession({ user: { id: 'account-a' }, access_token: 'fixture-token-a' });
  useAuthStore.getState().setProfile({ id: 'account-a', email: 'teacher@example.test' }, useAuthStore.getState().sessionVersion);
  auth.getSession = async () => ({ data: { session: useAuthStore.getState().session }, error: null });
  auth.refreshSession = async () => { throw new Error('Unexpected refresh'); };
});

test('adapter Dashboard dùng service/client chung, trả nguyên phiên mới', options, async () => {
  const initial = useAuthStore.getState();
  let calls = 0;
  api.defaults.adapter = async (config) => {
    calls += 1;
    assert.equal(config.method, 'post');
    assert.equal(api.getUri(config), '/api/sessions/source-a/clone');
    assert.equal(config.headers.get('Authorization'), 'Bearer fixture-token-a');
    assert.deepEqual(JSON.parse(config.data), { new_title: 'Bản sao' });
    return { status: 201, data: copy, headers: {}, config };
  };
  assert.equal(await cloneSessionForDashboard('source-a', ' Bản sao '), copy);
  assert.equal(calls, 1);
  assert.equal(useAuthStore.getState(), initial);
});

test('adapter giữ thông báo kiểm input, không gửi HTTP', options, async () => {
  let calls = 0;
  api.defaults.adapter = async () => { calls += 1; throw new Error('Unexpected request'); };
  await assert.rejects(cloneSessionForDashboard('', 'Bản sao'), /Phiên cần nhân bản không hợp lệ/);
  await assert.rejects(cloneSessionForDashboard('source-a', ' '), /Tên bản sao phải có/);
  assert.equal(calls, 0);
});

test('403/404/422/429 và HTTP khác được chuyển lời nhắn an toàn, không retry/logout', options, async () => {
  const initial = useAuthStore.getState();
  const expected = new Map([
    [403, /không có quyền nhân bản/], [404, /Không tìm thấy phiên nguồn/],
    [422, /kiểm tra tiêu đề/], [429, /thao tác quá nhanh/], [400, /Không thể nhân bản phiên/],
  ]);
  for (const [status, message] of expected) {
    let calls = 0;
    let original;
    api.defaults.adapter = async (config) => {
      calls += 1;
      original = new axios.AxiosError('Raw transport message', 'ERR_BAD_RESPONSE', config, null,
        { status, data: { detail: 'PRIVATE_BACKEND_DETAIL' }, headers: {}, config });
      throw original;
    };
    await assert.rejects(cloneSessionForDashboard('source-a', 'Bản sao'), (error) => {
      assert.match(error.message, message);
      assert.doesNotMatch(error.message, /PRIVATE_BACKEND_DETAIL|Raw transport/);
      assert.equal(error.cause, original);
      return true;
    });
    assert.equal(calls, 1);
    assert.equal(useAuthStore.getState(), initial);
  }
});

test('500/503/mạng/timeout nhắc kiểm danh sách trước gửi lại, chỉ một POST', options, async () => {
  const initial = useAuthStore.getState();
  for (const status of [500, 503, 'ERR_NETWORK', 'ECONNABORTED']) {
    let calls = 0;
    api.defaults.adapter = async (config) => {
      calls += 1;
      throw new axios.AxiosError('Raw transport message', typeof status === 'number' ? 'ERR_BAD_RESPONSE' : status,
        config, null, typeof status === 'number' ? { status, data: {}, headers: {}, config } : undefined);
    };
    await assert.rejects(cloneSessionForDashboard('source-a', 'Bản sao'), /tải lại trang để kiểm tra danh sách trước khi thử lại/);
    assert.equal(calls, 1);
    assert.equal(useAuthStore.getState(), initial);
  }
});

test('phản hồi201 sai giữ cảnh báo kiểm danh sách của service, không gửi lại', options, async () => {
  let calls = 0;
  api.defaults.adapter = async (config) => {
    calls += 1;
    return { status: 201, data: { id: 'copy-a' }, headers: {}, config };
  };
  await assert.rejects(cloneSessionForDashboard('source-a', 'Bản sao'), /Phản hồi nhân bản không hợp lệ.*kiểm tra lại danh sách/);
  assert.equal(calls, 1);
});

test('đổi tài khoản trong lúc clone giữ CanceledError, không biến thành lỗi của B', options, async () => {
  let release;
  let entered;
  const started = new Promise((resolve) => { entered = resolve; });
  api.defaults.adapter = async (config) => {
    entered();
    await new Promise((resolve) => { release = resolve; });
    return { status: 201, data: copy, headers: {}, config };
  };
  const request = cloneSessionForDashboard('source-a', 'Bản sao');
  await started;
  useAuthStore.getState().setSession({ user: { id: 'account-b' }, access_token: 'fixture-token-b' });
  const current = useAuthStore.getState();
  release();
  await assert.rejects(request, axios.isCancel);
  assert.equal(useAuthStore.getState(), current);
});

test('401 vẫn do client refresh/retry tối đa một lần rồi yêu cầu đăng nhập lại', options, async () => {
  let calls = 0;
  let refreshes = 0;
  auth.refreshSession = async () => {
    refreshes += 1;
    const session = { user: { id: 'account-a' }, access_token: 'fixture-fresh-token' };
    useAuthStore.getState().setSession(session);
    return { data: { session }, error: null };
  };
  api.defaults.adapter = async (config) => {
    calls += 1;
    throw new axios.AxiosError('Unauthorized', 'ERR_BAD_RESPONSE', config, null,
      { status: 401, data: {}, headers: {}, config });
  };
  await assert.rejects(cloneSessionForDashboard('source-a', 'Bản sao'), /Vui lòng đăng nhập lại/);
  assert.equal(calls, 2);
  assert.equal(refreshes, 1);
  assert.equal(useAuthStore.getState().status, 'reauth_required');
});

for (const expired of [false, true]) {
  test(`lỗi SDK Auth có lời nhắn phù hợp, không gửi POST (expired: ${expired})`, options, async () => {
    const initial = useAuthStore.getState();
    const cause = expired ? new AuthSessionMissingError() : new AuthRetryableFetchError('Raw offline message', 503);
    auth.getSession = async () => ({ data: { session: null }, error: cause });
    let calls = 0;
    api.defaults.adapter = async () => { calls += 1; throw new Error('Unexpected HTTP'); };
    await assert.rejects(cloneSessionForDashboard('source-a', 'Bản sao'), (error) => {
      assert.match(error.message, expired ? /Vui lòng đăng nhập lại/ : /Chưa thể kiểm tra phiên đăng nhập/);
      assert.equal(error.cause, cause);
      return true;
    });
    assert.equal(calls, 0);
    assert.equal(useAuthStore.getState().status, expired ? 'reauth_required' : initial.status);
  });
}

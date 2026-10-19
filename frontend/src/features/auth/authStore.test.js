import { beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { useAuthStore } from './authStore.js';

const sampleUser = {
    id: 'mock-user-001',
    name: 'Tài khoản mẫu',
};

beforeEach(() => {
    useAuthStore.getState().setChecking();
});

test('nhận người dùng và xóa người dùng khi đăng xuất', () => {
    useAuthStore.getState().setUser(sampleUser);

    assert.equal(useAuthStore.getState().status, 'authenticated');
    assert.deepEqual(useAuthStore.getState().user, sampleUser);

    useAuthStore.getState().setUser(null);

    assert.equal(useAuthStore.getState().status, 'unauthenticated');
    assert.equal(useAuthStore.getState().user, null);
});

test('xóa người dùng cũ khi kiểm tra lại phiên', () => {
    useAuthStore.getState().setUser(sampleUser);
    useAuthStore.getState().setChecking();

    assert.equal(useAuthStore.getState().status, 'checking');
    assert.equal(useAuthStore.getState().user, null);
});

test('không giữ trạng thái đăng nhập khi người dùng thiếu ID', () => {
    useAuthStore.getState().setUser(sampleUser);
    useAuthStore.getState().setUser({ name: 'Thiếu ID' });

    assert.equal(useAuthStore.getState().status, 'unauthenticated');
    assert.equal(useAuthStore.getState().user, null);
});

test('có phiên vẫn phải chờ profile và mất phiên phải xóa dữ liệu', () => {
    useAuthStore.getState().setUser(sampleUser);

    useAuthStore.getState().setSession({
        access_token: 'unit-test-token',
        user: { id: 'test-user-002' },
    });

    const pending = useAuthStore.getState();

    assert.equal(pending.status, 'profile_pending');
    assert.equal(pending.user, null);
    assert.equal(pending.session.user.id, 'test-user-002');

    useAuthStore.getState().setSession(null);

    const signedOut = useAuthStore.getState();

    assert.equal(signedOut.status, 'unauthenticated');
    assert.equal(signedOut.session, null);
    assert.equal(signedOut.user, null);
});

test('phân biệt đổi tài khoản với refresh token cùng tài khoản', () => {
    const store = useAuthStore;

    store.getState().setSession({
        access_token: 'test-token-a1',
        user: { id: 'account-a' },
    });

    const versionA = store.getState().sessionVersion;

    // Refresh cùng tài khoản không làm mất hiệu lực request hiện tại.
    store.getState().setSession({
        access_token: 'test-token-a2',
        user: { id: 'account-a' },
    });

    assert.equal(store.getState().sessionVersion, versionA);

    // Đổi sang B phải làm mất hiệu lực request của A.
    store.getState().setSession({
        access_token: 'test-token-b',
        user: { id: 'account-b' },
    });

    assert.ok(store.getState().sessionVersion > versionA);

    const versionB = store.getState().sessionVersion;

    // Đăng xuất rồi vào lại cùng B vẫn là lượt đăng nhập mới.
    store.getState().setSession(null);
    store.getState().setSession({
        access_token: 'test-token-b-new',
        user: { id: 'account-b' },
    });

    assert.ok(store.getState().sessionVersion > versionB);
});
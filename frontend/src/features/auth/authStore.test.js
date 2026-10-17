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
import { beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { useAuthStore } from './authStore.js';

const sampleUser = {
    id: 'mock-user-001',
    name: 'Tài khoản mẫu',
};

const sessionFor = (id, token = `test-token-${id}`) => ({
    access_token: token,
    user: { id },
});

const profileFor = (id) => ({
    id,
    email: `${id}@example.test`,
    name: null,
    created_at: null,
});

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

test('nhận profile đúng tài khoản và giữ nguyên phiên đăng nhập', () => {
    const session = sessionFor('account-a');
    const profile = profileFor('account-a');
    useAuthStore.getState().setSession(session);
    const version = useAuthStore.getState().sessionVersion;

    useAuthStore.getState().setProfile(profile, version);

    const state = useAuthStore.getState();
    assert.equal(state.status, 'authenticated');
    assert.deepEqual(state.user, profile);
    assert.equal(state.session, session);
    assert.equal(state.sessionVersion, version);
});

test('profile sai tài khoản, thiếu email hoặc sai lượt không mở quyền truy cập', () => {
    useAuthStore.getState().setSession(sessionFor('account-a'));
    const pending = useAuthStore.getState();
    const profile = profileFor('account-a');

    for (const invalid of [
        null,
        { email: profile.email },
        profileFor('account-b'),
        { id: profile.id },
        { ...profile, email: '   ' },
        { ...profile, email: 123 },
    ]) {
        pending.setProfile(invalid, pending.sessionVersion);
        assert.equal(useAuthStore.getState(), pending);
    }

    pending.setProfile(profile, pending.sessionVersion - 1);
    assert.equal(useAuthStore.getState(), pending);
    pending.setProfile(profile, pending.sessionVersion);
    assert.equal(useAuthStore.getState().status, 'authenticated');
});

test('profile cũ không khôi phục tài khoản sau logout hoặc đăng nhập lại cùng user', () => {
    useAuthStore.getState().setSession(sessionFor('account-a'));
    const oldVersion = useAuthStore.getState().sessionVersion;
    const profile = profileFor('account-a');

    useAuthStore.getState().setSession(null);
    const signedOut = useAuthStore.getState();
    signedOut.setProfile(profile, oldVersion);
    assert.equal(useAuthStore.getState(), signedOut);

    useAuthStore.getState().setSession(sessionFor('account-a', 'new-login-token'));
    const newLogin = useAuthStore.getState();
    newLogin.setProfile(profile, oldVersion);
    assert.equal(useAuthStore.getState(), newLogin);
    newLogin.setProfile(profile, newLogin.sessionVersion);
    assert.equal(useAuthStore.getState().status, 'authenticated');
});

test('kiểm tra lại phiên bỏ profile cũ đang trả về', () => {
    useAuthStore.getState().setSession(sessionFor('account-a'));
    const oldVersion = useAuthStore.getState().sessionVersion;
    useAuthStore.getState().setChecking();
    const checking = useAuthStore.getState();

    checking.setProfile(profileFor('account-a'), oldVersion);
    assert.equal(useAuthStore.getState(), checking);
    assert.equal(checking.status, 'checking');
    assert.equal(checking.user, null);
    assert.equal(checking.session, null);
});

test('đổi A sang B xóa profile A và không nhận kết quả A đến trễ', () => {
    useAuthStore.getState().setSession(sessionFor('account-a'));
    const versionA = useAuthStore.getState().sessionVersion;
    useAuthStore.getState().setProfile(profileFor('account-a'), versionA);

    const sessionB = sessionFor('account-b');
    useAuthStore.getState().setSession(sessionB);
    const pendingB = useAuthStore.getState();
    assert.equal(pendingB.status, 'profile_pending');
    assert.equal(pendingB.user, null);
    assert.equal(pendingB.session, sessionB);
    assert.ok(pendingB.sessionVersion > versionA);

    pendingB.setProfile(profileFor('account-a'), versionA);
    assert.equal(useAuthStore.getState(), pendingB);
    pendingB.setProfile(profileFor('account-b'), pendingB.sessionVersion);
    assert.equal(useAuthStore.getState().user.id, 'account-b');
});

test('refresh cùng tài khoản giữ profile và quyền truy cập đã xác nhận', () => {
    useAuthStore.getState().setSession(sessionFor('account-a'));
    const version = useAuthStore.getState().sessionVersion;
    const profile = profileFor('account-a');
    useAuthStore.getState().setProfile(profile, version);
    const refreshed = sessionFor('account-a', 'refreshed-token');

    useAuthStore.getState().setSession(refreshed);

    const state = useAuthStore.getState();
    assert.equal(state.status, 'authenticated');
    assert.equal(state.user, profile);
    assert.equal(state.session, refreshed);
    assert.equal(state.sessionVersion, version);
});

test('refresh khi đang chờ profile giữ phiên mới khi nhận kết quả đúng lượt', () => {
    useAuthStore.getState().setSession(sessionFor('account-a'));
    const version = useAuthStore.getState().sessionVersion;
    const refreshed = sessionFor('account-a', 'refreshed-pending-token');

    useAuthStore.getState().setSession(refreshed);
    assert.equal(useAuthStore.getState().status, 'profile_pending');
    useAuthStore.getState().setProfile(profileFor('account-a'), version);

    assert.equal(useAuthStore.getState().status, 'authenticated');
    assert.equal(useAuthStore.getState().session, refreshed);
});

test('reauth chặn profile cũ và token bị từ chối; token mới vẫn cần profile mới', () => {
    const rejectedSession = sessionFor('account-a');
    const profile = profileFor('account-a');
    useAuthStore.getState().setSession(rejectedSession);
    const oldVersion = useAuthStore.getState().sessionVersion;
    useAuthStore.getState().setProfile(profile, oldVersion);
    useAuthStore.getState().requireReauthentication(oldVersion);
    const rejected = useAuthStore.getState();
    assert.equal(rejected.status, 'reauth_required');
    assert.equal(rejected.user, null);

    rejected.setProfile(profile, oldVersion);
    rejected.setProfile(profile, rejected.sessionVersion);
    rejected.setSession(rejectedSession);
    assert.equal(useAuthStore.getState(), rejected);

    const recoveredSession = sessionFor('account-a', 'recovered-token');
    rejected.setSession(recoveredSession);
    const pending = useAuthStore.getState();
    assert.equal(pending.status, 'profile_pending');
    assert.equal(pending.user, null);
    pending.setProfile(profile, oldVersion);
    assert.equal(useAuthStore.getState(), pending);
    pending.setProfile(profile, pending.sessionVersion);
    assert.equal(useAuthStore.getState().status, 'authenticated');
    assert.equal(useAuthStore.getState().session, recoveredSession);
});

import assert from 'node:assert/strict';
import { register } from 'node:module';
import { test } from 'node:test';
import { setImmediate as nextTurn } from 'node:timers/promises';
import axios from 'axios';
import { useAuthStore } from '../features/auth/authStore.js';
import { auth } from './test-support/supabase.stub.js';

// Đăng ký trước dynamic import để nạp source thực với Auth giả lập.
// Mỗi test file được Node test runner chạy trong process riêng.
register('./test-support/auth-loader.js', import.meta.url);
const { api } = await import('./api.js');

const options = { timeout: 3000 };
const makeSession = (id = 'account-a', token = 'token-old') => ({
    user: { id },
    access_token: token,
});

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function fixture() {
    useAuthStore.getState().setChecking();
    let session;
    let refreshes = 0;
    let calls = 0;
    const refreshStarted = deferred();
    const context = {
        refreshStarted,
        change(nextSession) {
            session = nextSession;
            useAuthStore.getState().setSession(nextSession);
        },
        refresh: async () => ({
            data: { session: makeSession('account-a', 'token-new') },
            error: null,
        }),
        get counts() { return { refreshes, calls }; },
        adapter(handle) {
            api.defaults.adapter = async (config) => {
                calls += 1;
                return handle(config);
            };
        },
    };

    context.change(makeSession());
    auth.getSession = async () => ({ data: { session }, error: null });
    auth.refreshSession = async () => {
        refreshes += 1;
        refreshStarted.resolve();
        const result = await context.refresh();
        if (!result.error && result.data?.session) {
            context.change(result.data.session);
        }
        return result;
    };

    return context;
}

function fail(config, status) {
    throw new axios.AxiosError(
        'Test HTTP error', 'ERR_BAD_RESPONSE', config, null,
        { status, data: {}, headers: {}, config },
    );
}

function ok(config) {
    return { status: 200, data: { ok: true }, headers: {}, config };
}

function rejectOldToken(config) {
    if (config.headers.get('Authorization') === 'Bearer token-old') {
        fail(config, 401);
    }
    return ok(config);
}

test('gắn token hiện tại và bỏ Authorization cũ khi không có phiên', options, async () => {
    const context = fixture();
    context.adapter(ok);
    const signedIn = await api.get('/test');
    assert.equal(signedIn.config.headers.get('Authorization'), 'Bearer token-old');

    context.change(null);
    const signedOut = await api.get('/test', {
        headers: { Authorization: 'Bearer stale-token' },
    });
    assert.equal(signedOut.config.headers.has('Authorization'), false);
    assert.deepEqual(context.counts, { refreshes: 0, calls: 2 });
});

test('401 refresh và retry bằng token mới', options, async () => {
    const context = fixture();
    context.adapter(rejectOldToken);
    const response = await api.get('/test');
    assert.equal(response.config.headers.get('Authorization'), 'Bearer token-new');
    assert.deepEqual(context.counts, { refreshes: 1, calls: 2 });
});

test('401 lần hai dừng, không tạo vòng lặp', options, async () => {
    const context = fixture();
    context.adapter((config) => fail(config, 401));
    await assert.rejects(api.get('/test'), (error) => error.response?.status === 401);
    assert.deepEqual(context.counts, { refreshes: 1, calls: 2 });
});

test('401 khi chưa đăng nhập không refresh', options, async () => {
    const context = fixture();
    context.change(null);
    context.adapter((config) => fail(config, 401));
    await assert.rejects(api.get('/test'), (error) => error.response?.status === 401);
    assert.deepEqual(context.counts, { refreshes: 0, calls: 1 });
});

for (const status of [403, 500]) {
    test(`${status} không refresh hoặc thay đổi phiên`, options, async () => {
        const context = fixture();
        const version = useAuthStore.getState().sessionVersion;
        context.adapter((config) => fail(config, status));
        await assert.rejects(api.get('/test'), (error) => error.response?.status === status);
        assert.deepEqual(context.counts, { refreshes: 0, calls: 1 });
        assert.equal(useAuthStore.getState().sessionVersion, version);
        assert.equal(useAuthStore.getState().session.user.id, 'account-a');
    });
}

test('lỗi mạng không refresh hoặc thay đổi phiên', options, async () => {
    const context = fixture();
    const version = useAuthStore.getState().sessionVersion;
    context.adapter((config) => {
        throw new axios.AxiosError('Test network error', 'ERR_NETWORK', config);
    });
    await assert.rejects(api.get('/test'), (error) => error.code === 'ERR_NETWORK');
    assert.deepEqual(context.counts, { refreshes: 0, calls: 1 });
    assert.equal(useAuthStore.getState().sessionVersion, version);
});

test('refresh lỗi không retry, lần sau vẫn có thể refresh lại', options, async () => {
    const context = fixture();
    const refreshFailure = new Error('Test refresh failure');
    context.refresh = async () => ({ data: {}, error: refreshFailure });
    context.adapter(rejectOldToken);
    await assert.rejects(api.get('/test'), (error) => error === refreshFailure);
    assert.deepEqual(context.counts, { refreshes: 1, calls: 1 });

    context.refresh = async () => ({
        data: { session: makeSession('account-a', 'token-new') }, error: null,
    });
    await api.get('/test');
    assert.deepEqual(context.counts, { refreshes: 2, calls: 3 });
});

test('refresh trả null session không retry', options, async () => {
    const context = fixture();
    context.refresh = async () => ({ data: { session: null }, error: null });
    context.adapter(rejectOldToken);
    await assert.rejects(api.get('/test'), /Không thể làm mới phiên/);
    assert.deepEqual(context.counts, { refreshes: 1, calls: 1 });
});

test('hai 401 đồng thời dùng chung một lần refresh', options, async () => {
    const context = fixture();
    const gate = deferred();
    const bothSent = deferred();
    let oldCalls = 0;
    context.refresh = async () => {
        await gate.promise;
        return { data: { session: makeSession('account-a', 'token-new') }, error: null };
    };
    context.adapter(async (config) => {
        if (config.headers.get('Authorization') !== 'Bearer token-old') return ok(config);
        oldCalls += 1;
        if (oldCalls === 2) bothSent.resolve();
        await bothSent.promise;
        fail(config, 401);
    });

    const requests = Promise.all([api.get('/one'), api.get('/two')]);
    await context.refreshStarted.promise;
    // Để cả hai response handler chờ chung promise trước khi kết thúc refresh.
    await nextTurn();
    gate.resolve();
    await requests;
    assert.deepEqual(context.counts, { refreshes: 1, calls: 4 });
});

for (const status of [200, 401]) {
    for (const change of ['switch', 'logout']) {
        test(`bỏ response ${status} cũ sau ${change}`, options, async () => {
            const context = fixture();
            const sent = deferred();
            const done = deferred();
            context.adapter(async (config) => {
                sent.resolve();
                await done.promise;
                if (status === 401) fail(config, status);
                return ok(config);
            });

            const request = api.get('/test');
            await sent.promise;
            context.change(change === 'switch' ? makeSession('account-b', 'token-b') : null);
            done.resolve();
            await assert.rejects(request, (error) => axios.isCancel(error));
            assert.deepEqual(context.counts, { refreshes: 0, calls: 1 });
            assert.equal(
                useAuthStore.getState().session?.user.id ?? null,
                change === 'switch' ? 'account-b' : null,
            );
        });
    }
}

test('401 trễ dùng token đã refresh sẵn, không refresh thêm', options, async () => {
    const context = fixture();
    context.adapter((config) => {
        if (config.headers.get('Authorization') === 'Bearer token-old') {
            context.change(makeSession('account-a', 'token-new'));
            fail(config, 401);
        }
        return ok(config);
    });
    await api.get('/test');
    assert.deepEqual(context.counts, { refreshes: 0, calls: 2 });
});

test('đổi tài khoản khi đang refresh không replay request của A bằng token B', options, async () => {
    const context = fixture();
    const gate = deferred();
    const sessionB = makeSession('account-b', 'token-b');
    context.refresh = async () => {
        await gate.promise;
        return { data: { session: sessionB }, error: null };
    };
    context.adapter(rejectOldToken);

    const request = api.get('/test');
    await context.refreshStarted.promise;
    context.change(sessionB);
    gate.resolve();
    await assert.rejects(request, (error) => axios.isCancel(error));
    assert.deepEqual(context.counts, { refreshes: 1, calls: 1 });
    assert.equal(useAuthStore.getState().session.user.id, 'account-b');
});

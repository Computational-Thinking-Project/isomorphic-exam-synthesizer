import assert from 'node:assert/strict';
import { register } from 'node:module';
import { beforeEach, test } from 'node:test';
import axios from 'axios';
import { useAuthStore } from '../features/auth/authStore.js';
import { auth } from './test-support/supabase.stub.js';

// Dùng service/client/store thật; chỉ giả lập Auth và đường truyền HTTP.
register('./test-support/auth-loader.js', import.meta.url);
const { listSessions } = await import('./sessions.js');
const { api } = await import('./api.js');

const options = { timeout: 3000 };
const item = {
    id: 'session-a',
    user_id: 'account-a',
    title: 'Phiên kiểm thử',
    subject: 'Toán',
    status: 'partial_generated',
    created_at: '2026-10-24T08:00:00Z',
};

function envelope(overrides = {}) {
    return { items: [], total: 0, page: 1, page_size: 20, ...overrides };
}

function response(config, data) {
    return { status: 200, data, headers: {}, config };
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
        access_token: 'test-list-token-a',
    });
    const version = useAuthStore.getState().sessionVersion;
    useAuthStore.getState().setProfile({
        id: 'account-a', email: 'teacher@example.test',
    }, version);
    auth.getSession = async () => ({
        data: { session: useAuthStore.getState().session }, error: null,
    });
    auth.refreshSession = async () => {
        throw new Error('Không được refresh trong ca kiểm này.');
    };
});

test('list mặc định đúng endpoint và giữ danh sách rỗng hợp lệ', options, async () => {
    const data = envelope();
    api.defaults.adapter = async (config) => {
        assert.equal(config.method, 'get');
        assert.equal(api.getUri(config), '/api/sessions?page=1&page_size=20');
        return response(config, data);
    };
    assert.equal(await listSessions(), data);
});

test('list dùng Bearer chung và giữ đủ metadata của trang có dữ liệu', options, async () => {
    const data = envelope({ items: [item], total: 41, page: 2, page_size: 10 });
    const initial = useAuthStore.getState();
    api.defaults.adapter = async (config) => {
        assert.equal(api.getUri(config), '/api/sessions?page=2&page_size=10');
        assert.equal(config.headers.get('Authorization'), 'Bearer test-list-token-a');
        return response(config, data);
    };
    assert.equal(await listSessions({ page: 2, pageSize: 10 }), data);
    assert.equal(useAuthStore.getState(), initial);
});

test('trang vượt phạm vi vẫn giữ total để UI điều chỉnh trang, không báo sai dữ liệu', options, async () => {
    const data = envelope({ total: 1, page: 3 });
    api.defaults.adapter = async (config) => response(config, data);
    assert.equal(await listSessions({ page: 3 }), data);
});

test('envelope sai hoặc metadata lệch không bị biến thành danh sách rỗng', options, async () => {
    for (const data of [
        null, [], { data: envelope() }, { items: [] },
        envelope({ items: null }), envelope({ total: '0' }),
        envelope({ total: -1 }), envelope({ total: 0.5 }),
        envelope({ page: 2 }), envelope({ page_size: 10 }),
    ]) {
        api.defaults.adapter = async (config) => response(config, data);
        await assert.rejects(listSessions(), /Phản hồi danh sách phiên không hợp lệ/);
    }
});

test('một dòng lỗi trong trang phải báo lỗi thay vì bỏ dòng hoặc trả rỗng', options, async () => {
    for (const invalid of [null, 'session', { ...item, id: ' ' }, { ...item, user_id: null }]) {
        api.defaults.adapter = async (config) => response(config,
            envelope({ items: [item, invalid], total: 2 }));
        await assert.rejects(listSessions(), /Phản hồi danh sách phiên không hợp lệ/);
    }
});

test('trang đầu vào không hợp lệ bị chặn trước Auth và HTTP', options, async () => {
    let calls = 0;
    auth.getSession = async () => { calls += 1; throw new Error('Không được gọi Auth.'); };
    api.defaults.adapter = async () => { calls += 1; throw new Error('Không được gửi HTTP.'); };
    for (const input of [
        { page: 0 }, { page: -1 }, { page: 1.5 }, { page: '1' },
        { pageSize: 0 }, { pageSize: 101 }, { pageSize: '20' },
    ]) {
        await assert.rejects(listSessions(input), /Trang hoặc kích thước trang không hợp lệ/);
    }
    assert.equal(calls, 0);
});

test('lỗi quyền, giới hạn lượt, server và mạng giữ nguyên, không retry hoặc logout', options, async () => {
    const initial = useAuthStore.getState();
    let refreshCalls = 0;
    auth.refreshSession = async () => { refreshCalls += 1; throw new Error('Unexpected refresh'); };
    for (const status of [403, 404, 429, 500, 503, null]) {
        let calls = 0;
        let expected;
        api.defaults.adapter = async (config) => {
            calls += 1;
            expected = new axios.AxiosError('Lỗi list thử nghiệm',
                status ? 'ERR_BAD_RESPONSE' : 'ERR_NETWORK', config, null,
                status ? { status, data: { detail: 'Test detail' }, headers: {}, config } : undefined);
            throw expected;
        };
        await assert.rejects(listSessions(), (error) => error === expected);
        assert.equal(calls, 1);
        assert.equal(useAuthStore.getState(), initial);
    }
    assert.equal(refreshCalls, 0);
});

test('signal đã hủy chặn list trước đường truyền', options, async () => {
    const controller = new AbortController();
    controller.abort();
    let calls = 0;
    api.defaults.adapter = async (config) => {
        calls += 1;
        return response(config, envelope());
    };
    await assert.rejects(listSessions({ signal: controller.signal }), axios.isCancel);
    assert.equal(calls, 0);
});

test('hủy list đang chạy bỏ response đến muộn', options, async () => {
    const controller = new AbortController();
    const entered = deferred();
    const release = deferred();
    api.defaults.adapter = async (config) => {
        assert.equal(config.signal, controller.signal);
        entered.resolve();
        await release.promise;
        return response(config, envelope());
    };
    const request = listSessions({ signal: controller.signal });
    await entered.promise;
    controller.abort();
    release.resolve();
    await assert.rejects(request, axios.isCancel);
});

for (const nextId of ['account-b', null]) {
    test(`đổi tài khoản hoặc logout (${nextId ?? 'logout'}) bỏ list A đến muộn`, options, async () => {
        const entered = deferred();
        const release = deferred();
        api.defaults.adapter = async (config) => {
            entered.resolve();
            await release.promise;
            return response(config, envelope({ items: [item], total: 1 }));
        };
        const request = listSessions();
        await entered.promise;
        useAuthStore.getState().setSession(nextId
            ? { user: { id: nextId }, access_token: 'test-list-token-b' }
            : null);
        const current = useAuthStore.getState();
        release.resolve();
        await assert.rejects(request, axios.isCancel);
        assert.equal(useAuthStore.getState(), current);
    });
}

test('refresh cùng tài khoản trong lúc tải không hủy list hợp lệ', options, async () => {
    const entered = deferred();
    const release = deferred();
    const data = envelope({ items: [item], total: 1 });
    api.defaults.adapter = async (config) => {
        entered.resolve();
        await release.promise;
        return response(config, data);
    };
    const version = useAuthStore.getState().sessionVersion;
    const request = listSessions();
    await entered.promise;
    useAuthStore.getState().setSession({
        user: { id: 'account-a' }, access_token: 'test-list-refreshed-token',
    });
    release.resolve();
    assert.equal(await request, data);
    assert.equal(useAuthStore.getState().sessionVersion, version);
    assert.equal(useAuthStore.getState().status, 'authenticated');
});

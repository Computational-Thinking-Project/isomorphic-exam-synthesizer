import assert from 'node:assert/strict';
import { register } from 'node:module';
import { beforeEach, test } from 'node:test';
import axios from 'axios';
import { useAuthStore } from '../features/auth/authStore.js';
import { auth } from './test-support/supabase.stub.js';

// Giữ service/API client thật, chỉ giả lập Supabase và đường truyền HTTP.
register('./test-support/auth-loader.js', import.meta.url);
const { getMyProfile } = await import('./profile.js');
const { api } = await import('./api.js');

const options = { timeout: 3000 };
const profile = {
    id: 'account-a',
    email: 'teacher@example.test',
    name: null,
    created_at: null,
};

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function response(config, data = profile) {
    return { status: 200, data, headers: {}, config };
}

beforeEach(() => {
    useAuthStore.getState().setChecking();
    useAuthStore.getState().setSession({
        user: { id: profile.id },
        access_token: 'test-profile-token',
    });
    auth.getSession = async () => ({
        data: { session: useAuthStore.getState().session },
        error: null,
    });
    auth.refreshSession = async () => {
        throw new Error('Không được refresh trong tình huống test này.');
    };
});

test('profile dùng đúng endpoint/token, trả dữ liệu trực tiếp và không ghi store', options, async () => {
    const pending = useAuthStore.getState();
    api.defaults.adapter = async (config) => {
        assert.equal(config.method, 'get');
        assert.equal(api.getUri(config), '/api/users/me');
        assert.equal(config.headers.get('Authorization'), 'Bearer test-profile-token');
        return response(config);
    };

    assert.equal(await getMyProfile(), profile);
    assert.equal(useAuthStore.getState(), pending);
});

test('profile thiếu ID/email hoặc bị bọc sai cấu trúc phải báo lỗi', options, async () => {
    const pending = useAuthStore.getState();
    for (const invalid of [
        null,
        { data: profile },
        { ...profile, id: undefined },
        { ...profile, id: ' ' },
        { ...profile, id: 123 },
        { ...profile, email: undefined },
        { ...profile, email: ' ' },
        { ...profile, email: 123 },
    ]) {
        api.defaults.adapter = async (config) => response(config, invalid);
        await assert.rejects(getMyProfile(), /hồ sơ không hợp lệ/);
        assert.equal(useAuthStore.getState(), pending);
    }
});

test('profile giữ nguyên lỗi HTTP/mạng để caller xử lý, không xóa phiên', options, async () => {
    const pending = useAuthStore.getState();
    for (const status of [403, 429, 503, null]) {
        let expected;
        api.defaults.adapter = async (config) => {
            expected = new axios.AxiosError(
                'Lỗi profile thử nghiệm',
                status ? 'ERR_BAD_RESPONSE' : 'ERR_NETWORK',
                config,
                null,
                status ? { status, data: { detail: 'Test detail' }, headers: {}, config } : undefined,
            );
            throw expected;
        };
        await assert.rejects(getMyProfile(), (error) => error === expected);
        assert.equal(useAuthStore.getState(), pending);
    }
});

test('signal đã hủy chặn profile trước khi gửi HTTP', options, async () => {
    const controller = new AbortController();
    controller.abort();
    let calls = 0;
    api.defaults.adapter = async (config) => {
        calls += 1;
        return response(config);
    };

    await assert.rejects(getMyProfile({ signal: controller.signal }), axios.isCancel);
    assert.equal(calls, 0);
});

test('hủy profile đang tải không nhận kết quả đến sau', options, async () => {
    const controller = new AbortController();
    const entered = deferred();
    const release = deferred();
    const pendingState = useAuthStore.getState();
    api.defaults.adapter = async (config) => {
        assert.equal(config.signal, controller.signal);
        entered.resolve();
        await release.promise;
        return response(config);
    };

    const request = getMyProfile({ signal: controller.signal });
    await entered.promise;
    controller.abort();
    release.resolve();

    await assert.rejects(request, axios.isCancel);
    assert.equal(useAuthStore.getState(), pendingState);
});

test('đổi sang B khi đang tải profile A thì client chung bỏ kết quả A', options, async () => {
    const entered = deferred();
    const release = deferred();
    api.defaults.adapter = async (config) => {
        entered.resolve();
        await release.promise;
        return response(config);
    };

    const request = getMyProfile();
    await entered.promise;
    useAuthStore.getState().setSession({
        user: { id: 'account-b' },
        access_token: 'test-token-b',
    });
    const accountB = useAuthStore.getState();
    release.resolve();

    await assert.rejects(request, axios.isCancel);
    assert.equal(useAuthStore.getState(), accountB);
    assert.equal(accountB.user, null);
});

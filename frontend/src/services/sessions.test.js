import assert from 'node:assert/strict';
import { register } from 'node:module';
import { beforeEach, test } from 'node:test';
import axios from 'axios';
import { useAuthStore } from '../features/auth/authStore.js';
import { auth } from './test-support/supabase.stub.js';

// Dùng service/client/store thật; chỉ giả lập Auth và đường truyền HTTP.
register('./test-support/auth-loader.js', import.meta.url);
const { listSessions, cloneSession, createSession, getSessionDetail } = await import('./sessions.js');
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

function clonedItem(overrides = {}) {
    return { ...item, id: 'session-copy', title: 'Bản sao', status: 'draft', ...overrides };
}

function createdItem(overrides = {}) {
    return {
        ...clonedItem({ title: 'Phiên mới' }), grade: 12,
        updated_at: '2026-10-26T08:00:00Z', ...overrides,
    };
}

function detailItem(overrides = {}) {
    return { ...createdItem({ id: item.id }), source_questions: [], exam_versions: [], ...overrides };
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

test('clone gửi POST đúng ID/tên và Bearer, trả trực tiếp phiên mới HTTP 201', options, async () => {
    const data = clonedItem();
    const initial = useAuthStore.getState();
    let calls = 0;
    api.defaults.adapter = async (config) => {
        calls += 1;
        assert.equal(config.method, 'post');
        assert.equal(api.getUri(config), '/api/sessions/session%3Fa%23b/clone');
        assert.deepEqual(JSON.parse(config.data), { new_title: 'Bản sao' });
        assert.equal(config.headers.get('Authorization'), 'Bearer test-list-token-a');
        return { ...response(config, data), status: 201 };
    };
    assert.equal(await cloneSession(' session?a#b ', ' Bản sao '), data);
    assert.equal(calls, 1);
    assert.equal(useAuthStore.getState(), initial);
});

test('clone nhận tên 255 ký tự Unicode theo giới hạn backend', options, async () => {
    const title = '📚'.repeat(255);
    const data = clonedItem({ title });
    api.defaults.adapter = async (config) => {
        assert.deepEqual(JSON.parse(config.data), { new_title: title });
        return { ...response(config, data), status: 201 };
    };
    assert.equal(await cloneSession(item.id, title), data);
});

test('clone chặn ID/tên không hợp lệ trước Auth và HTTP', options, async () => {
    let calls = 0;
    auth.getSession = async () => { calls += 1; throw new Error('Unexpected Auth'); };
    api.defaults.adapter = async () => { calls += 1; throw new Error('Unexpected HTTP'); };
    for (const id of [undefined, null, 123, '', ' \n ']) {
        await assert.rejects(cloneSession(id, 'Bản sao'), /Phiên cần nhân bản không hợp lệ/);
    }
    for (const title of [undefined, null, 123, '', ' \n ', 'a'.repeat(256), '📚'.repeat(256)]) {
        await assert.rejects(cloneSession(item.id, title), /Tên bản sao phải có/);
    }
    assert.equal(calls, 0);
});

test('clone không nhận object lỗi/phiên gốc/sai trạng thái và không tự gửi lại', options, async () => {
    const initial = useAuthStore.getState();
    for (const data of [
        null, [], { data: clonedItem() }, { id: 'session-copy' },
        clonedItem({ id: ' ' }), clonedItem({ user_id: null }),
        clonedItem({ id: item.id }), clonedItem({ status: 'approved' }),
    ]) {
        let calls = 0;
        api.defaults.adapter = async (config) => {
            calls += 1;
            return { ...response(config, data), status: 201 };
        };
        await assert.rejects(cloneSession(item.id, 'Bản sao'), /kiểm tra lại danh sách/);
        assert.equal(calls, 1);
        assert.equal(useAuthStore.getState(), initial);
    }
});

test('clone lỗi HTTP/mạng/timeout giữ nguyên lỗi, không tự nhân bản lần nữa', options, async () => {
    const initial = useAuthStore.getState();
    let refreshCalls = 0;
    auth.refreshSession = async () => { refreshCalls += 1; throw new Error('Unexpected refresh'); };
    for (const status of [403, 404, 422, 429, 500, 503, 'network', 'timeout']) {
        let calls = 0;
        let expected;
        api.defaults.adapter = async (config) => {
            calls += 1;
            const http = typeof status === 'number';
            expected = new axios.AxiosError('Lỗi clone thử nghiệm',
                http ? 'ERR_BAD_RESPONSE' : status === 'timeout' ? 'ECONNABORTED' : 'ERR_NETWORK',
                config, null, http ? { status, data: {}, headers: {}, config } : undefined);
            throw expected;
        };
        await assert.rejects(cloneSession(item.id, 'Bản sao'), (error) => error === expected);
        assert.equal(calls, 1);
        assert.equal(useAuthStore.getState(), initial);
    }
    assert.equal(refreshCalls, 0);
});

for (const nextId of ['account-b', null]) {
    test(`clone không trả kết quả A sau ${nextId ?? 'logout'}, không gửi lại`, options, async () => {
        const entered = deferred();
        const release = deferred();
        let calls = 0;
        api.defaults.adapter = async (config) => {
            calls += 1;
            entered.resolve();
            await release.promise;
            return { ...response(config, clonedItem()), status: 201 };
        };
        const request = cloneSession(item.id, 'Bản sao');
        await entered.promise;
        useAuthStore.getState().setSession(nextId
            ? { user: { id: nextId }, access_token: 'test-clone-token-b' }
            : null);
        const current = useAuthStore.getState();
        release.resolve();
        await assert.rejects(request, axios.isCancel);
        assert.equal(calls, 1);
        assert.equal(useAuthStore.getState(), current);
        // Bỏ kết quả ở frontend không chứng minh backend chưa tạo bản sao.
    });
}

for (const retryFails of [false, true]) {
    test(`clone dùng refresh/retry 401 chung tối đa một lần (retry lỗi: ${retryFails})`, options, async () => {
        let calls = 0;
        let refreshCalls = 0;
        const version = useAuthStore.getState().sessionVersion;
        const data = clonedItem();
        auth.refreshSession = async () => {
            refreshCalls += 1;
            const session = { user: { id: 'account-a' }, access_token: 'test-clone-fresh-token' };
            useAuthStore.getState().setSession(session);
            return { data: { session }, error: null };
        };
        api.defaults.adapter = async (config) => {
            calls += 1;
            assert.equal(config.method, 'post');
            assert.equal(api.getUri(config), '/api/sessions/session-a/clone');
            assert.deepEqual(JSON.parse(config.data), { new_title: 'Bản sao' });
            assert.equal(config.headers.get('Authorization'), calls === 1
                ? 'Bearer test-list-token-a' : 'Bearer test-clone-fresh-token');
            if (calls === 1 || retryFails) {
                throw new axios.AxiosError('Test unauthorized', 'ERR_BAD_RESPONSE', config, null,
                    { status: 401, data: {}, headers: {}, config });
            }
            return { ...response(config, data), status: 201 };
        };
        if (retryFails) {
            await assert.rejects(cloneSession(item.id, 'Bản sao'),
                (error) => error.response?.status === 401);
            assert.equal(useAuthStore.getState().status, 'reauth_required');
            assert.equal(useAuthStore.getState().user, null);
            assert.equal(useAuthStore.getState().sessionVersion, version + 1);
        } else {
            assert.equal(await cloneSession(item.id, 'Bản sao'), data);
            assert.equal(useAuthStore.getState().status, 'authenticated');
            assert.equal(useAuthStore.getState().sessionVersion, version);
        }
        assert.equal(calls, 2);
        assert.equal(refreshCalls, 1);
    });
}

test('create gửi metadata chuẩn, bỏ trường owner/status từ caller và trả phiên 201 trực tiếp', options, async () => {
    const data = createdItem();
    let calls = 0;
    api.defaults.adapter = async (config) => {
        calls += 1;
        assert.equal(config.method, 'post');
        assert.equal(api.getUri(config), '/api/sessions');
        assert.equal(config.headers.get('Authorization'), 'Bearer test-list-token-a');
        assert.deepEqual(JSON.parse(config.data), { title: 'Phiên mới', subject: 'Toán', grade: 12 });
        return { ...response(config, data), status: 201 };
    };
    assert.equal(await createSession({ title: ' Phiên mới ', user_id: 'account-b', status: 'approved' }), data);
    assert.equal(calls, 1);
});

test('create giữ môn/lớp đã chọn và giới hạn Unicode theo backend', options, async () => {
    const title = '📚'.repeat(255);
    const subject = '🧪'.repeat(100);
    const data = createdItem({ title, subject, grade: 1 });
    api.defaults.adapter = async (config) => {
        assert.deepEqual(JSON.parse(config.data), { title, subject, grade: 1 });
        return { ...response(config, data), status: 201 };
    };
    assert.equal(await createSession({ title: ` ${title} `, subject: ` ${subject} `, grade: 1 }), data);
});

test('create chặn metadata sai trước Auth/HTTP', options, async () => {
    let calls = 0;
    auth.getSession = async () => { calls += 1; throw new Error('Unexpected Auth'); };
    api.defaults.adapter = async () => { calls += 1; throw new Error('Unexpected HTTP'); };
    for (const metadata of [
        undefined, null, [], '', {}, { title: 5 }, { title: ' \n ' },
        { title: '📚'.repeat(256) }, { title: 'A', subject: null },
        { title: 'A', subject: 'a'.repeat(101) },
        ...[0, 13, 1.5, '12', null].map((grade) => ({ title: 'A', grade })),
    ]) {
        await assert.rejects(createSession(metadata), /Thông tin tạo phiên|Tiêu đề phiên|Môn học|Khối lớp/);
    }
    assert.equal(calls, 0);
});

test('create response sai không được gửi lại vì server có thể đã tạo phiên', options, async () => {
    for (const data of [null, [], { data: createdItem() }, createdItem({ grade: '12' }),
        createdItem({ status: 'blueprinted' }), createdItem({ updated_at: '' })]) {
        let calls = 0;
        api.defaults.adapter = async (config) => {
            calls += 1;
            return { ...response(config, data), status: 201 };
        };
        await assert.rejects(createSession({ title: 'Phiên mới' }), /kiểm tra lại danh sách/);
        assert.equal(calls, 1);
    }
});

test('detail chỉ GET đúng ID đã mã hóa, giữ metadata/nguồn/mã đề và không sửa store', options, async () => {
    const id = 'session?a#b';
    const data = detailItem({ id, status: 'future_status',
        source_questions: [{ id: 'question-a', session_id: id, raw_content: '$x+3=7$' }],
        exam_versions: [{ id: 'version-a', session_id: id, version_code: '101' }],
    });
    const initial = useAuthStore.getState();
    api.defaults.adapter = async (config) => {
        assert.equal(config.method, 'get');
        assert.equal(api.getUri(config), '/api/sessions/session%3Fa%23b');
        assert.equal(config.headers.get('Authorization'), 'Bearer test-list-token-a');
        return response(config, data);
    };
    assert.equal(await getSessionDetail(` ${id} `), data);
    assert.equal(useAuthStore.getState(), initial);
});

test('detail chấp nhận phiên rỗng và UUID khác kiểu viết hoa', options, async () => {
    const id = 'abcdefab-1234-1234-1234-123456789abc';
    const data = detailItem({ id });
    api.defaults.adapter = async (config) => response(config, data);
    assert.equal(await getSessionDetail(id.toUpperCase()), data);
});

test('detail chặn ID trống hoặc literal new trước Auth/HTTP', options, async () => {
    let calls = 0;
    auth.getSession = async () => { calls += 1; throw new Error('Unexpected Auth'); };
    api.defaults.adapter = async () => { calls += 1; throw new Error('Unexpected HTTP'); };
    for (const id of [undefined, null, 5, '', ' \n ', 'new', ' NEW ']) {
        await assert.rejects(getSessionDetail(id), /Phiên cần đọc không hợp lệ/);
    }
    assert.equal(calls, 0);
});

test('detail không biến response thiếu nguồn/mã đề hoặc sai liên kết thành nguồn trống', options, async () => {
    for (const data of [null, { data: detailItem() }, detailItem({ id: 'other-session' }),
        detailItem({ grade: null }), detailItem({ source_questions: undefined }),
        detailItem({ exam_versions: null }), detailItem({ source_questions: [null] }),
        detailItem({ source_questions: [{ id: 'question-a', session_id: 'other-session' }] }),
        detailItem({ exam_versions: [{ id: 'version-a', session_id: 'other-session' }] }),
    ]) {
        api.defaults.adapter = async (config) => response(config, data);
        await assert.rejects(getSessionDetail(item.id), /Phản hồi chi tiết phiên không hợp lệ/);
    }
});

const createDetailCases = [
    { name: 'create', call: (config) => createSession({ title: 'Phiên mới' }, config), data: createdItem },
    { name: 'detail', call: (config) => getSessionDetail(item.id, config), data: detailItem },
];

for (const operation of createDetailCases) {
    test(`${operation.name}: lỗi HTTP/mạng/timeout không tự retry hoặc logout`, options, async () => {
        const initial = useAuthStore.getState();
        for (const status of [403, 404, 409, 422, 429, 500, 503, 'network', 'timeout']) {
            let calls = 0;
            let expected;
            api.defaults.adapter = async (config) => {
                calls += 1;
                const http = typeof status === 'number';
                expected = new axios.AxiosError('Fixture error',
                    http ? 'ERR_BAD_RESPONSE' : status === 'timeout' ? 'ECONNABORTED' : 'ERR_NETWORK',
                    config, null, http ? { status, data: {}, headers: {}, config } : undefined);
                throw expected;
            };
            await assert.rejects(operation.call(), (error) => error === expected);
            assert.equal(calls, 1);
            assert.equal(useAuthStore.getState(), initial);
        }
    });

    test(`${operation.name}: signal chặn trước gửi và bỏ phản hồi sau khi hủy`, options, async () => {
        const before = new AbortController();
        before.abort();
        let calls = 0;
        api.defaults.adapter = async (config) => { calls += 1; return response(config, operation.data()); };
        await assert.rejects(operation.call({ signal: before.signal }), axios.isCancel);
        assert.equal(calls, 0);

        const entered = deferred();
        const release = deferred();
        const during = new AbortController();
        api.defaults.adapter = async (config) => {
            calls += 1;
            assert.equal(config.signal, during.signal);
            entered.resolve();
            await release.promise;
            return response(config, operation.data());
        };
        const request = operation.call({ signal: during.signal });
        await entered.promise;
        during.abort();
        release.resolve();
        await assert.rejects(request, axios.isCancel);
        assert.equal(calls, 1);
    });

    for (const nextId of ['account-b', null]) {
        test(`${operation.name}: bỏ kết quả cũ sau ${nextId ?? 'logout'}`, options, async () => {
            const entered = deferred();
            const release = deferred();
            let calls = 0;
            api.defaults.adapter = async (config) => {
                calls += 1;
                entered.resolve();
                await release.promise;
                return response(config, operation.data());
            };
            const request = operation.call();
            await entered.promise;
            useAuthStore.getState().setSession(nextId
                ? { user: { id: nextId }, access_token: 'fixture-account-b-token' } : null);
            const current = useAuthStore.getState();
            release.resolve();
            await assert.rejects(request, axios.isCancel);
            assert.equal(calls, 1);
            assert.equal(useAuthStore.getState(), current);
        });
    }

    for (const retryFails of [false, true]) {
        test(`${operation.name}: 401 chỉ dùng refresh/retry chung một lần (${retryFails})`, options, async () => {
            let calls = 0;
            let refreshCalls = 0;
            const data = operation.data();
            auth.refreshSession = async () => {
                refreshCalls += 1;
                const session = { user: { id: 'account-a' }, access_token: 'fixture-refreshed-token' };
                useAuthStore.getState().setSession(session);
                return { data: { session }, error: null };
            };
            api.defaults.adapter = async (config) => {
                calls += 1;
                if (calls === 1 || retryFails) {
                    throw new axios.AxiosError('Unauthorized fixture', 'ERR_BAD_RESPONSE', config, null,
                        { status: 401, data: {}, headers: {}, config });
                }
                assert.equal(config.headers.get('Authorization'), 'Bearer fixture-refreshed-token');
                return response(config, data);
            };
            if (retryFails) {
                await assert.rejects(operation.call(), (error) => error.response?.status === 401);
                assert.equal(useAuthStore.getState().status, 'reauth_required');
            } else {
                assert.equal(await operation.call(), data);
                assert.equal(useAuthStore.getState().status, 'authenticated');
            }
            assert.equal(calls, 2);
            assert.equal(refreshCalls, 1);
        });
    }
}

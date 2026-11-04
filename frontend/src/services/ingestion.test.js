import assert from 'node:assert/strict';
import { register } from 'node:module';
import { beforeEach, test } from 'node:test';
import axios from 'axios';
import { useAuthStore } from '../features/auth/authStore.js';
import { auth } from './test-support/supabase.stub.js';

// Keep the production service/client/store; replace only Auth and HTTP transport.
register('./test-support/auth-loader.js', import.meta.url);
const {
    ingestText, ingestFile, validateIngestText, validateIngestFile,
    IngestionInputError, IngestionResponseError,
} = await import('./ingestion.js');
const { api } = await import('./api.js');
const options = { timeout: 3000 };
const sessionId = 'abcdefab-1234-1234-1234-123456789abc';
const source = '### Câu 1: Giải $3x-5=10$.\nA. 3\nB. 4\nC. 5\nD. 6\nĐáp án: C';
const makeFile = (name = 'đại số.md', content = source) => new File([content], name);
const savedQuestion = (overrides = {}) => ({
    id: 'question-a', session_id: sessionId, question_no: 3, raw_content: 'Giải $3x-5=10$.',
    options: { A: '3', B: '4', C: '5', D: '6' }, correct_key: 'C',
    solution_md: '$3x=15$, vậy $x=5$.', has_missing_answer: false,
    has_security_warning: true, ...overrides,
});
const success = (overrides = {}) => ({
    session_id: sessionId, total_questions: 1, questions: [savedQuestion()], ...overrides,
});
const response = (config, data) => ({ status: 200, data, headers: {}, config });
function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}
function httpError(config, status, data = {}) {
    return new axios.AxiosError('Fixture HTTP error', 'ERR_BAD_RESPONSE', config, null,
        { status, data, headers: {}, config });
}

beforeEach(() => {
    useAuthStore.getState().setSession({ user: { id: 'account-a' }, access_token: 'fixture-token-a' });
    const version = useAuthStore.getState().sessionVersion;
    useAuthStore.getState().setProfile({ id: 'account-a', email: 'teacher@example.test' }, version);
    auth.getSession = async () => ({ data: { session: useAuthStore.getState().session }, error: null });
    auth.refreshSession = async () => { throw new Error('Unexpected refresh'); };
    api.defaults.adapter = async () => { throw new Error('Unexpected HTTP'); };
});

test('text: đúng endpoint/Bearer/raw_text, giữ công thức và không đổi Auth/timeout', options, async () => {
    const data = success();
    const initial = useAuthStore.getState();
    api.defaults.adapter = async (config) => {
        assert.equal(config.method, 'post');
        assert.equal(api.getUri(config), `/api/sessions/${sessionId.toUpperCase()}/ingest-text`);
        assert.equal(config.headers.get('Authorization'), 'Bearer fixture-token-a');
        assert.equal(config.timeout, 15000);
        assert.deepEqual(JSON.parse(config.data), { raw_text: source });
        return response(config, data);
    };
    assert.equal(await ingestText(` ${sessionId.toUpperCase()} `, `\u0085${source}\u001f`), data);
    assert.equal(useAuthStore.getState(), initial);
    assert.equal(api.defaults.timeout, 15000);
});

test('ID có ký tự đặc biệt được encode, không trở thành query/fragment', options, async () => {
    const id = 'session?a#b';
    const data = success({ session_id: id, questions: [savedQuestion({ session_id: id })] });
    api.defaults.adapter = async (config) => {
        assert.equal(api.getUri(config), '/api/sessions/session%3Fa%23b/ingest-text');
        return response(config, data);
    };
    assert.equal(await ingestText(id, source), data);
});

test('text: biên100k Unicode codepoints sau Python strip, không JS.length hoặc normalize công thức', options, async () => {
    for (const text of ['a'.repeat(100_000), '📚'.repeat(100_000), '\ufeffx', 'e\u0301']) {
        let calls = 0;
        api.defaults.adapter = async (config) => {
            calls++;
            assert.deepEqual(JSON.parse(config.data), { raw_text: text });
            return response(config, success());
        };
        assert.equal(validateIngestText(`\u001c\u0085 ${text}\u3000`), text);
        await ingestText(sessionId, `\u001c\u0085 ${text}\u3000`);
        assert.equal(calls, 1);
    }
});

test('ID/text không hợp lệ bị chặn trước Auth/HTTP', options, async () => {
    let calls = 0;
    auth.getSession = async () => { calls++; throw new Error('Unexpected Auth'); };
    api.defaults.adapter = async () => { calls++; throw new Error('Unexpected HTTP'); };
    for (const id of [undefined, null, 4, '', ' \n ', '\ufeff', 'new', ' NEW ']) {
        await assert.rejects(ingestText(id, source), IngestionInputError);
        await assert.rejects(ingestFile(id, makeFile()), IngestionInputError);
    }
    for (const text of [undefined, null, {}, [], 4, '', '\u001c\u0085\u3000',
        'a'.repeat(100_001), '📚'.repeat(100_001), '\ufeff' + 'a'.repeat(100_000)]) {
        await assert.rejects(ingestText(sessionId, text), IngestionInputError);
    }
    assert.equal(calls, 0);
});

test('file: multipart chỉ có file, giữ tên/bytes và chuyển tiếp signal/progress', options, async () => {
    const file = makeFile();
    const controller = new AbortController();
    const events = [];
    const progress = (event) => events.push(event);
    const half = { loaded: 5, total: 10, progress: 0.5 };
    const unknown = { loaded: 10, total: undefined };
    const data = success();
    api.defaults.adapter = async (config) => {
        assert.equal(api.getUri(config), `/api/sessions/${sessionId}/ingest-file`);
        assert.equal(config.headers.get('Authorization'), 'Bearer fixture-token-a');
        assert.equal(config.signal, controller.signal);
        assert.equal(config.onUploadProgress, progress);
        assert(config.data instanceof FormData);
        assert.deepEqual([...config.data.keys()], ['file']);
        const uploaded = config.data.get('file');
        assert.equal(uploaded.name, file.name);
        assert.equal(await uploaded.text(), source);
        config.onUploadProgress(half);
        config.onUploadProgress(unknown);
        return response(config, data);
    };
    assert.equal(await ingestFile(sessionId, file, { signal: controller.signal, onUploadProgress: progress }), data);
    assert.deepEqual(events, [half, unknown]);
});

test('file: ba đuôi không phân biệt hoa/thường; đúng10MiB được gửi', options, async () => {
    for (const file of [makeFile('exam.DOCX'), makeFile('exam.TEX'), makeFile('exam.MD'),
        makeFile('limit.md', new Uint8Array(10 * 1024 * 1024))]) {
        assert.equal(validateIngestFile(file), file);
        let calls = 0;
        api.defaults.adapter = async (config) => { calls++; return response(config, success()); };
        await ingestFile(sessionId, file);
        assert.equal(calls, 1);
    }
    // Transport fixtures do not claim to be valid DOCX archives or exercise the backend parser.
});

test('file: PDF/sai đuôi/rỗng/quá10MiB và object giả bị chặn trước Auth/HTTP', options, async () => {
    let calls = 0;
    auth.getSession = async () => { calls++; throw new Error('Unexpected Auth'); };
    api.defaults.adapter = async () => { calls++; throw new Error('Unexpected HTTP'); };
    for (const file of [null, undefined, [], [makeFile()], new Blob([source]),
        { name: 'exam.md', size: 10 }, makeFile('exam.pdf'), makeFile('exam.md.exe'),
        makeFile('exam'), makeFile('exam.md '), makeFile('empty.md', ''),
        makeFile('large.md', new Uint8Array(10 * 1024 * 1024 + 1))]) {
        await assert.rejects(ingestFile(sessionId, file), IngestionInputError);
    }
    assert.equal(calls, 0);
});

test('response: nhận số câu1–20, số thứ tự không liên tiếp, không sửa cảnh báo/solution', options, async () => {
    const questions = Array.from({ length: 20 }, (_, index) => savedQuestion({
        id: `question-${index}`, question_no: index + 10,
    }));
    const data = success({ questions, total_questions: 20 });
    api.defaults.adapter = async (config) => response(config, data);
    assert.equal(await ingestText(sessionId, source), data);
    assert.equal(data.questions[0].has_security_warning, true);
    assert.equal(data.questions[0].solution_md, '$3x=15$, vậy $x=5$.');
});

const operations = [
    { name: 'text', call: (config) => ingestText(sessionId, source, config) },
    { name: 'file', call: (config) => ingestFile(sessionId, makeFile(), config) },
];

for (const operation of operations) {
    test(`${operation.name}: response sai phiên/count/shape/ID/key không thành success và cần đối chiếu`, options, async () => {
        const invalid = [null, [], { data: success() }, success({ session_id: 'other-session' }),
            success({ total_questions: '1' }), success({ total_questions: 0, questions: [] }),
            success({ total_questions: 21, questions: Array.from({ length: 21 }, (_, index) =>
                savedQuestion({ id: `question-${index}`, question_no: index + 1 })) }),
            success({ questions: undefined }),
            success({ total_questions: 2 }), success({ questions: [null] })];
        for (const override of [
            { id: '' }, { session_id: 'other-session' }, { question_no: 0 }, { question_no: 1.5 },
            { raw_content: '\u0085' }, { options: null }, { options: ['3', '4', '5', '6'] },
            { options: { A: '3', B: '4', C: '5' } },
            { options: { A: '3', B: '4', C: '5', D: '\u0085' } },
            { options: { A: '3', B: '4', C: '5', D: '6', E: '7' } },
            { correct_key: 'E' }, { correct_key: null }, { solution_md: {} },
            { has_missing_answer: true }, { has_unparsed_omml: true },
            { has_unparsed_image: true }, { is_empty_stem: true }, { has_security_warning: 'false' },
        ]) invalid.push(success({ questions: [savedQuestion(override)] }));
        invalid.push(success({ total_questions: 2, questions: [savedQuestion(), savedQuestion({ question_no: 7 })] }));
        invalid.push(success({ total_questions: 2, questions: [savedQuestion(), savedQuestion({ id: 'question-b' })] }));
        for (const data of invalid) {
            let calls = 0;
            api.defaults.adapter = async (config) => { calls++; return response(config, data); };
            await assert.rejects(operation.call(), (error) => error instanceof IngestionResponseError
                && error.code === 'ERR_INGEST_RESPONSE' && error.outcomeUncertain === true);
            assert.equal(calls, 1);
        }
    });

    test(`${operation.name}: HTTP/network/timeout giữ nguyên cause/payload, không retry/logout`, options, async () => {
        const initial = useAuthStore.getState();
        const incomplete = { detail: { message: 'Incomplete', errors: [{ question_no: 0, error_type: 'INVALID_FORMAT' }] } };
        for (const status of [400, 403, 404, 409, 422, 429, 500, 504, 'network', 'timeout']) {
            let calls = 0;
            let expected;
            api.defaults.adapter = async (config) => {
                calls++;
                expected = typeof status === 'number' ? httpError(config, status, incomplete)
                    : new axios.AxiosError('Fixture connection error',
                        status === 'timeout' ? 'ECONNABORTED' : 'ERR_NETWORK', config);
                throw expected;
            };
            await assert.rejects(operation.call(), (error) => error === expected);
            assert.equal(calls, 1);
            assert.equal(useAuthStore.getState(), initial);
        }
        for (const data of [{ detail: [{ loc: ['body', 'raw_text'], msg: 'Invalid text' }] },
            { detail: 'Other validation error' }]) {
            let expected;
            api.defaults.adapter = async (config) => { expected = httpError(config, 422, data); throw expected; };
            await assert.rejects(operation.call(), (error) => error === expected && error.response.data === data);
        }
    });

    test(`${operation.name}: signal hủy trước gửi hoặc trong request, không nhận kết quả muộn`, options, async () => {
        const before = new AbortController();
        before.abort();
        let calls = 0;
        api.defaults.adapter = async (config) => { calls++; return response(config, success()); };
        await assert.rejects(operation.call({ signal: before.signal }), axios.isCancel);
        assert.equal(calls, 0);
        const entered = deferred();
        const release = deferred();
        const during = new AbortController();
        api.defaults.adapter = async (config) => {
            calls++;
            assert.equal(config.signal, during.signal);
            entered.resolve();
            await release.promise;
            return response(config, success());
        };
        const request = operation.call({ signal: during.signal });
        await entered.promise;
        during.abort();
        release.resolve();
        await assert.rejects(request, axios.isCancel);
        assert.equal(calls, 1);
    });

    for (const nextId of ['account-b', null]) {
        test(`${operation.name}: client bỏ response A khi ${nextId ?? 'logout'}`, options, async () => {
            const entered = deferred();
            const release = deferred();
            let calls = 0;
            api.defaults.adapter = async (config) => {
                calls++; entered.resolve(); await release.promise;
                return response(config, success());
            };
            const request = operation.call();
            await entered.promise;
            useAuthStore.getState().setSession(nextId
                ? { user: { id: nextId }, access_token: 'fixture-token-b' } : null);
            const current = useAuthStore.getState();
            release.resolve();
            await assert.rejects(request, axios.isCancel);
            assert.equal(calls, 1);
            assert.equal(useAuthStore.getState(), current);
        });
    }

    for (const failsAgain of [false, true]) {
        test(`${operation.name}: chỉ refresh/retry401 chung một lần, thất bại lại=${failsAgain}`, options, async () => {
            let calls = 0;
            let refreshes = 0;
            auth.refreshSession = async () => {
                refreshes++;
                const session = { user: { id: 'account-a' }, access_token: 'fixture-refreshed-token' };
                useAuthStore.getState().setSession(session);
                return { data: { session }, error: null };
            };
            api.defaults.adapter = async (config) => {
                calls++;
                if (calls === 1 || failsAgain) throw httpError(config, 401);
                assert.equal(config.headers.get('Authorization'), 'Bearer fixture-refreshed-token');
                // Shared Auth retry must keep the original body, including a replayable file.
                if (operation.name === 'file') assert.equal(await config.data.get('file').text(), source);
                else assert.deepEqual(JSON.parse(config.data), { raw_text: source });
                return response(config, success());
            };
            if (failsAgain) {
                await assert.rejects(operation.call(), (error) => error.response?.status === 401);
                assert.equal(useAuthStore.getState().status, 'reauth_required');
            } else await operation.call();
            assert.equal(calls, 2);
            assert.equal(refreshes, 1);
        });
    }
}

import { api } from './api.js';

export const MAX_INGEST_TEXT_LENGTH = 100_000;
export const MAX_INGEST_FILE_BYTES = 10 * 1024 * 1024;
const OPTION_KEYS = ['A', 'B', 'C', 'D'];
// Python str.strip() includes NEL/control separators, but does not strip BOM.
const STRIP_CHARS = '[\\u0009-\\u000d\\u001c-\\u0020\\u0085\\u00a0\\u1680'
    + '\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]';
const EDGE_WHITESPACE = new RegExp(`^${STRIP_CHARS}+|${STRIP_CHARS}+$`, 'gu');
const strip = (text) => text.replace(EDGE_WHITESPACE, '');
const isRecord = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const hasText = (value) => typeof value === 'string' && strip(value) !== '';
const sameId = (value, expected) => typeof value === 'string'
    && value.toLowerCase() === expected.toLowerCase();

export class IngestionInputError extends Error {
    constructor(message) {
        super(message);
        this.name = 'IngestionInputError';
        this.code = 'ERR_INGEST_INPUT';
    }
}

export class IngestionResponseError extends Error {
    constructor() {
        super('Phản hồi nạp nguồn không hợp lệ. Hãy tải lại phiên để kiểm tra trước khi gửi lại.');
        this.name = 'IngestionResponseError';
        this.code = 'ERR_INGEST_RESPONSE';
        this.outcomeUncertain = true;
    }
}

function sessionPath(sessionId) {
    const id = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!id || id.toLowerCase() === 'new') {
        throw new IngestionInputError('Phiên cần nạp nguồn không hợp lệ.');
    }
    return { id, path: `/sessions/${encodeURIComponent(id)}` };
}

export function validateIngestText(rawText) {
    if (typeof rawText !== 'string') {
        throw new IngestionInputError('Nội dung đề phải là văn bản.');
    }
    const text = strip(rawText);
    if (!text || [...text].length > MAX_INGEST_TEXT_LENGTH) {
        throw new IngestionInputError('Nội dung đề phải có từ 1 đến 100.000 ký tự.');
    }
    return text;
}

export function validateIngestFile(file) {
    if (!(file instanceof Blob) || typeof file.name !== 'string') {
        throw new IngestionInputError('Vui lòng chọn một tệp đề nguồn.');
    }
    const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!['.docx', '.tex', '.md'].includes(extension)) {
        throw new IngestionInputError('Chỉ nhận DOCX, TeX hoặc MD; không hỗ trợ PDF đầu vào.');
    }
    if (file.size === 0 || file.size > MAX_INGEST_FILE_BYTES) {
        throw new IngestionInputError('Tệp phải có nội dung và không vượt quá 10MB.');
    }
    return file;
}

function isSavedQuestion(question, sessionId) {
    return isRecord(question) && hasText(question.id)
        && sameId(question.session_id, sessionId)
        && Number.isInteger(question.question_no) && question.question_no > 0
        && hasText(question.raw_content)
        && isRecord(question.options) && Object.keys(question.options).length === 4
        && OPTION_KEYS.every((key) => hasText(question.options[key]))
        && OPTION_KEYS.includes(question.correct_key)
        && (question.solution_md == null || typeof question.solution_md === 'string')
        && ['has_missing_answer', 'has_unparsed_omml', 'has_unparsed_image', 'is_empty_stem']
            .every((flag) => question[flag] === undefined || question[flag] === false)
        && (question.has_security_warning === undefined
            || typeof question.has_security_warning === 'boolean');
}

function readIngestResponse(data, sessionId) {
    // The current ingestion contract accepts 1–20 source questions per request.
    if (!isRecord(data) || !sameId(data.session_id, sessionId)
        || !Number.isInteger(data.total_questions) || data.total_questions < 1
        || data.total_questions > 20 || !Array.isArray(data.questions)
        || data.questions.length !== data.total_questions
        || !data.questions.every((question) => isSavedQuestion(question, data.session_id))
        || new Set(data.questions.map((question) => question.id.toLowerCase())).size !== data.total_questions
        || new Set(data.questions.map((question) => question.question_no)).size !== data.total_questions) {
        // A malformed success response does not prove the database was untouched.
        throw new IngestionResponseError();
    }
    return data;
}

export async function ingestText(sessionId, rawText, { signal } = {}) {
    const { id, path } = sessionPath(sessionId);
    const text = validateIngestText(rawText);
    const { data } = await api.post(`${path}/ingest-text`, { raw_text: text }, { signal });
    return readIngestResponse(data, id);
}

export async function ingestFile(sessionId, file, { signal, onUploadProgress } = {}) {
    const { id, path } = sessionPath(sessionId);
    validateIngestFile(file);
    const body = new FormData();
    body.append('file', file, file.name);
    // The browser sets the multipart boundary; upload completion is not parser completion.
    const { data } = await api.post(`${path}/ingest-file`, body, { signal, onUploadProgress });
    return readIngestResponse(data, id);
}

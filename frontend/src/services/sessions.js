import { api } from './api.js';

function isSessionItem(item) {
    return (
        item !== null &&
        typeof item === 'object' &&
        !Array.isArray(item) &&
        ['id', 'user_id', 'title', 'subject', 'status', 'created_at']
            .every((field) => typeof item[field] === 'string') &&
        item.id.trim() !== '' &&
        item.user_id.trim() !== '' &&
        item.status.trim() !== ''
    );
}

function isSessionMetadata(item) {
    return (
        isSessionItem(item) &&
        Number.isInteger(item.grade) && item.grade >= 1 && item.grade <= 12 &&
        typeof item.updated_at === 'string' && item.updated_at.trim() !== ''
    );
}

function isSessionRecord(row, sessionId) {
    return row !== null && typeof row === 'object' && !Array.isArray(row) &&
        typeof row.id === 'string' && row.id.trim() !== '' &&
        row.session_id === sessionId;
}

export async function createSession(metadata = {}, { signal } = {}) {
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
        throw new Error('Thông tin tạo phiên không hợp lệ.');
    }

    const { title, subject = 'Toán', grade = 12 } = metadata;
    const trimmedTitle = typeof title === 'string' ? title.trim() : '';
    if (!trimmedTitle || [...trimmedTitle].length > 255) {
        throw new Error('Tiêu đề phiên phải có từ 1 đến 255 ký tự.');
    }
    if (typeof subject !== 'string' || [...subject.trim()].length > 100) {
        throw new Error('Môn học phải là văn bản, tối đa 100 ký tự.');
    }
    if (!Number.isInteger(grade) || grade < 1 || grade > 12) {
        throw new Error('Khối lớp phải là số nguyên từ 1 đến 12.');
    }

    const { data } = await api.post('/sessions', {
        title: trimmedTitle,
        subject: subject.trim(),
        grade,
    }, { signal });

    if (!isSessionMetadata(data) || data.status !== 'draft') {
        throw new Error(
            'Phản hồi tạo phiên không hợp lệ. '
            + 'Hãy kiểm tra lại danh sách trước khi thử lại.',
        );
    }
    return data;
}

export async function getSessionDetail(sessionId, { signal } = {}) {
    if (
        typeof sessionId !== 'string' || !sessionId.trim() ||
        sessionId.trim().toLowerCase() === 'new'
    ) {
        throw new Error('Phiên cần đọc không hợp lệ.');
    }
    const id = sessionId.trim();
    const { data } = await api.get(`/sessions/${encodeURIComponent(id)}`, { signal });
    if (
        !isSessionMetadata(data) || data.id.toLowerCase() !== id.toLowerCase() ||
        !Array.isArray(data.source_questions) ||
        !data.source_questions.every((row) => isSessionRecord(row, data.id)) ||
        !Array.isArray(data.exam_versions) ||
        !data.exam_versions.every((row) => isSessionRecord(row, data.id))
    ) {
        throw new Error('Phản hồi chi tiết phiên không hợp lệ. Vui lòng tải lại.');
    }
    return data;
}

export async function listSessions({
    page = 1,
    pageSize = 20,
    signal,
} = {}) {
    if (
        !Number.isInteger(page) ||
        page < 1 ||
        !Number.isInteger(pageSize) ||
        pageSize < 1 ||
        pageSize > 100
    ) {
        throw new Error('Trang hoặc kích thước trang không hợp lệ.');
    }

    const { data } = await api.get('/sessions', {
        params: {
            page,
            page_size: pageSize,
        },
        signal,
    });

    if (
        !data ||
        !Array.isArray(data.items) ||
        !data.items.every(isSessionItem) ||
        !Number.isInteger(data.total) ||
        data.total < 0 ||
        data.page !== page ||
        data.page_size !== pageSize
    ) {
        throw new Error(
            'Phản hồi danh sách phiên không hợp lệ. Vui lòng thử lại.',
        );
    }

    return data;
}

export async function cloneSession(sessionId, title) {
    if (typeof sessionId !== 'string' || !sessionId.trim()) {
        throw new Error('Phiên cần nhân bản không hợp lệ.');
    }

    const sourceId = sessionId.trim();
    const newTitle = typeof title === 'string' ? title.trim() : '';

    if (!newTitle || [...newTitle].length > 255) {
        throw new Error('Tên bản sao phải có từ 1 đến 255 ký tự.');
    }

    const { data } = await api.post(
        `/sessions/${encodeURIComponent(sourceId)}/clone`,
        { new_title: newTitle },
    );

    if (
        !isSessionItem(data) ||
        data.id === sourceId ||
        data.status !== 'draft'
    ) {
        throw new Error(
            'Phản hồi nhân bản không hợp lệ. '
            + 'Hãy kiểm tra lại danh sách trước khi thử lại.',
        );
    }

    return data;
}

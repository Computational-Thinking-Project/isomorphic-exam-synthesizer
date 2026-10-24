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
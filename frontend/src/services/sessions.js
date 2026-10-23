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
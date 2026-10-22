import { api } from './api.js';

export async function getMyProfile({ signal } = {}) {
    const { data } = await api.get('/users/me', { signal });

    if (
        !data ||
        typeof data.id !== 'string' ||
        !data.id.trim() ||
        typeof data.email !== 'string' ||
        !data.email.trim()
    ) {
        throw new Error('Phản hồi hồ sơ không hợp lệ. Vui lòng thử lại.');
    }

    return data;
}
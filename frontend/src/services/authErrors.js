import {
    isAuthApiError,
    isAuthRetryableFetchError,
    isAuthSessionMissingError,
} from '@supabase/supabase-js';

const expiredSessionCodes = new Set([
    'session_not_found',
    'session_expired',
    'refresh_token_not_found',
    'refresh_token_already_used',
]);

// Dùng cho lỗi từ Supabase Auth, không suy từ HTTP status của backend.
export function classifyAuthError(error) {
    if (isAuthRetryableFetchError(error)) {
        return 'temporary';
    }

    if (isAuthSessionMissingError(error)) {
        return 'expired';
    }

    if (
        isAuthApiError(error) &&
        expiredSessionCodes.has(error.code)
    ) {
        return 'expired';
    }

    return 'unknown';
}
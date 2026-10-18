import { getSupabase } from './supabase.js';

let refreshPromise = null;

export function refreshSessionOnce() {
    if (!refreshPromise) {
        refreshPromise = Promise.resolve()
            .then(() => getSupabase().auth.refreshSession())
            .then(({ data, error }) => {
                if (error) throw error;

                if (!data.session?.access_token) {
                    throw new Error(
                        'Không thể làm mới phiên. Vui lòng đăng nhập lại.',
                    );
                }

                return data.session;
            })
            .finally(() => {
                refreshPromise = null;
            });
    }

    return refreshPromise;
}
import { getSupabase } from './supabase.js';
import { AuthSessionMissingError } from '@supabase/supabase-js';

let refreshPromise = null;

export function refreshSessionOnce() {
    if (!refreshPromise) {
        refreshPromise = Promise.resolve()
            .then(() => getSupabase().auth.refreshSession())
            .then(({ data, error }) => {
                if (error) throw error;

                if (!data.session?.access_token) {
                    const sessionError = new AuthSessionMissingError();
                    sessionError.message =
                        'Không thể làm mới phiên. Vui lòng đăng nhập lại.';
                    throw sessionError;
                }

                return data.session;
            })
            .finally(() => {
                refreshPromise = null;
            });
    }

    return refreshPromise;
}
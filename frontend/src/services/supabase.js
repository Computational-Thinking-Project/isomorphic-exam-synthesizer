import { createClient } from '@supabase/supabase-js';

let client;

export function getSupabase() {
    if (client) return client;

    const url = import.meta.env.VITE_SUPABASE_URL?.trim();
    const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();

    if (!url || !key) {
        throw new Error(
            'Thiếu cấu hình Supabase. Kiểm tra frontend/.env.local.',
        );
    }

    client = createClient(url, key, {
        auth: {
            persistSession: true,
            autoRefreshToken: true,
            detectSessionInUrl: true,
        },
    });

    return client;
}
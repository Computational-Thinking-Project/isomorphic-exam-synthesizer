import axios from 'axios';
import { getSupabase } from './supabase.js';

export const api = axios.create({
    baseURL: '/api',
    timeout: 15000,
    allowAbsoluteUrls: false,
});

api.interceptors.request.use(async (config) => {
    const { data, error } = await getSupabase().auth.getSession();

    if (error) throw error;

    // Mỗi request lấy token hiện tại, không giữ header của phiên cũ.
    config.headers.delete('Authorization');

    const accessToken = data.session?.access_token;

    if (accessToken) {
        config.headers.set('Authorization', `Bearer ${accessToken}`);
    }

    return config;
});
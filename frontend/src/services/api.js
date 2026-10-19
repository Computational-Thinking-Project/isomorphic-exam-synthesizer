import axios from 'axios';
import { getSupabase } from './supabase.js';
import { refreshSessionOnce } from './authRefresh.js';
import { useAuthStore } from '../features/auth/authStore.js';
import { classifyAuthError } from './authErrors.js';

export const api = axios.create({
    baseURL: '/api',
    timeout: 15000,
    allowAbsoluteUrls: false,
});

function assertSameAccount(config, session = useAuthStore.getState().session) {
    const state = useAuthStore.getState();
    const scope = config._authScope;

    if (
        state.status === 'reauth_required' ||
        scope.version !== state.sessionVersion ||
        scope.userId !== (state.session?.user.id ?? null) ||
        scope.userId !== (session?.user.id ?? null)
    ) {
        throw new axios.CanceledError(
            'Phiên đăng nhập đã thay đổi. Request cũ đã bị hủy.',
            config,
        );
    }
}

function requireReauthenticationForRequest(config, expectedToken) {
    assertSameAccount(config);
    const state = useAuthStore.getState();

    if ((state.session?.access_token ?? null) !== expectedToken) {
        throw new axios.CanceledError(
            'Phiên đã được cập nhật. Request cũ đã bị hủy.',
            config,
        );
    }

    state.requireReauthentication(config._authScope.version);
}

function failAuthRequest(error, config, expectedToken) {
    assertSameAccount(config);

    if (classifyAuthError(error) === 'expired') {
        requireReauthenticationForRequest(config, expectedToken);
    }

    throw error;
}

async function getCurrentSession(config) {
    assertSameAccount(config);

    const expectedToken =
        useAuthStore.getState().session?.access_token ?? null;

    const { data, error } = await getSupabase().auth.getSession()
        .catch((cause) => {
            failAuthRequest(cause, config, expectedToken);
        });

    if (error) {
        failAuthRequest(error, config, expectedToken);
    }

    assertSameAccount(config, data.session);
    return data.session;
}

api.interceptors.request.use(async (config) => {
    const state = useAuthStore.getState();

    config._authScope ??= {
        version: state.sessionVersion,
        userId: state.session?.user.id ?? null,
    };

    const session = await getCurrentSession(config);
    config.headers.delete('Authorization');
    config._authToken = session?.access_token ?? null;

    if (config._authToken) {
        config.headers.set('Authorization', `Bearer ${config._authToken}`);
    }

    return config;
});

api.interceptors.response.use(
    (response) => {
        assertSameAccount(response.config);
        return response;
    },
    async (error) => {
        const config = error.config;

        if (!config || axios.isCancel(error)) throw error;
        if (config._authScope) assertSameAccount(config);

        if (
            error.response?.status !== 401 ||
            !config._authToken
        ) {
            throw error;
        }

        if (config._authRetried) {
            requireReauthenticationForRequest(config, config._authToken);
            throw error;
        }

        config._authRetried = true;
        let session = await getCurrentSession(config);

        // Nếu request khác đã refresh, dùng phiên mới sẵn có.
        if (session.access_token === config._authToken) {
            try {
                session = await refreshSessionOnce();
            } catch (refreshError) {
                failAuthRequest(refreshError, config, session.access_token);
            }
        }

        assertSameAccount(config, session);
        return api(config);
    },
);

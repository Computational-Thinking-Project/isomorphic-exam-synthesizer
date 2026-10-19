import { create } from 'zustand';

export const useAuthStore = create((set) => ({
    status: 'checking',
    session: null,
    user: null,
    sessionVersion: 0,

    setChecking: () => {
        set((state) => ({
            status: 'checking',
            session: null,
            user: null,
            sessionVersion: state.sessionVersion + 1,
        }));
    },

    requireReauthentication: (expectedVersion) => {
        set((state) => {
            if (
                state.sessionVersion !== expectedVersion ||
                !state.session ||
                state.status === 'reauth_required'
            ) {
                return state;
            }

            return {
                status: 'reauth_required',
                user: null,
                sessionVersion: state.sessionVersion + 1,
            };
        });
    },

    setSession: (session) => {
        const validSession = Boolean(
            session &&
            typeof session.access_token === 'string' &&
            session.access_token.trim() &&
            typeof session.user?.id === 'string' &&
            session.user.id.trim(),
        );

        if (!validSession) {
            set((state) => ({
                status: 'unauthenticated',
                session: null,
                user: null,
                sessionVersion: state.sessionVersion + 1,
            }));
            return;
        }

        set((state) => {
            const sameRejectedSession =
                state.status === 'reauth_required' &&
                state.session?.user.id === session.user.id &&
                state.session.access_token === session.access_token;

            if (sameRejectedSession) return state;

            return {
                status: 'profile_pending',
                session,
                user: null,
                sessionVersion:
                    state.sessionVersion +
                    (state.session?.user.id !== session.user.id ? 1 : 0),
            };
        });
    },

    // Tạm giữ cho code mẫu cũ; chưa dùng để xác nhận profile thật.
    setUser: (user) => {
        const validUser = Boolean(
            user &&
            typeof user.id === 'string' &&
            user.id.trim(),
        );

        set((state) => ({
            status: validUser ? 'authenticated' : 'unauthenticated',
            session: null,
            user: validUser ? user : null,
            sessionVersion: state.sessionVersion + 1,
        }));
    },
}));
import { create } from 'zustand';

export const useAuthStore = create((set) => ({
    status: 'checking',
    session: null,
    user: null,

    setChecking: () => {
        set({
            status: 'checking',
            session: null,
            user: null,
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
            set({
                status: 'unauthenticated',
                session: null,
                user: null,
            });
            return;
        }

        set({
            status: 'profile_pending',
            session,
            user: null,
        });
    },

    // Tạm giữ cho màn AuthPreview; sẽ bỏ khi chuyển hẳn sang auth thật.
    setUser: (user) => {
        const validUser = Boolean(
            user &&
            typeof user.id === 'string' &&
            user.id.trim(),
        );

        set({
            status: validUser ? 'authenticated' : 'unauthenticated',
            session: null,
            user: validUser ? user : null,
        });
    },
}));
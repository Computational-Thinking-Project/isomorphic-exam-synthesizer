import { create } from 'zustand';

export const useAuthStore = create((set) => ({
    status: 'checking',
    user: null,

    setChecking: () => {
        set({ status: 'checking', user: null });
    },

    setUser: (user) => {
        if (!user || typeof user.id !== 'string' || !user.id.trim()) {
            set({ status: 'unauthenticated', user: null });
            return;
        }

        set({ status: 'authenticated', user });
    },
}));
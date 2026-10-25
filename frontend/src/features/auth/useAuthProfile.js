import { useEffect, useState } from 'react';
import { useAuthStore } from './authStore.js';
import { getMyProfile } from '../../services/profile.js';

export function useAuthProfile() {
    const status = useAuthStore((state) => state.status);
    const userId = useAuthStore((state) => state.session?.user.id);
    const version = useAuthStore((state) => state.sessionVersion);
    const setProfile = useAuthStore((state) => state.setProfile);
    const [attempt, setAttempt] = useState(0);
    const [failure, setFailure] = useState(null);

    useEffect(() => {
        if (status !== 'profile_pending' || !userId) return;

        const controller = new AbortController();
        let active = true;

        function isCurrent() {
            const state = useAuthStore.getState();

            return (
                active &&
                state.status === 'profile_pending' &&
                state.sessionVersion === version &&
                state.session?.user.id === userId
            );
        }

        getMyProfile({ signal: controller.signal })
            .then((profile) => {
                if (!isCurrent()) return;

                if (profile.id !== userId) {
                    throw new Error('Hồ sơ không khớp tài khoản.');
                }

                setProfile(profile, version);
            })
            .catch((cause) => {
                if (!isCurrent()) return;

                const httpStatus = cause?.response?.status;
                const message = httpStatus === 403
                    ? 'Tài khoản không có quyền truy cập hồ sơ.'
                    : httpStatus === 429
                        ? 'Có quá nhiều yêu cầu. Vui lòng chờ rồi thử lại.'
                        : 'Chưa thể tải hồ sơ. Vui lòng thử lại.';

                setFailure({ version, attempt, message });
            });

        return () => {
            active = false;
            controller.abort();
        };
    }, [status, userId, version, attempt, setProfile]);

    const error =
        status === 'profile_pending' &&
            failure?.version === version &&
            failure.attempt === attempt
            ? failure.message
            : '';

    return {
        isLoading: status === 'profile_pending' && !error,
        error,
        retry: () => setAttempt((current) => current + 1),
    };
}
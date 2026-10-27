import { Link, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from './authStore.js';

export default function ProtectedRoute({ profileState }) {
  const status = useAuthStore((state) => state.status);
  const user = useAuthStore((state) => state.user);
  const location = useLocation();

  if (status === 'checking') {
    return (
      <p role="status" className="p-6 text-slate-300">
        Đang kiểm tra phiên đăng nhập…
      </p>
    );
  }

  // A restored session still needs profile verification. Keep the requested URL
  // while blocking the outlet, so a reload does not detour through Login.
  if (status === 'profile_pending') {
    return (
      <section aria-label="Xác minh tài khoản" className="p-6 text-slate-300">
        {profileState?.error ? (
          <div role="alert">
            <p>{profileState.error}</p>
            <button type="button" onClick={profileState.retry}
              className="mt-3 rounded-lg border border-current px-4 py-2">
              Thử lại tải hồ sơ
            </button>
          </div>
        ) : <p role="status">Đang xác minh hồ sơ tài khoản…</p>}
        <Link to="/login" replace className="mt-4 inline-block text-sky-300 underline">
          Quay về đăng nhập
        </Link>
      </section>
    );
  }

  if (status !== 'authenticated' || !user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  return <Outlet />;
}

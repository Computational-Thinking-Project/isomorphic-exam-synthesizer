import { Link, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from './authStore.js';

export default function ProtectedRoute({ profileState }) {
  const status = useAuthStore((state) => state.status);
  const user = useAuthStore((state) => state.user);
  const location = useLocation();

  if (status === 'checking') {
    return (
      <div className="paper-ui min-h-screen bg-canvas p-6">
        <p role="status" className="text-muted">
          Đang kiểm tra phiên đăng nhập…
        </p>
      </div>
    );
  }

  // A restored session still needs profile verification. Keep the requested URL
  // while blocking the outlet, so a reload does not detour through Login.
  if (status === 'profile_pending') {
    return (
      <div className="paper-ui min-h-screen bg-canvas p-6">
        <section aria-label="Xác minh tài khoản" className="rounded-2xl border border-line bg-surface p-6 shadow-paper max-w-md">
          {profileState?.error ? (
            <div role="alert" className="text-danger">
              <p>{profileState.error}</p>
              <button type="button" onClick={profileState.retry}
                className="mt-3 rounded-lg border border-danger-border bg-danger-soft px-4 py-2 text-sm font-semibold hover:bg-danger-soft/80">
                Thử lại tải hồ sơ
              </button>
            </div>
          ) : <p role="status" className="text-muted">Đang xác minh hồ sơ tài khoản…</p>}
          <Link to="/login" replace className="mt-4 inline-block text-highlight font-semibold hover:underline">
            Quay về đăng nhập
          </Link>
        </section>
      </div>
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

import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from './authStore.js';

export default function ProtectedRoute() {
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
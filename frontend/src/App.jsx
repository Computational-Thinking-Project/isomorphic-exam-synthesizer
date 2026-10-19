import { useEffect, useState } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from 'react-router-dom';
import LoginPage from './features/auth/LoginPage.jsx';
import ProtectedRoute from './features/auth/ProtectedRoute.jsx';
import { useAuthStore } from './features/auth/authStore.js';
import DashboardRoute from './features/dashboard/DashboardRoute.jsx';
import { getSupabase } from './services/supabase.js';
import { classifyAuthError } from './services/authErrors.js';

export default function App() {
  const [authMessage, setAuthMessage] = useState(null);
  const [authAttempt, setAuthAttempt] = useState(0);
  const setChecking = useAuthStore((state) => state.setChecking);
  const setSession = useAuthStore((state) => state.setSession);

  useEffect(() => {
    let active = true;
    let subscription;
    let revision = 0;

    setChecking();
    setAuthMessage(null);

    const bootstrapVersion = useAuthStore.getState().sessionVersion;

    function canApplyBootstrap() {
      return (
        active &&
        revision === 0 &&
        useAuthStore.getState().sessionVersion === bootstrapVersion
      );
    }

    function handleFailure(cause) {
      if (!canApplyBootstrap()) return;

      const kind = classifyAuthError(cause);

      if (kind === 'expired') {
        setSession(null);
        setAuthMessage({
          kind: 'error',
          text: 'Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.',
          retry: false,
        });
        return;
      }

      // Chưa xác minh được phiên: tiếp tục chặn truy cập,
      // giữ nguyên phiên lưu trong SDK và cho phép thử lại.
      setAuthMessage({
        kind: 'error',
        text: kind === 'temporary'
          ? 'Không thể kết nối để kiểm tra phiên. Kiểm tra mạng rồi thử lại.'
          : 'Chưa thể kiểm tra phiên đăng nhập. Vui lòng thử lại.',
        retry: true,
      });
    }

    try {
      const supabase = getSupabase();

      const { data } = supabase.auth.onAuthStateChange(
        (event, nextSession) => {
          if (!active || event === 'INITIAL_SESSION') return;

          revision += 1;
          setSession(nextSession);

          setAuthMessage(
            event === 'SIGNED_OUT'
              ? {
                  kind: 'info',
                  text: 'Phiên đăng nhập đã kết thúc. Bạn có thể đăng nhập lại.',
                  retry: false,
                }
              : null,
          );
        },
      );

      subscription = data.subscription;

      supabase.auth.getSession()
        .then(({ data: sessionData, error }) => {
          if (!canApplyBootstrap()) return;

          if (error) {
            handleFailure(error);
            return;
          }

          setSession(sessionData.session);
          setAuthMessage(null);
        })
        .catch(handleFailure);
    } catch (cause) {
      handleFailure(cause);
    }

    return () => {
      active = false;
      subscription?.unsubscribe();
    };
  }, [authAttempt, setChecking, setSession]);

  return (
    <BrowserRouter>
      {authMessage && (
        <div
          role={authMessage.kind === 'error' ? 'alert' : 'status'}
          className={`p-4 ${
            authMessage.kind === 'error'
              ? 'text-rose-300'
              : 'text-slate-300'
          }`}
        >
          <p>{authMessage.text}</p>

          {authMessage.retry && (
            <button
              type="button"
              onClick={() => setAuthAttempt((attempt) => attempt + 1)}
              className="mt-2 rounded-lg border border-current px-4 py-2"
            >
              Thử lại
            </button>
          )}
        </div>
      )}

      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<DashboardRoute />} />
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
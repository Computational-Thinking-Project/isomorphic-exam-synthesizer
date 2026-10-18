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

export default function App() {
  const [authError, setAuthError] = useState('');
  const setChecking = useAuthStore((state) => state.setChecking);
  const setSession = useAuthStore((state) => state.setSession);

  useEffect(() => {
    let active = true;
    let subscription;
    let revision = 0;

    function handleFailure() {
      if (!active) return;

      setSession(null);
      setAuthError(
        'Không thể khôi phục phiên đăng nhập. Hãy tải lại để thử lại.',
      );
    }

    setChecking();
    setAuthError('');

    try {
      const supabase = getSupabase();

      const { data } = supabase.auth.onAuthStateChange(
        (event, nextSession) => {
          if (!active) return;

          if (event === 'INITIAL_SESSION' && revision > 0) return;
          if (event !== 'INITIAL_SESSION') revision += 1;

          setAuthError('');
          setSession(nextSession);
        },
      );

      subscription = data.subscription;
      const initialRevision = revision;

      supabase.auth.getSession()
        .then(({ data: sessionData, error }) => {
          if (!active || revision !== initialRevision) return;

          if (error) {
            handleFailure();
            return;
          }

          setSession(sessionData.session);
        })
        .catch(() => {
          if (revision === initialRevision) handleFailure();
        });
    } catch {
      handleFailure();
    }

    return () => {
      active = false;
      subscription?.unsubscribe();
    };
  }, [setChecking, setSession]);

  return (
    <BrowserRouter>
      {authError && (
        <div role="alert" className="p-4 text-rose-300">
          <p>{authError}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-2 rounded-lg border border-rose-300 px-4 py-2"
          >
            Tải lại
          </button>
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
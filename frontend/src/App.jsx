import { useEffect } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from 'react-router-dom';
import LoginPage from './features/auth/LoginPage.jsx';
import ProtectedRoute from './features/auth/ProtectedRoute.jsx';
import AuthPreview from './features/auth/AuthPreview.jsx';
import { useAuthStore } from './features/auth/authStore.js';
import DashboardRoute from './features/dashboard/DashboardRoute.jsx';

export default function App() {
  const setUser = useAuthStore((state) => state.setUser);

  useEffect(() => {
    // Tạm khởi động ở trạng thái chưa đăng nhập.
    // Bước tích hợp Supabase sẽ thay phần này bằng kiểm tra phiên thật.
    setUser(null);
  }, [setUser]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
              <Route path="/dashboard" element={<DashboardRoute />} />
          </Route>
        {import.meta.env.DEV && (
          <Route path="/auth-preview" element={<AuthPreview />}>
            <Route
              index
              element={<p>Chọn trạng thái để kiểm tra trang nội bộ.</p>}
            />

            <Route element={<ProtectedRoute />}>
              <Route
                path="private"
                element={
                  <p>Đã vào trang nội bộ bằng phiên mẫu.</p>
                }
              />
            </Route>
          </Route>
        )}

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
import { Outlet, useNavigate } from 'react-router-dom';
import { useAuthStore } from './authStore.js';

const buttonClass =
  'rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800 ' +
  'focus-visible:outline focus-visible:outline-2 ' +
  'focus-visible:outline-offset-4 focus-visible:outline-sky-400';

export default function AuthPreview() {
  const navigate = useNavigate();
  const status = useAuthStore((state) => state.status);
  const setChecking = useAuthStore((state) => state.setChecking);
  const setUser = useAuthStore((state) => state.setUser);

  function handleChecking() {
    setChecking();
    navigate('/auth-preview/private');
  }

  function handleMockSignIn() {
    setUser({
      id: 'mock-user-001',
      name: 'Tài khoản mẫu (DEV)',
    });
    navigate('/auth-preview/private');
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="text-2xl font-semibold">
        Kiểm tra trạng thái đăng nhập — DEV
      </h1>

      <p className="mt-3 text-slate-400">
        Dữ liệu mẫu để kiểm tra giao diện, chưa kết nối Google.
      </p>

      <p className="mt-4" role="status">
        Trạng thái: {status}
      </p>

      <div className="my-6 flex flex-wrap gap-3">
        <button
          type="button"
          className={buttonClass}
          onClick={handleChecking}
        >
          Đang kiểm tra
        </button>

        <button
          type="button"
          className={buttonClass}
          onClick={handleMockSignIn}
        >
          Dùng phiên mẫu
        </button>

        <button
          type="button"
          className={buttonClass}
          disabled={status !== 'authenticated'}
          onClick={() => navigate('/dashboard')}
        >
          Mở Dashboard
        </button>

        <button
          type="button"
          className={buttonClass}
          onClick={() => setUser(null)}
        >
          Đăng xuất mẫu
        </button>
      </div>

      <section className="rounded-xl border border-slate-700 p-6">
        <Outlet />
      </section>
    </main>
  );
}
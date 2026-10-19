import { useState } from 'react';
import { getSupabase } from '../../services/supabase.js';
import { useAuthStore } from './authStore.js';

export default function LoginPage() {
  const [notice, setNotice] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  const status = useAuthStore((state) => state.status);

  const sessionNotice =
    status === 'checking'
        ? 'Đang khôi phục phiên đăng nhập…'
        : status === 'reauth_required'
            ? 'Phiên hiện tại không thể tiếp tục sử dụng. Hãy đăng xuất rồi đăng nhập lại.'
            : status === 'profile_pending'
                ? 'Đã có phiên đăng nhập. Bước kiểm tra hồ sơ chưa được kết nối nên chưa thể mở Dashboard.'
                : '';

  async function handleGoogleSignIn() {
    if (isSubmitting || isSigningOut) return;

    setSignOutError('');

    setIsSubmitting(true);
    setNotice('Đang chuyển đến Google…');

    try {
      const { error } = await getSupabase().auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/login`,
        },
      });

      if (error) throw error;
    } catch (cause) {
      setNotice(
        cause instanceof Error
          ? cause.message
          : 'Không thể bắt đầu đăng nhập. Vui lòng thử lại.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSignOut() {
    if (isSubmitting || isSigningOut) return;

    setIsSigningOut(true);
    setSignOutError('');
    setNotice('');

    try {
      const { error } = await getSupabase().auth.signOut({
        scope: 'local',
      });

      if (error) throw error;

      setNotice('Đã đăng xuất.');
    } catch (cause) {
      setSignOutError(
        cause instanceof Error
          ? cause.message
          : 'Không thể đăng xuất. Vui lòng thử lại.',
      );
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4 py-12">
      <section
        aria-labelledby="login-title"
        className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8"
      >
        <p className="mb-3 text-sm font-medium text-sky-400">
          Isomorphic Exam Synthesizer
        </p>

        <h1 id="login-title" className="text-3xl font-semibold">
          Đăng nhập
        </h1>

        <p className="mt-3 text-slate-400">
          Không gian dành cho giáo viên quản lý và biên soạn các mã đề.
        </p>

        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={
            isSubmitting ||
            isSigningOut ||
            status === 'checking' ||
            status === 'profile_pending' ||
            status === 'reauth_required'
          }
          className="mt-8 w-full rounded-lg bg-sky-400 px-4 py-3 font-semibold text-slate-950 hover:bg-sky-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting
            ? 'Đang chuyển đến Google…'
            : 'Đăng nhập bằng Google'}
        </button>

        {(status === 'profile_pending' || status === 'reauth_required') && (
          <button
            type="button"
            onClick={handleSignOut}
            disabled={isSigningOut || isSubmitting}
            className="mt-3 w-full rounded-lg border border-slate-600 px-4 py-3 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSigningOut ? 'Đang đăng xuất…' : 'Đăng xuất'}
          </button>
        )}

        <p
          role="status"
          aria-live="polite"
          className="mt-4 text-sm text-slate-300"
        >
          {sessionNotice || notice}
        </p>

        {signOutError && (
          <p role="alert" className="mt-3 text-sm text-rose-300">
            {signOutError}
          </p>
        )}
      </section>
    </main>
  );
}
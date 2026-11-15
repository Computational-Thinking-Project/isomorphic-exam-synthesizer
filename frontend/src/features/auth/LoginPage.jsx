import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { AlertCircle, AlertTriangle, BookOpen, Loader2, LogOut, RefreshCw, ShieldCheck } from 'lucide-react';
import { getSupabase } from '../../services/supabase.js';
import { useAuthStore } from './authStore.js';

export default function LoginPage({ profileState }) {
  const [notice, setNotice] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  const status = useAuthStore((state) => state.status);
  const user = useAuthStore((state) => state.user);

  const sessionNotice =
    status === 'checking'
      ? 'Đang khôi phục phiên đăng nhập…'
      : status === 'reauth_required'
        ? 'Phiên hiện tại không thể tiếp tục sử dụng. Hãy đăng xuất rồi đăng nhập lại.'
        : profileState?.isLoading
          ? 'Đang tải hồ sơ…'
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

  if (status === 'authenticated' && user) {
    return <Navigate to="/dashboard" replace />;
  }

  const isButtonDisabled =
    isSubmitting ||
    isSigningOut ||
    status === 'checking' ||
    status === 'profile_pending' ||
    status === 'reauth_required';

  return (
    <main className="min-h-screen bg-canvas flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Paper Canvas Card */}
        <section
          aria-labelledby="login-title"
          className="rounded-2xl border border-line bg-surface p-8 sm:p-10 shadow-paper"
        >
          {/* Brand Identity Header */}
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-support-line bg-support-bg px-3 py-1 text-xs font-bold uppercase tracking-wider text-highlight">
              <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
              Exam Mirror
            </span>
            <span className="inline-flex items-center gap-1 text-xs text-muted">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
              Bảo mật
            </span>
          </div>

          <h1 id="login-title" className="mt-4 text-2xl sm:text-3xl font-bold tracking-tight text-strong">
            Đăng nhập
          </h1>

          <p className="mt-2 text-sm text-muted leading-relaxed">
            Không gian dành cho giáo viên quản lý và biên soạn các mã đề thi đẳng cấu.
          </p>

          {/* Google Sign-in Action */}
          <div className="mt-8 space-y-3">
            <button
              type="button"
              onClick={handleGoogleSignIn}
              disabled={isButtonDisabled}
              className="w-full inline-flex items-center justify-center gap-3 rounded-xl border border-zinc-300 bg-white px-4 py-3 text-sm font-semibold text-strong shadow-soft transition-all hover:bg-zinc-50 hover:border-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin text-highlight" aria-hidden="true" />
                  <span>Đang chuyển đến Google…</span>
                </>
              ) : (
                <>
                  <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                      fill="#4285F4"
                    />
                    <path
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                      fill="#34A853"
                    />
                    <path
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                      fill="#FBBC05"
                    />
                    <path
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                      fill="#EA4335"
                    />
                  </svg>
                  <span>Đăng nhập bằng Google</span>
                </>
              )}
            </button>

            {(status === 'profile_pending' || status === 'reauth_required') && (
              <button
                type="button"
                onClick={handleSignOut}
                disabled={isSigningOut || isSubmitting}
                className="w-full inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-surface px-4 py-2.5 text-xs font-semibold text-muted hover:bg-rail hover:text-strong transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:cursor-not-allowed disabled:opacity-50"
              >
                <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                {isSigningOut ? 'Đang đăng xuất…' : 'Đăng xuất tài khoản hiện tại'}
              </button>
            )}
          </div>

          {/* Feedback & Session Notices */}
          {(sessionNotice || notice) && (
            <div
              role="status"
              aria-live="polite"
              className="mt-6 flex items-start gap-2.5 rounded-xl border border-support-line bg-support-bg p-3.5 text-xs text-support-text"
            >
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-highlight mt-0.5" aria-hidden="true" />
              <p className="min-w-0 flex-1">{sessionNotice || notice}</p>
            </div>
          )}

          {profileState?.error && (
            <div
              role="alert"
              className="mt-4 rounded-xl border border-danger-border bg-danger-soft p-3.5 text-xs text-danger"
            >
              <div className="flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
                <p className="min-w-0 flex-1">{profileState.error}</p>
              </div>

              {profileState.retry && (
                <button
                  type="button"
                  onClick={profileState.retry}
                  disabled={isSubmitting || isSigningOut}
                  className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg border border-danger px-3 py-1 text-xs font-semibold text-danger hover:bg-danger/10 disabled:opacity-50"
                >
                  <RefreshCw className="h-3 w-3" aria-hidden="true" />
                  Thử lại tải hồ sơ
                </button>
              )}
            </div>
          )}

          {signOutError && (
            <div
              role="alert"
              className="mt-4 flex items-center gap-2 rounded-xl border border-danger-border bg-danger-soft p-3.5 text-xs text-danger"
            >
              <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
              <p>{signOutError}</p>
            </div>
          )}
        </section>

        {/* Footer info */}
        <p className="mt-6 text-center text-xs text-muted">
          Isomorphic Exam Synthesizer · Nhóm 04 · Thử nghiệm sư phạm
        </p>
      </div>
    </main>
  );
}

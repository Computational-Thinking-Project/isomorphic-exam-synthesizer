import { useState } from 'react';
import { useAuthStore } from '../auth/authStore.js';
import DashboardPage from './DashboardPage.jsx';
import { listDashboardSessions } from './dashboardMock.js';
import { getSupabase } from '../../services/supabase.js';
import UserAvatar from '../auth/UserAvatar.jsx';

export default function DashboardRoute() {
  const [notice, setNotice] = useState('');
  const user = useAuthStore((state) => state.user);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  const session = useAuthStore((state) => state.session);
  const sessionVersion = useAuthStore((state) => state.sessionVersion);

  const displayName = user?.name?.trim() || user?.email || 'Tài khoản';

  const metadata =
    user?.id && session?.user?.id === user.id
      ? session.user.user_metadata
      : null;

  const avatarUrl = [metadata?.avatar_url, metadata?.picture].find(
    (value) =>
      typeof value === 'string' &&
      value.trim().startsWith('https://'),
  )?.trim() || '';

  async function handleSignOut() {
    if (isSigningOut) return;

    setIsSigningOut(true);
    setSignOutError('');
    setNotice('');

    try {
      const { error } = await getSupabase().auth.signOut({
        scope: 'local',
      });

      if (error) throw error;
    } catch {
      setSignOutError('Không thể đăng xuất. Vui lòng thử lại.');
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <>
      <aside className="mx-auto max-w-6xl border-b border-slate-700 px-4 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <UserAvatar
              key={`${user?.id}:${sessionVersion}:${avatarUrl}`}
              src={avatarUrl}
              name={displayName}
            />

            <p className="min-w-0 break-words font-medium">
              {displayName}
            </p>
          </div>

          <p className="text-sm text-amber-300">
            Dashboard đang dùng dữ liệu mẫu, chưa kết nối API.
          </p>

          <button
            type="button"
            onClick={handleSignOut}
            disabled={isSigningOut}
            className="rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800 disabled:opacity-60"
          >
            {isSigningOut ? 'Đang đăng xuất…' : 'Đăng xuất'}
          </button>
        </div>

        {signOutError && (
          <p role="alert" className="mt-3 text-sm text-rose-300">
            {signOutError}
          </p>
        )}

        <p role="status" className="mt-3 break-words text-sm text-slate-300">
          {notice}
        </p>
      </aside>

      <DashboardPage
        loadSessions={listDashboardSessions}
        onCreate={() => {
          setNotice('Đã nhận thao tác Tạo đề mới; chưa nối màn nhập nguồn.');
        }}
        onOpen={(session) => {
          setNotice(`Đã chọn mở: ${session.title} (${session.id}).`);
        }}
        onClone={(session) => {
          setNotice(`Đã chọn nhân bản: ${session.title}; đang chờ Clone Modal.`);
        }}
      />
    </>
  );
}

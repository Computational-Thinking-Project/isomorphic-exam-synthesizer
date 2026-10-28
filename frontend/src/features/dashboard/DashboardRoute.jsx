import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../auth/authStore.js';
import DashboardPage from './DashboardPage.jsx';
import { getSessionDetail, listSessions } from '../../services/sessions.js';
import { createSessionOpener } from './sessionDestination.js';
import CloneSessionModal from './CloneSessionModal.jsx';
import { cloneSessionForDashboard } from './cloneSessionForDashboard.js';
import { getSupabase } from '../../services/supabase.js';
import UserAvatar from '../auth/UserAvatar.jsx';

export default function DashboardRoute() {
  const accountKey = useAuthStore(
    (state) => `${state.user?.id ?? ''}:${state.sessionVersion}`,
  );

  return <DashboardContent key={accountKey} accountKey={accountKey} />;
}

function DashboardContent({ accountKey }) {
  const navigate = useNavigate();
  const [notice, setNotice] = useState('');
  const user = useAuthStore((state) => state.user);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  const session = useAuthStore((state) => state.session);
  const sessionVersion = useAuthStore((state) => state.sessionVersion);
  const [pageInfo, setPageInfo] = useState(null);
  const [page, setPage] = useState(1);
  const [cloningSession, setCloningSession] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [opener] = useState(() => createSessionOpener({
    load: getSessionDetail,
    navigate,
    isCurrent: () => {
      const auth = useAuthStore.getState();
      return auth.status === 'authenticated'
        && `${auth.user?.id ?? ''}:${auth.sessionVersion}` === accountKey;
    },
  }));
  const opening = useSyncExternalStore(opener.subscribe, opener.getSnapshot, opener.getSnapshot);
  useEffect(() => () => opener.cancel(), [opener]);

  const totalPages = pageInfo
    ? Math.max(1, Math.ceil(pageInfo.total / pageInfo.pageSize))
    : 1;

  const isPageReady = pageInfo?.page === page;

  const loadSessions = useCallback(async ({ signal } = {}) => {
    setPageInfo(null);

    try {
      const result = await listSessions({
        page,
        pageSize: 20,
        signal,
      });

      signal?.throwIfAborted();

      const lastPage = Math.max(
        1,
        Math.ceil(result.total / result.page_size),
      );

      if (page > lastPage) {
        setPage(lastPage);
        return [];
      }

      setPageInfo({
        total: result.total,
        page: result.page,
        pageSize: result.page_size,
      });

      return result.items;
    } catch (cause) {
      if (signal?.aborted) throw cause;

      const messages = {
        403: 'Bạn không có quyền tải danh sách phiên đề.',
        429: 'Bạn thao tác quá nhanh. Hãy chờ một chút rồi thử lại.',
      };

      throw new Error(
        messages[cause?.response?.status]
        ?? 'Không tải được danh sách phiên đề. Vui lòng thử lại.',
        { cause },
      );
    }
  }, [page]);

  function handleCloneSuccess(newSession) {
    setCloningSession(null);
    setPageInfo(null);
    setPage(1);
    setRefreshKey((value) => value + 1);
    setNotice(`Đã nhân bản thành công: ${newSession.title}.`);
  }

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

    opener.cancel();
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
        {opening.phase === 'loading' && (
          <div className="mt-3 flex items-center gap-3">
            <p role="status">Đang mở phiên…</p>
            <button type="button" onClick={opener.cancel} className="text-sky-300 underline">
              Hủy mở phiên
            </button>
          </div>
        )}
        {opening.notice && <p role="status" className="mt-3 text-slate-300">{opening.notice}</p>}
        {opening.error && (
          <div className="mt-3">
            <p role="alert" className="text-rose-300">{opening.error}</p>
            <button type="button" onClick={() => void opener.open(opening.sessionId)}
              className="mt-2 text-sky-300 underline">
              Thử mở lại
            </button>
          </div>
        )}
      </aside>

      <DashboardPage
        key={`${page}:${refreshKey}`}
        loadSessions={loadSessions}
        openingSessionId={opening.phase === 'loading' ? opening.sessionId : null}
        onCreate={() => {
          opener.cancel();
          navigate('/session/new/stage1');
        }}
        onOpen={(session) => {
          setNotice('');
          void opener.open(session.id);
        }}
        onClone={(selectedSession) => {
          opener.cancel();
          setNotice('');
          setCloningSession(selectedSession);
        }}
      />

      <CloneSessionModal
        isOpen={Boolean(cloningSession)}
        session={cloningSession}
        onClose={() => setCloningSession(null)}
        onSuccess={handleCloneSuccess}
        cloneFn={cloneSessionForDashboard}
      />

      <nav
        aria-label="Phân trang phiên đề"
        className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 pb-6"
      >
        <button
          type="button"
          disabled={!isPageReady || page <= 1}
          onClick={() => { opener.cancel(); setPage((value) => value - 1); }}
          className="rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Trước
        </button>

        <p role="status" className="text-sm text-slate-400">
          {isPageReady
            ? `Trang ${page} / ${totalPages} · Tổng ${pageInfo.total} phiên`
            : `Trang ${page}`}
        </p>

        <button
          type="button"
          disabled={!isPageReady || page >= totalPages}
          onClick={() => { opener.cancel(); setPage((value) => value + 1); }}
          className="rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Sau
        </button>
      </nav>
    </>
  );
}

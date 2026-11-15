import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { stage1Path } from '../../sessionPaths.js';
import { useAuthStore } from '../auth/authStore.js';
import DashboardPage from './DashboardPage.jsx';
import { getSessionDetail, listSessions } from '../../services/sessions.js';
import { createSessionOpener } from './sessionDestination.js';
import CloneSessionModal from './CloneSessionModal.jsx';
import CreateSessionModal from './CreateSessionModal.jsx';
import { cloneSessionForDashboard } from './cloneSessionForDashboard.js';
import { getSupabase } from '../../services/supabase.js';
import UserAvatar from '../auth/UserAvatar.jsx';
import { ChevronLeft, ChevronRight, Loader2, LogOut } from 'lucide-react';

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
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
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
      <aside className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur-sm shadow-soft">
        <div className="mx-auto max-w-6xl px-4 py-3 sm:py-3.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <UserAvatar
                key={`${user?.id}:${sessionVersion}:${avatarUrl}`}
                src={avatarUrl}
                name={displayName}
              />

              <div className="min-w-0">
                <p className="truncate text-sm font-bold text-strong">
                  {displayName}
                </p>
                <p className="text-[11px] text-muted flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Đang hoạt động
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={handleSignOut}
              disabled={isSigningOut}
              className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-3.5 py-1.5 text-xs font-semibold text-strong hover:bg-rail transition-all disabled:opacity-50"
            >
              <LogOut className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
              <span>{isSigningOut ? 'Đang đăng xuất…' : 'Đăng xuất'}</span>
            </button>
          </div>

          {signOutError && (
            <p role="alert" className="mt-2.5 rounded-lg border border-danger-border bg-danger-soft p-2.5 text-xs text-danger">
              {signOutError}
            </p>
          )}

          {notice && (
            <p role="status" className="mt-2.5 break-words rounded-lg border border-support-line bg-support-bg p-2.5 text-xs text-support-text">
              {notice}
            </p>
          )}

          {opening.phase === 'loading' && (
            <div className="mt-2.5 flex items-center gap-3 rounded-lg border border-support-line bg-support-bg p-2.5 text-xs text-support-text">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-highlight" aria-hidden="true" />
              <p role="status">Đang mở phiên…</p>
              <button type="button" onClick={opener.cancel} className="font-semibold text-highlight underline hover:text-[#253b57]">
                Hủy mở phiên
              </button>
            </div>
          )}

          {opening.notice && (
            <p role="status" className="mt-2.5 rounded-lg border border-support-line bg-support-bg p-2.5 text-xs text-support-text">
              {opening.notice}
            </p>
          )}

          {opening.error && (
            <div className="mt-2.5 rounded-lg border border-danger-border bg-danger-soft p-2.5 text-xs text-danger">
              <p role="alert">{opening.error}</p>
              <button
                type="button"
                onClick={() => void opener.open(opening.sessionId)}
                className="mt-1 font-semibold text-highlight underline"
              >
                Thử mở lại
              </button>
            </div>
          )}
        </div>
      </aside>

      <DashboardPage
        key={`${page}:${refreshKey}`}
        loadSessions={loadSessions}
        openingSessionId={opening.phase === 'loading' ? opening.sessionId : null}
        onCreate={() => {
          opener.cancel();
          setIsCreateModalOpen(true);
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

      <CreateSessionModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreated={(newId) => {
          setIsCreateModalOpen(false);
          navigate(stage1Path(newId));
        }}
        accountKey={accountKey}
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
        className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 pt-4 pb-12"
      >
        <button
          type="button"
          disabled={!isPageReady || page <= 1}
          onClick={() => { opener.cancel(); setPage((value) => value - 1); }}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-2 text-xs font-semibold text-strong shadow-soft transition-all hover:bg-rail disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Trước</span>
        </button>

        <p role="status" className="text-xs font-medium text-muted">
          {isPageReady
            ? `Trang ${page} / ${totalPages} · Tổng ${pageInfo.total} phiên`
            : `Trang ${page}`}
        </p>

        <button
          type="button"
          disabled={!isPageReady || page >= totalPages}
          onClick={() => { opener.cancel(); setPage((value) => value - 1); }}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-2 text-xs font-semibold text-strong shadow-soft transition-all hover:bg-rail disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span>Sau</span>
          <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </nav>
    </>
  );
}

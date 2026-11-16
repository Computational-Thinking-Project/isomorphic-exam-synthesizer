import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { BookOpen, ChevronLeft, GraduationCap, Loader2, Plus, Sparkles } from 'lucide-react';
import { stage1Path, stage2Path } from '../../sessionPaths.js';
import { useAuthStore } from '../auth/authStore.js';
import { createSession, getSessionDetail } from '../../services/sessions.js';
import { sessionDestination } from '../dashboard/sessionDestination.js';
import { createConfirmationIntentStore } from './confirmationIntent.js';
import { createSessionEntryController } from './sessionEntry.js';
import Stage1SourcePanel from './Stage1SourcePanel.jsx';

const buttonClass =
  'inline-flex items-center justify-center gap-2 rounded-xl bg-highlight px-6 py-2.5 text-sm font-semibold text-white ' +
  'shadow-sm hover:bg-[#253b57] focus-visible:outline-none focus-visible:ring-2 ' +
  'focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all';

const inputClass =
  'mt-1.5 w-full rounded-xl border border-zinc-300 bg-white px-3.5 py-2.5 text-sm text-strong ' +
  'placeholder-muted focus:border-highlight focus:outline-none focus:ring-2 ' +
  'focus:ring-highlight/20 disabled:opacity-50 transition-all';

const QUICK_SUBJECTS = ['Toán', 'Vật lý', 'Hóa học', 'Sinh học', 'Tiếng Anh'];
const QUICK_GRADES = [10, 11, 12];

export default function Stage1Route() {
  const { sessionId } = useParams();
  const accountKey = useAuthStore(
    (state) => `${state.user?.id ?? ''}:${state.sessionVersion}`,
  );
  return (
    <SessionEntry
      key={`${accountKey}:${sessionId}`}
      sessionId={sessionId}
      accountKey={accountKey}
    />
  );
}

function SessionEntry({ sessionId, accountKey }) {
  const navigate = useNavigate();
  const isNew = sessionId === 'new';

  const isCurrent = useCallback(() => {
    const auth = useAuthStore.getState();
    return (
      auth.status === 'authenticated' &&
      `${auth.user?.id ?? ''}:${auth.sessionVersion}` === accountKey
    );
  }, [accountKey]);

  const openConfirmed = useCallback(
    (detail) => {
      if (!detail || !isCurrent() || detail.id.toLowerCase() !== sessionId?.toLowerCase()) return;
      const { path } = sessionDestination(detail);
      if (path !== stage2Path(detail.id)) return;
      const accountId = useAuthStore.getState().session?.user.id;
      try {
        createConfirmationIntentStore(accountId, detail.id).clear();
      } catch {
        /* the server already confirmed */
      }
      navigate(path, { replace: true });
    },
    [isCurrent, navigate, sessionId],
  );

  const [metadata, setMetadata] = useState({
    title: '',
    subject: 'Toán',
    grade: 12,
  });

  const [controller] = useState(() =>
    createSessionEntryController({
      create: createSession,
      load: getSessionDetail,
      isCurrent,
      onCreated: (id) => navigate(stage1Path(id), { replace: true }),
    }),
  );

  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );

  useEffect(() => {
    if (!isNew) void controller.load(sessionId);
    return () => controller.cancel();
  }, [controller, isNew, sessionId]);

  useEffect(() => {
    openConfirmed(state.detail);
  }, [openConfirmed, state.detail]);

  const creating = state.phase === 'creating' || state.phase === 'created';
  const update = (field, value) =>
    setMetadata((previous) => ({ ...previous, [field]: value }));

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col">
      <main
        className={
          isNew
            ? 'min-h-screen flex flex-col items-center justify-center px-4 py-12'
            : 'mx-auto flex h-dvh min-h-[42rem] max-w-7xl flex-1 flex-col overflow-hidden px-4 py-4 sm:px-6 w-full'
        }
      >
      {isNew ? (
        <div className="w-full max-w-xl">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-highlight hover:text-[#253b57] transition-colors mb-4"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            <span>Quay về Dashboard</span>
          </Link>

          <section
            aria-labelledby="create-title"
            className="rounded-2xl border border-line bg-surface p-8 sm:p-10 shadow-paper"
          >
            <div className="flex items-center gap-2 mb-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-support-bg text-highlight border border-support-line">
                <Sparkles className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="text-xs font-bold uppercase tracking-wider text-highlight">
                Khởi tạo phiên mới
              </span>
            </div>

            <h1 id="create-title" className="text-2xl sm:text-3xl font-bold tracking-tight text-strong">
              Tạo phiên đề mới
            </h1>

            <p className="mt-2 text-sm text-muted leading-relaxed">
              Nhập thông tin để tạo phiên. Bước này chưa tải lên hoặc xử lý nguồn đề.
            </p>

            <form
              className="mt-6 space-y-5"
              onSubmit={(event) => {
                event.preventDefault();
                void controller.submit(metadata);
              }}
            >
              <fieldset
                disabled={creating || state.createUncertain}
                className="space-y-5"
              >
                <div>
                  <label
                    htmlFor="session-title"
                    className="block text-sm font-semibold text-strong mb-1"
                  >
                    Tên phiên <span className="text-danger">*</span>
                  </label>
                  <input
                    id="session-title"
                    value={metadata.title}
                    required
                    onChange={(event) => update('title', event.target.value)}
                    placeholder="Ví dụ: Đề thi Giữa kỳ I - Khối 12..."
                    className={inputClass}
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label
                      htmlFor="session-subject"
                      className="text-sm font-semibold text-strong inline-flex items-center gap-1.5"
                    >
                      <BookOpen className="h-3.5 w-3.5 text-highlight" aria-hidden="true" />
                      Môn học
                    </label>
                    <span className="text-xs text-muted">Gợi ý nhanh</span>
                  </div>

                  <input
                    id="session-subject"
                    value={metadata.subject}
                    onChange={(event) => update('subject', event.target.value)}
                    className={inputClass}
                  />

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {QUICK_SUBJECTS.map((sub) => (
                      <button
                        key={sub}
                        type="button"
                        onClick={() => update('subject', sub)}
                        className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                          metadata.subject === sub
                            ? 'bg-highlight text-white'
                            : 'bg-support-bg text-support-text border border-support-line hover:bg-zinc-200'
                        }`}
                      >
                        {sub}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label
                    htmlFor="session-grade"
                    className="block text-sm font-semibold text-strong inline-flex items-center gap-1.5 mb-1"
                  >
                    <GraduationCap className="h-3.5 w-3.5 text-highlight" aria-hidden="true" />
                    Khối lớp <span className="text-danger">*</span>
                  </label>

                  <div className="grid grid-cols-3 gap-2 mt-1 mb-2">
                    {QUICK_GRADES.map((grade) => (
                      <button
                        key={grade}
                        type="button"
                        onClick={() => update('grade', grade)}
                        className={`rounded-xl border py-2 text-center text-sm font-semibold transition-all ${
                          metadata.grade === grade
                            ? 'border-highlight bg-support-bg text-highlight ring-1 ring-highlight shadow-sm'
                            : 'border-zinc-200 bg-white text-muted hover:border-zinc-300 hover:text-strong'
                        }`}
                      >
                        Lớp {grade}
                      </button>
                    ))}
                  </div>

                  <input
                    id="session-grade"
                    type="number"
                    min="1"
                    max="12"
                    step="1"
                    required
                    value={metadata.grade}
                    onChange={(event) =>
                      update(
                        'grade',
                        event.target.value === '' ? '' : Number(event.target.value),
                      )
                    }
                    className={inputClass}
                  />
                </div>

                <div className="pt-2">
                  <button type="submit" className={buttonClass}>
                    {creating ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                        <span>Đang tạo phiên…</span>
                      </>
                    ) : (
                      <>
                        <Plus className="h-4 w-4" aria-hidden="true" />
                        <span>Tạo phiên</span>
                      </>
                    )}
                  </button>
                </div>
              </fieldset>

              {creating && (
                <p role="status" className="text-xs text-muted flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-highlight" aria-hidden="true" />
                  <span>Đang lưu thông tin phiên…</span>
                </p>
              )}
            </form>
          </section>
        </div>
      ) : (
        <section
          className="mt-1 flex min-h-0 flex-1 flex-col"
          aria-label="Thông tin phiên"
        >
          {/* Top Session Breadcrumb Bar */}
          <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-line pb-3 mb-2">
            <div className="flex items-center gap-2">
              <Link
                to="/dashboard"
                className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold text-highlight hover:bg-support-bg transition-colors"
              >
                <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Dashboard</span>
              </Link>
              <span className="text-line">/</span>
              <span className="text-xs font-semibold text-strong">
                {state.detail ? state.detail.title : 'Đang tải…'}
              </span>
            </div>

            {state.detail && (
              <div className="flex items-center gap-2 text-xs text-muted">
                <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 text-xs font-medium text-highlight">
                  <BookOpen className="h-3 w-3" aria-hidden="true" />
                  {state.detail.subject || 'Chưa ghi môn'}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 text-xs font-medium text-highlight">
                  <GraduationCap className="h-3 w-3" aria-hidden="true" />
                  Khối {state.detail.grade}
                </span>
              </div>
            )}
          </header>

          {(state.phase === 'idle' || state.phase === 'loading') && (
            <div className="flex h-40 items-center justify-center gap-2 text-xs text-muted">
              <Loader2 className="h-4 w-4 animate-spin text-highlight" aria-hidden="true" />
              <p role="status">Đang tải phiên…</p>
            </div>
          )}

          {state.detail && (
            <>
              {state.detail.status === 'draft' ||
              state.detail.status === 'blueprinted' ? (
                <Stage1SourcePanel
                  detail={state.detail}
                  isCurrent={isCurrent}
                  onConfirmed={openConfirmed}
                />
              ) : (
                <Stage1NonDraftStatus detail={state.detail} />
              )}
            </>
          )}

          {state.phase === 'error' && (
            <div className="mt-4">
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-2 text-xs font-semibold text-strong hover:bg-rail"
                onClick={() => void controller.load(sessionId)}
              >
                Thử tải lại
              </button>
            </div>
          )}
        </section>
      )}

      {state.error && (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-danger-border bg-danger-soft p-3 text-xs text-danger"
        >
          {state.error}
        </div>
      )}
    </main>
  </div>
);
}

function Stage1NonDraftStatus({ detail }) {
  const destination = sessionDestination(detail);
  const isLocked = ['approved', 'exported'].includes(detail.status);
  const linkLabel = isLocked ? 'Mở màn hình Xuất bản' : 'Đi tới bước hiện tại';

  return (
    <div role="status" className="mt-4 space-y-3 rounded-xl border border-slate-700 bg-slate-900/60 p-4 text-slate-200">
      <p>
        {isLocked
          ? 'Phiên không còn ở trạng thái nháp. Đề thi đã được phê duyệt và khóa chỉnh sửa đề nguồn (HTTP 423).'
          : 'Phiên không còn ở trạng thái nháp. Bạn có thể quay về Dashboard hoặc chuyển tới bước tiếp theo của phiên.'}
      </p>
      {destination.path && (
        <Link to={destination.path} className="inline-block text-sky-300 underline">
          {linkLabel}
        </Link>
      )}
    </div>
  );
}

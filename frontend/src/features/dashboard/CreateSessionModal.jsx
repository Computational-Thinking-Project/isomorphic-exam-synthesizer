import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { BookOpen, GraduationCap, Loader2, Plus, Sparkles, X } from 'lucide-react';
import { createSession } from '../../services/sessions.js';
import { createSessionEntryController } from '../stage1-ingestion/sessionEntry.js';
import { useAuthStore } from '../auth/authStore.js';

const QUICK_SUBJECTS = ['Toán', 'Vật lý', 'Hóa học', 'Sinh học', 'Tiếng Anh'];
const QUICK_GRADES = [10, 11, 12];

export default function CreateSessionModal({
  isOpen,
  onClose,
  onCreated,
  onCheckSessions,
  accountKey,
}) {
  const [metadata, setMetadata] = useState({
    title: '',
    subject: 'Toán',
    grade: 12,
  });

  const isCurrent = useCallback(() => {
    const auth = useAuthStore.getState();
    return (
      auth.status === 'authenticated' &&
      `${auth.user?.id ?? ''}:${auth.sessionVersion}` === accountKey
    );
  }, [accountKey]);

  const [controller] = useState(() =>
    createSessionEntryController({
      create: createSession,
      load: () => Promise.resolve(null),
      isCurrent,
      onCreated: (newId) => {
        if (onCreated) onCreated(newId);
      },
    }),
  );

  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );

  const inputRef = useRef(null);
  const modalBoxRef = useRef(null);
  const creating = state.phase === 'creating' || state.phase === 'created';

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setMetadata({ title: '', subject: 'Toán', grade: 12 });
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
      return () => {
        clearTimeout(timer);
        controller.cancel();
      };
    }
    controller.cancel();
  }, [controller, isOpen]);

  // Handle ESC key and focus trapping
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        if (!creating) {
          event.preventDefault();
          onClose();
        }
        return;
      }

      if (event.key === 'Tab' && modalBoxRef.current) {
        const focusable = modalBoxRef.current.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [creating, isOpen, onClose]);

  if (!isOpen) return null;

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget && !creating) {
      onClose();
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    void controller.submit(metadata);
  }

  const update = (field, value) =>
    setMetadata((prev) => ({ ...prev, [field]: value }));

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/60 p-4 backdrop-blur-sm"
      onClick={handleBackdropClick}
    >
      <div
        ref={modalBoxRef}
        className="w-full max-w-lg rounded-2xl border border-line bg-surface p-6 sm:p-8 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3 mb-5">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-support-bg text-highlight border border-support-line">
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            </span>
            <div>
              <h2 id="create-modal-title" className="text-xl font-bold text-strong">
                Tạo phiên đề thi mới
              </h2>
              <p className="text-xs text-muted">
                Khởi tạo phiên làm việc để nạp nguồn và bóc tách ma trận đề.
              </p>
            </div>
          </div>

          <button
            type="button"
            disabled={creating}
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-rail hover:text-strong transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:opacity-50"
            aria-label="Đóng hộp thoại"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {state.error && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-danger-border bg-danger-soft p-3.5 text-xs text-danger"
          >
            <p>{state.error}</p>

            {state.createUncertain && (
              <button
                type="button"
                onClick={onCheckSessions}
                className="mt-3 rounded-lg border border-danger px-3 py-2 font-semibold hover:bg-danger/10 transition-colors"
              >
                Kiểm tra danh sách phiên
              </button>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Tên phiên */}
          <div>
            <label
              htmlFor="create-session-title"
              className="block text-sm font-semibold text-strong mb-1.5"
            >
              Tên phiên đề thi <span className="text-danger">*</span>
            </label>
            <input
              ref={inputRef}
              id="create-session-title"
              type="text"
              required
              disabled={creating}
              value={metadata.title}
              onChange={(e) => update('title', e.target.value)}
              placeholder="Ví dụ: Đề kiểm tra Giữa kỳ I Toán 12..."
              className="w-full rounded-xl border border-zinc-300 bg-white px-3.5 py-2.5 text-sm text-strong placeholder-muted focus:border-highlight focus:outline-none focus:ring-2 focus:ring-highlight/20 transition-all disabled:opacity-50"
            />
          </div>

          {/* Môn học */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label
                htmlFor="create-session-subject"
                className="text-sm font-semibold text-strong inline-flex items-center gap-1.5"
              >
                <BookOpen className="h-3.5 w-3.5 text-highlight" aria-hidden="true" />
                Môn học
              </label>
              <span className="text-xs text-muted">Gợi ý nhanh</span>
            </div>

            <input
              id="create-session-subject"
              type="text"
              disabled={creating}
              value={metadata.subject}
              onChange={(e) => update('subject', e.target.value)}
              className="w-full rounded-xl border border-zinc-300 bg-white px-3.5 py-2.5 text-sm text-strong focus:border-highlight focus:outline-none focus:ring-2 focus:ring-highlight/20 transition-all disabled:opacity-50"
            />

            <div className="mt-2 flex flex-wrap gap-1.5">
              {QUICK_SUBJECTS.map((sub) => (
                <button
                  key={sub}
                  type="button"
                  disabled={creating}
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

          {/* Khối lớp */}
          <div>
            <label className="text-sm font-semibold text-strong inline-flex items-center gap-1.5 mb-1.5">
              <GraduationCap className="h-3.5 w-3.5 text-highlight" aria-hidden="true" />
              Khối lớp
            </label>

            <div className="grid grid-cols-3 gap-2">
              {QUICK_GRADES.map((grade) => (
                <button
                  key={grade}
                  type="button"
                  disabled={creating}
                  onClick={() => update('grade', grade)}
                  className={`rounded-xl border py-2 text-center text-sm font-semibold transition-all ${
                    metadata.grade === grade
                      ? 'border-highlight bg-support-bg text-highlight shadow-sm ring-1 ring-highlight'
                      : 'border-zinc-200 bg-white text-muted hover:border-zinc-300 hover:text-strong'
                  }`}
                >
                  Lớp {grade}
                </button>
              ))}
            </div>
          </div>

          <footer className="mt-6 flex flex-wrap justify-end gap-3 pt-2 border-t border-line">
            <button
              type="button"
              disabled={creating}
              onClick={onClose}
              className="rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-medium text-strong hover:bg-rail focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:cursor-not-allowed disabled:opacity-50 transition-all"
            >
              Hủy
            </button>

            <button
              type="submit"
              disabled={creating || state.createUncertain || !metadata.title.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-highlight px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#253b57] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all"
            >
              {creating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Đang khởi tạo…
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  Tạo phiên ngay
                </>
              )}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

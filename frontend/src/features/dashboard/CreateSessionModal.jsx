import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Loader2, Plus, X } from 'lucide-react';
import { createSession } from '../../services/sessions.js';
import { createSessionEntryController } from '../stage1-ingestion/sessionEntry.js';
import { useAuthStore } from '../auth/authStore.js';

import SessionMetadataFields from '../stage1-ingestion/SessionMetadataFields.jsx';

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
      const trigger = document.activeElement;
      setMetadata({ title: '', subject: 'Toán', grade: 12 });
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
      return () => {
        clearTimeout(timer);
        controller.cancel();
        if (trigger?.isConnected) trigger.focus();
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
        if (focusable.length === 0) {
          event.preventDefault();
          modalBoxRef.current.focus();
          return;
        }

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
        tabIndex={-1}
        className="max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-2xl border border-line bg-surface p-6 sm:p-8 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3 mb-5">
          <div className="flex items-center gap-2">
            <div>
              <h2 id="create-modal-title" className="text-xl font-bold text-strong">
                Tạo bộ đề mới
              </h2>
              <p className="text-xs text-muted">
                Đặt tên bộ đề. Bạn sẽ thêm đề gốc ở bước tiếp theo.
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
          <SessionMetadataFields
            metadata={metadata}
            onChange={update}
            disabled={creating || state.createUncertain}
            titleRef={inputRef}
          />

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
                  Tạo bộ đề
                </>
              )}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

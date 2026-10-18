import { useEffect, useRef, useState } from 'react';
import { mockCloneSession } from '../../services/mocks/cloneMock.js';

const primaryButtonClass =
  'rounded-lg bg-sky-400 px-4 py-2 font-medium text-slate-950 ' +
  'hover:bg-sky-300 focus-visible:outline focus-visible:outline-2 ' +
  'focus-visible:outline-offset-4 focus-visible:outline-sky-400 ' +
  'disabled:cursor-not-allowed disabled:opacity-50 flex items-center justify-center gap-2';

const secondaryButtonClass =
  'rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 ' +
  'hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 ' +
  'focus-visible:outline-offset-4 focus-visible:outline-sky-400 ' +
  'disabled:cursor-not-allowed disabled:opacity-50';

/**
 * Modal nhân bản phiên làm việc (CloneSessionModal — TASK-103b).
 *
 * @param {Object} props
 * @param {boolean} props.isOpen - Cờ hiển thị modal
 * @param {Object|null} props.session - Đối tượng phiên cần nhân bản ({ id, title, ... })
 * @param {Function} props.onClose - Callback khi đóng/hủy modal
 * @param {Function} props.onSuccess - Callback khi nhân bản thành công: onSuccess(newSession)
 * @param {Function} [props.cloneFn=mockCloneSession] - Hàm thực hiện clone (hỗ trợ DI/mock/real API)
 */
export default function CloneSessionModal({
  isOpen,
  session,
  onClose,
  onSuccess,
  cloneFn = mockCloneSession,
}) {
  const [title, setTitle] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const inputRef = useRef(null);

  // Khởi tạo tiêu đề gợi ý và reset lỗi mỗi khi mở modal với phiên mới
  useEffect(() => {
    if (isOpen && session) {
      const defaultTitle = session.title ? `[Bản sao] ${session.title}` : '[Bản sao] Đề mới';
      setTitle(defaultTitle);
      setErrorMessage('');
      setIsSubmitting(false);

      // Focus vào ô input sau khi render
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          inputRef.current.select();
        }
      }, 50);
    }
  }, [isOpen, session]);

  // Lắng nghe phím ESC để đóng modal an toàn
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape' && isOpen && !isSubmitting) {
        onClose();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen || !session) {
    return null;
  }

  const isTitleValid = Boolean(title && title.trim().length > 0);

  async function handleSubmit(event) {
    event.preventDefault();

    if (!isTitleValid || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage('');

    try {
      const clonedSession = await cloneFn(session.id, title.trim());

      setIsSubmitting(false);
      if (onSuccess) {
        onSuccess(clonedSession);
      }
      onClose();
    } catch (cause) {
      // Lỗi: giữ nguyên modal, giữ input để người dùng chỉnh sửa và thử lại
      setIsSubmitting(false);
      const message =
        cause instanceof Error && cause.message
          ? cause.message
          : 'Không thể nhân bản phiên lúc này. Vui lòng thử lại.';
      setErrorMessage(message);
    }
  }

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget && !isSubmitting) {
      onClose();
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="clone-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={handleBackdropClick}
    >
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <header className="mb-4">
          <h2 id="clone-modal-title" className="text-xl font-semibold text-slate-100">
            Nhân bản phiên đề thi
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Tạo một bản sao độc lập từ phiên{' '}
            <span className="font-medium text-slate-200">
              “{session.title || 'Chưa đặt tên'}”
            </span>
            .
          </p>
        </header>

        {errorMessage && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-rose-800 bg-rose-950/40 p-3 text-sm text-rose-300"
          >
            {errorMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="clone-session-title"
              className="block text-sm font-medium text-slate-300 mb-1"
            >
              Tiêu đề phiên mới <span className="text-rose-400">*</span>
            </label>
            <input
              ref={inputRef}
              id="clone-session-title"
              type="text"
              required
              disabled={isSubmitting}
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                if (errorMessage) setErrorMessage('');
              }}
              placeholder="Nhập tiêu đề cho phiên nhân bản..."
              className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 placeholder-slate-500 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400 disabled:opacity-50"
            />
          </div>

          <footer className="mt-6 flex flex-wrap justify-end gap-3">
            <button
              type="button"
              className={secondaryButtonClass}
              disabled={isSubmitting}
              onClick={onClose}
            >
              Hủy
            </button>

            <button
              type="submit"
              className={primaryButtonClass}
              disabled={!isTitleValid || isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-950 border-t-transparent" />
                  Đang nhân bản…
                </>
              ) : (
                'Nhân bản'
              )}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

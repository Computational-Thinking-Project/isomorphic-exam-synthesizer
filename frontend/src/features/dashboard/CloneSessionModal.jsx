import { useCallback, useEffect, useRef, useState } from 'react';
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

function getDefaultTitle(session) {
  if (!session) return '';
  return session.title ? `[Bản sao] ${session.title}` : '[Bản sao] Đề mới';
}

/**
 * Modal nhân bản phiên làm việc (CloneSessionModal — TASK-103b).
 *
 * @param {Object} props
 * @param {boolean} props.isOpen - Cờ hiển thị modal
 * @param {Object|null} props.session - Đối tượng phiên cần nhân bản ({ id, title, ... })
 * @param {Function} props.onClose - Callback khi đóng/hủy modal
 * @param {Function} props.onSuccess - Callback khi nhân bản thành công: onSuccess(newSession)
 *   Lưu ý: cloneFn bắt buộc trả về trực tiếp đối tượng phiên mới (unwrap response data)
 * @param {Function} [props.cloneFn=mockCloneSession] - Hàm thực hiện clone (hỗ trợ DI/mock/real API)
 */
export default function CloneSessionModal({
  isOpen,
  session,
  onClose,
  onSuccess,
  cloneFn = mockCloneSession,
}) {
  const [title, setTitle] = useState(() => getDefaultTitle(session));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const inputRef = useRef(null);
  const modalBoxRef = useRef(null);
  const triggerElementRef = useRef(null);
  const activeRequestIdRef = useRef(0);
  const isMountedRef = useRef(true);
  const isSubmittingRef = useRef(false);

  // Theo dõi trạng thái isOpen và session để hủy bỏ request cũ ngay trong chu trình render
  const isOpenRef = useRef(isOpen);
  const prevIsOpenRef = useRef(isOpen);
  const prevSessionIdRef = useRef(session?.id);

  if (prevIsOpenRef.current && !isOpen) {
    // Modal vừa bị chuyển sang đóng/ẩn (isOpen: true -> false): hủy bỏ mọi request đang chờ
    activeRequestIdRef.current += 1;
    isSubmittingRef.current = false;
  }
  prevIsOpenRef.current = isOpen;
  isOpenRef.current = isOpen;

  if (prevSessionIdRef.current !== session?.id) {
    // Phiên vừa bị thay đổi sang phiên khác: hủy bỏ request của phiên cũ
    activeRequestIdRef.current += 1;
    prevSessionIdRef.current = session?.id;
    isSubmittingRef.current = false;
  }

  // Ghi nhận trạng thái mount và hủy request cũ khi unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      activeRequestIdRef.current += 1;
      isSubmittingRef.current = false;
    };
  }, []);

  // Đóng modal và khôi phục vị trí focus bàn phím về nút đã kích hoạt
  const handleClose = useCallback(() => {
    // Hủy bỏ lượt đang chờ nếu người dùng chủ động đóng hộp thoại
    activeRequestIdRef.current += 1;
    isSubmittingRef.current = false;
    isOpenRef.current = false;

    if (triggerElementRef.current && typeof triggerElementRef.current.focus === 'function') {
      try {
        triggerElementRef.current.focus();
      } catch {
        // Bỏ qua nếu element kích hoạt không còn trên DOM
      }
    }

    if (onClose) {
      onClose();
    }
  }, [onClose]);

  // Vô hiệu hóa và dọn dẹp state khi modal bị ẩn
  useEffect(() => {
    isOpenRef.current = isOpen;
    if (!isOpen) {
      activeRequestIdRef.current += 1;
      isSubmittingRef.current = false;
      setIsSubmitting(false);
      setErrorMessage('');
    }
  }, [isOpen]);

  // Khởi tạo tiêu đề gợi ý, reset lỗi và lưu trigger element mỗi khi mở modal
  useEffect(() => {
    if (isOpen && session) {
      // Lưu lại phần tử đang được focus trước khi mở modal
      if (typeof document !== 'undefined' && document.activeElement) {
        triggerElementRef.current = document.activeElement;
      }

      setTitle(getDefaultTitle(session));
      setErrorMessage('');
      setIsSubmitting(false);
      isSubmittingRef.current = false;
      activeRequestIdRef.current += 1;

      // Focus vào ô input sau khi render
      const timer = setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          inputRef.current.select();
        }
      }, 50);

      return () => {
        clearTimeout(timer);
        // Hủy bỏ request đang chờ nếu modal bị unmount hoặc đóng giữa chừng
        activeRequestIdRef.current += 1;
        isSubmittingRef.current = false;
      };
    }
  }, [isOpen, session]);

  // Focus trap: Giữ vị trí chọn (Tab/Shift+Tab) bên trong modal và xử lý phím ESC
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        if (!isSubmittingRef.current) {
          event.preventDefault();
          handleClose();
        }
        return;
      }

      if (event.key === 'Tab') {
        // Khi đang submit, khóa toàn bộ di chuyển focus ra ngoài
        if (isSubmittingRef.current) {
          event.preventDefault();
          return;
        }

        if (!modalBoxRef.current) return;

        const focusableElements = modalBoxRef.current.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );

        if (!focusableElements || focusableElements.length === 0) {
          event.preventDefault();
          return;
        }

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (event.shiftKey) {
          // Shift + Tab: nếu đang ở phần tử đầu tiên, chuyển focus về phần tử cuối cùng
          if (
            document.activeElement === firstElement ||
            !modalBoxRef.current.contains(document.activeElement)
          ) {
            event.preventDefault();
            lastElement.focus();
          }
        } else {
          // Tab: nếu đang ở phần tử cuối cùng, chuyển focus về phần tử đầu tiên
          if (
            document.activeElement === lastElement ||
            !modalBoxRef.current.contains(document.activeElement)
          ) {
            event.preventDefault();
            firstElement.focus();
          }
        }
      }
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleClose]);

  if (!isOpen || !session) {
    return null;
  }

  const isTitleValid = Boolean(title && title.trim().length > 0);

  async function handleSubmit(event) {
    event.preventDefault();

    // Chặn gửi nếu tiêu đề không hợp lệ hoặc ĐANG gửi (kiểm tra tức thì qua ref đồng bộ)
    if (!isTitleValid || isSubmittingRef.current) {
      return;
    }

    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setErrorMessage('');

    const currentRequestId = activeRequestIdRef.current + 1;
    activeRequestIdRef.current = currentRequestId;

    try {
      const clonedSession = await cloneFn(session.id, title.trim());

      isSubmittingRef.current = false;

      // Nếu modal đã đóng/ẩn (isOpen=false), unmount, hoặc đã có request mới hơn:
      // BỎ QUA HOÀN TOÀN, không gọi onSuccess, không gọi handleClose!
      if (
        !isMountedRef.current ||
        !isOpenRef.current ||
        currentRequestId !== activeRequestIdRef.current
      ) {
        return;
      }

      setIsSubmitting(false);
      if (onSuccess) {
        onSuccess(clonedSession);
      }
      handleClose();
    } catch (cause) {
      isSubmittingRef.current = false;

      // Nếu modal đã đóng/ẩn hoặc request đã cũ: BỎ QUA HOÀN TOÀN
      if (
        !isMountedRef.current ||
        !isOpenRef.current ||
        currentRequestId !== activeRequestIdRef.current
      ) {
        return;
      }

      setIsSubmitting(false);
      const message =
        cause instanceof Error && cause.message
          ? cause.message
          : 'Không thể nhân bản phiên lúc này. Vui lòng thử lại.';
      setErrorMessage(message);
    }
  }

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget && !isSubmittingRef.current) {
      handleClose();
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
      <div
        ref={modalBoxRef}
        className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl"
      >
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
              onClick={handleClose}
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

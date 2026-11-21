import { useEffect, useId, useRef } from 'react';
import { AlertCircle } from 'lucide-react';

const buttonClass =
  'rounded-xl border border-line bg-surface px-4 py-2 text-xs font-semibold text-strong ' +
  'hover:bg-rail focus-visible:outline-none focus-visible:ring-2 ' +
  'focus-visible:ring-highlight focus-visible:ring-offset-2 transition-all';

export default function IncompleteContentDialog({
  open,
  errors = [],
  onClose,
  onChooseFile,
  onSwitchToText,
}) {
  const id = useId();
  const box = useRef(null);
  const closeButton = useRef(null);
  const textButton = useRef(null);
  const trigger = useRef(null);
  const visible = open && errors.length > 0;

  useEffect(() => {
    if (!visible) return;
    const modal = box.current;
    trigger.current = document.activeElement;
    modal.showModal();
    closeButton.current?.focus();
    return () => {
      if (modal.open) modal.close();
      trigger.current = null;
    };
  }, [visible]);

  if (!visible) return null;

  const finish = (action, restoreFocus = false) => {
    if (!box.current?.open) return;
    const target = trigger.current;
    box.current.close();
    action();
    if (
      restoreFocus &&
      target?.ownerDocument?.documentElement?.contains(target) &&
      target.getAttribute('disabled') === null
    ) {
      target.focus();
    }
  };

  const close = () => finish(onClose, true);

  const handleKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (event.key === 'Tab') {
      const first = closeButton.current;
      const last = textButton.current;
      if (
        event.shiftKey
          ? document.activeElement === first
          : document.activeElement === last
      ) {
        event.preventDefault();
        (event.shiftKey ? last : first)?.focus();
      }
    }
  };

  return (
    <dialog
      ref={box}
      role="dialog"
      aria-modal="true"
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-help`}
      className="fixed inset-0 m-0 h-dvh max-h-none w-screen max-w-none items-center justify-center border-0 bg-transparent p-4 text-strong open:flex backdrop:bg-zinc-900/60 backdrop:backdrop-blur-sm"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onKeyDown={handleKeyDown}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className="flex max-h-[calc(100dvh-2rem)] w-full max-w-xl flex-col rounded-2xl border border-line bg-surface shadow-2xl">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-line p-4 sm:p-5">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-danger-border bg-danger-soft text-danger">
              <AlertCircle className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 id={`${id}-title`} className="text-lg font-bold text-strong">
                  Đề nguồn chưa đầy đủ
                </h2>
                <span className="rounded-md border border-danger-border bg-danger-soft px-2 py-0.5 text-[11px] font-semibold text-danger">
                  {errors.length} mục cần sửa
                </span>
              </div>
              <p id={`${id}-help`} className="mt-1 text-xs leading-relaxed text-muted">
                Sửa tệp hoặc văn bản nguồn theo các lỗi dưới đây, sau đó bấm Nạp nguồn để gửi lại.
              </p>
            </div>
          </div>
          <button
            ref={closeButton}
            type="button"
            className={`${buttonClass} shrink-0`}
            aria-label="Đóng cảnh báo nội dung"
            onClick={close}
          >
            Đóng
          </button>
        </header>

        <ol
          aria-label="Danh sách lỗi nguồn"
          tabIndex={0}
          className="min-h-0 space-y-3 overflow-auto p-4 sm:p-5"
        >
          {errors.map((error, index) => (
            <li
              key={index}
              className="space-y-1.5 break-words rounded-xl border border-danger-border bg-danger-soft/40 p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-xs font-bold text-danger">
                  {error.location} · {error.title}
                </h3>
                <span className="rounded bg-surface px-1.5 py-0.5 text-[11px] font-semibold text-danger border border-danger-border">
                  #{index + 1}
                </span>
              </div>
              {error.detail && (
                <p className="whitespace-pre-wrap text-xs text-strong">
                  {error.detail}
                </p>
              )}
              <p className="text-xs text-muted">{error.guidance}</p>
            </li>
          ))}
        </ol>

        <footer className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-line bg-rail/40 p-4">
          <button
            type="button"
            className={buttonClass}
            onClick={() => finish(onChooseFile)}
          >
            Chọn tệp đã sửa
          </button>
          <button
            ref={textButton}
            type="button"
            className={buttonClass}
            onClick={() => finish(onSwitchToText)}
          >
            Chuyển sang Nhập trực tiếp
          </button>
        </footer>
      </div>
    </dialog>
  );
}

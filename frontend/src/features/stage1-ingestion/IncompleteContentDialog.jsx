import { useEffect, useId, useRef } from 'react';

const buttonClass = 'rounded-lg border border-slate-600 px-3 py-2 hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400';

export default function IncompleteContentDialog({ open, errors = [], onClose, onChooseFile, onSwitchToText }) {
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
    // Release native inertness before the callback opens a picker in this same user click.
    box.current.close();
    action();
    if (restoreFocus && target?.ownerDocument?.documentElement?.contains(target) && target.getAttribute('disabled') === null) {
      target.focus();
    }
  };
  const close = () => finish(onClose, true);
  const handleKeyDown = event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (event.key === 'Tab') {
      const first = closeButton.current;
      const last = textButton.current;
      if (event.shiftKey ? document.activeElement === first : document.activeElement === last) {
        event.preventDefault();
        (event.shiftKey ? last : first)?.focus();
      }
    }
  };

  return (
    <dialog ref={box} role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} aria-describedby={`${id}-help`}
      className="fixed inset-0 m-0 h-dvh max-h-none w-screen max-w-none items-center justify-center border-0 bg-transparent p-4 text-slate-100 open:flex backdrop:bg-slate-950/80 backdrop:backdrop-blur-sm"
      onCancel={event => { event.preventDefault(); close(); }}
      onKeyDown={handleKeyDown} onClick={event => { if (event.target === event.currentTarget) close(); }}>
      <div className="flex max-h-[calc(100dvh-2rem)] w-full max-w-xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-700 p-4">
          <div>
            <h2 id={`${id}-title`} className="text-xl font-semibold">Đề nguồn chưa đầy đủ</h2>
            <p id={`${id}-help`} className="mt-2 text-sm text-slate-300">Sửa tệp hoặc văn bản nguồn theo các lỗi dưới đây, sau đó bấm Nạp nguồn để gửi lại.</p>
          </div>
          <button ref={closeButton} type="button" className={`${buttonClass} shrink-0`} aria-label="Đóng cảnh báo nội dung" onClick={close}>Đóng</button>
        </header>
        <ol aria-label="Danh sách lỗi nguồn" tabIndex={0} className="min-h-0 space-y-4 overflow-auto p-4">
          {errors.map((error, index) => <li key={index} className="space-y-2 break-words rounded-lg border border-slate-700 p-3">
            <h3 className="font-semibold">{error.location} · {error.title}</h3>
            {error.detail && <p className="whitespace-pre-wrap text-sm text-slate-300">{error.detail}</p>}
            <p>{error.guidance}</p>
          </li>)}
        </ol>
        <footer className="flex shrink-0 flex-wrap gap-2 border-t border-slate-700 p-4">
          <button type="button" className={buttonClass} onClick={() => finish(onChooseFile)}>Chọn tệp đã sửa</button>
          <button ref={textButton} type="button" className={buttonClass} onClick={() => finish(onSwitchToText)}>Chuyển sang Nhập trực tiếp</button>
        </footer>
      </div>
    </dialog>
  );
}

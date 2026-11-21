import { useEffect, useRef } from 'react';

// Keep keyboard navigation inside an open dialog and restore its trigger on close.
export default function useDialogFocus(open, busy, onClose) {
  const dialogRef = useRef(null);
  const stateRef = useRef({ busy, onClose });
  stateRef.current = { busy, onClose };

  useEffect(() => {
    if (!open) return;
    const trigger = document.activeElement;
    const dialog = dialogRef.current;
    const bodyStyle = document.body?.style;
    const previousOverflow = bodyStyle?.overflow;
    if (bodyStyle) bodyStyle.overflow = 'hidden';
    const controls = () => Array.from(dialog?.querySelectorAll('button, a[href], input, select, textarea, [tabindex]') || [])
      .filter((element) => !element.disabled && element.tabIndex !== -1);
    const timer = setTimeout(() => (controls()[0] || dialog)?.focus?.(), 0);
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (!stateRef.current.busy) stateRef.current.onClose();
      }
      if (event.key !== 'Tab') return;
      const elements = controls();
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (!first) {
        event.preventDefault();
        dialog?.focus?.();
      } else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('keydown', onKeyDown);
      if (bodyStyle) bodyStyle.overflow = previousOverflow;
      trigger?.focus?.();
    };
  }, [open]);

  return dialogRef;
}

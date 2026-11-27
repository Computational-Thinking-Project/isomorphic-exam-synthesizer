import { useEffect, useRef, useState } from 'react';
import { ReviewQuestionContent, ReviewSolution } from './Stage3Comparison.jsx';
const reasons = {
  INCORRECT_ANSWER: 'Đáp án không chính xác',
  NO_CORRECT_ANSWER: 'Không có phương án đúng',
  MULTIPLE_CORRECT_ANSWERS: 'Có nhiều phương án đúng',
  EQUIVALENT_OPTIONS: 'Phương án tương đương',
  INVALID_QUESTION: 'Nội dung đề bài sai',
  ISOMORPHISM_MISMATCH: 'Không đảm bảo tính đẳng cấu',
  DIFFICULTY_MISMATCH: 'Mức độ khó không tương đương',
  INCORRECT_SOLUTION: 'Lời giải không chính xác',
};

export default function Stage3InspectionDialog({ selection, boundReasons, versionLabel, message, readOnly, approved,
  busy, rejectBusy, canRevert, onClose, onApprove, onRegenerate, onRevert, onNext }) {
  const dialog = useRef(null);
  const heading = useRef(null);
  const mounted = useRef(false);
  const [confirmation, setConfirmation] = useState(null);
  const [selectedReasons, setSelectedReasons] = useState([]);
  const { variant, qNo } = selection;
  const candidateId = variant.candidate_id || variant.id || variant.question_id;
  const warning = [variant.warning_message, variant.validation_report?.warning, variant.validation_report?.message]
    .find(value => typeof value === 'string' && value.trim())
    || (variant.has_warning ? 'Có cảnh báo kiểm định; vui lòng kiểm tra đáp án và lời giải.' : null);
  useEffect(() => {
    mounted.current = true;
    const node = dialog.current;
    const opener = document.activeElement;
    if (node.showModal) node.showModal();
    else node.setAttribute('open', ''); // DOM test harness; browsers use the native top layer.
    heading.current?.focus();
    return () => {
      mounted.current = false;
      if (node.close) node.close();
      opener?.focus?.();
    };
  }, []);
  useEffect(() => { heading.current?.focus(); }, [confirmation, candidateId]);
  const close = () => { if (!busy) onClose(); };
  const confirm = async () => {
    await (confirmation === 'revert' ? onRevert() : onRegenerate(selectedReasons));
    if (mounted.current) setConfirmation(null);
  };
  const keyDown = (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key !== 'Tab') return;
    // Markdown solutions can contain links, including in a read-only dialog with no footer actions.
    const focusable = Array.from(dialog.current.querySelectorAll('button, input, a[href], [tabindex]'))
      .filter(element => !element.disabled && Number(element.getAttribute('tabindex') ?? 0) >= 0);
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (!first) { event.preventDefault(); return; }
    if (event.shiftKey && (document.activeElement === first || document.activeElement === heading.current)) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  return (
    <dialog ref={dialog} role="dialog" aria-modal="true" aria-labelledby="stage3-inspection-title"
      id={`solution-${selection.versionIndex}-${qNo}`} className="stage3-inspection" aria-busy={busy}
      onKeyDown={keyDown} onCancel={event => { event.preventDefault(); close(); }}
      onClick={event => { if (event.target === event.currentTarget) close(); }}>
      <header className="stage3-inspection-header">
        <h2 id="stage3-inspection-title" ref={heading} tabIndex={-1}>
          {confirmation ? (confirmation === 'revert' ? 'Xác nhận khôi phục đề gốc' : 'Xác nhận tạo lại') : 'Kiểm tra đáp án'} · Câu {qNo} · {versionLabel}
        </h2>
        <button type="button" aria-label="Đóng kiểm tra đáp án" disabled={busy} onClick={close}>×</button>
      </header>
      <div className="stage3-inspection-body">
        {message && <p role={message.type === 'error' ? 'alert' : 'status'}>{message.text}</p>}
        {warning && <p role="status">{warning}</p>}
        {confirmation ? <p>Thao tác chỉ áp dụng Câu {qNo} · {versionLabel}. Kết quả mới phải được kiểm tra và duyệt lại; các cặp khác được giữ nguyên.</p> :
          <div className="stage3-inspection-columns">
            <section aria-label="Biến thể đang xem"><h3>Biến thể · Câu {qNo}</h3><ReviewQuestionContent question={variant} /></section>
            <section aria-label="Đáp án và lời giải"><h3>Đáp án và lời giải</h3>
              <p>Đáp án đúng: {variant.correct_key || variant.answer || 'Chưa có đáp án'}</p>
              <ReviewSolution question={variant} />
            </section>
          </div>}
        {confirmation === 'regenerate' && <fieldset disabled={busy || Boolean(boundReasons)}>
          <legend>Lý do tạo lại (tùy chọn)</legend>
          {Object.entries(reasons).map(([code, label]) => <label key={code} className="block">
            <input type="checkbox" checked={(boundReasons || selectedReasons).includes(code)}
              onChange={event => setSelectedReasons(event.target.checked
                ? [...selectedReasons, code].sort() : selectedReasons.filter(value => value !== code))} /> {label}
          </label>)}
        </fieldset>}
        {readOnly && <p>Chỉ xem: phiên hiện không cho phép thay đổi nội dung hoặc duyệt câu.</p>}
      </div>
      <footer className="stage3-inspection-actions">
        {!readOnly && (confirmation ? <div className="stage3-primary-actions">
          <button type="button" disabled={busy} onClick={() => setConfirmation(null)}>Hủy {confirmation === 'revert' ? 'khôi phục' : 'tạo lại'}</button>
          <button type="button" data-review-confirm disabled={busy} onClick={() => void confirm()}>
            {busy ? 'Đang xử lý…' : confirmation === 'revert' ? 'Khôi phục đúng cặp' : 'Tạo lại đúng cặp'}
          </button>
        </div> : <>
          {canRevert && <button type="button" className="stage3-revert" data-review-revert disabled={busy} onClick={() => setConfirmation('revert')}>Khôi phục đề gốc</button>}
          <div className="stage3-primary-actions">
            <button type="button" data-review-regenerate disabled={busy || rejectBusy || !candidateId} onClick={() => setConfirmation('regenerate')}>Tạo lại</button>
            <button type="button" data-review-approve disabled={busy || approved || !candidateId} onClick={() => void onApprove()}>{busy ? 'Đang xử lý…' : approved ? 'Đã duyệt' : 'Duyệt biến thể'}</button>
            {approved && <button type="button" onClick={onNext} disabled={busy}>Đến câu chưa duyệt tiếp theo</button>}
          </div>
        </>)}
      </footer>
    </dialog>
  );
}

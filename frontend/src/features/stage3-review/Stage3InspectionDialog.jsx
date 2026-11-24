import { useEffect, useRef, useState } from 'react';
import { ReviewQuestionContent, reviewPairIssue } from './Stage3Comparison.jsx';
import MathRenderer from '../../components/MathRenderer.jsx';

export default function Stage3InspectionDialog({ selection, versionLabel, message, readOnly, approved,
  busy, canRevert, onClose, onApprove, onRegenerate, onRevert, onNext }) {
  const dialog = useRef(null);
  const heading = useRef(null);
  const mounted = useRef(false);
  const [confirmation, setConfirmation] = useState(null);
  const { variant, qNo } = selection;
  const candidateId = variant.candidate_id || variant.id || variant.question_id;
  const issue = reviewPairIssue(variant);
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
    await (confirmation === 'revert' ? onRevert() : onRegenerate());
    if (mounted.current) setConfirmation(null);
  };
  const keyDown = (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key !== 'Tab') return;
    const buttons = Array.from(dialog.current.querySelectorAll('button')).filter(button => !button.disabled);
    const first = buttons[0], last = buttons[buttons.length - 1];
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
        {issue && <p role="alert">{issue}</p>}
        {confirmation ? <p>Thao tác chỉ áp dụng Câu {qNo} · {versionLabel}. Kết quả mới phải được kiểm tra và duyệt lại; các cặp khác được giữ nguyên.</p> :
          <div className="stage3-inspection-columns">
            <section aria-label="Biến thể đang xem"><h3>Biến thể · Câu {qNo}</h3><ReviewQuestionContent question={variant} /></section>
            <section aria-label="Đáp án và lời giải"><h3>Đáp án và lời giải</h3>
              <p>Đáp án đúng: {variant.correct_key || variant.answer || 'Chưa có đáp án'}</p>
              {variant.solution_md ? <MathRenderer content={variant.solution_md} /> : <p>Chưa có lời giải chi tiết cho câu hỏi này.</p>}
            </section>
          </div>}
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
            <button type="button" data-review-regenerate disabled={busy || !candidateId} onClick={() => setConfirmation('regenerate')}>Tạo lại</button>
            <button type="button" data-review-approve disabled={busy || approved || !candidateId || Boolean(issue)} onClick={() => void onApprove()}>{busy ? 'Đang xử lý…' : approved ? 'Đã duyệt' : 'Duyệt biến thể'}</button>
            {approved && <button type="button" onClick={onNext} disabled={busy}>Đến câu chưa duyệt tiếp theo</button>}
          </div>
        </>)}
      </footer>
    </dialog>
  );
}

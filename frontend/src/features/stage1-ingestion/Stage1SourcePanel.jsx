import { useEffect, useId, useState, useSyncExternalStore } from 'react';
import { ingestText, validateIngestText } from '../../services/ingestion.js';
import { getSessionDetail } from '../../services/sessions.js';
import { createSourceIngestionController } from './sourceIngestion.js';
import SourceQuestionPreview from './SourceQuestionPreview.jsx';

const buttonClass = 'rounded-lg border border-slate-600 px-3 py-2 hover:bg-slate-800 disabled:opacity-50';

export default function Stage1SourcePanel({ detail, isCurrent }) {
  const inputId = useId();
  const [controller] = useState(() => createSourceIngestionController({
    initialDetail: detail, ingestText, load: getSessionDetail, validateText: validateIngestText, isCurrent,
  }));
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  useEffect(() => () => controller.dispose(), [controller]);
  const busy = state.phase !== 'idle';
  const readOnly = state.detail.status !== 'draft';

  return (
    <section aria-label="Nhập nguồn đề" className="mt-4 flex min-h-0 flex-1 flex-col gap-3">
      {state.error && <p role="alert" id={`${inputId}-error`} className="shrink-0 text-rose-300">{state.error}</p>}
      <p role="status" aria-live="polite" className="shrink-0 text-slate-300">
        {state.phase === 'submitting' ? 'Đang gửi và xử lý nguồn…'
          : state.phase === 'reloading' ? 'Đang đọc lại nguồn đã lưu…' : state.message}
      </p>
      {readOnly && <p>Phiên không còn ở trạng thái nháp. Bạn chỉ có thể đọc nguồn tại đây.</p>}
      <div className="grid min-h-0 flex-1 grid-rows-2 gap-4 md:grid-cols-2 md:grid-rows-1">
        <form id={`${inputId}-form`} aria-label="Nhập trực tiếp" className="flex min-h-0 flex-col gap-2 overflow-auto" onSubmit={(event) => {
          event.preventDefault(); void controller.submit();
        }}>
          <label htmlFor={inputId} className="font-semibold">Nhập trực tiếp</label>
          <p id={`${inputId}-help`} className="text-sm text-slate-300">Tối đa 100.000 ký tự. Nhập câu hỏi, các phương án A–D và đáp án đúng.</p>
          <textarea id={inputId} value={state.text} onChange={(event) => controller.setText(event.target.value)}
            disabled={busy || readOnly || state.unavailable}
            aria-describedby={`${inputId}-help${state.error ? ` ${inputId}-error` : ''}`}
            aria-invalid={state.cause?.code === 'ERR_INGEST_INPUT'}
            className="min-h-[4rem] flex-1 resize-none rounded-lg border border-slate-600 bg-slate-900 p-3" />
        </form>
        {state.unavailable ? <p>Chưa thể hiển thị nguồn. Hãy kiểm tra lại quyền truy cập phiên.</p> : (
          <SourceQuestionPreview questions={state.detail.source_questions} versionCount={state.detail.exam_versions?.length ?? 0} />
        )}
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        <button type="submit" form={`${inputId}-form`} className={buttonClass} disabled={!controller.canSubmit()}>Nạp nguồn</button>
        <button type="button" className={buttonClass} disabled={busy} onClick={() => void controller.reload()}>Đọc lại nguồn đã lưu</button>
        {busy && <button type="button" className={buttonClass} onClick={() => controller.cancelRequest()}>Dừng chờ</button>}
      </div>
    </section>
  );
}

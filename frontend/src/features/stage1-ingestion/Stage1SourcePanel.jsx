import { useEffect, useId, useState, useSyncExternalStore } from 'react';
import { ingestFile, ingestText, validateIngestFile, validateIngestText } from '../../services/ingestion.js';
import { getSessionDetail } from '../../services/sessions.js';
import { createSourceIngestionController } from './sourceIngestion.js';
import SourceQuestionPreview from './SourceQuestionPreview.jsx';

const buttonClass = 'rounded-lg border border-slate-600 px-3 py-2 hover:bg-slate-800 disabled:opacity-50';

export default function Stage1SourcePanel({ detail, isCurrent }) {
  const inputId = useId();
  const [controller] = useState(() => createSourceIngestionController({
    initialDetail: detail, ingestText, ingestFile, load: getSessionDetail,
    validateText: validateIngestText, validateFile: validateIngestFile, isCurrent,
  }));
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  useEffect(() => () => controller.dispose(), [controller]);
  const busy = state.phase !== 'idle';
  const readOnly = state.detail.status !== 'draft';
  const inputDisabled = busy || readOnly || state.unavailable;
  const uploadPercent = state.upload?.total === null || !state.upload ? undefined
    : Math.min(100, Math.floor(state.upload.loaded / state.upload.total * 100));

  return (
    <section aria-label="Nhập nguồn đề" className="mt-4 flex min-h-0 flex-1 flex-col gap-3">
      {state.error && <p role="alert" id={`${inputId}-error`} className="shrink-0 text-rose-300">{state.error}</p>}
      <p role="status" aria-live="polite" className="shrink-0 text-slate-300">
        {state.phase === 'submitting' ? state.upload
          ? state.upload.complete ? 'Đã tải tệp lên. Đang xử lý nguồn…'
            : `Đang tải tệp lên${uploadPercent === undefined ? '…' : `: ${uploadPercent}%…`}`
          : 'Đang gửi và xử lý nguồn…'
          : state.phase === 'reloading' ? 'Đang đọc lại nguồn đã lưu…' : state.message}
      </p>
      {state.upload && <progress aria-label="Tiến độ tải tệp lên" className="w-full shrink-0"
        max="100" value={uploadPercent} />}
      {readOnly && <p>Phiên không còn ở trạng thái nháp. Bạn chỉ có thể đọc nguồn tại đây.</p>}
      <div className="grid min-h-0 flex-1 grid-rows-2 gap-4 md:grid-cols-2 md:grid-rows-1">
        <form id={`${inputId}-form`} aria-label="Nhập nguồn" className="flex min-h-0 flex-col gap-2 overflow-auto" onSubmit={(event) => {
          event.preventDefault(); void controller.submit();
        }}>
          <div role="group" aria-label="Cách nhập nguồn" className="flex shrink-0 flex-wrap gap-2">
            <button type="button" className={buttonClass} aria-pressed={state.mode === 'text'}
              disabled={inputDisabled} onClick={() => controller.setMode('text')}>Nhập trực tiếp</button>
            <button type="button" className={buttonClass} aria-pressed={state.mode === 'file'}
              disabled={inputDisabled} onClick={() => controller.setMode('file')}>Tải tệp</button>
          </div>
          {state.mode === 'text' ? <>
          <label htmlFor={inputId} className="font-semibold">Nhập trực tiếp</label>
          <p id={`${inputId}-help`} className="text-sm text-slate-300">Tối đa 100.000 ký tự. Nhập câu hỏi, các phương án A–D và đáp án đúng.</p>
          <textarea id={inputId} value={state.text} onChange={(event) => controller.setText(event.target.value)}
            disabled={inputDisabled}
            aria-describedby={`${inputId}-help${state.error ? ` ${inputId}-error` : ''}`}
            aria-invalid={state.cause?.code === 'ERR_INGEST_INPUT'}
            className="min-h-[4rem] flex-1 resize-none rounded-lg border border-slate-600 bg-slate-900 p-3" />
          </> : <div className="flex min-h-[8rem] flex-1 flex-col gap-3 rounded-lg border border-dashed border-slate-600 p-3"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              if (!inputDisabled) controller.selectFiles(Array.from(event.dataTransfer.files));
            }}>
            <label htmlFor={`${inputId}-file`} className="font-semibold">Chọn hoặc kéo thả một tệp đề nguồn</label>
            <p id={`${inputId}-file-help`} className="text-sm text-slate-300">DOCX, TeX hoặc MD, tối đa 10MB. Không nhận PDF. Chọn tệp xong, bấm Nạp nguồn để gửi.</p>
            <input id={`${inputId}-file`} type="file" accept=".docx,.tex,.md" disabled={inputDisabled}
              className="w-full min-w-0" aria-describedby={`${inputId}-file-help${state.error ? ` ${inputId}-error` : ''}`}
              aria-invalid={state.cause?.code === 'ERR_INGEST_INPUT'} onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                // Reset the native selection so the same file can fire change after editing/retrying.
                event.target.value = '';
                if (files.length) controller.selectFiles(files);
              }} />
            <p className="break-all">{state.file
              ? `Đã chọn: ${state.file.name} (${state.file.size.toLocaleString('vi-VN')} byte)` : 'Chưa chọn tệp.'}</p>
            {state.file && <button type="button" className={`${buttonClass} self-start`} disabled={inputDisabled}
              onClick={() => controller.clearFile()}>Bỏ chọn tệp</button>}
          </div>}
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

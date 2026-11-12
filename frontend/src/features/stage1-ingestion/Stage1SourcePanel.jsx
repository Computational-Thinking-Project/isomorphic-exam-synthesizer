import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { ingestFile, ingestText, validateIngestFile, validateIngestText } from '../../services/ingestion.js';
import { getSessionDetail } from '../../services/sessions.js';
import { confirmSource, getSourceArtifactStatus, isSourceUuid, retrySourceArtifacts } from '../../services/sourceConfirmation.js';
import { useAuthStore } from '../auth/authStore.js';
import { createConfirmationIntentStore } from './confirmationIntent.js';
import { createSourceIngestionController } from './sourceIngestion.js';
import SourceQuestionPreview from './SourceQuestionPreview.jsx';
import { readIncompleteError } from './stage1Errors.js';
import IncompleteContentDialog from './IncompleteContentDialog.jsx';

const buttonClass = 'rounded-lg border border-slate-600 px-3 py-2 hover:bg-slate-800 disabled:opacity-50';

export default function Stage1SourcePanel({ detail, isCurrent, onConfirmed }) {
  const inputId = useId();
  const [controller] = useState(() => createSourceIngestionController({
    initialDetail: detail, ingestText, ingestFile, load: getSessionDetail,
    validateText: validateIngestText, validateFile: validateIngestFile, isCurrent,
    confirmSource, readArtifacts: getSourceArtifactStatus,
    retryArtifacts: retrySourceArtifacts,
    onConfirmed,
    confirmationStore: createConfirmationIntentStore(useAuthStore.getState().session?.user.id, detail.id),
  }));
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const [dismissedCause, setDismissedCause] = useState(null);
  const textInput = useRef(null);
  const fileInput = useRef(null);
  const pendingFocus = useRef(null);
  const incomplete = useMemo(() => readIncompleteError(state.cause), [state.cause]);
  const dialogOpen = incomplete !== null && dismissedCause !== state.cause && controller.canSubmit();
  useEffect(() => {
    void controller.restoreConfirmation();
    return () => controller.dispose();
  }, [controller]);
  useEffect(() => {
    if (!pendingFocus.current) return;
    const target = pendingFocus.current === 'file' ? fileInput.current : textInput.current;
    pendingFocus.current = null;
    if (controller.canSubmit()) target?.focus();
  }, [controller, state.mode, dismissedCause]);
  const busy = state.phase !== 'idle';
  const readOnly = state.detail.status !== 'draft';
  const inputDisabled = busy || readOnly || state.unavailable;
  const uploadPercent = state.upload?.total === null || !state.upload ? undefined
    : Math.min(100, Math.floor(state.upload.loaded / state.upload.total * 100));
  const chooseInput = mode => {
    if (!controller.canSubmit()) return;
    pendingFocus.current = mode;
    setDismissedCause(state.cause);
    controller.setMode(mode);
    // Keep the single picker mounted so this click stays in the user's gesture, even from text mode.
    if (mode === 'file') fileInput.current?.click();
  };

  return (
    <section aria-label="Nhập nguồn đề" className="mt-4 flex min-h-0 flex-1 flex-col gap-3">
      {state.error && <p role="alert" aria-hidden={dialogOpen || undefined} id={`${inputId}-error`} className="shrink-0 text-rose-300">{state.error}</p>}
      {state.confirmationError && <p role="alert" className="shrink-0 text-rose-300">{state.confirmationError}</p>}
      <p role="status" aria-live="polite" className="shrink-0 text-slate-300">
        {state.phase === 'submitting' ? state.upload
          ? state.upload.complete ? 'Đã tải tệp lên. Đang xử lý nguồn…'
            : `Đang tải tệp lên${uploadPercent === undefined ? '…' : `: ${uploadPercent}%…`}`
          : 'Đang gửi và xử lý nguồn…'
          : state.phase === 'reloading' ? 'Đang đọc lại nguồn đã lưu…'
            : state.phase === 'confirming' ? 'Đang xác nhận đề nguồn…'
              : state.phase === 'reconciling' ? 'Đang kiểm tra kết quả xác nhận…'
                : state.phase === 'checking_status' ? 'Đang kiểm tra trạng thái Blueprint…'
                  : state.phase === 'retrying_canonical' ? 'Đang yêu cầu tạo lại Blueprint…' : state.message}
      </p>
      {state.upload && <progress aria-label="Tiến độ tải tệp lên" className="w-full shrink-0"
        max="100" value={uploadPercent} />}
      {readOnly && <p>Phiên không còn ở trạng thái nháp. Bạn chỉ có thể đọc nguồn tại đây.</p>}
      {state.canonicalStatus && (
        <div className="shrink-0 rounded-lg border border-slate-700 bg-slate-800/80 p-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-300">Trạng thái Blueprint:</p>
              <p className="text-base font-semibold text-white" data-testid="canonical-status-text">
                {state.canonicalStatus === 'pending' && 'Đang chờ tạo Blueprint'}
                {state.canonicalStatus === 'running' && 'Đang tạo Blueprint'}
                {state.canonicalStatus === 'ready' && 'Blueprint đã sẵn sàng'}
                {state.canonicalStatus === 'failed' && 'Tạo Blueprint thất bại'}
              </p>
              {state.retryAccepted && (
                <p className="mt-1 text-xs text-sky-300">
                  Đã tiếp nhận yêu cầu tạo lại. Kiểm tra trạng thái để cập nhật.
                </p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className={buttonClass}
                disabled={busy}
                onClick={() => void controller.checkCanonicalStatus()}
              >
                Kiểm tra trạng thái
              </button>
              {state.canonicalStatus === 'failed' && !state.retryAccepted && (
                <button
                  type="button"
                  className={buttonClass}
                  disabled={busy}
                  onClick={() => void controller.retryCanonical()}
                >
                  Thử tạo lại Blueprint
                </button>
              )}
              {state.canonicalReady && (
                <button
                  type="button"
                  className={`${buttonClass} bg-sky-600 font-semibold text-white hover:bg-sky-500`}
                  disabled={busy}
                  onClick={() => controller.proceedToStage2()}
                >
                  Tiếp tục Stage 2
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      {state.canonicalError && (
        <div role="alert" className="shrink-0 rounded-lg border border-rose-600/40 bg-rose-950/40 p-3 text-rose-300 flex items-center justify-between gap-3">
          <p>{state.canonicalError}</p>
          {!state.canonicalStatus && (
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => void controller.checkCanonicalStatus()}
            >
              Kiểm tra trạng thái
            </button>
          )}
        </div>
      )}
      <div className="grid min-h-0 flex-1 grid-rows-2 gap-4 md:grid-cols-2 md:grid-rows-1">
        <form id={`${inputId}-form`} aria-label="Nhập nguồn" className="flex min-h-0 flex-col gap-2 overflow-auto" onSubmit={(event) => {
          event.preventDefault();
          if (!controller.canSubmit()) return;
          setDismissedCause(null);
          void controller.submit();
        }}>
          <div role="group" aria-label="Cách nhập nguồn" className="flex shrink-0 flex-wrap gap-2">
            <button type="button" className={buttonClass} aria-pressed={state.mode === 'text'}
              disabled={inputDisabled} onClick={() => controller.setMode('text')}>Nhập trực tiếp</button>
            <button type="button" className={buttonClass} aria-pressed={state.mode === 'file'}
              disabled={inputDisabled} onClick={() => controller.setMode('file')}>Tải tệp</button>
          </div>
          {state.mode === 'text' && <>
          <label htmlFor={inputId} className="font-semibold">Nhập trực tiếp</label>
          <p id={`${inputId}-help`} className="text-sm text-slate-300">Tối đa 100.000 ký tự. Nhập câu hỏi, các phương án A–D và đáp án đúng.</p>
          <textarea ref={textInput} id={inputId} value={state.text} onChange={(event) => controller.setText(event.target.value)}
            disabled={inputDisabled}
            aria-describedby={`${inputId}-help${state.error ? ` ${inputId}-error` : ''}`}
            aria-invalid={state.cause?.code === 'ERR_INGEST_INPUT'}
            className="min-h-[4rem] flex-1 resize-none rounded-lg border border-slate-600 bg-slate-900 p-3" />
          </>}
          <div hidden={state.mode !== 'file'} className={state.mode === 'file'
            ? 'flex min-h-[8rem] flex-1 flex-col gap-3 rounded-lg border border-dashed border-slate-600 p-3' : 'hidden'}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              if (!inputDisabled) controller.selectFiles(Array.from(event.dataTransfer.files));
            }}>
            <label htmlFor={`${inputId}-file`} className="font-semibold">Chọn hoặc kéo thả một tệp đề nguồn</label>
            <p id={`${inputId}-file-help`} className="text-sm text-slate-300">DOCX, TeX hoặc MD, tối đa 10MB. Không nhận PDF. Chọn tệp xong, bấm Nạp nguồn để gửi.</p>
            <input ref={fileInput} id={`${inputId}-file`} type="file" accept=".docx,.tex,.md" disabled={inputDisabled}
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
          </div>
        </form>
        {state.unavailable ? <p>Chưa thể hiển thị nguồn. Hãy kiểm tra lại quyền truy cập phiên.</p> : (
          <SourceQuestionPreview questions={state.detail.source_questions} versionCount={state.detail.exam_versions?.length ?? 0} />
        )}
      </div>
      <p id={`${inputId}-confirm-help`} className="shrink-0 text-sm text-slate-300">
        {state.retryConfirmation ? 'Chưa thấy kết quả xác nhận. Bạn có thể thử lại lần xác nhận trước.'
          : !readOnly && state.detail.source_questions.length > 0 && !isSourceUuid(state.detail.source_revision)
            ? 'Bản đề này chưa thể xác nhận. Hãy đọc lại nguồn đã lưu.'
            : 'Xác nhận bản đề đang hiển thị. Nếu đã sửa nội dung nhập, hãy nạp lại trước khi xác nhận.'}
      </p>
      <div className="flex shrink-0 flex-wrap gap-2">
        {controller.canRecoverStorage() && <button type="button" className={buttonClass}
          onClick={() => void controller.recoverConfirmationStorage()}>Khôi phục thông tin xác nhận</button>}
        <button type="submit" form={`${inputId}-form`} className={buttonClass} disabled={!controller.canSubmit()}>Nạp nguồn</button>
        <button type="button" className={buttonClass} disabled={busy} onClick={() => void controller.reload()}>
          {state.confirmationPending ? 'Đọc lại trạng thái phiên' : 'Đọc lại nguồn đã lưu'}
        </button>
        {!readOnly && (
          <button type="button" className={buttonClass} disabled={dialogOpen || !controller.canConfirm()}
            aria-describedby={`${inputId}-confirm-help`} onClick={() => { if (!dialogOpen) void controller.confirm(); }}>
            {state.retryConfirmation ? 'Thử xác nhận lại' : 'Xác nhận đề gốc và tiếp tục'}
          </button>
        )}
        {['submitting', 'reloading'].includes(state.phase) && <button type="button" className={buttonClass} onClick={() => controller.cancelRequest()}>Dừng chờ</button>}
      </div>
      <IncompleteContentDialog open={dialogOpen} errors={incomplete?.errors ?? []}
        onClose={() => setDismissedCause(state.cause)}
        onChooseFile={() => chooseInput('file')} onSwitchToText={() => chooseInput('text')} />
    </section>
  );
}

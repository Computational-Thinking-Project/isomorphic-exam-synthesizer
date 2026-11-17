import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { AlertTriangle, CheckCircle2, Clock, Loader2 } from 'lucide-react';
import { ingestFile, ingestText, validateIngestFile, validateIngestText } from '../../services/ingestion.js';
import { getSessionDetail } from '../../services/sessions.js';
import { confirmSource, getSourceArtifactStatus, isSourceUuid, retrySourceArtifacts } from '../../services/sourceConfirmation.js';
import { useAuthStore } from '../auth/authStore.js';
import { createConfirmationIntentStore } from './confirmationIntent.js';
import { createSourceIngestionController } from './sourceIngestion.js';
import SourceQuestionPreview from './SourceQuestionPreview.jsx';
import { readIncompleteError } from './stage1Errors.js';
import IncompleteContentDialog from './IncompleteContentDialog.jsx';

const buttonClass = 'rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-rail hover:text-strong disabled:opacity-50 transition-colors';

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
  const [mobileTab, setMobileTab] = useState('input');
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
  const preparing = state.detail.status === 'blueprinted' && !state.canonicalReady
    && (!state.canonicalStatus || ['pending', 'running'].includes(state.canonicalStatus) || state.retryAccepted)
    && !state.unavailable;
  useEffect(() => {
    if (!preparing) return;
    // Controller guards prevent overlapping requests and stale account/session updates.
    const timer = setInterval(() => void controller.checkCanonicalStatus(), 2000);
    return () => clearInterval(timer);
  }, [controller, preparing]);
  const progress = state.canonicalProgress;
  const measuredProgress = Number.isInteger(progress?.completed) && Number.isInteger(progress?.total)
    && progress.total > 0 && progress.completed >= 0;
  const progressPercent = state.canonicalReady ? 100 : measuredProgress
    ? Math.min(99, Math.round(progress.completed / progress.total * 100)) : undefined;
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

  const questionCount = state.detail.source_questions?.length ?? 0;

  return (
    <section aria-label="Nhập nguồn đề" className="mt-4 flex min-h-0 flex-1 flex-col gap-3">
      {/* Mobile Tab Switcher */}
      {!readOnly && (<div className="flex md:hidden rounded-xl border border-line bg-surface p-1 shrink-0" role="group" aria-label="Vùng làm việc">
        <button
          type="button"
          className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold transition-colors ${
            mobileTab === 'input' ? 'bg-highlight text-white shadow-sm' : 'text-muted hover:text-ink'
          }`}
          aria-pressed={mobileTab === 'input'}
          onClick={() => setMobileTab('input')}
        >
          Bộ nạp nguồn
        </button>
        <button
          type="button"
          className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold transition-colors ${
            mobileTab === 'preview' ? 'bg-highlight text-white shadow-sm' : 'text-muted hover:text-ink'
          }`}
          aria-pressed={mobileTab === 'preview'}
          onClick={() => setMobileTab('preview')}
        >
          {`Bản đọc (${questionCount} câu)`}
        </button>
      </div>)}

      {state.error && (
        <p role="alert" aria-hidden={dialogOpen || undefined} id={`${inputId}-error`} className="shrink-0 rounded-xl border border-danger/30 bg-danger-soft p-3 text-sm font-medium text-danger">
          {state.error}
        </p>
      )}
      {state.confirmationError && (
        <p role="alert" className="shrink-0 rounded-xl border border-danger/30 bg-danger-soft p-3 text-sm font-medium text-danger">
          {state.confirmationError}
        </p>
      )}
      <p role="status" aria-live="polite" className="shrink-0 text-sm font-medium text-muted">
        {state.phase === 'submitting' ? state.upload
          ? state.upload.complete ? 'Đã tải tệp lên. Đang xử lý nguồn…'
            : `Đang tải tệp lên${uploadPercent === undefined ? '…' : `: ${uploadPercent}%…`}`
          : 'Đang gửi và xử lý nguồn…'
          : state.phase === 'reloading' ? 'Đang đọc lại nguồn đã lưu…'
            : state.phase === 'confirming' ? 'Đang xác nhận đề nguồn…'
              : state.phase === 'reconciling' ? 'Đang kiểm tra kết quả xác nhận…'
                : state.phase === 'checking_status' ? 'Đang kiểm tra cấu trúc đề…'
                  : state.phase === 'retrying_canonical' ? 'Đang yêu cầu chuẩn bị lại cấu trúc đề…' : state.message}
      </p>
      {state.upload && (
        <progress
          aria-label="Tiến độ tải tệp lên"
          className="w-full h-2 shrink-0 overflow-hidden rounded-full [&::-webkit-progress-bar]:bg-rail [&::-webkit-progress-value]:bg-highlight [&::-moz-progress-bar]:bg-highlight"
          max="100"
          value={uploadPercent}
        />
      )}
      {readOnly && (
        <p className="shrink-0 text-sm text-muted bg-rail p-3 rounded-xl border border-line">
          Phiên không còn ở trạng thái nháp. Bạn chỉ có thể đọc nguồn tại đây.
        </p>
      )}
      {state.detail.status === 'blueprinted' && (
        <div className="shrink-0 rounded-xl border border-line bg-surface p-4 shadow-soft">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start sm:items-center gap-3">
              <div className="mt-0.5 sm:mt-0 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-support-bg text-highlight">
                {state.canonicalStatus === 'pending' && <Clock className="w-5 h-5 text-muted" />}
                {state.canonicalStatus === 'running' && <Loader2 className="w-5 h-5 animate-spin text-highlight" />}
                {state.canonicalStatus === 'ready' && <CheckCircle2 className="w-5 h-5 text-approved-ink" />}
                {state.canonicalStatus === 'failed' && <AlertTriangle className="w-5 h-5 text-danger" />}
              </div>
              <div>
                <p className="text-xs font-medium text-muted">Chuẩn bị cấu trúc đề</p>
                <p className="text-base font-semibold text-strong" data-testid="canonical-status-text">
                  {state.canonicalStatus === 'pending' && 'Đang chờ chuẩn bị cấu trúc đề'}
                  {state.canonicalStatus === 'running' && 'Đang chuẩn bị cấu trúc đề'}
                  {state.canonicalStatus === 'ready' && 'Cấu trúc đề đã sẵn sàng'}
                  {state.canonicalStatus === 'failed' && 'Chưa chuẩn bị được cấu trúc đề'}
                </p>
                {state.retryAccepted && (
                  <p className="mt-1 text-xs font-medium text-highlight">
                    Đã tiếp nhận yêu cầu tạo lại. Tiến độ sẽ tự cập nhật.
                  </p>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {state.canonicalStatus === 'failed' && !state.retryAccepted && (
                <button
                  type="button"
                  className={`${buttonClass} border-danger/30 text-danger hover:bg-danger-soft`}
                  disabled={busy}
                  onClick={() => void controller.retryCanonical()}
                >
                  Thử lại
                </button>
              )}
              {(
                <button
                  type="button"
                  className="rounded-lg bg-highlight px-4 py-2 text-sm font-semibold text-white shadow-soft hover:bg-[#253b57] disabled:opacity-50 transition-colors"
                  disabled={busy || !state.canonicalReady}
                  onClick={() => controller.proceedToStage2()}
                >
                  Tiếp tục cấu hình
                </button>
              )}
            </div>
          </div>
          <div className="mt-4 space-y-2">
            <progress aria-label="Tiến độ chuẩn bị cấu trúc đề" max="100" value={state.canonicalStatus === 'failed' && !state.retryAccepted ? (progressPercent ?? 0) : progressPercent}
              className="h-2 w-full overflow-hidden rounded-full accent-highlight [&::-webkit-progress-bar]:bg-rail [&::-webkit-progress-value]:bg-highlight [&::-moz-progress-bar]:bg-highlight" />
            <p role="status" className="text-xs text-muted">
              {state.canonicalReady ? 'Hoàn tất · 100%' : state.canonicalStatus === 'failed' && !state.retryAccepted
                ? 'Chuẩn bị chưa thành công. Hãy thử lại.'
                : measuredProgress ? `${Math.min(progress.completed, progress.total)}/${progress.total} câu đã chuẩn bị`
                  : 'Đang chuẩn bị cấu trúc đề. Tiến độ sẽ tự cập nhật.'}
            </p>
          </div>
        </div>
      )}
      {state.canonicalError && (
        <div role="alert" className="shrink-0 rounded-xl border border-danger/30 bg-danger-soft p-3 text-sm text-danger flex items-center justify-between gap-3">
          <p className="font-medium">{state.canonicalError}</p>
          {state.unavailable && (
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
      <div className={`grid min-h-0 flex-1 gap-4 md:grid-rows-1 ${readOnly ? 'grid-cols-1' : 'md:grid-cols-2'}`}>
        {!readOnly && (<form
          id={`${inputId}-form`}
          aria-label="Nhập nguồn"
          className={`min-h-0 flex-col gap-3 overflow-auto rounded-xl border border-line bg-surface p-4 shadow-soft ${
            mobileTab === 'input' ? 'flex' : 'hidden md:flex'
          }`}
          onSubmit={(event) => {
            event.preventDefault();
            if (!controller.canSubmit()) return;
            setDismissedCause(null);
            void controller.submit();
          }}
        >
          <div role="group" aria-label="Cách nhập nguồn" className="flex shrink-0 flex-wrap gap-2">
            <button
              type="button"
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                state.mode === 'text'
                  ? 'bg-highlight text-white shadow-sm'
                  : 'border border-line bg-surface text-ink hover:bg-rail'
              } disabled:opacity-50`}
              aria-pressed={state.mode === 'text'}
              disabled={inputDisabled}
              onClick={() => controller.setMode('text')}
            >
              Nhập trực tiếp
            </button>
            <button
              type="button"
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                state.mode === 'file'
                  ? 'bg-highlight text-white shadow-sm'
                  : 'border border-line bg-surface text-ink hover:bg-rail'
              } disabled:opacity-50`}
              aria-pressed={state.mode === 'file'}
              disabled={inputDisabled}
              onClick={() => controller.setMode('file')}
            >
              Tải tệp
            </button>
          </div>
          {state.mode === 'text' && (
            <>
              <div>
                <label htmlFor={inputId} className="text-sm font-semibold text-strong">Nhập trực tiếp</label>
                <p id={`${inputId}-help`} className="mt-0.5 text-xs text-muted">
                  Tối đa 100.000 ký tự. Nhập câu hỏi, các phương án A–D và đáp án đúng.
                </p>
              </div>
              <textarea
                ref={textInput}
                id={inputId}
                value={state.text}
                onChange={(event) => controller.setText(event.target.value)}
                disabled={inputDisabled}
                aria-describedby={`${inputId}-help${state.error ? ` ${inputId}-error` : ''}`}
                aria-invalid={state.cause?.code === 'ERR_INGEST_INPUT'}
                placeholder="Nhập nội dung đề thi nguồn tại đây..."
                className="min-h-[10rem] flex-1 resize-y rounded-xl border border-line bg-white p-3.5 text-sm text-strong leading-relaxed focus:outline-none focus:border-highlight focus:ring-2 focus:ring-highlight/20 transition-all"
              />
            </>
          )}
          <div
            hidden={state.mode !== 'file'}
            className={state.mode === 'file'
              ? 'flex min-h-[10rem] flex-1 flex-col gap-3 rounded-xl border-2 border-dashed border-line bg-support-bg/40 hover:bg-support-bg/70 p-4 transition-colors'
              : 'hidden'}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              if (!inputDisabled) controller.selectFiles(Array.from(event.dataTransfer.files));
            }}
          >
            <div>
              <label htmlFor={`${inputId}-file`} className="text-sm font-semibold text-strong">
                Chọn hoặc kéo thả một tệp đề nguồn
              </label>
              <p id={`${inputId}-file-help`} className="mt-0.5 text-xs text-muted">
                DOCX, TeX hoặc MD, tối đa 10MB. Không nhận PDF. Chọn tệp xong, bấm Nạp nguồn để gửi.
              </p>
            </div>
            <input
              ref={fileInput}
              id={`${inputId}-file`}
              type="file"
              accept=".docx,.tex,.md"
              disabled={inputDisabled}
              className="w-full min-w-0 text-sm text-muted file:mr-3 file:min-h-11 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-line file:bg-surface file:text-sm file:font-medium file:text-ink hover:file:bg-rail cursor-pointer"
              aria-describedby={`${inputId}-file-help${state.error ? ` ${inputId}-error` : ''}`}
              aria-invalid={state.cause?.code === 'ERR_INGEST_INPUT'}
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                // Reset the native selection so the same file can fire change after editing/retrying.
                event.target.value = '';
                if (files.length) controller.selectFiles(files);
              }}
            />
            <p className="text-sm text-ink break-all">
              {state.file
                ? `Đã chọn: ${state.file.name} (${state.file.size.toLocaleString('vi-VN')} byte)`
                : 'Chưa chọn tệp.'}
            </p>
            {state.file && (
              <button
                type="button"
                className={`${buttonClass} self-start`}
                disabled={inputDisabled}
                onClick={() => controller.clearFile()}
              >
                Bỏ chọn tệp
              </button>
            )}
          </div>
        </form>)}
        <div className={`min-h-0 flex-1 flex-col overflow-auto ${
          readOnly || mobileTab === 'preview' ? 'flex' : 'hidden md:flex'
        }`}>
          {state.unavailable ? (
            <p className="rounded-xl border border-line bg-surface p-6 text-sm text-muted shadow-soft">
              Chưa thể hiển thị nguồn. Hãy kiểm tra lại quyền truy cập phiên.
            </p>
          ) : (
            <SourceQuestionPreview questions={state.detail.source_questions} />
          )}
        </div>
      </div>
      {!readOnly && (<p id={`${inputId}-confirm-help`} className="shrink-0 text-xs text-muted">
        {state.retryConfirmation ? 'Chưa thấy kết quả xác nhận. Bạn có thể thử lại lần xác nhận trước.'
          : !readOnly && state.detail.source_questions.length > 0 && !isSourceUuid(state.detail.source_revision)
            ? 'Bản đề này chưa thể xác nhận. Hãy đọc lại nguồn đã lưu.'
            : 'Xác nhận bản đề đang hiển thị. Nếu đã sửa nội dung nhập, hãy nạp lại trước khi xác nhận.'}
      </p>)}
      <div className="flex shrink-0 flex-wrap items-center gap-2 pt-2 border-t border-line">
        {controller.canRecoverStorage() && (
          <button
            type="button"
            className={buttonClass}
            onClick={() => void controller.recoverConfirmationStorage()}
          >
            Khôi phục thông tin xác nhận
          </button>
        )}
        {!readOnly && (<button
          type="submit"
          form={`${inputId}-form`}
          className={questionCount > 0 ? buttonClass : 'rounded-xl bg-highlight px-4 py-2 text-sm font-semibold text-white hover:bg-[#253b57] disabled:opacity-50'}
          disabled={!controller.canSubmit()}
        >
          Nạp nguồn
        </button>)}
        {(!readOnly || state.uncertain || state.requiresReload || state.unavailable || state.confirmationPending || state.error || (!readOnly && questionCount > 0 && !isSourceUuid(state.detail.source_revision))) && <button type="button" className={buttonClass} disabled={busy} onClick={() => void controller.reload()}>
          {state.confirmationPending ? 'Đọc lại trạng thái phiên' : 'Đọc lại nguồn đã lưu'}
        </button>}
        {!readOnly && questionCount > 0 && (
          <button
            type="button"
            className={state.retryConfirmation
              ? "rounded-lg border border-accent/40 bg-accent-soft px-4 py-2 text-sm font-semibold text-ink hover:bg-accent/20 disabled:opacity-50 transition-colors"
              : "rounded-lg bg-highlight px-4 py-2 text-sm font-semibold text-white shadow-soft hover:bg-[#253b57] disabled:opacity-50 transition-colors"}
            disabled={dialogOpen || !controller.canConfirm()}
            aria-describedby={`${inputId}-confirm-help`}
            onClick={() => { if (!dialogOpen) void controller.confirm(); }}
          >
            {state.retryConfirmation ? 'Thử xác nhận lại' : 'Xác nhận đề gốc và tiếp tục'}
          </button>
        )}
        {['submitting', 'reloading'].includes(state.phase) && (
          <button type="button" className={buttonClass} onClick={() => controller.cancelRequest()}>
            Dừng chờ
          </button>
        )}
      </div>
      <IncompleteContentDialog
        open={dialogOpen}
        errors={incomplete?.errors ?? []}
        onClose={() => setDismissedCause(state.cause)}
        onChooseFile={() => chooseInput('file')}
        onSwitchToText={() => chooseInput('text')}
      />
    </section>
  );
}

import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  KeyRound,
  Loader2,
  RefreshCw,
  Upload,
  X,
} from 'lucide-react';
import { ingestFile, ingestText, MAX_INGEST_TEXT_LENGTH, validateIngestFile, validateIngestText } from '../../services/ingestion.js';
import { getSessionDetail } from '../../services/sessions.js';
import { confirmSource, getSourceArtifactStatus, isSourceUuid, retrySourceArtifacts } from '../../services/sourceConfirmation.js';
import { useAuthStore } from '../auth/authStore.js';
import { createConfirmationIntentStore } from './confirmationIntent.js';
import { createSourceIngestionController } from './sourceIngestion.js';
import BlueprintStatusCard from './BlueprintStatusCard.jsx';
import SourceQuestionPreview from './SourceQuestionPreview.jsx';
import { readIncompleteError } from './stage1Errors.js';
import IncompleteContentDialog from './IncompleteContentDialog.jsx';

const buttonClass =
  'inline-flex items-center justify-center gap-1.5 rounded-xl border border-line bg-surface px-3.5 py-2 text-sm font-medium text-ink ' +
  'hover:bg-rail hover:text-strong disabled:cursor-not-allowed disabled:opacity-50 transition-colors';

const primaryButtonClass =
  'inline-flex items-center justify-center gap-1.5 rounded-xl bg-highlight px-4 py-2 text-sm font-semibold text-white ' +
  'shadow-soft hover:bg-[#253b57] disabled:cursor-not-allowed disabled:opacity-50 transition-colors';

function fileExtensionBadge(filename) {
  if (typeof filename !== 'string') return 'FILE';
  const dot = filename.lastIndexOf('.');
  return dot >= 0 ? filename.slice(dot + 1).toUpperCase() || 'FILE' : 'FILE';
}

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
  const [isDragging, setIsDragging] = useState(false);
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
  const retryInProgress = state.retryAccepted || state.retryOutcomeUnknown;
  const preparing = state.detail.status === 'blueprinted' && !state.canonicalReady
    && (!state.canonicalStatus || ['pending', 'running'].includes(state.canonicalStatus) || retryInProgress)
    && !state.unavailable;
  useEffect(() => {
    if (!preparing) return;
    // Controller guards prevent overlapping requests and stale account/session updates.
    const timer = setInterval(() => void controller.checkCanonicalStatus(), 2000);
    return () => clearInterval(timer);
  }, [controller, preparing]);
  const busy = state.phase !== 'idle';
  const readOnly = state.detail.status !== 'draft';
  const inputDisabled = busy || readOnly || state.unavailable;
  const uploadPercent = state.upload?.total === null || !state.upload ? undefined
    : Math.min(100, Math.floor(state.upload.loaded / state.upload.total * 100));
  const chooseInput = mode => {
    if (!controller.canSubmit()) return;
    pendingFocus.current = mode;
    setDismissedCause(state.cause);
    setIsDragging(false);
    controller.setMode(mode);
    // Keep the single picker mounted so this click stays in the user's gesture, even from text mode.
    if (mode === 'file') fileInput.current?.click();
  };

  const questionCount = state.detail.source_questions?.length ?? 0;
  const charCount = [...state.text].length;
  const nearCharLimit = charCount > Math.floor(MAX_INGEST_TEXT_LENGTH * 0.9);
  const overCharLimit = charCount > MAX_INGEST_TEXT_LENGTH;
  const missingRevision = !readOnly && questionCount > 0 && !isSourceUuid(state.detail.source_revision);
  const shouldShowReload = !readOnly || state.uncertain || state.requiresReload
    || state.unavailable || state.confirmationPending || state.error || missingRevision;

  const statusText = state.phase === 'submitting' ? state.upload
    ? state.upload.complete ? 'Đã tải tệp lên. Đang xử lý nguồn…'
      : `Đang tải tệp lên${uploadPercent === undefined ? '…' : `: ${uploadPercent}%…`}`
    : 'Đang gửi và xử lý nguồn…'
    : state.phase === 'reloading' ? 'Đang đọc lại nguồn đã lưu…'
      : state.phase === 'confirming' ? 'Đang xác nhận đề nguồn…'
        : state.phase === 'reconciling' ? 'Đang kiểm tra kết quả xác nhận…'
          : state.phase === 'checking_status' ? 'Đang kiểm tra cấu trúc đề…'
            : state.phase === 'retrying_canonical' ? 'Đang yêu cầu chuẩn bị lại cấu trúc đề…' : state.message;

  const canConfirmReady = controller.canConfirm();
  const ingestIsPrimary = questionCount === 0 || state.isInputDirty;

  return (
    <section aria-label="Nhập nguồn đề" className="mt-3 flex min-h-0 flex-1 flex-col gap-3">
      {/* Mobile Tab Switcher */}
      {!readOnly && (
        <div className="flex md:hidden rounded-xl border border-line bg-surface p-1 shadow-soft shrink-0" role="group" aria-label="Vùng làm việc">
          <button
            type="button"
            className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold transition-colors ${
              mobileTab === 'input' ? 'bg-highlight text-white shadow-sm' : 'text-muted hover:text-ink'
            }`}
            aria-pressed={mobileTab === 'input'}
            onClick={() => setMobileTab('input')}
          >
            Bộ nạp nguồn
          </button>
          <button
            type="button"
            className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold transition-colors relative ${
              mobileTab === 'preview' ? 'bg-highlight text-white shadow-sm' : 'text-muted hover:text-ink'
            }`}
            aria-pressed={mobileTab === 'preview'}
            onClick={() => setMobileTab('preview')}
          >
            {`Bản đọc (${questionCount} câu)`}
          </button>
        </div>
      )}

      {state.error && (
        <div
          role="alert"
          aria-hidden={dialogOpen || undefined}
          id={`${inputId}-error`}
          className="shrink-0 flex items-start gap-2.5 rounded-xl border border-danger-border bg-danger-soft p-3.5 text-sm font-medium text-danger"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{state.error}</span>
        </div>
      )}
      {state.confirmationError && (
        <div
          role="alert"
          className="shrink-0 flex items-start gap-2.5 rounded-xl border border-danger-border bg-danger-soft p-3.5 text-sm font-medium text-danger"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{state.confirmationError}</span>
        </div>
      )}

      {(statusText || state.upload) && (
        <div className="shrink-0 space-y-2 rounded-xl border border-line bg-surface px-4 py-2.5 shadow-soft">
          <p role="status" aria-live="polite" className="flex items-center gap-2 text-xs sm:text-sm font-medium text-muted">
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-highlight shrink-0" aria-hidden="true" />}
            <span>{statusText}</span>
          </p>
          {state.upload && (
            <progress
              aria-label="Tiến độ tải tệp lên"
              className="w-full h-2 overflow-hidden rounded-full [&::-webkit-progress-bar]:bg-rail [&::-webkit-progress-value]:bg-highlight [&::-moz-progress-bar]:bg-highlight"
              max="100"
              value={uploadPercent}
            />
          )}
        </div>
      )}

      {/* Preserve role="status" node stably in DOM for screen readers even when idle without message */}
      {!statusText && !state.upload && (
        <p role="status" aria-live="polite" className="sr-only" />
      )}

      {readOnly && (
        <div className="shrink-0 flex items-center gap-2 rounded-xl border border-line bg-rail px-4 py-3 text-sm text-ink">
          <AlertTriangle className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
          <p>Phiên không còn ở trạng thái nháp. Bạn chỉ có thể đọc nguồn tại đây.</p>
        </div>
      )}

      {state.detail.status === 'blueprinted' && (
        <BlueprintStatusCard
          status={state.canonicalStatus}
          ready={state.canonicalReady}
          retryAccepted={state.retryAccepted}
          retryOutcomeUnknown={state.retryOutcomeUnknown}
          progress={state.canonicalProgress}
          busy={busy}
          onRetry={() => void controller.retryCanonical()}
          onProceed={() => controller.proceedToStage2()}
        />
      )}

      {state.canonicalError && (
        <div role="alert" className="shrink-0 rounded-xl border border-danger-border bg-danger-soft p-3.5 text-sm text-danger flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <p className="font-medium">{state.canonicalError}</p>
          </div>
          {state.unavailable && (
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => void controller.checkCanonicalStatus()}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Kiểm tra trạng thái</span>
            </button>
          )}
        </div>
      )}

      {/* Workspace Split Grid */}
      <div className={`grid min-h-[24rem] flex-1 gap-4 ${readOnly ? 'grid-cols-1' : 'md:grid-cols-2'}`}>
        {!readOnly && (
          <form
            id={`${inputId}-form`}
            aria-label="Nhập nguồn"
            className={`min-h-[24rem] md:max-h-[calc(100dvh-13rem)] flex-col gap-3.5 overflow-auto rounded-2xl border border-line bg-surface p-4 sm:p-5 shadow-soft ${
              mobileTab === 'input' ? 'flex' : 'hidden md:flex'
            }`}
            onSubmit={(event) => {
              event.preventDefault();
              if (!controller.canSubmit()) return;
              setDismissedCause(null);
              void controller.submit();
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
              <div role="group" aria-label="Cách nhập nguồn" className="inline-flex rounded-xl border border-line bg-rail p-1 gap-1">
                <button
                  type="button"
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    state.mode === 'text'
                      ? 'bg-highlight text-white shadow-sm'
                      : 'text-ink hover:bg-surface hover:text-strong'
                  } disabled:opacity-50`}
                  aria-pressed={state.mode === 'text'}
                  disabled={inputDisabled}
                  onClick={() => {
                    setIsDragging(false);
                    controller.setMode('text');
                  }}
                >
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Nhập trực tiếp</span>
                </button>
                <button
                  type="button"
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    state.mode === 'file'
                      ? 'bg-highlight text-white shadow-sm'
                      : 'text-ink hover:bg-surface hover:text-strong'
                  } disabled:opacity-50`}
                  aria-pressed={state.mode === 'file'}
                  disabled={inputDisabled}
                  onClick={() => controller.setMode('file')}
                >
                  <Upload className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Tải tệp</span>
                </button>
              </div>

              {state.mode === 'text' && (
                <span
                  className={`text-xs font-medium tabular-nums ${
                    overCharLimit ? 'text-danger font-semibold' : nearCharLimit ? 'text-accent-ink' : 'text-muted'
                  }`}
                >
                  {charCount.toLocaleString('vi-VN')} / 100.000 ký tự
                </span>
              )}
            </div>

            {state.mode === 'text' && (
              <>
                <div>
                  <label htmlFor={inputId} className="text-sm font-semibold text-strong">
                    Nhập trực tiếp
                  </label>
                  <p id={`${inputId}-help`} className="mt-0.5 text-xs text-muted">
                    Tối đa 100.000 ký tự. Đề và đáp án phải có trong cùng nội dung nhập.
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
                  placeholder="Dán hoặc nhập đề thi (1–20 câu, kèm phương án A–D và đáp án đúng) tại đây…"
                  className="min-h-[13rem] flex-1 resize-y rounded-xl border border-control-border/60 bg-white p-3.5 text-sm text-strong leading-relaxed focus:outline-none focus:border-highlight focus:ring-2 focus:ring-highlight/20 transition-all"
                />
                <details className="rounded-xl border border-line bg-canvas/70 px-3.5 py-2.5 text-xs text-muted">
                  <summary className="cursor-pointer font-semibold text-ink select-none">
                    Gợi ý định dạng đề nguồn chuẩn
                  </summary>
                  <pre className="mt-2 whitespace-pre-wrap rounded-lg border border-line bg-surface p-2.5 font-mono text-[11px] leading-relaxed text-strong">
                    {'Câu 1: Rút gọn $\\frac{x^2-9}{x-3}$, với $x \\neq 3$.\nA. $x-3$\nB. $x+3$\nC. $x$\nD. $3$\nĐáp án: B'}
                  </pre>
                </details>
              </>
            )}

            <div
              hidden={state.mode !== 'file'}
              className={
                state.mode === 'file'
                  ? `flex min-h-[14rem] flex-1 flex-col justify-between gap-3 rounded-xl border-2 border-dashed p-5 transition-colors ${
                      isDragging
                        ? 'border-highlight bg-support-bg/80'
                        : 'border-support-line bg-support-bg/40 hover:bg-support-bg/70'
                    }`
                  : 'hidden'
              }
              onDragEnter={(event) => {
                event.preventDefault();
                if (!inputDisabled) setIsDragging(true);
              }}
              onDragOver={(event) => {
                event.preventDefault();
                if (!inputDisabled && !isDragging) setIsDragging(true);
              }}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) {
                  setIsDragging(false);
                }
              }}
              onDrop={(event) => {
                event.preventDefault();
                setIsDragging(false);
                if (!inputDisabled) controller.selectFiles(Array.from(event.dataTransfer.files));
              }}
            >
              <div className="space-y-2">
                <div className="flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-support-line bg-surface text-highlight">
                    <Upload className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div>
                    <label htmlFor={`${inputId}-file`} className="text-sm font-semibold text-strong">
                      Chọn hoặc kéo thả một tệp đề nguồn
                    </label>
                    <p id={`${inputId}-file-help`} className="mt-0.5 text-xs text-muted leading-relaxed">
                      DOCX, TeX hoặc MD, tối đa 10MB. Không nhận PDF. Chọn tệp xong, bấm Nạp nguồn để gửi.
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {['DOCX', 'TEX', 'MD'].map((ext) => (
                    <span key={ext} className="rounded-md border border-support-line bg-surface px-2 py-0.5 text-[11px] font-semibold text-highlight">
                      .{ext.toLowerCase()}
                    </span>
                  ))}
                  <span className="rounded-md border border-danger-border bg-danger-soft/60 px-2 py-0.5 text-[11px] font-medium text-danger">
                    Không nhận .pdf
                  </span>
                </div>
              </div>

              <input
                ref={fileInput}
                id={`${inputId}-file`}
                type="file"
                accept=".docx,.tex,.md"
                disabled={inputDisabled}
                className="w-full min-w-0 rounded-xl border border-line bg-surface p-2 text-sm text-muted file:mr-3 file:min-h-11 file:py-1.5 file:px-3.5 file:rounded-lg file:border file:border-line file:bg-rail file:text-sm file:font-semibold file:text-strong hover:file:bg-support-bg cursor-pointer"
                aria-describedby={`${inputId}-file-help${state.error ? ` ${inputId}-error` : ''}`}
                aria-invalid={state.cause?.code === 'ERR_INGEST_INPUT'}
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  // Reset the native selection so the same file can fire change after editing/retrying.
                  event.target.value = '';
                  if (files.length) controller.selectFiles(files);
                }}
              />

              <div className="rounded-xl border border-line bg-surface p-3.5 space-y-2.5">
                {state.file ? (
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-support-line bg-support-bg text-[10px] font-bold text-highlight">
                        {fileExtensionBadge(state.file.name)}
                      </span>
                      <p className="text-sm font-medium text-strong break-all">
                        {`Đã chọn: ${state.file.name} (${state.file.size.toLocaleString('vi-VN')} byte)`}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted">Chưa chọn tệp.</p>
                )}

                {state.file && (
                  <button
                    type="button"
                    className={`${buttonClass} self-start`}
                    disabled={inputDisabled}
                    onClick={() => controller.clearFile()}
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Bỏ chọn tệp</span>
                  </button>
                )}
              </div>
            </div>
          </form>
        )}

        <div
          className={`min-h-[24rem] ${readOnly ? '' : 'md:max-h-[calc(100dvh-13rem)]'} flex-col overflow-auto ${
            readOnly || mobileTab === 'preview' ? 'flex' : 'hidden md:flex'
          }`}
        >
          {state.isInputDirty && (
            <div role="status" className="shrink-0 mb-3 flex items-start gap-2.5 rounded-xl border border-accent-border bg-accent-soft p-3 text-xs text-accent-ink font-medium">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <div>
                <span className="font-bold block mb-0.5">Nguồn đã thay đổi — bản đọc chưa cập nhật</span>
                <span>Nội dung đã thay đổi. Nạp lại để cập nhật bản đọc.</span>
              </div>
            </div>
          )}
          {state.unavailable ? (
            <div className="rounded-2xl border border-line bg-surface p-6 text-sm text-muted shadow-soft flex items-center gap-2.5">
              <AlertCircle className="h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
              <p>Chưa thể hiển thị nguồn. Hãy kiểm tra lại quyền truy cập phiên.</p>
            </div>
          ) : (
            <SourceQuestionPreview questions={state.detail.source_questions} />
          )}
        </div>
      </div>

      {/* Action Footer Card */}
      <footer className="shrink-0 rounded-2xl border border-line bg-surface px-4 py-3.5 shadow-soft flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {!readOnly ? (
          <p
            id={`${inputId}-confirm-help`}
            className={`text-xs leading-relaxed ${
              state.isInputDirty || state.retryConfirmation || missingRevision
                ? 'font-medium text-accent-ink'
                : canConfirmReady
                  ? 'font-medium text-approved-ink'
                  : 'text-muted'
            }`}
          >
            {state.isInputDirty
              ? 'Nội dung đã thay đổi. Nạp lại để cập nhật bản đọc.'
              : state.retryConfirmation
                ? 'Chưa thấy kết quả xác nhận. Bạn có thể thử lại lần xác nhận trước.'
                : missingRevision
                  ? 'Bản đề này chưa thể xác nhận. Hãy đọc lại nguồn đã lưu.'
                  : 'Xác nhận bản đề đang hiển thị. Nếu đã sửa nội dung nhập, hãy nạp lại trước khi xác nhận.'}
          </p>
        ) : (
          <span className="text-xs text-muted">Chế độ chỉ đọc theo trạng thái phiên hiện tại.</span>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {controller.canRecoverStorage() && (
            <button
              type="button"
              className={buttonClass}
              onClick={() => void controller.recoverConfirmationStorage()}
            >
              <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Khôi phục thông tin xác nhận</span>
            </button>
          )}
          {!readOnly && (
            <button
              type="submit"
              form={`${inputId}-form`}
              className={ingestIsPrimary ? primaryButtonClass : buttonClass}
              disabled={!controller.canSubmit()}
            >
              <Upload className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Nạp nguồn</span>
            </button>
          )}
          {shouldShowReload && (
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => void controller.reload()}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{state.confirmationPending ? 'Đọc lại trạng thái phiên' : 'Đọc lại nguồn đã lưu'}</span>
            </button>
          )}
          {!readOnly && questionCount > 0 && (
            <button
              type="button"
              className={
                state.retryConfirmation
                  ? 'inline-flex items-center justify-center gap-1.5 rounded-xl border border-accent-border bg-accent-soft px-4 py-2 text-sm font-semibold text-accent-ink hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50 transition-colors'
                  : primaryButtonClass
              }
              disabled={dialogOpen || !canConfirmReady}
              aria-describedby={`${inputId}-confirm-help`}
              onClick={() => { if (!dialogOpen) void controller.confirm(); }}
            >
              {state.retryConfirmation ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Thử xác nhận lại</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Xác nhận đề gốc và tiếp tục</span>
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </>
              )}
            </button>
          )}
          {['submitting', 'reloading'].includes(state.phase) && (
            <button
              type="button"
              className={buttonClass}
              onClick={() => controller.cancelRequest()}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Dừng chờ</span>
            </button>
          )}
        </div>
      </footer>

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

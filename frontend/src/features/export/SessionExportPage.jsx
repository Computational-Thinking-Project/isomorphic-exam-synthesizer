import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronLeft,
  Download,
  FileArchive,
  FileText,
  GraduationCap,
  Loader2,
  Lock,
  RefreshCw,
} from 'lucide-react';
import { stage3PreviewPath } from '../../sessionPaths.js';
import { useAuthStore } from '../auth/authStore.js';
import { getSessionDetail } from '../../services/sessions.js';
import {
  getExportStatus,
  triggerExport as defaultTriggerExport,
  issueDownloadUrl as defaultIssueDownloadUrl,
} from '../../services/exportService.js';
import { createExportController } from './exportController.js';

const buttonClass =
  'inline-flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-semibold text-strong hover:bg-rail disabled:cursor-not-allowed disabled:opacity-50 transition-colors shadow-sm';
const primaryButtonClass =
  'inline-flex items-center gap-2 rounded-xl bg-highlight px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#253b57] disabled:cursor-not-allowed disabled:opacity-50 transition-all shadow-soft';

function formatBundleSize(sizeBytes) {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) return '';
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  const kb = sizeBytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(2)} MB`;
}

function defaultOpenDownload(url, filename) {
  if (typeof document === 'undefined') return;
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || 'exam_bundle.zip';
  link.rel = 'noopener noreferrer';
  link.click();
}

export default function SessionExportPage({
  loadSession = getSessionDetail,
  getStatus = getExportStatus,
  triggerExport = defaultTriggerExport,
  issueDownloadUrl = defaultIssueDownloadUrl,
  openDownload = defaultOpenDownload,
}) {
  const { sessionId } = useParams();
  const accountKey = useAuthStore((state) => `${state.user?.id ?? ''}:${state.sessionVersion}`);

  return (
    <SessionExportView
      key={`${accountKey}:${sessionId}`}
      sessionId={sessionId}
      accountKey={accountKey}
      loadSession={loadSession}
      getStatus={getStatus}
      triggerExport={triggerExport}
      issueDownloadUrl={issueDownloadUrl}
      openDownload={openDownload}
    />
  );
}

function SessionExportView({
  sessionId,
  accountKey,
  loadSession,
  getStatus,
  triggerExport,
  issueDownloadUrl,
  openDownload,
}) {
  const isCurrent = useCallback(() => {
    const auth = useAuthStore.getState();
    return auth.status === 'authenticated' && `${auth.user?.id ?? ''}:${auth.sessionVersion}` === accountKey;
  }, [accountKey]);

  const [controller] = useState(() =>
    createExportController({
      loadSession,
      getStatus,
      triggerExport,
      issueDownloadUrl,
      openDownload,
      isCurrent,
    }),
  );

  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );

  useEffect(() => {
    void controller.load(sessionId);
    return () => controller.cancel();
  }, [controller, sessionId]);

  const isBusy = state.busyAction !== null;
  const previewLink = sessionId ? stage3PreviewPath(sessionId) : '/dashboard';
  const showZipContents = ['ready_to_export', 'preparing', 'poll_timeout', 'ready_to_download', 'failed'].includes(state.phase);
  const statusLabel = state.detail?.status === 'exported'
    ? 'Đã xuất gói đề'
    : state.detail?.status === 'approved'
    ? 'Đã phê duyệt cuối'
    : state.detail?.status;
  const artifactSizeText = formatBundleSize(state.artifact?.size_bytes ?? state.artifact?.size);

  return (
    <div className="paper-ui min-h-screen bg-canvas text-strong font-sans py-6 sm:py-8 px-4 sm:px-6 lg:px-8">
      <main className="mx-auto max-w-3xl space-y-6">
        {/* Top Session Navigation & Step Badge (đồng bộ PR #100 + ui-walkthrough S08) */}
        <header className="space-y-3 border-b border-line pb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Link
                to="/dashboard"
                className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-highlight hover:bg-support-bg transition-colors"
              >
                <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Thư viện đề</span>
              </Link>
              <span className="text-line" aria-hidden="true">/</span>
              <span className="inline-flex shrink-0 items-center rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 text-xs font-semibold text-highlight">
                Bước 3/3 · Xuất đề &amp; Tải gói ZIP
              </span>
            </div>
            <Link
              to={previewLink}
              data-testid="export-link-preview"
              className="inline-flex items-center gap-1.5 rounded-lg border border-support-line bg-support-bg px-3 py-1 text-xs font-semibold text-highlight hover:bg-highlight hover:text-white transition-colors"
            >
              <FileText className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Xem bản đã duyệt</span>
            </Link>
          </div>

          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-strong">Xuất đề &amp; Tải gói ZIP</h1>
            <p className="mt-1 text-sm text-muted leading-relaxed">
              Đóng gói và tải về một gói ZIP duy nhất chứa đề thi PDF, nguồn LaTeX, Markdown cùng ma trận đáp án và lời giải chi tiết đã được khóa.
            </p>
          </div>
        </header>

        {state.phase === 'loading' && (
          <div role="status" className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-6 text-muted shadow-soft">
            <Loader2 className="w-5 h-5 animate-spin text-highlight" />
            <p className="text-sm">Đang tải thông tin xuất đề…</p>
          </div>
        )}

        {state.detail && (
          <section className="rounded-2xl border border-line bg-surface p-6 sm:p-8 shadow-paper space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4">
              <div className="min-w-0 flex-1">
                <h2 className="break-words text-xl font-bold text-strong">{state.detail.title}</h2>
                <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 font-medium text-highlight">
                    <BookOpen className="h-3 w-3" aria-hidden="true" />
                    Môn: {state.detail.subject || 'Chưa ghi'}
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 font-medium text-highlight">
                    <GraduationCap className="h-3 w-3" aria-hidden="true" />
                    Khối {state.detail.grade}
                  </span>
                </div>
              </div>
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-approved-bg px-3 py-1 text-xs font-semibold text-approved-ink border border-approved-border">
                <Lock className="h-3 w-3" aria-hidden="true" />
                {statusLabel}
              </span>
            </div>

            {showZipContents && (
              <div
                data-testid="zip-structure-info"
                className="rounded-xl border border-line bg-canvas p-4 space-y-2 text-xs text-ink"
              >
                <div className="flex items-center gap-2 font-semibold text-strong">
                  <FileArchive className="h-4 w-4 text-highlight shrink-0" aria-hidden="true" />
                  <span>Nội dung gói ZIP (w4-export-v2 · chỉ tải trọn gói)</span>
                </div>
                <ul className="list-disc pl-5 space-y-1 text-muted">
                  <li>
                    Mỗi mã đề có 1 file PDF (<code className="text-strong">pdf/exam_&lt;mã&gt;.pdf</code>), 1 nguồn XeLaTeX (<code className="text-strong">latex/exam_&lt;mã&gt;.tex</code>) và 1 Markdown (<code className="text-strong">markdown/exam_&lt;mã&gt;.md</code>).
                  </li>
                  <li>
                    Cấu trúc mỗi tài liệu gồm: <strong>đề thi</strong> &rarr; <strong>ma trận đáp án</strong> &rarr; <strong>lời giải chi tiết</strong> (không hỗ trợ tải lẻ từng file hoặc từng mã).
                  </li>
                  <li>
                    Lưu ý khi phát đề: file đã kèm ma trận đáp án và lời giải ở các trang sau; chỉ gửi phần trang đề thi cho thí sinh.
                  </li>
                </ul>
              </div>
            )}

            {state.phase === 'blocked' && (
              <div role="alert" className="rounded-xl border border-accent-border bg-accent-soft p-4 text-xs text-accent-ink flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 shrink-0 text-accent-ink mt-0.5" />
                <p>{state.error}</p>
              </div>
            )}

            {state.phase === 'unwired' && (
              <div role="status" className="rounded-xl border border-support-line bg-support-bg p-4 text-xs text-highlight flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 shrink-0 text-highlight mt-0.5" />
                <p>
                  Phiên đã sẵn sàng để xuất đề, nhưng tính năng xuất file hoàn chỉnh chưa được nối vào giao diện.
                </p>
              </div>
            )}

            {state.phase === 'ready_to_export' && (
              <div className="space-y-4">
                <p className="text-sm text-ink leading-relaxed">
                  Đề thi đã được duyệt cuối. Bấm nút bên dưới để đóng gói PDF, LaTeX, Markdown và đáp án thành file ZIP.
                </p>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.startExport()}
                    className={primaryButtonClass}
                  >
                    {state.busyAction === 'export' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang khởi tạo đóng gói…</span>
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" />
                        <span>Tạo gói ZIP</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'preparing' && (
              <div className="space-y-4">
                <div role="status" className="rounded-xl border border-support-line bg-support-bg p-4 text-xs text-highlight flex items-center gap-3">
                  <Loader2 className="w-4 h-4 animate-spin text-highlight shrink-0" />
                  <p>
                    Đang biên dịch PDF và đóng gói đề thi… Vui lòng giữ nguyên trang hoặc quay lại sau.
                  </p>
                </div>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.refreshStatus()}
                    className={buttonClass}
                  >
                    {state.busyAction === 'refresh' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang kiểm tra…</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        <span>Kiểm tra trạng thái</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'poll_timeout' && (
              <div className="space-y-4">
                <div role="status" className="rounded-xl border border-accent-border bg-accent-soft p-4 text-xs text-accent-ink flex items-start gap-2.5">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-accent-ink mt-0.5" />
                  <p>{state.error}</p>
                </div>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.refreshStatus()}
                    className={buttonClass}
                  >
                    {state.busyAction === 'refresh' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang kiểm tra…</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        <span>Kiểm tra trạng thái</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'ready_to_download' && (
              <div className="space-y-4">
                <div role="status" className="rounded-xl border border-approved-border bg-approved-bg p-4 text-xs text-approved-ink flex items-start gap-2.5">
                  <CheckCircle2 className="w-5 h-5 text-approved-ink shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="font-semibold">
                      Gói đề thi đã sẵn sàng để tải xuống ({state.artifact?.filename}).
                    </p>
                    {artifactSizeText && (
                      <p className="text-[11px] text-approved-ink">
                        Dung lượng gói ZIP: <strong>{artifactSizeText}</strong>
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.download()}
                    className={primaryButtonClass}
                  >
                    {state.busyAction === 'download' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang lấy liên kết tải…</span>
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" />
                        <span>Tải gói ZIP</span>
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.refreshStatus()}
                    className={buttonClass}
                  >
                    <RefreshCw className="w-4 h-4" />
                    <span>Làm mới trạng thái</span>
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'failed' && (
              <div className="space-y-4">
                <div role="alert" className="rounded-xl border border-danger-border bg-danger-soft p-4 text-xs text-danger flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
                  <p>{state.error}</p>
                </div>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.startExport()}
                    className={primaryButtonClass}
                  >
                    {state.busyAction === 'export' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang thử lại…</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        <span>Thử đóng gói lại</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'error' && (
              <div className="space-y-4">
                <div role="alert" className="rounded-xl border border-danger-border bg-danger-soft p-4 text-xs text-danger flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
                  <p>{state.error}</p>
                </div>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.refreshStatus()}
                    className={buttonClass}
                  >
                    <RefreshCw className="w-4 h-4" />
                    <span>Kiểm tra trạng thái</span>
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'ready_to_download' && state.error && (
              <div role="alert" className="rounded-xl border border-danger-border bg-danger-soft p-4 text-xs text-danger flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
                <p>{state.error}</p>
              </div>
            )}
          </section>
        )}

        {!state.detail && state.phase === 'error' && (
          <div className="space-y-4">
            <div role="alert" className="rounded-xl border border-danger-border bg-danger-soft p-4 text-xs text-danger flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
              <p>{state.error}</p>
            </div>
            <div>
              <button
                type="button"
                disabled={isBusy}
                onClick={() => void controller.load(sessionId)}
                className={buttonClass}
              >
                <RefreshCw className="w-4 h-4" />
                <span>Thử tải lại</span>
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

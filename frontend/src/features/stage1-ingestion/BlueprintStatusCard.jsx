import { AlertTriangle, ArrowRight, CheckCircle2, Clock, Loader2, RefreshCw } from 'lucide-react';

const STATUS_META = {
  pending: {
    badge: 'Chờ xử lý',
    heading: 'Đang chờ chuẩn bị cấu trúc đề',
    guidance:
      'Yêu cầu phân tích cấu trúc đề đang ở hàng đợi. Tiến trình sẽ tự cập nhật; chưa thể sang Bước 2 lúc này.',
    cardClass: 'border-accent-border bg-accent-soft/50',
    iconBoxClass: 'bg-surface border border-accent-border text-accent-ink',
    badgeClass: 'border-accent-border bg-surface text-accent-ink',
  },
  running: {
    badge: 'Đang xử lý',
    heading: 'Đang chuẩn bị cấu trúc đề',
    guidance:
      'Hệ thống đang phân tích cấu trúc đề từ các câu nguồn. Nút Tiếp tục cấu hình sẽ mở khi hoàn tất.',
    cardClass: 'border-support-line bg-support-bg/60',
    iconBoxClass: 'bg-surface border border-support-line text-highlight',
    badgeClass: 'border-support-line bg-surface text-highlight',
  },
  ready: {
    badge: 'Sẵn sàng',
    heading: 'Cấu trúc đề đã sẵn sàng',
    guidance: 'Cấu trúc đề đã hoàn tất. Bạn có thể bấm Tiếp tục cấu hình để sang Bước 2 (Tạo mã đề).',
    cardClass: 'border-approved-border bg-approved-bg/60',
    iconBoxClass: 'bg-surface border border-approved-border text-approved-ink',
    badgeClass: 'border-approved-border bg-surface text-approved-ink',
  },
  failed: {
    badge: 'Cần thử lại',
    heading: 'Chưa chuẩn bị được cấu trúc đề',
    guidance: 'Quá trình chuẩn bị bị gián đoạn. Hãy bấm Thử lại để yêu cầu xử lý lại; chưa thể sang Bước 2.',
    cardClass: 'border-danger-border bg-danger-soft/60',
    iconBoxClass: 'bg-surface border border-danger-border text-danger',
    badgeClass: 'border-danger-border bg-surface text-danger',
  },
};

const UNKNOWN_META = {
  badge: 'Đang kiểm tra',
  heading: 'Đang kiểm tra trạng thái chuẩn bị cấu trúc đề',
  guidance: 'Hệ thống đang đồng bộ trạng thái Blueprint từ máy chủ.',
  cardClass: 'border-line bg-surface',
  iconBoxClass: 'bg-support-bg border border-support-line text-highlight',
  badgeClass: 'border-line bg-rail text-muted',
};

function StatusIcon({ status }) {
  if (status === 'pending') return <Clock className="h-5 w-5" aria-hidden="true" />;
  if (status === 'running') return <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />;
  if (status === 'ready') return <CheckCircle2 className="h-5 w-5" aria-hidden="true" />;
  if (status === 'failed') return <AlertTriangle className="h-5 w-5" aria-hidden="true" />;
  return <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />;
}

/**
 * Displays the current backend Blueprint preparation status (pending/running/failed/ready)
 * without exposing internal canonical structures or variation dimensions.
 */
export default function BlueprintStatusCard({
  status,
  ready,
  retryAccepted,
  progress,
  busy,
  onRetry,
  onProceed,
}) {
  const meta = STATUS_META[status] ?? UNKNOWN_META;
  const measuredProgress =
    Number.isInteger(progress?.completed) &&
    Number.isInteger(progress?.total) &&
    progress.total > 0 &&
    progress.completed >= 0;
  const progressPercent = ready
    ? 100
    : measuredProgress
      ? Math.min(99, Math.round((progress.completed / progress.total) * 100))
      : undefined;

  return (
    <section
      aria-label="Trạng thái chuẩn bị cấu trúc đề"
      className={`shrink-0 rounded-2xl border p-4 sm:p-5 shadow-soft transition-colors ${meta.cardClass}`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${meta.iconBoxClass}`}>
            <StatusIcon status={status} />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-medium text-muted">Chuẩn bị cấu trúc đề</p>
              <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold ${meta.badgeClass}`}>
                {meta.badge}
              </span>
            </div>
            <p className="mt-0.5 text-base font-bold text-strong" data-testid="canonical-status-text">
              {status ? meta.heading : ''}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-ink">
              {meta.guidance}
            </p>
            {retryAccepted && (
              <p className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-semibold text-highlight">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                <span>Đã tiếp nhận yêu cầu tạo lại. Tiến độ sẽ tự cập nhật.</span>
              </p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {status === 'failed' && !retryAccepted && (
            <button
              type="button"
              className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-danger-border bg-surface px-4 py-2 text-sm font-semibold text-danger hover:bg-danger-soft disabled:opacity-50 transition-colors"
              disabled={busy}
              onClick={onRetry}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              <span>Thử lại</span>
            </button>
          )}
          <button
            type="button"
            className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-highlight px-4 py-2 text-sm font-semibold text-white shadow-soft hover:bg-[#253b57] disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
            disabled={busy || !ready}
            onClick={onProceed}
          >
            <span>Tiếp tục cấu hình</span>
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="mt-4 space-y-1.5">
        <progress
          aria-label="Tiến độ chuẩn bị cấu trúc đề"
          max="100"
          value={status === 'failed' && !retryAccepted ? (progressPercent ?? 0) : progressPercent}
          className="h-2 w-full overflow-hidden rounded-full accent-highlight [&::-webkit-progress-bar]:bg-surface [&::-webkit-progress-value]:bg-highlight [&::-moz-progress-bar]:bg-highlight"
        />
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
          <p role="status">
            {ready
              ? 'Hoàn tất · 100%'
              : status === 'failed' && !retryAccepted
                ? 'Chuẩn bị chưa thành công. Hãy thử lại.'
                : measuredProgress
                  ? `${Math.min(progress.completed, progress.total)}/${progress.total} câu đã chuẩn bị`
                  : 'Đang chuẩn bị cấu trúc đề. Tiến độ sẽ tự cập nhật.'}
          </p>
          {Number.isInteger(progressPercent) && !ready && (
            <span className="font-semibold text-strong">{progressPercent}%</span>
          )}
        </div>
      </div>
    </section>
  );
}

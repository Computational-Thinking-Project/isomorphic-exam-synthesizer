import { Calendar, Clock, Copy, ExternalLink, FileText, Loader2 } from 'lucide-react';

const statusLabels = {
  draft: 'Đang chuẩn bị',
  blueprinted: 'Đã xác nhận đề gốc',
  configured: 'Đã cấu hình sinh đề',
  generating: 'Đang sinh đề',
  partial_generated: 'Đã sinh một phần',
  generated: 'Đã sinh đề',
  reviewed: 'Đã duyệt các câu',
  approved: 'Đã chốt',
  exported: 'Đã xuất',
  failed: 'Sinh đề gặp lỗi',
};

const statusStyles = {
  draft: 'bg-accent-soft text-accent-ink border-accent-border font-medium',
  blueprinted: 'bg-support-bg text-highlight border-support-line font-medium',
  configured: 'bg-support-bg text-highlight border-support-line font-medium',
  generating: 'bg-accent-soft text-accent-ink border-accent-border font-medium animate-pulse',
  partial_generated: 'bg-accent-soft text-accent-ink border-accent-border font-medium',
  generated: 'bg-sky-50 text-sky-800 border-sky-200 font-medium',
  reviewed: 'bg-sky-50 text-sky-800 border-sky-200 font-medium',
  approved: 'bg-approved-bg text-approved-ink border-approved-border font-semibold',
  exported: 'bg-rail text-ink border-line font-medium',
  failed: 'bg-danger-soft text-danger border-danger-border font-semibold',
};

function formatCreatedAt(value) {
  if (!value) return 'Chưa có ngày tạo';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Chưa có ngày tạo'
    : date.toLocaleDateString('vi-VN');
}

export default function DashboardSessionCard({
  session,
  onOpen,
  onClone,
  openingSessionId = null,
}) {
  const isReadOnly = ['approved', 'exported'].includes(session.status);
  const statusLabel = Object.hasOwn(statusLabels, session.status)
    ? statusLabels[session.status]
    : 'Chưa xác định';
  const statusStyle = Object.hasOwn(statusStyles, session.status)
    ? statusStyles[session.status]
    : 'bg-zinc-100 text-zinc-700 border-zinc-200 font-medium';

  const isCurrentOpening = openingSessionId === session.id;

  return (
    <article className="group relative bg-surface hover:bg-rail/60 transition-colors p-4 sm:px-6 sm:py-4">
      <div className="flex flex-col lg:grid lg:grid-cols-[minmax(240px,1fr)_140px_110px_220px] lg:items-center gap-3.5 lg:gap-4">
        {/* Column 1: Document icon & Title copy */}
        <div className="flex items-start sm:items-center gap-3.5 min-w-0">
          <div
            className={`flex h-10 w-9 shrink-0 items-center justify-center rounded-lg border transition-colors ${
              session.status === 'draft'
                ? 'border-accent-border/60 bg-accent-soft text-accent-ink'
                : isReadOnly
                ? 'border-line bg-rail text-muted'
                : 'border-support-line bg-support-bg text-highlight'
            }`}
          >
            <FileText className="h-5 w-5" aria-hidden="true" />
          </div>

          <div className="min-w-0 flex-1">
            <h2 className="break-words text-sm sm:text-base font-bold text-strong group-hover:text-highlight transition-colors leading-snug">
              {session.title || 'Đề chưa đặt tên'}
            </h2>
            <div className="flex items-center gap-1.5 text-xs text-muted mt-0.5 truncate flex-wrap">
              <span className="font-semibold text-strong">{session.subject || 'Toán'}</span>
              {session.grade && (
                <>
                  <span className="h-1 w-1 rounded-full bg-muted/40" aria-hidden="true" />
                  <span>K{session.grade}</span>
                </>
              )}
              {isReadOnly && <span>· Chỉ xem</span>}
            </div>
          </div>
        </div>

        {/* Column 2: Status pill */}
        <div className="flex items-center">
          <span
            className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs ${statusStyle}`}
          >
            {session.status === 'draft' ? (
              <Clock className="h-3 w-3" aria-hidden="true" />
            ) : null}
            <span>{statusLabel}</span>
          </span>
        </div>

        {/* Column 3: Created date */}
        <div className="flex items-center gap-1.5 text-xs text-muted">
          <Calendar className="h-3.5 w-3.5 text-muted/70 lg:hidden" aria-hidden="true" />
          <time dateTime={session.created_at}>{formatCreatedAt(session.created_at)}</time>
        </div>

        {/* Column 4: Actions */}
        <div className="flex items-center gap-2 justify-end pt-2 lg:pt-0 border-t lg:border-t-0 border-line/40">
          <button
            type="button"
            disabled={!onClone}
            onClick={() => onClone(session)}
            title="Nhân bản phiên này"
            className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-semibold text-strong hover:bg-rail hover:border-zinc-300 transition-all disabled:opacity-50"
          >
            <Copy className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
            <span>Nhân bản</span>
          </button>

          <button
            type="button"
            disabled={!onOpen || openingSessionId !== null}
            onClick={() => onOpen(session)}
            className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg bg-highlight px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-[#253b57] transition-all disabled:opacity-50 min-w-[88px]"
          >
            {isCurrentOpening ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                <span>Đang mở…</span>
              </>
            ) : isReadOnly ? (
              <>
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Mở bộ đề</span>
              </>
            ) : ['partial_generated', 'generated'].includes(session.status) ? (
              <span>Tiếp tục duyệt</span>
            ) : (
              <span>Tiếp tục</span>
            )}
          </button>
        </div>
      </div>
    </article>
  );
}

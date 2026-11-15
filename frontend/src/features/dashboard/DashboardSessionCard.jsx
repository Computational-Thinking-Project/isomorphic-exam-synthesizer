import { BookOpen, Calendar, Clock, Copy, ExternalLink, FileText, GraduationCap, Loader2 } from 'lucide-react';

const statusLabels = {
  draft: 'Đang chuẩn bị',
  blueprinted: 'Đã xác nhận quy tắc',
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
    <article className="group relative flex h-full flex-col justify-between rounded-2xl border border-line bg-surface p-5 sm:p-6 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-zinc-300 hover:shadow-paper">
      {/* Top Section */}
      <div>
        <div className="flex items-start gap-3.5">
          {/* Document Sheet Icon styled like PREVIEW.html */}
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
            <div className="flex items-start justify-between gap-2">
              <h2 className="line-clamp-2 break-words text-base font-bold tracking-tight text-strong group-hover:text-highlight transition-colors leading-snug">
                {session.title || 'Đề chưa đặt tên'}
              </h2>
            </div>

            <p className="mt-1 text-xs text-muted flex items-center gap-1.5 flex-wrap">
              <span>{isReadOnly ? 'Bản đã chốt · chỉ xem' : 'Bản nháp · có thể chỉnh sửa'}</span>
            </p>
          </div>
        </div>

        {/* Status Pill & Metadata Row */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line/50 pt-3">
          <span
            className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs ${statusStyle}`}
          >
            {session.status === 'draft' ? (
              <Clock className="h-3 w-3" aria-hidden="true" />
            ) : null}
            <span>{statusLabel}</span>
          </span>

          <dl className="flex items-center gap-2.5 text-xs text-muted">
            <div className="inline-flex items-center gap-1">
              <BookOpen className="h-3.5 w-3.5 text-highlight/70" aria-hidden="true" />
              <dt className="sr-only">Môn học:</dt>
              <dd className="font-medium text-strong">{session.subject || 'Chưa có môn'}</dd>
            </div>

            {session.grade && (
              <>
                <span className="h-1 w-1 rounded-full bg-muted/40" aria-hidden="true" />
                <div className="inline-flex items-center gap-1">
                  <GraduationCap className="h-3.5 w-3.5 text-highlight/70" aria-hidden="true" />
                  <dt className="sr-only">Khối lớp:</dt>
                  <dd className="font-medium text-strong">K{session.grade}</dd>
                </div>
              </>
            )}
          </dl>
        </div>
      </div>

      {/* Bottom Action Footer */}
      <div className="mt-5 flex items-center justify-between gap-3 pt-3.5 border-t border-line/60">
        <div className="flex items-center gap-1.5 text-xs text-muted">
          <Calendar className="h-3.5 w-3.5 text-muted/70" aria-hidden="true" />
          <time dateTime={session.created_at}>{formatCreatedAt(session.created_at)}</time>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={!onClone}
            onClick={() => onClone(session)}
            title="Nhân bản phiên này"
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-line bg-surface px-3 py-2 text-xs font-semibold text-strong transition-all hover:bg-rail hover:border-zinc-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Copy className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
            <span className="hidden sm:inline">Nhân bản</span>
          </button>

          <button
            type="button"
            disabled={!onOpen || openingSessionId !== null}
            onClick={() => onOpen(session)}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-highlight px-4 py-2 text-xs font-semibold text-white shadow-sm transition-all hover:bg-[#253b57] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 min-w-[96px]"
          >
            {isCurrentOpening ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                <span>Đang mở…</span>
              </>
            ) : isReadOnly ? (
              <>
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Xem đề</span>
              </>
            ) : (
              <>
                <span>Tiếp tục</span>
              </>
            )}
          </button>
        </div>
      </div>
    </article>
  );
}

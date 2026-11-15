import { BookOpen, Calendar, Copy, ExternalLink, GraduationCap, Loader2 } from 'lucide-react';

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
  draft: 'bg-zinc-100 text-zinc-700 border-zinc-200',
  blueprinted: 'bg-support-bg text-highlight border-support-line',
  configured: 'bg-accent-soft text-accent-ink border-accent-border',
  generating: 'bg-accent-soft text-accent-ink border-accent-border animate-pulse',
  partial_generated: 'bg-accent-soft text-accent-ink border-accent-border',
  generated: 'bg-sky-50 text-sky-800 border-sky-200',
  reviewed: 'bg-sky-50 text-sky-800 border-sky-200',
  approved: 'bg-approved-bg text-approved-ink border-approved-border font-medium',
  exported: 'bg-approved-bg text-approved-ink border-approved-border font-medium',
  failed: 'bg-danger-soft text-danger border-danger-border font-medium',
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
    : 'bg-zinc-100 text-zinc-700 border-zinc-200';

  const isCurrentOpening = openingSessionId === session.id;

  return (
    <article className="group flex h-full flex-col justify-between rounded-2xl border border-line bg-surface p-5 sm:p-6 shadow-card transition-all hover:border-zinc-300 hover:shadow-paper">
      <div>
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 flex-1 break-words text-base sm:text-lg font-bold tracking-tight text-strong group-hover:text-highlight transition-colors">
            {session.title || 'Đề chưa đặt tên'}
          </h2>

          <span
            className={`shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-medium ${statusStyle}`}
          >
            {statusLabel}
          </span>
        </div>

        <dl className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
          <div className="inline-flex items-center gap-1.5">
            <BookOpen className="h-3.5 w-3.5 text-highlight" aria-hidden="true" />
            <dt className="sr-only">Môn học:</dt>
            <dd className="font-medium text-strong">{session.subject || 'Chưa có môn'}</dd>
          </div>

          {session.grade && (
            <div className="inline-flex items-center gap-1.5">
              <GraduationCap className="h-3.5 w-3.5 text-highlight" aria-hidden="true" />
              <dt className="sr-only">Khối lớp:</dt>
              <dd className="font-medium text-strong">Lớp {session.grade}</dd>
            </div>
          )}

          <div className="inline-flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
            <dt className="sr-only">Ngày tạo:</dt>
            <dd>{formatCreatedAt(session.created_at)}</dd>
          </div>
        </dl>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2.5 pt-4 border-t border-line/60">
        <button
          type="button"
          disabled={!onOpen || openingSessionId !== null}
          onClick={() => onOpen(session)}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-highlight px-4 py-2 text-xs font-semibold text-white shadow-sm transition-all hover:bg-[#253b57] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
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

        <button
          type="button"
          disabled={!onClone}
          onClick={() => onClone(session)}
          className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-line bg-surface px-3 py-2 text-xs font-medium text-strong transition-all hover:bg-rail hover:border-zinc-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Copy className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
          <span>Nhân bản</span>
        </button>
      </div>
    </article>
  );
}

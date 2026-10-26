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

const buttonClass =
  'rounded-lg border border-slate-600 px-4 py-2 text-sm ' +
  'hover:bg-slate-800 focus-visible:outline ' +
  'focus-visible:outline-2 focus-visible:outline-offset-4 ' +
  'focus-visible:outline-sky-400 ' +
  'disabled:cursor-not-allowed disabled:opacity-50';

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

  return (
    <article className="rounded-xl border border-slate-700 bg-slate-900 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="min-w-0 break-words text-lg font-semibold">
          {session.title || 'Đề chưa đặt tên'}
        </h2>

        <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
          {statusLabel}
        </span>
      </div>

      <dl className="mt-4 space-y-2 text-sm">
        <div className="flex gap-2">
          <dt className="text-slate-400">Môn:</dt>
          <dd>{session.subject || 'Chưa có môn'}</dd>
        </div>

        <div className="flex gap-2">
          <dt className="text-slate-400">Ngày tạo:</dt>
          <dd>{formatCreatedAt(session.created_at)}</dd>
        </div>
      </dl>

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          type="button"
          className={buttonClass}
          disabled={!onOpen || openingSessionId !== null}
          onClick={() => onOpen(session)}
        >
          {openingSessionId === session.id ? 'Đang mở…' : isReadOnly ? 'Xem đề' : 'Tiếp tục'}
        </button>

        <button
          type="button"
          className={buttonClass}
          disabled={!onClone}
          onClick={() => onClone(session)}
        >
          Nhân bản
        </button>
      </div>
    </article>
  );
}

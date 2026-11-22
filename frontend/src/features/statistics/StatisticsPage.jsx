import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  BarChart2,
  CheckCircle2,
  Clock,
  FileText,
  Layers,
  PackageCheck,
  RefreshCw,
} from 'lucide-react';
import { useAuthStore } from '../auth/authStore.js';
import { getMyStatistics } from '../../services/statistics.js';

const cards = [
  ['total_sessions', 'Tổng số phiên đề'],
  ['in_progress_sessions', 'Đang thực hiện'],
  ['approved_not_exported_sessions', 'Đã duyệt, chưa xuất'],
  ['exported_sessions', 'Đã xuất'],
];

const statuses = [
  ['draft', 'Đang chuẩn bị đề gốc'],
  ['blueprinted', 'Đã xác nhận đề gốc'],
  ['configured', 'Đã cấu hình sinh đề'],
  ['generating', 'Đang sinh đề'],
  ['partial_generated', 'Đã sinh một phần'],
  ['generated', 'Đã sinh đề'],
  ['reviewed', 'Đã duyệt các câu, chờ chốt'],
  ['approved', 'Đã duyệt, chưa xuất'],
  ['exported', 'Đã tạo gói xuất'],
  ['failed', 'Sinh đề gặp lỗi'],
  ['unknown', 'Chưa xác định'],
];

const number = new Intl.NumberFormat('vi-VN');

function getStatusMeta(key) {
  switch (key) {
    case 'draft':
      return {
        barColor: 'bg-slate-500',
        dotColor: 'bg-slate-500',
      };
    case 'blueprinted':
      return {
        barColor: 'bg-sky-500',
        dotColor: 'bg-sky-500',
      };
    case 'configured':
      return {
        barColor: 'bg-indigo-600',
        dotColor: 'bg-indigo-600',
      };
    case 'generating':
      return {
        barColor: 'bg-amber-500',
        dotColor: 'bg-amber-500 animate-pulse',
      };
    case 'partial_generated':
      return {
        barColor: 'bg-amber-600',
        dotColor: 'bg-amber-600',
      };
    case 'generated':
      return {
        barColor: 'bg-violet-600',
        dotColor: 'bg-violet-600',
      };
    case 'reviewed':
      return {
        barColor: 'bg-teal-600',
        dotColor: 'bg-teal-600',
      };
    case 'approved':
      return {
        barColor: 'bg-emerald-600',
        dotColor: 'bg-emerald-600',
      };
    case 'exported':
      return {
        barColor: 'bg-[#304c70]',
        dotColor: 'bg-[#304c70]',
      };
    case 'failed':
      return {
        barColor: 'bg-danger',
        dotColor: 'bg-danger',
      };
    case 'unknown':
    default:
      return {
        barColor: 'bg-muted',
        dotColor: 'bg-muted',
      };
  }
}

/**
 * Phân bố chi tiết trạng thái phiên đề
 */
function StatusChart({ counts, total }) {
  const largest = Math.max(1, ...Object.values(counts));
  const chartColumns = `minmax(0,1fr) ${number.format(largest).length + 1}ch`;
  const visibleStatuses = statuses.filter(([key]) => key !== 'unknown' || counts.unknown > 0);

  return (
    <section
      aria-labelledby="status-chart-title"
      className="rounded-xl border border-line bg-surface p-6 shadow-paper"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-line mb-4">
        <div>
          <div className="flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-highlight" aria-hidden="true" />
            <h2 id="status-chart-title" className="text-base font-bold text-strong">
              Phân bố trạng thái phiên
            </h2>
          </div>
          <p className="mt-0.5 text-xs text-muted">
            Chi tiết các trạng thái dọc theo chuỗi nghiệp vụ sinh đề đẳng cấu
          </p>
        </div>

        {total > 0 && (
          <span className="font-mono tabular-nums text-xs text-muted bg-rail px-2.5 py-1 rounded border border-line self-start sm:self-auto">
            {visibleStatuses.length} trạng thái
          </span>
        )}
      </div>

      {total === 0 ? (
        <div className="py-12 px-4 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-rail text-muted border border-line mb-3">
            <FileText className="h-6 w-6" aria-hidden="true" />
          </div>
          <p className="text-sm font-semibold text-strong">
            Bạn chưa có phiên đề nào trong tài khoản.
          </p>
          <p className="mt-1 text-xs text-muted max-w-sm mx-auto">
            Bắt đầu bằng cách tạo phiên đề mới hoặc nạp tài liệu từ Thư viện đề.
          </p>
          <div className="mt-5">
            <Link
              to="/dashboard"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-highlight px-4 py-2 text-xs font-semibold text-white shadow-soft transition-colors hover:bg-highlight/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 min-h-[44px]"
            >
              <span>Về Thư viện đề</span>
            </Link>
          </div>
        </div>
      ) : (
        <dl className="divide-y divide-line/60">
          {visibleStatuses.map(([key, label]) => {
            const meta = getStatusMeta(key);
            const count = counts[key] ?? 0;
            const barWidth = count > 0 ? Math.max(4, (count / largest) * 100) : 0;
            const isZero = count === 0;

            return (
              <div
                key={key}
                className="group grid items-center gap-x-4 gap-y-1.5 py-2.5 px-2 rounded-lg transition-colors hover:bg-rail/50 sm:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span
                    className={`inline-block h-2 w-2 rounded-full shrink-0 ${isZero ? 'bg-muted/40' : meta.dotColor}`}
                    aria-hidden="true"
                  />
                  <dt className={`break-words text-sm font-medium ${isZero ? 'text-muted' : 'text-strong'}`}>
                    {label}
                  </dt>
                </div>

                <dd className="grid items-center gap-3.5" style={{ gridTemplateColumns: chartColumns }}>
                  <span aria-hidden="true" className="block h-2 overflow-hidden rounded-full bg-rail">
                    <span
                      className={`block h-full rounded-full transition-all duration-500 ease-out ${meta.barColor}`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </span>
                  <span className={`text-right font-mono text-sm tabular-nums ${isZero ? 'text-muted/50' : 'font-bold text-strong'}`}>
                    {number.format(count)}
                  </span>
                </dd>
              </div>
            );
          })}
        </dl>
      )}
    </section>
  );
}

function getCardConfig(key) {
  switch (key) {
    case 'total_sessions':
      return {
        icon: Layers,
        subtitle: 'Toàn bộ phiên lưu trữ',
      };
    case 'in_progress_sessions':
      return {
        icon: Clock,
        subtitle: 'Khởi tạo đến chờ chốt',
      };
    case 'approved_not_exported_sessions':
      return {
        icon: CheckCircle2,
        subtitle: 'Sẵn sàng đóng gói xuất',
      };
    case 'exported_sessions':
      return {
        icon: PackageCheck,
        subtitle: 'Đã hoàn tất gói đề',
      };
    default:
      return {
        icon: FileText,
        subtitle: '',
      };
  }
}

function StatisticsData() {
  const [requestKey, setRequestKey] = useState(0);
  const [result, setResult] = useState({ state: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    getMyStatistics({ signal: controller.signal }).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ state: 'ready', data });
      },
      () => {
        if (!controller.signal.aborted) setResult({ state: 'error' });
      },
    );
    return () => controller.abort();
  }, [requestKey]);

  if (result.state === 'loading') {
    return (
      <div
        className="rounded-xl border border-line bg-surface p-12 shadow-paper text-center min-h-[400px] flex flex-col items-center justify-center"
        aria-busy="true"
        aria-live="polite"
      >
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-rail text-highlight border border-line mb-3 animate-pulse">
          <RefreshCw className="h-5 w-5 animate-spin text-highlight" aria-hidden="true" />
        </div>
        <p role="status" className="text-base font-bold text-strong">
          Đang tải thống kê…
        </p>
        <p className="mt-1 text-xs text-muted max-w-sm mx-auto">
          Đang truy vấn số liệu các phiên đề từ hệ thống…
        </p>
      </div>
    );
  }

  if (result.state === 'error') {
    return (
      <div className="rounded-xl border border-danger-border bg-danger-soft p-8 shadow-paper text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-danger/10 text-danger border border-danger-border mb-3">
          <AlertCircle className="h-6 w-6 text-danger" aria-hidden="true" />
        </div>
        <p role="alert" className="text-base font-bold text-danger">
          Không tải được thống kê.
        </p>
        <p className="mt-1 text-xs text-danger/80 max-w-sm mx-auto leading-relaxed">
          Không thể lấy dữ liệu thống kê từ hệ thống. Kiểm tra kết nối mạng và thử lại.
        </p>
        <button
          type="button"
          className="mt-5 inline-flex items-center justify-center gap-2 rounded-lg bg-danger px-5 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-danger/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger focus-visible:ring-offset-2 min-h-[44px]"
          onClick={() => {
            setResult({ state: 'loading' });
            setRequestKey((key) => key + 1);
          }}
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Thử lại</span>
        </button>
      </div>
    );
  }

  const { data } = result;
  const { failed = 0, unknown = 0 } = data.by_status;
  const remainder = [
    failed > 0 && `${number.format(failed)} phiên sinh đề gặp lỗi`,
    unknown > 0 && `${number.format(unknown)} phiên chưa xác định trạng thái`,
  ].filter(Boolean);

  const total = data.total_sessions || 0;

  return (
    <div className="space-y-6">
      {/* 4 Summary Metrics in a Single Integrated Deck */}
      <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-paper">
        <dl className="grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-y-0 sm:divide-x lg:grid-cols-4">
          {cards.map(([key, label]) => {
            const cfg = getCardConfig(key);
            const count = data[key] || 0;
            const sharePct = total > 0
              ? (key === 'total_sessions' ? 100 : Math.round((count / total) * 100))
              : null;

            return (
              <div
                key={key}
                className="p-5 sm:p-6 flex flex-col justify-between transition-colors hover:bg-rail/20"
              >
                <div>
                  <dt className="text-xs font-bold uppercase tracking-wider text-muted">
                    {label}
                  </dt>

                  <dd className="mt-3 flex items-baseline gap-2">
                    <span className="font-mono text-4xl sm:text-5xl font-bold tracking-tight tabular-nums text-strong">
                      {number.format(count)}
                    </span>
                    <span className="text-xs font-medium text-muted">phiên đề</span>
                  </dd>
                </div>

                {total > 0 && (
                  <div className="mt-4 pt-3 border-t border-line/60 flex items-center justify-between text-xs text-muted">
                    <span className="truncate">{cfg.subtitle}</span>
                    {sharePct !== null && (
                      <span className="font-mono font-semibold text-strong shrink-0 tabular-nums">
                        {sharePct}%
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </dl>
      </div>

      {/* Incident Alert Banner when there are failed or unknown sessions */}
      {remainder.length > 0 && (
        <div className="rounded-xl border border-danger-border bg-danger-soft p-4 sm:p-5 text-sm text-danger shadow-soft flex items-start gap-3.5">
          <div className="p-2 rounded-lg bg-danger/10 text-danger shrink-0 mt-0.5">
            <AlertTriangle className="h-4 w-4 text-danger" aria-hidden="true" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-xs font-bold uppercase tracking-wider text-danger">
              Lưu ý trạng thái phiên đề
            </h3>
            <p className="mt-1 text-sm text-danger/90 leading-relaxed font-medium">
              Tổng số phiên bao gồm {remainder.join(' và ')}.
            </p>
            <p className="mt-1 text-xs text-danger/80">
              Các phiên gặp sự cố có thể thử sinh lại câu hỏi hoặc nhân bản phiên mới từ Thư viện đề.
            </p>
          </div>
        </div>
      )}

      {/* Status Distribution Chart */}
      <StatusChart counts={data.by_status} total={data.total_sessions} />
    </div>
  );
}

export default function StatisticsPage() {
  const accountKey = useAuthStore((state) => `${state.user?.id ?? ''}:${state.sessionVersion}`);

  return (
    <div className="paper-ui min-h-screen bg-canvas text-ink">
      <main className="mx-auto max-w-[1160px] px-4 py-6 sm:px-8 sm:py-10">
        {/* Navigation Bar */}
        <nav aria-label="Điều hướng trang" className="mb-6 flex items-center justify-between">
          <Link
            to="/dashboard"
            className="group inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-semibold text-strong shadow-soft transition-colors hover:bg-rail hover:text-highlight focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 min-h-[44px]"
          >
            <ArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" aria-hidden="true" />
            <span>Thư viện đề</span>
          </Link>

          <div className="text-xs font-mono text-muted">
            <span>Số liệu tại thời điểm tải trang</span>
          </div>
        </nav>

        {/* Page Heading */}
        <div className="mb-8 border-b border-line pb-6">
          <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-2">
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-strong">
                Thống kê sử dụng
              </h1>
              <p className="mt-1.5 text-sm text-muted">
                Các phiên đề hiện đang lưu trong tài khoản của bạn.
              </p>
            </div>
            <div className="text-xs font-mono text-muted">
              Cập nhật theo tài khoản cá nhân
            </div>
          </div>
        </div>

        {/* Dynamic Statistics Content */}
        <StatisticsData key={accountKey} />
      </main>
    </div>
  );
}

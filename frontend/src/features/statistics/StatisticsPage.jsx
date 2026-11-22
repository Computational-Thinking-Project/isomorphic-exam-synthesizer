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
  Workflow,
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
        stageId: '01',
        stageLabel: 'Đề gốc',
        barColor: 'bg-slate-500',
        dotColor: 'bg-slate-500',
      };
    case 'blueprinted':
      return {
        stageId: '01',
        stageLabel: 'Blueprint',
        barColor: 'bg-sky-500',
        dotColor: 'bg-sky-500',
      };
    case 'configured':
      return {
        stageId: '02',
        stageLabel: 'Cấu hình',
        barColor: 'bg-indigo-600',
        dotColor: 'bg-indigo-600',
      };
    case 'generating':
      return {
        stageId: '02',
        stageLabel: 'Đang sinh',
        barColor: 'bg-amber-500',
        dotColor: 'bg-amber-500 animate-pulse',
      };
    case 'partial_generated':
      return {
        stageId: '02',
        stageLabel: 'Sinh một phần',
        barColor: 'bg-amber-600',
        dotColor: 'bg-amber-600',
      };
    case 'generated':
      return {
        stageId: '02',
        stageLabel: 'Đã sinh đề',
        barColor: 'bg-violet-600',
        dotColor: 'bg-violet-600',
      };
    case 'reviewed':
      return {
        stageId: '03',
        stageLabel: 'Chờ chốt',
        barColor: 'bg-teal-600',
        dotColor: 'bg-teal-600',
      };
    case 'approved':
      return {
        stageId: '03',
        stageLabel: 'Đã duyệt',
        barColor: 'bg-emerald-600',
        dotColor: 'bg-emerald-600',
      };
    case 'exported':
      return {
        stageId: '04',
        stageLabel: 'Đã xuất',
        barColor: 'bg-[#304c70]',
        dotColor: 'bg-[#304c70]',
      };
    case 'failed':
      return {
        stageId: 'ERR',
        stageLabel: 'Lỗi',
        barColor: 'bg-danger',
        dotColor: 'bg-danger',
      };
    case 'unknown':
    default:
      return {
        stageId: 'N/A',
        stageLabel: 'Chưa rõ',
        barColor: 'bg-muted',
        dotColor: 'bg-muted',
      };
  }
}

/**
 * Biểu đồ tròn vành khuyên thể hiện cơ cấu vòng đời phiên đề
 */
function CompositionDonut({ data }) {
  const total = data.total_sessions || 0;
  if (total <= 0) return null;

  const inProgress = data.in_progress_sessions || 0;
  const approved = data.approved_not_exported_sessions || 0;
  const exported = data.exported_sessions || 0;
  const failed = data.by_status?.failed || 0;
  const unknown = data.by_status?.unknown || 0;
  const exceptions = failed + unknown;

  const radius = 56;
  const circumference = 2 * Math.PI * radius;

  const inProgLen = (inProgress / total) * circumference;
  const appLen = (approved / total) * circumference;
  const expLen = (exported / total) * circumference;
  const excLen = (exceptions / total) * circumference;

  const inProgOffset = 0;
  const appOffset = inProgLen;
  const expOffset = appOffset + appLen;
  const excOffset = expOffset + expLen;

  return (
    <div className="flex flex-col items-center justify-center p-6">
      <div className="relative flex items-center justify-center shrink-0">
        <svg
          className="h-44 w-44 -rotate-90 transform"
          viewBox="0 0 140 140"
          aria-hidden="true"
        >
          {/* Base rail */}
          <circle
            cx="70"
            cy="70"
            r={radius}
            fill="transparent"
            stroke="var(--rail)"
            strokeWidth="14"
          />
          {inProgress > 0 && (
            <circle
              cx="70"
              cy="70"
              r={radius}
              fill="transparent"
              stroke="#304c70"
              strokeWidth="14"
              strokeDasharray={`${inProgLen} ${circumference}`}
              strokeDashoffset={-inProgOffset}
              className="transition-all duration-500 ease-out"
            />
          )}
          {approved > 0 && (
            <circle
              cx="70"
              cy="70"
              r={radius}
              fill="transparent"
              stroke="#d97706"
              strokeWidth="14"
              strokeDasharray={`${appLen} ${circumference}`}
              strokeDashoffset={-appOffset}
              className="transition-all duration-500 ease-out"
            />
          )}
          {exported > 0 && (
            <circle
              cx="70"
              cy="70"
              r={radius}
              fill="transparent"
              stroke="#15803d"
              strokeWidth="14"
              strokeDasharray={`${expLen} ${circumference}`}
              strokeDashoffset={-expOffset}
              className="transition-all duration-500 ease-out"
            />
          )}
          {exceptions > 0 && (
            <circle
              cx="70"
              cy="70"
              r={radius}
              fill="transparent"
              stroke="#a32b32"
              strokeWidth="14"
              strokeDasharray={`${excLen} ${circumference}`}
              strokeDashoffset={-excOffset}
              className="transition-all duration-500 ease-out"
            />
          )}
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center text-center select-none pointer-events-none">
          <span className="font-mono text-3xl font-bold tracking-tight tabular-nums text-strong">
            {number.format(total)}
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Phiên đề
          </span>
        </div>
      </div>

      {/* Legend list with clean monolithic tabular rows */}
      <div className="w-full mt-6 space-y-2.5 border-t border-line pt-4 text-xs font-medium">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[#304c70]" aria-hidden="true" />
            <span className="text-strong">Đang thực hiện</span>
          </div>
          <span className="font-mono tabular-nums text-muted">
            {number.format(inProgress)} <span className="text-muted/60">({Math.round((inProgress / total) * 100)}%)</span>
          </span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-amber-600" aria-hidden="true" />
            <span className="text-strong">Đã duyệt, chưa xuất</span>
          </div>
          <span className="font-mono tabular-nums text-muted">
            {number.format(approved)} <span className="text-muted/60">({Math.round((approved / total) * 100)}%)</span>
          </span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-600" aria-hidden="true" />
            <span className="text-strong">Đã xuất</span>
          </div>
          <span className="font-mono tabular-nums text-muted">
            {number.format(exported)} <span className="text-muted/60">({Math.round((exported / total) * 100)}%)</span>
          </span>
        </div>

        {exceptions > 0 && (
          <div className="flex items-center justify-between text-danger">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-danger" aria-hidden="true" />
              <span className="font-semibold">Ngoại lệ / lỗi</span>
            </div>
            <span className="font-mono tabular-nums">
              {number.format(exceptions)} <span className="opacity-80">({Math.round((exceptions / total) * 100)}%)</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Funnel liên kết 4 chặng luân chuyển phiên đề
 */
function PipelineFunnel({ counts, total }) {
  if (total <= 0) return null;

  const stage1 = (counts.draft || 0) + (counts.blueprinted || 0);
  const stage2 =
    (counts.configured || 0) +
    (counts.generating || 0) +
    (counts.partial_generated || 0) +
    (counts.generated || 0);
  const stage3 = (counts.reviewed || 0) + (counts.approved || 0);
  const stage4 = counts.exported || 0;

  const pipelineStages = [
    {
      num: '01',
      title: 'Đề gốc & Blueprint',
      count: stage1,
      detail: 'Bóc tách dữ liệu & chốt ma trận',
      bar: 'bg-indigo-600',
    },
    {
      num: '02',
      title: 'Sinh biến thể AI',
      count: stage2,
      detail: 'Cấu hình hoán vị & sinh câu hỏi',
      bar: 'bg-[#304c70]',
    },
    {
      num: '03',
      title: 'Kiểm định & Phê duyệt',
      count: stage3,
      detail: 'Đối soát toán học & duyệt chốt',
      bar: 'bg-amber-600',
    },
    {
      num: '04',
      title: 'Đóng gói xuất bản',
      count: stage4,
      detail: 'Hoàn thiện tài liệu PDF/Word',
      bar: 'bg-emerald-600',
    },
  ];

  return (
    <div className="rounded-xl border border-line bg-surface p-6 shadow-paper">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6 pb-4 border-b border-line">
        <div>
          <h2 className="text-base font-bold text-strong flex items-center gap-2">
            <Workflow className="h-4 w-4 text-highlight" aria-hidden="true" />
            <span>Quy trình xử lý phiên đề 4 chặng</span>
          </h2>
          <p className="mt-0.5 text-xs text-muted">
            Sơ đồ luân chuyển tuyến tính từ nạp nguồn đến đóng gói xuất bản
          </p>
        </div>
        <div className="text-xs font-mono tabular-nums text-muted bg-rail px-3 py-1 rounded-md border border-line self-start sm:self-auto">
          Tổng luân chuyển: {number.format(total)} phiên
        </div>
      </div>

      <div className="grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-y-0 sm:divide-x lg:grid-cols-4 border border-line rounded-lg overflow-hidden bg-canvas">
        {pipelineStages.map((stg) => {
          const pct = Math.round((stg.count / total) * 100);
          return (
            <div key={stg.num} className="p-4 sm:p-5 flex flex-col justify-between bg-surface transition-colors hover:bg-rail/30">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="font-mono text-xs font-bold text-muted tracking-wider">
                    CHẶNG {stg.num}
                  </span>
                  <span className="font-mono tabular-nums text-xs font-semibold text-muted bg-rail px-2 py-0.5 rounded border border-line">
                    {pct}%
                  </span>
                </div>

                <div className="text-sm font-bold text-strong mb-1">
                  {stg.title}
                </div>

                <div className="text-xs text-muted leading-relaxed line-clamp-2">
                  {stg.detail}
                </div>
              </div>

              <div className="mt-5 pt-3 border-t border-line/60">
                <div className="flex items-baseline justify-between mb-2">
                  <span className="font-mono text-2xl font-bold tabular-nums text-strong">
                    {number.format(stg.count)}
                  </span>
                  <span className="text-xs font-medium text-muted">phiên</span>
                </div>

                <div className="h-1.5 w-full overflow-hidden rounded-full bg-rail" aria-hidden="true">
                  <div
                    className={`h-full rounded-full ${stg.bar} transition-all duration-500`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Phân bố chi tiết 11 trạng thái phiên đề
 * Tuân thủ 100% hợp đồng kiểm thử:
 * - container.querySelector('section') tìm thấy section này
 * - chart.querySelectorAll('dt').length === 11
 * - textContent chứa chính xác: /Đã tạo gói xuất1/, /Chưa xác định1/, /Đang chuẩn bị đề gốc0/
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
            Chi tiết 11 trạng thái dọc theo chuỗi nghiệp vụ sinh đề đẳng cấu
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

      {/* Main Analysis Hub: 11-Status Distribution + Composition Donut */}
      {total > 0 && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div>
            <StatusChart counts={data.by_status} total={data.total_sessions} />
          </div>

          <div className="order-first lg:order-none rounded-xl border border-line bg-surface shadow-paper flex flex-col">
            <div className="px-5 py-4 border-b border-line flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-muted">
                Tỷ trọng phân bổ phiên
              </span>
              <span className="font-mono text-xs font-semibold tabular-nums text-muted">
                {Math.round(((data.approved_not_exported_sessions + data.exported_sessions) / total) * 100)}% hoàn tất
              </span>
            </div>
            <CompositionDonut data={data} />
          </div>
        </div>
      )}

      {/* When total is 0, render StatusChart as empty */}
      {total === 0 && (
        <StatusChart counts={data.by_status} total={data.total_sessions} />
      )}

      {/* 4-Stage Lifecycle Progression Funnel */}
      <PipelineFunnel counts={data.by_status} total={data.total_sessions} />
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

          <div className="flex items-center gap-2 font-mono text-xs text-muted">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
            <span>ĐỒNG BỘ TRỰC TIẾP</span>
          </div>
        </nav>

        {/* Page Heading: Clean, authoritative, no clipart slop */}
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

import { useEffect, useState } from 'react';
import { ArrowLeft, RotateCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import BrandLogo from '../../components/BrandLogo.jsx';
import { getMyStatistics } from '../../services/statistics.js';
import { useAuthStore } from '../auth/authStore.js';
import './statistics.css';

const subtotals = [
  ['in_progress_sessions', 'Đang thực hiện', 'bg-highlight'],
  ['approved_not_exported_sessions', 'Đã duyệt, chưa xuất', 'bg-[#99712b]'],
  ['exported_sessions', 'Đã xuất', 'bg-approved-ink'],
];

const statuses = [
  ['draft', 'Đang chuẩn bị đề gốc'],
  ['blueprinted', 'Đã xác nhận đề gốc'],
  ['configured', 'Đã cấu hình sinh đề'],
  ['generating', 'Đang sinh đề'],
  ['partial_generated', 'Đã sinh một phần'],
  ['generated', 'Đã sinh đề'],
  ['reviewed', 'Đã duyệt các câu, chờ chốt'],
  ['approved', 'Đã duyệt, chưa xuất', 'bg-[#99712b]'],
  ['exported', 'Đã tạo gói xuất', 'bg-approved-ink'],
  ['failed', 'Sinh đề gặp lỗi', 'bg-danger'],
  ['unknown', 'Chưa xác định', 'bg-muted'],
];

const number = new Intl.NumberFormat('vi-VN');

function SessionSummary({ data }) {
  const total = number.format(data.total_sessions);
  const { failed, unknown } = data.by_status;
  const remainder = [
    failed > 0 && `${number.format(failed)} phiên sinh đề gặp lỗi`,
    unknown > 0 && `${number.format(unknown)} phiên chưa xác định trạng thái`,
  ].filter(Boolean);

  return (
    <section aria-label="Tổng quan phiên đề" className="min-w-0">
      <dl className="stats-summary border border-line bg-surface">
        <div className="stats-total">
          <dt className="text-sm font-semibold">Tổng số phiên đề</dt>
          <dd className="mt-3">
            <span className="stats-total-number"
              style={{ fontSize: `clamp(1.25rem, ${153 / total.length}cqi, var(--total-size))` }}>
              {total}
            </span>
            {' '}<span className="inline-block text-sm text-white/80">phiên đề</span>
          </dd>
        </div>
        {subtotals.map(([key, label, color]) => (
          <div key={key} className="stats-subtotal mx-5 sm:mx-6">
            <dt className="flex items-center gap-3 text-sm font-medium">
              <span aria-hidden="true" className={`h-0.5 w-4 shrink-0 ${color}`} />
              {label}
            </dt>
            <dd className="text-right text-xl font-semibold tabular-nums text-strong">
              {number.format(data[key])}<span className="sr-only"> phiên đề</span>
            </dd>
          </div>
        ))}
      </dl>
      {remainder.length > 0 && (
        <p className="mt-4 border-l-2 border-control-border pl-3 text-sm leading-6 text-muted">
          Tổng số phiên bao gồm {remainder.join(' và ')}.
        </p>
      )}
    </section>
  );
}

function StatusChart({ counts, total }) {
  const [hideZeros, setHideZeros] = useState(false);
  const largest = Math.max(...Object.values(counts));
  const visibleStatuses = statuses.filter(([key]) => counts[key] > 0 || (!hideZeros && key !== 'unknown'));

  return (
    <section aria-labelledby="status-chart-title" className="min-w-0 border-t-2 border-highlight">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3">
        <h2 id="status-chart-title" className="stats-heading text-2xl text-strong">Phân bố trạng thái</h2>
        {total > 0 && (
          <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm text-ink">
            <input type="checkbox" className="stats-checkbox" checked={hideZeros}
              onChange={(event) => setHideZeros(event.target.checked)} />
            Ẩn trạng thái có 0 phiên
          </label>
        )}
      </div>
      {total === 0 ? (
        <div className="border-y border-line bg-surface px-5 py-8 sm:px-6">
          <p className="font-semibold text-strong">Bạn chưa có phiên đề nào.</p>
          <p className="mt-1 text-sm leading-6 text-muted">Khi bạn tạo phiên đầu tiên trong thư viện, trạng thái của phiên sẽ xuất hiện ở đây.</p>
        </div>
      ) : (
        <table className="stats-chart" aria-labelledby="status-chart-title">
          <thead>
            <tr>
              <th scope="col">
                <div className="stats-plot">
                  <span>Trạng thái phiên</span>
                  <span className="stats-axis" aria-hidden="true"><span>0</span><span>{number.format(largest)}</span></span>
                </div>
              </th>
              <th scope="col" className="text-right">Số phiên</th>
            </tr>
          </thead>
          <tbody>
            {visibleStatuses.map(([key, label, color = 'bg-highlight']) => (
              <tr key={key}>
                <th scope="row">
                  <div className="stats-plot">
                    <span>{label}</span>
                    <span className="stats-track" aria-hidden="true">
                      <span className={`block h-full ${color}`} style={{ width: `${counts[key] / largest * 100}%` }} />
                    </span>
                  </div>
                </th>
                <td>{number.format(counts[key])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
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
      <div className="border-y border-line bg-surface px-5 py-8">
        <p role="status" className="text-highlight">Đang tải thống kê…</p>
      </div>
    );
  }

  if (result.state === 'error') {
    return (
      <div className="flex flex-wrap items-center justify-between gap-4 border-y border-line bg-surface px-5 py-6">
        <p role="alert" className="border-l-2 border-danger pl-3 font-semibold text-danger">Không tải được thống kê.</p>
        <button type="button" className="stats-action border border-line px-4"
          onClick={() => {
            setResult({ state: 'loading' });
            setRequestKey((key) => key + 1);
          }}>
          <RotateCw size={16} aria-hidden="true" /> Thử lại
        </button>
      </div>
    );
  }

  return (
    <div className="grid items-start gap-7 lg:grid-cols-[minmax(0,0.76fr)_minmax(0,1.65fr)] lg:gap-10">
      <SessionSummary data={result.data} />
      <StatusChart counts={result.data.by_status} total={result.data.total_sessions} />
    </div>
  );
}

export default function StatisticsPage() {
  const accountKey = useAuthStore((state) => `${state.user?.id ?? ''}:${state.sessionVersion}`);

  return (
    <div className="paper-ui min-h-screen bg-[#f8f8f5] text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1160px] flex-wrap items-center justify-between gap-x-3 px-4 py-2 sm:px-8">
          <BrandLogo size="sm" className="stats-brand" />
          <Link to="/dashboard" className="stats-action"><ArrowLeft size={16} aria-hidden="true" />Thư viện đề</Link>
        </div>
      </header>
      <main className="mx-auto max-w-[1160px] px-4 pb-12 pt-7 sm:px-8 sm:pt-10">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-x-8 gap-y-3 sm:mb-8">
          <div>
            <h1 className="stats-heading text-[2.15rem] leading-tight text-strong sm:text-[2.75rem]">Thống kê sử dụng</h1>
            <p className="mt-2 text-[0.9375rem] leading-6 text-muted">Các phiên đề hiện đang lưu trong thư viện của bạn.</p>
          </div>
          <p className="border-l-2 border-accent-border pl-3 text-sm text-ink">
            <span className="mr-2 text-muted">Phạm vi</span>Toàn bộ thời gian
          </p>
        </div>
        <StatisticsData key={accountKey} />
      </main>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
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
const panel = 'rounded-xl border border-line bg-surface p-5 shadow-soft sm:p-6';

function StatusChart({ counts, total }) {
  const largest = Math.max(1, ...Object.values(counts));
  const chartColumns = `minmax(0,1fr) ${number.format(largest).length + 1}ch`;

  return (
    <section aria-labelledby="status-chart-title" className={panel}>
      <h2 id="status-chart-title" className="mb-4 text-lg font-bold text-strong">
        Phân bố trạng thái phiên
      </h2>
      {total === 0 ? <p className="text-muted">Bạn chưa có phiên đề nào.</p> : (
        <dl className="space-y-3">
          {statuses.filter(([key]) => key !== 'unknown' || counts.unknown > 0).map(([key, label]) => (
            <div key={key} className="grid items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
              <dt className="break-words text-sm">{label}</dt>
              <dd className="grid items-center gap-3" style={{ gridTemplateColumns: chartColumns }}>
                <span aria-hidden="true" className="block h-2 overflow-hidden rounded-full bg-rail">
                  <span className="block h-full rounded-full bg-highlight" style={{ width: `${counts[key] / largest * 100}%` }} />
                </span>
                <span className="text-right text-sm font-semibold tabular-nums">{number.format(counts[key])}</span>
              </dd>
            </div>
          ))}
        </dl>
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
    return <div className={panel} aria-busy="true"><p role="status">Đang tải thống kê…</p></div>;
  }

  if (result.state === 'error') {
    return (
      <div className={panel}>
        <p role="alert" className="text-danger">Không tải được thống kê.</p>
        <button
          type="button"
          className="mt-3 rounded-lg border border-line px-4 py-2 font-semibold text-highlight hover:bg-rail"
          onClick={() => {
            setResult({ state: 'loading' });
            setRequestKey((key) => key + 1);
          }}
        >
          Thử lại
        </button>
      </div>
    );
  }

  const { data } = result;
  const { failed, unknown } = data.by_status;
  const remainder = [
    failed > 0 && `${number.format(failed)} phiên sinh đề gặp lỗi`,
    unknown > 0 && `${number.format(unknown)} phiên chưa xác định trạng thái`,
  ].filter(Boolean);

  return (
    <div className="space-y-5">
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([key, label]) => (
          <div key={key} className={panel}>
            <dt className="text-sm font-semibold text-muted">{label}</dt>
            <dd className="mt-2 flex flex-wrap items-baseline gap-x-2">
              <span className="break-all text-3xl font-bold tabular-nums text-strong">{number.format(data[key])}</span>
              <span className="text-sm text-muted">phiên đề</span>
            </dd>
          </div>
        ))}
      </dl>
      {remainder.length > 0 && <p className="text-sm text-muted">Tổng số phiên bao gồm {remainder.join(' và ')}.</p>}
      <StatusChart counts={data.by_status} total={data.total_sessions} />
    </div>
  );
}

export default function StatisticsPage() {
  const accountKey = useAuthStore((state) => `${state.user?.id ?? ''}:${state.sessionVersion}`);

  return (
    <div className="paper-ui min-h-screen bg-canvas text-ink">
      <main className="mx-auto max-w-[1160px] px-4 py-6 sm:px-8 sm:py-10">
        <Link to="/dashboard" className="inline-flex rounded-md py-2 text-sm font-semibold text-highlight hover:underline">
          ← Thư viện đề
        </Link>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-strong sm:text-4xl">Thống kê sử dụng</h1>
        <p className="mb-6 mt-2 text-muted">Các phiên đề hiện đang lưu trong tài khoản của bạn.</p>
        <StatisticsData key={accountKey} />
      </main>
    </div>
  );
}

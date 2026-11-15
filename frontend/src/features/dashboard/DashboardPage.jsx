import { useEffect, useState } from 'react';
import { AlertCircle, FilePlus2, Plus, RefreshCw } from 'lucide-react';
import DashboardSessionCard from './DashboardSessionCard.jsx';

export default function DashboardPage({
  loadSessions,
  onCreate,
  onOpen,
  onClone,
  openingSessionId = null,
}) {
  const [requestKey, setRequestKey] = useState(0);
  const [{ status, items, error }, setState] = useState({
    status: 'loading',
    items: [],
    error: '',
  });

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    setState({ status: 'loading', items: [], error: '' });

    async function load() {
      try {
        const sessions = await loadSessions({
          signal: controller.signal,
        });

        if (!Array.isArray(sessions)) {
          throw new Error('Dữ liệu danh sách chưa hợp lệ.');
        }

        if (active) {
          setState({
            status: 'success',
            items: sessions,
            error: '',
          });
        }
      } catch (cause) {
        if (active) {
          setState({
            status: 'error',
            items: [],
            error:
              cause instanceof Error && cause.message
                ? cause.message
                : 'Không tải được danh sách đề. Vui lòng thử lại.',
          });
        }
      }
    }

    load();

    return () => {
      active = false;
      controller.abort();
    };
  }, [loadSessions, requestKey]);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:py-10">
      {/* Page Header */}
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-strong">
            Thư viện đề thi
          </h1>
          <p className="mt-1.5 text-sm text-muted">
            Quản lý các phiên làm việc, tiếp tục biên soạn hoặc xem lại các đề đã chốt.
          </p>
        </div>

        <button
          type="button"
          disabled={!onCreate}
          onClick={onCreate}
          className="inline-flex items-center gap-2 rounded-xl bg-highlight px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#253b57] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span>Tạo bộ đề mới</span>
        </button>
      </header>

      {/* Main Section */}
      <section
        aria-label="Danh sách phiên đề"
        aria-busy={status === 'loading'}
      >
        {/* Loading State: Skeleton Cards */}
        {status === 'loading' && (
          <div>
            <p role="status" className="sr-only">
              Đang tải danh sách đề…
            </p>
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4, 5, 6].map((idx) => (
                <div
                  key={idx}
                  className="flex h-48 animate-pulse flex-col justify-between rounded-2xl border border-line bg-surface p-6 shadow-card"
                >
                  <div>
                    <div className="flex items-center justify-between gap-3">
                      <div className="h-5 w-3/5 rounded-lg bg-support-bg" />
                      <div className="h-5 w-1/4 rounded-full bg-support-bg" />
                    </div>
                    <div className="mt-4 flex gap-3">
                      <div className="h-4 w-20 rounded bg-rail" />
                      <div className="h-4 w-20 rounded bg-rail" />
                    </div>
                  </div>
                  <div className="flex gap-2 pt-4 border-t border-line">
                    <div className="h-8 flex-1 rounded-xl bg-support-bg" />
                    <div className="h-8 w-24 rounded-xl bg-rail" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Error State */}
        {status === 'error' && (
          <div
            role="alert"
            className="rounded-2xl border border-danger-border bg-danger-soft p-6 sm:p-8 text-center"
          >
            <AlertCircle className="mx-auto h-10 w-10 text-danger" aria-hidden="true" />
            <h2 className="mt-3 text-lg font-bold text-danger">Không tải được danh sách đề</h2>
            <p className="mt-1 text-sm text-danger/90">{error}</p>
            <button
              type="button"
              onClick={() => setRequestKey((val) => val + 1)}
              className="mt-5 inline-flex items-center gap-2 rounded-xl bg-danger px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-danger/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Thử lại
            </button>
          </div>
        )}

        {/* Empty State */}
        {status === 'success' && items.length === 0 && (
          <div
            role="status"
            className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-line bg-surface p-12 text-center shadow-soft"
          >
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-support-bg text-highlight border border-support-line">
              <FilePlus2 className="h-7 w-7" aria-hidden="true" />
            </div>
            <h2 className="mt-4 text-lg font-bold text-strong">
              Bạn chưa có phiên đề thi nào
            </h2>
            <p className="mt-1 max-w-sm text-sm text-muted">
              Bắt đầu tạo bộ đề đầu tiên để nạp nguồn, bóc tách cấu trúc và sinh các mã đề trắc nghiệm đẳng cấu.
            </p>
            <button
              type="button"
              onClick={onCreate}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-highlight px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#253b57] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Tạo bộ đề ngay
            </button>
          </div>
        )}

        {/* Session Card Grid */}
        {status === 'success' && items.length > 0 && (
          <ul className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {items.map((session) => (
              <li key={session.id} className="min-w-0">
                <DashboardSessionCard
                  session={session}
                  onOpen={onOpen}
                  onClone={onClone}
                  openingSessionId={openingSessionId}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

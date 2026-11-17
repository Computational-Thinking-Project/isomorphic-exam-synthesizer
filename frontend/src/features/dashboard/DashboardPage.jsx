import { useEffect, useState } from 'react';
import {
  AlertCircle,
  FilePlus2,
  Plus,
  RefreshCw,
} from 'lucide-react';
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
    <main className="mx-auto max-w-[1160px] px-4 sm:px-8 py-6 sm:py-8">
      {/* Page Heading Banner matching docs/ui-walkthrough/PREVIEW.html */}
      <section
        aria-labelledby="library-heading"
        className="relative mb-6 overflow-hidden rounded-2xl border border-line bg-surface p-6 sm:p-8 shadow-paper"
      >
        <div className="relative z-10 flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div className="max-w-xl">
            <h1
              id="library-heading"
              className="text-3xl sm:text-4xl font-extrabold tracking-tight text-strong"
            >
              Thư viện đề
            </h1>

            <p className="mt-2 text-sm text-muted leading-relaxed">
              Quản lý đề gốc, tiếp tục biên soạn và xem lại các bộ đề đã hoàn thành.
            </p>

            {items && items.length > 0 && (
              <button
                type="button"
                disabled={!onCreate}
                onClick={onCreate}
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-highlight px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#253b57] hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                <span>Tạo bộ đề mới</span>
              </button>
            )}
          </div>

          {/* Decorative artwork from PREVIEW.html */}
          <div className="hidden md:flex shrink-0 items-center justify-center">
            <img
              src="/library-artwork.webp"
              alt=""
              className="w-[200px] lg:w-[240px] h-auto object-contain select-none pointer-events-none drop-shadow-sm"
              draggable={false}
            />
          </div>
        </div>
      </section>

      {/* Main Library Panel matching PREVIEW.html */}
      <section
        aria-label="Danh sách phiên đề"
        aria-busy={status === 'loading'}
        className="rounded-xl border border-line bg-surface overflow-hidden shadow-soft"
      >
        {/* Loading State */}
        {status === 'loading' && (
          <div className="p-8 sm:p-12 text-center">
            <p role="status" className="text-sm text-muted animate-pulse">
              Đang tải danh sách đề…
            </p>
          </div>
        )}

        {/* Error State */}
        {status === 'error' && (
          <div
            role="alert"
            className="p-8 text-center bg-danger-soft text-danger"
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
            className="flex flex-col items-center justify-center p-6 py-12 sm:p-12 text-center"
          >
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-support-bg text-highlight border border-support-line">
              <FilePlus2 className="h-7 w-7" aria-hidden="true" />
            </div>
            <h2 className="mt-4 text-lg font-bold text-strong">
              Bạn chưa có phiên đề thi nào
            </h2>
            <p className="mt-1 max-w-sm text-sm text-muted leading-relaxed">
              Tạo bộ đề đầu tiên, thêm đề gốc và bắt đầu biên soạn các mã đề.
            </p>
            <button
              type="button"
              onClick={onCreate}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-highlight px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#253b57] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Tạo bộ đề ngay
            </button>
          </div>
        )}

        {/* Table Header Row (Hidden on mobile, visible on desktop matching PREVIEW.html) */}
        {status === 'success' && items.length > 0 && (
          <div>
            <div
              className="hidden lg:grid lg:grid-cols-[minmax(240px,1fr)_140px_110px_220px] gap-4 px-6 py-3 bg-support-bg text-support-text text-xs font-semibold uppercase tracking-wider border-b border-line"
              aria-hidden="true"
            >
              <span>Tên bộ đề</span>
              <span>Trạng thái</span>
              <span>Ngày tạo</span>
              <span className="text-right">Thao tác</span>
            </div>

            {/* Session List Rows */}
            <ul className="divide-y divide-line" aria-label="Danh sách bộ đề">
              {items.map((session) => (
                <li key={session.id}>
                  <DashboardSessionCard
                    session={session}
                    onOpen={onOpen}
                    onClone={onClone}
                    openingSessionId={openingSessionId}
                  />
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </main>
  );
}

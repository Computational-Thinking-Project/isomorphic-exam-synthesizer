import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  FilePlus2,
  Filter,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  X,
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
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
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

  // Client-side search and filtering for smooth instant response
  const filteredItems = useMemo(() => {
    if (!items || items.length === 0) return [];
    return items.filter((session) => {
      const matchQuery =
        !searchQuery.trim() ||
        (session.title || '').toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
        (session.subject || '').toLowerCase().includes(searchQuery.trim().toLowerCase());

      const matchStatus =
        statusFilter === 'all' ||
        (statusFilter === 'draft' && session.status === 'draft') ||
        (statusFilter === 'approved' && (session.status === 'approved' || session.status === 'exported')) ||
        session.status === statusFilter;

      return matchQuery && matchStatus;
    });
  }, [items, searchQuery, statusFilter]);

  const activeFilterCount = (searchQuery.trim() ? 1 : 0) + (statusFilter !== 'all' ? 1 : 0);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:py-10">
      {/* Page Header / Hero Banner */}
      <header className="relative mb-8 overflow-hidden rounded-2xl border border-line bg-gradient-to-r from-surface via-surface to-support-bg/50 p-6 sm:p-8 shadow-soft">
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-6">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-support-line bg-support-bg px-3 py-1 text-xs font-semibold text-highlight mb-3">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Exam Mirror · Paper Canvas Workspace</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-strong">
              Thư viện đề thi
            </h1>
            <p className="mt-2 text-sm text-muted leading-relaxed">
              Quản lý các phiên làm việc, tiếp tục biên soạn hoặc xem lại các đề đã chốt.
              Mỗi bộ đề hỗ trợ sinh biến thể câu hỏi đẳng cấu với thẩm định đại số tự động.
            </p>
          </div>

          <button
            type="button"
            disabled={!onCreate}
            onClick={onCreate}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-highlight px-5 py-3 text-sm font-semibold text-white shadow-md transition-all hover:bg-[#253b57] hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            <span>Tạo bộ đề mới</span>
          </button>
        </div>
      </header>

      {/* Toolbar: Search, Status Filter & Count */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-1 flex-wrap items-center gap-3 min-w-[280px]">
          {/* Search Field */}
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden="true" />
            <input
              type="text"
              placeholder="Tìm theo tên đề, môn học…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              disabled={status === 'loading'}
              className="w-full rounded-xl border border-line bg-surface py-2 pl-9 pr-9 text-xs text-strong placeholder-muted shadow-soft transition-all focus:border-highlight focus:outline-none focus:ring-2 focus:ring-highlight/20 disabled:opacity-50"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted hover:bg-rail hover:text-strong"
                aria-label="Xóa từ khóa tìm kiếm"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            )}
          </div>

          {/* Status Filter */}
          <div className="relative flex items-center">
            <Filter className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" aria-hidden="true" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              disabled={status === 'loading'}
              className="rounded-xl border border-line bg-surface py-2 pl-8 pr-8 text-xs font-medium text-strong shadow-soft transition-all focus:border-highlight focus:outline-none focus:ring-2 focus:ring-highlight/20 disabled:opacity-50 cursor-pointer"
            >
              <option value="all">Mọi trạng thái</option>
              <option value="draft">Bản nháp / Đang chuẩn bị</option>
              <option value="blueprinted">Đã xác nhận quy tắc</option>
              <option value="generating">Đang sinh đề</option>
              <option value="approved">Đã chốt / Đã xuất</option>
            </select>
          </div>

          {activeFilterCount > 0 && (
            <button
              type="button"
              onClick={() => { setSearchQuery(''); setStatusFilter('all'); }}
              className="rounded-xl px-2.5 py-1.5 text-xs text-muted hover:text-strong hover:bg-rail transition-colors"
            >
              Xóa bộ lọc
            </button>
          )}
        </div>

        {status === 'success' && (
          <p className="text-xs text-muted font-medium" role="status">
            Hiển thị <span className="font-semibold text-strong">{filteredItems.length}</span> / {items.length} bộ đề
          </p>
        )}
      </div>

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
                  className="flex h-52 animate-pulse flex-col justify-between rounded-2xl border border-line bg-surface p-6 shadow-soft"
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
                    <div className="h-9 flex-1 rounded-xl bg-support-bg" />
                    <div className="h-9 w-24 rounded-xl bg-rail" />
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
            className="rounded-2xl border border-danger-border bg-danger-soft p-8 text-center shadow-soft"
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

        {/* No Filter Results State */}
        {status === 'success' && items.length > 0 && filteredItems.length === 0 && (
          <div
            role="status"
            className="flex flex-col items-center justify-center rounded-2xl border border-line bg-surface p-10 text-center shadow-soft"
          >
            <Search className="h-8 w-8 text-muted mb-2" aria-hidden="true" />
            <h3 className="text-base font-bold text-strong">Không tìm thấy bộ đề phù hợp</h3>
            <p className="mt-1 text-xs text-muted max-w-xs">
              Thử thay đổi từ khóa tìm kiếm hoặc bỏ chọn trạng thái đã lọc.
            </p>
            <button
              type="button"
              onClick={() => { setSearchQuery(''); setStatusFilter('all'); }}
              className="mt-4 rounded-xl border border-line bg-surface px-4 py-2 text-xs font-semibold text-strong hover:bg-rail transition-colors"
            >
              Xóa điều kiện tìm kiếm
            </button>
          </div>
        )}

        {/* Session Card Grid */}
        {status === 'success' && filteredItems.length > 0 && (
          <ul className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {filteredItems.map((session) => (
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

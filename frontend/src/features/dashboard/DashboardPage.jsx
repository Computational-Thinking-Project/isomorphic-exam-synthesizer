import { useEffect, useState } from 'react';
import DashboardSessionCard from './DashboardSessionCard.jsx';

const buttonClass =
  'rounded-lg bg-sky-400 px-4 py-2 font-medium text-slate-950 ' +
  'hover:bg-sky-300 focus-visible:outline focus-visible:outline-2 ' +
  'focus-visible:outline-offset-4 focus-visible:outline-sky-400 ' +
  'disabled:cursor-not-allowed disabled:opacity-50';

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
    <main className="mx-auto max-w-6xl px-4 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">Các phiên đề của bạn</h1>
          <p className="mt-2 text-slate-400">
            Tiếp tục biên soạn hoặc xem lại các đề đã chốt.
          </p>
        </div>

        <button
          type="button"
          className={buttonClass}
          disabled={!onCreate}
          onClick={onCreate}
        >
          Tạo đề mới
        </button>
      </header>

      <section
        aria-label="Danh sách phiên đề"
        aria-busy={status === 'loading'}
      >
        {status === 'loading' && (
          <p role="status" className="py-10 text-slate-300">
            Đang tải danh sách đề…
          </p>
        )}

        {status === 'error' && (
          <div className="rounded-xl border border-rose-800 p-6">
            <p role="alert" className="text-rose-300">
              {error}
            </p>
            <button
              type="button"
              className={`${buttonClass} mt-4`}
              onClick={() => setRequestKey((value) => value + 1)}
            >
              Thử lại
            </button>
          </div>
        )}

        {status === 'success' && items.length === 0 && (
          <div
            role="status"
            className="rounded-xl border border-dashed border-slate-700 p-10 text-center"
          >
            <p className="text-lg font-medium">Bạn chưa có phiên đề nào</p>
            <p className="mt-2 text-slate-400">
              Chọn “Tạo đề mới” để bắt đầu biên soạn.
            </p>
          </div>
        )}

        {status === 'success' && items.length > 0 && (
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
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

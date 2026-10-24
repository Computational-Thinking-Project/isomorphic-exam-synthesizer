import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CloneSessionModal from './CloneSessionModal.jsx';
import '../../index.css';

const sampleSessions = [
  {
    id: 'mock-session-001',
    title: 'Đề mẫu — Tích phân',
    subject: 'Toán',
    status: 'draft',
    created_at: '2026-10-16T02:00:00Z',
  },
  {
    id: 'mock-session-002',
    title: 'Đề mẫu — Xác suất',
    subject: 'Toán',
    status: 'approved',
    created_at: '2026-10-15T07:30:00Z',
  },
];

function CloneModalPreview() {
  const [selectedSession, setSelectedSession] = useState(null);
  const [history, setHistory] = useState([]);
  const [lastAction, setLastAction] = useState('Chưa có hành động nào.');

  function handleOpenClone(session) {
    setSelectedSession(session);
    setLastAction(`Đã mở modal nhân bản cho: ${session.title}`);
  }

  function handleSuccess(clonedSession) {
    setHistory((prev) => [clonedSession, ...prev]);
    setLastAction(
      `Nhân bản thành công! Tạo phiên mới ID: ${clonedSession.id} — "${clonedSession.title}"`,
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-8">
      <header className="border-b border-slate-700 pb-4">
        <span className="inline-block rounded-full bg-sky-950 px-3 py-1 text-xs font-semibold text-sky-400 border border-sky-800">
          TASK-103b Preview
        </span>
        <h1 className="mt-2 text-3xl font-bold">Xem thử CloneSessionModal</h1>
        <p className="mt-1 text-slate-400">
          Kiểm tra luồng mở modal, gợi ý tiêu đề, chống double-submit, xử lý lỗi và nhận kết quả nhân bản.
        </p>
      </header>

      {/* Danh sách các phiên mẫu để bấm thử nhân bản */}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <h2 className="text-xl font-semibold text-slate-100">1. Chọn một phiên để thử nghiệm:</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sampleSessions.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950/60 p-4"
            >
              <div>
                <h3 className="font-semibold text-slate-200">{s.title}</h3>
                <p className="text-xs text-slate-400 mt-1">ID: {s.id} · Trạng thái: {s.status}</p>
              </div>
              <button
                type="button"
                onClick={() => handleOpenClone(s)}
                className="rounded-lg bg-sky-400 px-3 py-1.5 text-xs font-medium text-slate-950 hover:bg-sky-300"
              >
                Nhân bản
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Trạng thái hoạt động */}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <h2 className="text-xl font-semibold text-slate-100">2. Nhật ký tương tác & Kết quả:</h2>
        <div className="rounded-lg border border-slate-700 bg-slate-950/80 p-4 font-mono text-sm text-sky-300">
          {lastAction}
        </div>

        <p className="text-xs text-slate-400">
          💡 <strong>Mẹo thử nghiệm lỗi:</strong> Khi modal mở, hãy nhập từ khóa <code>error</code> vào ô tiêu đề rồi bấm "Nhân bản" để xem cách modal xử lý lỗi máy chủ giả lập mà không bị tắt.
        </p>

        {history.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-slate-300 mb-2">Các phiên vừa nhân bản trong phiên xem thử này:</h3>
            <ul className="space-y-2">
              {history.map((item) => (
                <li
                  key={item.id}
                  className="rounded-lg border border-emerald-800/60 bg-emerald-950/20 p-3 text-xs text-emerald-300 flex justify-between"
                >
                  <span><strong>{item.title}</strong> (ID: {item.id})</span>
                  <span>Nguồn: {item.source_session_id}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* Modal được điều khiển qua state */}
      <CloneSessionModal
        isOpen={Boolean(selectedSession)}
        session={selectedSession}
        onClose={() => setSelectedSession(null)}
        onSuccess={handleSuccess}
      />
    </main>
  );
}

if (import.meta.env.DEV) {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <CloneModalPreview />
    </StrictMode>,
  );
}

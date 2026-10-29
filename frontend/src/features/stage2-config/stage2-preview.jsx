import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../../index.css';
import Stage2ConfigCard from './Stage2ConfigCard.jsx';
import {
  getStage2Session,
  mockStage2Session,
  saveStage2Config,
} from '../../services/mocks/stage2ConfigMock.js';

function Stage2PreviewApp() {
  const [session, setSession] = useState(mockStage2Session);
  const [scenario, setScenario] = useState('success');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [lastSubmittedPayload, setLastSubmittedPayload] = useState(null);

  async function handleScenarioChange(newScenario) {
    setScenario(newScenario);
    setError(null);
    setLastSubmittedPayload(null);
    const updated = await getStage2Session('mock-session-stage2-001', {
      scenario: newScenario,
    });
    setSession(updated);
  }

  async function handleSubmit(payload) {
    setIsSubmitting(true);
    setError(null);
    setLastSubmittedPayload(null);

    try {
      const res = await saveStage2Config(session.id, payload, {
        scenario,
      });
      setLastSubmittedPayload(payload);
      setSession(res.session);
    } catch (err) {
      setError(err.message || 'Lỗi lưu cấu hình');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100">
      {/* Control Panel cho kịch bản preview */}
      <div className="mx-auto mb-8 max-w-4xl rounded-xl border border-slate-700 bg-slate-900 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-white">
              Bảng điều khiển Xem trước (Stage 2 Config Preview)
            </h2>
            <p className="text-xs text-slate-400">
              Chọn kịch bản để kiểm tra các hành vi của giao diện cấu hình
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {[
              { id: 'success', label: 'Bình thường (Success)' },
              { id: 'error_conflict', label: 'Lỗi xung đột (Conflict 400)' },
              { id: 'error_network', label: 'Lỗi mạng (Network Error)' },
            ].map((sc) => (
              <button
                key={sc.id}
                type="button"
                onClick={() => handleScenarioChange(sc.id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                  scenario === sc.id
                    ? 'bg-sky-600 text-white'
                    : 'border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                {sc.label}
              </button>
            ))}
          </div>
        </div>

        {lastSubmittedPayload && (
          <div className="mt-4 rounded-lg bg-emerald-950/40 border border-emerald-500/40 p-3 text-xs text-emerald-200">
            <strong>Payload đã gửi thành công:</strong>
            <pre className="mt-1 overflow-x-auto text-[11px] text-emerald-300">
              {JSON.stringify(lastSubmittedPayload, null, 2)}
            </pre>
          </div>
        )}
      </div>

      <Stage2ConfigCard
        session={session}
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        error={error}
        onBack={() => alert('Quay lại Bước 1')}
      />
    </div>
  );
}

const rootElement = document.getElementById('root');
if (rootElement) {
  createRoot(rootElement).render(<Stage2PreviewApp />);
}

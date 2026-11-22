import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import StatisticsPage from './StatisticsPage.jsx';
import { useAuthStore } from '../auth/authStore.js';
import { api } from '../../services/api.js';
import { normalStatisticsFixture, emptyStatisticsFixture } from '../../../dev-mocks/statistics.js';
import '../../index.css';

const mixedStatisticsFixture = {
  total_sessions: 6,
  in_progress_sessions: 1,
  approved_not_exported_sessions: 1,
  exported_sessions: 1,
  by_status: {
    draft: 0,
    blueprinted: 0,
    configured: 0,
    generating: 0,
    partial_generated: 0,
    generated: 1,
    reviewed: 0,
    approved: 1,
    exported: 1,
    failed: 2,
    unknown: 1,
  },
};

const scenarios = {
  normal: {
    label: 'Thông thường (23 phiên đề)',
    handler: async (config) => ({ status: 200, config, data: normalStatisticsFixture, headers: {} }),
  },
  mixed: {
    label: 'Hỗn hợp có lỗi (6 phiên, 2 lỗi, 1 chưa xác định)',
    handler: async (config) => ({ status: 200, config, data: mixedStatisticsFixture, headers: {} }),
  },
  empty: {
    label: 'Tài khoản mới (0 phiên đề)',
    handler: async (config) => ({ status: 200, config, data: emptyStatisticsFixture, headers: {} }),
  },
  error: {
    label: 'Lỗi kết nối máy chủ (503)',
    handler: async () => Promise.reject(new Error('Network error: 503 Service Unavailable')),
  },
};

function StatisticsPreview() {
  const [scenario, setScenario] = useState(() => {
    const param = typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('scenario')
      : null;
    return param && scenarios[param] ? param : 'normal';
  });

  useEffect(() => {
    // Seed authenticated mock user for preview
    useAuthStore.getState().setUser({
      id: 'teacher-preview-001',
      name: 'Cô Nguyễn Thị Mai',
    });

    const originalAdapter = api.defaults.adapter;
    api.defaults.adapter = async (config) => {
      if (config.url === '/users/me/statistics') {
        return scenarios[scenario].handler(config);
      }
      return originalAdapter ? originalAdapter(config) : Promise.reject(new Error('Not found'));
    };

    return () => {
      api.defaults.adapter = originalAdapter;
    };
  }, [scenario]);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <aside className="border-b border-line bg-surface/90 backdrop-blur-sm px-4 py-3 shadow-soft sticky top-0 z-40">
        <div className="mx-auto max-w-[1160px] flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-bold text-highlight uppercase tracking-wider">DEV PREVIEW</span>
            <span className="text-muted">· Xem thử giao diện Thống kê</span>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="scenario-select" className="font-medium text-muted">
              Tình huống:
            </label>
            <select
              id="scenario-select"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              className="rounded-lg border border-line bg-surface px-3 py-1 font-semibold text-strong shadow-soft focus:outline-none focus:ring-2 focus:ring-highlight"
            >
              {Object.entries(scenarios).map(([key, s]) => (
                <option key={key} value={key}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </aside>

      <MemoryRouter initialEntries={['/statistics']}>
        <Routes>
          <Route path="/statistics" element={<StatisticsPage key={scenario} />} />
          <Route
            path="/dashboard"
            element={
              <div className="mx-auto max-w-xl p-8 text-center">
                <h1 className="text-xl font-bold">Thư viện đề (Mock Target)</h1>
                <p className="mt-2 text-sm text-muted">Đã điều hướng thành công về /dashboard</p>
              </div>
            }
          />
        </Routes>
      </MemoryRouter>
    </div>
  );
}

if (import.meta.env.DEV) {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <StatisticsPreview />
    </StrictMode>,
  );
}
